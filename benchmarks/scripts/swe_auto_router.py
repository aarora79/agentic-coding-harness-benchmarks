#!/usr/bin/env python3
"""Deterministic routing core for the /swe-auto skill.

The /swe-auto skill lets a developer hand over model selection: given a repo,
ref, and problem, a router model triages the task into a tier (frontier,
workhorse, or budget), and this module then does everything mechanical --
parse the measured Pareto frontier, map the tier to a quality band, and pick
the cheapest non-dominated model that clears that band. The model-driven triage
lives in the skill (SKILL.md); everything here is pure, deterministic, and unit
tested, so a given (frontier, tier, config) always yields the same choice.

This module is intentionally placed under ``benchmarks/scripts`` (not the skill
directory) so it can reuse the harness's own helpers and is covered by the
benchmarks project's ruff / mypy / pytest tooling. The skill invokes it with
``uv run scripts/swe_auto_router.py`` from the ``benchmarks/`` directory.

Run it directly to preview a routing decision without executing anything:

    uv run scripts/swe_auto_router.py select --tier workhorse \\
        --config ../.claude/skills/swe-auto/swe-auto.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Tiers in ascending capability order. Escalation walks this list toward the end;
# the router model classifies a task into exactly one of these.
TIER_BUDGET = "budget"
TIER_WORKHORSE = "workhorse"
TIER_FRONTIER = "frontier"
TIERS = (TIER_BUDGET, TIER_WORKHORSE, TIER_FRONTIER)

# Which list inside a pareto-frontier JSON each frontier_scope reads. The
# combined list mixes a metered Bedrock bill with a hardware-derived self-hosted
# figure, so it is directional for cost; the per-hosting lists are apples-to-apples.
FRONTIER_SCOPE_KEYS = {
    "combined": "combined_frontier_cross_hosting_directional",
    "bedrock-only": "bedrock_frontier",
    "self-hosted-only": "self_hosted_frontier",
}
VALID_FRONTIER_SCOPES = set(FRONTIER_SCOPE_KEYS)

# budget_posture shifts the budget / workhorse quality floors up or down by
# ``posture_shift_points`` (frontier is always "the top model", so it is never
# shifted). "cheap" lowers the bar (accept a cheaper, lower-scoring model),
# "best" raises it, "balanced" leaves the configured floors as-is.
POSTURE_SIGN = {"cheap": -1, "balanced": 0, "best": 1}
VALID_POSTURES = set(POSTURE_SIGN)

# Illustrative default quality bands (see issue #123). frontier is None, meaning
# "pick the top-scoring model regardless of cost". Calibrate against real frontier
# data; every value is overridable in swe-auto.yaml.
DEFAULT_TIER_BANDS: dict[str, float | None] = {
    TIER_BUDGET: 47.0,
    TIER_WORKHORSE: 54.0,
    TIER_FRONTIER: None,
}

# Canonical source of truth for the frontier: the committed JSON on the default
# branch, served raw. A local docs/metrics copy is only a fallback.
_FRONTIER_RAW_BASE = (
    "https://raw.githubusercontent.com/aarora79/"
    "agentic-coding-harness-benchmarks/main/docs/metrics"
)
# harness config value -> the short code used in the frontier filenames.
_HARNESS_FRONTIER_CODE = {"claude-code": "cc", "pi": "pi", "kiro-cli": "kiro"}
# harness config value -> the run-swe-headless.py --agent value.
_HARNESS_AGENT = {"claude-code": "claude", "pi": "pi", "kiro-cli": "kiro"}
VALID_HARNESSES = set(_HARNESS_FRONTIER_CODE)

_FRONTIER_FETCH_TIMEOUT_SECONDS = 15


class RouterError(Exception):
    """Raised when config, frontier data, or a routing request is invalid."""


class ModelExecution(BaseModel):
    """How to actually run one selectable model through the headless runner.

    The frontier lists short model slugs (e.g. ``claude-opus-5``); the executor
    needs a provider, the wire model id, and (for an endpoint) a base URL. This
    maps a frontier slug to that execution recipe. A model absent from the
    registry is treated as not runnable and is skipped during selection, so the
    router never picks a model it cannot actually launch.
    """

    model_config = ConfigDict(extra="forbid")

    provider: str = Field(
        description="run-swe-headless --provider: 'bedrock' or 'endpoint'."
    )
    model: str = Field(
        description="Wire model id passed to --model (e.g. a Bedrock inference "
        "profile such as us.anthropic.claude-opus-5, or a vLLM served-model-name)."
    )
    endpoint: str | None = Field(
        default=None,
        description="Base URL for provider=endpoint (a running vLLM/gateway). "
        "Required for endpoint; ignored for bedrock.",
    )


# Built-in execution recipes for the known Bedrock Anthropic frontier models, so
# the Bedrock path needs ZERO registry config. The frontier lists the short slug
# (e.g. claude-opus-5); Bedrock needs the inference-profile id. A user's
# model_execution entry overrides these; an unknown Bedrock "claude-*" slug is
# derived as us.anthropic.<slug> (see resolve_execution).
_BUILTIN_EXECUTION: dict[str, ModelExecution] = {
    "claude-opus-5": ModelExecution(
        provider="bedrock", model="us.anthropic.claude-opus-5"
    ),
    "claude-sonnet-5": ModelExecution(
        provider="bedrock", model="us.anthropic.claude-sonnet-5"
    ),
    "claude-opus-4-8": ModelExecution(
        provider="bedrock", model="us.anthropic.claude-opus-4-8"
    ),
    "claude-haiku-4-5": ModelExecution(
        provider="bedrock", model="us.anthropic.claude-haiku-4-5-20251001-v1:0"
    ),
}


class SweAutoConfig(BaseModel):
    """Routing knobs for /swe-auto, read from swe-auto.yaml in the skill's dir.

    The task itself (repo, ref, problem) is never in this file; it is always a
    user argument to the skill. Only routing behavior lives here.
    """

    model_config = ConfigDict(extra="forbid")

    router_model: str = Field(
        default="claude-opus-5",
        description="Model that triages/classifies the task into a tier.",
    )
    harness: str = Field(
        default="pi",
        description="Which agent the executor runs /swe3 under (claude-code | pi). "
        "Defaults to pi: single-agent, typically faster and cheaper per task.",
    )
    skill: str = Field(default="swe3", description="Executed SWE skill (swe3 in v1).")
    frontier_file: str | None = Field(
        default=None,
        description="Frontier JSON URL or local path. Defaults to the canonical "
        "GitHub raw URL for this harness+skill; a local docs/metrics copy is the "
        "fallback.",
    )
    frontier_scope: str = Field(
        default="combined",
        description="Which frontier list to read: combined | bedrock-only | "
        "self-hosted-only.",
    )
    budget_posture: str = Field(
        default="balanced",
        description="Shifts the per-tier quality bar: cheap | balanced | best.",
    )
    posture_shift_points: float = Field(
        default=5.0,
        ge=0.0,
        description="How many score points 'cheap'/'best' move the budget and "
        "workhorse floors.",
    )
    judge: bool = Field(
        default=True,
        description="Run the judge to score the executed run (produces eval.json).",
    )
    max_escalations: int = Field(
        default=1,
        ge=0,
        description="How many times the router may escalate one tier and re-run.",
    )
    reliability_gating: bool = Field(
        default=True,
        description="Prefer models that completed every task in the frontier "
        "data; fall back to partial-completion models only if none qualify.",
    )
    runner_path: str | None = Field(
        default=None,
        description="Path to the in-repo run-swe-headless.py. Defaults to the "
        "sibling in benchmarks/scripts. (Pinned-install support is a follow-up; "
        "v1 runs the in-repo runner in place.)",
    )
    aws_region: str | None = Field(
        default=None,
        description="AWS region for the Bedrock executor path. Falls back to the "
        "AWS_REGION/AWS_DEFAULT_REGION environment when unset.",
    )
    tier_bands: dict[str, float | None] = Field(
        default_factory=lambda: dict(DEFAULT_TIER_BANDS),
        description="Minimum mean score each tier must clear. frontier=None means "
        "'the top-scoring model regardless of cost'.",
    )
    model_execution: dict[str, ModelExecution] = Field(
        default_factory=dict,
        description="Frontier model slug -> how to run it (provider/model/endpoint). "
        "Only models present here are selectable, so the router never picks a "
        "model it cannot launch.",
    )

    @property
    def agent(self) -> str:
        """The run-swe-headless.py --agent value for the configured harness."""
        return _HARNESS_AGENT[self.harness]

    def validate_semantics(self) -> None:
        """Check enum-valued fields the type system cannot.

        Raises:
            RouterError: If a value is outside its allowed set.
        """
        if self.harness not in VALID_HARNESSES:
            raise RouterError(
                f"harness '{self.harness}' not in {sorted(VALID_HARNESSES)}."
            )
        if self.frontier_scope not in VALID_FRONTIER_SCOPES:
            raise RouterError(
                f"frontier_scope '{self.frontier_scope}' not in "
                f"{sorted(VALID_FRONTIER_SCOPES)}."
            )
        if self.budget_posture not in VALID_POSTURES:
            raise RouterError(
                f"budget_posture '{self.budget_posture}' not in {sorted(VALID_POSTURES)}."
            )
        for tier in TIERS:
            if tier not in self.tier_bands:
                raise RouterError(f"tier_bands is missing the '{tier}' tier.")


class FrontierEntry(BaseModel):
    """One model's position on a frontier list (a row of the frontier JSON)."""

    model_config = ConfigDict(extra="ignore")

    model: str
    mean_score: float
    mean_cost_per_task: float
    hosting: str
    n_scored: int = 0
    n_tasks: int = 0
    completed: str | None = None

    @property
    def is_full(self) -> bool:
        """True when the model scored on every task in the frontier data."""
        return self.n_tasks > 0 and self.n_scored == self.n_tasks

    @property
    def pricing_basis(self) -> str:
        """Cost basis implied by hosting: metered (Bedrock) vs hardware-derived."""
        return (
            "metered"
            if self.hosting.lower().startswith("bedrock")
            else "hardware-derived"
        )


