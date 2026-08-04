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
METRICS_FILENAME = "metrics.json"

# Short per-harness code used (with the skill) to suffix chart filenames so each
# agent+skill's chart is self-identifying and never overwrites another's
# (cost-quality-cc-swe2.png, cost-quality-pi-swe3.png). An unknown harness falls
# back to its own slug.
HARNESS_CODES = {"claude-code": "cc", "pi": "pi", "opencode": "oc", "kiro-cli": "kiro"}


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

    return ModelPoint(
        model=model,
        mean_cost=cost,
        mean_score=float(score),
        n_tasks=int(summary.get("num_tasks") or 0),
        n_scored=int(summary.get("num_scored") or 0),
        excluded=list(excluded),
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
        tokens = (task.get("input_tokens") or 0) + (task.get("output_tokens") or 0)
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


def _label(point: ModelPoint) -> str:
    """Build a point label; mark models whose mean excludes a failed task."""
    if point.excluded:
        return f"{point.model}*"
    return point.model


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


def _label_offsets(ax, fig, points: list[ModelPoint]) -> dict[int, float]:
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

    Returns:
        ``{id(point): dy_in_points}`` -- 0.0 for labels that did not move.
    """
    to_px = ax.transData.transform
    line_px = 9 * 1.35 * fig.dpi / 72.0  # one label's height in pixels
    # Two labels collide when they share a horizontal band (near in x) AND sit
    # within ~1.6 line-heights in y. The x band is generous (a label is wide), so
    # a whole diagonal run of nearby dots merges into one cluster rather than
    # fragmenting into pairs that would still overlap each other.
    x_band_px = 12 + 9 * 0.6 * 16  # 12px gap + ~16 chars at ~0.6em, fontsize 9
    y_touch_px = line_px * 1.6
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
        spread_px = _spread(ys_px, line_px * 1.35)
        for p, new_y in zip(members, spread_px):
            # display-y grows downward in some backends; transData is bottom-up,
            # so a higher pixel value = higher on screen. Convert delta to points.
            offsets[id(p)] = (new_y - px[id(p)][1]) * 72.0 / fig.dpi
    return offsets


def _plot(
    points: list[ModelPoint],
    frontier: list[ModelPoint],
    *,
    mode: str,
    title: str,
    cost_label: str,
    output: Path,
) -> None:
    """Render the scatter with its frontier and save to ``output``.

    Args:
        points: All model aggregates.
        frontier: The non-dominated subset (ascending cost).
        mode: "light" or "dark" theme.
        title: Chart title.
        cost_label: X-axis label (cost provenance is caller's responsibility).
        output: Destination image path.
    """
    theme = _THEME[mode]
    fig, ax = plt.subplots(figsize=(11, 7), dpi=150)
    fig.patch.set_facecolor(theme["surface"])
    ax.set_facecolor(theme["surface"])

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
            label="Cost/quality frontier",
        )
        ax.fill_between(
            fx,
            fy,
            min(p.mean_score for p in points) - 5,
            color=theme["accent"],
            alpha=0.06,
            zorder=1,
        )

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
            color=theme["accent"] if on_frontier else theme["dot"],
            edgecolors=theme["surface"],
            linewidths=1.5,
            zorder=3,
        )

    ax.set_xlabel(cost_label, fontsize=11, color=theme["ink"], labelpad=10)
    ax.set_ylabel(
        "Mean task score (0-100)", fontsize=11, color=theme["ink"], labelpad=10
    )
    ax.set_title(title, fontsize=13, color=theme["ink"], pad=16, loc="left")

    ax.grid(True, color=theme["grid"], linewidth=0.8, zorder=0)
    ax.set_axisbelow(True)
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    for spine in ("left", "bottom"):
        ax.spines[spine].set_color(theme["grid"])
    ax.tick_params(colors=theme["muted"], labelsize=9)

    # Headroom so labels near the axis edges do not clip.
    xs = [p.mean_cost for p in points]
    ys = [p.mean_score for p in points]
    xpad = max((max(xs) - min(xs)) * 0.12, 1.0)
    ypad = max((max(ys) - min(ys)) * 0.12, 3.0)
    ax.set_xlim(max(0.0, min(xs) - xpad), max(xs) + xpad * 2.2)
    ax.set_ylim(max(0.0, min(ys) - ypad), min(100.0, max(ys) + ypad))

    # Labels last, after the limits are final. Only labels that actually collide
    # (close in BOTH x and y) are spread apart in y, and only those get a leader
    # line back to the dot -- an isolated point keeps the plain right-of-dot
    # offset with no line. A draw() fixes the data<->pixel scale so a label's
    # rendered size can be expressed in data units.
    fig.canvas.draw()
    dy_by_point = _label_offsets(ax, fig, points)
    for point in points:
        dy_pts = dy_by_point[id(point)]
        moved = abs(dy_pts) > 1e-6
        ax.annotate(
            _label(point),
            (point.mean_cost, point.mean_score),
            textcoords="offset points",
            xytext=(12, dy_pts),
            fontsize=9,
            color=theme["ink"],
            ha="left",
            va="center",
            zorder=4,
            arrowprops=(
                {
                    "arrowstyle": "-",
                    "color": theme["muted"],
                    "linewidth": 0.6,
                    "shrinkA": 2,
                    "shrinkB": 3,
                }
                if moved
                else None
            ),
        )

    if len(frontier) >= 2:
        legend = ax.legend(loc="lower right", frameon=False, fontsize=9)
        for text in legend.get_texts():
            text.set_color(theme["muted"])

    # Note any excluded failed tasks so the chart is self-explaining: a 0-score
    # (missing-artifact) task is a model failure, not a quality reading, so it is
    # left out of the means, pending investigation.
    excl_notes = [f"{p.model}: {', '.join(p.excluded)}" for p in points if p.excluded]
    if excl_notes:
        note = (
            "* Mean excludes a failed task (0 score / missing artifacts), pending "
            "investigation -- " + "; ".join(excl_notes)
        )
        fig.text(
            0.5,
            -0.02,
            note,
            ha="center",
            va="top",
            fontsize=8,
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
        default="Mean cost per task ($) -- self-hosted hardware-derived; Anthropic metered (see notes)",
        help="X-axis label; make cost provenance explicit",
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
    title = args.title or f"Cost vs. quality -- {args.repo}"

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
    _plot(
        points,
        frontier,
        mode=mode,
        title=title,
        cost_label=args.cost_label,
        output=output,
    )


if __name__ == "__main__":
    main()
