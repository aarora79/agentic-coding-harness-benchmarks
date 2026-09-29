"""Amazon Bedrock price table and cost helpers for the benchmark harness.

Used by the codex and strands agent paths to derive total_cost_usd from token
counts, since neither reports a billed cost itself, and as the fallback for any
agent that reports none.

Provenance of the rates:
- Rates were read directly from https://aws.amazon.com/bedrock/pricing/ on the
  date in ``PRICES_AS_OF``.
- Tier: Standard (on-demand). For the openai.* rows this is the Global CRIS
  (cross-region inference, global profile) Long Context Window (1M) table, the
  tier codex exec uses when it routes through bedrock-mantle; the run token
  counts confirmed it (all tasks exceeded 272K input tokens).
- Cache write is the 30-minute TTL rate for the openai.* rows.
- The anthropic.* rows come from the AWS Price List API (service
  AmazonBedrockFoundationModels, us-east-1, OnDemand) on the date in
  ``ANTHROPIC_PRICES_AS_OF``. Each model has a Regional row (plain key) and a
  Global cross-region row (``global.`` key); cache write is the 5-minute TTL
  rate. Re-read them with ``aws pricing get-products --region us-east-1
  --service-code AmazonBedrockFoundationModels`` filtered on ``servicename``.

Not every model on Bedrock supports prompt caching. Qwen does not: a Converse
call carrying a ``cachePoint`` block is rejected with ``AccessDeniedException:
You invoked an unsupported model or your request did not allow prompt
caching``, and the pricing page publishes only input and output columns for
those models. Such a row omits ``cache_read`` / ``cache_write`` entirely, and
``cost_usd`` returns None if a caller ever reports cached tokens against it,
rather than pricing them at zero and understating the bill.

All prices are per 1M tokens in USD.

Public API:
    cost_usd(model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
    PRICES, PRICES_AS_OF, ANTHROPIC_PRICES_AS_OF
"""

from __future__ import annotations

import re

PRICES_AS_OF = "2026-09-11"
# The Anthropic rows were read from the AWS Price List API on this date.
ANTHROPIC_PRICES_AS_OF = "2026-09-29"

