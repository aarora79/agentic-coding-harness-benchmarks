#!/usr/bin/env python3
"""Run the SWE benchmark headless: drive `claude -p /swe2` over a dataset.

Given a dataset YAML and a runner config (endpoint, model, claude flags), this
harness runs each task end to end:

  1. Clone the task's repo at its pinned ref into a temporary directory.
  2. Invoke `claude -p "/swe2 repo: ... problem: ... model: ... answers: ..."`
     non-interactively, letting the /swe2 skill produce the four design
     artifacts (github-issue.md, lld.md, review.md, testing.md) AND implement
     the change, capturing patch.diff + implementation.md.
  3. Parse the run's JSON result for the six benchmark metrics (input/output/
     cache tokens, latency, and the number of LLM turns the agent took) and
     write them to metrics.json next to the artifacts.

Routing and claude flags come from the runner config; any field may be
overridden on the command line (CLI wins).

Usage:
    uv run scripts/run-swe-headless.py --config config/runner.example.yaml
    uv run scripts/run-swe-headless.py --config config/runner.example.yaml \\
        --model qwen3-coder-30b --tasks remove-faiss
    uv run scripts/run-swe-headless.py --config config/runner.example.yaml --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess  # nosec B404 - used with list args, no shell, hardcoded command
import sys
import time
import yaml
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from dataset_loader import Dataset, DatasetError, Task, load_dataset
from runner_config import (
    RunnerConfig,
    RunnerConfigError,
    load_runner_config,
    model_to_wire_id,
)
from bedrock_pricing import cost_usd as _bedrock_cost_usd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# The four design artifacts every /swe2 run must produce. These are the ones
# whose presence defines a "complete" design and gate the ok flag / retry.
DESIGN_ARTIFACT_FILENAMES = ("github-issue.md", "lld.md", "review.md", "testing.md")
# The /swe2 implementation artifacts (the actual code change plus its summary).
IMPLEMENTATION_ARTIFACT_FILENAMES = ("patch.diff", "implementation.md")
# Everything a full /swe2 run emits, in produced-count order.
ARTIFACT_FILENAMES = DESIGN_ARTIFACT_FILENAMES + IMPLEMENTATION_ARTIFACT_FILENAMES
GIT_CLONE_TIMEOUT_SECONDS = 300

# Sanity floor for output tokens per turn, used to catch a token-accounting bug at
# run time rather than in PR review. An agent that edits files emits hundreds of
# output tokens per turn (measured: ~370-730 across claude-code and pi). A value in
# the single digits is not a model behaviour -- it means usage was read from one
# scope instead of summed across all of them, which is exactly how the pi
# per-message usage bug (#99) and the earlier claude modelUsage bug undercounted
# multi-turn runs by ~100x. The failure is silent (a plausible number in the right
# field), so only a ratio check catches it. Set well below any real per-turn rate so
# it fires on a genuine accounting fault, not on a terse run.
MIN_PLAUSIBLE_OUTPUT_TOKENS_PER_TURN = 20
# Below this turn count the ratio is noise (a 1-2 turn run can legitimately emit
# very little), so the check is skipped.
TOKEN_SANITY_MIN_TURNS = 5

# The SWE skill file, shared by both agents. Claude Code auto-loads it from the
# repo's .claude/skills tree via the matching slash command; pi is pointed at the
# same file explicitly with `--skill` so both agents run the identical task. Which
# skill (swe2 multi-agent vs swe3 single-agent) is selected per run via config.
_SKILLS_DIR = REPO_ROOT / ".claude" / "skills"


def _skill_path(config: RunnerConfig) -> Path:
    """Absolute SKILL.md path for the run's configured skill (swe2/swe3)."""
    return _SKILLS_DIR / config.skill / "SKILL.md"


# pi provider names (the `--provider` value pi expects). For an OpenAI-compatible
# endpoint (LiteLLM proxy) pi reads an "endpoint" block from its models.json; for
# Amazon Bedrock pi has a native provider backed by the bundled AWS SDK.
# A task's true cost is the sum of ALL its agent invocations -- every transient
# retry and every top-up, not just the pass that happened to succeed. Each
# _run_task call overwrites metrics.json with only that pass's numbers, so these
# fields are accumulated across passes and the sums restored. Fix for upstream
# issue #143: retried tasks previously underreported cost by ~2x.
ADDITIVE_COST_FIELDS = (
    "input_tokens",
    "output_tokens",
    "num_turns",
    "latency_seconds",
    "total_cost_usd",
    "cache_read_tokens",
    "cache_creation_tokens",
)
# The normalized block renames cache-write; everything else keeps its name.
MM_BLOCK_KEY = {"cache_creation_tokens": "cache_write_tokens"}

PI_PROVIDER_ENDPOINT = "endpoint"
PI_PROVIDER_BEDROCK = "amazon-bedrock"

# omp uses the same provider ids as pi; named separately so the two agents can
# diverge without a silent name change.
OMP_PROVIDER_VLLM = "vllm"
OMP_PROVIDER_BEDROCK = "amazon-bedrock"

# kiro-cli binary and the parsers for the one-line summary it prints on stderr at
# the end of a non-interactive run, e.g. "▸ Credits: 0.21 • Time: 17s". kiro-cli
# reports no token counts, so credits (its billing unit) are the cost signal; the
# harness turns them into dollars with a configurable per-credit rate. Output is
# ANSI-colored, so strip escape codes before matching. See docs/kiro-cli-setup.md.
KIRO_CLI_BIN = "kiro-cli"
_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;?]*[a-zA-Z]")
_KIRO_CREDITS_RE = re.compile(r"Credits:\s*([0-9]*\.?[0-9]+)")
_KIRO_TIME_RE = re.compile(r"Time:\s*([0-9]+)\s*s")



def _repo_name(repo_url: str) -> str:
    """Derive the kebab-case repo name from a clone URL.

    Args:
        repo_url: The HTTPS clone URL (with or without a trailing .git).

    Returns:
        The repository basename, e.g. "mcp-gateway-registry".
    """
    return repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def _safe_task_slug(task_id: str) -> str:
    """Return a filesystem-safe slug for a task id, for use in a clone path.

    The task id lands in a directory name, so anything that is not a plain
    path-segment character is replaced with ``-``. This both keeps the path the
    agent must reproduce simple and blocks path-traversal (``/`` and ``.`` runs
    cannot escape the parent). Task ids are already kebab-case slugs in practice,
    so this is a defensive no-op for well-formed input.

    Args:
        task_id: The dataset task id.

    Returns:
        A slug containing only ``[A-Za-z0-9._-]``, with leading dots/dashes and
        empty results collapsed to ``task``.

    Raises:
        ValueError: If task_id is empty.
    """
    if not task_id:
        raise ValueError("task id must not be empty")
    slug = re.sub(r"[^A-Za-z0-9._-]", "-", task_id).lstrip(".-")
    return slug or "task"


