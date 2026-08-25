"""Exemplar Nokia FX-style vendor pack (CLI dialect stub).

Illustrates the Vendor/Session/Device contract a real pack would fill in with
paramiko/aiossh adapters behind the same interface.
"""

from __future__ import annotations

from fncollect.discovery import discover_hardware
from fncollect.sessions import CommandResult, Endpoint, Session
from fncollect.vendor import (
    BaseDevice,
    Device,
    DeviceInfo,
    DeviceRole,
    Vendor,
)
from fncollect.vendors.registry import registry


class FxSession(Session):
    async def connect(self) -> None:
        return None

    async def exec_cmd(self, command: str) -> CommandResult:
        raise NotImplementedError("transport adapter not wired yet")

    async def close(self) -> None:
        return None


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
            transport="cli",
        )

    def create_session(self, endpoint: Endpoint) -> Session:
        return FxSession(endpoint)

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
