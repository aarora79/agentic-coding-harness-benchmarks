"""Tests for the swe-router rubric: policy, mapping, parsing and consolidation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import eval_swe_router as ev  # noqa: E402
import swe_router_rubric as r  # noqa: E402


def _scores(**overrides: int) -> dict[str, int]:
    """All six dimensions at 0, with overrides."""
    base = {d: 0 for d in r.DIMENSIONS}
    base.update(overrides)
    return base


def _judgment(confidence: str = "high", **overrides: int) -> dict:
    """A parsed judgment as extract_judgment returns it."""
    return {
        "scores": _scores(**overrides),
        "evidence": {},
        "confidence": confidence,
        "summary": "s",
    }


def _reply(scores: dict[str, int], confidence: str = "high") -> str:
    """An agent reply carrying one fenced rubric block."""
    body = {
        "scores": {d: {"score": v, "evidence": f"e-{d}"} for d, v in scores.items()},
        "confidence": confidence,
        "summary": "needs a passthrough",
    }
    return f"I read the repo.\n```json\n{json.dumps(body)}\n```"


def _write_policy(data: dict) -> Path:
    """Write a policy dict to a temp file."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
    json.dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


class PolicyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = r.load_policy()
        self.raw = json.loads(r.DEFAULT_POLICY.read_text(encoding="utf-8"))

    def test_shipped_policy_loads(self) -> None:
        self.assertEqual(self.policy.required_quality.by_blast_radius[1], 70)

    def test_every_reachable_bar_has_a_meaning(self) -> None:
        rq = self.policy.required_quality
        bars = {
            q + bump
            for q in rq.by_blast_radius.values()
            for bump in (0, rq.add_when_verification_is_2)
        }
        self.assertEqual({str(int(b)) for b in bars} - set(rq.meaning), set())

    def test_missing_blast_radius_level_is_rejected(self) -> None:
        self.raw["required_quality"]["by_blast_radius"].pop("2")
        with self.assertRaisesRegex(r.RubricError, "by_blast_radius"):
            r.load_policy(_write_policy(self.raw))

    def test_gap_between_buckets_is_rejected(self) -> None:
        self.raw["difficulty"]["buckets"]["moderate"] = [3, 3]
        with self.assertRaisesRegex(r.RubricError, "must start at"):
            r.load_policy(_write_policy(self.raw))

    def test_buckets_must_cover_the_full_sum(self) -> None:
        self.raw["difficulty"]["buckets"]["very_hard"] = [6, 7]
        with self.assertRaisesRegex(r.RubricError, "cover"):
            r.load_policy(_write_policy(self.raw))

    def test_missing_policy_file_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(r.RubricError, "no routing policy"):
            r.load_policy(Path("/nonexistent/routing-policy.json"))


class MappingTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = r.load_policy()

    def test_blast_radius_sets_the_bar(self) -> None:
        self.assertEqual(r.required_quality(_scores(blast_radius=2), self.policy), 75)

    def test_unverifiable_work_raises_the_bar(self) -> None:
        scores = _scores(blast_radius=1, verification=2)
        self.assertEqual(r.required_quality(scores, self.policy), 75)

    def test_difficulty_dimensions_never_move_the_bar(self) -> None:
        hard = _scores(hidden_contract=2, silent_invariant=2, ambiguity=2)
        self.assertEqual(r.required_quality(hard, self.policy), 60)

    def test_bar_dimensions_never_move_the_bucket(self) -> None:
        scores = _scores(blast_radius=2, verification=2)
        self.assertEqual(r.bucket(scores, self.policy), "easy")

    def test_bucket_edges(self) -> None:
        cases = {1: "easy", 2: "moderate", 5: "hard", 6: "very_hard"}
        got = {}
        for total in cases:
            dims = dict.fromkeys(self.policy.difficulty.dimensions, 0)
            for d in list(dims)[: total // 2]:
                dims[d] = 2
            if total % 2:
                dims[list(dims)[total // 2]] = 1
            got[total] = r.bucket(_scores(**dims), self.policy)
        self.assertEqual(got, cases)


class ExtractTest(unittest.TestCase):
    def test_reads_a_fenced_block(self) -> None:
        out = r.extract_judgment(_reply(_scores(blast_radius=2)))
        self.assertEqual(
            (out["scores"]["blast_radius"], out["evidence"]["ambiguity"]),
            (2, "e-ambiguity"),
        )

    def test_takes_the_last_valid_block(self) -> None:
        text = _reply(_scores(ambiguity=1)) + "\n" + _reply(_scores(ambiguity=2))
        self.assertEqual(r.extract_judgment(text)["scores"]["ambiguity"], 2)

    def test_reads_a_bare_object_without_a_fence(self) -> None:
        body = _reply(_scores(verification=1)).split("```json\n")[1].split("\n```")[0]
        self.assertEqual(
            r.extract_judgment("Answer: " + body)["scores"]["verification"], 1
        )

    def test_rejects_a_score_off_the_scale(self) -> None:
        with self.assertRaisesRegex(r.RubricError, "0, 1 or 2"):
            r.extract_judgment(_reply(_scores(ambiguity=3)))

    def test_rejects_a_boolean_score(self) -> None:
        with self.assertRaisesRegex(r.RubricError, "0, 1 or 2"):
            r.extract_judgment(_reply({**_scores(), "ambiguity": True}))

    def test_rejects_a_missing_dimension(self) -> None:
        scores = _scores()
        scores.pop("verification")
        with self.assertRaisesRegex(r.RubricError, "exactly"):
            r.extract_judgment(_reply(scores))

    def test_rejects_an_unknown_confidence(self) -> None:
        with self.assertRaisesRegex(r.RubricError, "confidence"):
            r.extract_judgment(_reply(_scores(), confidence="certain"))


class ConsolidateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.policy = r.load_policy()

    def test_lower_median_keeps_scores_on_the_scale(self) -> None:
        runs = [_judgment(ambiguity=1), _judgment(ambiguity=2)]
        out = r.consolidate(runs, self.policy)
        self.assertEqual(out["scores"]["ambiguity"], 1)

    def test_disagreeing_repeats_are_flagged(self) -> None:
        runs = [_judgment(blast_radius=1), _judgment(blast_radius=2)]
        out = r.consolidate(runs, self.policy)
        self.assertEqual(
            (out["quality_unanimous"], out["quality_seen"]), (False, [70.0, 75.0])
        )

    def test_quality_and_bucket_come_from_the_consolidated_scores(self) -> None:
        runs = [_judgment(blast_radius=2, hidden_contract=2, ambiguity=2)] * 3
        out = r.consolidate(runs, self.policy)
        self.assertEqual((out["required_quality"], out["bucket"]), (75, "hard"))

    def test_no_judgments_is_an_error(self) -> None:
        with self.assertRaisesRegex(r.RubricError, "no successful"):
            r.consolidate([], self.policy)


class PromptTest(unittest.TestCase):
    def test_prompt_carries_rubric_task_and_every_dimension(self) -> None:
        prompt = r.build_prompt("t-1", "do it", Path("/tmp/clone"), "RUBRIC-TEXT")  # nosec B108
        self.assertTrue(
            all(
                s in prompt for s in ("RUBRIC-TEXT", "t-1", "/tmp/clone", *r.DIMENSIONS)
            )  # nosec B108
        )

    def test_prompt_never_names_a_price_or_model(self) -> None:
        # The model describes the task; the policy prices it.
        prompt = r.build_prompt("t", "x", Path("/c"), r.DEFAULT_RUBRIC.read_text())
        self.assertFalse(any(w in prompt for w in ("required_quality", "$", "claude-")))


class ReplayRubricInputsTest(unittest.TestCase):
    def _inputs(self, tasks: dict) -> Path:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"mode": "rubric", "judged_by": {"model": "m"}, "tasks": tasks}, tmp)
        tmp.close()
        return Path(tmp.name)

    def test_regroups_scores_by_bucket_and_sets_floors(self) -> None:
        path = self._inputs({"a": {"required_quality": 75, "bucket": "very_hard"}})
        results = {"m1": {"a": {"complexity": "trivial", "score": 80}}}
        floors, columns, meta = ev._apply_rubric_inputs(path, [{"id": "a"}], results)
        self.assertEqual(
            (floors["a"], columns["a"], results["m1"]["a"]["complexity"], meta["mode"]),
            (75.0, "high", "high", "rubric"),
        )

    def test_rejects_a_floor_mode_file(self) -> None:
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        json.dump({"mode": "floor", "tasks": {}}, tmp)
        tmp.close()
        with self.assertRaisesRegex(SystemExit, "not a rubric pass"):
            ev._apply_rubric_inputs(Path(tmp.name), [], {})

    def test_rejects_a_file_missing_a_task(self) -> None:
        with self.assertRaisesRegex(SystemExit, "missing 1 task"):
            ev._apply_rubric_inputs(self._inputs({}), [{"id": "a"}], {})


if __name__ == "__main__":
    unittest.main()
