#!/usr/bin/env python3
"""Unified cost-vs-quality Pareto scatter with BOTH harnesses on one chart.

One view that encapsulates the core trade-off across harnesses:

  * x = cost per task (USD)          y = mean task score (0-100)
  * color = harness                  (claude-code vs pi)
  * marker shape = cost basis        (circle = self-hosted, square = Bedrock)
  * a thin connector joins the SAME model across the two harnesses, so the
    per-model harness trade-off (cheaper? better?) reads at a glance
  * a dashed Pareto frontier over ALL points (both harnesses): the set where
    nothing else is both higher-scoring AND cheaper

Cost per task = each run's total cost / scored tasks, from gen_agent_report
(_collect + _row_cost) so it matches the harness docs. A model with no derivable
cost or no scored tasks is dropped with a logged note.

Usage:
    uv run scripts/plot_cost_quality_harness.py --skill swe3
    uv run scripts/plot_cost_quality_harness.py --skill swe3 --dark

Output: docs/images/cost-quality-harness-<skill>{,-dark}.png
"""

from __future__ import annotations

import argparse
import importlib.util
import logging
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
DEFAULT_DATA_DIR = _SCRIPTS_DIR.parent / "swe-benchmark-data"
DEFAULT_OUT_DIR = _REPO_ROOT / "docs" / "images"

_GEN_PATH = _SCRIPTS_DIR / "gen_agent_report.py"
_spec = importlib.util.spec_from_file_location("gen_agent_report", _GEN_PATH)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

HARNESSES = ("claude-code", "pi")
HARNESS_LABELS = {"claude-code": "Claude Code", "pi": "pi"}

# Two validated categorical hues for the harnesses (colorblind-checked, both
# modes). Marker SHAPE carries the self-hosted/Bedrock split, so host-vs-buy is
# never color-alone. Text wears ink tokens.
_THEME = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e6e5e2",
        "connector": "#b9b8b4",
        "frontier": "#0b0b0b",
        "claude-code": "#3d7dca",
        "pi": "#eb6834",
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "muted": "#c3c2b7",
        "grid": "#333330",
        "connector": "#55544f",
        "frontier": "#d7d6cf",
        "claude-code": "#4a90d9",
        "pi": "#d95926",
    },
}


def _points(data_dir: Path, skill: str, repo: str) -> dict[str, list[dict[str, Any]]]:
    """Return per-harness point lists: {harness: [{model, cost, score, bedrock}]}.

    cost is per task (run total / scored tasks). Rows without a derivable cost or
    with zero scored tasks are dropped (logged), not plotted at a fake 0.
    """
    out: dict[str, list[dict[str, Any]]] = {}
    for harness in HARNESSES:
        pts: list[dict[str, Any]] = []
        for row in gen._collect(data_dir, harness, skill, repo):
            cost_str, basis = gen._row_cost(row)
            scored = row.get("num_scored") or 0
            if cost_str == "--" or not scored or row.get("mean") is None:
                logger.info(
                    "skipping %s/%s: no cost or no scored tasks", harness, row["model"]
                )
                continue
            pts.append(
                {
                    "model": row["model"],
                    "cost": float(cost_str.lstrip("$")) / scored,
                    "score": float(row["mean"]),
                    "bedrock": basis.startswith("metered"),
                }
            )
        out[harness] = pts
    return out