# USD per 1M tokens — Global CRIS, Long Context Window (1M), Standard tier.
# Sourced from https://aws.amazon.com/bedrock/pricing/ on PRICES_AS_OF.
PRICES: dict[str, dict[str, float]] = {
    # GPT-5.6 Terra — high-capability variant
    "openai.gpt-5.6-terra": {
        "input": 4.00,
        "cache_write": 5.00,
        "cache_read": 0.40,
        "output": 18.00,
    },
    # GPT-5.6 Luna — cost-efficient variant
    "openai.gpt-5.6-luna": {
        "input": 0.40,
        "cache_write": 0.50,
        "cache_read": 0.04,
        "output": 1.80,
    },
    # Kimi K3 — Global CRIS, Standard tier.
    "moonshotai.kimi-k3": {
        "input": 3.00,
        "cache_write": 3.75,
        "cache_read": 0.30,
        "output": 15.00,
    },
    # Qwen3 Coder 30B A3B — Standard tier. No cache keys: Bedrock refuses a
    # cachePoint for this family, so a cached-token count here is a bug, not a
    # discount. Flex and Batch are both $0.0773 / $0.3090, Priority is
    # $0.2704 / $1.0815, if a run ever uses another tier.
    "qwen.qwen3-coder-30b-a3b": {
        "input": 0.1545,
        "output": 0.6180,
    },
    # Anthropic Claude -- AWS Price List API, service AmazonBedrockFoundationModels,
    # us-east-1, OnDemand, read on ANTHROPIC_PRICES_AS_OF. The plain key is the
    # Regional rate, which every in-region and geo cross-region id pays
    # (``us.``/``eu.``/``ap.``/bare -- all the committed runs use ``us.``). The
    # ``global.``-prefixed key is the Global cross-region rate, 10% lower, used
    # only for ``global.`` ids (see _rates). Cache write is the default 5-minute
    # TTL rate, the TTL Claude Code and the Strands runner use.
    # Claude Haiku 4.5 -- Regional.
    "anthropic.claude-haiku-4-5": {
        "input": 1.1,
        "cache_write": 1.375,
        "cache_read": 0.11,
        "output": 5.5,
    },
    # Claude Haiku 4.5 -- Global cross-region.
    "global.anthropic.claude-haiku-4-5": {
        "input": 1.0,
        "cache_write": 1.25,
        "cache_read": 0.1,
        "output": 5.0,
    },
    # Claude Opus 4.5 -- Regional.
    "anthropic.claude-opus-4-5": {
        "input": 5.5,
        "cache_write": 6.875,
        "cache_read": 0.55,
        "output": 27.5,
    },
    # Claude Opus 4.5 -- Global cross-region.
    "global.anthropic.claude-opus-4-5": {
        "input": 5.0,
        "cache_write": 6.25,
        "cache_read": 0.5,
        "output": 25.0,
    },
    # Claude Opus 4.6 -- Regional.
    "anthropic.claude-opus-4-6": {
        "input": 5.5,
        "cache_write": 6.875,
        "cache_read": 0.55,
        "output": 27.5,
    },
    # Claude Opus 4.6 -- Global cross-region.
    "global.anthropic.claude-opus-4-6": {
        "input": 5.0,
        "cache_write": 6.25,
        "cache_read": 0.5,
        "output": 25.0,
    },
    # Claude Opus 4.7 -- Regional.
    "anthropic.claude-opus-4-7": {
        "input": 5.5,
        "cache_write": 6.875,
        "cache_read": 0.55,
        "output": 27.5,
    },
    # Claude Opus 4.7 -- Global cross-region.
    "global.anthropic.claude-opus-4-7": {
        "input": 5.0,
        "cache_write": 6.25,
        "cache_read": 0.5,
        "output": 25.0,
    },
    # Claude Opus 4.8 -- Regional.
    "anthropic.claude-opus-4-8": {
        "input": 5.5,
        "cache_write": 6.875,
        "cache_read": 0.55,
        "output": 27.5,
    },
    # Claude Opus 4.8 -- Global cross-region.
    "global.anthropic.claude-opus-4-8": {
        "input": 5.0,
        "cache_write": 6.25,
        "cache_read": 0.5,
        "output": 25.0,
    },
    # Claude Opus 5 -- Regional.
    "anthropic.claude-opus-5": {
        "input": 5.5,
        "cache_write": 6.875,
        "cache_read": 0.55,
        "output": 27.5,
    },
    # Claude Opus 5 -- Global cross-region.
    "global.anthropic.claude-opus-5": {
        "input": 5.0,
        "cache_write": 6.25,
        "cache_read": 0.5,
        "output": 25.0,
    },
    # Claude Sonnet 5 -- Regional.
    "anthropic.claude-sonnet-5": {
        "input": 2.2,
        "cache_write": 2.75,
        "cache_read": 0.22,
        "output": 11.0,
    },
    # Claude Sonnet 5 -- Global cross-region.
    "global.anthropic.claude-sonnet-5": {
        "input": 2.0,
        "cache_write": 2.5,
        "cache_read": 0.2,
        "output": 10.0,
    },
    # Claude Fable 5.1 -- Regional.
    "anthropic.claude-fable-5-1": {
        "input": 11.0,
        "cache_write": 13.75,
        "cache_read": 0.275,
        "output": 55.0,
    },
    # Claude Fable 5.1 -- Global cross-region.
    "global.anthropic.claude-fable-5-1": {
        "input": 10.0,
        "cache_write": 12.5,
        "cache_read": 0.25,
        "output": 50.0,
    },
    # Claude Opus 5.5 -- Regional.
    "anthropic.claude-opus-5-5": {
        "input": 4.4,
        "cache_write": 5.5,
        "cache_read": 0.22,
        "output": 22.0,
    },
    # Claude Opus 5.5 -- Global cross-region.
    "global.anthropic.claude-opus-5-5": {
        "input": 4.0,
        "cache_write": 5.0,
        "cache_read": 0.2,
        "output": 20.0,
    },
    # Claude Sonnet 5.5 -- Regional.
    "anthropic.claude-sonnet-5-5": {
        "input": 2.2,
        "cache_write": 2.75,
        "cache_read": 0.22,
        "output": 11.0,
    },
    # Claude Sonnet 5.5 -- Global cross-region.
    "global.anthropic.claude-sonnet-5-5": {
        "input": 2.0,
        "cache_write": 2.5,
        "cache_read": 0.2,
        "output": 10.0,
    },
}

