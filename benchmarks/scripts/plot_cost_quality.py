#!/usr/bin/env python3
"""Render a cost-vs-quality scatter (with a Pareto frontier) from run artifacts.

Reads the scored benchmark runs under ``swe-benchmark-data/`` and plots one point
per model: mean cost per task on the x-axis, mean task score (the same 0-100
scores shown in the README leaderboard) on the y-axis. Non-dominated models --
those where no other model is both cheaper and higher-scoring -- are connected by
a highlighted frontier line, so the cost/quality trade-off is read at a glance.

Each model's numbers come from its committed ``run-summary.json`` when present
(the reproducible, machine-readable per-run record written by
``summarize_run.py``), falling back to aggregating the per-task ``metrics.json``
(``total_cost_usd``) and ``eval.json`` (``task_score``) when it is not. Using the
summary means the chart plots every model in the repo -- including runs produced
on a different node whose gitignored per-task files are not present locally. A
task that scored 0 (a model failure -- missing artifacts) is an unresolved
anomaly, not a quality reading, so it is EXCLUDED from both the score and cost
means and noted on the chart, pending investigation.

Cost is HARDWARE-DERIVED, not token-priced: when a model has a throughput sweep
(``self-hosted/vllm/benchmark-output/throughput/<model>/performance-summary.json``)
its cost per task is the cheapest blended $/token there (instance $/hr / measured
tokens/sec) times this run's actual input+output tokens per task, averaged over
the non-failed tasks. Only when no performance summary exists does it fall back
to run-summary's token-priced ``total_cost_usd`` estimate.

Usage:
    uv run scripts/plot_cost_quality.py
    uv run scripts/plot_cost_quality.py --repo mcp-gateway-registry --dark
    uv run scripts/plot_cost_quality.py --data-dir ../swe-benchmark-data --out chart.png
"""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: render to file, never a display
import matplotlib.pyplot as plt  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BENCHMARKS_DIR = _SCRIPTS_DIR.parent
_REPO_ROOT = _BENCHMARKS_DIR.parent
DEFAULT_DATA_DIR = _BENCHMARKS_DIR / "swe-benchmark-data"
DEFAULT_IMAGES_DIR = _REPO_ROOT / "docs" / "images"
# Machine-readable frontier data lives apart from the rendered images.
DEFAULT_METRICS_DIR = _REPO_ROOT / "docs" / "metrics"
METRICS_FILENAME = "metrics.json"

# Short per-harness code used (with the skill) to suffix chart filenames so each
# agent+skill's chart is self-identifying and never overwrites another's
# (cost-quality-cc-swe2.png, cost-quality-pi-swe3.png). An unknown harness falls
# back to its own slug.
HARNESS_CODES = {"claude-code": "cc", "pi": "pi", "opencode": "oc", "kiro-cli": "kiro"}
# Human-readable harness names for the chart title (the code is for filenames).
HARNESS_LABELS = {
    "claude-code": "Claude Code",
    "pi": "pi",
    "opencode": "opencode",
    "kiro-cli": "kiro-cli",
}

# Chart font sizes (points). Sized up for legibility when the chart is embedded
# in slides and social posts. The two footnotes stay at FOOTNOTE_FONTSIZE so the
# pricing-basis and excluded-task notes read as fine print, not body text.
TITLE_FONTSIZE = 19
AXIS_LABEL_FONTSIZE = 16
TICK_FONTSIZE = 14
POINT_LABEL_FONTSIZE = 14
LEGEND_FONTSIZE = 14
FOOTNOTE_FONTSIZE = 9


def _default_output(harness: str, skill: str, dark: bool) -> Path:
    """Committed docs/images path for a (harness, skill) cost-quality chart.

    Keyed by both harness and skill (e.g. cost-quality-cc-swe3.png), because
    swe2 and swe3 differ materially in tokens/accuracy and get separate charts.
    Defaults here so the chart the README embeds stays in sync when re-run.
    (swe-benchmark-data is gitignored; docs/images is tracked.)
    """
    code = HARNESS_CODES.get(harness, harness)
    suffix = "-dark" if dark else ""
    return DEFAULT_IMAGES_DIR / f"cost-quality-{code}-{skill}{suffix}.png"


EVAL_FILENAME = "eval.json"
# The committed, machine-readable per-run summary (written by summarize_run.py).
# Preferred source: it carries the same excluded-failure means as the leaderboard
# and, unlike the gitignored per-task metrics.json/eval.json, is present for every
# model in the repo -- including runs produced on a different node. This is what
# makes the chart reproducible from committed data alone.
RUN_SUMMARY_FILENAME = "run-summary.json"
# Hardware-derived per-token cost lives in the throughput sweep's summary, one
# per model. Cost per task = (this model's cheapest blended $/token) x (this
# run's actual input+output tokens for the task) -- so cost reflects BOTH the
# measured serving economics AND the real token load of the quality run, rather
# than the token-priced estimate that run-summary.total_cost_usd carries for
# self-hosted models. See self-hosted/vllm/cost-per-task-methodology.md.
PERF_SUMMARY_DIR = (
    _REPO_ROOT / "self-hosted" / "vllm" / "benchmark-output" / "throughput"
)
PERF_SUMMARY_FILENAME = "performance-summary.json"


