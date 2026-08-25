"""Transport/session abstraction for fncollect.

A *session* is how fncollect talks to a device over a given transport
(SSH, Telnet, NETCONF, ...). Each session encapsulates its own connection
endpoint (host/port/auth), prompt handling and command execution. Devices
compose a session rather than owning transport logic, so adding a new
transport (or a device that speaks a different protocol) never touches the
device or DCP code.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


class DeviceConnectionError(RuntimeError):
    """Raised when a session cannot be established or authenticated."""


class CommandError(RuntimeError):
    """Raised when a command on a session fails."""


@dataclass
class CommandResult:
    command: str
    output: str
    exit_code: int = 0
    duration_sec: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


# Default ports per transport.
DEFAULT_PORTS: dict[str, int] = {
    "ssh": 22,
    "telnet": 23,
    "netconf": 830,
    "mock": 0,
}


@dataclass
class Endpoint:
    """Where and how to reach a device."""

    hostname: str
    transport: str = "ssh"
    port: int | None = None
    username: str | None = None
    password: str | None = None

    def __post_init__(self) -> None:
        if self.port is None:
            self.port = DEFAULT_PORTS.get(self.transport)

    @property
    def address(self) -> str:
        return f"{self.transport}://{self.hostname}:{self.port}"


class Session(ABC):
    """A single logical connection to a device.

    Implementations must handle their own prompt matching and framing.
    """

    def __init__(self, endpoint: Endpoint) -> None:
        self.endpoint = endpoint

    @property
    def transport(self) -> str:
        return self.endpoint.transport

    @abstractmethod
    async def connect(self) -> None:
        """Open the connection and enter a known prompt state."""

    @abstractmethod
    async def exec_cmd(self, command: str) -> CommandResult:
        """Send a command and return its captured output."""

    @abstractmethod
    async def close(self) -> None:
        """Close the connection and release resources."""