def _clone_repo(task: Task, ref: str, clone_dir: str, log_prefix: str = "") -> Path:
    """Clone a task's repo at a ref into a temp dir named after the task.

    The checkout lands at ``<clone_dir>/swe-clone-<task-id>/<repo-name>`` so the
    /swe skill, which derives {repo-name} from the clone path's basename, gets
    the right name -- and the parent is a stable, transcribable name (the task
    id) rather than a random mktemp suffix, which agents were mis-copying
    character by character and burning turns on. The task-id parent is unique
    per task (ids are unique within a dataset), so serial and concurrent runs do
    not collide. The ``swe-clone-`` prefix is distinct from the ``swe-benchmark-
    data`` output dir so a gitignore glob can target clones precisely. A leftover
    directory from a previously killed run is removed first.

    Args:
        task: The task whose repo to clone.
        ref: The git ref (tag/branch/commit) to check out.
        clone_dir: Parent directory for the temporary clone.
        log_prefix: Optional label (e.g. ``[task=x] 3 of 12``) prepended to the
            clone log line so interleaved concurrent runs stay legible.

    Returns:
        Path to the cloned repository.

    Raises:
        RuntimeError: If the clone command fails or times out.
    """
    name = _repo_name(task.repo)
    parent = Path(clone_dir) / f"swe-clone-{_safe_task_slug(task.id)}"
    # Clear any leftover clone from a prior killed run so the fresh clone into a
    # deterministic path does not fail on a non-empty destination.
    shutil.rmtree(parent, ignore_errors=True)
    parent.mkdir(parents=True, exist_ok=True)
    dest = parent / name
    prefix = f"{log_prefix} " if log_prefix else ""
    logger.info("  %sCloning %s @ %s into %s", prefix, task.repo, ref, dest)
    try:
        subprocess.run(  # nosec B603 B607 - hardcoded git, args are dataset values, no shell
            [
                "git",
                "clone",
                "--branch",
                ref,
                "--depth",
                "1",
                task.repo,
                str(dest),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=GIT_CLONE_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(parent, ignore_errors=True)
        raise RuntimeError(f"git clone timed out for {task.repo} @ {ref}") from exc
    except subprocess.CalledProcessError as exc:
        shutil.rmtree(parent, ignore_errors=True)
        raise RuntimeError(
            f"git clone failed for {task.repo} @ {ref}: {exc.stderr.strip()[:500]}"
        ) from exc
    return dest


def _build_prompt(
    task: Task,
    clone_path: Path,
    ref: str,
    model: str,
    artifacts_dir: Path,
    agent: str = "claude",
    skill: str = "swe2",
    topup_missing: list[str] | None = None,
) -> str:
    """Build the non-interactive /swe2 prompt for a task.

    This function only **hydrates** the `/swe2` invocation with the per-run values
    the skill cannot know on its own -- it carries no behavioral instructions.
    All rules about *how* `/swe2` should run headless (use `artifacts_dir`
    verbatim, do not re-clone or `cd` out, pace/budget, subagent cap) live in the
    skill (`.claude/skills/swe2/SKILL.md`), which applies to every invocation;
    duplicating them here only risks the two copies drifting apart.

    The invocation passes the keys the skill needs to enter non-interactive mode
    (repo, problem, model, tag, answers) plus ``artifacts_dir`` (the absolute
    directory the skill writes to) and the task's problem statement and, when
    present, its reference issue URL.

    The only agent-specific difference is how the skill is triggered. Claude Code
    auto-loads the skill from the ``/swe2`` slash command, so the prompt starts
    with it. pi loads the same ``SKILL.md`` via ``--skill`` and exposes it as a
    skill named ``swe2``; it has no slash-command syntax, so the pi prompt names
    the skill in prose and passes the identical key/value payload. Both carry the
    exact same values, so the two agents run the same task.

    Args:
        task: The task to run.
        clone_path: Local path to the already-cloned repo (the sole code source).
        ref: The git ref checked out.
        model: The model name (also the artifact subfolder name).
        artifacts_dir: Absolute directory the six artifacts must be written to.
        agent: Which agent will receive the prompt ("claude" or "pi").
        topup_missing: When set, build a FOCUSED top-up prompt instead of the full
            task prompt: the design docs already exist in ``artifacts_dir`` and the
            agent is asked to produce ONLY these missing files (reading the ones
            already on disk), then stop. Used by the harness's completion loop when
            a main run finished the design but ran out of context before the
            implementation artifacts. Everything else (repo, ids, layout) is the
            same, so the topped-up artifacts belong to the same task.

    Returns:
        The prompt string to pass to the agent.
    """
    answers = task.clarifying_answers or (
        "No separate answers provided. Use your best judgment; all needed "
        "information is in the task description below."
    )
    payload = (
        f"repo: {clone_path} problem: {task.id} model: {model} "
        f'tag: {ref} artifacts_dir: {artifacts_dir} answers: "{answers.strip()}"'
    )
    if agent in ("pi", "kiro", "codex", "omp"):
        # These agents have no slash commands; name the skill in prose and hand
        # it the payload. (pi loads SKILL.md via --skill; kiro and codex have no
        # --skill flag, so their _build_*_cmd inlines the SKILL.md content ahead
        # of this prompt.)
        invocation = f"Use the {skill} skill to complete this task. {payload}"
    else:
        invocation = f"/{skill} {payload}"
    if topup_missing:
        # Focused completion pass: the prior run already wrote the design docs
        # into artifacts_dir; only the listed files are missing. Ask the agent to
        # read what exists and produce ONLY those, without redoing the rest. This
        # keeps the top-up cheap (fresh, small context) so it does not hit the
        # same window wall that truncated the main run.
        missing = ", ".join(topup_missing)
        existing = ", ".join(f for f in ARTIFACT_FILENAMES if f not in topup_missing)
        lines = [
            invocation,
            "",
            "COMPLETION PASS -- do NOT restart the task.",
            f"The artifact directory ({artifacts_dir}) already contains these "
            f"finished artifacts: {existing}. Read them as needed for consistency.",
            f"Produce ONLY the missing artifact(s): {missing}. Follow the same "
            "skill rules for those artifacts (for patch.diff, implement the change "
            "the existing lld.md describes in the cloned repo and capture the diff; "
            "for implementation.md, summarize that change). Do not modify or "
            "rewrite the artifacts that already exist. When the missing files are "
            "written, stop.",
            "",
            "Task description:",
            task.problem_statement or "(see reference issue)",
        ]
        if task.problem_issue_url:
            lines += ["", f"Reference issue: {task.problem_issue_url}"]
        return "\n".join(lines)
    lines = [
        invocation,
        "",
        "Task description:",
        task.problem_statement or "(see reference issue)",
    ]
    if task.problem_issue_url:
        lines += ["", f"Reference issue: {task.problem_issue_url}"]
    return "\n".join(lines)


def _build_env(config: RunnerConfig) -> dict[str, str]:
    """Build the environment for the claude subprocess from the runner config.

    For provider=endpoint, routing pins ANTHROPIC_BASE_URL/API_KEY and disables
    Bedrock. For provider=bedrock, it flips CLAUDE_CODE_USE_BEDROCK=1 and sets
    AWS_REGION so claude talks to Amazon Bedrock natively, using the ambient AWS
    credentials; no base URL or api key is set.

    Args:
        config: The runner config.

    Returns:
        A copy of the current environment with routing overrides applied.
    """
    env = os.environ.copy()
    env["DISABLE_NON_ESSENTIAL_MODEL_CALLS"] = "1"
    env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] = str(config.max_output_tokens)
    env["CLAUDE_CODE_SUBAGENT_MODEL"] = config.model
    # Calibrate auto-compaction to the model's true window when known. Claude
    # Code cannot detect the window of a custom model on a custom base URL, so
    # without this it never compacts and the request eventually overflows the
    # endpoint's context limit (a 500 the client then retries forever).
    if config.auto_compact_window is not None:
        env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(config.auto_compact_window)
    if config.is_bedrock:
        env["CLAUDE_CODE_USE_BEDROCK"] = "1"
        region = config.resolved_region()
        if region:
            env["AWS_REGION"] = region
        # A stray ANTHROPIC_BASE_URL in the ambient env would otherwise redirect
        # the Bedrock-mode client away from Bedrock, so clear it.
        env.pop("ANTHROPIC_BASE_URL", None)
    else:
        env["ANTHROPIC_BASE_URL"] = config.endpoint
        env["ANTHROPIC_API_KEY"] = config.api_key
        env["CLAUDE_CODE_USE_BEDROCK"] = "0"
    return env


def _build_settings_arg(config: RunnerConfig) -> str:
    """Build the value for `claude --settings`.

    A settings file's ``env`` block takes precedence over process environment
    variables, so relying on _build_env alone is not enough: a user's global
    ``~/.claude/settings.json`` (e.g. one that pins CLAUDE_CODE_USE_BEDROCK=1)
    would override our routing and the request would hit Bedrock, which rejects
    the local model id with a 400. Passing --settings overrides that global
    file, so we always supply one.

    Uses the configured ``settings_file`` when set; otherwise synthesizes an
    inline JSON settings object that pins routing at the config's endpoint.

    Args:
        config: The runner config.

    Returns:
        Either a settings file path or an inline JSON settings string.
    """
    if config.settings_file:
        return str(REPO_ROOT / config.settings_file)
    if config.is_bedrock:
        # Bedrock mode authenticates with ambient AWS credentials, so no token
        # source is needed. Pin CLAUDE_CODE_USE_BEDROCK=1 (and the region) here
        # too, so a global settings file cannot flip routing back off Bedrock.
        env: dict[str, str] = {
            "CLAUDE_CODE_USE_BEDROCK": "1",
            "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
            "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(config.max_output_tokens),
            "CLAUDE_CODE_SUBAGENT_MODEL": config.model,
        }
        region = config.resolved_region()
        if region:
            env["AWS_REGION"] = region
        # The settings env block overrides the process env, so mirror the
        # auto-compaction window here too when it is set.
        if config.auto_compact_window is not None:
            env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(config.auto_compact_window)
        return json.dumps({"env": env})
    endpoint_env = {
        "CLAUDE_CODE_USE_BEDROCK": "0",
        "ANTHROPIC_BASE_URL": config.endpoint,
        "ANTHROPIC_API_KEY": config.api_key,
        "DISABLE_NON_ESSENTIAL_MODEL_CALLS": "1",
        "CLAUDE_CODE_MAX_OUTPUT_TOKENS": str(config.max_output_tokens),
        "CLAUDE_CODE_SUBAGENT_MODEL": config.model,
    }
    # The settings env block overrides the process env, so mirror the
    # auto-compaction window here too when it is set.
    if config.auto_compact_window is not None:
        endpoint_env["CLAUDE_CODE_AUTO_COMPACT_WINDOW"] = str(
            config.auto_compact_window
        )
    settings = {
        # Claude Code requires a token source even against a local endpoint that
        # ignores the value; without it the run fails with "Not logged in".
        "apiKeyHelper": f"echo {config.api_key}",
        "env": endpoint_env,
    }
    return json.dumps(settings)


def _build_claude_cmd(
    config: RunnerConfig,
    prompt: str,
    stream: bool = False,
    clone_path: Path | None = None,
) -> list[str]:
    """Assemble the `claude -p` argument vector from the runner config.

    Args:
        config: The runner config.
        prompt: The /swe prompt to run.
        stream: If True, emit newline-delimited JSON events as the run
            progresses (``--output-format stream-json``, which requires
            ``--verbose``) instead of a single buffered JSON result.
        clone_path: The task's cloned repo directory. When set, it is added as
            an allowed working directory with ``--add-dir`` so Bash commands can
            operate inside the clone. Read/Glob/Grep already reach absolute paths
            regardless; without this, Bash (ls/cd/find/grep into the clone) is
            blocked because it is sandboxed to the harness's own working dir.

    Returns:
        The command as a list of arguments (never a shell string).
    """
    output_format = "stream-json" if stream else "json"
    cmd = [
        "claude",
        "-p",
        prompt,
        "--model",
        config.model,
        "--output-format",
        output_format,
        "--permission-mode",
        config.permission_mode,
        "--allowedTools",
        ",".join(config.allowed_tools),
        "--max-turns",
        str(config.max_turns),
        "--settings",
        _build_settings_arg(config),
    ]
    if clone_path is not None:
        cmd += ["--add-dir", str(clone_path)]
    if stream:
        # stream-json in -p mode requires --verbose to emit per-event objects.
        cmd.append("--verbose")
    return cmd


def _write_pi_models_json(config: RunnerConfig, agent_dir: Path) -> None:
    """Write an ephemeral pi ``models.json`` pointing at the config's endpoint.

    pi resolves providers from ``<agent_dir>/models.json`` (agent_dir defaults to
    ``~/.pi/agent`` but is overridden per run via ``PI_CODING_AGENT_DIR`` so the
    benchmark never mutates a developer's global pi config). This writes a single
    ``endpoint`` provider block for the OpenAI-compatible LiteLLM proxy (Path 2).

    Args:
        config: The runner config (endpoint + model).
        agent_dir: The per-run pi agent dir to write ``models.json`` into.
    """
    # pi's baseUrl expects the OpenAI-compatible root ending in /v1.
    base = config.endpoint.rstrip("/")
    base_url = base if base.endswith("/v1") else f"{base}/v1"
    window = config.context_window or 200000
    models_json = {
        "providers": {
            "endpoint": {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": config.api_key,
                "compat": {
                    "supportsDeveloperRole": False,
                    "supportsReasoningEffort": False,
                },
                "models": [
                    {
                        "id": config.model,
                        "name": config.model,
                        "reasoning": False,
                        "input": ["text"],
                        "contextWindow": window,
                        "maxTokens": config.max_output_tokens,
                        "cost": {
                            "input": 0,
                            "output": 0,
                            "cacheRead": 0,
                            "cacheWrite": 0,
                        },
                    }
                ],
            }
        }
    }
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "models.json").write_text(
        json.dumps(models_json, indent=2) + "\n", encoding="utf-8"
    )
    _write_pi_settings(config, agent_dir)


def _write_pi_settings(config: RunnerConfig, agent_dir: Path) -> None:
    """Write an ephemeral pi ``settings.json`` that tunes auto-compaction.

    pi has built-in auto-compaction (docs/compaction.md): it summarizes older
    messages once ``contextTokens > contextWindow - reserveTokens``. Left at pi's
    default ``reserveTokens`` of 16384, a long ``/swe2`` task on a 200K-window
    model overflows anyway -- pi lets the window fill to within 16K, then a single
    response (capped at ``maxTokens``, which we raise well above 16K) blows past
    the window and the run dies with ``stop_reason: length`` before the last
    artifacts are written (observed on the mcp-gateway-registry tasks).

    The fix is to reserve at least a full response worth of tokens (plus headroom)
    so threshold compaction fires *before* the overflow wall, keeping the run
    alive through the whole six-artifact chain -- the same role
    ``CLAUDE_CODE_AUTO_COMPACT_WINDOW`` plays for the Claude Code path. We set
    ``reserveTokens`` to ``max_output_tokens`` plus a margin, and keep pi's default
    ``keepRecentTokens``. ``contextWindow`` itself is carried in models.json.

    Args:
        config: The runner config (its ``max_output_tokens`` sizes the reserve).
        agent_dir: The per-run pi agent dir to write ``settings.json`` into.
    """
    # Reserve a full response plus ~8K headroom so compaction triggers with room
    # to spare for the reply and per-request overhead, never after overflow.
    reserve = config.max_output_tokens + 8192
    settings = {
        "compaction": {
            "enabled": True,
            "reserveTokens": reserve,
        }
    }
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "settings.json").write_text(
        json.dumps(settings, indent=2) + "\n", encoding="utf-8"
    )


def _build_pi_env(config: RunnerConfig, agent_dir: Path) -> dict[str, str]:
    """Build the environment for the pi subprocess.

    ``PI_CODING_AGENT_DIR`` points pi at the per-run config dir so the benchmark
    stays isolated from a developer's global ``~/.pi`` setup. For an endpoint
    (LiteLLM proxy), routing comes from the per-run ``models.json`` and no other
    override is needed. For Amazon Bedrock, pi uses the ambient AWS credential
    chain (env/ini/sso/...) and needs the region pinned from the resolved config.

    Args:
        config: The runner config (provider, aws region).
        agent_dir: The per-run pi agent config dir.

    Returns:
        A copy of the current environment with the pi agent dir pinned (plus the
        AWS region for the bedrock path).
    """
    env = os.environ.copy()
    env["PI_CODING_AGENT_DIR"] = str(agent_dir)
    if config.is_bedrock:
        region = config.resolved_region()
        if region:
            env["AWS_REGION"] = region
        _ensure_aws_sigv4_env(env)
    return env


