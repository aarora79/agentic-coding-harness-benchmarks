"""Tests for the vended models.json generator."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
_REPO_ROOT = _SCRIPTS_DIR.parent.parent
sys.path.insert(0, str(_SCRIPTS_DIR))

_spec = importlib.util.spec_from_file_location(
    "build_vended_models", _SCRIPTS_DIR / "build_vended_models.py"
)
bvm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bvm)

_VEND_DIR = _REPO_ROOT / "vend" / "model-router"


def _frontier(**overrides) -> dict:
    """Build a minimal frontier JSON shaped like the real one."""
    data = {
        "harness": "omp",
        "skill": "swe3",
        "repo": "mcp-gateway-registry-v2",
        "all_models": [
            {
                "model": "big",
                "mean_score": 80.0,
                "mean_cost_per_task": 10.0,
                "hosting": "Bedrock",
                "n_scored": 21,
                "n_tasks": 21,
                "excluded_tasks": [],
            },
            {
                "model": "small",
                "mean_score": 60.0,
                "mean_cost_per_task": 1.0,
                "hosting": "self-hosted",
                "n_scored": 20,
                "n_tasks": 21,
                "excluded_tasks": ["a-task"],
            },
        ],
        "combined_frontier_cross_hosting_directional": [{"model": "small"}],
        "bedrock_frontier": [{"model": "big"}],
        "self_hosted_frontier": [{"model": "small"}],
    }
    data.update(overrides)
    return data


def _write(data: dict) -> Path:
    """Write a frontier dict to a temp file and return its path."""
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".json", delete=False, encoding="utf-8"
    )
    json.dump(data, tmp)
    tmp.close()
    return Path(tmp.name)


class BuildTest(unittest.TestCase):
    def test_includes_every_model_not_only_the_frontier(self) -> None:
        # The skill filters to what the user's assistant offers before ranking,
        # and that set may contain no frontier model at all. Shipping only the
        # frontier would leave it mute for those users.
        out = bvm.build(_write(_frontier()), _REPO_ROOT)
        self.assertEqual({m["model"] for m in out["models"]}, {"big", "small"})

    def test_frontier_membership_is_an_annotation(self) -> None:
        out = bvm.build(_write(_frontier()), _REPO_ROOT)
        by = {m["model"]: m for m in out["models"]}
        self.assertTrue(by["small"]["on_combined_frontier"])
        self.assertFalse(by["big"]["on_combined_frontier"])
        # big is on the Bedrock frontier even though it is off the combined one.
        self.assertTrue(by["big"]["on_hosting_frontier"])

    def test_models_are_ordered_by_score_descending(self) -> None:
        out = bvm.build(_write(_frontier()), _REPO_ROOT)
        scores = [m["score"] for m in out["models"]]
        self.assertEqual(scores, sorted(scores, reverse=True))

    def test_incomplete_runs_stay_visible(self) -> None:
        # A mean over fewer tasks should not be averaged into silence.
        out = bvm.build(_write(_frontier()), _REPO_ROOT)
        small = next(m for m in out["models"] if m["model"] == "small")
        self.assertEqual((small["tasks_completed"], small["tasks_total"]), (20, 21))
        self.assertEqual(small["excluded_tasks"], ["a-task"])

    def test_provenance_carries_the_measurement_context(self) -> None:
        # A vended file has no reader who knows this repo, so the context
        # travels with the data.
        out = bvm.build(_write(_frontier()), _REPO_ROOT)
        p = out["provenance"]
        self.assertEqual(p["harness"], "omp")
        self.assertEqual(p["skill"], "swe3")
        self.assertEqual(p["dataset"], "mcp-gateway-registry-v2")
        self.assertTrue(p["measured_on"])
        self.assertIn("model", p["judge"])

    def test_cost_basis_is_explained_for_both_hostings(self) -> None:
        out = bvm.build(_write(_frontier()), _REPO_ROOT)
        basis = out["measurement_basis"]["cost_basis"]
        self.assertIn("Bedrock", basis)
        self.assertIn("self-hosted", basis)

    def test_missing_source_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(SystemExit, "no frontier JSON"):
            bvm.build(Path("/nope/absent.json"), _REPO_ROOT)

    def test_empty_source_is_a_clear_error(self) -> None:
        with self.assertRaisesRegex(SystemExit, "no all_models"):
            bvm.build(_write(_frontier(all_models=[])), _REPO_ROOT)


class CommittedArtifactTest(unittest.TestCase):
    """The vended files are committed, so they are checked like any other input."""

    def test_committed_models_json_matches_the_generator(self) -> None:
        # Guards the staleness trap: opus once moved $7.63 -> $11.95 with every
        # score unchanged, so a drifted copy looks perfectly plausible.
        payload = bvm.build(bvm.DEFAULT_SOURCE, _REPO_ROOT)
        expected = json.dumps(payload, indent=2) + "\n"
        self.assertEqual(
            bvm.DEFAULT_OUT.read_text(encoding="utf-8"),
            expected,
            "vend/model-router/models.json is stale; run build_vended_models.py",
        )

    def test_source_commit_tracks_the_frontier_not_head(self) -> None:
        # Stamping HEAD would make the file differ after every unrelated commit
        # and turn --check into noise. It must identify the data's version.
        payload = bvm.build(bvm.DEFAULT_SOURCE, _REPO_ROOT)
        stamped = payload["provenance"]["source_commit"]
        head = subprocess.run(
            ["git", "-C", str(_REPO_ROOT), "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        last_touch = subprocess.run(
            [
                "git",
                "-C",
                str(_REPO_ROOT),
                "log",
                "-1",
                "--format=%h",
                "--",
                str(bvm.DEFAULT_SOURCE.relative_to(_REPO_ROOT)),
            ],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        self.assertEqual(stamped, last_touch)
        if head != last_touch:
            self.assertNotEqual(stamped, head)

    def test_vend_dir_has_exactly_the_four_portable_files(self) -> None:
        # The portability contract: the skill must work in a directory holding
        # only these. An extra file is a dependency someone will start relying on.
        self.assertEqual(
            sorted(p.name for p in _VEND_DIR.iterdir()),
            ["README.md", "SKILL.md", "model-aliases.json", "models.json"],
        )

    def test_every_model_has_an_alias_entry(self) -> None:
        # A model with no aliases can never be matched against an assistant's
        # list, so it is invisible to the skill that ships beside it.
        models = {m["model"] for m in json.loads(bvm.DEFAULT_OUT.read_text())["models"]}
        aliases = json.loads((_VEND_DIR / "model-aliases.json").read_text())["aliases"]
        self.assertEqual(models - set(aliases), set())

    def test_every_alias_entry_names_a_real_model(self) -> None:
        models = {m["model"] for m in json.loads(bvm.DEFAULT_OUT.read_text())["models"]}
        aliases = json.loads((_VEND_DIR / "model-aliases.json").read_text())["aliases"]
        self.assertEqual(set(aliases) - models, set())

    def test_aliases_are_unambiguous_across_models(self) -> None:
        # Two models sharing a normalized alias would make matching a coin flip.
        aliases = json.loads((_VEND_DIR / "model-aliases.json").read_text())["aliases"]
        # Duplicates inside one model are harmless -- "claude-opus-5" and
        # "Claude Opus 5" normalize to the same key and both mean that model.
        # A key shared by two DIFFERENT models makes matching a coin flip.
        seen: dict[str, str] = {}
        for model, names in aliases.items():
            for name in names:
                key = name.lower().replace("-", "").replace("_", "").replace(" ", "")
                self.assertEqual(
                    seen.setdefault(key, model),
                    model,
                    f"alias {name!r} is claimed by {seen[key]} and {model}",
                )

    def test_skill_does_not_reference_the_benchmark_repo_internals(self) -> None:
        # Portability: the vended skill must not tell a consumer to look at a
        # path that only exists inside this repository.
        text = (_VEND_DIR / "SKILL.md").read_text(encoding="utf-8")
        for path in ("benchmarks/", "docs/metrics/", "run-swe-headless"):
            self.assertNotIn(path, text, f"SKILL.md references {path}")


if __name__ == "__main__":
    unittest.main()
