"""Tests for ONT cutthrough and SoC-chipset dispatch."""

import asyncio

import pytest

from fncollect.cutthrough import OntTarget
from fncollect.ont import (
    BroadcomOnt,
    MediaTekOnt,
    OntDevice,
    RealtekOnt,
    ont_device_for,
)
from fncollect.sessions import Endpoint
from fncollect.vendor import DeviceInfo, DeviceRole
from fncollect.vendors.mock import (
    MockCutthroughProvider,
    MockSession,
    MockVendor,
)


def _session():
    return MockSession(Endpoint(hostname="127.0.0.1"))


def _info(chipset: str = "generic") -> DeviceInfo:
    return DeviceInfo(
        vendor="mock", model="SN123", ip="192.0.2.10", role=DeviceRole.ONT
    )


@pytest.mark.parametrize(
    "chipset,expected",
    [
        ("realtek", RealtekOnt),
        ("mediatek", MediaTekOnt),
        ("bcm", BroadcomOnt),
        ("broadcom", BroadcomOnt),
        ("mtk", MediaTekOnt),
        ("unknown-soc", OntDevice),
    ],
)
def test_chipset_dispatch(chipset, expected):
    device = ont_device_for(chipset, _info(), _session())
    assert isinstance(device, expected)
    assert device.role == DeviceRole.ONT


@pytest.mark.asyncio
async def test_ont_cutthrough_prepares_olt_before_open():
    vendor = MockVendor()
    olt = vendor.create_device()
    provider = MockCutthroughProvider()
    target = OntTarget(serial="SN123", vlan=100, chipset="mediatek")

    session = vendor.build_ont_cutthrough_session(olt, target)
    session.provider = provider  # ensure we inspect the same provider

    assert len(provider.prepare_calls) == 0
    # exec before connect must fail (precondition not met)
    with pytest.raises(RuntimeError):
        await session.exec_cmd("show version")

    await session.connect()
    assert len(provider.prepare_calls) == 1
    assert provider.prepare_calls[0].serial == "SN123"
    # inner reaches the provisioned ONT address
    assert session.access.ip == "192.0.2.10"

    # build the chipset ONT device from the access
    ont = vendor.create_ont(session.access, session)
    assert isinstance(ont, MediaTekOnt)
    r = await ont.exec_cmd("show version")
    assert r.output

    await session.close()
    assert len(provider.restore_calls) == 1


@pytest.mark.asyncio
async def test_provider_prepare_restore_ordering():
    provider = MockCutthroughProvider()
    target = OntTarget(serial="SN1")
    orders = []

    async def prepare(olt, tgt):
        await asyncio.sleep(0)
        orders.append("prepare")
        return __import__("fncollect.cutthrough", fromlist=["OntAccess"]).OntAccess(
            ip="x"
        )

    async def restore(olt, tgt):
        await asyncio.sleep(0)
        orders.append("restore")

    provider.prepare, provider.restore = prepare, restore
    vendor = MockVendor()
    session = vendor.build_ont_cutthrough_session(vendor.create_device(), target)
    session.provider = provider
    await session.connect()
    await session.close()
    assert orders == ["prepare", "restore"]