def _blended_cost_per_token(model: str) -> float | None:
    """Return the cheapest blended $/token for a model from its perf summary.

    The blended lens charges every processed token (prompt + generation) the
    same measured GPU slice; the cheapest concurrency level is the model's best
    sustainable per-token cost on its benchmarked instance. Returns None when no
    performance summary exists for the model (e.g. not swept for throughput).
    """
    summary = _read_json(PERF_SUMMARY_DIR / model / PERF_SUMMARY_FILENAME)
    if summary is None:
        return None
    rates = [
        r["blended_cost_per_token_usd"]
        for r in summary.get("levels", [])
        if isinstance(r.get("blended_cost_per_token_usd"), (int, float))
    ]
    return min(rates) if rates else None


# Palette (from the dataviz skill's validated reference instance). Marks are a
# recessive dark neutral; the frontier is the warm accent. Text wears ink tokens.
_THEME = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e6e5e2",
        "dot": "#33322f",
        "accent": "#eb6834",
        "label_bg": "#ffffff",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "muted": "#c3c2b7",
        "grid": "#333330",
        "dot": "#d7d6cf",
        "accent": "#d95926",
        "label_bg": "#26262410",
    },
}


@dataclass
class ModelPoint:
    """One model's aggregate for the scatter.

    Means are over the tasks the model actually completed with a non-zero
    score. Zero-score tasks (a genuine model failure -- missing artifacts) are
    an unresolved anomaly, not a quality measurement, so they are excluded from
    both the score and cost means and surfaced separately (``excluded``) pending
    investigation.
    """

    model: str
    mean_cost: float
    mean_score: float
    n_tasks: int
    n_scored: int
    excluded: list[str]
    hosting: str = (
        "self-hosted"  # "Bedrock" (metered) or "self-hosted" (hardware-derived)
    )
    # The coding agent that produced the run. Empty on a single-harness chart
    # (its title already names the harness); set by the combined chart, which
    # reports it in the frontier JSON and folds it into ``label``.
    harness: str = ""
    # Optional ready-made chart label. ``model`` stays the identity used for
    # lookups and for every emitted JSON; only the drawn text changes. The
    # combined chart uses it to name both the model and the harness that won.
    label: str = ""


