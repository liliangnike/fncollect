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
        self._dead: dict[str, str] = {}
        self._contexts: dict[str, Any] = {}
        # remember each connection's starting prompt so we can restore it
        # after leaving a target context.
        self._base_prompt: dict[str, str] = {}
        for alias, sess in sessions.items():
            self._base_prompt[alias] = getattr(sess, "prompt_pattern", "")

    def set_contexts(self, contexts: dict[str, Any]) -> None:
        self._contexts = contexts

    def contexts(self) -> dict[str, Any]:
        return self._contexts

    def resolve_target(self, target: str):
        """Resolve a logical target to (Context, params).

        Supports parameterized targets ``lt:1103`` -> context ``lt`` with
        ``{"id": "1103"}``.
        """
        name, _, arg = target.partition(":")
        ctx = self._contexts.get(name)
        if ctx is None:
            raise KeyError(
                f"unknown target {target!r}; known contexts: {sorted(self._contexts)}"
            )
        params = dict(ctx.params)
        if arg:
            params["id"] = arg
        return ctx, params

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
        if alias in self._dead:
            raise ConnectionError(self._dead[alias])
        session = self._sessions[alias]
        if id(session) not in self._connected:
            try:
                await session.connect()
                self._connected.add(id(session))
            except Exception as exc:
                # remember the failure so later commands on this session fail
                # fast instead of retrying a slow connect each time.
                self._dead[alias] = str(exc)
                raise

    async def connect_all(self) -> None:
        """Connect the active session (must succeed).

        Other sessions are connected lazily the first time they are targeted;
        if a session cannot connect it is marked dead and later commands on it
        fail fast (they never delay or clutter the run's active session).
        """
        await self._connect(self._current)

    async def exec_cmd(self, command: str, session: str | None = None) -> CommandResult:
        target = session or self._current
        await self._connect(target)
        result = await self._sessions[target].exec_cmd(command)
        result.session = target
        return result

    async def exec_target(
        self, target: str, command: str, leave: bool = True
    ) -> CommandResult:
        """Execute a command on a logical target, auto-navigating its context.

        E.g. ``lt:1103`` connects the TND session, runs ``login board 1103``
        (setting the LT prompt), runs the command, then exits back to NT.
        """
        ctx, params = self.resolve_target(target)
        alias = ctx.session
        await self._connect(alias)
        sess = self._sessions[alias]
        ctx.params.update(params)
        sess.set_prompt(ctx.prompt)
        for enter_cmd in ctx.enter_commands():
            await sess.exec_cmd(enter_cmd)
        result = await sess.exec_cmd(command)
        result.session = alias
        if leave and ctx.exit_commands():
            for exit_cmd in ctx.exit_commands():
                await sess.exec_cmd(exit_cmd)
            restore = self._base_prompt.get(alias)
            if restore:
                sess.set_prompt(restore)
        return result

    async def close_all(self, aliases: list[str] | None = None) -> None:
        targets = aliases or list(self._sessions)
        for alias in targets:
            try:
                await self._sessions[alias].close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._connected.discard(id(self._sessions[alias]))
