"""Model capability tier system.

Tiers drive Speaker assignment and gap warnings.
No user configuration needed — this is internal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from parliament.core.types import TIER_GAP, UNRATED, Member, SessionWarning
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
    # The dated id the Anthropic preset ships with; family rules match no dates.
    "claude-haiku-4-5-20251001": 3,
    "mistral-small-latest": 3,
    "llama-3.1-8b-instant": 3,
    "qwen-2.5-32b": 3,
    # Tier 4 — small
    "phi3:mini": 4,
    "gemma2:2b": 4,
    "tinyllama": 4,
}

DEFAULT_TIER = 3

# Family rules (#67): rate releases newer than MODEL_TIERS from vendor naming,
# which has stayed stable across versions. A rating found here is *inferred*,
# and labelled so; MODEL_TIERS wins wherever both apply.
#
# Each pattern must match the whole tier identity (see canonical_model_id), so
# a fine-tune, snapshot or unknown variant (`claude-opus-5-5-custom`,
# `gpt-5-codex`, `gemini-2.0-flash-002`) stays unrated rather than inheriting
# its family's rating. Major versions start where the family is current, so a
# superseded generation (`claude-3-opus`, `gemini-1.5-pro`) stays unrated too.
# tests/test_model_tiers.py pins every rule with example ids, and fails when a
# MODEL_TIERS entry disagrees with the rule that also covers it.
_CLAUDE = r"(?:[4-9]|[1-9]\d)(?:-\d{1,2})?"  # claude-opus-4, -4-1, -5-5
_GPT = r"(?:[5-9]|[1-9]\d)(?:\.\d{1,2})?"  # gpt-5, gpt-5.1
_GEMINI = r"(?:[2-9]|[1-9]\d)(?:\.\d)?"  # gemini-2.5, gemini-3
FAMILY_RULES: tuple[tuple[str, int], ...] = (
    (rf"claude-opus-{_CLAUDE}", 1),
    (rf"claude-sonnet-{_CLAUDE}", 2),
    (rf"claude-haiku-{_CLAUDE}", 3),
    (rf"gpt-{_GPT}", 1),
    (rf"gpt-{_GPT}-mini", 2),
    (rf"gpt-{_GPT}-nano", 3),
    # Google ships its newest models as `-preview` for months at a time.
    (rf"gemini-{_GEMINI}-pro(?:-preview)?", 1),
    (rf"gemini-{_GEMINI}-flash(?:-preview)?", 2),
    (rf"gemini-{_GEMINI}-flash-lite(?:-preview)?", 3),
)
_FAMILY_PATTERNS = tuple((re.compile(pattern), tier) for pattern, tier in FAMILY_RULES)

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


def inferred_tier(model_id: str) -> int | None:
    """The tier a family rule gives a tier identity, or None when none matches."""
    for pattern, tier in _FAMILY_PATTERNS:
        if pattern.fullmatch(model_id):
            return tier
    return None


def _rating(model: str, provider: str, base_url: str | None) -> tuple[int, bool] | None:
    """(tier, inferred) from MODEL_TIERS, then the family rules; None when unrated."""
    model_id = canonical_model_id(model, provider, base_url)
    if model_id in MODEL_TIERS:
        return MODEL_TIERS[model_id], False
    tier = inferred_tier(model_id)
    return (tier, True) if tier is not None else None


def has_known_tier(model: str, provider: str, base_url: str | None = None) -> bool:
    """Distinguish rated models, assessed or inferred, from the unknown-model fallback."""
    return _rating(model, provider, base_url) is not None


def is_inferred_tier(model: str, provider: str, base_url: str | None = None) -> bool:
    rating = _rating(model, provider, base_url)
    return rating is not None and rating[1]


def get_tier(model: str, provider: str, base_url: str | None = None) -> int:
    """Return tier for a model name. Unrated models default to tier 3."""
    rating = _rating(model, provider, base_url)
    return rating[0] if rating is not None else DEFAULT_TIER


def get_tier_label(tier: int) -> str:
    return TIER_LABELS.get(tier, "unknown")


def get_member_tier_label(member: Member) -> str:
    if member.provider_name == "mock":
        return get_tier_label(member.tier)
    rating = _rating(member.model, member.provider_name, member.tier_base_url)
    if rating is None:
        return f"unrated (assumed tier {DEFAULT_TIER})"
    tier, inferred = rating
    return f"{get_tier_label(tier)} (inferred)" if inferred else get_tier_label(tier)


def is_rated(member: Member) -> bool:
    """Whether a member's tier is a rating rather than the unrated fallback."""
    # Mock tiers are supplied synthetic ratings, not unknown-model defaults.
    return member.provider_name == "mock" or has_known_tier(
        member.model, member.provider_name, member.tier_base_url
    )


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

    def session_warnings(self) -> list[SessionWarning]:
        warnings = []
        if self.gap is not None:
            warnings.append(SessionWarning(TIER_GAP, self.gap.warning()))
        if self.unrated_members:
            names = [m.name for m in self.unrated_members]
            warnings.append(SessionWarning(UNRATED, unrated_warning(names)))
        return warnings

    def warnings(self) -> list[str]:
        return [w.message for w in self.session_warnings()]


def calculate_gap(members: list[Member]) -> TierAssessment:
    """Report assessed gaps and missing ratings without changing members."""
    comparisons: list[tuple[Member, int]] = []
    unrated: list[Member] = []
    for member in members:
        # Mock tiers are supplied synthetic ratings, not unknown-model defaults.
        if member.provider_name == "mock":
            tier = member.tier
        else:
            rating = _rating(member.model, member.provider_name, member.tier_base_url)
            if rating is None:
                unrated.append(member)
                continue
            tier = rating[0]
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
