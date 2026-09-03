#!/usr/bin/env python3
"""Generate the vended ``models.json`` the model-router skill reads.

The skill runs in someone else's repository, inside whatever coding assistant
they use. It cannot import anything from this one. So the measurements it needs
are copied into ``vend/model-router/models.json``, which is committed and served
raw, and this script is the only thing that writes it.

Two differences from the internal ``docs/metrics/pareto-frontier-*.json`` it
reads:

* **Every measured model is included, not the frontier.** The skill filters to
  what the user's assistant actually offers before it ranks anything, and that
  set may contain no frontier model at all -- somebody with only
  ``claude-sonnet-5`` and ``claude-haiku-4-5`` has two models, neither on the
  combined frontier, and still deserves an answer. Dominance is computed at
  recommendation time over the available subset. ``on_combined_frontier`` rides
  along as an annotation.
* **Provenance travels with the data.** The internal file assumes a reader who
  knows this repo. A vended file has no such reader, so it carries the schema
  version, when it was measured, the harness, the skill, the dataset and the
  judge. A consumer holding a stale copy can see that it is stale.

Usage:
    uv run scripts/build_vended_models.py
    uv run scripts/build_vended_models.py --check    # CI: fail if out of date
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
from datetime import date
from pathlib import Path
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

_SCRIPTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
DEFAULT_SOURCE = _REPO_ROOT / "docs" / "metrics" / "pareto-frontier-omp-swe3.json"
DEFAULT_OUT = _REPO_ROOT / "vend" / "model-router" / "models.json"

# Bumped when the shape of models.json changes in a way a consumer would notice.
# Consumers pin this; the skill refuses a major it does not know.
SCHEMA_VERSION = "1.0"

# The judge is not recorded in the frontier JSON, so it is stated here. Keep in
# step with codex_judge.py's default (JUDGE_MODEL overrides it per run).
JUDGE = {
    "model": "openai.gpt-5.6-sol",
    "reasoning_effort": "high",
    "repo_grounded": True,
}

# What each hosting label means for the dollar figures, in the consumer's terms.
# Without this a reader ranks a metered bill against a GPU-hour derivation.
COST_BASIS = {
    "Bedrock": ("Metered Amazon Bedrock token pricing -- what the invoice says."),
    "self-hosted": (
        "Derived: GPU-hour price divided by measured throughput, assuming the "
        "server stays busy. Not directly comparable with a metered bill."
    ),
}


def _git_commit(repo_root: Path) -> str | None:
    """Return the short HEAD sha, or None outside a git checkout.

    Args:
        repo_root: The repository to describe.

    Returns:
        The abbreviated commit, or None if git is unavailable.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.strip() or None


