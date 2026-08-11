#!/usr/bin/env python3
"""Single-source EC2 pricing lookup for cost-per-token / cost-per-task math.

Reads ``self-hosted/vllm/pricing.json`` so no script hardcodes a dollar figure.
The effective hourly rate a run is charged is
``dollars_per_hour * discount_multiplier``, then further prorated by
``tp / gpus_per_instance`` when a model is served with tensor parallelism below
the instance's GPU count (it uses only part of the box) -- e.g. a TP=4 model on
an 8-GPU p5en.48xlarge is charged half the (discounted) instance rate.

``discount_multiplier`` lets us keep an on-demand base rate on record while
pricing runs at a committed-capacity equivalent (e.g. p5en at 0.35x on-demand);
where the base rate already reflects the target (e.g. g6e at its 3-year RI
rate), the multiplier is 1.0.

Usage:
    from pricing import resolve, instance_hourly
    rate = resolve("p5en.48xlarge", tp=4)   # half-box effective $/hr (discounted)
    full = instance_hourly("g6e.12xlarge")  # whole-instance effective $/hr
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

# pricing.json lives at the vLLM dir root: clients/ -> parent.
_PRICING_PATH = Path(__file__).resolve().parent.parent / "pricing.json"


class PricingError(ValueError):
    """Raised when an instance type is missing from pricing.json."""


@lru_cache(maxsize=1)
def _load() -> dict:
    """Load and cache pricing.json."""
    if not _PRICING_PATH.is_file():
        raise PricingError(f"pricing.json not found at {_PRICING_PATH}")
    return json.loads(_PRICING_PATH.read_text(encoding="utf-8"))


def _entry(instance_type: str) -> dict:
    """Return the pricing.json entry for ``instance_type`` or raise."""
    instances = _load().get("instances", {})
    entry = instances.get(instance_type)
    if entry is None:
        raise PricingError(
            f"instance '{instance_type}' not in pricing.json "
            f"(have: {sorted(instances)}). Add it there, do not hardcode a rate."
        )
    return entry


def _effective_full(entry: dict) -> float:
    """Whole-instance effective $/hr = base dollars_per_hour x discount_multiplier."""
    base = float(entry["dollars_per_hour"])
    mult = float(entry.get("discount_multiplier", 1.0))
    return base * mult


def instance_hourly(instance_type: str) -> float:
    """Return the whole-instance effective $/hr for ``instance_type``.

    Effective = ``dollars_per_hour * discount_multiplier`` (the discount lets us
    keep an on-demand base on record while charging a committed-capacity rate).

    Args:
        instance_type: e.g. ``g6e.12xlarge`` or ``p5en.48xlarge``.

    Returns:
        Effective dollars per hour for the full instance.

    Raises:
        PricingError: If the instance type is not in pricing.json.
    """
    return _effective_full(_entry(instance_type))


def resolve(instance_type: str, tp: int | None = None) -> float:
    """Return the effective $/hr for a run, accounting for a partial-box TP.

    A model served at ``tp`` GPUs on an instance with more GPUs uses only that
    fraction of the box, so it is charged ``dollars_per_hour * tp /
    gpus_per_instance``. With ``tp`` unset (or >= the instance's GPU count) the
    full-instance rate is returned.

    Args:
        instance_type: The EC2 instance type.
        tp: Tensor-parallel size (GPUs the model actually used). None = full box.

    Returns:
        Effective dollars per hour to attribute to this model's run.

    Raises:
        PricingError: If the instance type is not in pricing.json.
    """
    entry = _entry(instance_type)
    full = _effective_full(entry)
    gpus = int(entry.get("gpus_per_instance") or 0)
    if tp is None or gpus <= 0 or tp >= gpus:
        return full
    return full * tp / gpus
