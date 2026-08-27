"""DCP (Data Collection Procedure) engine.

A DCP is a declarative, YAML-defined collection procedure. The engine runs
each step against a device, records captured output as artifacts, and drives
a typed variable context: values are parsed from command output (regex
extraction), computed as derived expressions, and substituted back into
commands and save paths via ``{{ name }}`` templating.

Meta-operations per step:
  * ``skip``      -- skip the step entirely.
  * ``condition`` -- gate the step on a boolean expression over the context.
  * ``wait``      -- sleep before executing the step.
  * ``loop``      -- repeat the step over a list of values (``{{ item }}``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from fncollect.session_ctx import RunContext
from fncollect.variables import (
    Parameter,
    VariableContext,
    VariableError,
    render,
    safe_eval,
)
from fncollect.vendor import CommandError, Device

STEP_META_OPS = ("loop", "wait", "skip", "condition")


@dataclass
class DcpStep:
    id: str
    command: str | None = None
    action: str | None = None
    save: str | None = None
    extract: list[dict] = field(default_factory=list)
    condition: str | None = None
    loop: dict[str, Any] | None = None
    wait: float | None = None
    skip: bool = False


@dataclass
class DcpDefinition:
    name: str
    vendor: str
    parameters: list[Parameter] = field(default_factory=list)
    derivations: list[dict] = field(default_factory=list)
    steps: list[DcpStep] = field(default_factory=list)

    def resolve_step(self, idx: int) -> DcpStep:
        return self.steps[idx]


def parse_dcp(raw: str | dict[str, Any]) -> DcpDefinition:
    if isinstance(raw, str):
        raw = yaml.safe_load(raw)
    parameters = [Parameter(**p) for p in raw.get("parameters", [])]
    steps = [DcpStep(**step) for step in raw.get("steps", [])]
    return DcpDefinition(
        name=raw.get("name", "unnamed"),
        vendor=raw.get("vendor", ""),
        parameters=parameters,
        derivations=raw.get("derivations", []),
        steps=steps,
    )


async def execute_dcp(
    dcp: DcpDefinition,
    device: Device,
    run: RunContext,
    *,
    max_steps: int = 100,
    seed_variables: dict[str, Any] | None = None,
    progress=None,
) -> dict[str, Any]:
    """Run every step in a DCP against a device, saving outputs."""
    context = VariableContext(dcp.parameters)
    for name, value in (seed_variables or {}).items():
        context.set(name, value, via="seed")

    results: dict[str, Any] = {"steps": []}
    bar = None
    if progress is not None:
        bar = progress.steps(dcp.name, len(dcp.steps))
    for idx, step in enumerate(dcp.steps):
        if idx >= max_steps:
            break
        if not _should_run(step, context):
            results["steps"].append({"id": step.id, "skipped": True})
            if bar:
                bar.update(1)
            continue
        await _maybe_wait(step)
        for item in _loop_items(step, context):
            if item is not None:
                context.set("item", item, via="loop")
            await _run_step(step, dcp, device, run, context, results)
        if bar:
            bar.update(1)

    if bar:
        bar.close()

    try:
        context.record_artifacts(dcp.name, run)
    except VariableError:
        pass
    return results


def _should_run(step: DcpStep, context: VariableContext) -> bool:
    """Evaluate the meta-operations that gate whether a step runs."""
    if step.skip:
        return False
    if step.condition:
        return bool(safe_eval(step.condition, context))
    return True


async def _maybe_wait(step: DcpStep) -> None:
    if step.wait:
        await asyncio.sleep(step.wait)


def _loop_items(step: DcpStep, context: VariableContext) -> list:
    """Resolve the loop iterable for a step, if any; else a single None item."""
    if not step.loop:
        return [None]
    items = step.loop.get("items")
    if isinstance(items, str) and context.has(items):
        value = context.get(items)
        return value if isinstance(value, list) else []
    if isinstance(items, list):
        return items
    return []


async def _run_step(
    step: DcpStep,
    dcp: DcpDefinition,
    device: Device,
    run: RunContext,
    context: VariableContext,
    results: dict[str, Any],
) -> None:
    try:
        rendered_command = render(step.command, context)
        result = (
            await device.exec_cmd(rendered_command)
            if rendered_command
            else None
        )
        if result is not None:
            _apply_extractions(step, result.output, context)
        _apply_derivations(dcp.derivations, context)

        placed = None
        if step.save and result is not None:
            save_path = render(step.save, context)
            if save_path == step.save and step.loop and context.has("item"):
                save_path = f"{save_path}-{context.get('item')}"
            placed = run.write_text(
                Path(save_path).parent,
                Path(save_path).name,
                result.output,
                "dcp",
                {
                    "dcp": dcp.name,
                    "step": step.id,
                    "variables": {
                        k: v
                        for k, v in context.snapshot().items()
                        if _referenced(step, k)
                    },
                },
            )
        results["steps"].append(
            {
                "id": step.id,
                "ok": True,
                "item": context.get("item") if step.loop else None,
                "artifact": str(placed) if placed else None,
            }
        )
    except (CommandError, VariableError) as exc:
        results["steps"].append({"id": step.id, "ok": False, "error": str(exc)})


def _apply_extractions(step: DcpStep, output: str, context: VariableContext) -> None:
    from fncollect.processors import extract_values

    values = extract_values(output, step.extract, context)
    for name, value in values.items():
        context.set(name, value, via="extract")


def _apply_derivations(
    derivations: list[dict], context: VariableContext
) -> None:
    changed = True
    while changed:
        changed = False
        for derivation in derivations:
            name = derivation["name"]
            if context.has(name):
                continue
            deps = derivation.get("from", [])
            if any(not context.has(d) for d in deps):
                continue
            value = safe_eval(derivation["expr"], context)
            context.set(name, value, via="derived")
            changed = True


def _referenced(step: DcpStep, name: str) -> bool:
    return (
        (step.command and name in step.command)
        or (step.save and name in step.save)
        or any(spec.get("name") == name for spec in step.extract)
    )


def make_runner(device: Device, run: RunContext):
    async def runner(dcp: DcpDefinition) -> dict[str, Any]:
        return await execute_dcp(dcp, device, run)

    return runner
