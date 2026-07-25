#!/usr/bin/env python3
"""Throughput harness: drive N concurrent agentic /swe2 sessions for a fixed window.

This is the SEPARATE, throughput-oriented sibling of ``run-swe-headless.py``. It
answers a different question -- *how much agentic-coding load can this model on
this hardware sustain, and therefore what does a task really cost?* -- so it is
kept apart from the quality harness rather than bolted onto it. It **imports** the
stable building blocks from ``run-swe-headless.py`` (clone / prompt / env / claude
command / run) and only adds the throughput loop on top; the quality harness is
not modified.

How it differs from the quality run:

  * **Concurrency is the point, not a side effect.** It holds ``--concurrency N``
    agentic sessions in flight, refilling a slot as soon as one finishes, for a
    fixed ``--duration-seconds`` window -- so a saturation curve can be built by
    sweeping N.
  * **Each slot picks a task at RANDOM.** As a slot frees up it is filled by a
    task drawn at random (with replacement) from the dataset -- so with a
    multi-repo dataset (e.g. dataset/multi-repo-throughput.yaml) each concurrent
    slot tends to clone and reason over a DIFFERENT repo, simulating N developers
    each working on their own project rather than N sessions on one repo. Each
    running instance gets a unique slot id so its clone dir and (throwaway)
    artifact dir never collide with a sibling running the same task.
  * **Artifacts are load, not results.** We measure server throughput (via the
    DuckDB metrics collector) and client-side per-request tokens/latency; the
    written artifacts are not scored and their dirs are cleaned up.

The real request shape (large read-heavy prompts, short outputs) comes for free
because each session is a genuine /swe2 run against a real cloned repo -- the same
workload the quality harness produces, just driven at a controlled concurrency.

Usage (normally invoked by run-throughput-sweep.sh, one concurrency per call):
    uv run scripts/run-throughput-harness.py --config config/runner.yaml \\
        --model gemma-4-31b --dataset dataset/mcp-gateway-registry.yaml \\
        --endpoint http://127.0.0.1:8000 --context-window 200000 \\
        --concurrency 5 --duration-seconds 600 --out throughput-c5.json
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import logging
import random
import shutil
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

# Import the quality harness as a library (its filename has hyphens).
_HARNESS_PATH = _SCRIPTS_DIR / "run-swe-headless.py"
_spec = importlib.util.spec_from_file_location("run_swe_headless", _HARNESS_PATH)
if _spec is None or _spec.loader is None:  # pragma: no cover - import wiring
    raise ImportError(f"cannot load harness building blocks from {_HARNESS_PATH}")
harness = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(harness)

from dataset_loader import Dataset, Task, load_dataset  # noqa: E402
from runner_config import RunnerConfig, load_runner_config  # noqa: E402


def _utc_now() -> str:
    """Return the current UTC time as an ISO 8601 string with a trailing Z."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _run_one_session(
    config: RunnerConfig,
    task: Task,
    ref: str,
    slot_label: str,
    deadline: float,
) -> dict[str, Any]:
    """Run one agentic /swe2 session for load and return its per-request record.

    Throughput is measured server-side (vLLM counters in DuckDB), so a session
    does NOT need to finish to count -- the tokens it generated while running are
    already in the collector's window. This session's ``claude -p`` timeout is
    therefore bounded by the remaining window (``deadline``): at window close,
    any still-running session self-terminates promptly via the existing timeout
    rather than dragging the level out by ~30 min waiting for a full agentic run.
    Such a session is recorded as ``cutoff`` (not a failure) -- it consumed real
    serving capacity for the whole window.

    Clones into a slot-unique dir so repeated instances of the same task never
    collide, and always cleans up the clone.

    Args:
        config: The runner config (endpoint, model, timeout, ...).
        task: The dataset task to run this session on.
        ref: The git ref to clone.
        slot_label: A unique label for this in-flight instance (e.g. ``c5#12``).
        deadline: ``time.time()`` value after which the session is cut off.

    Returns:
        A record with tokens, latency, turns, and ok/cutoff/error for this session.
    """
    started = time.time()
    started_iso = _utc_now()
    slot_dir = Path(config.clone_dir) / f"swe-thru-{slot_label.replace('#', '-')}"
    slot_dir.mkdir(parents=True, exist_ok=True)
    # Bound this session by whichever is smaller: the config timeout or the time
    # left in the window. min 1s so a just-past-deadline submit still terminates.
    session_timeout = max(1, int(min(config.timeout_seconds, deadline - started)))

    def _record(status: str, result: dict[str, Any] | None, error: str = "") -> dict:
        usage = (result or {}).get("usage") or {}
        elapsed = time.time() - started
        rec = {
            "slot": slot_label,
            "task": task.id,
            "status": status,  # "ok" | "cutoff" | "error"
            "ok": status == "ok",
            "started_at": started_iso,
            "ended_at": _utc_now(),
            "latency_seconds": round(elapsed, 1),
            "input_tokens": usage.get("input_tokens", 0),
            "output_tokens": usage.get("output_tokens", 0),
            "num_turns": (result or {}).get("num_turns", 0),
        }
        if error:
            rec["error"] = error[:300]
        return rec

    try:
        clone_path = harness._clone_repo(
            task, ref, str(slot_dir), log_prefix=slot_label
        )
        prompt = harness._build_prompt(task, clone_path, ref, config.model_slug)
        cmd = harness._build_claude_cmd(
            config, prompt, stream=False, clone_path=clone_path
        )
        env = harness._build_env(config)
        result = harness._run_claude(cmd, env, session_timeout)
        return _record("ok" if not result.get("is_error", False) else "error", result)
    except Exception as exc:
        # A window-bounded timeout is an expected cutoff, not a failure; anything
        # else (clone error, etc.) is a real error but must not kill the sweep.
        msg = str(exc)
        if "timed out" in msg.lower():
            return _record("cutoff", None, "cut off at window close")
        logger.warning("%s failed: %s", slot_label, msg[:200])
        return _record("error", None, msg)
    finally:
        shutil.rmtree(slot_dir, ignore_errors=True)


