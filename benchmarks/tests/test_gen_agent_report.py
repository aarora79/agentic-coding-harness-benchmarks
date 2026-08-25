"""Tests for the per-agent results-doc generator's cost logic.

The cost column is the error-prone part: a Bedrock run has a real metered bill,
while a self-hosted run has only a hardware-derived (GPU-time) estimate. Mixing
the two bases -- e.g. applying the GPU hourly rate to a Bedrock run -- produces a
fabricated dollar figure, so these tests pin the basis selection.
"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest import mock

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

_GEN_PATH = _SCRIPTS_DIR / "gen_agent_report.py"
_spec = importlib.util.spec_from_file_location("gen_agent_report", _GEN_PATH)
assert _spec is not None and _spec.loader is not None
gen = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gen)


class RunTotalsTest(unittest.TestCase):
    def test_sums_tokens_time_and_metered_cost(self) -> None:
        summary = {
            "tasks": [
                {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "latency_seconds": 30,
                    "total_cost_usd": 0.10,
                },
                {
                    "input_tokens": 5,
                    "output_tokens": 1,
                    "latency_seconds": 60,
                    "total_cost_usd": 0.20,
                },
            ]
        }
        totals = gen._run_totals(summary)
        self.assertEqual(totals["input_tokens"], 15)
        self.assertEqual(totals["output_tokens"], 3)
        self.assertEqual(totals["latency_seconds"], 90)
        self.assertAlmostEqual(totals["metered_cost"], 0.30)

    def test_total_tokens_includes_cache(self) -> None:
        # Total tokens processed must include cache-read + cache-write, not just
        # input+output -- else a heavily-cached Bedrock task (input_tokens ~2)
        # looks ~100x lighter than the work it actually did.
        summary = {
            "tasks": [
                {
                    "input_tokens": 2,
                    "output_tokens": 1000,
                    "cache_read_tokens": 180000,
                    "cache_write_tokens": 500,
                },
            ]
        }
        totals = gen._run_totals(summary)
        # 2 + 1000 + 180000 + 500
        self.assertEqual(totals["total_tokens"], 181502)
        # The 4 token types are also tracked separately for the breakdown columns.
        self.assertEqual(totals["input_tokens"], 2)
        self.assertEqual(totals["output_tokens"], 1000)
        self.assertEqual(totals["cache_read_tokens"], 180000)
        self.assertEqual(totals["cache_write_tokens"], 500)

    def test_total_tokens_partition_not_double_counted(self) -> None:
        # Self-hosted vLLM (issue #136): cache_read + cache_write == input_tokens,
        # so the cache is a PARTITION of input (already counted inside it). The
        # total must be input + output only, NOT input + output + cache (which was
        # the ~2x double-count bug).
        summary = {
            "tasks": [
                {
                    "input_tokens": 4_141_291,
                    "output_tokens": 23_657,
                    "cache_read_tokens": 4_070_208,
                    "cache_write_tokens": 71_083,
                },
            ]
        }
        totals = gen._run_totals(summary)
        self.assertEqual(totals["total_tokens"], 4_141_291 + 23_657)
        # The per-field breakdown columns are still tracked verbatim.
        self.assertEqual(totals["cache_read_tokens"], 4_070_208)
        self.assertEqual(totals["cache_write_tokens"], 71_083)

    def test_total_tokens_accepts_cache_creation_alias(self) -> None:
        # claude-code metrics use cache_creation_tokens for cache-write.
        summary = {
            "tasks": [
                {
                    "input_tokens": 5,
                    "output_tokens": 10,
                    "cache_read_tokens": 1000,
                    "cache_creation_tokens": 200,
                },
            ]
        }
        self.assertEqual(gen._run_totals(summary)["total_tokens"], 1215)

    def test_metered_cost_none_when_all_zero(self) -> None:
        # Self-hosted tasks report total_cost_usd 0/None -> no metered cost.
        summary = {"tasks": [{"latency_seconds": 30, "total_cost_usd": 0}]}
        self.assertIsNone(gen._run_totals(summary)["metered_cost"])


class RowCostTest(unittest.TestCase):
    def test_bedrock_uses_metered_bill_not_gpu_time(self) -> None:
        # A Bedrock run's cost is its summed metered bill.
        row = {"provider": "bedrock", "metered_cost": 0.63}
        cost, basis = gen._row_cost(row)
        self.assertEqual(cost, "$0.63")
        self.assertEqual(basis, "metered (Bedrock)")

    def test_bedrock_without_metered_cost_is_dash(self) -> None:
        # A bedrock run must never fall back to a hardware estimate.
        row = {"provider": "bedrock", "metered_cost": None}
        cost, basis = gen._row_cost(row)
        self.assertEqual(cost, "--")
        self.assertEqual(basis, "metered (Bedrock)")

    def test_endpoint_prices_all_processed_tokens_at_blended_rate(self) -> None:
        # Self-hosted: cost = blended $/token (from throughput sweep) x TOTAL
        # tokens processed. 1,000,000 tokens at 2e-6 $/token = $2.00, and the
        # instance name flows into the basis label.
        row = {"provider": "endpoint", "model": "some-model", "total_tokens": 1_000_000}
        with mock.patch.object(
            gen, "_blended_rate", return_value=(2e-6, "p5en.48xlarge")
        ):
            cost, basis = gen._row_cost(row)
        self.assertEqual(cost, "$2.00")
        self.assertEqual(basis, "hardware-derived (p5en.48xlarge)")

    def test_endpoint_without_throughput_summary_is_dash(self) -> None:
        # No performance-summary for the model -> no rate -> dash, not a guess.
        row = {"provider": "endpoint", "model": "unswept", "total_tokens": 1_000_000}
        with mock.patch.object(gen, "_blended_rate", return_value=None):
            cost, basis = gen._row_cost(row)
        self.assertEqual(cost, "--")
        self.assertEqual(basis, "hardware-derived")

    def test_endpoint_without_tokens_is_dash(self) -> None:
        row = {"provider": "endpoint", "model": "some-model", "total_tokens": 0}
        with mock.patch.object(gen, "_blended_rate", return_value=(2e-6, "g6e")):
            cost, basis = gen._row_cost(row)
        self.assertEqual(cost, "--")


if __name__ == "__main__":
    unittest.main()
