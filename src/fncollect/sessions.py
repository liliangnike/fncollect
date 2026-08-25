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


# Default ports per transport are carried by the corresponding Session
# class (SSHSession=22, TelnetSession=23, NetconfSession=830, and so on).


@dataclass
class Endpoint:
    """Where and how to reach a device.

    The ``port`` is filled by the Session that owns the connection (each
    session type knows its own default port). An explicitly-set ``port``
    always wins.
    """

    hostname: str
    transport: str = "ssh"
    port: int | None = None
    username: str | None = None
    password: str | None = None
    session_type: str | None = None

    @property
    def address(self) -> str:
        return f"{self.transport}://{self.hostname}:{self.port}"


class Session(ABC):
    """A single logical connection to a device.

    Implementations handle their own prompt matching and framing, and
    declare the default port (and prompt) characteristic of their session
    type -- e.g. an SSH CLI session on port 22 vs an SSH TND session on
    port 11130.
    """

    #: Default remote port for this specific session type.
    default_port: int = 22
    #: Regex used to detect the device prompt after commands.
    prompt_pattern: str = r"[>#$%]"

    def __init__(self, endpoint: Endpoint) -> None:
        if endpoint.port is None:
            endpoint.port = self.default_port
        self.endpoint = endpoint
        # Copy the class default onto the instance so it can be overridden
        # per-session (e.g. from config) without mutating the class.
        self.prompt_pattern = type(self).prompt_pattern

    def apply_profile(self, port: int | None = None, prompt: str | None = None) -> None:
        if port is not None:
            self.endpoint.port = port
        if prompt is not None:
            self.prompt_pattern = prompt

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


class SSHSession(Session):
    """Base SSH CLI session (port 22 by default).

    Concrete device SSH CLI sessions subclass this; those that share the
    SSH transport but use a different port (e.g. a TND session on 11130)
    override ``default_port`` (and usually ``prompt_pattern``).
    """

    default_port = 22

    async def connect(self) -> None:
        raise NotImplementedError("SSH transport adapter not wired yet")

    async def exec_cmd(self, command: str) -> CommandResult:
        raise NotImplementedError("SSH transport adapter not wired yet")

    async def close(self) -> None:
        return None


class TelnetSession(Session):
    default_port = 23

    async def connect(self) -> None:
        raise NotImplementedError("Telnet transport adapter not wired yet")

    async def exec_cmd(self, command: str) -> CommandResult:
        raise NotImplementedError("Telnet transport adapter not wired yet")

    async def close(self) -> None:
        return None


class NetconfSession(Session):
    default_port = 830

    async def connect(self) -> None:
        raise NotImplementedError("NETCONF transport adapter not wired yet")

    async def exec_cmd(self, command: str) -> CommandResult:
        raise NotImplementedError("NETCONF transport adapter not wired yet")

    async def close(self) -> None:
        return None