_PER_1M = 1_000_000.0
_GLOBAL_PREFIX = "global."


def _normalize(model: str) -> str:
    """Return a model id reduced to its price-table key.

    Several spellings of one model reach this module, and all must price the
    same: the inference-profile form (``us.openai.gpt-5.6-terra``), the raw
    Bedrock id with its version suffix (``qwen.qwen3-coder-30b-a3b-v1:0``), the
    LiteLLM alias the harness records as ``--model``
    (``qwen.qwen3-coder-30b-a3b-instruct``), and the Anthropic forms with a
    release date, a bare version or a context-window tag
    (``anthropic.claude-haiku-4-5-20251001-v1:0``,
    ``anthropic.claude-opus-4-6-v1``, ``anthropic.claude-opus-4-8[1m]``).
    Without these a priced model still yields a null cost, which reads as a
    free run.

    Args:
        model: The model id in any of those spellings.

    Returns:
        The bare key: prefix, version suffix, release date, context tag and
        ``-instruct`` removed.
    """
    clean = re.sub(r"\[[^\]]*\]$", "", model)
    for prefix in ("us.", "global.", "eu.", "ap."):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :]
            break
    # Bedrock version suffixes: '-v1:0', ':0', '-v2:1', and a bare '-v1'.
    clean = re.sub(r"(-v\d+)?(:\d+)?$", "", clean)
    # Anthropic release dates: 'claude-haiku-4-5-20251001'.
    clean = re.sub(r"-\d{8}$", "", clean)
    if clean.endswith("-instruct"):
        clean = clean[: -len("-instruct")]
    return clean


def _rates(model: str) -> dict[str, float] | None:
    """Return the price row for a model id, or None if unknown.

    Args:
        model: The model id, in any spelling ``_normalize`` accepts.

    A ``global.`` id is billed at the Global cross-region rate, so it prefers
    the ``global.``-keyed row when the table has one; every other id, and a
    ``global.`` id with no such row, uses the plain key.

    Returns:
        The rate row, or None when the model is not in the table.
    """
    key = _normalize(model)
    if model.startswith(_GLOBAL_PREFIX) and _GLOBAL_PREFIX + key in PRICES:
        return PRICES[_GLOBAL_PREFIX + key]
    return PRICES.get(key) or PRICES.get(model)


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """Compute total cost in USD for a single run.

    Returns None when the model is not in the price table rather than
    returning a misleading 0.

    Args:
        model: The model id (with or without inference-profile prefix).
        input_tokens: Fresh (non-cached) input tokens.
        output_tokens: Output tokens.
        cache_read_tokens: Tokens served from cache (cache read).
        cache_write_tokens: Tokens written to cache (cache write).

    Returns:
        Total cost in USD, or None if the model is not priced, or if cached
        tokens are reported against a model whose row carries no cache rate
        (a caching-incapable model such as Qwen: pricing those at zero would
        understate the bill and cannot be told apart from a real free run).
    """
    rates = _rates(model)
    if rates is None:
        return None
    for tokens, key in (
        (cache_read_tokens, "cache_read"),
        (cache_write_tokens, "cache_write"),
    ):
        if tokens and key not in rates:
            return None
    total = (
        input_tokens * rates["input"] / _PER_1M
        + output_tokens * rates["output"] / _PER_1M
        + cache_read_tokens * rates.get("cache_read", 0.0) / _PER_1M
        + cache_write_tokens * rates.get("cache_write", 0.0) / _PER_1M
    )
    return round(total, 6)
