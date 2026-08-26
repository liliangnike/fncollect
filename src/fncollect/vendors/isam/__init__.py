"""Nokia ISAM (7360/7362) vendor pack.

Uses the real interactive SSH session with context-based CLI navigation.
Bare-bones but functional; extend the command catalog in
``config/vendors/isam/vendor.yml`` and add hardware models under
``vendors/isam/hardware/``.
"""

from __future__ import annotations

from fncollect.net import InteractiveSshSession
from fncollect.sessions import SSHSession
from fncollect.vendor import (
    BaseDevice,
    Device,
    DeviceInfo,
    DeviceRole,
    Vendor,
)
from fncollect.vendors.registry import registry


class IsamCliSession(InteractiveSshSession):
    default_port = 22
    prompt_pattern = r"typ:[\w-]+(?:>[^>#]+)*#"


class IsamDevice(BaseDevice):
    pass


class IsamVendor(Vendor):
    name = "isam"

    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            vendor=self.name,
            model="7360-ISAM",
            ip="0.0.0.0",
            role=DeviceRole.OLT,
            transport="ssh",
            session_type="cli",
        )

    def session_types(self) -> dict[str, type[SSHSession]]:
        return {"cli": IsamCliSession}

    def create_hardware(self, info: DeviceInfo, session) -> Device:
        return IsamDevice(info, session)

    def registered_actions(self) -> list[str]:
        return ["inventory", "run_commands"]


registry.register(IsamVendor)
