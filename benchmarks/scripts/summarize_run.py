#!/usr/bin/env python3
"""Summarize one model+dataset benchmark run into RUN-SUMMARY.json and .md.

Reads a ``{model-slug}/{harness}/{scope}/`` folder under ``swe-benchmark-data``
(one subfolder per task, each with ``metrics.json`` and, when scored, ``eval.json``)
and writes two sibling files:

  * ``RUN-SUMMARY.json`` -- machine-readable, for later charting / aggregation.
  * ``RUN-SUMMARY.md``   -- human-readable, rendered from the same data.

A task that scored 0 is treated as a model failure (missing/empty artifacts) and
is EXCLUDED from the headline mean (score and cost), matching the leaderboard
convention; it is still listed with its 0 so the failure stays visible.

Usage:
    uv run scripts/summarize_run.py --folder ../swe-benchmark-data/gemma-4-31b/claude-code/mcp-gateway-registry
    uv run scripts/summarize_run.py --folder <dir> --run-date 2026-07-24
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Everything a full /swe2 run emits: the four design artifacts plus the
# implementation artifact (patch.diff + implementation.md). The produced count
# in the run summary is out of all six.
ARTIFACT_FILENAMES = (
    "github-issue.md",
    "lld.md",
    "review.md",
    "testing.md",
    "patch.diff",
    "implementation.md",
)


def _read_json(path: Path) -> dict[str, Any] | None:
    """Return the parsed JSON object at ``path``, or None if absent/invalid."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _task_row(task_dir: Path) -> dict[str, Any] | None:
    """Build one task's summary row from its metrics.json and eval.json.

    Args:
        task_dir: A single task's artifact directory.

    Returns:
        A row dict, or None if the folder has no metrics.json (not a task).
    """
    metrics = _read_json(task_dir / "metrics.json")
    if metrics is None:
        return None
    mm = metrics.get("metrics_that_matter", {}) or {}
    eval_data = _read_json(task_dir / "eval.json")
    score = None
    if eval_data and isinstance(eval_data.get("task_score"), (int, float)):
        score = float(eval_data["task_score"])
    produced = sum(1 for f in ARTIFACT_FILENAMES if (task_dir / f).exists())
    return {
        "task": task_dir.name,
        "complexity": metrics.get("complexity"),
        "artifacts_produced": produced,
        "artifacts_expected": len(ARTIFACT_FILENAMES),
        "num_turns": mm.get("num_turns"),
        "input_tokens": mm.get("input_tokens"),
        "output_tokens": mm.get("output_tokens"),
        "latency_seconds": mm.get("latency_seconds"),
        "total_cost_usd": metrics.get("total_cost_usd"),
        "task_score": score,
        # Embed the judge's per-artifact criterion breakdown (from eval.json) so
        # RUN-SUMMARY.json is self-contained -- the committed rollup carries the
        # scores + judge notes even though the per-task eval.json is gitignored.
        # None when the task was not scored (a failure or no judge run).
        "eval_scores": (eval_data or {}).get("scores"),
        "is_error": metrics.get("is_error"),
        "failed": not score,  # 0 or missing score == model failure
    }


def _summarize(folder: Path, run_date: str | None) -> dict[str, Any]:
    """Aggregate every task folder under ``folder`` into a summary dict.

    Args:
        folder: The ``{model-slug}/{scope}/`` run directory.
        run_date: Optional ISO date to stamp; omitted when None.

    Returns:
        The structured summary (also written as RUN-SUMMARY.json).

    Raises:
        SystemExit: If no task folders with metrics.json are found.
    """
    rows = [
        row
        for task_dir in sorted(p for p in folder.iterdir() if p.is_dir())
        if (row := _task_row(task_dir)) is not None
    ]
    if not rows:
        raise SystemExit(f"no task folders with metrics.json under {folder}")

    # Identity/serving from the first task's metrics (uniform across a run).
    first = _read_json(folder / rows[0]["task"] / "metrics.json") or {}
    # RUN-SUMMARY.json is committed to git, so drop the judge block's local-only
    # temp path (repo_root, e.g. /tmp/swe-judge-repos/...); it is machine-specific
    # noise, not provenance worth committing.
    judge = dict((first.get("evaluation") or {}).get("judge") or {})
    judge.pop("repo_root", None)
    scored = [r for r in rows if not r["failed"]]
    failed = [r for r in rows if r["failed"]]
    mean_score = (
        round(sum(r["task_score"] for r in scored) / len(scored), 2) if scored else None
    )
    costs = [r["total_cost_usd"] for r in scored if r["total_cost_usd"] is not None]
    mean_cost = round(sum(costs) / len(costs), 2) if costs else None

    # Layout: <model-slug>/<harness>/<repo>. folder is the <repo> (scope) dir, so
    # its parent is the harness and its grandparent is the model slug.
    summary: dict[str, Any] = {
        "model": first.get("model"),
        "model_slug": folder.parent.parent.name,
        "agent": first.get("agent") or folder.parent.name,
        "scope": folder.name,
        "provider": first.get("provider"),
        "ref": first.get("ref"),
        "serving": first.get("serving"),
        "judge": judge or None,
        "num_tasks": len(rows),
        "num_scored": len(scored),
        "num_failed": len(failed),
        "failed_tasks": [r["task"] for r in failed],
        "mean_task_score_excl_failed": mean_score,
        "mean_cost_usd_excl_failed": mean_cost,
        "tasks": sorted(rows, key=lambda r: r["task_score"] or -1, reverse=True),
    }
    if run_date:
        summary["run_date"] = run_date
    return summary


