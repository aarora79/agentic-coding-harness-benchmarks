#!/usr/bin/env python3
"""Render an omp event stream as readable text, live or after the fact.

``run-swe-headless.py`` mirrors omp's JSON-lines events to
``<artifacts_dir>/omp-stream.jsonl`` while a task runs (see ``_run_omp``). That
file is the only way to watch an omp task in flight, but one line per token
makes it unreadable raw -- a sentence arrives as fifty ``text_delta`` events.

This reassembles the stream: prose is printed as continuous text, tool calls are
announced with their arguments, tool results are summarized, and each turn ends
with its token usage. It follows the file by default, so it can be pointed at a
task that is still running.

Usage:
    # Follow the task that is running now
    uv run scripts/omp_stream_view.py --latest

    # A specific task, from the beginning, without following
    uv run scripts/omp_stream_view.py --no-follow \\
        swe-benchmark-data/qwen3.8-27b/omp/swe3/mcp-gateway-registry/remove-faiss/omp-stream.jsonl

    # Only what the model did, not what it said
    uv run scripts/omp_stream_view.py --latest --tools-only

    # Also works as a filter
    tail -f .../omp-stream.jsonl | uv run scripts/omp_stream_view.py -
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Iterator, TextIO

_SCRIPTS_DIR = Path(__file__).resolve().parent
_BENCHMARKS_DIR = _SCRIPTS_DIR.parent
DEFAULT_DATA_DIR = _BENCHMARKS_DIR / "swe-benchmark-data"
STREAM_FILENAME = "omp-stream.jsonl"

# How much of a tool's arguments and result to show. Full arguments can be a
# whole file's contents, which would bury the trace it is meant to reveal.
ARGS_PREVIEW_CHARS = 220
RESULT_PREVIEW_CHARS = 400
# Poll interval when following a file that has not grown yet.
FOLLOW_POLL_SECONDS = 0.4


def _latest_stream(data_dir: Path) -> Path:
    """Return the most recently modified omp stream under ``data_dir``.

    Args:
        data_dir: The swe-benchmark-data root to search.

    Returns:
        Path to the newest ``omp-stream.jsonl``.

    Raises:
        SystemExit: If no stream file exists yet.
    """
    streams = sorted(
        data_dir.rglob(STREAM_FILENAME), key=lambda p: p.stat().st_mtime, reverse=True
    )
    if not streams:
        raise SystemExit(
            f"no {STREAM_FILENAME} under {data_dir} -- is an omp run in progress?"
        )
    return streams[0]


def _follow(path: Path) -> Iterator[str]:
    """Yield lines from ``path`` forever, waiting when it stops growing.

    Args:
        path: The file to follow.

    Yields:
        Each line as it is appended.
    """
    with path.open("r", encoding="utf-8") as fh:
        while True:
            line = fh.readline()
            if line:
                yield line
                continue
            time.sleep(FOLLOW_POLL_SECONDS)


def _preview(value: Any, limit: int) -> str:
    """Collapse a value to a single-line preview of at most ``limit`` chars."""
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[:limit] + " ..."


def _result_text(result: Any) -> str:
    """Extract the text of a tool result, whatever shape it arrived in."""
    if isinstance(result, dict):
        parts = [
            c.get("text", "")
            for c in result.get("content") or []
            if isinstance(c, dict) and c.get("type") == "text"
        ]
        if parts:
            return "\n".join(parts)
    return _preview(result, RESULT_PREVIEW_CHARS)


def _usage_line(message: dict[str, Any]) -> str | None:
    """Format an assistant message's token usage, or None if it carries none."""
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    cost = usage.get("cost")
    total = cost.get("total") if isinstance(cost, dict) else cost
    bits = [
        f"in={usage.get('input', 0):,}",
        f"out={usage.get('output', 0):,}",
        f"cacheRead={usage.get('cacheRead', 0):,}",
    ]
    if isinstance(total, (int, float)) and total:
        bits.append(f"${total:.4f}")
    return "  [" + "  ".join(bits) + "]"


