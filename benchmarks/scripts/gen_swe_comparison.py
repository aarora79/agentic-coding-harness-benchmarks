#!/usr/bin/env python3
"""Generate the cross-model, cross-harness /swe3 comparison doc.

The swe counterpart to agentic-coding-model-comparison.md (which is throughput/
serving-economics from the synthetic sweep). This one is built from the REAL
/swe3 benchmark runs and combines the three axes a buyer trades off -- quality,
tokens, and cost -- for every model under BOTH harnesses (Claude Code and pi),
plus wall-clock latency.

Numbers come from gen_agent_report (_collect + _row_cost), so this doc, the
per-harness docs, and the charts all agree. The doc embeds:
  * the unified both-harness cost-vs-quality Pareto chart (headline), and
  * the four-panel per-model scorecard for each harness,
which are rendered by plot_cost_quality_harness.py and plot_model_scorecard.py.

Usage:
    uv run scripts/gen_swe_comparison.py                 # -> docs/agentic-coding-swe-comparison.md
    uv run scripts/gen_swe_comparison.py --skill swe3 --out-dir ../docs
"""

from __future__ import annotations

import argparse
import importlib.util
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

_GEN_PATH = _SCRIPTS_DIR / "gen_agent_report.py"
_spec = importlib.util.spec_from_file_location("gen_agent_report", _GEN_PATH)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

HARNESSES = ("claude-code", "pi")
HARNESS_LABELS = {"claude-code": "Claude Code", "pi": "pi"}
HARNESS_CODES = {"claude-code": "cc", "pi": "pi"}


def _human_tokens(value: float) -> str:
    """Compact token count (e.g. 82.7M)."""
    if value >= 1e9:
        return f"{value / 1e9:.1f}B"
    if value >= 1e6:
        return f"{value / 1e6:.1f}M"
    if value >= 1e3:
        return f"{value / 1e3:.0f}K"
    return f"{value:.0f}"


def _rows(data_dir: Path, harness: str, skill: str, repo: str) -> list[dict[str, Any]]:
    """Collect display rows (score, tokens, cost, cost/task, cost/point, mins)."""
    out: list[dict[str, Any]] = []
    for r in gen._collect(data_dir, harness, skill, repo):
        cost_str, basis = gen._row_cost(r)
        scored = r.get("num_scored") or 0
        cost = None if cost_str == "--" else float(cost_str.lstrip("$"))
        mean = r.get("mean")
        out.append(
            {
                "model": r["model"],
                "mean": mean,
                "completed": f"{scored}/{r.get('num_tasks')}",
                "total_tokens": r.get("total_tokens") or 0,
                "cost": cost,
                "cost_str": cost_str,
                "basis": basis,
                "cost_per_task": (cost / scored) if (cost and scored) else None,
                "cost_per_point": (cost / mean) if (cost and mean) else None,
                "minutes": (r.get("latency_seconds") or 0) / 60.0,
                "bedrock": basis.startswith("metered"),
            }
        )
    return out


