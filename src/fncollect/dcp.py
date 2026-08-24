"""DCP (Data Collection Procedure) engine.

A DCP is a declarative, YAML-defined collection procedure. The engine runs
each step against a device and records the captured output as artifacts in
the run context.

The base engine supports plain command steps. Meta-operations (loop, wait,
skip, and command templating) are implemented in
``apply_meta_operation`` which is intentionally incomplete and is a
learning exercise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from fncollect.session_ctx import RunContext
from fncollect.vendor import CommandError, Device

STEP_META_OPS = ("loop", "wait", "skip")


@dataclass
class DcpStep:
    id: str
    command: str | None = None
    action: str | None = None
    save: str | None = None
    loop: dict[str, Any] | None = None
    wait: float | None = None
    skip: bool | None = False


@dataclass
class DcpDefinition:
    name: str
    vendor: str
    steps: list[DcpStep] = field(default_factory=list)

    def resolve_step(self, idx: int) -> DcpStep:
        return self.steps[idx]


def parse_dcp(raw: str | dict[str, Any]) -> DcpDefinition:
    if isinstance(raw, str):
        raw = yaml.safe_load(raw)
    steps = [DcpStep(**step) for step in raw.get("steps", [])]
    return DcpDefinition(
        name=raw.get("name", "unnamed"),
        vendor=raw.get("vendor", ""),
        steps=steps,
    )


def apply_meta_operations(step: DcpStep, context: dict[str, Any]) -> bool:
    """Decide whether a step should run given its meta-operations.

    Currently only evaluates ``skip``. Support for ``loop`` (repeat a step
    over a list of context values) and ``wait`` (delay before execution) is
    TODO -- see the failing tests.
    """
    return not step.skip


async def execute_dcp(
    dcp: DcpDefinition,
    device: Device,
    run: RunContext,
    *,
    max_steps: int = 100,
    progress=None,
) -> dict[str, Any]:
    """Run every step in a DCP against a device, saving outputs."""
    results: dict[str, Any] = {"steps": []}
    for idx, step in enumerate(dcp.steps):
        if idx >= max_steps:
            break
        if not apply_meta_operations(step, {"index": idx}):
            results["steps"].append({"id": step.id, "skipped": True})
            continue
        try:
            result = await device.exec_cmd(step.command) if step.command else None
            placed = None
            if step.save and result is not None:
                placed = run.write_text(
                    Path(step.save).parent,
                    Path(step.save).name,
                    result.output,
                    "dcp",
                    {"dcp": dcp.name, "step": step.id},
                )
            results["steps"].append(
                {"id": step.id, "ok": True, "artifact": str(placed) if placed else None}
            )
        except CommandError as exc:
            results["steps"].append({"id": step.id, "ok": False, "error": str(exc)})
    return results


def make_runner(device: Device, run: RunContext):
    async def runner(dcp: DcpDefinition) -> dict[str, Any]:
        return await execute_dcp(dcp, device, run)

    return runner
