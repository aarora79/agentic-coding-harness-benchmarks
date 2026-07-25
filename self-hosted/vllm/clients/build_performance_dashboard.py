#!/usr/bin/env python3
"""Render a self-contained HTML dashboard from a PERFORMANCE-SUMMARY.json.

Takes the throughput-sweep summary (see build_performance_summary.py) and writes
a single static HTML file -- no external assets, no CDN, works offline -- showing,
for one model on one EC2 instance:

  * headline tiles: peak throughput, cheapest $/1M output tokens, cost per task;
  * throughput vs concurrency (output + prompt tokens/s);
  * cost per 1M output tokens vs concurrency;
  * latency vs concurrency (TTFT, TPOT);
  * saturation vs concurrency (KV-cache %, running/waiting requests).

Charts are inline SVG built from the JSON, so the file is portable and diffable.

Usage:
    uv run python -m clients.build_performance_dashboard \\
        --summary benchmark-output/throughput/gemma-4-31b/PERFORMANCE-SUMMARY.json
"""

from __future__ import annotations

import argparse
import html
import json
import logging
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# dataviz palette (light surface): recessive neutrals + one warm accent line.
_INK = "#0b0b0b"
_MUTED = "#52514e"
_GRID = "#e6e5e2"
_ACCENT = "#eb6834"
_BLUE = "#2a78d6"
_SURFACE = "#fcfcfb"

_W, _H = 640, 300
_PAD_L, _PAD_R, _PAD_T, _PAD_B = 64, 24, 24, 44


def _line_chart(
    title: str,
    xs: list[float],
    series: list[tuple[str, list[float | None], str]],
    y_label: str,
    x_label: str = "concurrency",
) -> str:
    """Build one inline-SVG line chart. series = [(name, ys, hex_color)]."""
    finite = [v for _, ys, _ in series for v in ys if v is not None]
    if not xs or not finite:
        return f'<div class="chart"><h3>{html.escape(title)}</h3><p class="muted">no data</p></div>'
    xmin, xmax = min(xs), max(xs)
    ymax = max(finite) * 1.15 or 1.0
    ymin = 0.0

    def px(x: float) -> float:
        span = (xmax - xmin) or 1.0
        return _PAD_L + (x - xmin) / span * (_W - _PAD_L - _PAD_R)

    def py(y: float) -> float:
        span = (ymax - ymin) or 1.0
        return _H - _PAD_B - (y - ymin) / span * (_H - _PAD_T - _PAD_B)

    parts = [f'<svg viewBox="0 0 {_W} {_H}" class="svg" role="img">']
    # y gridlines + labels (5 ticks)
    for i in range(6):
        yv = ymin + (ymax - ymin) * i / 5
        y = py(yv)
        parts.append(
            f'<line x1="{_PAD_L}" y1="{y:.1f}" x2="{_W - _PAD_R}" y2="{y:.1f}" '
            f'stroke="{_GRID}" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{_PAD_L - 8}" y="{y + 4:.1f}" text-anchor="end" '
            f'font-size="11" fill="{_MUTED}">{yv:.0f}</text>'
        )
    # x labels at each concurrency point
    for x in xs:
        parts.append(
            f'<text x="{px(x):.1f}" y="{_H - _PAD_B + 18:.1f}" text-anchor="middle" '
            f'font-size="11" fill="{_MUTED}">{int(x)}</text>'
        )
    parts.append(
        f'<text x="{_W / 2:.0f}" y="{_H - 6}" text-anchor="middle" font-size="12" '
        f'fill="{_INK}">{html.escape(x_label)}</text>'
    )
    parts.append(
        f'<text x="16" y="{_H / 2:.0f}" text-anchor="middle" font-size="12" '
        f'fill="{_INK}" transform="rotate(-90 16 {_H / 2:.0f})">{html.escape(y_label)}</text>'
    )
    # series
    for name, ys, color in series:
        pts = [(px(x), py(y)) for x, y in zip(xs, ys) if y is not None]
        if not pts:
            continue
        path = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.append(
            f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.5"/>'
        )
        for x, y in pts:
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{color}"/>')
    parts.append("</svg>")
    legend = " ".join(
        f'<span class="key"><span class="dot" style="background:{c}"></span>{html.escape(n)}</span>'
        for n, _, c in series
        if len(series) > 1
    )
    return (
        f'<div class="chart"><h3>{html.escape(title)}</h3>'
        + "".join(parts)
        + (f'<div class="legend">{legend}</div>' if legend else "")
        + "</div>"
    )


