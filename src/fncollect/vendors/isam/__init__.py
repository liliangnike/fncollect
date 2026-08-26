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


class IsamTndSession(InteractiveSshSession):
    """NT_TND provisioning session -- same OLT, non-standard SSH port."""

    default_port = 11130
    prompt_pattern = r"[\w-]+(?:>[^>#]+)*#"


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
        return {"cli": IsamCliSession, "tnd": IsamTndSession}

    def create_hardware(self, info: DeviceInfo, session) -> Device:
        return IsamDevice(info, session)

    def registered_actions(self) -> list[str]:
        return ["inventory", "ont_inventory", "run_commands"]

    def build_ont_cutthrough(self, olt: Device, target, run):
        """Assemble an OLT-gated ONT session using DCP-driven provisioning.

        The OLT side is configured through the NT_TND session by running a
        setup DCP (declare a debug vlan path, set the client IP, provision
        the GPON index, verify); restored by a teardown DCP on close.
        """
        from fncollect.config import guess_project_root
        from fncollect.cutthrough import DcpCutthroughProvider, OntCutthroughSession
        from fncollect.dcp import parse_dcp
        from fncollect.sessions import Endpoint

        root = guess_project_root()
        dcp_dir = root / "config" / "vendors" / "isam" / "dcps"

        tnd_info = DeviceInfo(
            vendor=self.name,
            model="NT-TND",
            ip=olt.info.ip,
            role=DeviceRole.OLT,
            session_type="tnd",
        )
        tnd_device = self.create_device(tnd_info)

        setup = parse_dcp((dcp_dir / "ont_cutthrough_setup.yml").read_text())
        teardown_path = dcp_dir / "ont_cutthrough_teardown.yml"
        teardown = (
            parse_dcp(teardown_path.read_text()) if teardown_path.exists() else None
        )
        provider = DcpCutthroughProvider(tnd_device, run, setup, teardown)

        endpoint = Endpoint(
            hostname=target.serial, transport="ssh", session_type="cli"
        )
        return OntCutthroughSession(endpoint, olt, provider, target, IsamCliSession)


registry.register(IsamVendor)
