"""Tests for the /swe-auto deterministic routing core."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from swe_auto_router import (  # noqa: E402
    FrontierEntry,
    RouterError,
    SweAutoConfig,
    frontier_entries,
    load_config,
    next_tier,
    resolve_execution,
    runnable_entries,
    select_model,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# A small frontier fixture shaped like the real pareto-frontier JSON. Scores and
# costs are chosen so the band / cheapest logic has clear right answers.
_FRONTIER = {
    "combined_frontier_cross_hosting_directional": [
        {
            "model": "budget-a",
            "mean_score": 47.0,
            "mean_cost_per_task": 0.30,
            "hosting": "self-hosted",
            "n_scored": 5,
            "n_tasks": 5,
            "completed": "5/5",
        },
        {
            "model": "mid-b",
            "mean_score": 55.0,
            "mean_cost_per_task": 0.90,
            "hosting": "self-hosted",
            "n_scored": 5,
            "n_tasks": 5,
            "completed": "5/5",
        },
        {
            "model": "mid-cheap-partial",
            "mean_score": 60.0,
            "mean_cost_per_task": 0.50,
            "hosting": "self-hosted",
            "n_scored": 2,
            "n_tasks": 5,
            "completed": "2/5",
        },
        {
            "model": "top-c",
            "mean_score": 76.0,
            "mean_cost_per_task": 8.00,
            "hosting": "Bedrock",
            "n_scored": 5,
            "n_tasks": 5,
            "completed": "5/5",
        },
    ],
    "bedrock_frontier": [
        {
            "model": "top-c",
            "mean_score": 76.0,
            "mean_cost_per_task": 8.00,
            "hosting": "Bedrock",
            "n_scored": 5,
            "n_tasks": 5,
            "completed": "5/5",
        },
    ],
}


def _config(**overrides: object) -> SweAutoConfig:
    """Build a config from defaults with overrides (empty registry = all runnable)."""
    return SweAutoConfig.model_validate(overrides)


class TestNextTier(unittest.TestCase):
    """Escalation walks tiers toward the top and stops there."""

    def test_budget_escalates_to_workhorse(self) -> None:
        self.assertEqual(next_tier("budget"), "workhorse")

    def test_workhorse_escalates_to_frontier(self) -> None:
        self.assertEqual(next_tier("workhorse"), "frontier")

    def test_frontier_is_the_ceiling(self) -> None:
        self.assertIsNone(next_tier("frontier"))

    def test_unknown_tier_raises(self) -> None:
        with self.assertRaises(RouterError):
            next_tier("nope")


class TestFrontierEntries(unittest.TestCase):
    """Scope selects the right list and rejects unknown scopes."""

    def test_combined_scope_reads_the_combined_list(self) -> None:
        entries = frontier_entries(_FRONTIER, "combined")
        self.assertEqual(
            {e.model for e in entries},
            {"budget-a", "mid-b", "mid-cheap-partial", "top-c"},
        )

    def test_unknown_scope_raises(self) -> None:
        with self.assertRaises(RouterError):
            frontier_entries(_FRONTIER, "made-up")

    def test_missing_list_raises(self) -> None:
        with self.assertRaises(RouterError):
            frontier_entries(
                {"combined_frontier_cross_hosting_directional": []}, "bedrock-only"
            )


class TestSelectModel(unittest.TestCase):
    """The heart: tier -> band -> cheapest non-dominated clearing model."""

    def test_workhorse_picks_cheapest_clearing_full_model(self) -> None:
        # Floor 54: mid-b (55, full, $0.90) and mid-cheap-partial (60, $0.50) clear it.
        # Reliability gating prefers the full model even though it is pricier.
        entries = frontier_entries(_FRONTIER, "combined")
        sel = select_model(entries, "workhorse", _config())
        self.assertEqual(sel.selected_model, "mid-b")
        self.assertTrue(sel.clears_band)
        self.assertEqual(sel.band_floor, 54.0)

    def test_reliability_gating_off_takes_the_cheaper_partial_model(self) -> None:
        entries = frontier_entries(_FRONTIER, "combined")
        sel = select_model(entries, "workhorse", _config(reliability_gating=False))
        self.assertEqual(sel.selected_model, "mid-cheap-partial")

    def test_budget_picks_the_cheapest_clearing_the_low_bar(self) -> None:
        entries = frontier_entries(_FRONTIER, "combined")
        sel = select_model(entries, "budget", _config())
        self.assertEqual(sel.selected_model, "budget-a")  # 47 clears 47, cheapest

    def test_frontier_tier_takes_top_score_regardless_of_cost(self) -> None:
        entries = frontier_entries(_FRONTIER, "combined")
        sel = select_model(entries, "frontier", _config())
        self.assertEqual(sel.selected_model, "top-c")
        self.assertIsNone(sel.band_floor)

    def test_cheap_posture_lowers_the_bar(self) -> None:
        cfg = _config(
            budget_posture="cheap",
            tier_bands={"budget": 50.0, "workhorse": 54.0, "frontier": None},
        )
        entries = frontier_entries(_FRONTIER, "combined")
        # budget floor 50 - 5 = 45: budget-a (47) now clears and is cheapest.
        sel = select_model(entries, "budget", cfg)
        self.assertEqual(sel.selected_model, "budget-a")
        self.assertEqual(sel.band_floor, 45.0)

    def test_best_posture_raises_the_bar(self) -> None:
        cfg = _config(budget_posture="best")
        entries = frontier_entries(_FRONTIER, "combined")
        # workhorse 54 + 5 = 59: only mid-cheap-partial (60) and top-c (76) clear;
        # gating prefers full -> top-c.
        sel = select_model(entries, "workhorse", cfg)
        self.assertEqual(sel.band_floor, 59.0)
        self.assertEqual(sel.selected_model, "top-c")

    def test_no_model_clears_band_falls_back_and_flags(self) -> None:
        cfg = _config(tier_bands={"budget": 99.0, "workhorse": 99.0, "frontier": None})
        entries = frontier_entries(_FRONTIER, "combined")
        sel = select_model(entries, "budget", cfg)
        self.assertFalse(sel.clears_band)
        self.assertEqual(sel.selected_model, "top-c")  # best effort = highest score
        self.assertIn("does NOT clear", sel.rationale)

    def test_empty_candidates_raises(self) -> None:
        with self.assertRaises(RouterError):
            select_model([], "budget", _config())


class TestExecutionResolution(unittest.TestCase):
    """Frontier is the selectable universe; execution is a thin recipe layer."""

    def _entry(self, model: str, hosting: str) -> FrontierEntry:
        return FrontierEntry(
            model=model,
            mean_score=60.0,
            mean_cost_per_task=1.0,
            hosting=hosting,
            n_scored=5,
            n_tasks=5,
        )

    def test_builtin_bedrock_recipe(self) -> None:
        ex = resolve_execution(_config(), self._entry("claude-opus-5", "Bedrock"))
        self.assertIsNotNone(ex)
        assert ex is not None
        self.assertEqual(ex.provider, "bedrock")
        self.assertEqual(ex.model, "us.anthropic.claude-opus-5")

    def test_unknown_bedrock_claude_slug_is_derived(self) -> None:
        ex = resolve_execution(_config(), self._entry("claude-future-9", "Bedrock"))
        assert ex is not None
        self.assertEqual(ex.model, "us.anthropic.claude-future-9")

    def test_self_hosted_without_override_is_not_runnable(self) -> None:
        self.assertIsNone(
            resolve_execution(_config(), self._entry("glm-5.2", "self-hosted"))
        )

    def test_override_wins_over_builtin(self) -> None:
        cfg = _config(
            model_execution={
                "claude-opus-5": {"provider": "bedrock", "model": "custom-profile-id"}
            }
        )
        ex = resolve_execution(cfg, self._entry("claude-opus-5", "Bedrock"))
        assert ex is not None
        self.assertEqual(ex.model, "custom-profile-id")

    def test_runnable_entries_filters_to_launchable(self) -> None:
        # Fixture: budget-a/mid-b/mid-cheap-partial are self-hosted (no endpoint),
        # top-c is Bedrock but slug is not "claude-*", so none are runnable by default.
        entries = frontier_entries(_FRONTIER, "combined")
        self.assertEqual(runnable_entries(entries, _config()), [])
        # Add an endpoint for one self-hosted model and it becomes selectable.
        cfg = _config(
            model_execution={
                "mid-b": {
                    "provider": "endpoint",
                    "model": "mid-b",
                    "endpoint": "http://x:8000",
                }
            }
        )
        runnable = runnable_entries(entries, cfg)
        self.assertEqual([e.model for e in runnable], ["mid-b"])


class TestLoadConfig(unittest.TestCase):
    """Config loading, overrides, and semantic validation."""

    def test_defaults_when_no_file(self) -> None:
        cfg = load_config(None)
        self.assertEqual(cfg.router_model, "claude-opus-5")
        self.assertEqual(cfg.harness, "pi")
        self.assertEqual(cfg.agent, "pi")

    def test_cli_overrides_win(self) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False, encoding="utf-8"
        ) as handle:
            handle.write("harness: pi\nbudget_posture: cheap\n")
            cfg_path = Path(handle.name)
        cfg = load_config(cfg_path, {"budget_posture": "best"})
        self.assertEqual(cfg.harness, "pi")  # from file
        self.assertEqual(cfg.budget_posture, "best")  # CLI wins
        self.assertEqual(cfg.agent, "pi")

    def test_invalid_harness_raises(self) -> None:
        with self.assertRaises(RouterError):
            load_config(None, {"harness": "emacs"})

    def test_invalid_scope_raises(self) -> None:
        with self.assertRaises(RouterError):
            load_config(None, {"frontier_scope": "everything"})

    def test_missing_file_raises(self) -> None:
        with self.assertRaises(RouterError):
            load_config(Path(tempfile.gettempdir()) / "swe-auto-does-not-exist.yaml")

    def test_pricing_basis_from_hosting(self) -> None:
        by_model = {e.model: e for e in frontier_entries(_FRONTIER, "combined")}
        self.assertEqual(by_model["top-c"].pricing_basis, "metered")
        self.assertEqual(by_model["budget-a"].pricing_basis, "hardware-derived")


class TestRealCommittedFrontier(unittest.TestCase):
    """The selection core reads the actual committed pi/swe3 frontier JSON."""

    def test_frontier_tier_picks_the_top_committed_model(self) -> None:
        frontier_path = _REPO_ROOT / "docs" / "metrics" / "pareto-frontier-pi-swe3.json"
        frontier = json.loads(frontier_path.read_text(encoding="utf-8"))
        entries = frontier_entries(frontier, "combined")
        self.assertTrue(entries, "combined frontier should be non-empty")
        sel = select_model(entries, "frontier", _config())
        # claude-opus-5 tops the committed pi/swe3 combined frontier.
        self.assertEqual(sel.selected_model, "claude-opus-5")


if __name__ == "__main__":
    unittest.main()