def _tile(label: str, value: str, sub: str = "") -> str:
    """Build one headline stat tile."""
    return (
        f'<div class="tile"><div class="tile-val">{html.escape(value)}</div>'
        f'<div class="tile-label">{html.escape(label)}</div>'
        + (f'<div class="tile-sub">{html.escape(sub)}</div>' if sub else "")
        + "</div>"
    )


def _render(summary: dict[str, Any]) -> str:
    """Render the full HTML document from the summary dict."""
    levels = summary.get("levels", [])
    xs = [float(r["concurrency"]) for r in levels]

    def col(key: str, sub: str | None = None) -> list[float | None]:
        return [(r.get(key, {}).get(sub) if sub else r.get(key)) for r in levels]

    charts = [
        _line_chart(
            "Throughput vs concurrency",
            xs,
            [
                ("output tokens/s", col("output_tokens_per_second"), _ACCENT),
                ("prompt tokens/s", col("prompt_tokens_per_second"), _BLUE),
            ],
            "tokens / second",
        ),
        _line_chart(
            "Latency vs concurrency",
            xs,
            [
                ("TTFT (ms)", col("ttft_ms_mean"), _ACCENT),
                ("TPOT (ms)", col("tpot_ms_mean"), _BLUE),
            ],
            "milliseconds",
        ),
        _line_chart(
            "Cost per 1M tokens vs concurrency",
            xs,
            [
                (
                    "blended $/1M (Lens A)",
                    col("blended_cost_per_1m_tokens_usd"),
                    _ACCENT,
                ),
                (
                    "output $/1M (Lens B)",
                    col("split_cost_per_1m_output_tokens_usd"),
                    _BLUE,
                ),
                (
                    "input $/1M (Lens B)",
                    col("split_cost_per_1m_input_tokens_usd"),
                    _MUTED,
                ),
            ],
            "USD / 1M tokens",
        ),
        _line_chart(
            "Saturation vs concurrency",
            xs,
            [
                (
                    "KV cache % (x100)",
                    [
                        (v * 100 if v is not None else None)
                        for v in col("kv_cache_usage", "peak")
                    ],
                    _ACCENT,
                ),
                ("running reqs (peak)", col("requests_running", "peak"), _BLUE),
                ("waiting reqs (peak)", col("requests_waiting", "peak"), _MUTED),
            ],
            "value",
        ),
    ]

    peak_tps = summary.get("peak_output_tokens_per_second")
    min_blended_task = summary.get("min_task_cost_blended_usd")
    min_split_task = summary.get("min_task_cost_split_usd")
    n_in = summary.get("task_input_tokens")
    m_out = summary.get("task_output_tokens")
    ratio = summary.get("task_input_output_ratio")
    w = summary.get("split_input_weight")
    tiles = [
        _tile(
            "peak throughput",
            f"{peak_tps:.0f} tok/s" if peak_tps else "n/a",
            f"at concurrency {summary.get('peak_at_concurrency')}",
        ),
        _tile(
            "cost per task (blended)",
            f"${min_blended_task:.2f}" if min_blended_task is not None else "n/a",
            f"{n_in:,}:{m_out:,} in:out" if n_in and m_out else "",
        ),
        _tile(
            "cost per task (split)",
            f"${min_split_task:.2f}" if min_split_task is not None else "n/a",
            f"input weighted {w}x" if w is not None else "",
        ),
        _tile(
            "cheapest blended",
            f"${summary.get('min_blended_cost_per_1m_tokens_usd')}/1M"
            if summary.get("min_blended_cost_per_1m_tokens_usd")
            else "n/a",
            "per token processed",
        ),
        _tile(
            "instance",
            summary.get("instance_type", "?"),
            f"${summary.get('dollars_per_hour')}/hr",
        ),
    ]

    model = html.escape(str(summary.get("model", "?")))
    instance = html.escape(str(summary.get("instance_type", "?")))
    rows = "".join(
        "<tr>"
        + f"<td>{r['concurrency']}</td>"
        + f"<td>{r.get('output_tokens_per_second') or '-'}</td>"
        + f"<td>{r.get('prompt_tokens_per_second') or '-'}</td>"
        + f"<td>{r.get('ttft_ms_mean') or '-'}</td>"
        + f"<td>{r.get('tpot_ms_mean') or '-'}</td>"
        + f"<td>{(r.get('kv_cache_usage') or {}).get('peak') or '-'}</td>"
        + f"<td>{r.get('blended_cost_per_1m_tokens_usd') or '-'}</td>"
        + f"<td>{r.get('task_cost_blended_usd') or '-'}</td>"
        + f"<td>{r.get('task_cost_split_usd') or '-'}</td>"
        + "</tr>"
        for r in levels
    )
    # Per-level per-token costs for the in-browser N:M / w recompute.
    calc_levels = json.dumps(
        [
            {
                "c": r["concurrency"],
                "blended": r.get("blended_cost_per_token_usd"),
                "out": r.get("split_cost_per_output_token_usd"),
                # split_cost_per_input = w * out; recomputed in JS from w so the
                # slider works, but seed with the summary's value.
                "prompt_tps": r.get("prompt_tokens_per_second"),
                "gen_tps": r.get("output_tokens_per_second"),
            }
            for r in levels
        ]
    )
    dps = (summary.get("dollars_per_hour") or 0) / 3600.0
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Throughput &amp; cost -- {model} on {instance}</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, Roboto, sans-serif; margin: 0;
         background: {_SURFACE}; color: {_INK}; }}
  .wrap {{ max-width: 1360px; margin: 0 auto; padding: 28px; }}
  h1 {{ font-size: 20px; margin: 0 0 4px; }}
  .sub {{ color: {_MUTED}; margin: 0 0 20px; font-size: 13px; }}
  .tiles {{ display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 24px; }}
  .tile {{ background: #fff; border: 1px solid {_GRID}; border-radius: 10px;
          padding: 16px 20px; min-width: 150px; }}
  .tile-val {{ font-size: 24px; font-weight: 650; }}
  .tile-label {{ color: {_MUTED}; font-size: 12px; text-transform: uppercase;
                letter-spacing: .04em; margin-top: 2px; }}
  .tile-sub {{ color: {_MUTED}; font-size: 12px; margin-top: 2px; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr));
          gap: 18px; }}
  .chart {{ background: #fff; border: 1px solid {_GRID}; border-radius: 10px; padding: 14px 16px; }}
  .chart h3 {{ font-size: 14px; margin: 0 0 6px; }}
  .svg {{ width: 100%; height: auto; }}
  .legend {{ font-size: 12px; color: {_MUTED}; margin-top: 6px; }}
  .key {{ margin-right: 14px; }}
  .dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 2px;
         margin-right: 5px; vertical-align: middle; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 24px; font-size: 13px; }}
  th, td {{ border-bottom: 1px solid {_GRID}; padding: 7px 10px; text-align: right; }}
  th:first-child, td:first-child {{ text-align: left; }}
  th {{ color: {_MUTED}; font-weight: 600; }}
  .muted {{ color: {_MUTED}; }}
  .calc {{ background: #fff; border: 1px solid {_GRID}; border-radius: 10px;
          padding: 16px 20px; margin: 24px 0; }}
  .calc h3 {{ font-size: 14px; margin: 0 0 10px; }}
  .calc label {{ font-size: 12px; color: {_MUTED}; margin-right: 6px; }}
  .calc input {{ width: 120px; padding: 4px 6px; margin-right: 18px;
                border: 1px solid {_GRID}; border-radius: 6px; font-size: 13px; }}
  .calc .out {{ font-size: 15px; margin-top: 12px; }}
  .calc .out b {{ font-size: 20px; }}
