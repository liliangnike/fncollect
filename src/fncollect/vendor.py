"""Abstract interfaces for fncollect.

A *vendor* is a collection of device types that share a command dialect,
prompt conventions and login behaviour. A *device* is a concrete box the
tool talks to; an *action* is one unit of work (inventory, log collection,
cutthrough, ...) that a device can perform.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class DeviceConnectionError(RuntimeError):
    """Raised when a device cannot be reached or authenticated."""


class CommandError(RuntimeError):
    """Raised when a command on a device fails."""


@dataclass
class CommandResult:
    command: str
    output: str
    exit_code: int = 0
    duration_sec: float = 0.0


@dataclass
class DeviceInfo:
    vendor: str
    model: str
    ip: str
    extra: dict[str, Any] = field(default_factory=dict)


class Device(ABC):
    """A single box to collect from."""

    @abstractmethod
    async def connect(self, credentials: dict[str, str]) -> None:
        """Open a session to the device."""

    @abstractmethod
    async def exec_cmd(self, command: str) -> CommandResult:
        """Run one command and return its output."""

    @abstractmethod
    async def collect(self, command: str) -> CommandResult:
        """Alias of exec_cmd used by collection steps."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the session and release resources."""


class Action(ABC):
    """A unit of work performable against a device."""

    @abstractmethod
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def run(self, device: Device, config: Any, **kwargs: Any) -> dict[str, Any]:
        """Execute the action and return a result summary."""


class Vendor(ABC):
    """A family of devices sharing dialect and behaviour."""

    name: str = "abstract"

    @abstractmethod
    def device_info(self) -> DeviceInfo:
        """Describe the vendor (model, ip) for device creation."""

    @abstractmethod
    def create_device(self, info: DeviceInfo) -> Device:
        """Create a device object for this vendor from its info."""

    def registered_actions(self) -> list[str]:
        return []
