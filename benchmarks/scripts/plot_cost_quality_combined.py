#!/usr/bin/env python3
"""Render ONE cost-vs-quality chart across harnesses, keeping each model's best.

The per-harness charts (``plot_cost_quality.py``) answer "which model should I
pick if I have already chosen a harness". This one answers the buyer's actual
question: "across everything measured, what is the best I can do per dollar, and
which harness gets me there". It plots Claude Code and pi together, one frontier
over the union, and labels every point with the harness that produced it.

Each model contributes exactly ONE point -- its best harness -- chosen in two
steps, because "best" is only partly well-defined:

1. **Pareto dominance.** If one harness run is no worse on both axes and better
   on at least one (>= score AND <= cost), it wins outright. This settles 7 of
   the 12 models measured under both harnesses.
2. **Cost per point, as the tie-break.** For the rest, neither run dominates --
   one is cheaper, the other scores higher -- so the winner is the one with the
   lower cost/point (cost per task / mean score), the value-efficiency ratio the
   comparison docs already report. Ranking by score alone would systematically
   plot the pricier harness (claude-sonnet-5 would land at $24.64 instead of
   $3.81 for 1.5 more points); ranking by cost alone would plot the weaker one.

Nothing is hidden by that choice: the emitted JSON records the runner-up and the
verdict for every model, so a reader can see exactly what was set aside and why.

Numbers come from the same ``_collect_points`` the per-harness charts use, so
this chart can never disagree with them; nothing is re-derived here. Every point
carries the model name, with the winning harness encoded as the marker shape
and named in the legend.

Cost bases are NOT comparable as raw dollars across hosting (a metered Bedrock
bill vs a hardware-derived self-hosted figure), so -- exactly as the per-harness
charts do -- the emitted JSON carries a per-hosting frontier alongside the
combined, cross-hosting one, and the combined view is directional only. See
docs/cost-per-task-methodology.md.

Cost is linear, matching the per-harness charts. ``--log-x`` switches to a log
axis, which spreads the sub-$1 models out of the left margin at the price of an
axis that no longer reads directly against the other charts.

Usage:
    uv run scripts/plot_cost_quality_combined.py
    uv run scripts/plot_cost_quality_combined.py --dark
    uv run scripts/plot_cost_quality_combined.py --harnesses claude-code,pi,kiro-cli
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # headless: render to file, never a display
from matplotlib.lines import Line2D  # noqa: E402

import plot_cost_quality as cq  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Filename code for the merged view, slotting into the same
# cost-quality-<code>-<skill>.png convention as the per-harness charts.
COMBINED_CODE = "combined"
DEFAULT_HARNESSES = ("claude-code", "pi")
# Harness names as they read in the legend.
HARNESS_DISPLAY = {
    "claude-code": "Claude Code",
    "pi": "Pi",
    "kiro-cli": "Kiro CLI",
    "opencode": "opencode",
}
# Marker per harness. The harness is encoded as a shape rather than spelled out
# in every label, which keeps the labels short enough to sit beside their dots.
HARNESS_MARKERS = {"claude-code": "s", "pi": "o", "kiro-cli": "^", "opencode": "D"}
FALLBACK_MARKER = "o"
# Colour per harness, doubling the shape encoding so the split is legible at a
# glance and still survives colour-blindness and greyscale printing.
#
# The frontier line owns the warm accent, and every warm hue fails the
# separation floors against it (orange vs red is dE 7.1 to normal vision, vs
# yellow 13.7 -- both under the 15 floor), so a second warm hue is not
# available. One harness therefore takes violet, the palette slot furthest from
# the accent (dE 37.6 light / 27.0 dark, and clear on all three CVD axes), and
# the other keeps the chart's own warm charcoal. That adds exactly one hue to
# the scheme rather than importing a cool pair that fights it, and the two are
# separated by lightness as well as hue, with the marker shape behind both.
HARNESS_COLORS = {
    "light": {"claude-code": "#4a3aa7", "pi": "#33322f"},
    "dark": {"claude-code": "#9085e9", "pi": "#d7d6cf"},
}
# Vendor prefix dropped from chart labels only. Each label here already carries
# a harness, so the model half has to earn its width, and "opus-5" is no less
# clear than "claude-opus-5". Every emitted JSON still reports the full slug.
LABEL_PREFIX_TO_DROP = "claude-"


def _default_output(skill: str, dark: bool) -> Path:
    """Committed docs/images path for the combined chart."""
    suffix = "-dark" if dark else ""
    return cq.DEFAULT_IMAGES_DIR / f"cost-quality-{COMBINED_CODE}-{skill}{suffix}.png"


def _chart_label(point: cq.ModelPoint) -> str:
    """Build the short label drawn next to a point.

    The model slug loses its vendor prefix (claude-opus-5 -> opus-5) so the
    label sits beside its dot; ``point.model`` itself is untouched, so the
    frontier JSON keeps the real slug. The harness is not spelled out here --
    the marker shape and its legend key carry it.

    Args:
        point: The winning model+harness aggregate.

    Returns:
        The label text, e.g. "opus-5".
    """
    model = point.model
    if model.startswith(LABEL_PREFIX_TO_DROP):
        return model[len(LABEL_PREFIX_TO_DROP) :]
    return model


def _marker_for(point: cq.ModelPoint) -> str:
    """Marker shape encoding the harness that won this model."""
    return HARNESS_MARKERS.get(point.harness, FALLBACK_MARKER)


def _color_for(point: cq.ModelPoint, mode: str) -> str:
    """Marker colour encoding the harness that won this model.

    Args:
        point: The winning model+harness aggregate.
        mode: "light" or "dark".

    Returns:
        The hex colour for that harness, falling back to the theme's recessive
        neutral for a harness with no assigned slot.
    """
    return HARNESS_COLORS[mode].get(point.harness, cq._THEME[mode]["dot"])


def _legend_handles(harnesses: list[str], mode: str) -> list[Line2D]:
    """Build the marker key naming which shape and colour is which harness."""
    theme = cq._THEME[mode]
    return [
        Line2D(
            [],
            [],
            linestyle="none",
            marker=HARNESS_MARKERS.get(harness, FALLBACK_MARKER),
            markersize=9,
            markerfacecolor=HARNESS_COLORS[mode].get(harness, theme["dot"]),
            markeredgecolor=theme["surface"],
            label=HARNESS_DISPLAY.get(harness, harness),
        )
        for harness in harnesses
    ]


def _dominates(a: cq.ModelPoint, b: cq.ModelPoint) -> bool:
    """True when ``a`` is at least as good as ``b`` on both axes, better on one.

    The same rule ``plot_cost_quality._pareto_frontier`` applies, kept here as a
    named predicate because per-model harness selection needs it pairwise.

    Args:
        a: The candidate dominator.
        b: The point that may be dominated.

    Returns:
        Whether ``a`` dominates ``b``.
    """
    no_worse = a.mean_cost <= b.mean_cost and a.mean_score >= b.mean_score
    strictly_better = a.mean_cost < b.mean_cost or a.mean_score > b.mean_score
    return no_worse and strictly_better


def _collect_across_harnesses(
    data_dir: Path,
    repo: str,
    skill: str,
    harnesses: list[str],
) -> list[cq.ModelPoint]:
    """Collect every model point for every harness, tagged with its harness.

    Delegates to ``plot_cost_quality._collect_points`` per harness so the merged
    chart reads the identical aggregates (and identical failed-task exclusions)
    as the per-harness charts.

    Args:
        data_dir: The ``swe-benchmark-data`` root.
        repo: Dataset repo subfolder (e.g. mcp-gateway-registry).
        skill: SWE skill folder (swe2 or swe3).
        harnesses: Coding-agent folders to merge.

    Returns:
        Every (model, harness) aggregate found.

    Raises:
        SystemExit: If no harness yielded a scorable run.
    """
    points: list[cq.ModelPoint] = []
    for harness in harnesses:
        try:
            found = cq._collect_points(data_dir, repo, harness, skill)
        except SystemExit:
            # One empty harness is not fatal here: the chart's job is to merge
            # whatever HAS been measured. Say so rather than failing the run.
            logger.warning(
                "no scorable %s runs for repo '%s' skill '%s' -- skipping that harness",
                harness,
                repo,
                skill,
            )
            continue
        for point in found:
            point.harness = harness
        logger.info("  %s: %d models", harness, len(found))
        points.extend(found)
    if not points:
        raise SystemExit(
            f"no scorable runs found under {data_dir} for repo '{repo}' skill "
            f"'{skill}' under any of: {', '.join(harnesses)}."
        )
    return points


def _cost_per_point(point: cq.ModelPoint) -> float:
    """Cost per quality point -- the tie-break between non-dominated runs.

    The same value-efficiency lens as the ``Cost/point`` column in the
    comparison docs: dollars per mean score point, lower being better. A
    non-positive score cannot be divided into, so it sorts last.

    Args:
        point: One model+harness aggregate.

    Returns:
        Cost per task divided by mean score, or infinity when unscoreable.
    """
    if point.mean_score <= 0:
        return float("inf")
    return point.mean_cost / point.mean_score


def _select_best_harness(
    points: list[cq.ModelPoint],
) -> tuple[list[cq.ModelPoint], list[dict]]:
    """Reduce each model to its single best harness run; report the reasoning.

    Dominance decides where it can (a run no worse on both axes and better on
    one). Where it cannot -- one harness cheaper, the other higher-scoring --
    the lower cost/point wins, so the chart never plots a run that costs several
    times more for a point or two of score. Ties beyond that fall back to the
    order the harnesses were given, keeping the output deterministic.

    Args:
        points: Every (model, harness) aggregate.

    Returns:
        One winning point per model (highest score first), and one selection
        record per model naming the winner, the runner-up, and the verdict.
    """
    by_model: dict[str, list[cq.ModelPoint]] = {}
    for point in points:
        by_model.setdefault(point.model, []).append(point)

    winners: list[cq.ModelPoint] = []
    records: list[dict] = []
    for model, runs in sorted(by_model.items()):
        undominated = [
            run
            for run in runs
            if not any(o is not run and _dominates(o, run) for o in runs)
        ]
        # Dominance settled it when it left exactly one run standing; otherwise
        # the cost/point tie-break picks among the survivors.
        by_dominance = len(undominated) == 1
        winner = min(undominated, key=_cost_per_point)
        winner.label = _chart_label(winner)
        winners.append(winner)
        records.append(_selection_record(model, runs, winner, by_dominance))
    return sorted(winners, key=lambda p: p.mean_score, reverse=True), records


def _selection_record(
    model: str,
    runs: list[cq.ModelPoint],
    winner: cq.ModelPoint,
    by_dominance: bool,
) -> dict:
    """Describe one model's harness selection for the machine-readable JSON.

    Args:
        model: The model slug.
        runs: Every harness run measured for it.
        winner: The run that will be plotted.
        by_dominance: Whether dominance alone decided it (vs the tie-break).

    Returns:
        The winner, the runs set aside, and a plain-language verdict.
    """
    if len(runs) == 1:
        verdict = f"single-harness: only {winner.harness} measured"
    elif by_dominance:
        verdict = f"{winner.harness} dominates (>= score and <= cost)"
    else:
        verdict = (
            f"no harness dominates; {winner.harness} wins on cost/point "
            f"(${_cost_per_point(winner):.4f} per point)"
        )
    return {
        "model": model,
        "verdict": verdict,
        "decided_by": "dominance"
        if by_dominance or len(runs) == 1
        else "cost_per_point",
        "winner": cq._point_dict(winner)
        | {"cost_per_point": round(_cost_per_point(winner), 4)},
        "runners_up": [
            cq._point_dict(r) | {"cost_per_point": round(_cost_per_point(r), 4)}
            for r in runs
            if r is not winner
        ],
    }


def _write_frontier_json(
    points: list[cq.ModelPoint],
    records: list[dict],
    *,
    harnesses: list[str],
    skill: str,
    repo: str,
    out_dir: Path,
) -> Path:
    """Emit the combined frontier plus the harness-selection rationale as JSON.

    Reuses ``plot_cost_quality._pareto_frontier`` -- the same function that draws
    the line -- so the file and the chart can never diverge.
    """
    bedrock = [p for p in points if p.hosting == "Bedrock"]
    selfh = [p for p in points if p.hosting != "Bedrock"]
    payload = {
        "note": (
            "Combined cost/quality frontier across harnesses, behind "
            f"docs/images/cost-quality-{COMBINED_CODE}-{skill}.png. Emitted by "
            "plot_cost_quality_combined.py. Each model contributes ONE point -- "
            "its best harness; see harness_selection for the winner, the "
            "runners-up, and how each was decided. Use the per-hosting "
            "frontiers for cost claims -- the "
            "combined frontier mixes a metered Bedrock bill with a "
            "hardware-derived self-hosted figure and is directional only (see "
            "cost-per-task-methodology.md)."
        ),
        "harnesses": harnesses,
        "skill": skill,
        "repo": repo,
        "frontier_rule": "non-dominated on (max score, min cost/task)",
        "harness_selection_rule": (
            "one point per model: the harness run that dominates (>= score and "
            "<= cost); when neither dominates, the lower cost/point wins"
        ),
        "harness_selection": records,
        "combined_frontier_cross_hosting_directional": [
            cq._point_dict(p) for p in cq._pareto_frontier(points)
        ],
        "bedrock_frontier": [cq._point_dict(p) for p in cq._pareto_frontier(bedrock)],
        "self_hosted_frontier": [cq._point_dict(p) for p in cq._pareto_frontier(selfh)],
        "all_points": [
            cq._point_dict(p) for p in sorted(points, key=lambda p: -p.mean_score)
        ],
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"pareto-frontier-{COMBINED_CODE}-{skill}.json"
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    logger.info("wrote %s", out_path)
    return out_path


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Plot ONE cost-vs-quality scatter merging every harness, "
        "keeping each model's non-dominated harness run(s).",
        epilog="Example:\n"
        "  uv run scripts/plot_cost_quality_combined.py\n"
        "  uv run scripts/plot_cost_quality_combined.py --dark\n"
        "  uv run scripts/plot_cost_quality_combined.py --harnesses claude-code,pi",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=cq.DEFAULT_DATA_DIR,
        help=f"swe-benchmark-data root (default: {cq.DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--repo",
        default="mcp-gateway-registry",
        help="Dataset repo subfolder to aggregate (default: mcp-gateway-registry)",
    )
    parser.add_argument(
        "--harnesses",
        default=",".join(DEFAULT_HARNESSES),
        help="Comma-separated coding-agent folders to merge "
        f"(default: {','.join(DEFAULT_HARNESSES)}). A harness with no scorable "
        "run is skipped with a warning.",
    )
    parser.add_argument(
        "--skill",
        default="swe3",
        help="SWE skill folder to read: 'swe3' (default) or 'swe2'.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"Output image path (default: docs/images/cost-quality-{COMBINED_CODE}"
        "-<skill>.png; -dark suffix in dark mode)",
    )
    parser.add_argument(
        "--dark", action="store_true", help="Render the dark-mode theme"
    )
    parser.add_argument(
        "--log-x",
        action="store_true",
        help="Draw cost on a log axis. Cost spans nearly two orders of "
        "magnitude, so a log scale spreads the sub-$1 models out of the left "
        "margin; the linear default keeps the axis directly comparable with "
        "the per-harness charts.",
    )
    parser.add_argument(
        "--metrics-dir",
        type=Path,
        default=cq.DEFAULT_METRICS_DIR,
        help="Where to write the frontier JSON (default: docs/metrics/).",
    )
    parser.add_argument(
        "--fill-color",
        default=None,
        help="Colour of the tint under the frontier (default: the accent, so "
        "the shaded region reads as part of the frontier line that caps it).",
    )
    parser.add_argument("--title", default=None, help="Override the chart title")
    parser.add_argument(
        "--cost-label",
        default=None,
        help="X-axis label; make cost provenance explicit.",
    )
    return parser.parse_args()


def main() -> None:
    """Merge the harnesses and render the combined cost-quality chart."""
    args = _parse_args()
    data_dir = args.data_dir.expanduser().resolve()
    if not data_dir.is_dir():
        raise SystemExit(f"data dir not found: {data_dir}")

    harnesses = [h.strip() for h in args.harnesses.split(",") if h.strip()]
    if not harnesses:
        raise SystemExit("--harnesses must name at least one coding-agent folder")

    mode = "dark" if args.dark else "light"
    output = args.out or _default_output(args.skill, args.dark)
    labels = " + ".join(cq.HARNESS_LABELS.get(h, h) for h in harnesses)
    title = args.title or (
        f"Cost vs. quality -- best harness per model ({labels}), /{args.skill}"
    )
    cost_label = args.cost_label or (
        "Mean cost per task ($) -- self-hosted hardware-derived; "
        "Anthropic metered (see notes)"
    )

    all_points = _collect_across_harnesses(data_dir, args.repo, args.skill, harnesses)
    points, records = _select_best_harness(all_points)
    for record in records:
        logger.info("  %-24s %s", record["model"], record["verdict"])
    frontier = cq._pareto_frontier(points)

    # Emit the machine-readable frontier once (light run), theme-independent.
    if not args.dark:
        _write_frontier_json(
            points,
            records,
            harnesses=harnesses,
            skill=args.skill,
            repo=args.repo,
            out_dir=args.metrics_dir.expanduser().resolve(),
        )
    cq._plot(
        points,
        frontier,
        mode=mode,
        title=title,
        cost_label=cost_label,
        output=output,
        frontier_label=f"Cost/quality frontier ({args.repo})",
        # A linear cost axis packs the cheap models together, so a displaced
        # label needs a thin line back to its own dot to stay attributable.
        leader_lines=not args.log_x,
        label_weight="normal",
        marker_for=_marker_for,
        color_for=lambda point: _color_for(point, mode),
        fill_color=args.fill_color,
        extra_legend=_legend_handles(harnesses, mode),
        label_backing=False,
        log_x=args.log_x,
        avoid_markers=True,
        vertical_leaders=True,
    )


if __name__ == "__main__":
    main()
