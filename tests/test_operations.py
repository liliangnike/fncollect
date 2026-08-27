"""Tests for the generic operation framework (exec / get / configure)."""

import pytest

from fncollect.config import LoggingConfig, RunConfig
from fncollect.logging_setup import build_logger
from fncollect.operations import get_value, run_operation
from fncollect.session_ctx import RunContext
from fncollect.vendors.mock import MockVendor


@pytest.fixture
def run_ctx(tmp_path):
    return RunContext(
        RunConfig(output_dir="."),
        tmp_path,
        logger=build_logger(config=LoggingConfig()),
    )


@pytest.fixture
def device():
    vendor = MockVendor()
    return vendor.create_device()


async def test_exec_operation_runs_and_saves(run_ctx, device):
    await device.connect()
    result = await run_operation(
        {"type": "exec", "command": "show version", "save": "raw/version.txt"},
        device,
        run_ctx,
    )
    await device.disconnect()
    assert result.ok is True
    assert result.artifact is not None


async def test_get_operation_extracts_value(run_ctx, device):
    await device.connect()
    result = await get_value(
        device,
        "show version",
        [{"name": "model", "parser": "regex", "regex": r"Model: (.+)", "group": 1}],
        run_ctx,
    )
    await device.disconnect()
    assert result.type == "get"
    assert "mock-OLT-1000" in result.values["model"]


async def test_configure_operation_with_verify(run_ctx, device):
    await device.connect()
    result = await run_operation(
        {
            "type": "configure",
            "configure": {
                "commands": ["show version"],
                "verify": [{"name": "model", "parser": "regex", "regex": r"Model: (.+)", "group": 1}],
            },
        },
        device,
        run_ctx,
    )
    await device.disconnect()
    assert result.type == "configure"
    assert result.ok is True
