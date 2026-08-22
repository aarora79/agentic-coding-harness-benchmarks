#!/usr/bin/env python3
"""Executor and escalation loop for the /swe-auto skill.

The /swe-auto skill's model-driven triage (in SKILL.md) classifies a task into a
tier; this module then does the mechanical rest of the mermaid flow in
docs/vision.md: consult the frontier, pick the model (via swe_auto_router), run
``/swe3`` through the in-repo headless runner over an ephemeral one-task dataset,
optionally judge it, and escalate one tier and re-run when the result falls short
-- bounded by ``max_escalations``. Every attempt and the final decision are
written to ``routing.json`` beside the artifacts.

v1 runs the in-repo runner in place (Option B / monorepo): no packaging, no
vendored copy. The runner's sibling imports and venv resolve because we invoke it
from the ``benchmarks/`` directory.

    uv run scripts/swe_auto_run.py --tier workhorse \\
        --repo https://github.com/agentic-community/mcp-gateway-registry \\
        --ref 1.24.4 --problem remove-faiss \\
        --config ../.claude/skills/swe-auto/swe-auto.yaml

Add ``--dry-run`` to preview the routing decision without executing anything.
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess  # nosec B404 - list-form calls to hardcoded uv, no shell
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from runner_config import HARNESS_SLUGS, model_to_slug  # noqa: E402
from swe_auto_router import (  # noqa: E402
    ModelExecution,
    RouterError,
    Selection,
    SweAutoConfig,
    frontier_entries,
    load_config,
    load_frontier,
    next_tier,
    resolve_execution,
    runnable_entries,
    select_model,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

_REPO_ROOT = _SCRIPTS_DIR.parent.parent
_BENCHMARKS_DIR = _SCRIPTS_DIR.parent
_OUTPUT_DIR = "swe-benchmark-data"

# The six /swe3 artifacts; a run is "complete" only when all six exist.
_ARTIFACT_FILENAMES = (
    "github-issue.md",
    "lld.md",
    "review.md",
    "testing.md",
    "patch.diff",
    "implementation.md",
)

# Outer wall-clock caps. The runner enforces its own per-task timeout (default
# 2h) and self-kills; ours is a generous backstop above that so a hung child is
# still reaped. The judge is a single codex run.
_EXECUTOR_TIMEOUT_SECONDS = 10800
_JUDGE_TIMEOUT_SECONDS = 1800


# Which CLI each agent needs on PATH for the executor to drive it.
_AGENT_CLI = {"claude": "claude", "pi": "pi", "kiro": "kiro-cli"}


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with a trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _preflight(config: SweAutoConfig) -> tuple[list[str], list[str]]:
    """Check standalone prerequisites; return (blocking problems, warnings).

    Blocking: ``uv``, the agent CLI (claude/pi/kiro-cli), the ``codex`` judge when
    ``judge`` is on, and the executed skill's SKILL.md. Warnings cover credentials
    the executor validates itself (the Bedrock path needs the ``aws`` CLI). Model
    and endpoint credentials are checked by the headless runner at launch, so this
    stays fast and non-networked.

    Args:
        config: The routing config.

    Returns:
        A (problems, warnings) pair; an empty ``problems`` list means it is safe
        to run.
    """
    problems: list[str] = []
    warnings: list[str] = []
    if shutil.which("uv") is None:
        problems.append("uv is not on PATH (install: https://docs.astral.sh/uv/).")
    agent_cli = _AGENT_CLI[config.agent]
    if shutil.which(agent_cli) is None:
        problems.append(
            f"'{agent_cli}' CLI is not on PATH (harness={config.harness} runs it)."
        )
    if config.judge and shutil.which("codex") is None:
        problems.append(
            "'codex' CLI is not on PATH but judge is enabled. Install codex, set "
            "judge:false in swe-auto.yaml, or pass --no-judge."
        )
    skill_md = _REPO_ROOT / ".claude" / "skills" / config.skill / "SKILL.md"
    if not skill_md.exists():
        problems.append(f"the /{config.skill} skill was not found at {skill_md}.")
    if shutil.which("aws") is None:
        warnings.append(
            "the 'aws' CLI is not on PATH; the Bedrock executor path needs AWS "
            "credentials (self-hosted endpoint models do not)."
        )
    return problems, warnings


def _repo_name(repo_url: str) -> str:
    """Derive the kebab-case repo basename from a clone URL (matches the harness)."""
    return repo_url.rstrip("/").rsplit("/", 1)[-1].removesuffix(".git")


def _ephemeral_dataset_dict(
    repo: str,
    ref: str,
    problem: str,
    problem_statement: str | None = None,
    problem_issue_url: str | None = None,
) -> dict[str, Any]:
    """Build a one-task dataset mapping the headless runner accepts.

    The runner is dataset-driven, so /swe-auto hands it a synthetic single-task
    dataset instead of adding a new task interface. A task needs at least one
    problem source, and the runner's prompt builder uses both: a full
    ``problem_statement`` (the verbose description) and/or a ``problem_issue_url``
    (a GitHub issue link it appends as "Reference issue: <url>"). Rules:

    - a ``problem_statement`` is used verbatim when given;
    - otherwise, when only an issue URL is given, the URL is the sole source (no
      synthetic statement, so the issue stays authoritative);
    - when neither is given, a short pointer referencing the slug keeps the task
      valid.

    Args:
        repo: The repository clone URL.
        ref: The pinned git ref.
        problem: The task slug (also the artifact subfolder name).
        problem_statement: The full task description to hand /swe3.
        problem_issue_url: A GitHub issue URL the task derives from.

    Returns:
        A dict shaped like a dataset YAML with exactly one task.
    """
    task: dict[str, Any] = {
        "id": problem,
        "repo": repo,
        "ref": ref,
        "complexity": "medium",
        "tags": ["swe-auto"],
    }
    statement = (problem_statement or "").strip()
    if statement:
        task["problem_statement"] = statement
    elif not problem_issue_url:
        task["problem_statement"] = (
            f"Complete the task '{problem}' in {repo} at ref {ref}. "
            "See the /swe-auto invocation for the full problem description."
        )
    if problem_issue_url:
        task["problem_issue_url"] = problem_issue_url
    return {
        "schema_version": "1.0",
        "name": "swe-auto-ephemeral",
        "title": "swe-auto ephemeral single-task dataset",
        "description": "Generated by /swe-auto for one routed task; not committed.",
        "default_ref": ref,
        "metrics": ["input_tokens", "output_tokens", "num_turns"],
        "complexity_levels": ["low", "medium", "high"],
        "tasks": [task],
    }


def _write_ephemeral_dataset(
    repo: str,
    ref: str,
    problem: str,
    problem_statement: str | None = None,
    problem_issue_url: str | None = None,
) -> Path:
    """Write the one-task dataset to a temp YAML file and return its path."""
    data = _ephemeral_dataset_dict(
        repo, ref, problem, problem_statement, problem_issue_url
    )
    handle = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix=f"swe-auto-{problem}-",
        delete=False,
        encoding="utf-8",
    )
    with handle:
        yaml.safe_dump(data, handle, sort_keys=False)
    return Path(handle.name)


def _artifact_dir(
    config: SweAutoConfig, execution: ModelExecution, repo: str, problem: str
) -> Path:
    """Return the artifact dir the runner will write to for this model+task.

    Mirrors the harness layout exactly (reusing ``model_to_slug`` and
    ``HARNESS_SLUGS``) so /swe-auto reads back the same folder the runner wrote:
    ``benchmarks/swe-benchmark-data/<model-slug>/<harness>/<skill>/<repo>/<task>``.
    """
    slug = model_to_slug(execution.model)
    harness = HARNESS_SLUGS[config.agent]
    return (
        _BENCHMARKS_DIR
        / _OUTPUT_DIR
        / slug
        / harness
        / config.skill
        / _repo_name(repo)
        / problem
    )


def _build_runner_cmd(
    config: SweAutoConfig, execution: ModelExecution, dataset_path: Path, problem: str
) -> list[str]:
    """Assemble the ``uv run scripts/run-swe-headless.py`` argument vector.

    Passes the selected model, provider, and routing on the CLI (no --config), so
    the runner builds its config purely from these overrides. The runner clones
    the repo, drives /swe3, and writes the six artifacts + metrics.json.

    Args:
        config: The routing config (agent, skill, aws_region).
        execution: The selected model's launch recipe.
        dataset_path: The ephemeral one-task dataset file.
        problem: The task slug to run (the sole task in the dataset).

    Returns:
        The command as a list (never a shell string).
    """
    cmd = [
        "uv",
        "run",
        "scripts/run-swe-headless.py",
        "--agent",
        config.agent,
        "--skill",
        config.skill,
        "--provider",
        execution.provider,
        "--model",
        execution.model,
        "--dataset",
        str(dataset_path),
        "--tasks",
        problem,
    ]
    if execution.provider == "endpoint" and execution.endpoint:
        cmd += ["--endpoint", execution.endpoint]
    if execution.provider == "bedrock" and config.aws_region:
        cmd += ["--aws-region", config.aws_region]
    return cmd


def _stream_subprocess(cmd: list[str], cwd: Path, timeout: int) -> int:
    """Run a command, streaming its output to stderr, and return the exit code.

    Args:
        cmd: The argument vector (hardcoded tool + list args, no shell).
        cwd: Working directory for the child.
        timeout: Wall-clock cap in seconds.

    Returns:
        The child's exit code.

    Raises:
        RouterError: If the command times out.
    """
    start = time.time()
    proc = subprocess.Popen(  # nosec B603 - list-form, hardcoded 'uv', no shell
        cmd,
        cwd=str(cwd),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    if proc.stdout is None:  # pragma: no cover - stdout is always a pipe here
        raise RouterError("subprocess produced no stdout stream")
    for line in proc.stdout:
        if time.time() - start > timeout:
            proc.kill()
            raise RouterError(f"command timed out after {timeout}s: {cmd[:4]} ...")
        sys.stderr.write(line)
        sys.stderr.flush()
    proc.wait()
    return proc.returncode


def _run_judge(artifact_dir: Path) -> bool:
    """Score one artifact folder with the codex judge; return True on success.

    Best-effort: a judge failure is logged and returns False (the run's
    completeness is still known from the artifacts), so scoring problems do not
    crash the router.
    """
    cmd = [
        "uv",
        "run",
        "scripts/codex_judge.py",
        "--folder",
        str(artifact_dir),
    ]
    try:
        rc = _stream_subprocess(cmd, _BENCHMARKS_DIR, _JUDGE_TIMEOUT_SECONDS)
    except RouterError as exc:
        logger.warning("judge did not finish: %s", exc)
        return False
    if rc != 0:
        logger.warning("judge exited %s for %s", rc, artifact_dir)
    return rc == 0


def _read_json(path: Path) -> dict[str, Any] | None:
    """Return the parsed JSON object at ``path``, or None if absent/invalid."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _read_outcome(
    artifact_dir: Path, band_floor: float | None, judge: bool
) -> dict[str, Any]:
    """Assess a completed run: completeness, score, in-band, cost, error.

    Args:
        artifact_dir: The task's artifact directory.
        band_floor: The tier's minimum score, or None for the frontier tier.
        judge: Whether the judge ran (so a score is expected).

    Returns:
        A dict with complete, artifacts_produced, score, in_band, cost, is_error.
    """
    produced = [f for f in _ARTIFACT_FILENAMES if (artifact_dir / f).exists()]
    complete = len(produced) == len(_ARTIFACT_FILENAMES)
    metrics = _read_json(artifact_dir / "metrics.json") or {}
    mm = metrics.get("metrics") or metrics.get("metrics_that_matter") or {}
    cost = mm.get("total_cost_usd", metrics.get("total_cost_usd"))
    is_error = bool(metrics.get("is_error"))
    # Only trust a score when the judge ran THIS pass; otherwise a stale eval.json
    # left in a reused folder would be misattributed to this run.
    score: float | None = None
    if judge:
        eval_data = _read_json(artifact_dir / "eval.json")
        if eval_data and isinstance(eval_data.get("task_score"), (int, float)):
            score = float(eval_data["task_score"])
    # With judge off, completeness alone gates success. With judge on, the score
    # must also clear the tier's band (None band = frontier tier, always in band).
    if not judge or band_floor is None:
        in_band = True
    else:
        in_band = score is not None and score >= band_floor
    return {
        "complete": complete,
        "artifacts_produced": len(produced),
        "score": score,
        "in_band": in_band,
        "cost": cost,
        "is_error": is_error,
    }