def _ensure_aws_sigv4_env(env: dict[str, str]) -> None:
    """Populate SigV4 AWS credentials in ``env`` for pi's Bedrock provider.

    pi's ``amazon-bedrock`` provider authenticates from explicit credentials
    (``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` / ``AWS_SESSION_TOKEN`` or
    ``AWS_BEARER_TOKEN_BEDROCK``); unlike boto3 it does NOT probe the EC2 IMDS
    instance-profile chain. On an EC2 box whose only credentials come from an
    attached instance role, a run would fail with "No API key found". This
    resolves the role's short-lived credentials via ``aws configure
    export-credentials`` and injects them, so the ambient instance role Just Works.

    No-ops when credentials are already present in ``env`` (the caller's shell set
    them, or a bearer token is configured) or when the AWS CLI cannot mint any
    (off EC2 with no role) -- pi then reports its own clear auth error. Credentials
    are only placed in the child env, never logged or written to disk.

    Args:
        env: The subprocess environment to populate in place.
    """
    if env.get("AWS_ACCESS_KEY_ID") or env.get("AWS_BEARER_TOKEN_BEDROCK"):
        return
    try:
        proc = subprocess.run(
            ["aws", "configure", "export-credentials", "--format", "env-no-export"],  # nosec B603 B607 - hardcoded command, no user input
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
    except (
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        FileNotFoundError,
    ):
        # No resolvable credentials (or no AWS CLI): leave env as-is and let pi
        # surface its own auth error rather than failing opaquely here.
        logger.warning(
            "could not resolve AWS credentials via 'aws configure export-credentials'; "
            "pi will rely on whatever is already in the environment"
        )
        return
    for line in proc.stdout.splitlines():
        key, _, value = line.strip().partition("=")
        if key.startswith("AWS_") and value:
            env[key] = value


def _build_pi_cmd(config: RunnerConfig, prompt: str) -> list[str]:
    """Assemble the ``pi -p`` argument vector for a /swe3 run.

    pi runs headless with ``-p`` (process the prompt and exit) and ``--mode json``
    (emit a stream of JSON-lines events the harness parses for metrics). Tools run
    without an approval gate in ``-p`` mode, which is what an unattended benchmark
    needs. The ``/swe3`` behavior is delivered by loading the same SKILL.md Claude
    Code uses, via ``--skill``. ``--no-session`` keeps the run ephemeral (no
    session file written under the agent dir).

    The ``--provider`` depends on routing: native Amazon Bedrock (pi signs SigV4
    via the bundled AWS SDK; credentials come from the ambient chain, region from
    the env set in ``_build_pi_env``) or an OpenAI-compatible endpoint (the
    LiteLLM proxy for Path 2, resolved from the per-run models.json).

    Args:
        config: The runner config (model, provider).
        prompt: The hydrated /swe3 prompt (see ``_build_prompt`` agent="pi").

    Returns:
        The command as a list of arguments (never a shell string).
    """
    if config.is_bedrock:
        provider = PI_PROVIDER_BEDROCK
        model = model_to_wire_id(config.model)
    else:
        provider = PI_PROVIDER_ENDPOINT
        model = config.model
    return [
        "pi",
        "-p",
        "--mode",
        "json",
        "--no-session",
        "--provider",
        provider,
        "--model",
        model,
        "--skill",
        str(_skill_path(config)),
        prompt,
    ]


def _build_kiro_env(config: RunnerConfig) -> dict[str, str]:
    """Environment for a kiro-cli run.

    kiro-cli authenticates through its own global sign-in under ``~/.kiro`` (AWS
    Builder ID / IAM Identity Center / Google), so -- unlike pi -- the harness
    does NOT redirect ``KIRO_HOME`` to a per-run dir: that would hide the login
    and force an interactive re-auth mid-benchmark. The model is passed on the
    command line, so there is no per-run config to write; the developer's global
    kiro config is read but never mutated.

    Args:
        config: The runner config (unused today; kept for signature parity with
            ``_build_pi_env``).

    Returns:
        A copy of the current process environment.
    """
    return os.environ.copy()


def _build_kiro_cmd(config: RunnerConfig, prompt: str) -> list[str]:
    """Assemble the ``kiro-cli chat --no-interactive`` argument vector.

    kiro-cli is the ``claude -p`` / ``codex exec`` analogue: it takes a prompt
    argument, runs to completion, and exits. It has NO ``--skill`` flag, so the
    same ``SKILL.md`` the other agents load is inlined ahead of the task payload
    in the prompt. ``--trust-all-tools`` pre-approves tool use (no operator is
    present in a benchmark); ``--model`` selects one of Kiro's managed models.
    kiro-cli cannot target a custom endpoint, so there is no provider or
    endpoint to pass. See docs/kiro-cli-setup.md.

    Args:
        config: The runner config (model).
        prompt: The hydrated prompt (see ``_build_prompt`` agent="kiro").

    Returns:
        The command as a list of arguments (never a shell string).
    """
    skill_md = _skill_path(config).read_text(encoding="utf-8")
    full_prompt = (
        f"{skill_md}\n\n"
        "===TASK===\n"
        "Follow the skill instructions above to complete the following task.\n\n"
        f"{prompt}"
    )
    # A trailing "--" ends option parsing so the prompt is always treated as the
    # positional INPUT -- essential here because the inlined SKILL.md begins with
    # "---" (YAML frontmatter), which kiro-cli would otherwise reject as an
    # unknown flag.
    return [
        KIRO_CLI_BIN,
        "chat",
        "--no-interactive",
        "--trust-all-tools",
        "--model",
        config.model,
        "--",
        full_prompt,
    ]


def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with a trailing Z.

    Returns:
        The timestamp, e.g. ``2026-07-22T20:41:03.512874Z``.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _claude_token_usage(result: dict[str, Any]) -> dict[str, int]:
    """Return COMPLETE token counts from a claude -p result, subagents included.

    Claude Code reports two usage views:

    * ``usage`` -- the MAIN agent's tokens only. Task subagents' tokens are NOT
      in here, so on a multi-agent run (e.g. /swe2 fanning out) it undercounts
      the real work, and the token-derived cost does not reconcile with the
      billed ``total_cost_usd``.
    * ``modelUsage`` -- a per-model rollup that DOES include subagent tokens (all
      subagents run on ``CLAUDE_CODE_SUBAGENT_MODEL`` = the benchmarked model, so
      they fold into that model's entry). Its ``costUSD`` equals ``total_cost_usd``
      to the cent, which is the proof it is complete.

    We prefer ``modelUsage`` (summed across model entries) and fall back to
    ``usage`` only when ``modelUsage`` is absent (older Claude Code). Keys are
    normalized to input/output/cache_read/cache_creation.

    Args:
        result: The parsed JSON result object from ``claude -p``.

    Returns:
        Dict with input_tokens, output_tokens, cache_read_tokens,
        cache_creation_tokens (each an int; cache fields 0 when not reported).
    """
    model_usage = result.get("modelUsage")
    if isinstance(model_usage, dict) and model_usage:
        agg = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
        }
        for entry in model_usage.values():
            if not isinstance(entry, dict):
                continue
            agg["input_tokens"] += entry.get("inputTokens") or 0
            agg["output_tokens"] += entry.get("outputTokens") or 0
            agg["cache_read_tokens"] += entry.get("cacheReadInputTokens") or 0
            agg["cache_creation_tokens"] += entry.get("cacheCreationInputTokens") or 0
        return agg
    # Fallback: main-agent usage only (undercounts a fan-out run).
    usage = result.get("usage") or {}
    return {
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_tokens": usage.get("cache_creation_input_tokens", 0),
    }


def _check_token_accounting(
    metrics: dict[str, Any],
    agent: str,
    label: str,
) -> str | None:
    """Warn loudly when output tokens per turn are implausibly low.

    Guards against the token-accounting class of bug where usage is read from a
    single scope (pi's last per-message ``usage``, or claude's main-agent-only
    ``usage``) instead of summed across every message/model, undercounting a
    multi-turn run roughly in proportion to its turn count. Such a run still writes
    a well-formed metrics.json with a plausible-looking number, so nothing else in
    the pipeline notices; the ratio is the only cheap signal.

    This warns rather than fails: the artifacts and judge scores of an affected run
    are still valid (only tokens and cost are wrong), so aborting would discard good
    work. The warning names the run so it cannot be committed unnoticed.

    Args:
        metrics: The metrics dict from ``_metrics_from_result``.
        agent: Which coding agent produced the run (for the message).
        label: Task label used in log lines.

    Returns:
        The warning message if the check tripped, else None.
    """
    turns = metrics.get("num_turns") or 0
    output_tokens = metrics.get("output_tokens") or 0
    if turns < TOKEN_SANITY_MIN_TURNS:
        return None
    per_turn = output_tokens / turns
    if per_turn >= MIN_PLAUSIBLE_OUTPUT_TOKENS_PER_TURN:
        return None
    message = (
        f"{label} TOKEN ACCOUNTING SUSPECT: {output_tokens:,} output tokens over "
        f"{turns} turns = {per_turn:.1f}/turn, below the {MIN_PLAUSIBLE_OUTPUT_TOKENS_PER_TURN} "
        f"floor. An agent making edits emits hundreds per turn, so the {agent} usage "
        f"is likely being read from one scope instead of summed across all of them "
        f"(see the pi per-message usage bug, issue #99). Scores, turns, and latency "
        f"are unaffected and still valid -- but DO NOT publish the token or cost "
        f"columns from this run without re-checking the extractor."
    )
    logger.warning("!" * 100)
    logger.warning(message)
    logger.warning("!" * 100)
    return message


def _metrics_from_result(result: dict[str, Any], elapsed: float) -> dict[str, Any]:
    """Extract the benchmark metrics from a claude -p JSON result.

    Token counts come from ``_claude_token_usage`` (modelUsage-first, so subagent
    tokens are included and the counts reconcile with the billed cost).

    Args:
        result: The parsed JSON result object from `claude -p`.
        elapsed: Wall-clock seconds measured around the subprocess call.

    Returns:
        A metrics dictionary keyed by the dataset's metric names.
    """
    usage = result.get("usage") or {}
    tokens = _claude_token_usage(result)
    duration_ms = result.get("duration_ms")
    latency = round(duration_ms / 1000, 1) if duration_ms else round(elapsed, 1)
    is_error = result.get("is_error", False)
    metrics = {
        "input_tokens": tokens["input_tokens"],
        "output_tokens": tokens["output_tokens"],
        "latency_seconds": latency,
        "num_turns": result.get("num_turns", 0),
        "total_cost_usd": result.get("total_cost_usd"),
        "is_error": is_error,
        # claude -p's result subtype: "success", "error_max_turns" (hit the
        # --max-turns cap), "error_during_execution", etc. Recorded so the retry
        # logic can tell an exhausted turn budget (not retryable) from a
        # transient failure (retryable).
        "result_subtype": result.get("subtype"),
        # NOTE: the agent session UUID is intentionally NOT recorded -- metrics.json
        # is now committed to git, and a per-run session id is machine/run-specific
        # noise, not useful provenance. (Nothing downstream reads it.)
    }
    # Cache-token fields: from modelUsage (subagent-inclusive) when the backend
    # reports them (Amazon Bedrock / Anthropic API).
    if tokens["cache_read_tokens"] or "cache_read_input_tokens" in usage:
        metrics["cache_read_tokens"] = tokens["cache_read_tokens"]
    if tokens["cache_creation_tokens"] or "cache_creation_input_tokens" in usage:
        metrics["cache_creation_tokens"] = tokens["cache_creation_tokens"]
    # Streaming-only: peak running estimate of extended-thinking tokens for
    # reasoning models. output_tokens already includes these; this records the
    # thinking portion the model streamed as system/thinking_tokens events.
    thinking = result.get("_thinking_tokens_estimate")
    if thinking:
        metrics["thinking_tokens_estimate"] = thinking
    # agent=kiro only: kiro-cli reports credits (not tokens); record the raw
    # credits alongside the derived total_cost_usd (credits x $/credit) so the
    # cost is auditable back to what the CLI actually charged.
    if result.get("kiro_credits") is not None:
        metrics["kiro_credits"] = result["kiro_credits"]
    # Capture the error message so failures are diagnosable from metrics.json
    # without re-running the task by hand.
    if is_error:
        metrics["error"] = str(result.get("result", ""))[:1000]
        metrics["api_error_status"] = result.get("api_error_status")
    return metrics


def _run_claude(cmd: list[str], env: dict[str, str], timeout: int) -> dict[str, Any]:
    """Run `claude -p` and parse its JSON result.

    Args:
        cmd: The command argument vector.
        env: Environment for the subprocess.
        timeout: Wall-clock timeout in seconds.

    Returns:
        The parsed JSON result object.

    Raises:
        RuntimeError: If claude times out, exits nonzero, or emits no JSON.
    """
    start = time.time()
    try:
        proc = subprocess.run(  # nosec B603 - hardcoded 'claude', list args, no shell
            cmd,
            env=env,
            # Run from the repo root so the /swe skill's artifact paths (written
            # relative to the repo root, e.g. benchmarks/swe-benchmark-data/...)
            # resolve correctly. Without this, cwd is wherever the harness was
            # invoked (typically benchmarks/), and a model that writes a relative
            # path doubles it to benchmarks/benchmarks/... and the run scores 0/4.
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"claude -p timed out after {timeout}s") from exc
    elapsed = time.time() - start

    if not proc.stdout.strip():
        raise RuntimeError(
            f"claude -p produced no output (exit {proc.returncode}): "
            f"{proc.stderr.strip()[:500]}"
        )
    try:
        result = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"claude -p output was not JSON: {proc.stdout.strip()[:500]}"
        ) from exc
    result["_elapsed_seconds"] = round(elapsed, 1)
    return result


