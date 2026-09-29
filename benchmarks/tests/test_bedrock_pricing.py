"""Tests for the Bedrock price table used to derive codex run costs.

codex exec reports token counts but no billed cost, so the harness prices a
run locally. These cover the rate lookup (including inference-profile
prefixes) and the fresh-vs-cached token contract the caller must honour.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

from bedrock_pricing import PRICES, PRICES_AS_OF, cost_usd  # noqa: E402


class CostUsdTest(unittest.TestCase):
    def test_known_model_prices_each_token_class(self) -> None:
        # terra: input 4.00, output 18.00, cache_read 0.40, cache_write 5.00.
        cost = cost_usd(
            "openai.gpt-5.6-terra",
            input_tokens=1_000_000,
            output_tokens=1_000_000,
            cache_read_tokens=1_000_000,
            cache_write_tokens=1_000_000,
        )
        self.assertAlmostEqual(cost, 4.00 + 18.00 + 0.40 + 5.00, places=6)

    def test_unknown_model_returns_none_not_zero(self) -> None:
        # A silent 0 would look like a free run on the cost/quality frontier.
        self.assertIsNone(cost_usd("not-a-model", 100, 100))

    def test_inference_profile_prefix_is_stripped(self) -> None:
        bare = cost_usd("openai.gpt-5.6-luna", 1000, 1000)
        for prefix in ("us.", "global.", "eu.", "ap."):
            self.assertEqual(cost_usd(f"{prefix}openai.gpt-5.6-luna", 1000, 1000), bare)

    def test_zero_tokens_costs_nothing(self) -> None:
        self.assertEqual(cost_usd("openai.gpt-5.6-luna", 0, 0, 0, 0), 0.0)

    def test_cache_read_is_cheaper_than_fresh_input(self) -> None:
        # The whole point of passing fresh (non-cached) input separately.
        fresh = cost_usd("openai.gpt-5.6-terra", 1_000_000, 0)
        cached = cost_usd("openai.gpt-5.6-terra", 0, 0, cache_read_tokens=1_000_000)
        assert fresh is not None and cached is not None
        self.assertLess(cached, fresh)

    def test_price_table_rows_are_complete(self) -> None:
        # input and output are always required; a caching-incapable model
        # carries no cache rate at all (see test_cached_tokens_against_...).
        for model, rates in PRICES.items():
            for key in ("input", "output"):
                self.assertIn(key, rates, f"{model} missing {key}")
            for key, rate in rates.items():
                self.assertGreaterEqual(rate, 0.0, f"{model}.{key} is negative")

    def test_version_suffix_and_instruct_alias_resolve(self) -> None:
        # The Bedrock id, the LiteLLM alias the harness records, and the bare
        # key are the same model. A miss here reads as a free run.
        bare = cost_usd("qwen.qwen3-coder-30b-a3b", 1_000_000, 1_000_000)
        self.assertAlmostEqual(bare, 0.1545 + 0.6180, places=6)
        for spelling in (
            "qwen.qwen3-coder-30b-a3b-v1:0",
            "qwen.qwen3-coder-30b-a3b-instruct",
            "us.qwen.qwen3-coder-30b-a3b-v1:0",
        ):
            self.assertEqual(cost_usd(spelling, 1_000_000, 1_000_000), bare)

    def test_cached_tokens_against_an_uncached_model_returns_none(self) -> None:
        # Bedrock refuses a cachePoint for Qwen, so a non-zero cached count is
        # a measurement bug. Pricing it at 0 would understate the bill and look
        # exactly like a genuinely cheap run.
        priced = cost_usd("qwen.qwen3-coder-30b-a3b", 1000, 1000)
        self.assertIsNotNone(priced)
        self.assertIsNone(
            cost_usd("qwen.qwen3-coder-30b-a3b", 1000, 1000, cache_read_tokens=500)
        )
        self.assertIsNone(
            cost_usd("qwen.qwen3-coder-30b-a3b", 1000, 1000, cache_write_tokens=500)
        )

    def test_prices_carry_an_as_of_date(self) -> None:
        # Rates move; an undated table cannot be audited against the source.
        self.assertRegex(PRICES_AS_OF, r"^\d{4}-\d{2}-\d{2}$")


if __name__ == "__main__":
    unittest.main()


class AnthropicRatesTest(unittest.TestCase):
    """Claude rows: id spellings, the Regional/Global split, and provenance."""

    def test_haiku_profile_id_with_date_and_version_resolves(self) -> None:
        # The id the Strands and Claude Code runs record for Haiku 4.5.
        cost = cost_usd("us.anthropic.claude-haiku-4-5-20251001-v1:0", 1_000_000, 0)
        self.assertAlmostEqual(cost, 1.10, places=6)

    def test_context_window_tag_is_ignored(self) -> None:
        self.assertEqual(
            cost_usd("us.anthropic.claude-opus-4-8[1m]", 1_000_000, 1_000_000),
            cost_usd("anthropic.claude-opus-4-8", 1_000_000, 1_000_000),
        )

    def test_bare_version_suffix_resolves(self) -> None:
        self.assertIsNotNone(cost_usd("us.anthropic.claude-opus-4-6-v1", 1, 1))

    def test_global_profile_uses_the_global_rate(self) -> None:
        regional = cost_usd("us.anthropic.claude-sonnet-5", 1_000_000, 0)
        global_ = cost_usd("global.anthropic.claude-sonnet-5", 1_000_000, 0)
        self.assertEqual((regional, global_), (2.20, 2.00))

    def test_every_claude_row_has_a_global_twin(self) -> None:
        regional = {k for k in PRICES if k.startswith("anthropic.")}
        global_ = {k[len("global.") :] for k in PRICES if k.startswith("global.")}
        self.assertEqual(regional, global_)

    def test_every_claude_row_prices_the_cache(self) -> None:
        for key, rates in PRICES.items():
            if "anthropic." in key:
                self.assertEqual(
                    set(rates), {"input", "output", "cache_read", "cache_write"}, key
                )

    def test_anthropic_rates_carry_an_as_of_date(self) -> None:
        from bedrock_pricing import ANTHROPIC_PRICES_AS_OF

        self.assertRegex(ANTHROPIC_PRICES_AS_OF, r"^\d{4}-\d{2}-\d{2}$")
