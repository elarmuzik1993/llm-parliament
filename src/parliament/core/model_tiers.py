"""Model capability tier system.

Tiers drive Speaker assignment and gap warnings.
No user configuration needed — this is internal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from parliament.core.types import Member
from parliament.model_catalog import OPENAI_COMPATIBLE

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

MODEL_ALIASES: dict[str, dict[str, str]] = {
    "openrouter": {
        "llama-3.3-70b": "llama-3.3-70b-versatile",
        "llama-3.1-70b": "llama3.1:70b",
        "llama-3.1-8b": "llama3.1:8b",
        "mistral-7b": "mistral:7b",
        "gemma-2-9b": "gemma2:9b",
        "gemini-2.0-flash-001": "gemini-2.0-flash",
        "llama-3.1-70b-instruct": "llama3.1:70b",
        "llama-3.1-8b-instruct": "llama3.1:8b",
        "llama-3.3-70b-instruct": "llama-3.3-70b-versatile",
        "mistral-7b-instruct": "mistral:7b",
        "gemma-2-9b-it": "gemma2:9b",
    },
}

TIER_LABELS: dict[int, str] = {
    1: "frontier",
    2: "strong",
    3: "capable",
    4: "small",
}


def _endpoint_identity(base_url: str) -> tuple[str, str, int | None, str] | None:
    try:
        url = urlsplit(base_url)
        if not url.hostname or url.username or url.password or url.query or url.fragment:
            return None
        port = url.port
        if port is None:
            port = {"https": 443, "http": 80}.get(url.scheme)
        return url.scheme, url.hostname, port, url.path.rstrip("/")
    except ValueError:
        return None


def canonical_model_id(model: str, provider: str, base_url: str | None = None) -> str:
    """Resolve an internal tier identity without changing the API model ID."""
    if provider == "openai" and base_url:
        endpoint = _endpoint_identity(base_url)
        if endpoint is not None:
            for name, spec in OPENAI_COMPATIBLE.items():
                if endpoint == _endpoint_identity(spec.base_url):
                    provider = name
                    break
    if provider == "openrouter":
        # Only OpenRouter tier identities omit vendor/ and :variant and change
        # Claude version dots to dashes. Tuning/version suffixes require explicit
        # aliases; stripping them globally could give unfamiliar models a rating.
        model = model.split("/", 1)[-1].split(":", 1)[0]
        if model in MODEL_TIERS:
            return model
        if model.startswith("claude-"):
            model = re.sub(r"(?<=\d)\.(?=\d)", "-", model)
    return MODEL_ALIASES.get(provider, {}).get(model, model)


def has_known_tier(model: str, provider: str, base_url: str | None = None) -> bool:
    """Distinguish classified tier-3 models from the unknown-model fallback."""
    return canonical_model_id(model, provider, base_url) in MODEL_TIERS


def get_tier(model: str, provider: str, base_url: str | None = None) -> int:
    """Return tier for a model name. Unknown models default to tier 3."""
    return MODEL_TIERS.get(canonical_model_id(model, provider, base_url), DEFAULT_TIER)


def get_tier_label(tier: int) -> str:
    return TIER_LABELS.get(tier, "unknown")


def get_member_tier_label(member: Member) -> str:
    if member.provider_name == "mock":
        return get_tier_label(member.tier)
    if not has_known_tier(member.model, member.provider_name, member.tier_base_url):
        return f"unrated (assumed tier {DEFAULT_TIER})"
    return get_tier_label(get_tier(member.model, member.provider_name, member.tier_base_url))


def unrated_warning(names: list[str]) -> str:
    labels = ", ".join(f"{name} (unrated, assumed tier {DEFAULT_TIER})" for name in names)
    return (
        f"Unrated members: {labels}. Capability comparison is incomplete; "
        f"Speaker selection assumes tier {DEFAULT_TIER} for these models."
    )


@dataclass(frozen=True)
class TierGap:
    strongest: Member
    strongest_tier: int
    weakest: Member
    weakest_tier: int

    def warning(self) -> str:
        return (
            f"Large capability gap between {self.strongest.name} (tier {self.strongest_tier}) "
            f"and {self.weakest.name} (tier {self.weakest_tier}). "
            "Debate quality is limited by the weakest member."
        )


@dataclass(frozen=True)
class TierAssessment:
    gap: TierGap | None
    unrated_members: tuple[Member, ...]
    rated_count: int

    @property
    def comparable(self) -> bool:
        return self.rated_count >= 2 and self.gap is None and not self.unrated_members

    def warnings(self) -> list[str]:
        warnings = [self.gap.warning()] if self.gap is not None else []
        if self.unrated_members:
            warnings.append(unrated_warning([m.name for m in self.unrated_members]))
        return warnings


def calculate_gap(members: list[Member]) -> TierAssessment:
    """Report assessed gaps and missing ratings without changing members."""
    comparisons: list[tuple[Member, int]] = []
    unrated: list[Member] = []
    for member in members:
        # Mock tiers are supplied synthetic ratings, not unknown-model defaults.
        if member.provider_name == "mock":
            tier = member.tier
        else:
            model = canonical_model_id(member.model, member.provider_name, member.tier_base_url)
            known_tier = MODEL_TIERS.get(model)
            if known_tier is None:
                unrated.append(member)
                continue
            tier = known_tier
        comparisons.append((member, tier))
    gap = None
    if len(comparisons) >= 2:
        strongest, strongest_tier = min(comparisons, key=lambda comparison: comparison[1])
        weakest, weakest_tier = max(comparisons, key=lambda comparison: comparison[1])
        if weakest_tier - strongest_tier > 1:
            gap = TierGap(strongest, strongest_tier, weakest, weakest_tier)
    return TierAssessment(gap, tuple(unrated), len(comparisons))


def detect_gap(members: list[Member]) -> bool:
    """Return whether assessed members have a gap greater than one tier.

    False does not establish comparability: use calculate_gap() to inspect
    missing ratings and warnings as well.
    """
    return calculate_gap(members).gap is not None


def resolve_member_tier(member: Member) -> Member:
    """Resolve a member's tier in place, preserving its API model ID."""
    # Preserve synthetic mock ratings supplied by tests and programmatic callers.
    if member.provider_name != "mock":
        member.tier = get_tier(member.model, member.provider_name, member.tier_base_url)
    return member