def _attempt_record(
    tier: str,
    selection: Selection,
    execution: ModelExecution,
    runner_rc: int,
    outcome: dict[str, Any],
) -> dict[str, Any]:
    """Build one escalation-attempt record for routing.json."""
    return {
        "tier": tier,
        "selected_model": selection.selected_model,
        "wire_model": execution.model,
        "provider": execution.provider,
        "band_floor": selection.band_floor,
        "clears_band_by_frontier_data": selection.clears_band,
        "rationale": selection.rationale,
        "runner_exit_code": runner_rc,
        "complete": outcome["complete"],
        "artifacts_produced": outcome["artifacts_produced"],
        "score": outcome["score"],
        "in_band": outcome["in_band"],
        "cost_usd": outcome["cost"],
        "is_error": outcome["is_error"],
    }


def _run_one_attempt(
    config: SweAutoConfig,
    runnable: list[Any],
    tier: str,
    repo: str,
    problem: str,
    dataset_path: Path,
) -> tuple[dict[str, Any], bool]:
    """Select, execute, (judge,) and assess a single attempt at a tier.

    Returns:
        An (attempt record, satisfied) pair. ``satisfied`` is True when the run
        completed, had no error, and (with judge on) scored in band.

    Raises:
        RouterError: If no candidate can be selected or resolved.
    """
    selection = select_model(runnable, tier, config)
    if selection.selected_entry is None:
        raise RouterError(f"no model could be selected for tier '{tier}'.")
    execution = resolve_execution(config, selection.selected_entry)
    if execution is None:  # pragma: no cover - runnable_entries guarantees a recipe
        raise RouterError(
            f"selected model '{selection.selected_model}' is not runnable."
        )
    logger.info(
        "attempt tier=%s -> model=%s (%s %s)",
        tier,
        selection.selected_model,
        execution.provider,
        execution.model,
    )
    cmd = _build_runner_cmd(config, execution, dataset_path, problem)
    runner_rc = _stream_subprocess(cmd, _BENCHMARKS_DIR, _EXECUTOR_TIMEOUT_SECONDS)
    artifact_dir = _artifact_dir(config, execution, repo, problem)
    if config.judge:
        _run_judge(artifact_dir)
    outcome = _read_outcome(artifact_dir, selection.band_floor, config.judge)
    satisfied = outcome["complete"] and not outcome["is_error"] and outcome["in_band"]
    record = _attempt_record(tier, selection, execution, runner_rc, outcome)
    record["artifact_dir"] = str(artifact_dir)
    return record, satisfied


