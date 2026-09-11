"""Tests for multi-session support (switch / target the active SSH session)."""


import pytest

from fncollect.context import Context
from fncollect.dcp import DcpDefinition, DcpStep, execute_dcp
from fncollect.session_manager import SessionManager
from fncollect.sessions import CommandResult, DeviceConnectionError


class FakeSession:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.commands: list[str] = []
        self.connect_calls = 0
        self.prompt = "base"

    async def connect(self) -> None:
        self.connect_calls += 1

    def set_prompt(self, pattern: str) -> None:
        self.prompt = pattern

    async def exec_cmd(self, command: str) -> CommandResult:
        self.commands.append(command)
        return CommandResult(command=command, output=f"[{self.prompt}] {command}", session=self.tag)

    async def close(self) -> None:
        pass


class MultiDevice:
    """Minimal device exposing a SessionManager-backed interface."""

    def __init__(self, manager: SessionManager) -> None:
        self._manager = manager

    def switch_session(self, alias: str) -> None:
        self._manager.switch(alias)

    async def exec_cmd(self, command: str) -> CommandResult:
        return await self._manager.exec_cmd(command)

    async def exec_cmd_with_session(self, session: str, command: str) -> CommandResult:
        return await self._manager.exec_cmd(command, session=session)


@pytest.fixture
def run_ctx(tmp_path):
    from fncollect.config import LoggingConfig, RunConfig
    from fncollect.logging_setup import build_logger
    from fncollect.session_ctx import RunContext

    return RunContext(
        RunConfig(output_dir="."),
        tmp_path,
        logger=build_logger(config=LoggingConfig()),
    )


def _device():
    cli = FakeSession("cli")
    tnd = FakeSession("tnd")
    manager = SessionManager({"cli": cli, "tnd": tnd}, default="cli")
    return MultiDevice(manager), cli, tnd


async def test_switch_meta_op_changes_active_session(run_ctx):
    device, cli, tnd = _device()
    dcp = DcpDefinition(
        name="switch_dcp", vendor="mock",
        steps=[
            DcpStep(id="a", command="cmd-a"),              # runs on cli (active)
            DcpStep(id="b", command="cmd-b", switch="tnd"),  # switch then run on tnd
            DcpStep(id="c", command="cmd-c"),              # still tnd (active)
        ],
    )
    await execute_dcp(dcp, device, run_ctx)
    assert cli.commands == ["cmd-a"]
    assert tnd.commands == ["cmd-b", "cmd-c"]


async def test_step_session_targets_specific_session(run_ctx):
    device, cli, tnd = _device()
    dcp = DcpDefinition(
        name="target_dcp", vendor="mock",
        steps=[
            DcpStep(id="a", command="cmd-a", session="tnd"),
            DcpStep(id="b", command="cmd-b"),
        ],
    )
    await execute_dcp(dcp, device, run_ctx)
    assert tnd.commands == ["cmd-a"]
    assert cli.commands == ["cmd-b"]


async def test_connect_all_only_connects_active_then_lazy():
    cli = FakeSession("cli")
    tnd = FakeSession("tnd")
    manager = SessionManager({"cli": cli, "tnd": tnd}, default="cli")

    await manager.connect_all()
    assert cli.connect_calls == 1
    assert tnd.connect_calls == 0  # not eagerly opened

    # targeting the other session connects it lazily
    await manager.exec_cmd("x", session="tnd")
    assert tnd.connect_calls == 1
    assert tnd.commands == ["x"]


async def test_unreachable_session_fails_fast_after_first_attempt():
    class BadSession(FakeSession):
        async def connect(self) -> None:
            self.connect_calls += 1
            raise TimeoutError("no banner")

    cli = FakeSession("cli")
    tnd = BadSession("tnd")
    manager = SessionManager({"cli": cli, "tnd": tnd}, default="cli")

    # first targeting tries connect and fails with a typed connection error
    with pytest.raises(DeviceConnectionError):
        await manager.exec_cmd("a", session="tnd")
    assert tnd.connect_calls == 1
    # subsequent targeting fails fast with the same typed error (no retry connect)
    with pytest.raises(DeviceConnectionError):
        await manager.exec_cmd("b", session="tnd")
    assert tnd.connect_calls == 1  # still only one connect attempt


async def test_dcp_aborts_on_unreachable_session(run_ctx):
    class BadSession(FakeSession):
        async def connect(self) -> None:
            self.connect_calls += 1
            raise TimeoutError("no banner")

    cli = FakeSession("cli")
    tnd = BadSession("tnd")
    manager = SessionManager({"cli": cli, "tnd": tnd}, default="cli")
    device = MultiDevice(manager)

    dcp = DcpDefinition(
        name="abort_dcp", vendor="mock",
        steps=[
            DcpStep(id="a", command="cmd-a"),                      # cli (ok)
            DcpStep(id="b", command="cmd-b", session="tnd"),       # tnd connect fails
            DcpStep(id="c", command="cmd-c", session="tnd"),       # must NOT run
            DcpStep(id="d", command="cmd-d", session="tnd"),       # must NOT run
        ],
    )
    results = await execute_dcp(dcp, device, run_ctx)
    assert results["aborted"] == "no banner"
    assert {s["id"] for s in results["steps"] if s.get("error")} == {"b"}
    assert tnd.connect_calls == 1   # connected once, never retried
    assert tnd.commands == []       # no command ever reached TND


async def test_exec_target_navigates_to_lt_and_back():
    cli = FakeSession("cli")
    tnd = FakeSession("tnd")
    tnd.prompt_pattern = "^nt$"  # TND connection's base context = active NT
    manager = SessionManager({"cli": cli, "tnd": tnd}, default="cli")
    manager.set_contexts({
        "cli": Context("cli", "cli", "^cli$"),
        "nt": Context("nt", "tnd", "^nt$"),
        "lt": Context("lt", "tnd", "^lt$", enter=["login board {id}"], exit=["exit"], params={"id": ""}),
    })

    await manager.exec_target("lt:1103", "memm free_mem")
    # entered LT board via login, ran command, then exited
    assert tnd.commands[0] == "login board 1103"
    assert tnd.commands[-2] == "memm free_mem"
    assert tnd.commands[-1] == "exit"
    # prompt was restored to the active-NT (TND base) after exit
    assert tnd.prompt == "^nt$"


async def test_exec_target_nt_no_enter():
    cli = FakeSession("cli")
    tnd = FakeSession("tnd")
    manager = SessionManager({"cli": cli, "tnd": tnd}, default="cli")
    manager.set_contexts({
        "cli": Context("cli", "cli", "^cli$"),
        "nt": Context("nt", "tnd", "^nt$"),
    })
    await manager.exec_target("nt", "version")
    assert tnd.commands == ["version"]
    assert tnd.prompt == "^nt$"
