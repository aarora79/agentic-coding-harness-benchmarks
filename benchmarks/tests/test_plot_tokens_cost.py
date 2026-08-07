"""Tests for the faceted tokens+cost bar chart's data preparation.

The rendering is matplotlib (not unit-tested here); what matters is that
``_collect_rows`` reuses the doc generator's cost so the chart and the harness
doc agree, sorts by cost, parses the cost string, and drops rows with no
derivable cost rather than plotting a fake zero.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

_PATH = _SCRIPTS_DIR / "plot_tokens_cost.py"
_spec = importlib.util.spec_from_file_location("plot_tokens_cost", _PATH)
assert _spec is not None and _spec.loader is not None
tc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(tc)


class HumanTokensTest(unittest.TestCase):
    def test_scales(self) -> None:
        self.assertEqual(tc._human_tokens(950), "950")
        self.assertEqual(tc._human_tokens(12_000), "12K")
        self.assertEqual(tc._human_tokens(82_700_000), "83M")
        self.assertEqual(tc._human_tokens(1_200_000_000), "1.2B")


class CollectRowsTest(unittest.TestCase):
    def _rows(self, collected, cost_map):
        # Patch the reused gen_agent_report helpers with deterministic fakes.
        with mock.patch.object(tc.gen, "_collect", return_value=collected):
            with mock.patch.object(
                tc.gen, "_row_cost", side_effect=lambda r: cost_map[r["model"]]
            ):
                return tc._collect_rows(Path("/x"), "pi", "swe3", "repo")

    def test_sorted_by_cost_desc_and_cost_parsed(self) -> None:
        collected = [
            {"model": "cheap", "total_tokens": 10, "provider": "endpoint"},
            {"model": "dear", "total_tokens": 20, "provider": "bedrock"},
        ]
        cost_map = {
            "cheap": ("$2.50", "hardware-derived (g6e.12xlarge)"),
            "dear": ("$41.42", "metered (Bedrock)"),
        }
        rows = self._rows(collected, cost_map)
        self.assertEqual([r["model"] for r in rows], ["dear", "cheap"])
        self.assertEqual(rows[0]["cost"], 41.42)
        self.assertTrue(rows[0]["metered"])
        self.assertFalse(rows[1]["metered"])

    def test_rows_without_cost_or_tokens_are_dropped(self) -> None:
        collected = [
            {"model": "ok", "total_tokens": 100, "provider": "endpoint"},
            {"model": "no-cost", "total_tokens": 100, "provider": "endpoint"},
            {"model": "no-tokens", "total_tokens": 0, "provider": "endpoint"},
        ]
        cost_map = {
            "ok": ("$5.00", "hardware-derived (g6e.12xlarge)"),
            "no-cost": ("--", "hardware-derived"),
            "no-tokens": ("$1.00", "hardware-derived (g6e.12xlarge)"),
        }
        rows = self._rows(collected, cost_map)
        self.assertEqual([r["model"] for r in rows], ["ok"])


if __name__ == "__main__":
    unittest.main()
