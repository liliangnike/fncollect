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
from pathlib import Path
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
    serial: str = ""
    version: str = ""
    chipset: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class Device(ABC):
    """A single box to collect from.

    A device is identified by its role/hardware and talks through a session.
    """

    role: DeviceRole = DeviceRole.OLT

    def __init__(self, info: DeviceInfo, session: Session | None = None) -> None:
        self.info = info
        self._session = session
        self.attributes: dict[str, Any] = dict(info.extra)

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

    # --- multi-session support (overridden by BaseDevice when a manager
    #     is attached). Defaults keep single-session devices working. ---

    def sessions(self) -> list[str]:
        return []

    def switch_session(self, alias: str) -> None:
        raise KeyError(f"no session {alias!r} on this device")

    async def exec_cmd_with_session(self, session: str, command: str) -> CommandResult:
        return await self.exec_cmd(command)

    async def get_values(self, command: str, extract: list[dict]) -> dict[str, Any]:
        """Generic read: run a command, process its output, return collected
        values keyed by name. ``extract`` items follow the value-processor
        schema (see fncollect.processors)."""
        from fncollect.processors import extract_values

        result = await self.exec_cmd(command)
        return extract_values(result.output, extract)

    async def configure(self, command: str, verify: list[dict] | None = None) -> bool:
        """Generic configure: run a command; optionally verify by re-reading
        output against ``verify`` value specs. Returns whether it applied."""
        result = await self.exec_cmd(command)
        if not verify:
            return result.exit_code == 0
        from fncollect.processors import extract_values

        values = extract_values(result.output, verify)
        return bool(values)

    @abstractmethod
    async def disconnect(self) -> None:
        """Close the session and release resources."""