class Selection(BaseModel):
    """The outcome of one selection pass for a given tier."""

    model_config = ConfigDict(extra="forbid")

    tier: str
    band_floor: float | None
    selected_model: str | None
    selected_entry: FrontierEntry | None
    clears_band: bool
    candidates_considered: list[str]
    rationale: str


def _default_frontier_url(harness: str, skill: str) -> str:
    """Return the canonical GitHub raw URL for a harness+skill frontier JSON."""
    code = _HARNESS_FRONTIER_CODE[harness]
    return f"{_FRONTIER_RAW_BASE}/pareto-frontier-{code}-{skill}.json"


def _local_frontier_path(harness: str, skill: str) -> Path:
    """Return the in-repo docs/metrics fallback path for a frontier JSON."""
    code = _HARNESS_FRONTIER_CODE[harness]
    repo_root = Path(__file__).resolve().parent.parent.parent
    return repo_root / "docs" / "metrics" / f"pareto-frontier-{code}-{skill}.json"


def _band_floor(tier: str, config: SweAutoConfig) -> float | None:
    """Compute the quality floor a model must clear for a tier.

    The frontier tier has no numeric floor (None): it means "pick the top model".
    Budget and workhorse floors are shifted by the budget_posture: 'cheap' lowers
    the bar, 'best' raises it, 'balanced' leaves the configured value.

    Args:
        tier: One of TIERS.
        config: The routing config supplying the base bands and posture.

    Returns:
        The minimum mean score to clear, or None for the frontier tier.

    Raises:
        RouterError: If the tier is unknown.
    """
    if tier not in TIERS:
        raise RouterError(f"unknown tier '{tier}'; expected one of {list(TIERS)}.")
    base = config.tier_bands.get(tier, DEFAULT_TIER_BANDS[tier])
    if base is None:
        return None
    shift = POSTURE_SIGN[config.budget_posture] * config.posture_shift_points
    return max(0.0, base + shift)


