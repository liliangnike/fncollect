"""Tests for multi-session support (switch / target the active SSH session)."""


import pytest

from fncollect.dcp import DcpDefinition, DcpStep, execute_dcp
from fncollect.session_manager import SessionManager
from fncollect.sessions import CommandResult


class FakeSession:
    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.commands: list[str] = []

    async def connect(self) -> None:
        pass

    async def exec_cmd(self, command: str) -> CommandResult:
        self.commands.append(command)
        return CommandResult(command=command, output=f"[{self.tag}] {command}")

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
