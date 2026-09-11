"""Session context model.

A device can be reached through several session *types* (OLT CLI, NT_TND,
LT_TND, ...). Some are separate SSH connections; others are different
*contexts* inside the same connection (e.g. on the NT_TND connection you can
``login board 1103`` to reach an LT board). Each context has its own prompt.

A :class:`Context` declares how to reach a logical device target: which
connection it uses, the prompt in that context, and the enter/exit commands to
navigate to/from it. This lets a procedure address targets flexibly
(``cli``, ``nt``, ``nt_peer``, ``lt:<id>``) while the engine auto-navigates.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Context:
    """A logical addressable device context within a session type."""

    name: str                       # e.g. "cli", "nt", "nt_peer", "lt"
    session: str                    # connection alias (e.g. "cli", "tnd")
    prompt: str                     # prompt regex for this context
    enter: list[str] = field(default_factory=list)  # cmds to reach it
    exit: list[str] = field(default_factory=list)   # cmds to leave it
    # parameters to substitute into enter commands (e.g. {"id": "1103"})
    params: dict[str, Any] = field(default_factory=dict)

    def _fill(self, text: str) -> str:
        out = text
        for key, value in self.params.items():
            out = out.replace("{" + key + "}", str(value))
        return out

    def enter_commands(self) -> list[str]:
        return [self._fill(c) for c in self.enter]

    def exit_commands(self) -> list[str]:
        return [self._fill(c) for c in self.exit]


def prompt_re(pattern: str) -> re.Pattern:
    return re.compile(r"(" + pattern + r")\s*$")
