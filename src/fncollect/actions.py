"""Semantic actions and the action engine.

An *action* is a named unit of work against a device (inventory, run a set of
commands / on-demand commands, collect, ...), implemented as a class and
registered in ``ActionRegistry``. ``run_action`` resolves a vendor's command
catalog and executes the action, saving outputs into the run context.

This mirrors the "action handler" model of a troubleshooting assistant while
keeping the core generic and vendor-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fncollect.session_ctx import RunContext
from fncollect.vendor import Device, Vendor


@dataclass
class ActionResult:
    action: str
    device: str
    ok: bool
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None


class Action(ABC):
    """A named unit of work against a device."""

    name: str = ""

    @abstractmethod
    async def run(
        self,
        device: Device,
        run: RunContext,
        vendor: Vendor,
        params: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Execute the action, saving outputs into the run context."""


class CommandBatchAction(Action):
    """Run an ordered list of commands and save each output as an artifact.

    Used to implement inventory collection and generic on-demand command
    execution (the ngalexx "ODC"/mass-exec equivalent).
    """

    subdir: str = "commands"

    async def run(
        self,
        device: Device,
        run: RunContext,
        vendor: Vendor,
        params: dict[str, Any] | None = None,
    ) -> ActionResult:
        params = params or {}
        commands = params.get("commands")
        if commands is None:
            commands = vendor.resolve_action_commands(self.name)
        if not commands:
            return ActionResult(
                action=self.name,
                device=device.info.ip,
                ok=False,
                error=f"no commands defined for action {self.name!r}",
            )

        placed: list[str] = []
        for command in commands:
            try:
                result = await device.exec_cmd(command)
            except Exception as exc:  # noqa: BLE001 - surface per-command failure
                return ActionResult(
                    action=self.name,
                    device=device.info.ip,
                    ok=False,
                    error=f"{command!r} failed: {exc}",
                )
            path = run.write_text(
                Path(self.subdir),
                _filename(command, idx=len(placed)),
                result.output,
                self.name,
                {"command": command},
            )
            placed.append(str(path))
        return ActionResult(action=self.name, device=device.info.ip, ok=True, artifacts=placed)


class InventoryAction(CommandBatchAction):
    name = "inventory"
    subdir = "inventory"


class RunCommandsAction(CommandBatchAction):
    """On-demand command execution (ODC equivalent)."""

    name = "run_commands"
    subdir = "commands"


def _filename(command: str, idx: int) -> str:
    base = "".join(ch if (ch.isalnum() or ch in "._-") else "_" for ch in command)
    base = base[:60] or "command"
    return f"{idx:02d}_{base}.txt" if idx else f"00_{base}.txt"


class ActionRegistry:
    def __init__(self) -> None:
        self._actions: dict[str, type[Action]] = {}

    def register(self, cls: type[Action]) -> type[Action]:
        self._actions[cls.name] = cls
        return cls

    def get(self, name: str) -> type[Action]:
        try:
            return self._actions[name]
        except KeyError:
            raise KeyError(f"unknown action {name!r}; known: {sorted(self._actions)}") from None

    def names(self) -> list[str]:
        return sorted(self._actions)


registry = ActionRegistry()
registry.register(InventoryAction)
registry.register(RunCommandsAction)


async def run_action(
    name: str,
    device: Device,
    run: RunContext,
    vendor: Vendor,
    params: dict[str, Any] | None = None,
) -> ActionResult:
    """Invoke a registered action against a device."""
    action_cls = registry.get(name)
    action = action_cls()
    return await action.run(device, run, vendor, params)


def action_work(vendor: Vendor, action_name: str):
    """Return a ``ConcurrentRunner`` work function running a named action."""
    from fncollect.engine import DeviceResult

    async def work(device: Device, run: RunContext, params: dict[str, Any]):
        result = await run_action(action_name, device, run, vendor, params)
        return DeviceResult(
            device=device.info.ip,
            ok=result.ok,
            action=result.action,
            artifacts=result.artifacts,
            error=result.error,
        )

    return work
