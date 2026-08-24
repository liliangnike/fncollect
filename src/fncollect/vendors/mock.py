"""Mock vendor: a deterministic, in-memory device for tests and demos."""

from __future__ import annotations

import asyncio

from fncollect.vendor import CommandResult, Device, DeviceInfo, Vendor

_BANNER = "fncollect mock device"
_RESPONSES = {
    "show version": "Model: mock-OLT-1000\nSoftware: 1.2.3",
    "show alarms": "No active alarms",
    "show ont summary": "ONT 1: active\nONT 2: active\n",
}


class MockDevice(Device):
    def __init__(self, info: DeviceInfo) -> None:
        self.info = info
        self.connected = False

    async def connect(self, credentials: dict[str, str]) -> None:
        await asyncio.sleep(0)
        self.connected = True

    async def exec_cmd(self, command: str) -> CommandResult:
        await asyncio.sleep(0)
        output = _RESPONSES.get(command, f"no mock response for: {command}")
        return CommandResult(command=command, output=output)

    async def collect(self, command: str) -> CommandResult:
        return await self.exec_cmd(command)

    async def disconnect(self) -> None:
        self.connected = False


class MockVendor(Vendor):
    name = "mock"

    def device_info(self) -> DeviceInfo:
        return DeviceInfo(vendor=self.name, model="mock-OLT-1000", ip="127.0.0.1")

    def create_device(self, info: DeviceInfo) -> Device:
        return MockDevice(info)

    def registered_actions(self) -> list[str]:
        return ["inventory"]
