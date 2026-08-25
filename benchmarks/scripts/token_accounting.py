#!/usr/bin/env python3
"""Single source of truth for "how many tokens did the model actually process".

WHY THIS MODULE EXISTS (issue #136)
-----------------------------------
Every self-hosted ``$/task`` figure was ~2x too high because the total-token
count added ``cache_read_tokens`` and ``cache_write_tokens`` to ``input_tokens``
UNCONDITIONALLY. That is only correct when the cache fields are ADDITIVE to
input (the Bedrock / Anthropic accounting). For the self-hosted vLLM ``pi``
runs, the cache fields are a PARTITION OF input -- ``input_tokens`` already
contains the cached prompt tokens, and ``cache_read + cache_write`` just breaks
that same number down. Adding them back on top counts the cached prompt twice,
which roughly doubles the token total and therefore the cost.

The catch is that the accounting is NOT uniform, even within one harness:

  * ``pi`` self-hosted ``swe3``      -> cache_read+cache_write == input  (PARTITION -> was double-counted)
  * ``pi`` self-hosted ``swe2``      -> input tiny, cache huge           (ADDITIVE  -> was already correct)
  * ``claude-code`` self-hosted      -> cache_read+cache_write == 0       (input holds everything -> correct)
  * ``claude-code`` / ``pi`` Bedrock -> input tiny, cache huge           (ADDITIVE  -> correct)

So the fix is NOT per-harness and NOT "always input+output". The only reliable
signal is the data itself: the cache is a partition of input exactly when
``cache_read + cache_write`` is (approximately) equal to ``input_tokens``. When
that signature holds we must NOT re-add the cache; otherwise we must.

Every caller that turns per-field token counts into a single "total tokens
processed" number MUST go through ``compute_total_tokens_processed`` so the rule
lives in one place and every computation logs LOUDLY whether it detected the
partition signature and exactly which formula it used.
"""

from __future__ import annotations

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


# A run is treated as "cache is a partition of input" when cache_read+cache_write
# lands within this fraction of input_tokens. The real self-hosted partition runs
# sit within ~1% (the ratio is exactly the server prefix-cache hit rate); the
# additive runs are off by many multiples (or the cache fields are zero), so a
# 5% band separates the two cases cleanly with room to spare.
PARTITION_TOLERANCE: float = 0.05


def _is_cache_partition_of_input(
    input_tokens: int,
    cache_sum: int,
) -> bool:
    """Return True when the cache fields are a PARTITION of ``input_tokens``.

    Partition means ``input_tokens`` already includes the cached prompt tokens,
    so ``cache_read + cache_write`` merely re-describes part of that same count
    and must NOT be added on top. Detected when ``cache_sum`` is non-zero and
    within ``PARTITION_TOLERANCE`` of ``input_tokens``.

    Args:
        input_tokens: The run's summed input tokens.
        cache_sum: ``cache_read_tokens + cache_write_tokens`` for the run.

    Returns:
        True if the cache is a partition of input; False if it is additive
        (Bedrock-style) or zero.
    """
    if cache_sum <= 0 or input_tokens <= 0:
        return False
    return abs(cache_sum - input_tokens) <= PARTITION_TOLERANCE * input_tokens


def compute_total_tokens_processed(
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
    context: str = "unknown",
) -> int:
    """Return the total tokens the model actually processed, once each.

    Applies the partition rule from issue #136 and LOUDLY logs the decision:
    whether the partition signature was detected and the exact formula used.

      * PARTITION detected (``cache_read + cache_write`` ~= ``input_tokens``):
        the cached prompt is already inside ``input_tokens``, so
        ``total = input + output`` (adding the cache back would ~2x double-count).
      * NOT detected (cache is additive, or zero):
        ``total = input + output + cache_read + cache_write``.

    Args:
        input_tokens: Input (prompt) tokens.
        output_tokens: Generated (completion) tokens.
        cache_read_tokens: Prompt tokens served from cache.
        cache_write_tokens: Prompt tokens written to cache (cache creation).
        context: Short label (e.g. ``"gen_agent_report:qwen3.6-35b/pi/swe3"``)
            included in the trace so the decision is attributable per run/task.

    Returns:
        Total tokens processed (an ``int``).
    """
    inp = input_tokens or 0
    out = output_tokens or 0
    cr = cache_read_tokens or 0
    cw = cache_write_tokens or 0
    cache_sum = cr + cw

    if _is_cache_partition_of_input(inp, cache_sum):
        total = inp + out
        logger.info(
            "[token-accounting] context=%s: PARTITION SIGNATURE DETECTED -- "
            "cache_read(%d)+cache_write(%d)=%d is within %.0f%% of input_tokens(%d), "
            "so the cached prompt is ALREADY counted inside input_tokens. "
            "total_tokens = input(%d) + output(%d) = %d "
            "(NOT adding cache_read/cache_write; adding them would ~2x double-count "
            "the cached prompt -- see issue #136).",
            context,
            cr,
            cw,
            cache_sum,
            PARTITION_TOLERANCE * 100,
            inp,
            inp,
            out,
            total,
        )
        return total

    total = inp + out + cache_sum
    logger.info(
        "[token-accounting] context=%s: partition signature NOT detected -- "
        "cache_read(%d)+cache_write(%d)=%d vs input_tokens(%d) (cache is ADDITIVE, "
        "or zero -- not a partition of input). "
        "total_tokens = input(%d) + output(%d) + cache_read(%d) + cache_write(%d) = %d.",
        context,
        cr,
        cw,
        cache_sum,
        inp,
        inp,
        out,
        cr,
        cw,
        total,
    )
    return total
