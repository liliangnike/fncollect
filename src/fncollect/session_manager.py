"""Multi-session management for a device.

A Fixed Network device can be reached through several session types at once
(e.g. OLT CLI on port 22 and NT_TND provisioning on port 11130). This lets a
single procedure target or *switch* the active session any time -- the
robotframework-sshlibrary multi-connection pattern that ngalexx users rely
on, re-implemented for fncollect's own Session abstraction.

Sessions are connected lazily: the active one is connected on ``connect_all``
(required), while others connect on demand the first time they are targeted.
A session that cannot connect (e.g. a closed provisioning port) is not fatal.
"""

from __future__ import annotations

from typing import Any

from fncollect.sessions import CommandResult


class SessionManager:
    """Holds multiple aliased sessions and remembers the active one."""

    def __init__(self, sessions: dict[str, Any], default: str | None = None) -> None:
        if not sessions:
            raise ValueError("SessionManager requires at least one session")
        self._sessions = sessions
        self._current = default if default in sessions else next(iter(sessions))
        self._connected: set[int] = set()

    @property
    def aliases(self) -> list[str]:
        return list(self._sessions)

    @property
    def current(self) -> str:
        return self._current

    def has(self, alias: str) -> bool:
        return alias in self._sessions

    def switch(self, alias: str) -> None:
        if alias not in self._sessions:
            raise KeyError(f"no session {alias!r}; known: {self.aliases}")
        self._current = alias

    async def _connect(self, alias: str) -> None:
        session = self._sessions[alias]
        if id(session) not in self._connected:
            await session.connect()
            self._connected.add(id(session))

    async def connect_all(self) -> None:
        """Connect the active session (must succeed).

        Other sessions are connected lazily the first time they are targeted,
        so a session that cannot connect (e.g. a closed provisioning port) only
        fails if a procedure actually uses it -- it never delays or clutters a
        run that only uses the active session.
        """
        await self._connect(self._current)

    async def exec_cmd(self, command: str, session: str | None = None) -> CommandResult:
        target = session or self._current
        await self._connect(target)
        return await self._sessions[target].exec_cmd(command)

    async def close_all(self, aliases: list[str] | None = None) -> None:
        targets = aliases or list(self._sessions)
        for alias in targets:
            try:
                await self._sessions[alias].close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._connected.discard(id(self._sessions[alias]))