def run_swe_auto(
    config: SweAutoConfig,
    tier: str,
    repo: str,
    ref: str,
    problem: str,
    problem_statement: str | None = None,
    problem_issue_url: str | None = None,
) -> dict[str, Any]:
    """Run the full route-execute-escalate loop and write routing.json.

    Args:
        config: The routing config.
        tier: The tier the router model classified the task into.
        repo: Repository clone URL.
        ref: Pinned git ref.
        problem: Task slug.
        problem_statement: Full task description handed to /swe3 (see
            ``_ephemeral_dataset_dict``).
        problem_issue_url: A GitHub issue URL the task derives from (an
            alternative or supplement to ``problem_statement``).

    Returns:
        The routing record (also written to routing.json in the final artifact dir).

    Raises:
        RouterError: On unrecoverable selection/frontier/config errors, or when a
            preflight prerequisite is missing.
    """
    problems, warnings = _preflight(config)
    for warning in warnings:
        logger.warning("preflight: %s", warning)
    if problems:
        raise RouterError("preflight failed:\n  - " + "\n  - ".join(problems))
    frontier, provenance = load_frontier(config)
    entries = frontier_entries(frontier, config.frontier_scope)
    runnable = runnable_entries(entries, config)
    if not runnable:
        raise RouterError(
            "no frontier model is runnable in this environment. Configure "
            "model_execution / an endpoint in swe-auto.yaml (Bedrock models run "
            "with AWS credentials by default)."
        )
    dataset_path = _write_ephemeral_dataset(
        repo, ref, problem, problem_statement, problem_issue_url
    )
    initial_tier = tier
    attempts: list[dict[str, Any]] = []
    try:
        for attempt_index in range(config.max_escalations + 1):
            record, satisfied = _run_one_attempt(
                config, runnable, tier, repo, problem, dataset_path
            )
            record["attempt"] = attempt_index + 1
            record["escalated_from"] = (
                None if attempt_index == 0 else attempts[-1]["tier"]
            )
            attempts.append(record)
            if satisfied:
                break
            upper = next_tier(tier)
            if upper is None or attempt_index == config.max_escalations:
                logger.warning(
                    "attempt fell short and cannot escalate further (tier=%s).", tier
                )
                break
            logger.warning("escalating tier %s -> %s and re-running.", tier, upper)
            tier = upper
    finally:
        dataset_path.unlink(missing_ok=True)

    final = attempts[-1]
    record = {
        "task": {
            "repo": repo,
            "ref": ref,
            "problem": problem,
            "problem_issue_url": problem_issue_url,
        },
        "initial_tier": initial_tier,
        "final_tier": final["tier"],
        "selected_model": final["selected_model"],
        "harness": config.harness,
        "skill": config.skill,
        "router_model": config.router_model,
        "frontier_scope": config.frontier_scope,
        "budget_posture": config.budget_posture,
        "candidates_considered": [e.model for e in runnable],
        "pricing_basis": final["selected_model"] and _pricing_basis(runnable, final),
        "judge_enabled": config.judge,
        "succeeded": bool(
            attempts
            and attempts[-1]["complete"]
            and not attempts[-1]["is_error"]
            and attempts[-1]["in_band"]
        ),
        "escalations": attempts,
        "frontier_file": provenance.get("frontier_file"),
        "frontier_source": provenance.get("frontier_source"),
        "frontier_as_of": _now_iso(),
        "frontier_stale_warning": provenance.get("stale"),
        "routed_at": _now_iso(),
    }
    _write_routing_json(Path(final["artifact_dir"]), record)
    return record


