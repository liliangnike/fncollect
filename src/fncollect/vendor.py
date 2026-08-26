"""Abstract contracts for fncollect.

A *vendor* is a collection of device types that share a command dialect,
login behaviour and transport options. A *device* is a concrete box the tool
collects from, composed of a *session* (how to talk) and a *role* / hardware
type (what it is, e.g. OLT/NT/LT/ONT). An *action* is one unit of work a
device can perform.

Sessions, CommandResult and connection/command errors live in
``fncollect.sessions`` and are re-exported here for convenience.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from fncollect.sessions import (  # noqa: F401  (re-exported)
    CommandError,
    CommandResult,
    DeviceConnectionError,
    Endpoint,
    Session,
    SSHSession,
)


class DeviceRole(str, Enum):
    """What the device is within a fixed-network topology."""

    OLT = "olt"
    NT = "nt"
    LT = "lt"
    ONT = "ont"


@dataclass
class DeviceInfo:
    vendor: str
    model: str
    ip: str
    role: DeviceRole = DeviceRole.OLT
    hardware_type: str | None = None
    transport: str = "ssh"
    session_type: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class Device(ABC):
    """A single box to collect from.

    A device is identified by its role/hardware and talks through a session.
    """

    role: DeviceRole = DeviceRole.OLT

    def __init__(self, info: DeviceInfo, session: Session | None = None) -> None:
        self.info = info
        self._session = session

    @property
    def session(self) -> Session:
        if self._session is None:
            raise DeviceConnectionError(f"no session attached to device {self.info.ip}")
        return self._session

    @abstractmethod
    async def connect(self) -> None:
        """Open the session to the device."""

    @abstractmethod
    async def exec_cmd(self, command: str) -> CommandResult:
        """Run one command and return its output."""

    async def collect(self, command: str) -> CommandResult:
        return await self.exec_cmd(command)

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the session and release resources."""


class BaseDevice(Device):
    """Default Device implementation that delegates to a session."""

    def __init__(self, info: DeviceInfo, session: Session) -> None:
        super().__init__(info, session)
        self.role = info.role

    async def connect(self) -> None:
        await self.session.connect()

    async def exec_cmd(self, command: str) -> CommandResult:
        return await self.session.exec_cmd(command)

    async def disconnect(self) -> None:
        await self.session.close()


class Action(ABC):
    """A unit of work performable against a device."""

    @abstractmethod
    def name(self) -> str:
        return self.__class__.__name__

    @abstractmethod
    async def run(self, device: Device, config: Any, **kwargs: Any) -> dict[str, Any]:
        """Execute the action and return a result summary."""


class Vendor(ABC):
    """A family of devices sharing dialect, login and transports."""

    name: str = "abstract"

    @abstractmethod
    def device_info(self) -> DeviceInfo:
        """Describe a default device for this vendor."""

    @abstractmethod
    def create_hardware(
        self, info: DeviceInfo, session: Session
    ) -> Device:
        """Dispatch to the concrete hardware class for the device."""

    def cutthrough_provider(self) -> Any:
        """Return this vendor's ONT cutthrough provider, or None if it does
        not support gatewayed ONT sessions."""
        return None

    def create_ont(self, access: Any, session: Session) -> Device:
        """Create the chipset-specialised ONT device for a cutthrough access."""
        from fncollect.ont import ont_device_for

        info = DeviceInfo(
            vendor=self.name,
            model=access.serial,
            ip=access.ip,
            role=DeviceRole.ONT,
            session_type="ont",
            extra={"chipset": access.chipset},
        )
        return ont_device_for(access.chipset, info, session)

    def build_ont_cutthrough_session(self, olt: Device, target: Any) -> Session:
        """Convenience: wiring for a gatewayed ONT session on this vendor.

        Follows the precondition-gated flow: prepare OLT -> open ONT ->
        run -> restore.
        """
        from fncollect.cutthrough import OntCutthroughSession

        provider = self.cutthrough_provider()
        inner_cls = self._ont_inner_session_class()
        if provider is None or inner_cls is None:
            raise NotImplementedError(
                f"vendor {self.name!r} does not support ONT cutthrough"
            )
        endpoint = Endpoint(
            hostname=target.serial, transport="ont", session_type="ont"
        )
        return OntCutthroughSession(
            endpoint, olt, provider, target, inner_cls
        )

    def _ont_inner_session_class(self) -> type[Session] | None:
        """Session class used for the reachable ONT transport once the OLT
        is prepared. Subclasses that support cutthrough must override this."""
        return None

    def session_types(self) -> dict[str, type[Session]]:
        """Map of session-type name to session class for this vendor."""
        return {}

    def vendor_config(self) -> Any:
        """Load this vendor's declarative config (cached)."""
        if not hasattr(self, "_vendor_config"):
            from fncollect.config import VendorConfig, guess_project_root

            self._vendor_config = VendorConfig.load(self.name, guess_project_root())
        return self._vendor_config

    def resolve_profile(self, session_type: str | None) -> Any:
        """Return the SessionProfile overrides for a session type, if any."""
        config = self.vendor_config()
        if not config or not session_type:
            return None
        return config.sessions.get(session_type)

    def get_session_class(self, session_type: str | None) -> type[Session]:
        types = self.session_types()
        if session_type and session_type in types:
            return types[session_type]
        return types.get("default", next(iter(types.values()), SSHSession))

    def create_session(self, endpoint: Endpoint) -> Session:
        """Create a session for an endpoint.

        Precedence: explicitly-set ``endpoint.port`` > vendor config
        (``sessions.<type>.port``) > session class default.
        """
        explicit_port = endpoint.port  # None if the caller did not set one
        session_cls = self.get_session_class(endpoint.session_type)
        session = session_cls(endpoint)
        profile = self.resolve_profile(endpoint.session_type)
        if profile is not None:
            if explicit_port is None:
                session.apply_profile(port=profile.port, prompt=profile.prompt)
            else:
                session.apply_profile(prompt=profile.prompt)
        return session

    def create_device(
        self,
        info: DeviceInfo | None = None,
        session: Session | None = None,
        credentials: dict[str, str] | None = None,
    ) -> Device:
        """Convenience: build an info-derived session and dispatch to hardware."""
        info = info or self.device_info()
        cred = credentials or {}
        session = session or self.create_session(
            Endpoint(
                hostname=info.ip,
                transport=info.transport,
                session_type=info.session_type,
                username=cred.get("username"),
                password=cred.get("password"),
            )
        )
        return self.create_hardware(info, session)

    def registered_actions(self) -> list[str]:
        return []

    def resolve_action_commands(self, action: str) -> list[str]:
        """Return the command sequence for an action from the vendor's
        declarative command catalog (falls back to an empty list)."""
        config = self.vendor_config()
        if not config:
            return []
        return list(config.commands.get(action, []))