def run_level(
    config: RunnerConfig,
    dataset: Dataset,
    tasks: list[Task],
    concurrency: int,
    duration_seconds: int,
) -> dict[str, Any]:
    """Hold ``concurrency`` agentic sessions in flight for ``duration_seconds``.

    A thread pool of width ``concurrency`` is kept saturated: each time a session
    finishes, a task drawn at RANDOM (with replacement) from ``tasks`` is
    submitted, until the wall-clock window elapses. Random selection means that
    with a multi-repo dataset the in-flight slots spread across different repos,
    simulating many developers on different projects rather than one shared
    repo. Sessions still running at window close are **cut
    off** (their ``claude -p`` timeout is bounded by the remaining window) rather
    than drained to completion -- because throughput is measured server-side from
    vLLM's counters over the level's time window, a session need not finish to
    have contributed the tokens it generated. This keeps every level ~= the
    window, even for a slow model whose agentic sessions take far longer.

    ``level_started_at`` / ``level_ended_at`` bound the window so the performance
    summary can slice the DuckDB collector session to exactly this level.

    Args:
        config: The runner config.
        dataset: The loaded dataset (for ref resolution).
        tasks: The tasks to cycle through as load.
        concurrency: How many sessions to hold in flight.
        duration_seconds: Wall-clock window to keep submitting new sessions.

    Returns:
        A level summary: config, wall-clock window bounds, and per-session records.
    """
    refs = {t.id: dataset.resolved_ref(t) for t in tasks}
    records: list[dict[str, Any]] = []
    lock = threading.Lock()
    submitted = 0
    wall_start = time.time()
    deadline = wall_start + duration_seconds
    level_started = _utc_now()

    logger.info(
        "=== concurrency=%s: holding %s sessions in flight for %ss ===",
        concurrency,
        concurrency,
        duration_seconds,
    )
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures: set[Any] = set()

        def _submit() -> None:
            nonlocal submitted
            # Random draw (with replacement) so a multi-repo dataset spreads the
            # in-flight slots across different repos; a single-repo dataset is
            # unaffected (every draw is the same lone task). Load balancing only,
            # not security -- the pseudo-random generator is fine here.
            task = random.choice(tasks)  # nosec B311 - load-slot selection, not crypto
            slot = f"c{concurrency}#{submitted + 1}"
            fut = executor.submit(
                _run_one_session, config, task, refs[task.id], slot, deadline
            )
            futures.add(fut)
            submitted += 1

        for _ in range(concurrency):
            _submit()

        # Refill finished slots only while inside the window. After the window
        # closes, remaining in-flight sessions self-terminate at the deadline
        # (their timeout was bounded to it), so this loop drains in seconds.
        while futures:
            done = {f for f in futures if f.done()}
            for fut in done:
                futures.discard(fut)
                rec = fut.result()
                with lock:
                    records.append(rec)
                logger.info(
                    "  %s %s (%s) out=%s in %.0fs | done=%s in-flight=%s",
                    rec["status"],
                    rec["slot"],
                    rec["task"],
                    rec["output_tokens"],
                    rec["latency_seconds"],
                    len(records),
                    len(futures),
                )
                if time.time() < deadline:
                    _submit()
            if not done:
                time.sleep(0.5)

    wall_seconds = round(time.time() - wall_start, 1)
    by_status: dict[str, int] = {}
    for r in records:
        by_status[r["status"]] = by_status.get(r["status"], 0) + 1
    return {
        "concurrency": concurrency,
        "duration_seconds": duration_seconds,
        "wall_seconds": wall_seconds,
        # Window bounds for slicing the DuckDB collector session to this level.
        "level_started_at": level_started,
        "level_ended_at": _utc_now(),
        "sessions_started": submitted,
        "sessions_by_status": by_status,
        # Throughput is read from the vLLM DuckDB counters over this window, NOT
        # from these client-side token counts (which only cover sessions that
        # actually completed within the window). Kept for context.
        "client_completed_output_tokens": sum(
            r["output_tokens"] for r in records if r["status"] == "ok"
        ),
        "sessions": records,
    }


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Drive N concurrent /swe2 sessions for a fixed window (throughput).",
    )
    parser.add_argument("--config", help="Runner config YAML path")
    parser.add_argument("--model", help="Served model name / id")
    parser.add_argument("--endpoint", help="OpenAI/Anthropic-compatible base URL")
    parser.add_argument("--dataset", help="Dataset YAML path")
    parser.add_argument("--context-window", type=int, dest="context_window")
    parser.add_argument("--timeout-seconds", type=int, dest="timeout_seconds")
    parser.add_argument(
        "--concurrency", type=int, required=True, help="Sessions to hold in flight"
    )
    parser.add_argument(
        "--duration-seconds",
        type=int,
        default=600,
        help="Wall-clock window to keep submitting new sessions (default 600)",
    )
    parser.add_argument(
        "--tasks", help="Comma-separated task ids to cycle (default: all in dataset)"
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Write the level summary JSON here"
    )
    return parser.parse_args()