def _read_json(path: Path) -> dict | None:
    """Return the parsed JSON object at ``path``, or None if absent/invalid."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _task_score(eval_data: dict | None) -> float | None:
    """Extract ``task_score`` from an eval.json object, or None when missing."""
    if not eval_data:
        return None
    score = eval_data.get("task_score")
    return float(score) if isinstance(score, (int, float)) else None


def _point_from_summary(model_repo_dir: Path, model: str) -> ModelPoint | None:
    """Build a ModelPoint from the committed run-summary.json, if present.

    run-summary.json already carries the leaderboard-convention means (failed
    0-score tasks excluded) and is committed for every model, so it is the
    preferred, fully reproducible source. Returns None when the file is absent
    or lacks a usable mean score, so the caller can fall back to per-task files.

    Args:
        model_repo_dir: ``<data-dir>/<model>/<harness>/<repo>`` directory.
        model: The model-slug (passed in, not derived from the path, since the
            harness level now sits between the model and repo directories).

    Returns:
        The model's aggregate, or None if no usable summary exists.
    """
    summary = _read_json(model_repo_dir / RUN_SUMMARY_FILENAME)
    if summary is None:
        return None
    score = summary.get("mean_task_score_excl_failed")
    if not isinstance(score, (int, float)):
        return None
    excluded = summary.get("failed_tasks") or []

    # Cost: prefer the hardware-derived blended figure (per-token rate from the
    # throughput sweep x this run's actual per-task tokens, averaged over the
    # non-failed tasks). Fall back to run-summary's token-priced estimate only
    # when no performance summary exists for the model.
    cost = _blended_mean_cost(summary, model)
    if cost is None:
        est = summary.get("mean_cost_usd_excl_failed")
        cost = float(est) if isinstance(est, (int, float)) else 0.0

    hosting = "Bedrock" if summary.get("provider") == "bedrock" else "self-hosted"
    return ModelPoint(
        model=model,
        mean_cost=cost,
        mean_score=float(score),
        n_tasks=int(summary.get("num_tasks") or 0),
        n_scored=int(summary.get("num_scored") or 0),
        excluded=list(excluded),
        hosting=hosting,
    )


def _blended_mean_cost(summary: dict, model: str) -> float | None:
    """Mean blended cost per task from perf-summary per-token rate x run tokens.

    Uses the model's cheapest blended $/token (hardware-derived, from the
    throughput sweep) and this run's actual input+output tokens per task,
    averaged over the tasks that were NOT failed -- matching the score mean's
    exclusion convention. Returns None when the model has no performance summary
    (so the caller falls back to the token-priced estimate).
    """
    per_token = _blended_cost_per_token(model)
    if per_token is None:
        return None
    failed = set(summary.get("failed_tasks") or [])
    costs: list[float] = []
    for task in summary.get("tasks", []):
        if task.get("failed") or task.get("task") in failed:
            continue
        # Price ALL processed tokens (input + output + cache read + write), not
        # just input+output. The blended rate was measured over every token the
        # server processed, so the count must match. This also keeps pi and
        # claude-code consistent: pi reports vLLM cache tokens in cache_read/
        # cache_write, while claude-code folds them into input_tokens (its
        # cache_read is 0) -- the two agree only on the total-processed sum.
        tokens = (
            (task.get("input_tokens") or 0)
            + (task.get("output_tokens") or 0)
            + (task.get("cache_read_tokens") or 0)
            + (task.get("cache_write_tokens") or task.get("cache_creation_tokens") or 0)
        )
        if tokens > 0:
            costs.append(tokens * per_token)
    return sum(costs) / len(costs) if costs else None


def _aggregate_model(model_repo_dir: Path, model: str) -> ModelPoint | None:
    """Aggregate one model's cost and score under a repo directory.

    Prefers the committed ``run-summary.json`` (present for every model and
    reproducible from git). Falls back to aggregating the per-task
    ``metrics.json`` / ``eval.json`` when no summary exists (e.g. a fresh run
    not yet summarized). Tasks that scored 0 -- a genuine model failure
    (missing/empty artifacts) rather than a quality measurement -- are
    **excluded** from both means and returned in ``excluded`` for a visible
    note, pending investigation.

    Args:
        model_repo_dir: ``<data-dir>/<model>/<harness>/<repo>`` directory.
        model: The model-slug (passed in, not derived from the path).

    Returns:
        The model's aggregate, or None if it has neither a summary nor tasks.
    """
    from_summary = _point_from_summary(model_repo_dir, model)
    if from_summary is not None:
        return from_summary

    costs: list[float] = []
    scores: list[float] = []
    excluded: list[str] = []
    n_tasks = 0
    for task_dir in sorted(p for p in model_repo_dir.iterdir() if p.is_dir()):
        metrics = _read_json(task_dir / METRICS_FILENAME)
        if metrics is None:
            continue
        n_tasks += 1
        score = _task_score(_read_json(task_dir / EVAL_FILENAME))
        # A 0 (or unscored) task is a model failure, not a quality signal:
        # exclude it from both means and note it separately.
        if not score:
            excluded.append(task_dir.name)
            continue
        cost = metrics.get("total_cost_usd")
        costs.append(float(cost) if isinstance(cost, (int, float)) else 0.0)
        scores.append(score)
    if n_tasks == 0:
        return None
    return ModelPoint(
        model=model,
        mean_cost=sum(costs) / len(costs) if costs else 0.0,
        mean_score=sum(scores) / len(scores) if scores else 0.0,
        n_tasks=n_tasks,
        n_scored=len(scores),
        excluded=excluded,
    )


def _collect_points(
    data_dir: Path, repo: str, harness: str, skill: str
) -> list[ModelPoint]:
    """Collect one ModelPoint per model that has ``harness`` runs for ``repo``.

    Artifacts live at ``<data-dir>/<model>/<harness>/<repo>/``; this plots the
    results from one coding agent (harness) at a time so a model's Claude Code
    and pi runs are never blended on the same chart.

    Args:
        data_dir: The ``swe-benchmark-data`` root.
        repo: The dataset repo subfolder to aggregate (e.g. mcp-gateway-registry).
        harness: The coding-agent folder to read (e.g. ``claude-code`` or ``pi``).

    Returns:
        Model aggregates sorted by descending mean score.

    Raises:
        SystemExit: If no model has scorable runs for the repo under this harness.
    """
    points: list[ModelPoint] = []
    for model_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        repo_dir = model_dir / harness / skill / repo
        if not repo_dir.is_dir():
            continue
        point = _aggregate_model(repo_dir, model_dir.name)
        if point is None:
            continue
        # A model that never produced a scored task (e.g. one that could not be
        # served at a usable context window on this node) is "not viable", not a
        # $0 / 0% data point -- excluding it keeps it off the frontier. Log the
        # skip so the omission is explicit, never silent.
        if point.n_scored == 0:
            logger.warning(
                "  excluding %s: no scored tasks (not a viable run to plot)",
                point.model,
            )
            continue
        points.append(point)
    if not points:
        raise SystemExit(
            f"no scorable runs found under {data_dir} for repo '{repo}' with "
            f"harness '{harness}'. Run the benchmark and judge first."
        )
    return sorted(points, key=lambda p: p.mean_score, reverse=True)


def _pareto_frontier(points: list[ModelPoint]) -> list[ModelPoint]:
    """Return the non-dominated points: cheapest-and-best trade-off curve.

    A point dominates another when it is both no more expensive and no
    lower-scoring, and strictly better on at least one axis. The frontier is the
    set of points nothing dominates, ordered by ascending cost for drawing.

    Args:
        points: All model aggregates.

    Returns:
        The frontier points, ordered by ascending mean cost.
    """
    frontier: list[ModelPoint] = []
    for candidate in points:
        dominated = any(
            other is not candidate
            and other.mean_cost <= candidate.mean_cost
            and other.mean_score >= candidate.mean_score
            and (
                other.mean_cost < candidate.mean_cost
                or other.mean_score > candidate.mean_score
            )
            for other in points
        )
        if not dominated:
            frontier.append(candidate)
    return sorted(frontier, key=lambda p: p.mean_cost)


def _point_dict(p: ModelPoint) -> dict:
    """Serialize one model point for the frontier JSON."""
    entry = {
        "model": p.model,
        "mean_score": round(p.mean_score, 2),
        "mean_cost_per_task": round(p.mean_cost, 4),
        "hosting": p.hosting,
        "n_scored": p.n_scored,
        "n_tasks": p.n_tasks,
        "completed": f"{p.n_scored}/{p.n_tasks}",
        "excluded_tasks": p.excluded,
    }
    # Only the combined chart sets a harness; omitting the key elsewhere keeps
    # the existing per-harness JSONs byte-identical.
    if p.harness:
        entry["harness"] = p.harness
    return entry


def _write_frontier_json(
    points: list[ModelPoint], *, harness: str, skill: str, repo: str, out_dir: Path
) -> Path:
    """Emit the Pareto frontier (score vs cost/task) as machine-readable JSON.

    Reuses the SAME ``_pareto_frontier`` that draws the cost-quality chart, so
    the file and the chart never diverge. Emits three frontiers: the combined
    set (labelled as a cross-hosting view, non-authoritative on raw dollars) and
    one per hosting basis (Bedrock-only, self-hosted-only) -- the honest
    like-for-like comparisons, since a metered API bill and a hardware-derived
    figure are not comparable as raw dollars (see cost-per-task-methodology.md).
    """
    bedrock = [p for p in points if p.hosting == "Bedrock"]
    selfh = [p for p in points if p.hosting != "Bedrock"]
    payload = {
        "note": (
            "Pareto frontier (mean score vs mean cost/task) behind "
            f"docs/images/cost-quality-*-{skill}.png. Emitted by plot_cost_quality.py. "
            "A model is on a frontier when nothing scores at least as high for at "
            "most the cost. Use the per-hosting frontiers for cost claims; the "
            "combined frontier mixes a metered Bedrock bill with a hardware-derived "
            "self-hosted figure and is directional only (see "
            "cost-per-task-methodology.md)."
        ),
        "harness": harness,
        "skill": skill,
        "repo": repo,
        "frontier_rule": "non-dominated on (max score, min cost/task)",
        "combined_frontier_cross_hosting_directional": [
            _point_dict(p) for p in _pareto_frontier(points)
        ],
        "bedrock_frontier": [_point_dict(p) for p in _pareto_frontier(bedrock)],
        "self_hosted_frontier": [_point_dict(p) for p in _pareto_frontier(selfh)],
        "all_models": [
            _point_dict(p) for p in sorted(points, key=lambda p: -p.mean_score)
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = (
        out_dir / f"pareto-frontier-{HARNESS_CODES.get(harness, harness)}-{skill}.json"
    )
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("wrote %s", out_path)
    return out_path


def _point_name(point: ModelPoint) -> str:
    """Name a point: its caller-supplied label, else the bare model slug.

    A single-harness chart names its harness in the title, so the model alone
    reads best there. The combined chart mixes harnesses and supplies a label
    naming both.
    """
    return point.label or point.model


def _label(point: ModelPoint) -> str:
    """Build a point label; mark models whose mean excludes a failed task."""
    name = _point_name(point)
    if point.excluded:
        return f"{name}*"
    return name


def _spread(ys: list[float], step: float) -> list[float]:
    """Push a sorted-ascending list apart to >= ``step`` spacing, keeping center.

    A single bottom-up pass raises each value to clear the one below it, which
    drifts the whole group upward; subtracting the net mean shift re-centers it
    on the original cluster. Inputs must be sorted ascending.
    """
    out = list(ys)
    for i in range(1, len(out)):
        out[i] = max(out[i], out[i - 1] + step)
    drift = sum(out) / len(out) - sum(ys) / len(ys)
    return [y - drift for y in out]


def _label_sides(
    ax, fig, points: list[ModelPoint], offsets: dict[int, float], label_chars: int
) -> dict[int, str]:
    """Choose which side of its dot each label sits on.

    ``_label_offsets`` only keeps labels from overlapping EACH OTHER; a label
    can still be drawn straight across another model's marker, which reads as
    if it belonged to that dot. Any label whose text would run over another
    point is flipped to the left of its own dot instead.

    Args:
        ax: The axes (already drawn, so transforms are valid).
        fig: The figure (for the pixel <-> point conversion).
        points: All model aggregates.
        offsets: The vertical offsets from ``_label_offsets``, in points.
        label_chars: Typical label length, used to estimate text width.

    Returns:
        ``{id(point): "left" | "right"}``.
    """
    to_px = ax.transData.transform
    px = {id(p): to_px((p.mean_cost, p.mean_score)) for p in points}
    text_w = 12 + POINT_LABEL_FONTSIZE * 0.6 * label_chars
    half_line = POINT_LABEL_FONTSIZE * 1.35 * fig.dpi / 72.0 * 0.5
    # Flipping left is only an option while the text still fits inside the axes;
    # past that it would run out over the y-axis instead.
    left_edge_px = ax.transAxes.transform((0.0, 0.0))[0]
    sides: dict[int, str] = {}
    for point in points:
        x_px, y_px = px[id(point)]
        label_y = y_px + offsets[id(point)] * fig.dpi / 72.0
        collides = any(
            other is not point
            and x_px < px[id(other)][0] <= x_px + text_w
            and abs(px[id(other)][1] - label_y) < half_line
            for other in points
        )
        room_on_left = x_px - text_w > left_edge_px
        sides[id(point)] = "left" if collides and room_on_left else "right"
    return sides


def _label_offsets(
    ax, fig, points: list[ModelPoint], label_chars: int = 22
) -> dict[int, float]:
    """Return each label's vertical offset (in points) to avoid overlaps.

    Labels sit to the right of their dot at the dot's y-level. Two labels collide
    only when they are close in BOTH axes -- near in x (their text would occupy
    the same horizontal band) and near in y (they would stack). This groups the
    points into such collision clusters and spreads ONLY those apart vertically,
    centered on the cluster; every isolated label keeps a 0 offset (stays pinned
    to its dot, no leader line). Offsets are returned in display points, keyed by
    ``id(point)``, so the caller can pass them straight to ``annotate`` and decide
    a leader line is needed exactly when the offset is non-zero.

    Args:
        ax: The axes (already drawn, so transforms are valid).
        fig: The figure (for DPI when converting pixels <-> points).
        points: All model aggregates.
        label_chars: Typical label length in characters, used to size the
            horizontal collision band. Charts with longer labels (the combined
            chart names a harness too) must raise it or wide labels will overlap
            without being detected as colliding.

    Returns:
        ``{id(point): dy_in_points}`` -- 0.0 for labels that did not move.
    """
    to_px = ax.transData.transform
    line_px = POINT_LABEL_FONTSIZE * 1.35 * fig.dpi / 72.0  # one label's height in px
    # Two labels collide when they share a horizontal band (near in x) AND sit
    # within ~1.6 line-heights in y. The x band is generous (a label is wide), so
    # a whole diagonal run of nearby dots merges into one cluster rather than
    # fragmenting into pairs that would still overlap each other.
    x_band_px = 12 + POINT_LABEL_FONTSIZE * 0.6 * label_chars  # gap + text width
    y_touch_px = line_px * 2.8
    px = {id(p): to_px((p.mean_cost, p.mean_score)) for p in points}

    # Union-find over "collides" (near in x AND y) to form clusters.
    parent = {id(p): id(p) for p in points}

    def find(a: int) -> int:
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    for i, a in enumerate(points):
        for b in points[i + 1 :]:
            ax_px, ay = px[id(a)]
            bx_px, by = px[id(b)]
            if abs(ax_px - bx_px) < x_band_px and abs(ay - by) < y_touch_px:
                parent[find(id(a))] = find(id(b))

    clusters: dict[int, list[ModelPoint]] = {}
    for p in points:
        clusters.setdefault(find(id(p)), []).append(p)

    offsets: dict[int, float] = {id(p): 0.0 for p in points}
    for members in clusters.values():
        if len(members) < 2:
            continue  # isolated label: no move, no line
        members.sort(key=lambda p: px[id(p)][1])  # by pixel-y, ascending
        ys_px = [px[id(p)][1] for p in members]
        spread_px = _spread(ys_px, line_px * 2.5)
        for p, new_y in zip(members, spread_px):
            # display-y grows downward in some backends; transData is bottom-up,
            # so a higher pixel value = higher on screen. Convert delta to points.
            offsets[id(p)] = (new_y - px[id(p)][1]) * 72.0 / fig.dpi
    return offsets


_DEFAULT_COST_BASIS_NOTE = (
    "Self-hosted cost basis: g6e = 3-year RI rate; p5en = on-demand x 35% "
    "placeholder discount (pay 65%) -- configurable in self-hosted/vllm/pricing.json."
)


def _plot(
    points: list[ModelPoint],
    frontier: list[ModelPoint],
    *,
    mode: str,
    title: str,
    cost_label: str,
    output: Path,
    frontier_label: str = "Cost/quality frontier",
    cost_basis_note: str = _DEFAULT_COST_BASIS_NOTE,
    leader_lines: bool = True,
    label_weight: str = "bold",
    marker_for: Callable[[ModelPoint], str] | None = None,
    color_for: Callable[[ModelPoint], str] | None = None,
    accent_color: str | None = None,
    extra_legend: list | None = None,
    label_backing: bool = True,
    log_x: bool = False,
    avoid_markers: bool = False,
    vertical_leaders: bool = False,
) -> None:
    """Render the scatter with its frontier and save to ``output``.

    Args:
        points: All model aggregates.
        frontier: The non-dominated subset (ascending cost).
        mode: "light" or "dark" theme.
        title: Chart title.
        cost_label: X-axis label (cost provenance is caller's responsibility).
        output: Destination image path.
        frontier_label: Legend text for the frontier line.
        cost_basis_note: Fine-print note naming the cost basis.
        leader_lines: Draw a thin line from a displaced label back to its dot.
            Off for charts whose labels are self-identifying enough not to need
            them.
        label_weight: Font weight for the point labels.
        marker_for: Optional per-point marker chooser; defaults to a circle for
            every point. The combined chart uses it to encode the harness.
        color_for: Optional per-point colour chooser. Without it a point is the
            warm accent when it sits on the frontier and a recessive neutral
            otherwise -- i.e. colour encodes rank. Supplying it moves colour
            onto the entity (the harness), leaving the frontier to be read from
            the line that connects its points.
        accent_color: Override the accent -- the frontier line AND the tint
            under it. They are one colour by design: the fill is the line at
            low alpha, which is what makes the shaded region read as belonging
            to the frontier rather than as a second, unexplained object.
        extra_legend: Optional extra legend handles, e.g. the marker key that
            says which shape is which harness.
        label_backing: Draw the surface-coloured plate behind each label. It
            keeps text readable where labels sit over the frontier fill; turn it
            off for a flatter look when labels clear the fill anyway.
        log_x: Put cost on a log scale. Cost spans nearly two orders of
            magnitude, so a linear axis crushes the cheapest models into the
            left margin, and their labels cannot sit beside their own dots.
        avoid_markers: Flip a label to the left of its dot when drawing it to
            the right would run the text across another model's marker.
        vertical_leaders: Centre a displaced label over its own dot so the
            leader line runs (near) vertically instead of diagonally. Reads as
            a tick up to the label rather than a wire across the plot.
    """
    theme = dict(_THEME[mode])
    if accent_color:
        theme["accent"] = accent_color
    fig, ax = plt.subplots(figsize=(16, 10), dpi=150)
    fig.patch.set_facecolor(theme["surface"])
    ax.set_facecolor(theme["surface"])
    if log_x:
        ax.set_xscale("log")

    # Frontier: a recessive accent line under the marks, filled to the baseline.
    if len(frontier) >= 2:
        fx = [p.mean_cost for p in frontier]
        fy = [p.mean_score for p in frontier]
        ax.plot(
            fx,
            fy,
            color=theme["accent"],
            linewidth=2,
            linestyle="--",
            marker="o",
            markersize=9,
            zorder=2,
            label=frontier_label,
        )
        # Gradient fill under frontier: strongest near the line, fading to
        # transparent at the bottom. Uses imshow with a vertical alpha gradient
        # clipped to the frontier polygon.
        import numpy as np
        from matplotlib.patches import PathPatch
        from matplotlib.path import Path as MplPath
        from matplotlib.colors import to_rgba

        y_bottom = min(p.mean_score for p in points) - 5
        # Build polygon: frontier line top, then straight down to bottom
        poly_x = fx + [fx[-1], fx[0]]
        poly_y = fy + [y_bottom, y_bottom]
        poly_verts = list(zip(poly_x, poly_y))
        if log_x:
            # imshow maps its extent linearly, so a log axis needs a plain fill.
            ax.fill_between(
                fx, fy, y_bottom, color=theme["accent"], alpha=0.08, zorder=1
            )
        poly_path = MplPath(poly_verts + [poly_verts[0]], closed=True)
        patch = PathPatch(poly_path, facecolor="none", edgecolor="none")
        ax.add_patch(patch)

        # Render gradient image clipped to the polygon
        x_min, x_max = min(fx), max(fx)
        y_min, y_max = y_bottom, max(fy)
        gradient = np.linspace(1, 0, 256).reshape(256, 1)
        accent_rgba = to_rgba(theme["accent"])
        ax.imshow(
            gradient,
            extent=[x_min, x_max, y_min, y_max],
            origin="upper",
            aspect="auto",
            cmap=None,
            vmin=0,
            vmax=1,
            alpha=0.12,
            zorder=1,
            interpolation="bicubic",
        )
        # Apply color by using a custom colormap from accent to transparent
        from matplotlib.colors import LinearSegmentedColormap

        accent_cmap = LinearSegmentedColormap.from_list(
            "accent_fade",
            [(*accent_rgba[:3], 0.15), (*accent_rgba[:3], 0.0)],
        )
        # Clear the plain imshow and redo with the colormap
        ax.images[-1].remove()
        im = ax.imshow(
            gradient,
            extent=[x_min, x_max, y_min, y_max],
            origin="upper",
            aspect="auto",
            cmap=accent_cmap,
            vmin=0,
            vmax=1,
            zorder=1,
            interpolation="bicubic",
        )
        im.set_clip_path(patch)
        if log_x:
            im.remove()
            patch.remove()

    # Dots now; labels later (after the limits are final) so the declutter pass
    # can measure real text height. Frontier points are already accent from the
    # frontier line; the rest are a recessive dark neutral.
    frontier_ids = {id(p) for p in frontier}
    for point in points:
        on_frontier = id(point) in frontier_ids
        ax.scatter(
            point.mean_cost,
            point.mean_score,
            s=90,
            marker=marker_for(point) if marker_for else "o",
            color=(
                color_for(point)
                if color_for
                else (theme["accent"] if on_frontier else theme["dot"])
            ),
            edgecolors=theme["surface"],
            linewidths=1.5,
            zorder=3,
        )

    ax.set_xlabel(
        cost_label, fontsize=AXIS_LABEL_FONTSIZE, color=theme["ink"], labelpad=10
    )
    ax.set_ylabel(
        "Mean task score (0-100)",
        fontsize=AXIS_LABEL_FONTSIZE,
        color=theme["ink"],
        labelpad=10,
    )
    ax.set_title(title, fontsize=TITLE_FONTSIZE, color=theme["ink"], pad=16, loc="left")

    ax.grid(True, color=theme["grid"], linewidth=0.5, alpha=0.6, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(theme["grid"])
    ax.tick_params(colors=theme["muted"], labelsize=TICK_FONTSIZE)
    if log_x:
        # A log axis defaults to decade ticks (10^0, 10^1), which is useless on
        # a chart whose whole point is the dollar figure. Label the 1-2-5 steps
        # in plain dollars instead.
        from matplotlib.ticker import FuncFormatter, LogLocator, NullFormatter

        ax.xaxis.set_major_locator(LogLocator(base=10.0, subs=(1.0, 2.0, 5.0)))
        ax.xaxis.set_major_formatter(
            FuncFormatter(lambda v, _: f"${v:g}" if v >= 1 else f"${v:.2f}")
        )
        ax.xaxis.set_minor_formatter(NullFormatter())

    # Headroom so labels near the axis edges do not clip.
    xs = [p.mean_cost for p in points]
    ys = [p.mean_score for p in points]
    xpad = max((max(xs) - min(xs)) * 0.12, 1.0)
    ypad = max((max(ys) - min(ys)) * 0.12, 3.0)
    if log_x:
        ax.set_xlim(min(xs) / 1.5, max(xs) * 2.6)
    else:
        ax.set_xlim(max(0.0, min(xs) - xpad), max(xs) + xpad * 2.2)
    ax.set_ylim(max(0.0, min(ys) - ypad), min(100.0, max(ys) + ypad))

    # Labels last, after the limits are final. Only labels that actually collide
    # (close in BOTH x and y) are spread apart in y, and only those get a leader
    # line back to the dot -- an isolated point keeps the plain right-of-dot
    # offset with no line. A draw() fixes the data<->pixel scale so a label's
    # rendered size can be expressed in data units.
    fig.canvas.draw()
    # Size the collision band to the longest label actually drawn, so the wider
    # labels of a combined chart are spread rather than left overlapping.
    longest = max((len(_label(p)) for p in points), default=22)
    label_chars = max(22, longest)
    dy_by_point = _label_offsets(ax, fig, points, label_chars=label_chars)
    sides = (
        _label_sides(ax, fig, points, dy_by_point, label_chars)
        if avoid_markers
        else {id(p): "right" for p in points}
    )
    # A centred label spans half its width each side of the dot, so it can only
    # be centred while both halves stay inside the axes.
    x0_px, x1_px = (
        ax.transAxes.transform((0.0, 0.0))[0],
        ax.transAxes.transform((1.0, 0.0))[0],
    )
    half_w_px = (POINT_LABEL_FONTSIZE * 0.6 * label_chars) / 2
    for point in points:
        dy_pts = dy_by_point[id(point)]
        moved = abs(dy_pts) > 1e-6
        on_left = sides[id(point)] == "left"
        dot_x_px = ax.transData.transform((point.mean_cost, point.mean_score))[0]
        centred = (
            vertical_leaders
            and moved
            and leader_lines
            and dot_x_px - half_w_px > x0_px
            and dot_x_px + half_w_px < x1_px
        )
        ax.annotate(
            _label(point),
            (point.mean_cost, point.mean_score),
            textcoords="offset points",
            xytext=(0 if centred else (-12 if on_left else 12), dy_pts),
            fontsize=POINT_LABEL_FONTSIZE,
            fontweight=label_weight,
            color=theme["ink"],
            ha="center" if centred else ("right" if on_left else "left"),
            va="center",
            zorder=4,
            bbox=(
                {
                    "boxstyle": "round,pad=0.3",
                    "facecolor": theme["surface"],
                    "edgecolor": "none",
                    "alpha": 0.85,
                }
                if label_backing
                else None
            ),
            arrowprops=(
                {
                    "arrowstyle": "-",
                    "color": theme["muted"],
                    "linewidth": 0.6,
                    "shrinkA": 2,
                    "shrinkB": 3,
                }
                if moved and leader_lines
                else None
            ),
        )

    handles, _ = ax.get_legend_handles_labels()
    handles.extend(extra_legend or [])
    if handles:
        legend = ax.legend(
            handles=handles, loc="lower right", frameon=False, fontsize=LEGEND_FONTSIZE
        )
        for text in legend.get_texts():
            text.set_color(theme["muted"])

    # Pricing-basis note, shown prominently so no one misreads the dollars. For
    # self-hosted/mixed charts this states the g6e/p5en GPU rate basis; for a
    # kiro-cli chart (all points priced in Kiro credits) the caller passes the
    # credit-basis note instead. See _cost_basis_note / cost-per-task-methodology.md.
    fig.text(
        0.5,
        -0.02,
        cost_basis_note,
        ha="center",
        va="top",
        fontsize=FOOTNOTE_FONTSIZE,
        color=theme["muted"],
        wrap=True,
    )

    # Note any excluded failed tasks so the chart is self-explaining: a 0-score
    # (missing-artifact) task is a model failure, not a quality reading, so it is
    # left out of the means, pending investigation.
    excl_notes = [
        f"{_point_name(p)}: {', '.join(p.excluded)}" for p in points if p.excluded
    ]
    if excl_notes:
        note = (
            "* Mean excludes a failed task (0 score / missing artifacts), pending "
            "investigation -- " + "; ".join(excl_notes)
        )
        fig.text(
            0.5,
            -0.055,
            note,
            ha="center",
            va="top",
            fontsize=FOOTNOTE_FONTSIZE,
            color=theme["muted"],
            wrap=True,
        )

    fig.tight_layout()
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, facecolor=theme["surface"], bbox_inches="tight")
    plt.close(fig)
    logger.info(
        "wrote %s (%d models, %d on frontier)", output, len(points), len(frontier)
    )


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Plot a cost-vs-quality scatter with a Pareto frontier from "
        "benchmark run artifacts.",
        epilog="Example:\n"
        "  uv run scripts/plot_cost_quality.py --repo mcp-gateway-registry\n"
        "  uv run scripts/plot_cost_quality.py --dark --out chart-dark.png",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"swe-benchmark-data root (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--repo",
        default="mcp-gateway-registry",
        help="Dataset repo subfolder to aggregate (default: mcp-gateway-registry)",
    )
    parser.add_argument(
        "--harness",
        default="claude-code",
        help="Coding-agent folder to read: 'claude-code' (default) or 'pi'. "
        "Artifacts live at <model>/<harness>/<skill>/<repo>/.",
    )
    parser.add_argument(
        "--skill",
        default="swe3",
        help="SWE skill folder to read: 'swe3' (default) or 'swe2'. swe2 and swe3 "
        "get separate charts (they differ in tokens/accuracy).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output image path (default: docs/images/cost-quality-<code>.png, "
        "where <code> is the harness code, e.g. cc or pi; -dark suffix in dark mode)",
    )
    parser.add_argument(
        "--dark", action="store_true", help="Render the dark-mode theme"
    )
    parser.add_argument(
        "--metrics-dir",
        type=Path,
        default=DEFAULT_METRICS_DIR,
        help="Where to write the Pareto-frontier JSON (default: docs/metrics/).",
    )
    parser.add_argument(
        "--title",
        default=None,
        help="Override the chart title",
    )
    parser.add_argument(
        "--cost-label",
        # Basis-neutral: the chart mixes hardware-derived costs (self-hosted:
        # instance $/hr / measured tokens/sec) with real metered Bedrock bills
        # (Anthropic models). Naming one basis in the axis label misrepresents
        # the other, so the axis states only the quantity; provenance lives in
        # the caption/footnotes (see the README leaderboard notes).
        default=None,
        help="X-axis label; make cost provenance explicit. Defaults to a "
        "basis-appropriate label per harness (kiro-cli => Kiro credits).",
    )
    return parser.parse_args()


def main() -> None:
    """Aggregate the artifacts and render the cost-quality chart."""
    args = _parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    if not data_dir.is_dir():
        raise SystemExit(f"data dir not found: {data_dir}")

    mode = "dark" if args.dark else "light"
    output = args.out or _default_output(args.harness, args.skill, args.dark)
    # Title leads with the harness and skill (what the chart is OF); the repo and
    # its dataset provenance move into the frontier legend to declutter the title.
    harness_label = HARNESS_LABELS.get(args.harness, args.harness)
    title = args.title or f"Cost vs. quality -- {harness_label} harness, /{args.skill}"
    frontier_label = f"Cost/quality frontier ({args.repo})"

    # kiro-cli prices every point in Kiro credits (not GPU-seconds or a metered
    # Bedrock bill), so give it a credit-basis axis label and footnote instead of
    # the default self-hosted/Anthropic wording. See cost-per-task-methodology.md.
    is_kiro = args.harness == "kiro-cli"
    # Avoid two "$" in the kiro label: matplotlib treats a paired $...$ as a
    # MathText region (would italicize the text and drop the dollar signs), so
    # spell the credit rate as "USD" instead.
    cost_label = args.cost_label or (
        "Mean cost per task (USD) -- kiro-cli, Kiro credits at 0.04 USD/credit (see notes)"
        if is_kiro
        else "Mean cost per task ($) -- self-hosted hardware-derived; "
        "Anthropic metered (see notes)"
    )
    cost_basis_note = (
        "Cost basis: kiro-cli is priced in Kiro credits at $0.04/credit "
        "(configurable) -- see docs/cost-per-task-methodology.md."
        if is_kiro
        else _DEFAULT_COST_BASIS_NOTE
    )

    points = _collect_points(data_dir, args.repo, args.harness, args.skill)
    for point in points:
        logger.info(
            "  %-32s score=%.2f cost=$%.2f (%d/%d scored)",
            point.model,
            point.mean_score,
            point.mean_cost,
            point.n_scored,
            point.n_tasks,
        )
    frontier = _pareto_frontier(points)
    # Emit the machine-readable frontier once (light run), theme-independent.
    if not args.dark:
        _write_frontier_json(
            points,
            harness=args.harness,
            skill=args.skill,
            repo=args.repo,
            out_dir=args.metrics_dir.expanduser().resolve(),
        )
    _plot(
        points,
        frontier,
        mode=mode,
        title=title,
        cost_label=cost_label,
        output=output,
        frontier_label=frontier_label,
        cost_basis_note=cost_basis_note,
    )


if __name__ == "__main__":
    main()
