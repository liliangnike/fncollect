"""Mock vendor pack: deterministic, in-memory sessions/devices for tests/demos."""

from __future__ import annotations

import asyncio

from fncollect.cutthrough import CutthroughProvider, OntAccess, OntTarget
from fncollect.discovery import discover_hardware
from fncollect.ont import ont_device_for
from fncollect.sessions import CommandResult, Endpoint, Session
from fncollect.vendor import (
    BaseDevice,
    Device,
    DeviceInfo,
    DeviceRole,
    Vendor,
)
from fncollect.vendors.registry import registry

_RESPONSES: dict[str, str] = {
    "show version": "Model: mock-OLT-1000\nSoftware: 1.2.3",
    "show alarms": "No active alarms",
    "show ont summary": "ONT 1: active\nONT 2: active\n",
}


class MockSession(Session):
    """In-memory session that returns canned responses."""

    default_port = 22

    def __init__(self, endpoint: Endpoint) -> None:
        super().__init__(endpoint)
        self.connected = False

    async def connect(self) -> None:
        await asyncio.sleep(0)
        self.connected = True

    async def exec_cmd(self, command: str) -> CommandResult:
        await asyncio.sleep(0)
        output = _RESPONSES.get(command, f"no mock response for: {command}")
        return CommandResult(command=command, output=output)

    async def close(self) -> None:
        self.connected = False


class MockDevice(BaseDevice):
    """Base mock device; subclasses specialise by role."""


class MockOLT(MockDevice):
    role = DeviceRole.OLT


class MockONTMock(MockDevice):
    role = DeviceRole.ONT


class MockVendor(Vendor):
    name = "mock"

    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            vendor=self.name,
            model="mock-OLT-1000",
            ip="127.0.0.1",
            role=DeviceRole.OLT,
            transport="mock",
        )

    def session_types(self) -> dict[str, type[Session]]:
        return {
            "default": MockSession,
            "cli": MockSession,
            "tnd": MockSession,
            "ont": MockSession,
        }

    def create_hardware(self, info: DeviceInfo, session: Session) -> Device:
        hardware_cls = discover_hardware(
            "fncollect.vendors.mock", info.hardware_type or "", MockDevice
        )
        chosen: type = hardware_cls or MockDevice
        device = chosen(info, session)
        device.role = info.role
        return device

    def cutthrough_provider(self) -> CutthroughProvider:
        return MockCutthroughProvider()

    def _ont_inner_session_class(self) -> type[Session]:
        return MockSession

    def create_ont(self, access, session: Session) -> Device:
        info = DeviceInfo(
            vendor=self.name,
            model=access.serial,
            ip=access.ip,
            role=DeviceRole.ONT,
            session_type="ont",
            extra={"chipset": access.chipset},
        )
        return ont_device_for(access.chipset, info, session)

    def registered_actions(self) -> list[str]:
        return ["inventory"]


class MockCutthroughProvider(CutthroughProvider):
    """Mock provider: 'prepares' the OLT by recording the call, then hands
    back an ephemeral ONT session address in the mock range."""

    def __init__(self) -> None:
        self.prepare_calls: list[OntTarget] = []
        self.restore_calls: list[OntTarget] = []

    async def prepare(self, olt: Device, target: OntTarget) -> OntAccess:
        await asyncio.sleep(0)
        self.prepare_calls.append(target)
        return OntAccess(
            ip="192.0.2.10",
            username="ontadmin",
            password="ontpw",
            serial=target.serial,
            chipset=target.chipset,
        )

    async def restore(self, olt: Device, target: OntTarget) -> None:
        await asyncio.sleep(0)
        self.restore_calls.append(target)


registry.register(MockVendor)