def main() -> None:
    """Run one concurrency level and write its summary JSON."""
    args = _parse_args()
    overrides: dict[str, Any] = {
        "provider": "endpoint",
        "endpoint": args.endpoint,
        "model": args.model,
        "dataset": args.dataset,
        "context_window": args.context_window,
        "timeout_seconds": args.timeout_seconds,
    }
    config = load_runner_config(args.config, {k: v for k, v in overrides.items() if v})
    dataset = load_dataset(config.dataset)
    tasks = list(dataset.tasks)
    if args.tasks:
        wanted = {t.strip() for t in args.tasks.split(",") if t.strip()}
        tasks = [t for t in tasks if t.id in wanted]
    if not tasks:
        raise SystemExit("no tasks selected to drive load")

    summary = run_level(config, dataset, tasks, args.concurrency, args.duration_seconds)
    summary["model"] = config.model
    summary["endpoint"] = config.endpoint
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(summary, indent=2, default=str) + "\n", encoding="utf-8"
    )
    logger.info(
        "wrote %s: c=%s started=%s by_status=%s wall=%ss "
        "(throughput read from DuckDB over %s..%s)",
        args.out,
        summary["concurrency"],
        summary["sessions_started"],
        summary["sessions_by_status"],
        summary["wall_seconds"],
        summary["level_started_at"],
        summary["level_ended_at"],
    )


if __name__ == "__main__":
    main()
