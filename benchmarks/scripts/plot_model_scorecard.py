#!/usr/bin/env python3
"""Four-panel per-model scorecard for one (harness, skill): tokens, cost,
accuracy, latency -- side by side, sharing the model axis.

Each metric is a different scale, so they get their own panel rather than a
shared/dual axis (the #1 charting mistake). The four panels are a small-multiple
facet keyed on the model (y) axis; rows are sorted by accuracy (best at top) so
the quality ranking reads down the left labels and you scan across to see what
each model cost, how many tokens it burned, and how long it took.

Bars are a single recessive neutral (magnitude; the model name carries identity).
The cost panel alone is tinted by basis -- metered (Bedrock) vs hardware-derived
(self-hosted) -- because those dollars are NOT comparable as raw numbers; the two
hues pass the dataviz colorblind validator in light and dark, and every bar is
value-labelled with a legend so the split never rests on color alone.

Numbers are sourced from gen_agent_report (_collect + _row_cost), so this chart,
the harness doc's table, and the cost-quality chart always agree.

Usage:
    uv run scripts/plot_model_scorecard.py --harness pi --skill swe3
    uv run scripts/plot_model_scorecard.py --harness claude-code --skill swe2 --dark

Output: docs/images/scorecard-<code>-<skill>{,-dark}.png
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

# Reuse the doc generator's collectors + cost logic so numbers match the doc
# exactly (import by path: the filename has a dash).
_GEN_PATH = _SCRIPTS_DIR / "gen_agent_report.py"
_spec = importlib.util.spec_from_file_location("gen_agent_report", _GEN_PATH)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)

HARNESS_CODES = {"claude-code": "cc", "pi": "pi", "opencode": "oc", "kiro-cli": "kiro"}
HARNESS_LABELS = {"claude-code": "Claude Code", "pi": "pi"}

# Palette from the dataviz skill's validated reference instance (shared with the
# other plot scripts). Bars are a recessive neutral; two accents distinguish the
# (non-comparable) cost bases. Text always wears ink tokens.
_THEME = {
    "light": {
        "surface": "#fcfcfb",
        "ink": "#0b0b0b",
        "muted": "#52514e",
        "grid": "#e6e5e2",
        "bar": "#33322f",
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
    """Return per-model rows (model, tokens, cost, basis, score, minutes).

    Reuses gen_agent_report._collect (the run-summaries the doc reads) and
    _row_cost (the doc's cost). A model with no derivable cost or zero tokens is
    dropped with a logged note rather than plotted at a fake 0. Rows are sorted by
    accuracy (mean score) descending; a None score (0 scored) sorts last.
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
                "score": row.get("mean"),
                "minutes": (row.get("latency_seconds") or 0) / 60.0,
            }
        )
    rows.sort(key=lambda r: (r["score"] is None, -(r["score"] or 0.0)))
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
            fontsize=7.5,
            color=color,
        )


def _panel(
    ax: "plt.Axes",
    values: list[float],
    labels: list[str],
    *,
    title: str,
    colors: Any,
    t: dict[str, str],
    xfmt: Any,
) -> None:
    """Draw one horizontal-bar metric panel with value labels."""
    y = range(len(values))
    bars = ax.barh(list(y), values, color=colors, height=0.62, zorder=3)
    _bar_labels(ax, bars, labels, t["muted"])
    ax.set_title(title, fontsize=9.5, color=t["ink"], loc="left")
    ax.xaxis.set_major_formatter(FuncFormatter(xfmt))
    hi = max(values) if values else 1
    ax.set_xlim(right=hi * 1.22 if hi else 1)


