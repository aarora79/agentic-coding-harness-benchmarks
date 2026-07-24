#!/usr/bin/env python3
"""Build PERFORMANCE-SUMMARY.json for a throughput sweep of one model+instance.

Reads the shared DuckDB written by the concurrency sweep (one named collector
session per level, ``{model}_c{N}``) and derives, per concurrency level, the
server-measured throughput, latency, and saturation -- then a realistic cost per
token and per task from the instance's hourly price:

    cost_per_output_token = (dollars_per_hour / 3600) / output_tokens_per_second
    cost_per_task         = cost_per_output_token * output_tokens_per_task

Throughput comes from vLLM's own counters (generation/prompt tokens), NOT from
whether an agentic session finished -- the sweep deliberately cuts sessions off
at the window, so the counter delta over the session's window IS the sustained
throughput at that concurrency. The output is analysis-ready for a simple HTML
dashboard (see build_performance_dashboard.py).

Usage:
    uv run python -m clients.build_performance_summary \\
        --model gemma-4-31b --db benchmark-output/throughput/gemma-4-31b/throughput-metrics.duckdb \\
        --instance-type g6e.12xlarge --dollars-per-hour 10.49 \\
        --output-tokens-per-task 24000
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

import duckdb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Counter metrics -> throughput via (last - first) / window.
GEN_TOKENS = "vllm:generation_tokens_total"
PROMPT_TOKENS = "vllm:prompt_tokens_total"
# Gauge metrics -> saturation via peak/mean while under load.
KV_USAGE = "vllm:kv_cache_usage_perc"
REQ_RUNNING = "vllm:num_requests_running"
REQ_WAITING = "vllm:num_requests_waiting"
# Histogram sum/count pairs -> mean latency over the window's requests.
TTFT = "vllm:time_to_first_token_seconds"
TPOT = "vllm:request_time_per_output_token_seconds"


def _counter_rate(con: duckdb.DuckDBPyConnection, session: str, metric: str) -> dict:
    """Return {delta, seconds, per_second} for a counter over a session window.

    Sums across label sets per scrape (server-wide counters may be split by
    labels), then takes the last-minus-first over the session's elapsed time.
    """
    row = con.execute(
        """
        WITH per_scrape AS (
            SELECT scraped_at, sum(value) AS v
            FROM vllm_metric_samples
            WHERE session_name = ? AND metric = ?
            GROUP BY scraped_at
        )
        SELECT
            max(v) - min(v) AS delta,
            date_diff('second', min(scraped_at), max(scraped_at)) AS seconds
        FROM per_scrape
        """,
        [session, metric],
    ).fetchone()
    delta = float(row[0]) if row and row[0] is not None else 0.0
    seconds = float(row[1]) if row and row[1] else 0.0
    return {
        "delta_tokens": round(delta),
        "window_seconds": round(seconds, 1),
        "tokens_per_second": round(delta / seconds, 2) if seconds > 0 else None,
    }


def _gauge_stats(con: duckdb.DuckDBPyConnection, session: str, metric: str) -> dict:
    """Return {peak, mean} for a gauge over a session window (max across labels)."""
    row = con.execute(
        """
        WITH per_scrape AS (
            SELECT scraped_at, max(value) AS v
            FROM vllm_metric_samples
            WHERE session_name = ? AND metric = ?
            GROUP BY scraped_at
        )
        SELECT max(v), avg(v) FROM per_scrape
        """,
        [session, metric],
    ).fetchone()
    peak = float(row[0]) if row and row[0] is not None else None
    mean = float(row[1]) if row and row[1] is not None else None
    return {
        "peak": round(peak, 4) if peak is not None else None,
        "mean": round(mean, 4) if mean is not None else None,
    }


def _hist_mean_ms(
    con: duckdb.DuckDBPyConnection, session: str, base: str
) -> float | None:
    """Mean latency (ms) over a window from a histogram's _sum/_count deltas."""

    def _delta(suffix: str) -> float:
        row = con.execute(
            """
            WITH per_scrape AS (
                SELECT scraped_at, sum(value) AS v
                FROM vllm_metric_samples
                WHERE session_name = ? AND metric = ?
                GROUP BY scraped_at
            )
            SELECT max(v) - min(v) FROM per_scrape
            """,
            [session, base + suffix],
        ).fetchone()
        return float(row[0]) if row and row[0] is not None else 0.0

    sum_delta = _delta("_sum")
    count_delta = _delta("_count")
    if count_delta <= 0:
        return None
    return round((sum_delta / count_delta) * 1000, 1)


