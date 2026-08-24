"""Exemplar vendor pack showing how a real vendor would be modelled.

This is intentionally a thin, command-dialect demonstration (no real device
protocols are implemented). It exists to illustrate the Vendor/Device/Action
contract that a real pack (e.g. a GPON CLI dialect) would fill in, backed by
paramiko/aiossh adapters behind the same interface.
"""

from __future__ import annotations

from fncollect.vendor import CommandResult, Device, DeviceInfo, Vendor


class FxDevice(Device):
    def __init__(self, info: DeviceInfo) -> None:
        self.info = info

    async def connect(self, credentials: dict[str, str]) -> None:
        # TODO: open a real SSH/Telnet/NETCONF session via an adapter.
        return None

    async def exec_cmd(self, command: str) -> CommandResult:
        # TODO: wrap a real transport to issue the command.
        raise NotImplementedError("transport adapter not wired yet")

    async def collect(self, command: str) -> CommandResult:
        return await self.exec_cmd(command)

    async def disconnect(self) -> None:
        return None


class FxVendor(Vendor):
    name = "nokia_fx"

    def device_info(self) -> DeviceInfo:
        return DeviceInfo(vendor=self.name, model="OLT-FX", ip="0.0.0.0")

    def create_device(self, info: DeviceInfo) -> Device:
        return FxDevice(info)

    def registered_actions(self) -> list[str]:
        return ["inventory", "log_collection"]
