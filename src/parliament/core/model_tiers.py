"""Model capability tier system.

Tiers drive Speaker assignment and gap warnings.
No user configuration needed — this is internal.
"""

from __future__ import annotations

from parliament.core.types import Member


# Tier 1 = frontier, Tier 4 = small
MODEL_TIERS: dict[str, int] = {
    # Tier 1 — frontier
    "claude-opus-4-6": 1,
    "gpt-4o": 1,
    "gemini-2.0-pro": 1,
    # Tier 2 — strong
    "claude-sonnet-4-6": 2,
    "gpt-4o-mini": 2,
    "gemini-2.5-flash": 2,
    "gemini-2.0-flash": 2,
    "llama3.1:70b": 2,
    "mistral-large": 2,
    "qwen2:72b": 2,
    # Tier 3 — capable
    "llama3.1": 3,
    "llama3.1:8b": 3,
    "gemma2": 3,
    "gemma2:9b": 3,
    "mistral": 3,
    "mistral:7b": 3,
    "qwen2:7b": 3,
    "gemini-2.5-flash-lite": 3,
    # Tier 4 — small
    "phi3:mini": 4,
    "gemma2:2b": 4,
    "tinyllama": 4,
}

DEFAULT_TIER = 3

TIER_LABELS: dict[int, str] = {
    1: "frontier",
    2: "strong",
    3: "capable",
    4: "small",
}


def get_tier(model: str) -> int:
    """Return tier for a model name. Unknown models default to tier 3."""
    return MODEL_TIERS.get(model, DEFAULT_TIER)


def get_tier_label(tier: int) -> str:
    return TIER_LABELS.get(tier, "unknown")


def detect_gap(members: list[Member]) -> bool:
    """True when tier gap between any two members exceeds 1."""
    if len(members) < 2:
        return False
    tiers = [m.tier for m in members]
    return max(tiers) - min(tiers) > 1


def resolve_member_tier(member: Member) -> Member:
    """Return a copy of the member with tier resolved from MODEL_TIERS."""
    member.tier = get_tier(member.model)
    return member
