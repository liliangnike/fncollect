"""Tests for actions, command catalog, concurrency, and reports."""


import pytest

from fncollect.actions import run_action
from fncollect.engine import ConcurrentRunner
from fncollect.report import build_and_write
from fncollect.vendors.mock import MockVendor


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


async def test_inventory_action_uses_vendor_catalog(run_ctx):
    vendor = MockVendor()
    device = vendor.create_device()
    await device.connect()
    result = await run_action("inventory", device, run_ctx, vendor)
    await device.disconnect()
    assert result.ok is True
    assert result.action == "inventory"
    assert len(result.artifacts) == 3  # catalog: show version, alarms, ont summary


async def test_run_commands_action_with_explicit_commands(run_ctx):
    vendor = MockVendor()
    device = vendor.create_device()
    await device.connect()
    result = await run_action(
        "run_commands", device, run_ctx, vendor, {"commands": ["show version", "show alarms"]}
    )
    await device.disconnect()
    assert result.ok is True
    assert len(result.artifacts) == 2


async def test_unknown_action_raises(run_ctx):
    from fncollect.actions import run_action

    vendor = MockVendor()
    device = vendor.create_device()
    with pytest.raises(KeyError):
        await run_action("does_not_exist", device, run_ctx, vendor)


async def test_concurrent_runner_runs_all_devices(run_ctx):
    vendor = MockVendor()
    devices = []
    for _ in range(4):
        dev = vendor.create_device()
        dev.info.ip = "127.0.0.1"
        devices.append(dev)

    from fncollect.actions import action_work

    runner = ConcurrentRunner(max_parallel=2)
    results = await runner.run(devices, action_work(vendor, "inventory"), run_ctx)
    assert len(results) == 4
    assert all(r.ok for r in results)
    for r in results:
        assert len(r.artifacts) == 3


async def test_reports_written(run_ctx):
    summary = {
        "total": 1,
        "ok": 1,
        "failed": 0,
        "devices": [
            {"device": "127.0.0.1", "ok": True, "action": "inventory",
             "artifacts": ["a.txt"]},
        ],
    }
    paths = build_and_write(run_ctx, summary, {"vendor": "mock"})
    assert paths["summary"].exists()
    assert paths["results"].exists()
    assert paths["csv"].exists()
    text = paths["summary"].read_text()
    assert "inventory" in text and "127.0.0.1" in text
    csv_text = paths["csv"].read_text()
    assert "device,action,ok" in csv_text
