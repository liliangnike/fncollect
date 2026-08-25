"""Exemplar Nokia FX-style vendor pack (CLI dialect stub).

Illustrates the Vendor/Session/Device contract a real pack would fill in with
paramiko/aiossh adapters behind the same interface. In particular it shows
that different *session types* to the same box can use different SSH ports
and prompts (e.g. ISAM_CLI on 22 vs NT_TND on 11130).
"""

from __future__ import annotations

from fncollect.discovery import discover_hardware
from fncollect.sessions import (  # noqa: F401
    CommandResult,
    Endpoint,
    Session,
    SSHSession,
)
from fncollect.vendor import (
    BaseDevice,
    Device,
    DeviceInfo,
    DeviceRole,
    Vendor,
)
from fncollect.vendors.registry import registry


class FxCLISession(SSHSession):
    """Console/CLI session -- standard SSH port 22."""

    default_port = 22
    prompt_pattern = r"\w+[>#]"


class FxTndSession(SSHSession):
    """TND (network termination daemon) session -- non-standard SSH port."""

    default_port = 11130
    prompt_pattern = r"TND[>#]"


class FxDevice(BaseDevice):
    pass


class FxOLT(FxDevice):
    role = DeviceRole.OLT


class FxLT(FxDevice):
    role = DeviceRole.LT


class FxVendor(Vendor):
    name = "nokia_fx"

    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            vendor=self.name,
            model="OLT-FX",
            ip="0.0.0.0",
            role=DeviceRole.OLT,
            transport="ssh",
            session_type="cli",
        )

    def session_types(self) -> dict[str, type[Session]]:
        return {
            "cli": FxCLISession,
            "tnd": FxTndSession,
        }

    def create_hardware(self, info: DeviceInfo, session: Session) -> Device:
        hardware_cls = discover_hardware(
            "fncollect.vendors.nokia_fx", info.hardware_type or "", FxDevice
        )
        chosen: type = hardware_cls or FxDevice
        device = chosen(info, session)
        device.role = info.role
        return device

    def registered_actions(self) -> list[str]:
        return ["inventory", "log_collection"]


registry.register(FxVendor)
