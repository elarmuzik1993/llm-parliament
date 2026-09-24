"""Model capability tier system.

Tiers drive Speaker assignment and gap warnings.
No user configuration needed — this is internal.
"""

from __future__ import annotations

import re

from parliament.core.types import Member

# Tier 1 = frontier, Tier 4 = small
MODEL_TIERS: dict[str, int] = {
    # Tier 1 — frontier
    "claude-opus-4-6": 1,
    "gpt-4o": 1,
    "gemini-2.5-pro": 1,
    "gemini-2.0-pro": 1,
    # Tier 2 — strong
    "claude-sonnet-4-6": 2,
    "gpt-4o-mini": 2,
    "gemini-2.5-flash": 2,
    "gemini-2.0-flash": 2,
    "llama3.1:70b": 2,
    "mistral-large": 2,
    "qwen2:72b": 2,
    # Tier 2 — Mistral's hosted API (api.mistral.ai)
    "mistral-large-latest": 2,
    "mistral-medium-latest": 2,
    # Tier 2 — Groq (api.groq.com), same weights as the Ollama names above,
    # served much faster
    "llama-3.3-70b-versatile": 2,
    "qwen-2.5-72b-instruct": 2,
    # Tier 3 — capable
    "llama3.1": 3,
    "llama3.1:8b": 3,
    "gemma2": 3,
    "gemma2:9b": 3,
    "mistral": 3,
    "mistral:7b": 3,
    "qwen2:7b": 3,
    "gemini-2.5-flash-lite": 3,
    "mistral-small-latest": 3,
    "llama-3.1-8b-instant": 3,
    "qwen-2.5-32b": 3,
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


# OpenRouter routing variants: same weights, different price or routing.
# Only these are stripped -- an Ollama tag like ``:70b`` names different weights.
_OPENROUTER_VARIANTS = frozenset(
    {"free", "beta", "extended", "thinking", "online", "nitro", "floor", "exacto"}
)

_VERSION_DOT = re.compile(r"(?<=\d)\.(?=\d)")


def _slug_candidates(model: str) -> list[str]:
    """Bare ids an OpenRouter ``vendor/slug`` may be stored under in MODEL_TIERS.

    ``anthropic/claude-sonnet-4.6:free`` -> ``claude-sonnet-4.6``, then
    ``claude-sonnet-4-6``: OpenRouter writes Claude versions with a dot where
    Anthropic's API uses a dash. The dotted form is tried first because Gemini
    ids carry a real dot (``gemini-2.5-pro``).
    """
    if "/" not in model:
        return []
    slug = model.rsplit("/", 1)[1]
    base, sep, variant = slug.rpartition(":")
    if sep and variant in _OPENROUTER_VARIANTS:
        slug = base
    dashed = _VERSION_DOT.sub("-", slug)
    return [slug] if dashed == slug else [slug, dashed]


def get_tier(model: str) -> int:
    """Return tier for a model name. Unknown models default to tier 3.

    An exact match wins; otherwise an OpenRouter ``vendor/slug`` resolves to
    the tier of the bare id it routes to, so one table serves both (#37).
    """
    if model in MODEL_TIERS:
        return MODEL_TIERS[model]
    for candidate in _slug_candidates(model):
        if candidate in MODEL_TIERS:
            return MODEL_TIERS[candidate]
    return DEFAULT_TIER


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