</style></head>
<body><div class="wrap">
  <h1>Throughput &amp; cost -- {model} on {instance}</h1>
  <p class="sub">Agentic /swe concurrency sweep. Throughput from vLLM server
     counters (DuckDB); machine cost = ${summary.get("dollars_per_hour")}/hr on
     {instance}. A "task" is a blended {n_in:,} input : {m_out:,} output tokens
     (~{ratio}:1, from real /swe runs). <b>Two cost lenses:</b> <b>blended</b> (Lens A)
     charges every processed token the same measured GPU-slice; <b>split</b> (Lens B)
     weights an input token at {w}&times; an output token (a lab-style convention,
     not measured). Cost is hardware-derived, not a per-token bill.</p>
  <div class="tiles">{"".join(tiles)}</div>
  <div class="grid">{"".join(charts)}</div>

  <div class="calc">
    <h3>Blended-task cost calculator (at the cheapest / peak-throughput level)</h3>
    <label>input tokens (N)</label><input id="nIn" type="number" value="{n_in}">
    <label>output tokens (M)</label><input id="mOut" type="number" value="{m_out}">
    <label>input weight w (Lens B)</label><input id="w" type="number" step="0.05" value="{w}">
    <div class="out">
      Lens A (blended): <b id="taskA">-</b> &nbsp;|&nbsp;
      Lens B (split): <b id="taskB">-</b>
      <span class="muted" id="atLevel"></span>
    </div>
  </div>

  <table>
    <thead><tr><th>concurrency</th><th>out tok/s</th><th>prompt tok/s</th>
      <th>TTFT ms</th><th>TPOT ms</th><th>KV peak</th>
      <th>blended $/1M</th><th>$/task blended</th><th>$/task split</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</div>
