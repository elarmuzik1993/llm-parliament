"""Core data types — all JSON-serializable via dataclasses."""

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime


@dataclass
class Bill:
    """The question submitted to Parliament."""

    content: str
    title: str = ""

    def __post_init__(self) -> None:
        if not self.title:
            self.title = self.content[:60].strip()


@dataclass
class Member:
    """A parliament member — wraps a provider + model."""

    name: str
    provider_name: str  # "ollama", "anthropic", "openai", "google", "mock"
    model: str
    tier: int = 3  # resolved from MODEL_TIERS, default = capable

    def __str__(self) -> str:
        return f"{self.name} ({self.provider_name}/{self.model})"


@dataclass
class Response:
    """A single member's output from a phase."""

    member_name: str
    content: str
    phase: str  # "first_reading" | "debate"
    duration_ms: int = 0


@dataclass
class Synthesis:
    """Speaker's structured synthesis from Division."""

    speaker_name: str
    consensus: str = ""
    split: str = ""
    risks: str = ""
    recommendation: str = ""
    raw: str = ""  # full Speaker output before parsing


@dataclass
class ProgressEvent:
    """An event emitted by a procedure as work happens, for live renderers.

    Carries the typed payload (Response / Synthesis / error) so a renderer
    can show actual content as it lands, not just status flags.
    """

    phase: str  # "first_reading" | "debate" | "division"
    member_name: str
    kind: str  # "started" | "completed" | "failed"
    response: Response | None = None  # set on FR/Debate "completed"
    synthesis: Synthesis | None = None  # set on Division "completed"
    error: str | None = None  # set on "failed"
    duration_ms: int | None = None


@dataclass
class Hansard:
    """Complete record of a parliamentary session."""

    bill: Bill
    members: list[Member]
    first_reading: list[Response]
    debate: list[Response]
    synthesis: Synthesis
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )
    duration_ms: int = 0
    # True when the verdict was reached with fewer members than configured,
    # because one or more members failed with a provider error. Degraded mode
    # is intended behaviour, but a consumer has to be able to tell a
    # three-member verdict from a two-member one — see #34.
    degraded: bool = False

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_dict(cls, data: dict) -> Hansard:
        return cls(
            bill=Bill(**data["bill"]),
            members=[Member(**m) for m in data["members"]],
            first_reading=[Response(**r) for r in data["first_reading"]],
            debate=[Response(**r) for r in data["debate"]],
            synthesis=Synthesis(**data["synthesis"]),
            id=data["id"],
            created_at=data["created_at"],
            duration_ms=data["duration_ms"],
            # Absent in Hansards written before the field existed.
            degraded=data.get("degraded", False),
        )
