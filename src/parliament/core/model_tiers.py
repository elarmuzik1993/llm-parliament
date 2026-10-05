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

# OpenRouter spells models as `vendor/slug[:variant]`, with Claude's version
# dotted and many slugs carrying `-instruct`, `-it` or a `-NNN` revision.
# canonical_model_id() folds those onto the bare ids above for the tier lookup
# only: the configured id, and the id sent to the API, are never rewritten.
# MODEL_ALIASES covers the slugs that still differ after that folding.
# Provider-scoped on purpose: `user/model:tag` is a real Ollama name.
_OPENROUTER_SUFFIX = re.compile(r"(-instruct|-it|-\d{3})$")
_VERSION_DOT = re.compile(r"(?<=\d)\.(?=\d)")

MODEL_ALIASES: dict[str, dict[str, str]] = {
    "openrouter": {
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        "llama-3.1-70b": "llama3.1:70b",
        "llama-3.1-8b": "llama-3.1-8b-instant",
        "mistral-7b": "mistral:7b",
        "gemma-2-9b": "gemma2:9b",
    },
}

TIER_LABELS: dict[int, str] = {
    1: "frontier",
    2: "strong",
    3: "capable",
    4: "small",
}


def canonical_model_id(model: str, provider: str) -> str:
    """The id to look up in MODEL_TIERS. Never use it to call an API."""
    if provider == "openrouter":
        model = model.split("/", 1)[-1].split(":", 1)[0]
        # An exact entry wins: `qwen-2.5-72b-instruct` is listed as-is.
        if model in MODEL_TIERS:
            return model
        model = _OPENROUTER_SUFFIX.sub("", model)
        if model.startswith("claude-"):
            model = _VERSION_DOT.sub("-", model)
    return MODEL_ALIASES.get(provider, {}).get(model, model)


def has_known_tier(model: str, provider: str) -> bool:
    """False for an OpenRouter model MODEL_TIERS cannot place.

    OpenRouter lists hundreds of models, so an unplaced one is routine and its
    default tier 3 is a guess; it must not manufacture a gap warning. Every
    other provider keeps counting its default tier, as before.
    """
    if provider != "openrouter":
        return True
    return canonical_model_id(model, provider) in MODEL_TIERS


def get_tier(model: str, provider: str) -> int:
    """Return tier for a model name. Unknown models default to tier 3."""
    return MODEL_TIERS.get(canonical_model_id(model, provider), DEFAULT_TIER)


def get_tier_label(tier: int) -> str:
    return TIER_LABELS.get(tier, "unknown")


def tiered_members(members: list[Member]) -> list[Member]:
    """The members whose tier is a classification rather than a default."""
    return [m for m in members if has_known_tier(m.model, m.provider_name)]


def detect_gap(members: list[Member]) -> bool:
    """True when tier gap between any two classified members exceeds 1."""
    tiers = [m.tier for m in tiered_members(members)]
    if len(tiers) < 2:
        return False
    return max(tiers) - min(tiers) > 1


def resolve_member_tier(member: Member) -> Member:
    """Set the member's tier from MODEL_TIERS, in place, and return it."""
    member.tier = get_tier(member.model, member.provider_name)
    return member