def _table(rows: list[dict[str, Any]], label: str) -> list[str]:
    """Render one harness's results table (sorted by score)."""
    ordered = sorted(rows, key=lambda r: (r["mean"] is None, -(r["mean"] or 0.0)))
    lines = [
        f"### {label}",
        "",
        "| Model | Hosting | Mean score | Completed | Tokens processed | "
        "Run cost | Cost/task | Cost/point | Wall-clock |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for r in ordered:
        host = "Bedrock" if r["bedrock"] else "self-hosted"
        mean = "-- (0 scored)" if r["mean"] is None else f"{r['mean']:.2f}"
        cpt = f"${r['cost_per_task']:.2f}" if r["cost_per_task"] else "--"
        cpp = f"${r['cost_per_point']:.2f}" if r["cost_per_point"] else "--"
        wall = f"{r['minutes']:.0f}m" if r["minutes"] else "--"
        lines.append(
            f"| {r['model']} | {host} | {mean} | {r['completed']} | "
            f"{_human_tokens(r['total_tokens'])} | {r['cost_str']} | {cpt} | "
            f"{cpp} | {wall} |"
        )
    lines.append("")
    return lines


def _render(data_dir: Path, skill: str, repo: str, out_dir: Path) -> str:
    """Render the full comparison document."""
    per = {h: _rows(data_dir, h, skill, repo) for h in HARNESSES}
    img = "images"

    def _cheapest_per_point(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        vals = [r for r in rows if r["cost_per_point"]]
        return min(vals, key=lambda r: r["cost_per_point"]) if vals else None

    def _best_score(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
        vals = [r for r in rows if r["mean"] is not None]
        return max(vals, key=lambda r: r["mean"]) if vals else None

    lines = [
        f"# Agentic coding: model comparison on /{skill} (quality, tokens, cost)",
        "",
        "How every benchmarked model compares as an **agentic coding** engine on "
        f"real `/{skill}` tasks against `{repo}`, under **both harnesses** (Claude "
        "Code and pi). Unlike the serving-economics view in "
        "[agentic-coding-model-comparison.md](agentic-coding-model-comparison.md) "
        "(synthetic throughput sweep), this doc is built from the actual benchmark "
        "runs and combines the three axes a buyer trades off -- **quality, tokens, "
        "and cost** -- plus wall-clock latency.",
        "",
        "Generated from the committed `run-summary.json` files; regenerate with "
        f"`uv run scripts/gen_swe_comparison.py --skill {skill}`. Numbers match the "
        "per-harness docs ([Claude Code]("
        f"harness-claude-code-{skill}.md), [pi](harness-pi-{skill}.md)) and the "
        "charts below exactly.",
        "",
        "## Cost basis (read this first)",
        "",
        "Two non-comparable cost bases share the cost columns; each row states which:",
        "",
        "- **metered (Bedrock)** -- a hosted API's real per-token bill, summed over "
        "the run. Benefits from Bedrock prompt caching.",
        "- **hardware-derived (self-hosted)** -- a rented GPU has no per-token bill, "
        "so cost is the model's blended $/token (measured by the throughput sweep "
        "at its true instance rate -- g6e.12xlarge for L40S, p5en.48xlarge for "
        "H200) times the tokens the run processed. See "
        "[cost-per-task-methodology.md](cost-per-task-methodology.md).",
        "",
        "`Cost/task` = run cost / scored tasks. `Cost/point` = run cost / mean score "
        "-- a value-efficiency figure (lower is more quality per dollar).",
        "",
        "## The one chart: cost vs. quality, both harnesses",
        "",
        "x = cost per task, y = mean score. Color = harness (Claude Code vs pi); "
        "marker shape = hosting (circle self-hosted, square Bedrock); a thin line "
        "joins the same model across harnesses; the dashed line is the Pareto "
        "frontier over all points (nothing else both cheaper and higher-scoring).",
        "",
        f"![Cost vs quality, both harnesses]({img}/cost-quality-harness-{skill}.png)",
        "",
        "## Results by harness",
        "",
        "Each row: quality (mean score), tokens processed, run cost + the two "
        "normalized cost lenses, and wall-clock. Sorted by score.",
        "",
    ]
    for h in HARNESSES:
        lines += _table(per[h], HARNESS_LABELS[h])
        code = HARNESS_CODES[h]
        lines += [
            f"Per-model scorecard ({HARNESS_LABELS[h]}) -- tokens, cost, accuracy, "
            "and latency side by side:",
            "",
            f"![{HARNESS_LABELS[h]} scorecard]({img}/scorecard-{code}-{skill}.png)",
            "",
        ]

    # Data-derived takeaways (so the prose never drifts from the tables).
    lines += ["## Takeaways", ""]
    for h in HARNESSES:
        best = _best_score(per[h])
        cheap = _cheapest_per_point(per[h])
        if best and cheap:
            lines.append(
                f"- **{HARNESS_LABELS[h]}:** highest score is **{best['model']}** "
                f"({best['mean']:.1f}); best value (lowest $/point) is "
                f"**{cheap['model']}** at ${cheap['cost_per_point']:.2f}/point "
                f"(score {cheap['mean']:.1f})."
            )
    lines += [
        "- **Cost bases are not comparable as raw dollars** -- a Bedrock metered "
        "bill and a hardware-derived self-hosted figure answer different questions; "
        "compare within a hosting column, and treat cross-hosting ties as "
        "order-of-magnitude, not exact (see the methodology doc).",
        "- **The same model can sit very differently under the two harnesses** -- "
        "the connectors on the chart show it; use the per-harness scorecards to see "
        "the token/latency drivers behind a cost gap.",
        "",
        "## How to reproduce",
        "",
        "```bash",
        "cd benchmarks",
        f"uv run python scripts/gen_swe_comparison.py --skill {skill}",
        "# charts:",
        f"uv run python scripts/plot_cost_quality_harness.py --skill {skill}",
        f"uv run python scripts/plot_model_scorecard.py --harness pi --skill {skill}",
        f"uv run python scripts/plot_model_scorecard.py --harness claude-code --skill {skill}",
        "```",
    ]
    return "\n".join(lines).rstrip("\n") + "\n"


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Generate the cross-harness /swe comparison doc from run-summaries.",
        epilog="Example: uv run scripts/gen_swe_comparison.py --skill swe3",
    )
    parser.add_argument("--skill", default="swe3", help="SWE skill (default: swe3).")
    parser.add_argument("--repo", default="mcp-gateway-registry", help="Dataset scope.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    return parser.parse_args()


def main() -> None:
    """Render the comparison doc and write it under out-dir."""
    args = _parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    doc = _render(data_dir, args.skill, args.repo, args.out_dir.expanduser().resolve())
    out_dir = args.out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"agentic-coding-swe-comparison-{args.skill}.md"
    out_path.write_text(doc, encoding="utf-8")
    logger.info("wrote %s", out_path)


if __name__ == "__main__":
    main()