def _levels(con: duckdb.DuckDBPyConnection, model: str) -> list[tuple[int, str]]:
    """Return [(concurrency, session_name)] for this model's sweep, sorted by N."""
    rows = con.execute(
        "SELECT DISTINCT session_name FROM collector_sessions WHERE session_name LIKE ?",
        [f"{model}_c%"],
    ).fetchall()
    out = []
    for (name,) in rows:
        suffix = name.rsplit("_c", 1)[-1]
        if suffix.isdigit():
            out.append((int(suffix), name))
    return sorted(out)


def _build(
    db: Path,
    model: str,
    instance_type: str,
    dph: float,
    out_tokens_per_task: int | None,
) -> dict[str, Any]:
    """Assemble the performance summary from the DuckDB sweep sessions."""
    con = duckdb.connect(str(db), read_only=True)
    try:
        levels = _levels(con, model)
        if not levels:
            raise SystemExit(f"no sweep sessions '{model}_c*' found in {db}")
        dollars_per_second = dph / 3600.0
        rows: list[dict[str, Any]] = []
        for concurrency, session in levels:
            gen = _counter_rate(con, session, GEN_TOKENS)
            prompt = _counter_rate(con, session, PROMPT_TOKENS)
            out_tps = gen["tokens_per_second"]
            cost_per_out_tok = (
                dollars_per_second / out_tps if out_tps and out_tps > 0 else None
            )
            rows.append(
                {
                    "concurrency": concurrency,
                    "session_name": session,
                    "output_tokens_per_second": out_tps,
                    "prompt_tokens_per_second": prompt["tokens_per_second"],
                    "window_seconds": gen["window_seconds"],
                    "kv_cache_usage": _gauge_stats(con, session, KV_USAGE),
                    "requests_running": _gauge_stats(con, session, REQ_RUNNING),
                    "requests_waiting": _gauge_stats(con, session, REQ_WAITING),
                    "ttft_ms_mean": _hist_mean_ms(con, session, TTFT),
                    "tpot_ms_mean": _hist_mean_ms(con, session, TPOT),
                    "cost_per_output_token_usd": cost_per_out_tok,
                    "cost_per_1m_output_tokens_usd": round(cost_per_out_tok * 1e6, 2)
                    if cost_per_out_tok
                    else None,
                    "cost_per_task_usd": round(
                        cost_per_out_tok * out_tokens_per_task, 4
                    )
                    if cost_per_out_tok and out_tokens_per_task
                    else None,
                }
            )
        # Peak sustained throughput across levels (the saturation ceiling).
        best = max(
            (r for r in rows if r["output_tokens_per_second"]),
            key=lambda r: r["output_tokens_per_second"],
            default=None,
        )
        return {
            "model": model,
            "instance_type": instance_type,
            "dollars_per_hour": dph,
            "output_tokens_per_task": out_tokens_per_task,
            "peak_output_tokens_per_second": best["output_tokens_per_second"]
            if best
            else None,
            "peak_at_concurrency": best["concurrency"] if best else None,
            "min_cost_per_1m_output_tokens_usd": min(
                (
                    r["cost_per_1m_output_tokens_usd"]
                    for r in rows
                    if r["cost_per_1m_output_tokens_usd"]
                ),
                default=None,
            ),
            "levels": rows,
        }
    finally:
        con.close()


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(
        description="Build PERFORMANCE-SUMMARY.json from a throughput-sweep DuckDB."
    )
    p.add_argument("--model", required=True, help="Served model name (session prefix)")
    p.add_argument("--db", required=True, type=Path, help="Sweep DuckDB path")
    p.add_argument(
        "--instance-type", default="unknown", help="EC2 instance type (provenance)"
    )
    p.add_argument(
        "--dollars-per-hour",
        type=float,
        required=True,
        help="Instance on-demand $/hr (e.g. 10.49 for g6e.12xlarge)",
    )
    p.add_argument(
        "--output-tokens-per-task",
        type=int,
        default=None,
        help="Mean output tokens per agentic task, for cost-per-task (from metrics).",
    )
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: <db dir>/PERFORMANCE-SUMMARY.json)",
    )
    return p.parse_args()


def main() -> None:
    """Build and write the performance summary."""
    args = _parse_args()
    db = args.db.expanduser().resolve()
    if not db.is_file():
        raise SystemExit(f"DuckDB not found: {db}")
    summary = _build(
        db,
        args.model,
        args.instance_type,
        args.dollars_per_hour,
        args.output_tokens_per_task,
    )
    out = args.out or (db.parent / "PERFORMANCE-SUMMARY.json")
    out.write_text(json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8")
    logger.info(
        "wrote %s: %d levels, peak %s tok/s @ c=%s, min $%.2f/1M output tokens",
        out,
        len(summary["levels"]),
        summary["peak_output_tokens_per_second"],
        summary["peak_at_concurrency"],
        summary["min_cost_per_1m_output_tokens_usd"] or 0.0,
    )


if __name__ == "__main__":
    main()