def _pick_cheapest_clearing(
    entries: list[FrontierEntry], floor: float, prefer_full: bool
) -> tuple[FrontierEntry | None, str]:
    """Pick the cheapest entry whose score clears ``floor``.

    Reliability gating (``prefer_full``) first restricts to models that completed
    every task; if none of those clear the floor it falls back to all clearing
    models and says so. Ties on cost break toward the higher score.

    Args:
        entries: Runnable frontier entries.
        floor: Minimum mean score to clear.
        prefer_full: Restrict to fully-completed models when possible.

    Returns:
        A (chosen entry or None, note) pair.
    """
    clearing = [e for e in entries if e.mean_score >= floor]
    if not clearing:
        return None, f"no runnable model clears the {floor:.0f} band"
    note = ""
    pool = clearing
    if prefer_full:
        full = [e for e in clearing if e.is_full]
        if full:
            pool = full
        else:
            note = "no fully-completed model clears the band; using a partial-completion model"
    chosen = min(pool, key=lambda e: (e.mean_cost_per_task, -e.mean_score))
    return chosen, note


def _pick_top_score(entries: list[FrontierEntry]) -> tuple[FrontierEntry | None, str]:
    """Pick the highest-scoring entry (frontier tier); ties break toward cheaper."""
    if not entries:
        return None, "no runnable models on the frontier"
    chosen = max(entries, key=lambda e: (e.mean_score, -e.mean_cost_per_task))
    return chosen, "frontier tier: highest-scoring runnable model, cost no object"