def _pricing_basis(runnable: list[Any], final_attempt: dict[str, Any]) -> str | None:
    """Return the pricing basis (metered/hardware-derived) of the final model."""
    for entry in runnable:
        if entry.model == final_attempt["selected_model"]:
            return entry.pricing_basis
    return None


def _write_routing_json(artifact_dir: Path, record: dict[str, Any]) -> Path:
    """Write routing.json into the final artifact directory."""
    artifact_dir.mkdir(parents=True, exist_ok=True)
    path = artifact_dir / "routing.json"
    path.write_text(json.dumps(record, indent=2, default=str) + "\n", encoding="utf-8")
    logger.info("wrote %s", path)
    return path


def _preview(config: SweAutoConfig, tier: str) -> dict[str, Any]:
    """Select without executing (for --dry-run): return the decision as a dict."""
    frontier, provenance = load_frontier(config)
    entries = frontier_entries(frontier, config.frontier_scope)
    runnable = runnable_entries(entries, config)
    selection = select_model(runnable, tier, config)
    execution = (
        resolve_execution(config, selection.selected_entry)
        if selection.selected_entry
        else None
    )
    return {
        "provenance": provenance,
        "runnable_models": [e.model for e in runnable],
        "selection": selection.model_dump(mode="json"),
        "execution": execution.model_dump(mode="json") if execution else None,
    }


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Route a task to a model and execute /swe3 via the headless runner.",
        epilog="Example:\n  uv run scripts/swe_auto_run.py --tier workhorse "
        "--repo <url> --ref 1.24.4 --problem remove-faiss "
        "--config ../.claude/skills/swe-auto/swe-auto.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--tier",
        required=True,
        choices=("budget", "workhorse", "frontier"),
        help="Tier the router model classified the task into.",
    )
    parser.add_argument(
        "--repo", help="Repository clone URL (required unless --dry-run)."
    )
    parser.add_argument("--ref", help="Pinned git ref (required unless --dry-run).")
    parser.add_argument("--problem", help="Task slug (required unless --dry-run).")
    parser.add_argument(
        "--problem-statement",
        help="Full task description handed to /swe3. Optional if --problem-issue-url "
        "is given; otherwise defaults to a generic pointer referencing the slug.",
    )
    parser.add_argument(
        "--problem-issue-url",
        help="GitHub issue URL the task derives from, appended to the /swe3 prompt "
        "as 'Reference issue: <url>'. May be used instead of --problem-statement.",
    )
    parser.add_argument("--config", help="Path to swe-auto.yaml.")
    parser.add_argument("--frontier-file", help="Override: frontier JSON URL or path.")
    parser.add_argument(
        "--frontier-scope", help="Override: combined|bedrock-only|self-hosted-only."
    )
    parser.add_argument("--budget-posture", help="Override: cheap|balanced|best.")
    parser.add_argument("--harness", help="Override: claude-code|pi.")
    parser.add_argument("--max-escalations", type=int, help="Override: escalation cap.")
    parser.add_argument(
        "--no-judge", action="store_true", help="Disable the judge for this run."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the routing decision without cloning, running, or judging.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="Only check prerequisites (CLIs, judge, skill) and report; do not run.",
    )
    return parser.parse_args()


