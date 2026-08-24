"""Base DCP engine tests (pass) and the meta-operations learning task.

The tests marked ``xfail`` describe behaviour that is not yet implemented.
They are YOUR assignment: implement ``loop``, ``wait`` and command
templating in ``fncollect/dcp.py`` and flip ``strict=False`` to ``True`` /
remove the marker once they pass.

What to implement:
  * ``wait``      : sleep before executing a step when ``step.wait`` is set.
  * `loop`        : repeat a step over a list of context values; render
                    ``{{ item }}`` in the command and derive a unique save
                    path (e.g. append "-a", "-b") so artifacts don't collide.
  * ``condition`` : gate a step on a boolean expression evaluated against the
                    variable context (``step.condition``), using
                    ``safe_eval`` from fncollect.variables.
"""

import asyncio
import time

import pytest

from fncollect.dcp import (
    DcpDefinition,
    DcpStep,
    execute_dcp,
    parse_dcp,
)
from fncollect.vendors.mock import MockVendor


class TimingMockVendor(MockVendor):
    def create_device(self, info):
        return TimingDevice(info)


class TimingDevice:
    def __init__(self, info):
        self._connect = False

    async def connect(self, credentials):
        self._connect = True

    async def exec_cmd(self, command):
        await asyncio.sleep(0)
        return type("R", (), {"output": f"out of {command}"})()

    async def collect(self, command):
        return await self.exec_cmd(command)

    async def disconnect(self):
        pass


@pytest.mark.asyncio
async def test_plain_steps_run_and_save(run_ctx):
    dcp = parse_dcp(
        """
name: basic_collect
vendor: mock
steps:
  - {id: s1, command: "show version", save: "inventory/version.txt"}
"""
    )
    vendor = MockVendor()
    device = vendor.create_device(vendor.device_info())
    results = await execute_dcp(dcp, device, run_ctx)
    assert results["steps"][0]["ok"] is True


@pytest.mark.asyncio
@pytest.mark.xfail(reason="learning task: wait not implemented", strict=False)
async def test_wait_step_delays_execution(run_ctx):
    dcp = DcpDefinition(
        name="wait_dcp",
        vendor="mock",
        steps=[DcpStep(id="s1", command="show version", wait=0.05)],
    )
    device = TimingDevice(None)
    start = time.monotonic()
    await execute_dcp(dcp, device, run_ctx)
    elapsed = time.monotonic() - start
    assert elapsed >= 0.04


@pytest.mark.asyncio
@pytest.mark.xfail(reason="learning task: loop+templating not implemented", strict=False)
async def test_loop_step_expands_artifacts(run_ctx):
    dcp = DcpDefinition(
        name="loop_dcp",
        vendor="mock",
        steps=[
            DcpStep(
                id="s1",
                command="show ont {{ item }}",
                save="ont/{{ item }}.txt",
                loop={"items": ["ont-1", "ont-2"]},
            )
        ],
    )
    mock = MockVendor()
    device = mock.create_device(mock.device_info())
    results = await execute_dcp(dcp, device, run_ctx)
    assert results["steps"][0]["ok"] is True
    assert len(run_ctx._manifest["artifacts"]) == 2


@pytest.mark.asyncio
@pytest.mark.xfail(reason="learning task: condition gating not implemented", strict=False)
async def test_condition_step_skips_on_false_expression(run_ctx):
    dcp = DcpDefinition(
        name="cond_dcp",
        vendor="mock",
        steps=[
            DcpStep(id="s1", command="show version", condition="model == 'absent'"),
            DcpStep(id="s2", command="show alarms"),
        ],
    )
    mock = MockVendor()
    device = mock.create_device(mock.device_info())
    results = await execute_dcp(dcp, device, run_ctx, seed_variables={"model": "x"})
    by_id = {s["id"]: s for s in results["steps"]}
    assert by_id["s1"]["skipped"] is True
    assert by_id["s2"]["ok"] is True