def resolve_execution(
    config: SweAutoConfig, entry: FrontierEntry
) -> ModelExecution | None:
    """Resolve how to launch a frontier model, or None if it is not runnable.

    Resolution order: a user ``model_execution`` override wins; else a built-in
    Bedrock recipe; else, for an unknown Bedrock ``claude-*`` slug, the derived
    ``us.anthropic.<slug>`` inference profile. A self-hosted model with no
    override returns None -- it needs an endpoint the frontier cannot supply, so
    it is simply not selectable in this environment.

    Args:
        config: The routing config (its ``model_execution`` is the override layer).
        entry: The frontier entry to resolve.

    Returns:
        A ModelExecution recipe, or None when the model cannot be launched here.
    """
    override = config.model_execution.get(entry.model)
    if override is not None:
        return override
    builtin = _BUILTIN_EXECUTION.get(entry.model)
    if builtin is not None:
        return builtin
    if entry.hosting.lower().startswith("bedrock") and entry.model.startswith(
        "claude-"
    ):
        return ModelExecution(provider="bedrock", model=f"us.anthropic.{entry.model}")
    return None


def runnable_entries(
    entries: list[FrontierEntry], config: SweAutoConfig
) -> list[FrontierEntry]:
    """Filter frontier entries to those runnable in this environment.

    The frontier is the selectable universe; this keeps only the entries for
    which ``resolve_execution`` yields a launch recipe (Bedrock by default;
    self-hosted only when an endpoint is configured), so the router never selects
    a model it cannot actually run.
    """
    return [e for e in entries if resolve_execution(config, e) is not None]


def frontier_entries(frontier: dict[str, Any], scope: str) -> list[FrontierEntry]:
    """Parse the frontier list for a scope out of a loaded frontier JSON.

    Args:
        frontier: The parsed pareto-frontier JSON object.
        scope: One of VALID_FRONTIER_SCOPES.

    Returns:
        The frontier entries for that scope, as typed models.

    Raises:
        RouterError: If the scope is unknown or the list is missing/malformed.
    """
    if scope not in FRONTIER_SCOPE_KEYS:
        raise RouterError(
            f"frontier_scope '{scope}' not in {sorted(VALID_FRONTIER_SCOPES)}."
        )
    key = FRONTIER_SCOPE_KEYS[scope]
    raw = frontier.get(key)
    if not isinstance(raw, list):
        raise RouterError(f"frontier JSON has no '{key}' list for scope '{scope}'.")
    try:
        return [FrontierEntry.model_validate(row) for row in raw]
    except ValidationError as exc:
        raise RouterError(f"invalid frontier entry under '{key}': {exc}") from exc