def _pi_result_from_events(
    events: list[dict[str, Any]], elapsed: float
) -> dict[str, Any]:
    """Normalize pi's JSON-lines event stream into the claude-shaped result dict.

    pi ``--mode json`` emits a stream of events, not one result object. The final
    ``agent_end`` carries the settled conversation, and ``stopReason`` reports why
    it stopped. Turns are counted from ``turn_start`` events.

    Token usage is PER-MESSAGE, not cumulative: each assistant message carries its
    own ``usage`` (``input``/``output``/``cacheRead``/``cacheWrite``), matching pi's
    own ``UsageTotals`` accounting (``addUsageToTotals`` is called once per message).
    Reading only the last message's usage undercounts a multi-turn run by ~100x
    (a 200-turn edit run would report only the final turn's tokens), so we SUM
    usage across every assistant message -- the same fix as sourcing claude's tokens
    from ``modelUsage`` rather than the main-agent-only ``usage``. This maps onto the
    keys ``_metrics_from_result`` reads for claude so the harness stays agent-agnostic.

    Args:
        events: The parsed JSON-lines events pi emitted, in order.
        elapsed: Wall-clock seconds measured around the subprocess call.

    Returns:
        A result dict shaped like ``claude -p``'s JSON result.

    Raises:
        RuntimeError: If the stream carried no ``agent_end`` (pi crashed or
            produced no parseable result).
    """
    num_turns = sum(1 for e in events if e.get("type") == "turn_start")
    agent_end = next(
        (e for e in reversed(events) if e.get("type") == "agent_end"), None
    )
    if agent_end is None:
        raise RuntimeError("pi emitted no agent_end event (no parseable result)")
    messages = agent_end.get("messages") or []
    assistant_msgs = [
        m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"
    ]
    # Sum per-message usage across the whole conversation (see docstring: usage is
    # per-message, not cumulative). stopReason comes from the LAST assistant message.
    totals = {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0, "cost": 0.0}
    for m in assistant_msgs:
        u = m.get("usage") or {}
        totals["input"] += u.get("input") or 0
        totals["output"] += u.get("output") or 0
        totals["cacheRead"] += u.get("cacheRead") or 0
        totals["cacheWrite"] += u.get("cacheWrite") or 0
        # Cost, when present, is per-message and additive (pi accrues it into
        # UsageTotals.cost the same way). Shapes vary by pi version: a bare number
        # or a {"total": ...} object -- accept both.
        mc = u.get("cost")
        if isinstance(mc, dict):
            mc = mc.get("total")
        if isinstance(mc, (int, float)):
            totals["cost"] += mc
    stop_reason = assistant_msgs[-1].get("stopReason") if assistant_msgs else None
    # remap onto the keys _metrics_from_result reads for claude.
    remapped_usage: dict[str, Any] = {
        "input_tokens": totals["input"],
        "output_tokens": totals["output"],
    }
    # Cache tokens: pi reports native prompt-cache usage (cacheRead/cacheWrite)
    # on the Bedrock path; pass through only when non-zero.
    if totals["cacheRead"]:
        remapped_usage["cache_read_input_tokens"] = totals["cacheRead"]
    if totals["cacheWrite"]:
        remapped_usage["cache_creation_input_tokens"] = totals["cacheWrite"]
    cost = totals["cost"] or None
    # An error retry (pi tried and gave up) or a non-"stop" terminal reason marks
    # the run failed so the harness's retry/failure logic can react.
    will_retry = agent_end.get("willRetry", False)
    is_error = bool(will_retry) or stop_reason not in (None, "stop", "end_turn")
    return {
        "usage": remapped_usage,
        "num_turns": num_turns,
        "total_cost_usd": cost if cost else None,
        "is_error": is_error,
        # Map pi's stopReason onto the subtype the retry logic keys on. pi has no
        # turn cap (no error_max_turns analogue), so a clean stop is "success".
        "subtype": "success" if stop_reason in ("stop", "end_turn") else stop_reason,
        "duration_ms": round(elapsed * 1000),
        "result": stop_reason or "",
    }


def _run_pi(cmd: list[str], env: dict[str, str], timeout: int) -> dict[str, Any]:
    """Run ``pi -p --mode json`` and normalize its event stream to a result dict.

    Args:
        cmd: The pi command argument vector.
        env: Environment for the subprocess (pins PI_CODING_AGENT_DIR).
        timeout: Wall-clock timeout in seconds.

    Returns:
        The claude-shaped result dict (see ``_pi_result_from_events``).

    Raises:
        RuntimeError: If pi times out, emits no output, or emits no agent_end.
    """
    start = time.time()
    try:
        proc = subprocess.run(  # nosec B603 - hardcoded 'pi', list args, no shell
            cmd,
            env=env,
            # Run from the repo root so the skill's artifact paths resolve, exactly
            # as for the claude path (see the note in _run_claude).
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"pi -p timed out after {timeout}s") from exc
    elapsed = time.time() - start

    if not proc.stdout.strip():
        raise RuntimeError(
            f"pi -p produced no output (exit {proc.returncode}): "
            f"{proc.stderr.strip()[:500]}"
        )
    events: list[dict[str, Any]] = []
    for line in proc.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            # pi may interleave non-JSON diagnostics; skip them, keep the events.
            continue
    if not events:
        raise RuntimeError(
            f"pi -p output had no JSON events: {proc.stdout.strip()[:500]}"
        )
    # Debug aid: dump the raw event stream when PI_RAW_EVENTS_DUMP is set, so the
    # usage-summation logic can be validated against real pi output.
    dump_path = os.environ.get("PI_RAW_EVENTS_DUMP")
    if dump_path:
        with open(dump_path, "w", encoding="utf-8") as fh:
            for e in events:
                fh.write(json.dumps(e) + "\n")
    result = _pi_result_from_events(events, elapsed)
    result["_elapsed_seconds"] = round(elapsed, 1)
    return result


def _kiro_result_from_output(
    output: str,
    returncode: int,
    elapsed: float,
    dollars_per_credit: float,
) -> dict[str, Any]:
    """Normalize a kiro-cli run to the claude-shaped result dict.

    kiro-cli emits ANSI-colored narration and a one-line summary, e.g.
    ``▸ Credits: 0.21 • Time: 17s``. It reports no token counts, so input/output
    tokens are 0 and ``num_turns`` is 0; the cost signal is credits, turned into
    dollars via the configured per-credit rate. Success is gated on the process
    exit code (kiro-cli returns non-zero on failure).

    Args:
        output: The captured combined stdout+stderr (carries the Credits/Time
            summary line).
        returncode: The process exit code.
        elapsed: Wall-clock seconds measured by the harness.
        dollars_per_credit: USD per credit for the cost estimate.

    Returns:
        The claude-shaped result dict, with ``kiro_credits`` added for provenance.
    """
    clean = _ANSI_ESCAPE_RE.sub("", output)
    credits_match = _KIRO_CREDITS_RE.search(clean)
    time_match = _KIRO_TIME_RE.search(clean)
    credits = float(credits_match.group(1)) if credits_match else None
    reported_s = float(time_match.group(1)) if time_match else None
    cost = round(credits * dollars_per_credit, 6) if credits is not None else None
    is_error = returncode != 0
    return {
        "usage": {"input_tokens": 0, "output_tokens": 0},
        "num_turns": 0,
        "total_cost_usd": cost,
        "is_error": is_error,
        "subtype": "success" if not is_error else f"exit_{returncode}",
        "duration_ms": round(
            (reported_s if reported_s is not None else elapsed) * 1000
        ),
        "result": "" if is_error else "stop",
        "kiro_credits": credits,
    }