def _render(lines: Iterator[str], out: TextIO, tools_only: bool) -> None:
    """Render an omp event stream to ``out``.

    Text deltas are written without newlines so prose reassembles as it streams;
    every other event is a discrete labelled line.

    Args:
        lines: The raw JSON-lines stream.
        out: Where to write the rendered trace.
        tools_only: Skip the model's prose, showing only tool calls and results.
    """
    turn = 0
    mid_text = False

    def end_text() -> None:
        nonlocal mid_text
        if mid_text:
            out.write("\n")
            mid_text = False

    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        etype = event.get("type")

        if etype == "turn_start":
            turn += 1
            end_text()
            out.write(f"\n{'=' * 70}\n=== turn {turn}\n{'=' * 70}\n")
        elif etype == "message_update":
            ame = event.get("assistantMessageEvent") or {}
            if ame.get("type") == "text_delta" and not tools_only:
                out.write(ame.get("delta") or "")
                mid_text = True
        elif etype == "tool_execution_start":
            end_text()
            out.write(
                f"\n  -> {event.get('toolName')}("
                f"{_preview(event.get('args'), ARGS_PREVIEW_CHARS)})\n"
            )
        elif etype == "tool_execution_end":
            end_text()
            text = _result_text(event.get("result"))
            first = text.splitlines()[0] if text.splitlines() else ""
            extra = len(text.splitlines()) - 1
            suffix = f"  (+{extra} more lines)" if extra > 0 else ""
            out.write(f"  <- {_preview(first, RESULT_PREVIEW_CHARS)}{suffix}\n")
        elif etype == "message_end":
            message = event.get("message") or {}
            if message.get("role") == "assistant":
                end_text()
                usage = _usage_line(message)
                if usage:
                    out.write(usage + "\n")
        elif etype == "agent_end":
            end_text()
            out.write("\n=== agent_end\n")
        out.flush()
    end_text()


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Render an omp event stream (omp-stream.jsonl) as readable text.",
        epilog="Examples:\n"
        "  uv run scripts/omp_stream_view.py --latest\n"
        "  uv run scripts/omp_stream_view.py --latest --tools-only\n"
        "  uv run scripts/omp_stream_view.py --no-follow path/to/omp-stream.jsonl\n"
        "  tail -f path/to/omp-stream.jsonl | uv run scripts/omp_stream_view.py -",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "stream",
        nargs="?",
        help="Path to an omp-stream.jsonl, or '-' to read stdin. "
        "Omit and pass --latest to pick the newest automatically.",
    )
    parser.add_argument(
        "--latest",
        action="store_true",
        help="Use the most recently modified omp-stream.jsonl under --data-dir "
        "(the task running now).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help=f"Root to search with --latest (default: {DEFAULT_DATA_DIR})",
    )
    parser.add_argument(
        "--no-follow",
        action="store_true",
        help="Render what is in the file and exit, instead of following it.",
    )
    parser.add_argument(
        "--tools-only",
        action="store_true",
        help="Show only tool calls and results, skipping the model's prose.",
    )
    return parser.parse_args()


def main() -> None:
    """Resolve the stream to read and render it."""
    args = _parse_args()
    if args.stream == "-":
        _render(iter(sys.stdin), sys.stdout, args.tools_only)
        return

    if args.stream:
        path = Path(args.stream).expanduser()
    elif args.latest:
        path = _latest_stream(args.data_dir.expanduser().resolve())
    else:
        raise SystemExit("pass a stream path, '-' for stdin, or --latest")
    if not path.is_file():
        raise SystemExit(f"stream not found: {path}")

    print(f"# {path}", file=sys.stderr)
    if args.no_follow:
        with path.open("r", encoding="utf-8") as fh:
            _render(iter(fh), sys.stdout, args.tools_only)
    else:
        try:
            _render(_follow(path), sys.stdout, args.tools_only)
        except KeyboardInterrupt:
            print("\n(stopped)", file=sys.stderr)


if __name__ == "__main__":
    main()