<script>
  // Per-level measured per-token costs; recompute task cost as N:M and w change.
  const LEVELS = {calc_levels};
  const DPS = {dps};
  function fmt(x) {{ return x == null ? "-" : "$" + x.toFixed(2); }}
  function recompute() {{
    const N = parseFloat(document.getElementById("nIn").value) || 0;
    const M = parseFloat(document.getElementById("mOut").value) || 0;
    const w = parseFloat(document.getElementById("w").value) || 0;
    // Cheapest blended task cost across levels drives the headline.
    let bestA = null, bestB = null, bestLevel = null;
    for (const L of LEVELS) {{
      if (L.blended != null) {{
        const a = L.blended * (N + M);
        if (bestA == null || a < bestA) {{ bestA = a; bestLevel = L.c; }}
      }}
      // Lens B recomputed from w so the slider is live:
      // cost_out = DPS / (gen_tps + w*prompt_tps); cost_in = w*cost_out.
      const denom = (L.gen_tps || 0) + w * (L.prompt_tps || 0);
      if (denom > 0) {{
        const costOut = DPS / denom;
        const b = costOut * M + (w * costOut) * N;
        if (bestB == null || b < bestB) bestB = b;
      }}
    }}
    document.getElementById("taskA").textContent = fmt(bestA);
    document.getElementById("taskB").textContent = fmt(bestB);
    document.getElementById("atLevel").textContent =
      bestLevel != null ? " (cheapest at concurrency " + bestLevel + ")" : "";
  }}
  for (const id of ["nIn", "mOut", "w"])
    document.getElementById(id).addEventListener("input", recompute);
  recompute();
</script>
</body></html>
"""


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="Render an HTML dashboard from a PERFORMANCE-SUMMARY.json."
    )
    p.add_argument(
        "--summary", required=True, type=Path, help="PERFORMANCE-SUMMARY.json"
    )
    p.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output HTML (default: <summary dir>/performance-dashboard.html)",
    )
    return p.parse_args()


def main() -> None:
    """Render the dashboard HTML from the summary JSON."""
    args = _parse_args()
    summary_path = args.summary.expanduser().resolve()
    if not summary_path.is_file():
        raise SystemExit(f"summary not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    output = args.output or (summary_path.parent / "performance-dashboard.html")
    output.write_text(_render(summary), encoding="utf-8")
    logger.info(
        "wrote %s (%d concurrency levels)", output, len(summary.get("levels", []))
    )


if __name__ == "__main__":
    main()
