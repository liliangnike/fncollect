"""Tests for the session/device-role/hardware-dispatch layer."""

import pytest

from fncollect.discovery import discover_hardware, normalize_type
from fncollect.sessions import Endpoint
from fncollect.vendor import DeviceRole
from fncollect.vendors.mock import MockDevice, MockVendor


def test_endpoint_default_port_by_transport():
    assert Endpoint(hostname="h", transport="ssh").port == 22
    assert Endpoint(hostname="h", transport="netconf").port == 830
    assert Endpoint(hostname="h", transport="telnet").port == 23


def test_vendor_creates_device_with_session():
    vendor = MockVendor()
    device = vendor.create_device()
    assert isinstance(device, MockDevice)
    assert device.info.ip == "127.0.0.1"
    assert device.info.role == DeviceRole.OLT


def test_vendor_dispatches_hardware_type():
    vendor = MockVendor()
    device = vendor.create_device(hardware_instance())
    assert isinstance(device, MockDevice)
    assert device.role == DeviceRole.OLT


def hardware_instance():
    from fncollect.vendor import DeviceInfo

    return DeviceInfo(
        vendor="mock", model="mock-OLT-1000", ip="127.0.0.1",
        hardware_type="MOCK_OLT",
    )


def test_discover_hardware_resolves_class():
    cls = discover_hardware("fncollect.vendors.mock", "MOCK_OLT", MockDevice)
    assert cls is not None
    assert issubclass(cls, MockDevice)


def test_discover_hardware_returns_none_for_unknown():
    assert discover_hardware("fncollect.vendors.mock", "NO_SUCH_BOARD", MockDevice) is None


def test_normalize_type_replaces_separators():
    assert normalize_type("ABC-1") == "ABC_1"


@pytest.mark.asyncio
async def test_mock_session_exec_cmd():
    from fncollect.vendors.mock import MockSession

    session = MockSession(Endpoint(hostname="127.0.0.1", transport="mock"))
    await session.connect()
    result = await session.exec_cmd("show version")
    assert "mock-OLT-1000" in result.output
    await session.close()


def test_unknown_vendor_raises():
    from fncollect.vendors.registry import registry

    with pytest.raises(KeyError):
        registry.get("does_not_exist")
