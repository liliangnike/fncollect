"""Generic, vendor-agnostic device operations.

The whole framework is three generic operation kinds, each described in YAML
and run by a single dispatcher, reusing the value-processor library and the
run context:

  * ``exec``       -- just run a command (and save its output as an artifact)
                       -> the "execution" framework (also covered by the DCP
                       engine).
  * ``get``        -- run a command, process its output with a named parser,
                       and extract exact value(s) -> the "data
                       retrieval/extraction" framework.
  * ``configure``  -- run one or more config commands, optionally verifying
                       the applied result -> the "configuration" framework
                       (e.g. configure an ONT from the OLT).

A vendor expresses an operation as YAML; the engine turns it into actions
against the abstract device.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fncollect.processors import extract_values
from fncollect.session_ctx import RunContext
from fncollect.vendor import Device


class OperationError(RuntimeError):
    """Raised when an operation cannot complete."""


@dataclass
class OperationResult:
    type: str
    command: str = ""
    values: dict[str, Any] = field(default_factory=dict)
    ok: bool = True
    artifact: str | None = None
    error: str | None = None


async def run_operation(
    spec: dict[str, Any],
    device: Device,
    run: RunContext,
    context=None,
) -> OperationResult:
    """Execute one YAML operation spec against a device.

    Spec schema:
      * ``type``    : exec | get | configure (default exec)
      * ``command`` : the command (may be multi-line for context navigation)
      * ``get``     : ``{extract: [<value-processor specs>]}``
      * ``configure`` : ``{commands: [...], verify: [...]}``
      * ``save``    : optional artifact save path
    """
    op_type = spec.get("type", "exec")

    if op_type == "configure":
        return await _run_configure(spec, device, run, context)
    if op_type == "get":
        return await _run_get(spec, device, run, context)
    return await _run_exec(spec, device, run)


async def _run_exec(
    spec: dict[str, Any], device: Device, run: RunContext
) -> OperationResult:
    command = spec.get("command")
    result = await device.exec_cmd(command)
    artifact = None
    if spec.get("save"):
        artifact = _save(run, spec["save"], result.output, "exec", {"command": command})
    return OperationResult(type="exec", command=command, artifact=artifact)


async def _run_get(
    spec: dict[str, Any], device: Device, run: RunContext, context
) -> OperationResult:
    command = spec.get("command")
    result = await device.exec_cmd(command)
    extract = (spec.get("get") or {}).get("extract", []) or spec.get("extract", [])
    values = extract_values(result.output, extract, context or _fallback_context())
    artifact = None
    if spec.get("save"):
        artifact = _save(run, spec["save"], result.output, "get", {"command": command})
    return OperationResult(type="get", command=command, values=values, artifact=artifact)


async def _run_configure(
    spec: dict[str, Any], device: Device, run: RunContext, context
) -> OperationResult:
    configure = spec.get("configure") or {}
    commands = configure.get("commands") or [spec.get("command")]
    verify = configure.get("verify") or []
    last = None
    for command in commands:
        last = await device.exec_cmd(command)
    # verify: re-read the output of the last command (or a fresh command if given)
    verified_ok = True
    if verify:
        if isinstance(verify, list):
            values = extract_values(last.output, verify, context or _fallback_context())
            verified_ok = bool(values)
        else:
            spec = {"type": "get", "command": verify.get("command", _first(configure, commands))}
            verified_ok = (await _run_get(spec, device, run, context)).ok
    return OperationResult(
        type="configure",
        command=_first(configure, commands),
        ok=verified_ok,
        artifact=None,
    )


def _first(configure: dict, commands: list) -> str:
    return commands[0] if commands else ""


def _save(run: RunContext, save: str, output: str, kind: str, meta: dict) -> str:
    path = run.write_text(Path(save).parent, Path(save).name, output, kind, meta)
    return str(path)


def _fallback_context():
    from fncollect.variables import VariableContext

    return VariableContext()


# Convenience wrappers for the three pillars --------------------------------

async def get_value(
    device: Device,
    command: str,
    extract: list[dict[Any, Any]],
    run: RunContext,
    context=None,
) -> OperationResult:
    return await run_operation(
        {"type": "get", "command": command, "get": {"extract": extract}},
        device,
        run,
        context,
    )


async def configure(
    device: Device,
    commands: list[str],
    run: RunContext,
    verify: list[dict] | None = None,
    context=None,
) -> OperationResult:
    spec: dict = {"type": "configure", "configure": {"commands": commands}}
    if verify:
        spec["configure"]["verify"] = verify
    return await run_operation(spec, device, run, context)
