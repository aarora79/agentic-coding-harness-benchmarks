"""Amazon Bedrock price table and cost helpers for the benchmark harness.

Used by the codex agent path to derive total_cost_usd from token counts,
since codex exec does not report a billed cost itself.

Provenance of the rates:
- Rates were read directly from https://aws.amazon.com/bedrock/pricing/ on the
  date in ``PRICES_AS_OF``.
- Tier: Standard (on-demand). For the openai.* rows this is the Global CRIS
  (cross-region inference, global profile) Long Context Window (1M) table, the
  tier codex exec uses when it routes through bedrock-mantle; the run token
  counts confirmed it (all tasks exceeded 272K input tokens).
- Cache write is the 30-minute TTL rate.

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
    PRICES, PRICES_AS_OF
"""

from __future__ import annotations

import re

PRICES_AS_OF = "2026-09-11"

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
    # Qwen3 Coder 30B A3B — Standard tier. No cache keys: Bedrock refuses a
    # cachePoint for this family, so a cached-token count here is a bug, not a
    # discount. Flex and Batch are both $0.0773 / $0.3090, Priority is
    # $0.2704 / $1.0815, if a run ever uses another tier.
    "qwen.qwen3-coder-30b-a3b": {
        "input": 0.1545,
        "output": 0.6180,
    },
}

_PER_1M = 1_000_000.0


def _normalize(model: str) -> str:
    """Return a model id reduced to its price-table key.

    Three spellings of one model reach this module, and all must price the
    same: the inference-profile form (``us.openai.gpt-5.6-terra``), the raw
    Bedrock id with its version suffix (``qwen.qwen3-coder-30b-a3b-v1:0``), and
    the LiteLLM alias the harness records as ``--model``
    (``qwen.qwen3-coder-30b-a3b-instruct``). Without the last two a priced
    model still yields a null cost, which reads as a free run.

    Args:
        model: The model id in any of those spellings.

    Returns:
        The bare key: prefix, version suffix and ``-instruct`` removed.
    """
    clean = model
    for prefix in ("us.", "global.", "eu.", "ap."):
        if clean.startswith(prefix):
            clean = clean[len(prefix) :]
            break
    # Bedrock version suffixes: '-v1:0', ':0', '-v2:1'.
    clean = re.sub(r"(-v\d+)?:\d+$", "", clean)
    if clean.endswith("-instruct"):
        clean = clean[: -len("-instruct")]
    return clean


def _rates(model: str) -> dict[str, float] | None:
    """Return the price row for a model id, or None if unknown.

    Args:
        model: The model id, in any spelling ``_normalize`` accepts.

    Returns:
        The rate row, or None when the model is not in the table.
    """
    return PRICES.get(_normalize(model)) or PRICES.get(model)


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