def select_model(
    entries: list[FrontierEntry], tier: str, config: SweAutoConfig
) -> Selection:
    """Select the model for a tier from a list of candidate entries.

    Selection is pure over the candidates it is given: filter to runnable models
    with ``runnable_entries`` before calling this. Budget/workhorse tiers pick the
    cheapest candidate that clears the tier's (posture-shifted) quality floor,
    honoring reliability gating. The frontier tier picks the top-scoring candidate
    regardless of cost. When nothing clears the floor, the highest-scoring
    candidate is chosen as a best effort and ``clears_band`` is False so the caller
    can flag it.

    Args:
        entries: Candidate frontier entries (already filtered to runnable).
        tier: The tier the router model classified the task into.
        config: The routing config.

    Returns:
        A populated Selection.

    Raises:
        RouterError: If the tier is unknown or there are no candidates.
    """
    floor = _band_floor(tier, config)
    considered = [e.model for e in entries]
    if not entries:
        raise RouterError(
            "no candidate models to select from: no frontier model is runnable in "
            "this environment (configure model_execution / an endpoint in swe-auto.yaml)."
        )
    runnable = entries
    if floor is None:
        chosen, note = _pick_top_score(runnable)
        clears = chosen is not None
    else:
        chosen, note = _pick_cheapest_clearing(
            runnable, floor, config.reliability_gating
        )
        clears = chosen is not None
        if chosen is None:
            chosen, _ = _pick_top_score(runnable)
            note = (
                f"{note}; falling back to the highest-scoring runnable model "
                f"({chosen.model if chosen else 'none'}), which does NOT clear the band"
            )
    floor_txt = "top model" if floor is None else f">= {floor:.0f}"
    rationale = (
        f"tier={tier} (band {floor_txt}), scope={config.frontier_scope}, "
        f"posture={config.budget_posture}: {note}"
    )
    return Selection(
        tier=tier,
        band_floor=floor,
        selected_model=chosen.model if chosen else None,
        selected_entry=chosen,
        clears_band=clears,
        candidates_considered=considered,
        rationale=rationale,
    )


def next_tier(tier: str) -> str | None:
    """Return the next tier up for escalation, or None if already at the top."""
    if tier not in TIERS:
        raise RouterError(f"unknown tier '{tier}'; expected one of {list(TIERS)}.")
    index = TIERS.index(tier)
    return TIERS[index + 1] if index + 1 < len(TIERS) else None