def _run_kiro(
    cmd: list[str],
    env: dict[str, str],
    timeout: int,
    dollars_per_credit: float,
) -> dict[str, Any]:
    """Run ``kiro-cli chat --no-interactive``, streaming its trace, and normalize output.

    kiro-cli streams ANSI narration on stdout and prints its ``Credits/Time``
    summary on stderr. We merge the two (``stderr=STDOUT``) and echo each line to
    this process's stderr as it arrives -- a live trace, the kiro analogue of
    Claude Code's ``--stream`` mode -- while accumulating the combined text for
    metrics parsing. The per-line timeout check mirrors ``_run_claude_streaming``.

    Args:
        cmd: The kiro-cli command argument vector.
        env: Environment for the subprocess.
        timeout: Wall-clock timeout in seconds.
        dollars_per_credit: USD per credit for the cost estimate.

    Returns:
        The claude-shaped result dict (see ``_kiro_result_from_output``).

    Raises:
        RuntimeError: If kiro-cli times out or produces no output.
    """
    start = time.time()
    proc = subprocess.Popen(  # nosec B603 - hardcoded 'kiro-cli', list args, no shell
        cmd,
        env=env,
        # Run from the repo root so the skill's artifact paths resolve, exactly as
        # for the claude and pi paths.
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:  # pragma: no cover - stdout is always a pipe here
        raise RuntimeError("kiro-cli produced no stdout stream")
    captured: list[str] = []
    for line in proc.stdout:
        if time.time() - start > timeout:
            proc.kill()
            raise RuntimeError(f"kiro-cli timed out after {timeout}s")
        # Echo the model's live trace so it shows up in the harness log/terminal.
        sys.stderr.write(line)
        sys.stderr.flush()
        captured.append(line)
    proc.wait()
    elapsed = time.time() - start

    combined = "".join(captured)
    if not combined.strip():
        raise RuntimeError(f"kiro-cli produced no output (exit {proc.returncode}).")
    result = _kiro_result_from_output(
        combined, proc.returncode, elapsed, dollars_per_credit
    )
    result["_elapsed_seconds"] = round(elapsed, 1)
    return result


def _write_omp_config(config: RunnerConfig, agent_dir: Path) -> None:
    """Write the per-run omp ``models.yml`` and ``config.yml`` into ``agent_dir``.

    omp is a fork of pi; its config is YAML rather than pi's ``models.json``.
    Writing both per run keeps the benchmark isolated from ``~/.omp``.

    Args:
        config: The runner config (endpoint, model, window, output cap).
        agent_dir: The per-run omp agent dir to write both files into.
    """
    base = config.endpoint.rstrip("/")
    base_url = base if base.endswith("/v1") else f"{base}/v1"
    window = config.context_window or 200000
    models_yml = {
        "providers": {
            OMP_PROVIDER_VLLM: {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": config.api_key,
                "models": [
                    {
                        "id": config.model,
                        "name": config.model,
                        "contextWindow": window,
                        "maxTokens": config.max_output_tokens,
                        "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
                    }
                ],
            }
        }
    }
    threshold = max(window - (config.max_output_tokens + 8192), 1)
    config_yml = {"compaction": {"enabled": True, "thresholdTokens": threshold}}
    agent_dir.mkdir(parents=True, exist_ok=True)
    (agent_dir / "models.yml").write_text(
        yaml.safe_dump(models_yml, sort_keys=False), encoding="utf-8"
    )
    (agent_dir / "config.yml").write_text(
        yaml.safe_dump(config_yml, sort_keys=False), encoding="utf-8"
    )


def _build_omp_env(config: RunnerConfig, agent_dir: Path) -> dict[str, str]:
    """Build the environment for the omp subprocess.

    Mirrors ``_build_pi_env``: ``PI_CODING_AGENT_DIR`` (which omp inherits from pi)
    points at the per-run config dir, and the Bedrock path pins the region.

    Args:
        config: The runner config (provider, aws region).
        agent_dir: The per-run omp agent config dir.

    Returns:
        A copy of the environment with the omp agent dir pinned.
    """
    env = os.environ.copy()
    env["PI_CODING_AGENT_DIR"] = str(agent_dir)
    if config.is_bedrock:
        region = config.resolved_region()
        if region:
            env["AWS_REGION"] = region
        _ensure_aws_sigv4_env(env)
    return env


def _build_omp_cmd(config: RunnerConfig, prompt: str) -> list[str]:
    """Assemble the ``omp -p --mode json`` argument vector.

    omp has no ``--skill`` flag so the SKILL.md is inlined into the prompt,
    exactly as ``_build_kiro_cmd`` does.

    Args:
        config: The runner config (model, provider).
        prompt: The hydrated prompt (see ``_build_prompt`` agent="omp").

    Returns:
        The command as a list of arguments (never a shell string).
    """
    skill_md = _skill_path(config).read_text(encoding="utf-8")
    full_prompt = (
        f"{skill_md}\n\n"
        "---\n\n"
        "Follow the skill instructions above to complete the following task.\n\n"
        f"{prompt}"
    )
    if config.is_bedrock:
        model = f"{OMP_PROVIDER_BEDROCK}/{model_to_wire_id(config.model)}"
    else:
        model = f"{OMP_PROVIDER_VLLM}/{config.model}"
    cmd = [
        "omp",
        "-p",
        "--mode",
        "json",
        "--no-session",
        "--auto-approve",
        "--model",
        model,
    ]
    if config.agent_max_time_seconds:
        cmd += [f"--max-time={config.agent_max_time_seconds}"]
    return [*cmd, "--", full_prompt]  # nosec B603 B607 - hardcoded command


def _run_omp(
    cmd: list[str],
    env: dict[str, str],
    timeout: int,
) -> dict[str, Any]:
    """Run ``omp -p --mode json`` and normalize its events to a result dict.

    omp emits the same event stream as pi, so ``_pi_result_from_events`` is
    reused. stdin=DEVNULL is required -- without it omp blocks waiting for EOF.

    Args:
        cmd: The omp command argument vector.
        env: Environment for the subprocess.
        timeout: Wall-clock timeout in seconds.

    Returns:
        The claude-shaped result dict (see ``_pi_result_from_events``).

    Raises:
        RuntimeError: If omp times out or produces no output.
    """
    start = time.time()
    events: list[dict[str, Any]] = []
    stdout_lines: list[str] = []
    proc = subprocess.Popen(  # nosec B603 B607 - hardcoded 'omp', list args, no shell
        cmd,
        env=env,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        stdin=subprocess.DEVNULL,
    )
    try:
        for line in proc.stdout or []:
            stdout_lines.append(line)
            sys.stderr.write(line)
            sys.stderr.flush()
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
        proc.wait(timeout=max(timeout - (time.time() - start), 1))
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise RuntimeError(f"omp -p timed out after {timeout}s") from exc
    elapsed = time.time() - start

    if not "".join(stdout_lines).strip():
        stderr = (proc.stderr.read() if proc.stderr else "") or ""
        raise RuntimeError(
            f"omp -p produced no output (exit {proc.returncode}): {stderr.strip()[:500]}"
        )
    result = _pi_result_from_events(events, elapsed)
    result["_elapsed_seconds"] = round(elapsed, 1)
    return result


CODEX_BIN = "codex"


def _build_codex_env(config: RunnerConfig) -> dict[str, str]:
    """Build the environment for a codex exec run.

    For provider=bedrock, pins AWS_REGION so codex uses the right region.
    For provider=endpoint, sets OPENAI_BASE_URL and OPENAI_API_KEY so codex
    routes through the LiteLLM proxy.

    Args:
        config: The runner config.

    Returns:
        A copy of the current environment with routing vars set.
    """
    env = os.environ.copy()
    if config.is_bedrock:
        region = config.resolved_region()
        if region:
            env["AWS_REGION"] = region
    else:
        env["OPENAI_BASE_URL"] = config.endpoint.rstrip("/") + "/v1"
        env["OPENAI_API_KEY"] = config.api_key or "local"
    return env


def _build_codex_cmd(config: RunnerConfig, clone_path: Path, prompt: str) -> list[str]:
    """Assemble the ``codex exec`` argument vector.

    codex exec runs non-interactively, outputs JSON lines, and supports
    ``--model`` to select any Bedrock or OpenAI-compatible model. ``--cd``
    sets the working directory to the cloned repo so codex file tools operate
    on the task. The SKILL.md is inlined ahead of the task payload (codex has
    no ``--skill`` flag, same as kiro).

    Args:
        config: The runner config (model, provider).
        clone_path: Path to the cloned task repo.
        prompt: The hydrated task prompt (from ``_build_prompt`` agent="codex").

    Returns:
        The command as a list of arguments (never a shell string).
    """
    skill_md = _skill_path(config).read_text(encoding="utf-8")
    full_prompt = (
        f"{skill_md}\n\n"
        "===TASK===\n"
        "Follow the skill instructions above to complete the following task.\n\n"
        f"{prompt}"
    )
    cmd = [
        CODEX_BIN,
        "exec",
        "--json",
        "--skip-git-repo-check",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd", str(clone_path),
        "--model", model_to_wire_id(config.model),
    ]
    if config.is_bedrock:
        cmd += ["-c", "model_provider=amazon-bedrock"]
    cmd += ["--", full_prompt]
    return cmd  # nosec B603 B607 - hardcoded command, no user input in cmd args


def _codex_result_from_events(
    events: list[dict[str, Any]],
    returncode: int,
    elapsed: float,
    model: str = "",
) -> dict[str, Any]:
    """Normalize codex JSON-lines output to the claude-shaped result dict.

    codex exec emits JSON-lines events. The ``turn.completed`` event carries
    full token usage (input, output, cache read/write). Cost is derived from
    the token counts using the local Bedrock price table in ``bedrock_pricing``.

    Args:
        events: Parsed JSON event dicts from codex exec stdout.
        returncode: The process exit code.
        elapsed: Wall-clock seconds measured by the harness.
        model: The model id used for cost derivation.

    Returns:
        The claude-shaped result dict.
    """
    usage: dict[str, int] = {}
    last_message = ""
    for event in events:
        if event.get("type") == "turn.completed":
            u = event.get("usage", {})
            usage = {
                "input_tokens": u.get("input_tokens", 0),
                "output_tokens": u.get("output_tokens", 0),
                "cache_read_input_tokens": u.get("cached_input_tokens", 0),
                "cache_creation_input_tokens": u.get("cache_write_input_tokens", 0),
            }
        if event.get("type") == "item.completed":
            item = event.get("item", {})
            if item.get("type") == "agent_message":
                last_message = item.get("text", "")

    cost = _bedrock_cost_usd(
        model,
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_input_tokens", 0),
        cache_write_tokens=usage.get("cache_creation_input_tokens", 0),
    ) if model else None

    is_error = returncode != 0
    return {
        "usage": usage,
        "num_turns": 1,
        "total_cost_usd": cost,
        "is_error": is_error,
        "subtype": "success" if not is_error else f"exit_{returncode}",
        "duration_ms": round(elapsed * 1000),
        "result": last_message if not is_error else f"exit_{returncode}",
    }


def _run_codex(
    cmd: list[str],
    env: dict[str, str],
    timeout: int,
    model: str = "",
) -> dict[str, Any]:
    """Run ``codex exec --json`` and normalize its JSON-lines output.

    codex exec streams JSON-lines events to stdout. We accumulate them and
    parse on completion. Each line is also echoed to stderr as a live trace.

    Args:
        cmd: The codex exec command argument vector.
        env: Environment for the subprocess.
        timeout: Wall-clock timeout in seconds.

    Returns:
        The claude-shaped result dict (see ``_codex_result_from_events``).

    Raises:
        RuntimeError: If codex times out or produces no output.
    """
    start = time.time()
    proc = subprocess.Popen(  # nosec B603 B607 - hardcoded 'codex', list args, no shell
        cmd,
        env=env,
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:  # pragma: no cover
        raise RuntimeError("codex produced no stdout stream")
    events: list[dict[str, Any]] = []
    for line in proc.stdout:
        if time.time() - start > timeout:
            proc.kill()
            raise RuntimeError(f"codex timed out after {timeout}s")
        sys.stderr.write(line)
        sys.stderr.flush()
        line = line.strip()
        if line:
            try:
                parsed = json.loads(line)
                if isinstance(parsed, dict):
                    events.append(parsed)
            except json.JSONDecodeError:
                pass
    proc.wait()
    elapsed = time.time() - start

    if not events:
        raise RuntimeError(f"codex produced no output (exit {proc.returncode}).")
    result = _codex_result_from_events(events, proc.returncode, elapsed, model=model)
    result["_elapsed_seconds"] = round(elapsed, 1)
    return result


TOOL_RESULT_PREVIEW_CHARS = 500


def _tool_result_text(content: Any) -> str:
    """Flatten a tool_result block's content into plain text.

    The Anthropic message format allows a tool_result's ``content`` to be either
    a plain string or a list of content blocks (each a ``{"type": "text",
    "text": ...}`` mapping, though other block types may appear). This joins the
    text it can find so the trace can show what a tool actually returned.

    Args:
        content: The ``content`` field of a tool_result block.

    Returns:
        The extracted text, stripped. Empty when no text could be found.
    """
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and isinstance(block.get("text"), str)
        ]
        return "\n".join(texts).strip()
    return ""


def _truncate(text: str, limit: int, verbose: bool) -> str:
    """Return text as-is when verbose, else truncated to limit with a marker.

    Args:
        text: The text to (maybe) truncate.
        limit: Max characters to keep when not verbose.
        verbose: When True, never truncate.

    Returns:
        The full text (verbose) or a truncated preview with a "+N chars" tail.
    """
    if verbose or len(text) <= limit:
        return text
    return f"{text[:limit]}... (+{len(text) - limit} chars)"


def _format_stream_event(event: dict[str, Any], verbose: bool = False) -> str | None:
    """Render one stream-json event as a human-readable trace line.

    Args:
        event: A single parsed event object from `--output-format stream-json`.
        verbose: When True, print assistant text and tool results in full
            instead of truncating them (thinking is always shown in full).

    Returns:
        A summary to print, or None for events not worth showing.
    """
    etype = event.get("type")
    if etype == "system":
        subtype = event.get("subtype", "")
        # Reasoning models (e.g. Kimi K2 Thinking) stream a running estimate of
        # extended-thinking tokens as system/thinking_tokens events. Surface the
        # count instead of a bare, repeated subtype line.
        if subtype == "thinking_tokens":
            est = event.get("estimated_tokens")
            return f"[system] thinking ~{est:,} tokens" if est is not None else None
        return f"[system] {subtype}".rstrip()
    if etype == "result":
        return None  # The caller logs the final result separately.
    if etype not in ("assistant", "user"):
        return None
    blocks = (event.get("message") or {}).get("content") or []
    parts: list[str] = []
    for block in blocks:
        btype = block.get("type")
        if btype == "text" and block.get("text", "").strip():
            parts.append(f"[{etype}] {_truncate(block['text'].strip(), 200, verbose)}")
        elif btype == "thinking" and block.get("thinking", "").strip():
            # Print the full reasoning trace, not a preview: for reasoning models
            # the thinking is the interesting signal, and truncating it hides why
            # a run stalled or how it reached a decision.
            parts.append(f"[{etype}:thinking] {block['thinking'].strip()}")
        elif btype == "tool_use":
            # In verbose mode also show the tool's input arguments, so a blocked
            # or surprising command is fully visible in the trace.
            line = f"[tool] {block.get('name', '?')}"
            if verbose and block.get("input"):
                line += f" {json.dumps(block['input'], default=str)}"
            parts.append(line)
        elif btype == "tool_result":
            text = _tool_result_text(block.get("content"))
            preview = _truncate(text, TOOL_RESULT_PREVIEW_CHARS, verbose)
            marker = "[tool_result:error]" if block.get("is_error") else "[tool_result]"
            parts.append(f"{marker} {preview}" if preview else marker)
    return "\n".join(parts) if parts else None


def _run_claude_streaming(
    cmd: list[str], env: dict[str, str], timeout: int, verbose: bool = False
) -> dict[str, Any]:
    """Run `claude -p` in streaming mode, printing a live trace.

    Reads newline-delimited JSON events as they arrive, prints a short summary
    of each, and returns the final ``result`` event (the same shape
    _metrics_from_result consumes).

    Args:
        cmd: The command argument vector (must include stream-json/--verbose).
        env: Environment for the subprocess.
        timeout: Wall-clock timeout in seconds.
        verbose: When True, print assistant text and tool results in full
            instead of truncating them in the live trace.

    Returns:
        The parsed final result event.

    Raises:
        RuntimeError: If claude times out or never emits a result event.
    """
    start = time.time()
    proc = subprocess.Popen(  # nosec B603 - hardcoded 'claude', list args, no shell
        cmd,
        env=env,
        # Run from the repo root so the /swe skill's relative artifact paths
        # resolve correctly (see the note in _run_claude); otherwise a model that
        # writes a relative path doubles it to benchmarks/benchmarks/...
        cwd=str(REPO_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    final: dict[str, Any] | None = None
    thinking_tokens = 0
    # Latest estimate of the current extended-thinking burst, held back so we log
    # ONE summary line per burst instead of a line per streamed estimate. Flushed
    # when the next non-thinking event arrives (burst ended) and at stream end.
    pending_thinking: int | None = None
    if proc.stdout is None:  # pragma: no cover - stdout is always a pipe here
        raise RuntimeError("claude -p produced no stdout stream")

    def _flush_thinking() -> None:
        nonlocal pending_thinking
        if pending_thinking is not None:
            logger.info("  [system] thinking ~%s tokens", f"{pending_thinking:,}")
            pending_thinking = None

    try:
        for line in proc.stdout:
            if time.time() - start > timeout:
                proc.kill()
                raise RuntimeError(f"claude -p timed out after {timeout}s")
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # Non-JSON progress noise; skip.
            if event.get("type") == "result":
                _flush_thinking()
                final = event
            elif event.get("subtype") == "thinking_tokens":
                # Reasoning models stream a running token estimate every few
                # tokens. Track the peak (the result event omits it) and hold the
                # latest value; do NOT log per event -- _flush_thinking prints one
                # summary line once the burst ends.
                est = event.get("estimated_tokens")
                if isinstance(est, int):
                    thinking_tokens = max(thinking_tokens, est)
                    pending_thinking = est
            else:
                _flush_thinking()
                trace = _format_stream_event(event, verbose=verbose)
                if trace:
                    logger.info("  %s", trace)
        _flush_thinking()
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise RuntimeError(f"claude -p timed out after {timeout}s") from exc

    if final is None:
        stderr = (proc.stderr.read() if proc.stderr else "").strip()
        raise RuntimeError(
            f"claude -p emitted no result event (exit {proc.returncode}): "
            f"{stderr[:500]}"
        )
    final["_elapsed_seconds"] = round(time.time() - start, 1)
    # Only present when the model streamed thinking_tokens events; buffered
    # (non-streaming) runs never see these, so the field stays absent there.
    if thinking_tokens:
        final["_thinking_tokens_estimate"] = thinking_tokens
    return final


def _artifact_dir(config: RunnerConfig, task: Task) -> Path:
    """Return the directory where the skill writes a task's artifacts.

    Layout: ``benchmarks/<output_dir>/<model>/<harness>/<skill>/<repo>/<task>/``.
    Model, harness (coding agent), and skill are each their own path level, so
    runs never collide: a pi run never overwrites a Claude Code run, and a swe3
    run never overwrites a swe2 run of the same model. swe2 and swe3 are sibling
    folders under the harness -- they differ materially in token use and accuracy,
    so each is its own dimension rather than a suffix.

    Args:
        config: The runner config.
        task: The task being run.

    Returns:
        The absolute artifact directory path.
    """
    return (
        REPO_ROOT
        / "benchmarks"
        / config.output_dir
        / config.model_slug
        / config.harness_slug
        / config.skill
        / _repo_name(task.repo)
        / task.id
    )


def _summary_metrics(
    metrics: dict[str, Any],
    generation_tokens_per_sec: float,
    agent: str = "claude",
) -> dict[str, Any]:
    """Build the headline "metrics that matter" block for a run.

    Reports what the model API returned for the run plus derived totals.

    Args:
        metrics: The API-reported metrics from _metrics_from_result.
        generation_tokens_per_sec: Output-token throughput (output_tokens /
            latency_seconds), computed once by the caller.
        agent: The coding agent name (claude, pi, kiro).

    Returns:
        A flat summary dict of headline numbers plus a ``sources`` map naming the
        provenance of each. Values are None when no source could supply them.
    """
    api = f"{agent}_api"
    cache_read: int | None = metrics.get("cache_read_tokens")
    cache_write: int | None = metrics.get("cache_creation_tokens")
    cache_read_src = (
        f"{api}.usage.cache_read_input_tokens"
        if cache_read is not None
        else f"{api}.usage.cache_read_input_tokens (not reported)"
    )
    cache_write_src = (
        f"{api}.usage.cache_creation_input_tokens"
        if cache_write is not None
        else "unavailable (backend reports no cache-write signal)"
    )
    inp = metrics.get("input_tokens") or 0
    out = metrics.get("output_tokens") or 0
    total_tokens = inp + out + (cache_read or 0) + (cache_write or 0)
    token_src = (
        f"{api}.modelUsage (per-model rollup; INCLUDES subagent tokens)"
        if agent == "claude"
        else f"{api}.usage"
    )
    summary = {
        "note": "Headline metrics as reported by the model API.",
        "input_tokens": metrics.get("input_tokens"),
        "output_tokens": metrics.get("output_tokens"),
        "cache_read_tokens": cache_read,
        "cache_write_tokens": cache_write,
        "total_tokens": total_tokens,
        "total_cost_usd": metrics.get("total_cost_usd"),
        "latency_seconds": metrics.get("latency_seconds"),
        "num_turns": metrics.get("num_turns"),
        "generation_tokens_per_sec": generation_tokens_per_sec,
        "sources": {
            "input_tokens": f"{token_src}.input",
            "output_tokens": f"{token_src}.output",
            "cache_read_tokens": cache_read_src,
            "cache_write_tokens": cache_write_src,
            "total_tokens": "sum(input + output + cache_read + cache_write)",
            "total_cost_usd": (
                f"{api}.total_cost_usd (metered)"
                if metrics.get("total_cost_usd") is not None
                else "null (no per-token bill available)"
            ),
            "latency_seconds": f"harness wall-clock (or {api}.duration_ms)",
            "num_turns": f"{api}.num_turns",
            "generation_tokens_per_sec": "derived: output_tokens / latency_seconds",
        },
    }
    return summary


def _save_metrics(
    config: RunnerConfig,
    task: Task,
    ref: str,
    metrics: dict[str, Any],
) -> Path:
    """Write the run metrics to metrics.json in the artifact directory.

    Args:
        config: The runner config.
        task: The task that was run.
        ref: The git ref used.
        metrics: The API-reported metrics from _metrics_from_result.

    Returns:
        Path to the written metrics.json.
    """
    out_dir = _artifact_dir(config, task)
    out_dir.mkdir(parents=True, exist_ok=True)
    produced = [f for f in ARTIFACT_FILENAMES if (out_dir / f).exists()]
    latency = metrics["latency_seconds"] or 0
    generation_tokens_per_sec = (
        round(metrics["output_tokens"] / latency, 1) if latency > 0 else 0
    )
    token_accounting_warning = _check_token_accounting(
        metrics, config.agent, f"[task={task.id}]"
    )
    record = {
        "task": task.id,
        "repo": task.repo,
        "ref": ref,
        "complexity": task.complexity,
        "tags": task.tags,
        "model": config.model,
        "model_slug": config.model_slug,
        "agent": config.agent,
        "skill": config.skill,
        "provider": config.provider,
        "endpoint": config.endpoint if not config.is_bedrock else None,
        "aws_region": config.resolved_region() if config.is_bedrock else None,
        "serving": {
            "instance_type": config.resolved_instance_type(),
            "tensor_parallel_size": config.tensor_parallel_size,
            "precision": config.precision,
            "context_window": config.context_window or None,
        },
        "artifacts_produced": len(produced),
        "artifacts_expected": len(ARTIFACT_FILENAMES),
        "generation_tokens_per_sec": generation_tokens_per_sec,
        "token_accounting_warning": token_accounting_warning,
        "metrics": _summary_metrics(
            metrics,
            generation_tokens_per_sec,
            agent=config.agent,
        ),
        **metrics,
    }
    record["metrics_that_matter"] = record["metrics"]
    path = out_dir / "metrics.json"
    path.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
    return path


def _run_task(
    config: RunnerConfig,
    dataset: Dataset,
    task: Task,
    stream: bool = False,
    position: int = 1,
    total: int = 1,
    verbose: bool = False,
    topup_missing: list[str] | None = None,
) -> dict[str, Any]:
    """Run a single task end to end and return its outcome summary.

    Args:
        config: The runner config.
        dataset: The loaded dataset (for default-ref resolution).
        task: The task to run.
        stream: If True, print a live event trace while claude -p runs.
        position: This task's 1-based position in the run (for legible logs).
        total: Total number of tasks in the run.
        verbose: When True (and streaming), print assistant text and tool
            results in full instead of truncating them in the live trace.

    Returns:
        A summary dict: task id, ok flag, artifacts produced, and metrics.
    """
    ref = dataset.resolved_ref(task)
    label = f"[task={task.id}] {position} of {total}"
    logger.info("=== %s [%s] ref=%s ===", label, task.complexity, ref)

    clone_path = _clone_repo(task, ref, config.clone_dir, log_prefix=label)
    clone_parent = clone_path.parent
    try:
        prompt = _build_prompt(
            task,
            clone_path,
            ref,
            config.model_slug,
            _artifact_dir(config, task),
            agent=config.agent,
            skill=config.skill,
            topup_missing=topup_missing,
        )
        run_kind = f"top-up ({', '.join(topup_missing)})" if topup_missing else "run"
        # Build the agent-specific command + environment. pi and Claude Code run
        # the same /swe2 task but take entirely different flags and routing, so
        # this is the single branch point; everything downstream (metrics,
        # scraping, artifact checks) is agent-agnostic.
        if config.is_pi:
            # Per-run pi config dir under the clone parent so it is cleaned up
            # with the clone and never touches the developer's global ~/.pi.
            pi_agent_dir = clone_parent / "pi-agent"
            # Endpoint routing (LiteLLM proxy) needs a models.json; Bedrock is
            # built into pi so only settings.json is written there.
            if config.is_bedrock:
                pi_agent_dir.mkdir(parents=True, exist_ok=True)
                _write_pi_settings(config, pi_agent_dir)
            else:
                _write_pi_models_json(config, pi_agent_dir)
            cmd = _build_pi_cmd(config, prompt)
            env = _build_pi_env(config, pi_agent_dir)
            logger.info(
                "  %s Running pi -p %s (agent=pi, no turn cap)...", label, run_kind
            )
        elif config.is_kiro:
            # kiro-cli uses its own global sign-in (~/.kiro); there is no per-run
            # config dir to write and no endpoint to route. The SKILL.md is inlined
            # into the prompt by _build_kiro_cmd (kiro has no --skill flag).
            cmd = _build_kiro_cmd(config, prompt)
            env = _build_kiro_env(config)
            logger.info(
                "  %s Running kiro-cli chat %s (agent=kiro, no turn cap)...",
                label,
                run_kind,
            )
        elif config.is_codex:
            # codex exec runs non-interactively with --json output and full token
            # counts. It supports bedrock and endpoint providers.
            cmd = _build_codex_cmd(config, clone_path, prompt)
            env = _build_codex_env(config)
            logger.info(
                "  %s Running codex exec %s (agent=codex, no turn cap)...",
                label,
                run_kind,
            )
        elif config.is_omp:
            # omp is a fork of pi with a different binary and YAML config.
            # The SKILL.md is inlined into the prompt (omp has no --skill flag).
            omp_agent_dir = clone_parent / "omp-agent"
            if config.is_bedrock:
                # Bedrock path: no models.yml needed (routing is built-in),
                # but config.yml is still needed for compaction settings.
                window = config.context_window or 200000
                threshold = max(window - (config.max_output_tokens + 8192), 1)
                config_yml = {"compaction": {"enabled": True, "thresholdTokens": threshold}}
                omp_agent_dir.mkdir(parents=True, exist_ok=True)
                (omp_agent_dir / "config.yml").write_text(
                    yaml.safe_dump(config_yml, sort_keys=False), encoding="utf-8"
                )
            else:
                _write_omp_config(config, omp_agent_dir)
            cmd = _build_omp_cmd(config, prompt)
            env = _build_omp_env(config, omp_agent_dir)
            max_time_note = (
                f", max-time {config.agent_max_time_seconds}s"
                if config.agent_max_time_seconds
                else ""
            )
            logger.info(
                "  %s Running omp -p %s (agent=omp, no turn cap%s)...",
                label,
                run_kind,
                max_time_note,
            )
        else:
            cmd = _build_claude_cmd(
                config, prompt, stream=stream, clone_path=clone_path
            )
            env = _build_env(config)
            logger.info(
                "  %s Running claude -p %s (max_turns=%s)...",
                label,
                run_kind,
                config.max_turns,
            )
        # Wall-clock UTC bounds of the run. ISO 8601 with a trailing Z.
        run_started_at = _utc_now_iso()
        if config.is_pi:
            # pi emits a JSON-lines event stream; _run_pi normalizes it to the
            # same result shape. It has no separate streaming trace mode.
            result = _run_pi(cmd, env, config.timeout_seconds)
        elif config.is_kiro:
            # kiro-cli streams ANSI text and prints a Credits/Time summary on
            # stderr; _run_kiro normalizes that to the same result shape.
            result = _run_kiro(
                cmd, env, config.timeout_seconds, config.kiro_dollars_per_credit
            )
        elif config.is_codex:
            # codex exec outputs JSON-lines events; _run_codex normalizes them.
            result = _run_codex(cmd, env, config.timeout_seconds, model=config.model or "")
        elif config.is_omp:
            # omp emits the same JSON-lines event stream as pi.
            result = _run_omp(cmd, env, config.timeout_seconds)
        elif stream:
            result = _run_claude_streaming(
                cmd, env, config.timeout_seconds, verbose=verbose
            )
        else:
            result = _run_claude(cmd, env, config.timeout_seconds)
        run_ended_at = _utc_now_iso()
        metrics = _metrics_from_result(result, result.get("_elapsed_seconds", 0))
        metrics["run_started_at"] = run_started_at
        metrics["run_ended_at"] = run_ended_at
    finally:
        shutil.rmtree(clone_parent, ignore_errors=True)

    metrics_path = _save_metrics(config, task, ref, metrics)
    out_dir = metrics_path.parent
    produced = [f for f in ARTIFACT_FILENAMES if (out_dir / f).exists()]
    # Completeness is gated on the four DESIGN artifacts plus the implementation
    # patch: a /swe2 task is "ok" only when it both designed and implemented the
    # change (patch.diff present) and claude did not report an error. The banner
    # still shows the full produced count over all six artifacts.
    design_done = all((out_dir / f).exists() for f in DESIGN_ARTIFACT_FILENAMES)
    patch_done = (out_dir / "patch.diff").exists()
    ok = design_done and patch_done and not metrics["is_error"]

    # One-line outcome banner: artifacts, turns, tokens, latency.
    cache_suffix = ""
    thinking_suffix = ""
    if metrics.get("thinking_tokens_estimate"):
        thinking_suffix = f" (~{metrics['thinking_tokens_estimate']:,} thinking)"
    summary = (
        f"{label} | {'OK' if ok else 'INCOMPLETE'}: "
        f"{len(produced)}/{len(ARTIFACT_FILENAMES)} artifacts, "
        f"{metrics['num_turns']} turns, "
        f"{metrics['input_tokens']:,} in / {metrics['output_tokens']:,} out{thinking_suffix} tokens, "
        f"{metrics['latency_seconds']}s{cache_suffix}"
    )
    banner = "=" * len(summary)
    logger.info(banner)
    logger.info(summary)
    logger.info(banner)
    if metrics["is_error"]:
        logger.error(
            "  %s -p reported an error (status %s): %s",
            config.agent,
            metrics.get("api_error_status"),
            metrics.get("error"),
        )
    logger.info("  Metrics: %s", metrics_path)
    return {
        "task": task.id,
        "ok": ok,
        "artifacts": len(produced),
        "design_done": design_done,
        "patch_done": patch_done,
        "metrics": metrics,
    }


def _select_tasks(dataset: Dataset, task_ids: list[str], count: int = 0) -> list[Task]:
    """Select tasks to run, preserving dataset order.

    Args:
        dataset: The loaded dataset.
        task_ids: Task ids to run; empty means all tasks.
        count: Keep only the first ``count`` selected tasks; 0 means no limit.

    Returns:
        The tasks to run.

    Raises:
        DatasetError: If a requested id is not in the dataset or count is negative.
    """
    if count < 0:
        raise DatasetError(
            f"--count must be 0 (all) or a positive integer, got {count}"
        )
    if not task_ids:
        selected = dataset.tasks
    else:
        known = {t.id for t in dataset.tasks}
        missing = [tid for tid in task_ids if tid not in known]
        if missing:
            raise DatasetError(
                f"Unknown task ids: {missing}. Available: {sorted(known)}"
            )
        selected = [t for t in dataset.tasks if t.id in set(task_ids)]
    return selected[:count] if count else selected


def _dry_run(config: RunnerConfig, dataset: Dataset, tasks: list[Task]) -> None:
    """Print the prompt and command for each task without executing anything."""
    for task in tasks:
        ref = dataset.resolved_ref(task)
        placeholder = (
            Path(config.clone_dir)
            / f"swe-clone-{_safe_task_slug(task.id)}"
            / _repo_name(task.repo)
        )
        prompt = _build_prompt(
            task,
            placeholder,
            ref,
            config.model_slug,
            _artifact_dir(config, task),
            agent=config.agent,
            skill=config.skill,
        )
        if config.is_pi:
            cmd = _build_pi_cmd(config, prompt)
        elif config.is_kiro:
            cmd = _build_kiro_cmd(config, prompt)
        elif config.is_codex:
            cmd = _build_codex_cmd(config, placeholder, prompt)
        elif config.is_omp:
            cmd = _build_omp_cmd(config, prompt)
        else:
            cmd = _build_claude_cmd(config, prompt, clone_path=placeholder)
        print(f"\n=== {task.id} [{task.complexity}] ref={ref} ===")
        print("PROMPT:")
        print(prompt)
        print("\nCOMMAND:")
        print(" ".join(cmd))


def _summary_is_retryable(summary: dict[str, Any]) -> bool:
    """Decide whether a failed task summary warrants a retry.

    A task is retried only when it failed for a TRANSIENT reason. It is NOT
    retried when it simply exhausted its turn budget: another attempt at the
    same ``max_turns`` will hit the same wall, so the fix is a larger budget,
    not a retry.

    Turn exhaustion is identified by claude -p's result subtype
    ``error_max_turns``, or, defensively, by a run that used up (near) all of its
    turns without producing the design artifacts. Everything else that left the
    task not-ok (a stream/JSON/timeout RuntimeError, an api/execution error, an
    empty result) is treated as transient and retryable.

    Args:
        summary: A task outcome dict from :func:`_run_task` (or the RuntimeError
            fallback below), possibly carrying a ``metrics`` block.

    Returns:
        True if the task should be retried, False otherwise.
    """
    if summary.get("ok"):
        return False
    metrics = summary.get("metrics") or {}
    if metrics.get("result_subtype") == "error_max_turns":
        return False
    # Defensive fallback: no subtype recorded but the run clearly ran the turn
    # budget dry (e.g. an older claude that omits the subtype). Treat a run that
    # burned >=95% of max_turns without finishing the design as turn exhaustion.
    max_turns = summary.get("max_turns")
    num_turns = metrics.get("num_turns")
    if (
        max_turns
        and num_turns is not None
        and num_turns >= 0.95 * max_turns
        and not summary.get("design_done", False)
    ):
        return False
    return True


def _clear_partial_artifacts(config: RunnerConfig, task: Task) -> None:
    """Remove a task's partially-written artifacts before a retry.

    A transiently-failed attempt may have left some artifacts (and a
    metrics.json) behind. Clearing them keeps the retry a clean run and prevents
    a stale partial file from masking what the retry actually produced.
    """
    out_dir = _artifact_dir(config, task)
    for filename in (*ARTIFACT_FILENAMES, "metrics.json"):
        (out_dir / filename).unlink(missing_ok=True)


def _missing_artifacts(config: RunnerConfig, task: Task) -> list[str]:
    """Return the ARTIFACT_FILENAMES not yet present in the task's output dir."""
    out_dir = _artifact_dir(config, task)
    return [f for f in ARTIFACT_FILENAMES if not (out_dir / f).exists()]


def _maybe_topup(
    config: RunnerConfig,
    dataset: Dataset,
    task: Task,
    summary: dict[str, Any],
    *,
    stream: bool,
    position: int,
    total: int,
    verbose: bool,
) -> dict[str, Any]:
    """Complete a design-complete task that is missing implementation artifacts.

    The outer completion loop: after the main run (and any transient retries), if
    the task is still not ``ok`` but the four DESIGN artifacts are all present, it
    is the common "ran out of context right before patch.diff" case. Up to
    ``config.max_topups`` times, re-invoke the agent in a FRESH context with a
    focused prompt that produces ONLY the missing files, reading (never rewriting)
    the ones already on disk. Existing artifacts are NOT cleared, so a top-up can
    only add. Each top-up is a separate agent invocation, recorded on the returned
    summary and in metrics.json (``agent_invocations``, ``topped_up_artifacts``),
    so a completed-but-assisted run stays distinguishable from a clean one.

    Top-up is intentionally NOT attempted when the design is incomplete: a run
    that could not finish the design docs is a genuine quality failure, not a
    truncation to be patched over.

    Args:
        summary: The outcome from the main run/retries (mutated with top-up
            provenance and replaced by the latest attempt's summary).

    Returns:
        The final summary (ok if a top-up completed the artifact set).
    """
    invocations = summary.get("attempts", 1)
    topped_up: list[str] = []
    # Seed running totals from what is already on disk. That record already holds
    # the sum across any transient retries (_run_task_safe folded them in before
    # we were called), so top-ups accumulate on top of it. Fix for upstream #143.
    base = _read_json_file(_artifact_dir(config, task) / "metrics.json") or {}
    totals = {k: _pass_cost_value(base, k) for k in ADDITIVE_COST_FIELDS}
    for topup in range(1, config.max_topups + 1):
        if summary.get("ok"):
            break
        # Only design-complete tasks are eligible; a missing design doc is a real
        # failure, not a truncation to top up.
        design_done = all(
            (_artifact_dir(config, task) / f).exists()
            for f in DESIGN_ARTIFACT_FILENAMES
        )
        missing = _missing_artifacts(config, task)
        if not design_done or not missing:
            break
        logger.warning(
            "[task=%s] %s of %s: design complete but missing %s; top-up %s of %s",
            task.id,
            position,
            total,
            ", ".join(missing),
            topup,
            config.max_topups,
        )
        try:
            summary = _run_task(
                config,
                dataset,
                task,
                stream=stream,
                position=position,
                total=total,
                verbose=verbose,
                topup_missing=missing,
            )
        except RuntimeError:
            logger.exception(
                "[task=%s] %s of %s top-up failed", task.id, position, total
            )
            break
        invocations += 1
        # This top-up overwrote metrics.json with only its own pass; fold its
        # additive cost into the running totals.
        pass_metrics = (
            _read_json_file(_artifact_dir(config, task) / "metrics.json") or {}
        )
        _fold_pass_into_totals(totals, pass_metrics)
        topped_up = [f for f in missing if (_artifact_dir(config, task) / f).exists()]

    # Record top-up provenance so the run is honestly flagged as assisted.
    summary["max_turns"] = config.max_turns
    summary["agent_invocations"] = invocations
    summary["topped_up_artifacts"] = topped_up
    if invocations > 1:
        _annotate_metrics_topup(config, task, invocations, topped_up, totals)
    return summary


def _annotate_metrics_topup(
    config: RunnerConfig,
    task: Task,
    invocations: int,
    topped_up: list[str],
    totals: dict[str, Any],
) -> None:
    """Record top-up provenance + summed cost into the task's metrics.json.

    Thin wrapper over :func:`_write_cost_totals`. Refactored as part of
    upstream fix #143 to reuse the same cost-accumulation logic as retries.
    """
    _write_cost_totals(
        _artifact_dir(config, task) / "metrics.json",
        totals,
        invocations,
        topped_up=topped_up,
    )


def _read_json_file(path: Path) -> dict[str, Any] | None:
    """Return parsed JSON at ``path``, or None if absent/unreadable/invalid."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def _pass_cost_value(record: dict[str, Any], key: str) -> float:
    """Read one additive cost field from a single pass's metrics record.

    The normalized block is preferred over the top-level mirror because it is
    what ``summarize_run`` reads.
    """
    block = record.get("metrics") or record.get("metrics_that_matter") or {}
    val = block.get(MM_BLOCK_KEY.get(key, key))
    if val is None:
        val = record.get(key)
    return val or 0


def _fold_pass_into_totals(
    totals: dict[str, Any],
    record: dict[str, Any],
) -> dict[str, Any]:
    """Add one pass's additive cost fields into a running total dict (mutated)."""
    for key in ADDITIVE_COST_FIELDS:
        totals[key] = (totals.get(key) or 0) + _pass_cost_value(record, key)
    return totals


def _write_cost_totals(
    path: Path,
    totals: dict[str, Any],
    invocations: int,
    topped_up: list[str] | None = None,
) -> None:
    """Restore summed multi-invocation cost into a task's metrics.json.

    The final pass left metrics.json holding only its own numbers. This writes
    the summed additive fields to both the top-level fields AND the normalized
    block, because ``summarize_run`` reads the normalized block. Best-effort:
    a write failure is logged, not fatal. Fix for upstream issue #143.

    Args:
        path: The task's metrics.json.
        totals: Summed additive fields across every agent invocation.
        invocations: How many agent invocations the task actually took.
        topped_up: Artifacts produced by a top-up pass, when any.
    """
    record = _read_json_file(path)
    if record is None:
        return
    record.update(totals)
    # Recompute top-level generation_tokens_per_sec from summed parts.
    latency = totals.get("latency_seconds") or 0
    out = totals.get("output_tokens") or 0
    if "generation_tokens_per_sec" in record:
        record["generation_tokens_per_sec"] = round(out / latency, 1) if latency > 0 else 0
    for block_name in ("metrics", "metrics_that_matter"):
        block = record.get(block_name)
        if not isinstance(block, dict):
            continue
        for key, value in totals.items():
            target = MM_BLOCK_KEY.get(key, key)
            if target in block:
                block[target] = value
        # Recompute derived fields from the summed parts.
        if "total_tokens" in block:
            inp = totals.get("input_tokens") or 0
            out = totals.get("output_tokens") or 0
            cr = totals.get("cache_read_tokens") or 0
            cw = totals.get("cache_creation_tokens") or 0
            block["total_tokens"] = inp + out + cr + cw
        if "generation_tokens_per_sec" in block:
            latency = totals.get("latency_seconds") or 0
            out = totals.get("output_tokens") or 0
            block["generation_tokens_per_sec"] = (
                round(out / latency, 1) if latency > 0 else 0
            )
    record["agent_invocations"] = invocations
    if topped_up is not None:
        record["topped_up_artifacts"] = topped_up
    try:
        path.write_text(
            json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8"
        )
    except OSError:
        logger.warning("could not write summed cost totals to %s", path)


def _run_task_safe(
    config: RunnerConfig,
    dataset: Dataset,
    task: Task,
    stream: bool,
    position: int,
    total: int,
    verbose: bool = False,
) -> dict[str, Any]:
    """Run one task with transient-failure retries, returning its outcome.

    Wraps :func:`_run_task` so a single task's failure never aborts the whole
    run. Retries up to ``config.max_retries`` times, but ONLY for transient
    failures (see :func:`_summary_is_retryable`): a task that exhausted its turn
    budget is returned as-is without retrying. A RuntimeError from ``_run_task``
    (timeout, empty/non-JSON output, clone failure) is a transient failure and
    counts as an attempt.

    Used as the unit of work for both the serial loop and the thread pool.
    """
    attempts = config.max_retries + 1
    last: dict[str, Any] = {"task": task.id, "ok": False, "artifacts": 0}
    # Cost carried over from attempts that were discarded. A failed attempt still
    # burned real tokens/turns/cost, so dropping it understates the task's true
    # cost. metrics.json is read BEFORE the wipe; the sum is restored onto the
    # final record after the loop. Fix for upstream issue #143.
    carried: dict[str, Any] = {}
    metrics_path = _artifact_dir(config, task) / "metrics.json"
    for attempt in range(1, attempts + 1):
        if attempt > 1:
            logger.warning(
                "[task=%s] %s of %s: transient failure, retry %s of %s",
                task.id,
                position,
                total,
                attempt - 1,
                config.max_retries,
            )
            prior = _read_json_file(metrics_path)
            if prior is not None:
                _fold_pass_into_totals(carried, prior)
            _clear_partial_artifacts(config, task)
        try:
            summary = _run_task(
                config,
                dataset,
                task,
                stream=stream,
                position=position,
                total=total,
                verbose=verbose,
            )
        except RuntimeError:
            logger.exception("[task=%s] %s of %s failed", task.id, position, total)
            # A thrown RuntimeError is transient (timeout / no output / clone
            # error); record it as a retryable attempt.
            summary = {
                "task": task.id,
                "ok": False,
                "artifacts": 0,
                "metrics": {"is_error": True, "error": "run raised RuntimeError"},
            }
        summary["max_turns"] = config.max_turns
        summary["attempts"] = attempt
        last = summary
        if summary.get("ok") or not _summary_is_retryable(summary):
            break
    else:
        logger.error(
            "[task=%s] %s of %s: still failing after %s attempt(s)",
            task.id,
            position,
            total,
            attempts,
        )
    # Fold discarded attempts' costs back so metrics.json reports the task's
    # true total cost, not just the final pass.
    if carried:
        existing = _read_json_file(metrics_path) or {}
        # If no metrics.json exists (all attempts raised RuntimeError and were
        # wiped), seed a minimal record on disk so costs are not silently dropped.
        if not existing:
            existing = {
                "task": task.id,
                "is_error": True,
                "artifacts_produced": 0,
                "artifacts_expected": len(ARTIFACT_FILENAMES),
                "metrics": {},
                "metrics_that_matter": {},
            }
            try:
                metrics_path.parent.mkdir(parents=True, exist_ok=True)
                metrics_path.write_text(
                    json.dumps(existing, indent=2, default=str) + "\n",
                    encoding="utf-8",
                )
            except OSError:
                logger.warning("could not seed metrics.json for carried costs on %s", task.id)
        totals = _fold_pass_into_totals(dict(carried), existing)
        _write_cost_totals(metrics_path, totals, last.get("attempts", attempts))

    # Outer completion loop: if the task is design-complete but missing the
    # implementation artifacts, try focused top-ups to finish it (see _maybe_topup).
    if not last.get("ok") and config.max_topups > 0:
        last = _maybe_topup(
            config,
            dataset,
            task,
            last,
            stream=stream,
            position=position,
            total=total,
            verbose=verbose,
        )
    return last


def _run(
    config: RunnerConfig,
    dataset: Dataset,
    tasks: list[Task],
    stream: bool = False,
    verbose: bool = False,
) -> None:
    """Run every selected task and log a final pass/fail summary.

    Tasks run serially when ``config.concurrency`` is 1 (the default) and in a
    thread pool of that width otherwise.
    """
    concurrency = max(1, min(config.concurrency, len(tasks)))
    target = (
        f"Amazon Bedrock ({config.resolved_region()})"
        if config.is_bedrock
        else config.endpoint
    )
    logger.info(
        "Running %s task(s) with model=%s against %s (concurrency=%s)",
        len(tasks),
        config.model,
        target,
        concurrency,
    )

    total = len(tasks)
    if concurrency == 1:
        summaries = [
            _run_task_safe(
                config,
                dataset,
                task,
                stream,
                position=i,
                total=total,
                verbose=verbose,
            )
            for i, task in enumerate(tasks, start=1)
        ]
    else:
        summaries = _run_concurrent(config, dataset, tasks, stream, concurrency)

    passed = sum(1 for s in summaries if s["ok"])
    logger.info("=" * 60)
    logger.info("Done: %s/%s tasks produced all artifacts.", passed, len(summaries))
    for s in summaries:
        logger.info(
            "  %s %s (%s artifacts)",
            "OK " if s["ok"] else "FAIL",
            s["task"],
            s["artifacts"],
        )


def _run_concurrent(
    config: RunnerConfig,
    dataset: Dataset,
    tasks: list[Task],
    stream: bool,
    concurrency: int,
) -> list[dict[str, Any]]:
    """Run tasks in a thread pool of the given width, preserving task order.

    Each task clones into its own temp dir and writes to a distinct artifact
    dir, and claude -p runs as an independent subprocess, so the work is safe to
    parallelize. Streaming is disabled here because interleaved event traces from
    concurrent tasks are unreadable.

    Returns:
        Summary dicts in the same order as ``tasks``.
    """
    if stream:
        logger.warning("Disabling --stream under concurrency; traces would interleave.")
    total = len(tasks)
    results: list[dict[str, Any]] = [{} for _ in tasks]
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        future_to_index = {
            executor.submit(
                _run_task_safe, config, dataset, task, False, index + 1, total
            ): index
            for index, task in enumerate(tasks)
        }
        for future in as_completed(future_to_index):
            index = future_to_index[future]
            results[index] = future.result()
    return results


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    CLI flags override the corresponding runner-config fields.
    """
    parser = argparse.ArgumentParser(
        description="Run the SWE benchmark headless via claude -p and the /swe skill.",
        epilog=(
            "Examples:\n"
            "  uv run scripts/run-swe-headless.py --config config/runner.example.yaml\n"
            "  uv run scripts/run-swe-headless.py --config config/runner.example.yaml "
            "--model qwen3-coder-30b --tasks remove-faiss,remove-efs-from-terraform-aws-ecs\n"
            "  uv run scripts/run-swe-headless.py --config config/runner.example.yaml --dry-run"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--config", help="Path to the runner config YAML file")
    parser.add_argument(
        "--agent",
        help="Override: coding agent that runs the task ('claude' for Claude "
        "Code, 'pi' for the pi coding agent). Both support provider=endpoint "
        "or provider=bedrock.",
    )
    parser.add_argument(
        "--skill",
        help="Override: SWE skill to run ('swe2' multi-agent fan-out, the "
        "default, or 'swe3' single-agent, no subagents). Same six artifacts; "
        "swe3 results land under a '<harness>-swe3' folder so they never "
        "overwrite swe2 results.",
    )
    parser.add_argument(
        "--provider",
        help="Override: routing provider ('endpoint' for a base URL, 'bedrock' "
        "for native Amazon Bedrock)",
    )
    parser.add_argument("--endpoint", help="Override: API endpoint base URL")
    parser.add_argument("--model", help="Override: model name")
    parser.add_argument(
        "--aws-region",
        help="Override: AWS region for provider=bedrock (e.g. us-east-1)",
    )
    parser.add_argument(
        "--instance-type",
        help="Override: EC2 instance type served on (e.g. p5en.48xlarge). "
        "Defaults to the EC2 metadata service when unset.",
    )
    parser.add_argument(
        "--tensor-parallel-size",
        type=int,
        help="Override: tensor-parallel size the model is served with. "
        "Recorded in the metrics.json serving block.",
    )
    parser.add_argument(
        "--precision",
        help="Override: served weight precision (e.g. BF16, FP8). Recorded in the "
        "metrics.json serving block.",
    )
    parser.add_argument("--dataset", help="Override: dataset YAML path")
    parser.add_argument(
        "--tasks", help="Override: comma-separated task ids to run (default: all)"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Run only the first N selected tasks (default: 0 = all)",
    )
    parser.add_argument("--max-turns", type=int, help="Override: cap on the agent loop")
    parser.add_argument(
        "--max-retries",
        type=int,
        help="Override: retries for a task that fails TRANSIENTLY (stream/JSON/"
        "timeout/api error). A task that ran out of turns is never retried. "
        "0 disables retries.",
    )
    parser.add_argument(
        "--max-topups",
        type=int,
        help="Override: focused top-up attempts when the main run left artifacts "
        "missing but the design docs are complete. A top-up re-invokes the agent "
        "in a fresh context to produce ONLY the missing files (existing ones are "
        "kept), flagged in metrics.json. 0 disables.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        help="Override: per-response output-token cap (CLAUDE_CODE_MAX_OUTPUT_TOKENS). "
        "Lower it on a small-window model so the prompt has usable input room "
        "(usable input ~= context_window - max_output_tokens).",
    )
    parser.add_argument(
        "--context-window",
        type=int,
        help="Override: the model's true context window in tokens. Calibrates "
        "auto-compaction (CLAUDE_CODE_AUTO_COMPACT_WINDOW) for custom models "
        "whose window Claude Code cannot detect. 0 leaves it unset.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        help="Override: wall-clock timeout for a single task's claude -p run. "
        "Raise it for a slow (e.g. dense) model that produces artifacts but "
        "does not return within the default before the harness kills it.",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        help="Override: how many tasks to run at once (default 1 = serial). "
        "Values above 1 overlap runs on the endpoint.",
    )
    parser.add_argument(
        "--kiro-dollars-per-credit",
        type=float,
        help="Override (agent=kiro only): USD per kiro-cli credit, used to turn "
        "the credits kiro-cli reports into a dollar cost per task. Default 0.04 "
        "(Kiro add-on/overage rate); use 0.02 for the blended included rate.",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Print prompts/commands without running"
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Print a live event trace as each task runs (uses stream-json)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="With --stream, print assistant text and tool results in full "
        "instead of truncating them in the live trace",
    )
    return parser.parse_args()


def main() -> None:
    """Parse arguments, load config and dataset, and run the benchmark."""
    args = _parse_args()
    overrides: dict[str, Any] = {
        "agent": args.agent,
        "skill": args.skill,
        "provider": args.provider,
        "endpoint": args.endpoint,
        "model": args.model,
        "aws_region": args.aws_region,
        "instance_type": args.instance_type,
        "tensor_parallel_size": args.tensor_parallel_size,
        "precision": args.precision,
        "dataset": args.dataset,
        "max_turns": args.max_turns,
        "max_retries": args.max_retries,
        "max_topups": args.max_topups,
        "max_output_tokens": args.max_output_tokens,
        "context_window": args.context_window,
        "timeout_seconds": args.timeout_seconds,
        "concurrency": args.concurrency,
        "kiro_dollars_per_credit": args.kiro_dollars_per_credit,
    }
    if args.tasks:
        overrides["tasks"] = [t.strip() for t in args.tasks.split(",") if t.strip()]

    try:
        config = load_runner_config(args.config, overrides)
    except RunnerConfigError as exc:
        logger.error("Config error: %s", exc)
        sys.exit(1)

    dataset_path = config.dataset
    if not Path(dataset_path).is_absolute():
        dataset_path = str(Path(__file__).resolve().parent.parent / dataset_path)
    try:
        dataset = load_dataset(dataset_path)
        tasks = _select_tasks(dataset, config.tasks, args.count)
    except DatasetError as exc:
        logger.error("Dataset error: %s", exc)
        sys.exit(1)

    if args.dry_run:
        _dry_run(config, dataset, tasks)
        return
    if args.verbose and not args.stream:
        logger.warning("--verbose has no effect without --stream; ignoring it.")
    _run(config, dataset, tasks, stream=args.stream, verbose=args.verbose)


if __name__ == "__main__":
    main()