class BaseDevice(Device):
    """Default Device implementation that delegates to a session."""

    def __init__(
        self, info: DeviceInfo, session: Session, session_manager=None
    ) -> None:
        super().__init__(info, session)
        self.role = info.role
        from fncollect.session_manager import SessionManager

        self._manager: SessionManager | None = session_manager

    async def connect(self) -> None:
        if self._manager is not None:
            await self._manager.connect_all()
            return
        await self.session.connect()

    def sessions(self) -> list[str]:
        return self._manager.aliases if self._manager else []

    def switch_session(self, alias: str) -> None:
        if self._manager is None:
            raise KeyError(f"no session {alias!r} on this device")
        self._manager.switch(alias)

    async def exec_cmd(self, command: str) -> CommandResult:
        if self._manager is not None:
            return await self._manager.exec_cmd(command)
        result = await self.session.exec_cmd(command)
        if not result.session:
            result.session = self.info.session_type or "default"
        return result

    async def exec_cmd_with_session(self, session: str, command: str) -> CommandResult:
        if self._manager is not None:
            return await self._manager.exec_cmd(command, session=session)
        result = await self.session.exec_cmd(command)
        if not result.session:
            result.session = session
        return result

    async def disconnect(self) -> None:
        if self._manager is not None:
            await self._manager.close_all()
            return
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
        device = self.create_hardware(info, session)
        # Multi-session devices (e.g. cli + tnd): attach a session manager so
        # procedures can switch the active session.
        if len(self.session_types()) >= 2 and isinstance(device, BaseDevice):
            device._manager = self.session_manager(info, cred)
        return device

    def session_manager(
        self, info: DeviceInfo, credentials: dict[str, str] | None = None
    ) -> Any:
        """Build a multi-session manager for a device with several session
        types (e.g. cli + tnd), so a procedure can switch the active session.

        Returns None when the vendor has only a single session type.
        """
        types = self.session_types()
        if len(types) < 2:
            return None
        from fncollect.session_manager import SessionManager

        cred = credentials or {}
        sessions = {}
        for name in types:
            endpoint = Endpoint(
                hostname=info.ip,
                transport=info.transport,
                session_type=name,
                username=cred.get("username"),
                password=cred.get("password"),
            )
            sessions[name] = self.create_session(endpoint)
        return SessionManager(sessions, default=info.session_type)

    def registered_actions(self) -> list[str]:
        return []

    def probe_definition(self) -> tuple[Any, dict[str, str]]:
        """Return (probe DCP, mappings) declared in the vendor config.

        ``probe`` in vendor.yml points at a YAML procedure whose extracted
        values are mapped onto DeviceInfo/attributes. Defaults to (None, {}).
        Loaded from YAML when present, else None sentinel.
        """
        config = self.vendor_config()
        if not config or not config.probe:
            return None, {}
        procedure = config.probe.get("procedure")
        dcp = None
        if procedure:
            from pathlib import Path

            from fncollect.config import guess_project_root
            from fncollect.dcp import parse_dcp

            path = Path(guess_project_root()) / "config" / "vendors" / self.name / "dcps" / Path(procedure).name
            if path.exists():
                dcp = parse_dcp(path.read_text())
        return dcp, dict(config.probe.get("mappings", {}))

    async def run_probe(self, device: Device, run) -> dict[str, str]:
        """Run the vendor's probe procedure and map values onto the device.

        Returns the mapped DeviceInfo/attribute summaries. This is the
        generic device-initialization method: run probe commands -> process
        output -> populate the abstract device.
        """
        mappings: dict[str, str]
        dcp, mappings = self.probe_definition()
        if dcp is None:
            return {}
        from fncollect.dcp import execute_dcp

        seed = {}  # could be seeded from CLI/credentials if needed
        await execute_dcp(dcp, device, run, seed_variables=seed)
        # read the recorded variable context back
        values = _read_probe_variables(run)
        applied: dict[str, str] = {}
        for var_name, target in mappings.items():
            if var_name not in values:
                continue
            if target.startswith("attributes."):
                device.attributes[target.split(".", 1)[1]] = values[var_name]
            elif hasattr(device.info, target):
                setattr(device.info, target, values[var_name])
            applied[var_name] = target
        return applied

    def resolve_action_commands(self, action: str) -> list[str]:
        """Return the command sequence for an action from the vendor's
        declarative command catalog (falls back to an empty list)."""
        config = self.vendor_config()
        if not config:
            return []
        return list(config.commands.get(action, []))

    def dcp_dir(self) -> Path:
        from pathlib import Path

        from fncollect.config import guess_project_root

        return Path(guess_project_root()) / "config" / "vendors" / self.name / "dcps"

    def list_procedures(self) -> dict[str, Path]:
        """Discover built-in YAML procedures for this vendor.

        Returns {name: path} from the vendor's dcps/ directory, plus the
        configured probe procedure. Names are the file stem (e.g. ``probe``).
        """

        procedures: dict[str, Path] = {}
        dcp_dir = self.dcp_dir()
        if dcp_dir.exists():
            for path in sorted(dcp_dir.glob("*.yml")):
                procedures[path.stem] = path
            for path in sorted(dcp_dir.glob("*.yaml")):
                procedures[path.stem] = path
        probe, _ = self.probe_definition()
        if probe is not None:
            procedures.setdefault("probe", probe)
        return procedures

    def load_procedure(self, name: str):
        """Load a built-in YAML procedure by name (case-insensitive)."""
        from fncollect.dcp import DcpDefinition, parse_dcp

        procedures = self.list_procedures()
        key = _match_procedure(procedures, name)
        if key is None:
            raise KeyError(
                f"unknown procedure {name!r} for vendor {self.name!r}; "
                f"known: {sorted(procedures)}"
            )
        proc = procedures[key]
        if isinstance(proc, DcpDefinition):
            return proc
        return parse_dcp(proc.read_text())


def _read_probe_variables(run) -> dict[str, Any]:
    """Read the variable context persisted by the DCP engine for a run."""
    import json

    try:
        path = run.dir / "variables" / "variables.json"
        if path.exists():
            return json.loads(path.read_text())
    except Exception:  # noqa: BLE001, S110
        pass
    return {}


def _match_procedure(procedures: dict[str, Path], name: str) -> str | None:
    lowered = name.lower()
    for key in procedures:
        if key.lower() == lowered:
            return key
    return None