def _render_markdown(summary: dict[str, Any]) -> str:
    """Render the human-readable RUN-SUMMARY.md from the summary dict."""
    s = summary
    serving = s.get("serving") or {}
    serving_line = (
        ", ".join(f"{k}={v}" for k, v in serving.items() if v is not None) or "n/a"
    )
    headline = (
        f"{s['num_scored']} of {s['num_tasks']} tasks scored"
        + (
            f"; {s['num_failed']} failed ({', '.join(s['failed_tasks'])}), "
            "excluded from the mean"
            if s["num_failed"]
            else "; no failures"
        )
        + "."
    )
    lines = [
        f"# Benchmark run summary: {s['model']} on {s['scope']}",
        "",
        f"- Model: {s['model']}",
        f"- Provider: {s['provider']}",
        f"- Dataset scope: {s['scope']} ({s['num_tasks']} tasks, ref {s['ref']})",
        f"- Serving: {serving_line}",
    ]
    if s.get("run_date"):
        lines.append(f"- Run date: {s['run_date']}")
    lines += [
        "",
        headline,
        "",
        "## Results",
        "",
        "| Task | Artifacts | Turns | Cost (est $) | Judge score |",
        "|---|---|---|---|---|",
    ]
    for r in s["tasks"]:
        score = "0.0 (model failure)" if r["failed"] else r["task_score"]
        cost = f"{r['total_cost_usd']:.2f}" if r["total_cost_usd"] is not None else "--"
        lines.append(
            f"| {r['task']} | {r['artifacts_produced']}/{r['artifacts_expected']} "
            f"| {r['num_turns']} | {cost} | {score} |"
        )
    lines += [
        "",
        f"Mean over the {s['num_scored']} completed tasks: "
        f"{s['mean_task_score_excl_failed']} "
        f"(mean cost ${s['mean_cost_usd_excl_failed']}). A 0-score task is a model "
        "failure (missing artifacts) and is excluded from the means, pending "
        "investigation. Cost is a token-based estimate for self-hosted models.",
        "",
    ]
    return "\n".join(lines) + "\n"


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Write RUN-SUMMARY.json and RUN-SUMMARY.md for a benchmark run.",
    )
    parser.add_argument(
        "--folder",
        required=True,
        type=Path,
        help="The {model-slug}/{scope}/ run directory under swe-benchmark-data.",
    )
    parser.add_argument(
        "--run-date",
        default=None,
        help="Optional ISO date to stamp in the summary (e.g. 2026-07-24).",
    )
    return parser.parse_args()


def main() -> None:
    """Summarize a run folder into RUN-SUMMARY.json and RUN-SUMMARY.md."""
    args = _parse_args()
    folder = args.folder.expanduser().resolve()
    if not folder.is_dir():
        raise SystemExit(f"not a directory: {folder}")
    summary = _summarize(folder, args.run_date)

    json_path = folder / "RUN-SUMMARY.json"
    json_path.write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    md_path = folder / "RUN-SUMMARY.md"
    md_path.write_text(_render_markdown(summary), encoding="utf-8")
    logger.info(
        "wrote %s and %s (%d scored, %d failed, mean %.2f)",
        json_path,
        md_path,
        summary["num_scored"],
        summary["num_failed"],
        summary["mean_task_score_excl_failed"] or 0.0,
    )


if __name__ == "__main__":
    main()
