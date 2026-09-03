"""LLM Parliament — multi-agent debate for better AI decisions."""

from importlib.metadata import PackageNotFoundError, version

from parliament.core.types import Bill, Hansard, Member, Response, Synthesis
from parliament.core.parliament import Parliament

try:
    # Read from installed metadata rather than hard-coding, so this can never
    # disagree with pyproject.toml -- a version string that has drifted is worse
    # than none, because a bug report quoting it sends someone to the wrong tag.
    __version__ = version("llm-parliament")
except PackageNotFoundError:  # pragma: no cover - a source tree with no install
    # Running straight from a checkout. Say so rather than inventing a number:
    # "0.0.0" in a bug report looks like a real release that nobody shipped.
    __version__ = "unknown"

__all__ = [
    "Parliament",
    "Bill",
    "Hansard",
    "Member",
    "Response",
    "Synthesis",
    "__version__",
]
