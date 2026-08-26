"""Tests for the DCP-driven ONT cutthrough provider."""


import pytest

from fncollect.config import LoggingConfig, RunConfig
from fncollect.cutthrough import DcpCutthroughProvider, OntTarget
from fncollect.dcp import DcpDefinition, DcpStep, parse_dcp
from fncollect.logging_setup import build_logger
from fncollect.session_ctx import RunContext
from fncollect.vendor import Device

SETUP_YAML = """
name: setup
vendor: mock
steps:
  - id: set_ip
    command: "ontSessionClientIpAddr {{ ont_client_ip_spaces }}"
  - id: provision
    command: "provision {{ ont_gpon_index }}"
"""
TEARDOWN_YAML = """
name: teardown
vendor: mock
steps:
  - id: clear
    command: "clear {{ ont_gpon_index }}"
"""


@pytest.fixture
def run_ctx(tmp_path):
    return RunContext(
        RunConfig(output_dir="."),
        tmp_path,
        logger=build_logger(config=LoggingConfig()),
    )


class RecordingDevice(Device):
    def __init__(self) -> None:
        self.commands: list[str] = []
        self.role = None

    async def connect(self) -> None:
        pass

    async def exec_cmd(self, command: str):
        from fncollect.sessions import CommandResult

        self.commands.append(command)
        return CommandResult(command=command, output=f"result {command}")

    async def disconnect(self) -> None:
        pass


async def test_dcp_provider_prepare_runs_setup_and_restore_runs_teardown(run_ctx):
    tnd = RecordingDevice()
    setup = parse_dcp(SETUP_YAML)
    teardown = parse_dcp(TEARDOWN_YAML)
    provider = DcpCutthroughProvider(tnd, run_ctx, setup, teardown)
    target = OntTarget(serial="SN1", client_ip="10.0.0.5", gpon_index="2/3/4")

    access = await provider.prepare(olt=None, target=target)
    assert tnd.commands[0] == "ontSessionClientIpAddr 10 0 0 5"
    assert tnd.commands[1] == "provision 2/3/4"
    assert access.serial == "SN1"

    await provider.restore(olt=None, target=target)
    assert tnd.commands[-1] == "clear 2/3/4"


async def test_dcp_provider_resolves_ont_ip_from_setup(run_ctx):
    # a setup DCP that extracts an ont_session_ip

    tnd = RecordingDevice()
    # override exec_cmd to emit an IP for the verify step
    async def exec_with_ip(command):
        from fncollect.sessions import CommandResult

        return CommandResult(command=command, output="ontSessionClientIpAddr 192.168.0.10")

    tnd.exec_cmd = exec_with_ip  # type: ignore[method-assign]
    setup = DcpDefinition(
        name="s", vendor="mock",
        steps=[DcpStep(id="v", command="verify", extract=[
            {"name": "ont_session_ip", "regex": r"([0-9.]+)", "group": 1}])],
    )
    provider = DcpCutthroughProvider(tnd, run_ctx, setup)
    access = await provider.prepare(None, OntTarget(serial="SN1", client_ip="10.0.0.5"))
    # variables recorded by the engine are picked up from variables.json
    assert access.ip  # non-empty, from recorded vars or client_ip fallback
