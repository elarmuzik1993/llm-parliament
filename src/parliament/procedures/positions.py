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

# Tolerates markdown around the label: "**POSITION:** ...", "- Position: ...".
_LABEL_PREFIX = r"^[ \t>*_#-]*"
_LABEL_SUFFIX = r"[*_]*[ \t]*:[*_]*[ \t]*"
_POSITION = re.compile(
    _LABEL_PREFIX + r"POSITION" + _LABEL_SUFFIX + r"(.+?)[ \t]*$",
    re.IGNORECASE | re.MULTILINE,
)
_CHANGED_MIND = re.compile(
    _LABEL_PREFIX + r"CHANGED[ _-]MIND" + _LABEL_SUFFIX + r"[*_]*(yes|no)\b",
    re.IGNORECASE | re.MULTILINE,
)


def parse_position(content: str) -> Position | None:
    """The member's position, or None when it left out the POSITION line.

    The last match wins: the instructions put the lines at the end, so an
    earlier "Position:" is more likely the member's own prose.
    """
    stances = _POSITION.findall(content)
    if not stances:
        return None
    stance = stances[-1].strip("*_ \t")
    if not stance:
        return None
    answers = _CHANGED_MIND.findall(content)
    changed_mind = answers[-1].lower() == "yes" if answers else None
    return Position(stance=stance, changed_mind=changed_mind)