def _measured_on(source: Path) -> str:
    """Return the date the source frontier was last modified, ISO format.

    Uses the file's last git commit date when available, so regenerating without
    changing the data does not advance the measurement date. Falls back to the
    filesystem mtime.

    Args:
        source: The frontier JSON.

    Returns:
        An ISO date string.
    """
    try:
        out = subprocess.run(
            [
                "git",
                "-C",
                str(source.parent),
                "log",
                "-1",
                "--format=%cs",
                "--",
                source.name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if out.stdout.strip():
            return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return date.fromtimestamp(source.stat().st_mtime).isoformat()


def _relative_or_name(source: Path, repo_root: Path) -> str:
    """Return the source path relative to the repo, or its bare name.

    A source outside the repository has no meaningful relative path, and
    recording an absolute one would leak a local directory layout into a file
    published to strangers.

    Args:
        source: The frontier JSON.
        repo_root: Repository root.

    Returns:
        A repo-relative path, or the filename when the source is outside it.
    """
    try:
        return str(source.resolve().relative_to(repo_root.resolve()))
    except ValueError:
        return source.name


def build(source: Path, repo_root: Path) -> dict[str, Any]:
    """Build the vended payload from a frontier JSON.

    Args:
        source: Path to a ``pareto-frontier-*.json``.
        repo_root: Repository root, used for the provenance commit.

    Returns:
        The payload to write as models.json.

    Raises:
        SystemExit: If the source is missing or carries no models.
    """
    if not source.is_file():
        raise SystemExit(f"no frontier JSON at {source}")
    data = json.loads(source.read_text(encoding="utf-8"))
    models = data.get("all_models") or []
    if not models:
        raise SystemExit(f"{source} carries no all_models list")

    combined = {
        m["model"] for m in data.get("combined_frontier_cross_hosting_directional", [])
    }
    bedrock = {m["model"] for m in data.get("bedrock_frontier", [])}
    self_hosted = {m["model"] for m in data.get("self_hosted_frontier", [])}

    out_models = []
    for m in sorted(models, key=lambda x: -x["mean_score"]):
        name = m["model"]
        out_models.append(
            {
                "model": name,
                "score": m["mean_score"],
                "cost_per_task_usd": m["mean_cost_per_task"],
                "hosting": m.get("hosting"),
                # A mean over fewer tasks deserves to be visible rather than
                # averaged into silence: three of the current models did not
                # finish every task.
                "tasks_completed": m.get("n_scored"),
                "tasks_total": m.get("n_tasks"),
                "excluded_tasks": m.get("excluded_tasks") or [],
                # Annotation, never a filter. The skill recomputes dominance
                # over whatever the user can actually select.
                "on_combined_frontier": name in combined,
                "on_hosting_frontier": name in bedrock or name in self_hosted,
            }
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_by": "benchmarks/scripts/build_vended_models.py",
        "provenance": {
            "measured_on": _measured_on(source),
            "source_file": _relative_or_name(source, repo_root),
            "source_commit": _git_commit(repo_root),
            "harness": data.get("harness"),
            "skill": data.get("skill"),
            "dataset": data.get("repo"),
            "judge": JUDGE,
            "repository": "https://github.com/aarora79/agentic-coding-harness-benchmarks",
        },
        "measurement_basis": {
            "what_the_score_is": (
                "Mean 0-100 score over the dataset's tasks. Each task is judged on "
                "six artifacts: a GitHub issue spec, a low-level design, an expert "
                "review, a testing plan, a patch, and an implementation summary."
            ),
            "single_repository_warning": (
                "Every task comes from one repository -- a Python/FastAPI and "
                "React service with nginx, Terraform, Helm and bash around it. "
                "Rankings are more portable than absolute scores, but applying "
                "these to a very different codebase is extrapolation."
            ),
            "runs_per_task": 1,
            "cost_basis": COST_BASIS,
        },
        "models": out_models,
    }


def _parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    p = argparse.ArgumentParser(description="Generate the vended models.json.")
    p.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument(
        "--check",
        action="store_true",
        help="Do not write; exit non-zero if the committed file is out of date.",
    )
    return p.parse_args()


def main() -> None:
    """Generate models.json, or verify the committed copy matches."""
    args = _parse_args()
    payload = build(args.source, _REPO_ROOT)
    text = json.dumps(payload, indent=2) + "\n"

    if args.check:
        if not args.out.is_file():
            raise SystemExit(f"{args.out} does not exist; run without --check")
        if args.out.read_text(encoding="utf-8") != text:
            raise SystemExit(
                f"{args.out} is out of date. Regenerate with:\n"
                f"  uv run scripts/build_vended_models.py"
            )
        logger.info("%s is up to date (%d models)", args.out, len(payload["models"]))
        return

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    logger.info(
        "wrote %s -- %d models, measured %s on %s/%s/%s",
        args.out,
        len(payload["models"]),
        payload["provenance"]["measured_on"],
        payload["provenance"]["harness"],
        payload["provenance"]["skill"],
        payload["provenance"]["dataset"],
    )


if __name__ == "__main__":
    main()
