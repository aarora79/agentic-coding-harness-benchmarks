"""Tests for the /swe-auto executor's pure helpers (no subprocess execution)."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import swe_auto_run as run  # noqa: E402
from dataset_loader import load_dataset  # noqa: E402
from swe_auto_router import FrontierEntry, ModelExecution, SweAutoConfig  # noqa: E402


def _config(**overrides: object) -> SweAutoConfig:
    return SweAutoConfig.model_validate(overrides)


class TestEphemeralDataset(unittest.TestCase):
    """The synthetic one-task dataset validates through the real loader."""

    def test_dict_has_single_task_with_pinned_ref(self) -> None:
        data = run._ephemeral_dataset_dict(
            "https://github.com/octocat/Hello-World", "1.2.3", "remove-faiss"
        )
        self.assertEqual(len(data["tasks"]), 1)
        task = data["tasks"][0]
        self.assertEqual(task["id"], "remove-faiss")
        self.assertEqual(task["ref"], "1.2.3")

    def test_full_problem_statement_is_carried_through(self) -> None:
        data = run._ephemeral_dataset_dict(
            "https://x/y/repo",
            "main",
            "add-guide",
            "Add a CONTRIBUTING.md with X and Y.",
        )
        self.assertEqual(
            data["tasks"][0]["problem_statement"], "Add a CONTRIBUTING.md with X and Y."
        )

    def test_missing_problem_statement_falls_back_to_pointer(self) -> None:
        data = run._ephemeral_dataset_dict("https://x/y/repo", "main", "add-guide")
        self.assertIn("add-guide", data["tasks"][0]["problem_statement"])

    def test_issue_url_only_omits_synthetic_statement(self) -> None:
        url = "https://github.com/o/r/issues/42"
        data = run._ephemeral_dataset_dict(
            "https://x/y/repo", "main", "fix-42", problem_issue_url=url
        )
        task = data["tasks"][0]
        self.assertEqual(task["problem_issue_url"], url)
        self.assertNotIn("problem_statement", task)  # issue is the sole source

    def test_issue_url_only_still_validates(self) -> None:
        path = run._write_ephemeral_dataset(
            "https://github.com/octocat/Hello-World",
            "master",
            "fix-42",
            problem_issue_url="https://github.com/octocat/Hello-World/issues/42",
        )
        try:
            dataset = load_dataset(path)  # Task requires >=1 problem source
            self.assertEqual([t.id for t in dataset.tasks], ["fix-42"])
            self.assertEqual(
                dataset.tasks[0].problem_issue_url,
                "https://github.com/octocat/Hello-World/issues/42",
            )
        finally:
            path.unlink(missing_ok=True)

    def test_statement_and_issue_url_both_carried(self) -> None:
        data = run._ephemeral_dataset_dict(
            "https://x/y/repo",
            "main",
            "fix-42",
            problem_statement="Do the thing.",
            problem_issue_url="https://github.com/o/r/issues/42",
        )
        task = data["tasks"][0]
        self.assertEqual(task["problem_statement"], "Do the thing.")
        self.assertEqual(task["problem_issue_url"], "https://github.com/o/r/issues/42")

    def test_written_dataset_loads(self) -> None:
        path = run._write_ephemeral_dataset(
            "https://github.com/octocat/Hello-World", "master", "add-guide"
        )
        try:
            dataset = load_dataset(path)
            self.assertEqual([t.id for t in dataset.tasks], ["add-guide"])
        finally:
            path.unlink(missing_ok=True)


class TestArtifactDir(unittest.TestCase):
    """Artifact dir mirrors the harness layout for both hosting paths."""

    def test_bedrock_wire_id_maps_to_the_slug_folder(self) -> None:
        ex = ModelExecution(provider="bedrock", model="us.anthropic.claude-opus-5")
        d = run._artifact_dir(
            _config(harness="claude-code"), ex, "https://x/y/mcp-gateway-registry", "t1"
        )
        self.assertEqual(
            d.parts[-5:],
            ("claude-opus-5", "claude-code", "swe3", "mcp-gateway-registry", "t1"),
        )

    def test_endpoint_served_name_is_the_slug(self) -> None:
        ex = ModelExecution(
            provider="endpoint", model="qwen3.6-35b", endpoint="http://x:8000"
        )
        d = run._artifact_dir(_config(harness="pi"), ex, "https://x/y/repo.git", "t2")
        self.assertEqual(d.parts[-5:], ("qwen3.6-35b", "pi", "swe3", "repo", "t2"))


class TestRunnerCmd(unittest.TestCase):
    """The headless-runner command carries the selected model + routing."""

    def test_endpoint_adds_endpoint_flag(self) -> None:
        ex = ModelExecution(provider="endpoint", model="m", endpoint="http://h:8000")
        cmd = run._build_runner_cmd(
            _config(harness="pi"), ex, Path("/tmp/ds.yaml"), "t"
        )
        self.assertIn("--endpoint", cmd)
        self.assertEqual(cmd[cmd.index("--endpoint") + 1], "http://h:8000")
        self.assertEqual(cmd[cmd.index("--agent") + 1], "pi")
        self.assertEqual(cmd[cmd.index("--model") + 1], "m")
        self.assertEqual(cmd[cmd.index("--skill") + 1], "swe3")

    def test_bedrock_adds_region_only_when_configured(self) -> None:
        ex = ModelExecution(provider="bedrock", model="us.anthropic.claude-opus-5")
        without = run._build_runner_cmd(_config(), ex, Path("/tmp/ds.yaml"), "t")
        self.assertNotIn("--aws-region", without)
        self.assertNotIn("--endpoint", without)
        with_region = run._build_runner_cmd(
            _config(aws_region="us-east-1"), ex, Path("/tmp/ds.yaml"), "t"
        )
        self.assertEqual(
            with_region[with_region.index("--aws-region") + 1], "us-east-1"
        )


class TestReadOutcome(unittest.TestCase):
    """Completeness, score, and in-band assessment from artifacts on disk."""

    def _make_run(
        self, tmp: Path, *, all_artifacts: bool, score: float | None, cost: float
    ) -> Path:
        names = (
            run._ARTIFACT_FILENAMES if all_artifacts else run._ARTIFACT_FILENAMES[:4]
        )
        for name in names:
            (tmp / name).write_text("x", encoding="utf-8")
        (tmp / "metrics.json").write_text(
            json.dumps({"is_error": False, "metrics": {"total_cost_usd": cost}}),
            encoding="utf-8",
        )
        if score is not None:
            (tmp / "eval.json").write_text(
                json.dumps({"task_score": score}), encoding="utf-8"
            )
        return tmp

    def test_complete_and_in_band(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = self._make_run(Path(d), all_artifacts=True, score=60.0, cost=3.5)
            out = run._read_outcome(tmp, band_floor=54.0, judge=True)
            self.assertTrue(out["complete"])
            self.assertTrue(out["in_band"])
            self.assertEqual(out["score"], 60.0)
            self.assertEqual(out["cost"], 3.5)

    def test_below_band_is_out_of_band(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = self._make_run(Path(d), all_artifacts=True, score=50.0, cost=1.0)
            out = run._read_outcome(tmp, band_floor=54.0, judge=True)
            self.assertFalse(out["in_band"])

    def test_missing_artifacts_is_incomplete(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            tmp = self._make_run(Path(d), all_artifacts=False, score=None, cost=1.0)
            out = run._read_outcome(tmp, band_floor=None, judge=False)
            self.assertFalse(out["complete"])
            self.assertEqual(out["artifacts_produced"], 4)

    def test_judge_off_ignores_score_for_band(self) -> None:
        with tempfile.TemporaryDirectory() as d:
            # A stale eval.json is present, but judge is off, so its score must be
            # ignored (not misattributed to this run) and completeness alone gates.
            tmp = self._make_run(Path(d), all_artifacts=True, score=99.0, cost=1.0)
            out = run._read_outcome(tmp, band_floor=54.0, judge=False)
            self.assertIsNone(out["score"])
            self.assertTrue(out["in_band"])


class TestPricingBasis(unittest.TestCase):
    def test_matches_final_model_hosting(self) -> None:
        runnable = [
            FrontierEntry(
                model="a", mean_score=1, mean_cost_per_task=1, hosting="Bedrock"
            ),
            FrontierEntry(
                model="b", mean_score=1, mean_cost_per_task=1, hosting="self-hosted"
            ),
        ]
        self.assertEqual(
            run._pricing_basis(runnable, {"selected_model": "a"}), "metered"
        )
        self.assertEqual(
            run._pricing_basis(runnable, {"selected_model": "b"}), "hardware-derived"
        )


if __name__ == "__main__":
    unittest.main()
