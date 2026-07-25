"""Tests for the shared judge core: the five-artifact schema and the /swe2
implementation artifact rendering.

These cover the two behaviors added when the implementation artifact (patch.diff
plus implementation.md) became a fifth judged artifact: the strict schema now
requires an ``implementation`` score and ``task_score`` is the mean of five
totals, and ``render_judge_prompt`` embeds the implementation (or an empty
string when a run is design-only) without erroring.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from judge_common import (  # noqa: E402
    EvaluationResult,
    JudgeError,
    _read_implementation,
    parse_and_validate_result,
    render_judge_prompt,
)


def _artifact(total: int) -> dict[str, Any]:
    """A criteria block whose four sub-scores sum to ``total`` (total // 4 each)."""
    each = total // 4
    return {
        "completeness": each,
        "correctness": each,
        "specificity": each,
        "risk_awareness": total - 3 * each,
        "total": total,
        "notes": "n",
    }


def _result(
    *, totals: tuple[int, int, int, int, int], task_score: float
) -> dict[str, Any]:
    gi, lld, rev, test, impl = totals
    return {
        "task": "task-a",
        "model": "candidate-a",
        "scores": {
            "github_issue": _artifact(gi),
            "lld": _artifact(lld),
            "review": _artifact(rev),
            "testing": _artifact(test),
            "implementation": _artifact(impl),
        },
        "task_score": task_score,
        "verdict": "v",
    }


def _design_only_folder(root: Path) -> Path:
    folder = root / "candidate-a" / "repo-a" / "task-a"
    folder.mkdir(parents=True)
    for filename in ("github-issue.md", "lld.md", "review.md", "testing.md"):
        (folder / filename).write_text(f"# {filename}\n\nbody\n", encoding="utf-8")
    return folder


class FiveArtifactSchemaTest(unittest.TestCase):
    def test_task_score_is_mean_of_five_totals(self) -> None:
        # Four 80s and one 0 -> 320 / 5 = 64.0.
        result = EvaluationResult.model_validate(
            _result(totals=(80, 80, 80, 80, 0), task_score=64.0)
        )
        self.assertEqual(result.task_score, 64.0)
        self.assertEqual(result.scores.implementation.total, 0)

    def test_wrong_mean_is_rejected(self) -> None:
        # Old mean-of-four value (80.0) must now fail against the five-total mean.
        with self.assertRaisesRegex(JudgeError, "task_score"):
            parse_and_validate_result(
                json.dumps(_result(totals=(80, 80, 80, 80, 0), task_score=80.0)),
                task_id="task-a",
                candidate_id="candidate-a",
            )

    def test_missing_implementation_score_is_rejected(self) -> None:
        payload = _result(totals=(80, 80, 80, 80, 0), task_score=64.0)
        del payload["scores"]["implementation"]
        with self.assertRaisesRegex(JudgeError, "implementation"):
            parse_and_validate_result(
                json.dumps(payload), task_id="task-a", candidate_id="candidate-a"
            )


class ImplementationRenderingTest(unittest.TestCase):
    def test_design_only_folder_renders_empty_implementation(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = _design_only_folder(Path(tmp))
            self.assertEqual(_read_implementation(folder), "")
            prompt, _, _, _ = render_judge_prompt(
                folder, task_context="t", repository_context="r"
            )
            # The implementation slot is present but empty (JSON empty string).
            self.assertIn('"implementation": ""', prompt)

    def test_patch_and_summary_are_embedded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            folder = _design_only_folder(Path(tmp))
            (folder / "implementation.md").write_text(
                "changed two files", encoding="utf-8"
            )
            (folder / "patch.diff").write_text(
                "diff --git a/x b/x\n+added line\n", encoding="utf-8"
            )
            impl = _read_implementation(folder)
            self.assertIn("changed two files", impl)
            self.assertIn("added line", impl)
            self.assertIn("patch.diff", impl)
            prompt, _, _, _ = render_judge_prompt(
                folder, task_context="t", repository_context="r"
            )
            self.assertIn("added line", prompt)


if __name__ == "__main__":
    unittest.main()
