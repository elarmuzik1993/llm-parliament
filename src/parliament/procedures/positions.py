"""Members' self-reported positions — disagreement as data, not prose (#69).

Each member ends its First Reading and Debate answers with labelled lines.
They are parsed here rather than asked of the Speaker: a member is the only
reliable witness to whether it changed its mind, and the Speaker already sees
only anonymised Debate text (#73).
"""

from __future__ import annotations

import re

from parliament.core.types import Position

FIRST_READING_INSTRUCTIONS = """\
End your answer with this line, on its own:
POSITION: <your recommendation, in one sentence>"""

DEBATE_INSTRUCTIONS = """\
End your answer with these two lines, on their own:
POSITION: <your revised recommendation, in one sentence>
CHANGED MIND: <yes or no — did the debate change your recommendation?>"""

# Tolerates markdown around a label: "**POSITION:** ...", "- Position: ...".
_LABEL_END = r"[*_]*[ \t]*:[*_]*"
_POSITION = re.compile(
    r"^[ \t>*_#-]*POSITION" + _LABEL_END, re.IGNORECASE | re.MULTILINE
)
# Not anchored to a line start: a member may put both answers on one line.
_CHANGED_MIND_LABEL = re.compile(r"[*_]*CHANGED[ _-]MIND" + _LABEL_END, re.IGNORECASE)
_CHANGED_MIND = re.compile(
    _CHANGED_MIND_LABEL.pattern + r"\s*[*_]*\s*(yes|no)\b", re.IGNORECASE
)
# Only the end of an answer is read. Debate prompts carry the peers' First
# Readings, so a POSITION line quoted from a peer must not count as the
# member's own when the member leaves its trailer out.
_TAIL_LINES = 6


def _tail(content: str) -> str:
    lines = content.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    nonblank = [i for i, line in enumerate(lines) if line.strip()]
    return "\n".join(lines[nonblank[-_TAIL_LINES:][0]:]) if nonblank else ""


def _clean(text: str) -> str:
    return _CHANGED_MIND_LABEL.split(text, maxsplit=1)[0].strip().strip("*_").strip()


def _stance_after(tail: str, end: int) -> str:
    """The stance on the label's line, or else on the next non-blank line."""
    first, *rest = tail[end:].split("\n")
    stance = _clean(first)
    if stance or _CHANGED_MIND_LABEL.search(first):
        return stance
    following = next((line for line in rest if line.strip()), "")
    return _clean(following)


def parse_position(content: str, *, with_changed_mind: bool = True) -> Position | None:
    """The member's position, or None when it left out the POSITION line.

    `with_changed_mind=False` for First Reading, which does not ask it. The
    last POSITION label wins: the instructions put it after the member's prose.
    """
    tail = _tail(content)
    labels = list(_POSITION.finditer(tail))
    if not labels:
        return None
    stance = _stance_after(tail, labels[-1].end())
    if not stance:
        return None
    answers = _CHANGED_MIND.findall(tail) if with_changed_mind else []
    changed_mind = answers[-1].lower() == "yes" if answers else None
    return Position(stance=stance, changed_mind=changed_mind)