def _plot(
    rows: list[dict[str, Any]],
    *,
    harness: str,
    skill: str,
    mode: str,
    out_dir: Path,
) -> Path:
    """Render the four-panel (tokens | cost | accuracy | latency) facet."""
    t = _THEME[mode]
    label = HARNESS_LABELS.get(harness, harness)
    models = [r["model"] for r in rows]
    height = max(2.8, 0.42 * len(models) + 1.6)
    fig, axes = plt.subplots(
        1, 4, figsize=(16, height), sharey=True, facecolor=t["surface"]
    )
    ax_tok, ax_cost, ax_acc, ax_lat = axes

    for ax in axes:
        ax.set_facecolor(t["surface"])
        for spine in ("top", "right", "left"):
            ax.spines[spine].set_visible(False)
        ax.spines["bottom"].set_color(t["grid"])
        ax.tick_params(colors=t["muted"], labelsize=7.5, length=0)
        ax.xaxis.grid(True, color=t["grid"], linewidth=0.6)
        ax.set_axisbelow(True)

    # Model labels on the shared axis (leftmost panel), best score at top.
    ax_tok.set_yticks(range(len(models)))
    ax_tok.set_yticklabels(models, fontsize=8, color=t["ink"])
    ax_tok.invert_yaxis()

    # Panel 1: total tokens processed.
    tok = [r["total_tokens"] for r in rows]
    _panel(
        ax_tok,
        tok,
        [_human_tokens(v) for v in tok],
        title="Total tokens processed",
        colors=t["bar"],
        t=t,
        xfmt=_human_tokens,
    )

    # Panel 2: run cost, tinted by basis.
    cost = [r["cost"] for r in rows]
    cost_colors = [t["metered"] if r["metered"] else t["hardware"] for r in rows]
    _panel(
        ax_cost,
        cost,
        [f"${c:,.2f}" for c in cost],
        title="Run cost, 5 tasks",
        colors=cost_colors,
        t=t,
        xfmt=lambda v, _p: f"${v:,.0f}",
    )

    # Panel 3: accuracy (mean task score, 0-100).
    acc = [r["score"] or 0.0 for r in rows]
    _panel(
        ax_acc,
        acc,
        [f"{v:.1f}" for v in acc],
        title="Mean score (0-100)",
        colors=t["bar"],
        t=t,
        xfmt=lambda v, _p: f"{v:.0f}",
    )
    ax_acc.set_xlim(right=max(100.0, max(acc) * 1.12) if acc else 100)

    # Panel 4: latency (total wall-clock minutes over the 5 tasks).
    mins = [r["minutes"] for r in rows]
    _panel(
        ax_lat,
        mins,
        [f"{v:.0f}m" for v in mins],
        title="Wall-clock (min, 5 tasks)",
        colors=t["bar"],
        t=t,
        xfmt=lambda v, _p: f"{v:.0f}m",
    )

    # Legend for the cost-basis hues (only the cost panel is colored).
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=t["metered"]),
        plt.Rectangle((0, 0), 1, 1, color=t["hardware"]),
    ]
    ax_cost.legend(
        handles,
        ["metered (Bedrock)", "hardware-derived (self-hosted)"],
        loc="lower right",
        fontsize=7,
        frameon=False,
        labelcolor=t["muted"],
    )

    fig.suptitle(
        f"{label} - {skill}: per-model scorecard (sorted by score)",
        fontsize=12.5,
        color=t["ink"],
        x=0.02,
        ha="left",
    )
    fig.text(
        0.02,
        0.005,
        "Cost bases are NOT directly comparable: metered = real Bedrock bill; "
        "hardware-derived = blended $/token (throughput sweep, real instance) x "
        "tokens processed. Latency is total wall-clock over 5 tasks.",
        fontsize=6.8,
        color=t["muted"],
    )
    fig.tight_layout(rect=(0, 0.03, 1, 0.955))

    code = HARNESS_CODES.get(harness, harness)
    suffix = "-dark" if mode == "dark" else ""
    out = out_dir / f"scorecard-{code}-{skill}{suffix}.png"
    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, dpi=150, facecolor=t["surface"])
    plt.close(fig)
    logger.info("wrote %s (%d models)", out, len(rows))
    return out


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Four-panel per-model scorecard (tokens, cost, accuracy, latency).",
        epilog="Example: uv run scripts/plot_model_scorecard.py --harness pi --skill swe3",
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
    """Collect per-model metrics and render the four-panel scorecard."""
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
