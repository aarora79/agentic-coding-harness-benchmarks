#!/usr/bin/env python3
"""Faceted tokens + cost bar chart for one (harness, skill), per model.

Two measures of different scale -- total tokens processed and run cost -- must
NOT share one axis (the #1 charting mistake). So this renders them as two
horizontal-bar panels side by side that SHARE the model (y) axis: a small-multiple
facet. Models are sorted by cost (descending) so the most expensive read at top.

Bars are a single recessive neutral (magnitude, not identity -- the model name on
the axis carries identity). The cost bar is tinted by its basis (metered Bedrock
vs hardware-derived self-hosted) because those dollars are NOT comparable as raw
numbers; the two hues are from the validated palette and every bar is also
value-labelled, so the distinction never rests on color alone.

Cost is sourced from gen_agent_report (blended $/token x total processed tokens
for self-hosted at the model's real instance; metered bill for Bedrock), so this
chart and the harness doc's cost column always agree.

Usage:
    uv run scripts/plot_tokens_cost.py --harness pi --skill swe3
    uv run scripts/plot_tokens_cost.py --harness claude-code --skill swe2 --dark

Output: docs/images/tokens-cost-<code>-<skill>{,-dark}.png
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
from matplotlib.ticker import FuncFormatter  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
DEFAULT_DATA_DIR = _SCRIPTS_DIR.parent / "swe-benchmark-data"
DEFAULT_OUT_DIR = _REPO_ROOT / "docs" / "images"

# Reuse the doc generator's collectors and cost logic so this chart's numbers are
# identical to the harness doc's table (import by path: the filename has a dash).
_GEN_PATH = _SCRIPTS_DIR / "gen_agent_report.py"
_spec = importlib.util.spec_from_file_location("gen_agent_report", _GEN_PATH)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

HARNESS_CODES = {"claude-code": "cc", "pi": "pi", "opencode": "oc", "kiro-cli": "kiro"}
HARNESS_LABELS = {"claude-code": "Claude Code", "pi": "pi"}

# Palette from the dataviz skill's validated reference instance (shared with the
# other plot scripts). Bars are a recessive neutral; the two accents distinguish
# the (non-comparable) cost bases. Text always wears ink tokens.
_THEME = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e6e5e2",
        "bar": "#33322f",  # tokens bar + neutral
        "metered": "#eb6834",  # Bedrock (warm accent)
        "hardware": "#3d7dca",  # self-hosted (validated cool accent)
    },
    "dark": {
        "surface": "#1a1a19",
        "ink": "#ffffff",
        "muted": "#c3c2b7",
        "grid": "#333330",
        "bar": "#d7d6cf",
        "metered": "#d95926",
        "hardware": "#4a90d9",
    },
}


def _human_tokens(value: float, _pos: int = 0) -> str:
    """Format a token count as a compact human string (e.g. 82.7M, 1.2B)."""
    if value >= 1e9:
        return f"{value / 1e9:.1f}B"
    if value >= 1e6:
        return f"{value / 1e6:.0f}M"
    if value >= 1e3:
        return f"{value / 1e3:.0f}K"
    return f"{value:.0f}"


def _collect_rows(
    data_dir: Path, harness: str, skill: str, repo: str
) -> list[dict[str, Any]]:
    """Return per-model rows (model, total_tokens, cost, basis), sorted by cost.

    Reuses gen_agent_report._collect (same run-summaries the doc reads) and
    _row_cost (same blended/metered cost the doc's column shows). A model whose
    cost cannot be derived (no throughput summary, no metered bill) is dropped
    from the chart with a logged note rather than plotted at a fake 0.
    """
    rows: list[dict[str, Any]] = []
    for row in gen._collect(data_dir, harness, skill, repo):
        cost_str, basis = gen._row_cost(row)
        total = row.get("total_tokens") or 0
        if cost_str == "--" or not total:
            logger.info("skipping %s: no derivable cost or zero tokens", row["model"])
            continue
        rows.append(
            {
                "model": row["model"],
                "total_tokens": total,
                "cost": float(cost_str.lstrip("$")),
                "metered": basis.startswith("metered"),
            }
        )
    rows.sort(key=lambda r: r["cost"], reverse=True)
    return rows


def _bar_labels(ax: "plt.Axes", bars: Any, texts: list[str], color: str) -> None:
    """Write a value label just past the end of each horizontal bar."""
    for bar, text in zip(bars, texts):
        ax.text(
            bar.get_width(),
            bar.get_y() + bar.get_height() / 2,
            f"  {text}",
            va="center",
            ha="left",
            fontsize=8,
            color=color,
        )


def _plot(
    rows: list[dict[str, Any]],
    *,
    harness: str,
    skill: str,
    mode: str,
    out_dir: Path,
) -> Path:
    """Render the two-panel (tokens | cost) facet and save it."""
    t = _THEME[mode]
    label = HARNESS_LABELS.get(harness, harness)
    models = [r["model"] for r in rows]
    y = range(len(models))
    # Taller figure when more models; two panels share the y axis.
    height = max(2.6, 0.42 * len(models) + 1.4)
    fig, (ax_tok, ax_cost) = plt.subplots(
        1, 2, figsize=(11, height), sharey=True, facecolor=t["surface"]
    )

    for ax in (ax_tok, ax_cost):
        ax.set_facecolor(t["surface"])
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(t["grid"])
        ax.tick_params(colors=t["muted"], labelsize=8, length=0)
        ax.xaxis.grid(True, color=t["grid"], linewidth=0.6)
        ax.set_axisbelow(True)

    # Panel 1: total tokens processed (single neutral hue -- magnitude).
    tok = [r["total_tokens"] for r in rows]
    bars_tok = ax_tok.barh(list(y), tok, color=t["bar"], height=0.62, zorder=3)
    _bar_labels(ax_tok, bars_tok, [_human_tokens(v) for v in tok], t["muted"])
    ax_tok.set_yticks(list(y))
    ax_tok.set_yticklabels(models, fontsize=8, color=t["ink"])
    ax_tok.invert_yaxis()  # highest-cost model on top
    ax_tok.xaxis.set_major_formatter(FuncFormatter(_human_tokens))
    ax_tok.set_title("Total tokens processed", fontsize=10, color=t["ink"], loc="left")
    ax_tok.set_xlim(right=max(tok) * 1.18)

    # Panel 2: run cost, tinted by basis (metered vs hardware-derived).
    cost = [r["cost"] for r in rows]
    colors = [t["metered"] if r["metered"] else t["hardware"] for r in rows]
    bars_cost = ax_cost.barh(list(y), cost, color=colors, height=0.62, zorder=3)
    _bar_labels(ax_cost, bars_cost, [f"${c:,.2f}" for c in cost], t["muted"])
    ax_cost.xaxis.set_major_formatter(FuncFormatter(lambda v, _p: f"${v:,.0f}"))
    ax_cost.set_title("Run cost (5 tasks)", fontsize=10, color=t["ink"], loc="left")
    ax_cost.set_xlim(right=max(cost) * 1.20)

    # Legend for the two cost bases (identity is never color-alone: bars are also
    # value-labelled and the models are named on the axis).
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=t["metered"]),
        plt.Rectangle((0, 0), 1, 1, color=t["hardware"]),
    ]
    ax_cost.legend(
        handles,
        ["metered (Bedrock)", "hardware-derived (self-hosted)"],
        loc="lower right",
        fontsize=7.5,
        frameon=False,
        labelcolor=t["muted"],
    )

    fig.suptitle(
        f"{label} - {skill}: tokens processed and cost per model",
        fontsize=12,
        color=t["ink"],
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        0.005,
        "Cost bases are NOT directly comparable: metered = real Bedrock bill; "
        "hardware-derived = blended $/token (throughput sweep, real instance) x "
        "tokens processed.",
        fontsize=6.8,
        color=t["muted"],
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.96))

    code = HARNESS_CODES.get(harness, harness)
    suffix = "-dark" if mode == "dark" else ""
    out = out_dir / f"tokens-cost-{code}-{skill}{suffix}.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=t["surface"])
    plt.close(fig)
    logger.info("wrote %s (%d models)", out, len(rows))
    return out


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Faceted tokens + cost bar chart per model for a (harness, skill).",
        epilog="Example: uv run scripts/plot_tokens_cost.py --harness pi --skill swe3",
    )
    parser.add_argument(
        "--harness", default="claude-code", help="Harness slug (default: claude-code)."
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
    """Collect per-model tokens + cost and render the faceted bar chart."""
    args = _parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    rows = _collect_rows(data_dir, args.harness, args.skill, args.repo)
    if not rows:
        raise SystemExit(
            f"no costable models under "
            f"{data_dir}/*/{args.harness}/{args.skill}/{args.repo}"
        )
    _plot(
        rows,
        harness=args.harness,
        skill=args.skill,
        mode="dark" if args.dark else "light",
        out_dir=args.out_dir.expanduser().resolve(),
    )


if __name__ == "__main__":
    main()
