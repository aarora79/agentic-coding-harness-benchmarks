#!/usr/bin/env python3
"""Generate a per-agent (per-harness) results document from committed summaries.

For one coding agent (``claude-code``, ``pi``, ...) this walks every model's
committed ``run-summary.json`` under that harness and renders a single Markdown
file with:

  * a per-model results table (mean score, completion, tokens, wall-clock,
    hardware-derived cost), and
  * the two headline charts for that harness (cost-vs-quality Pareto and the
    quality radar), which the chart scripts render with harness-suffixed names.

The doc is regenerated from data, so it never drifts from the run-summaries.
Charts are NOT rendered here -- run ``plot_cost_quality.py --harness <h>`` and
``plot_quality_radar.py --harness <h>`` first; this only embeds them.

Usage:
    uv run scripts/gen_agent_report.py --harness pi
    uv run scripts/gen_agent_report.py --harness claude-code --out-dir ../docs
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

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BENCHMARKS_DIR = _SCRIPTS_DIR.parent
_REPO_ROOT = _BENCHMARKS_DIR.parent
DEFAULT_DATA_DIR = _BENCHMARKS_DIR / "swe-benchmark-data"
DEFAULT_OUT_DIR = _REPO_ROOT / "docs"
RUN_SUMMARY_FILENAME = "run-summary.json"

# g6e.12xlarge on-demand, the default self-hosted node here. Cost on a rented GPU
# is hardware-derived: ($/hr / 3600) x wall-clock seconds (see
# docs/cost-per-task-methodology.md). This is a display default only.
DEFAULT_DOLLARS_PER_HOUR = 10.49

# Human labels for the harness slug used in the doc title and prose.
HARNESS_LABELS = {
    "claude-code": "Claude Code",
    "pi": "pi",
    "opencode": "opencode",
    "kiro-cli": "kiro-cli",
}


def _read_json(path: Path) -> dict[str, Any] | None:
    """Return the parsed JSON object at ``path``, or None if absent/invalid."""
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _run_totals(summary: dict[str, Any]) -> dict[str, Any]:
    """Sum a run's per-task tokens, wall-clock, and metered cost into totals.

    Args:
        summary: One model's run-summary dict.

    Returns:
        Dict with total input/output tokens, total latency seconds, and total
        metered cost (the sum of per-task ``total_cost_usd``; None on the
        self-hosted path where the model reports no per-token price).
    """
    tasks = summary.get("tasks", []) or []
    tin = sum((t.get("input_tokens") or 0) for t in tasks)
    tout = sum((t.get("output_tokens") or 0) for t in tasks)
    tsec = sum((t.get("latency_seconds") or 0) for t in tasks)
    costs = [t.get("total_cost_usd") for t in tasks if t.get("total_cost_usd")]
    metered_cost = sum(costs) if costs else None
    return {
        "input_tokens": tin,
        "output_tokens": tout,
        "latency_seconds": tsec,
        "metered_cost": metered_cost,
    }


def _collect(data_dir: Path, harness: str, repo: str) -> list[dict[str, Any]]:
    """Return one row per model that has a run-summary under this harness.

    Reads ``<data-dir>/<model>/<harness>/<repo>/run-summary.json``. Rows are
    sorted by mean score (a None mean -- a full harness collapse -- sorts last).
    """
    rows: list[dict[str, Any]] = []
    for model_dir in sorted(p for p in data_dir.iterdir() if p.is_dir()):
        summary = _read_json(model_dir / harness / repo / RUN_SUMMARY_FILENAME)
        if summary is None:
            continue
        totals = _run_totals(summary)
        rows.append(
            {
                # Prefer the clean slug (e.g. "claude-opus-5") over the raw id
                # ("us.anthropic.claude-opus-5[1m]") for a readable table.
                "model": summary.get("model_slug") or model_dir.name,
                "provider": summary.get("provider"),
                "mean": summary.get("mean_task_score_excl_failed"),
                "num_scored": summary.get("num_scored"),
                "num_tasks": summary.get("num_tasks"),
                "failed_tasks": summary.get("failed_tasks") or [],
                "run_date": summary.get("run_date"),
                **totals,
            }
        )
    rows.sort(key=lambda r: (r["mean"] is None, -(r["mean"] or 0.0)))
    return rows


def _row_cost(row: dict[str, Any], dollars_per_hour: float) -> tuple[str, str]:
    """Return (cost string, basis label) for a model row.

    Two cost bases, never mixed on one number:
      * **metered** -- a hosted API (provider=bedrock) reports a real per-token
        bill; use the summed ``total_cost_usd``.
      * **hardware** -- a self-hosted model has no per-token price, so cost is
        derived from the GPU it rents: ``($/hr / 3600) x wall-clock seconds``.

    Applying the GPU hourly rate to a Bedrock run (or vice versa) would be
    nonsense, so the basis is chosen per row and labelled in its own column.

    Args:
        row: A collected model row (provider, metered_cost, latency_seconds).
        dollars_per_hour: Instance $/hr for the hardware-derived basis.

    Returns:
        A ``(cost, basis)`` pair, e.g. ``("$0.63", "metered (Bedrock)")``.
    """
    if row.get("provider") == "bedrock":
        cost = row.get("metered_cost")
        return (f"${cost:.2f}" if cost else "--", "metered (Bedrock)")
    seconds = row.get("latency_seconds") or 0
    if not seconds:
        return ("--", "hardware-derived")
    return (f"${seconds * dollars_per_hour / 3600.0:.2f}", "hardware-derived")


def _render(
    rows: list[dict[str, Any]],
    *,
    harness: str,
    repo: str,
    dollars_per_hour: float,
    out_dir: Path,
) -> str:
    """Render the per-agent Markdown doc from the collected rows."""
    label = HARNESS_LABELS.get(harness, harness)
    # Charts live in docs/images; link relative to the doc's out_dir.
    img = (out_dir / "images").resolve()
    cq = img / (
        "cost-quality.png"
        if harness == "claude-code"
        else f"cost-quality-{harness}.png"
    )
    radar = img / (
        "quality-radar.png"
        if harness == "claude-code"
        else f"quality-radar-{harness}.png"
    )

    def _rel(p: Path) -> str:
        try:
            return p.relative_to(out_dir.resolve()).as_posix()
        except ValueError:
            return p.as_posix()

    lines = [
        f"# Results: {label} harness",
        "",
        f"Benchmark results for every model run under the **{label}** coding agent "
        f"on `{repo}`, generated from the committed `run-summary.json` files. "
        "Regenerate with `uv run scripts/gen_agent_report.py --harness "
        f"{harness}`. Companion to the cross-agent [harness comparison]"
        "(harness-comparison.md).",
        "",
        "## Results by model",
        "",
        "| Model | Mean score | Completed | Total tokens | Wall-clock | Run cost | Cost basis* |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    any_hardware = False
    any_metered = False
    for r in rows:
        mean = "-- (0 scored)" if r["mean"] is None else f"{r['mean']:.2f}"
        completed = f"{r['num_scored']}/{r['num_tasks']}"
        tok = f"{r['input_tokens'] + r['output_tokens']:,}"
        mins = (r["latency_seconds"] or 0) / 60.0
        wall = f"{mins:.1f}m" if mins else "--"
        cost, basis = _row_cost(r, dollars_per_hour)
        any_hardware = any_hardware or basis == "hardware-derived"
        any_metered = any_metered or basis.startswith("metered")
        lines.append(
            f"| {r['model']} | {mean} | {completed} | {tok} | {wall} | {cost} | {basis} |"
        )
    # The cost column mixes two bases that are NOT comparable as raw dollars: a
    # metered API bill vs a GPU-time estimate. Spell that out so no one reads the
    # column as a single apples-to-apples number.
    note = [
        "\\* **Cost basis differs by row and the dollars are NOT directly comparable.**"
    ]
    if any_hardware:
        note.append(
            f" _hardware-derived_ (self-hosted vLLM): a rented GPU has no per-token "
            f"bill, so cost is `($/hr / 3600) x wall-clock seconds` at g6e.12xlarge "
            f"on-demand (${dollars_per_hour}/hr)."
        )
    if any_metered:
        note.append(
            " _metered (Bedrock)_: a hosted API's real per-token bill, summed over "
            "the run. It is a metered invoice, not a hardware estimate, and (unlike "
            "the self-hosted rows) it benefits from Bedrock prompt caching."
        )
    note.append(" See [cost-per-task-methodology.md](cost-per-task-methodology.md).")
    lines += [
        "",
        "".join(note),
        "",
        "A task scoring 0 (missing/empty artifacts) is a model failure, excluded "
        "from the mean but counted in `Completed`. A model with 0 scored tasks "
        "did not complete any task under this harness.",
        "",
        "## Charts",
        "",
        "### Cost vs. quality (Pareto frontier)",
        "",
        f"![Cost vs quality, {label} harness]({_rel(cq)})",
        "",
        "### Quality by dimension (radar)",
        "",
        f"![Quality radar, {label} harness]({_rel(radar)})",
    ]
    # Exactly one trailing newline (the end-of-file-fixer hook strips extras).
    return "\n".join(lines).rstrip("\n") + "\n"


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate a per-agent results doc from committed run-summaries.",
        epilog="Example: uv run scripts/gen_agent_report.py --harness pi",
    )
    parser.add_argument(
        "--harness",
        required=True,
        help="Harness slug: claude-code, pi, opencode, kiro-cli.",
    )
    parser.add_argument("--repo", default="mcp-gateway-registry", help="Dataset scope.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help="Directory to write harness-<slug>.md into (default: docs/).",
    )
    parser.add_argument(
        "--dollars-per-hour",
        type=float,
        default=DEFAULT_DOLLARS_PER_HOUR,
        help="Instance $/hr for the hardware-derived cost column.",
    )
    return parser.parse_args()


def main() -> None:
    """Collect one harness's run-summaries and write its results doc."""
    args = _parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    rows = _collect(data_dir, args.harness, args.repo)
    if not rows:
        raise SystemExit(
            f"no run-summary.json found under {data_dir}/*/{args.harness}/{args.repo}"
        )
    doc = _render(
        rows,
        harness=args.harness,
        repo=args.repo,
        dollars_per_hour=args.dollars_per_hour,
        out_dir=args.out_dir.expanduser().resolve(),
    )
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"harness-{args.harness}.md"
    out_path.write_text(doc, encoding="utf-8")
    logger.info("wrote %s (%d models)", out_path, len(rows))


if __name__ == "__main__":
    main()