def load_config(
    path: str | Path | None, overrides: dict[str, Any] | None = None
) -> SweAutoConfig:
    """Load swe-auto.yaml and apply CLI overrides (CLI wins).

    Args:
        path: Path to the config YAML, or None to build from defaults+overrides.
        overrides: CLI-supplied values; None entries are ignored.

    Returns:
        A validated SweAutoConfig.

    Raises:
        RouterError: If the file is missing, unparseable, or invalid.
    """
    overrides = overrides or {}
    if path is None:
        raw: dict[str, Any] = {}
    else:
        file_path = Path(path)
        if not file_path.exists():
            raise RouterError(f"config not found: {file_path}")
        try:
            loaded = yaml.safe_load(file_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise RouterError(f"failed to parse {file_path}: {exc}") from exc
        if loaded is None:
            raw = {}
        elif isinstance(loaded, dict):
            raw = loaded
        else:
            raise RouterError(f"{file_path}: top level must be a mapping")
    merged = {**raw, **{k: v for k, v in overrides.items() if v is not None}}
    try:
        config = SweAutoConfig.model_validate(merged)
    except ValidationError as exc:
        raise RouterError(f"invalid swe-auto config:\n{exc}") from exc
    config.validate_semantics()
    return config


def load_frontier(config: SweAutoConfig) -> tuple[dict[str, Any], dict[str, str]]:
    """Load the frontier JSON, preferring the canonical URL with a local fallback.

    Args:
        config: The routing config (its frontier_file, harness, and skill decide
            what to load).

    Returns:
        A (frontier dict, provenance) pair. ``provenance`` records
        ``frontier_file``, ``frontier_source`` (github-raw | local | local-fallback |
        explicit-url | explicit-path), and a ``stale`` warning string when the
        canonical URL could not be reached and a local copy was used instead.

    Raises:
        RouterError: If neither the configured source nor the local fallback
            yields a usable frontier JSON.
    """
    explicit = config.frontier_file
    url = explicit or _default_frontier_url(config.harness, config.skill)
    local = _local_frontier_path(config.harness, config.skill)

    if explicit and not explicit.startswith(("http://", "https://")):
        # An explicit local path: read it directly, no network.
        data = _read_json_file(Path(explicit))
        if data is None:
            raise RouterError(f"frontier file not readable: {explicit}")
        return data, {"frontier_file": explicit, "frontier_source": "explicit-path"}

    data = _fetch_json_url(url)
    if data is not None:
        source = "explicit-url" if explicit else "github-raw"
        return data, {"frontier_file": url, "frontier_source": source}

    # Network unreachable: fall back to the committed local copy and flag it, so
    # routing.json honestly records that the frontier may lag the default branch.
    logger.warning("could not fetch frontier from %s; trying local copy %s", url, local)
    data = _read_json_file(local)
    if data is None:
        raise RouterError(
            f"frontier unavailable: could not fetch {url} and no local copy at {local}."
        )
    return data, {
        "frontier_file": str(local),
        "frontier_source": "local-fallback",
        "stale": f"canonical URL {url} was unreachable; using local copy which may lag main",
    }


def _read_json_file(path: Path) -> dict[str, Any] | None:
    """Return the parsed JSON object at ``path``, or None if absent/invalid."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _fetch_json_url(url: str) -> dict[str, Any] | None:
    """Fetch and parse a JSON object from an http(s) URL, or None on any failure."""
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(  # nosec B310 - http(s) frontier URL, scheme checked by caller
            req, timeout=_FRONTIER_FETCH_TIMEOUT_SECONDS
        ) as resp:
            value = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments for the preview (select) command."""
    parser = argparse.ArgumentParser(
        description="Preview a /swe-auto routing decision for a tier.",
        epilog="Example:\n  uv run scripts/swe_auto_router.py select --tier workhorse "
        "--config ../.claude/skills/swe-auto/swe-auto.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "command", choices=("select",), help="What to do (select: preview a decision)."
    )
    parser.add_argument(
        "--tier", required=True, choices=TIERS, help="Tier the router classified into."
    )
    parser.add_argument("--config", help="Path to swe-auto.yaml.")
    parser.add_argument("--frontier-file", help="Override: frontier JSON URL or path.")
    parser.add_argument(
        "--frontier-scope", choices=sorted(VALID_FRONTIER_SCOPES), help="Override."
    )
    parser.add_argument(
        "--budget-posture", choices=sorted(VALID_POSTURES), help="Override."
    )
    parser.add_argument("--harness", choices=sorted(VALID_HARNESSES), help="Override.")
    return parser.parse_args()


def main() -> None:
    """Preview a routing decision: load config + frontier, select, print JSON."""
    args = _parse_args()
    overrides = {
        "frontier_file": args.frontier_file,
        "frontier_scope": args.frontier_scope,
        "budget_posture": args.budget_posture,
        "harness": args.harness,
    }
    try:
        config = load_config(args.config, overrides)
        frontier, provenance = load_frontier(config)
        entries = frontier_entries(frontier, config.frontier_scope)
        runnable = runnable_entries(entries, config)
        selection = select_model(runnable, args.tier, config)
    except RouterError as exc:
        logger.error("routing error: %s", exc)
        sys.exit(1)
    execution = (
        resolve_execution(config, selection.selected_entry)
        if selection.selected_entry
        else None
    )
    out = {
        "provenance": provenance,
        "selection": selection.model_dump(mode="json"),
        "execution": execution.model_dump(mode="json") if execution else None,
    }
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    main()