def main() -> None:
    """Parse args, load config, and either preview or run the full loop."""
    args = _parse_args()
    overrides: dict[str, Any] = {
        "frontier_file": args.frontier_file,
        "frontier_scope": args.frontier_scope,
        "budget_posture": args.budget_posture,
        "harness": args.harness,
        "max_escalations": args.max_escalations,
    }
    if args.no_judge:
        overrides["judge"] = False
    try:
        config = load_config(args.config, overrides)
    except RouterError as exc:
        logger.error("config error: %s", exc)
        sys.exit(1)

    if args.preflight:
        problems, warnings = _preflight(config)
        for warning in warnings:
            logger.warning("preflight: %s", warning)
        if problems:
            logger.error("preflight failed:\n  - %s", "\n  - ".join(problems))
            sys.exit(1)
        logger.info(
            "preflight OK: prerequisites for harness=%s present.", config.harness
        )
        return

    if args.dry_run:
        try:
            preview = _preview(config, args.tier)
        except RouterError as exc:
            logger.error("routing error: %s", exc)
            sys.exit(1)
        print(json.dumps(preview, indent=2, default=str))
        return

    if not (args.repo and args.ref and args.problem):
        logger.error("--repo, --ref, and --problem are required unless --dry-run.")
        sys.exit(1)
    try:
        record = run_swe_auto(
            config,
            args.tier,
            args.repo,
            args.ref,
            args.problem,
            args.problem_statement,
            args.problem_issue_url,
        )
    except RouterError as exc:
        logger.error("routing error: %s", exc)
        sys.exit(1)
    print(json.dumps(record, indent=2, default=str))
    sys.exit(0 if record["succeeded"] else 2)


if __name__ == "__main__":
    main()