def _frontier(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return the cheaper-and-better Pareto set, sorted by cost ascending.

    A point is on the frontier if no other point is both cheaper (lower cost)
    and higher-scoring. Ties broken so the frontier is a clean step line.
    """
    ordered = sorted(points, key=lambda p: (p["cost"], -p["score"]))
    frontier: list[dict[str, Any]] = []
    best = float("-inf")
    for p in ordered:
        if p["score"] > best:
            frontier.append(p)
            best = p["score"]
    return frontier


def _plot(
    per_harness: dict[str, list[dict[str, Any]]],
    *,
    skill: str,
    mode: str,
    out_dir: Path,
) -> Path:
    """Render the unified both-harness cost-quality scatter."""
    t = _THEME[mode]
    fig, ax = plt.subplots(figsize=(11, 7.5), facecolor=t["surface"])
    ax.set_facecolor(t["surface"])
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(t["grid"])
    ax.tick_params(colors=t["muted"], labelsize=9)
    ax.grid(True, color=t["grid"], linewidth=0.6)
    ax.set_axisbelow(True)

    all_points = [p for pts in per_harness.values() for p in pts]

    # Connector: join the same model across harnesses (thin, recessive).
    by_model: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for harness, pts in per_harness.items():
        for p in pts:
            by_model.setdefault(p["model"], []).append((harness, p))
    for model, entries in by_model.items():
        if len(entries) == 2:
            (_, a), (_, b) = entries
            ax.plot(
                [a["cost"], b["cost"]],
                [a["score"], b["score"]],
                color=t["connector"],
                linewidth=0.9,
                zorder=1,
            )

    # Pareto frontier over ALL points (both harnesses), dashed step line.
    front = _frontier(all_points)
    if len(front) >= 2:
        ax.plot(
            [p["cost"] for p in front],
            [p["score"] for p in front],
            color=t["frontier"],
            linewidth=1.3,
            linestyle="--",
            zorder=2,
            alpha=0.7,
        )

    # Only the frontier and the Bedrock (hosted-API) points are labelled: the
    # crowded low-cost cluster would collide if every one of the 26 points had a
    # name. The full per-model numbers live in the doc's table below the chart.
    front_ids = {(p["model"], p["cost"], p["score"]) for p in front}
    labelled = [
        p
        for p in all_points
        if (p["model"], p["cost"], p["score"]) in front_ids or p["bedrock"]
    ]

    # Points: color = harness, shape = host/buy (o self-hosted, s Bedrock).
    for harness, pts in per_harness.items():
        for p in pts:
            ax.scatter(
                p["cost"],
                p["score"],
                s=70,
                marker="s" if p["bedrock"] else "o",
                color=t[harness],
                edgecolors=t["surface"],
                linewidths=0.8,
                zorder=4,
            )
    for p in labelled:
        ax.annotate(
            p["model"],
            (p["cost"], p["score"]),
            textcoords="offset points",
            xytext=(6, 4),
            fontsize=7.2,
            color=t["muted"],
        )

    ax.set_xlabel("Cost per task (USD)", fontsize=10, color=t["ink"])
    ax.set_ylabel("Mean task score (0-100)", fontsize=10, color=t["ink"])
    ax.set_title(
        f"Cost vs. quality on {skill} - Claude Code vs pi (both harnesses)",
        fontsize=13,
        color=t["ink"],
        loc="left",
    )

    # Legend: harness color + host/buy shape (two small legends).
    color_handles = [
        plt.Line2D(
            [], [], marker="o", linestyle="", color=t[h], label=HARNESS_LABELS[h]
        )
        for h in HARNESSES
    ]
    shape_handles = [
        plt.Line2D(
            [], [], marker="o", linestyle="", color=t["muted"], label="self-hosted"
        ),
        plt.Line2D([], [], marker="s", linestyle="", color=t["muted"], label="Bedrock"),
    ]
    leg1 = ax.legend(
        handles=color_handles,
        loc="lower right",
        fontsize=8.5,
        frameon=False,
        labelcolor=t["muted"],
        title="harness",
        title_fontsize=8.5,
    )
    leg1.get_title().set_color(t["muted"])
    ax.add_artist(leg1)
    ax.legend(
        handles=shape_handles,
        loc="lower right",
        bbox_to_anchor=(1.0, 0.16),
        fontsize=8.5,
        frameon=False,
        labelcolor=t["muted"],
        title="hosting",
        title_fontsize=8.5,
    )

    fig.text(
        0.01,
        0.005,
        "Connector joins the same model across harnesses. Dashed line = Pareto "
        "frontier (nothing else both cheaper and higher-scoring). Cost bases are "
        "not directly comparable (metered Bedrock vs hardware-derived self-hosted).",
        fontsize=6.8,
        color=t["muted"],
    )
    fig.tight_layout(rect=(0, 0.03, 1, 1))

    suffix = "-dark" if mode == "dark" else ""
    out = out_dir / f"cost-quality-harness-{skill}{suffix}.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=t["surface"])
    plt.close(fig)
    logger.info("wrote %s (%d points)", out, len(all_points))
    return out


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Unified cost-vs-quality Pareto scatter across both harnesses.",
        epilog="Example: uv run scripts/plot_cost_quality_harness.py --skill swe3",
    )
    parser.add_argument(
        "--skill", default="swe3", help="SWE skill: 'swe3' (default) or 'swe2'."
    )
    parser.add_argument("--repo", default="mcp-gateway-registry", help="Dataset scope.")
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--dark", action="store_true", help="Render the dark-theme variant."
    )
    return parser.parse_args()


def main() -> None:
    """Collect both harnesses' points and render the unified scatter."""
    args = _parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    per_harness = _points(data_dir, args.skill, args.repo)
    if not any(per_harness.values()):
        raise SystemExit(f"no costable points for skill={args.skill}")
    _plot(
        per_harness,
        skill=args.skill,
        mode="dark" if args.dark else "light",
        out_dir=args.out_dir.expanduser().resolve(),
    )


if __name__ == "__main__":
    main()
