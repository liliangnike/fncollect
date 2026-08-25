"""Tests for the session/device-role/hardware-dispatch layer."""

import pytest

from fncollect.discovery import discover_hardware, normalize_type
from fncollect.sessions import (
    Endpoint,
    NetconfSession,
    SSHSession,
    TelnetSession,
)
from fncollect.vendor import DeviceRole
from fncollect.vendors.mock import MockDevice, MockVendor


def test_session_class_default_ports():
    assert SSHSession(Endpoint(hostname="h")).endpoint.port == 22
    assert NetconfSession(Endpoint(hostname="h")).endpoint.port == 830
    assert TelnetSession(Endpoint(hostname="h")).endpoint.port == 23


def test_session_type_sets_different_ssh_ports():
    from fncollect.vendors import nokia_fx

    vendor = nokia_fx.FxVendor()
    cli = vendor.create_session(Endpoint(hostname="h", session_type="cli"))
    tnd = vendor.create_session(Endpoint(hostname="h", session_type="tnd"))
    assert cli.endpoint.port == 22
    assert tnd.endpoint.port == 11130
    assert cli.endpoint.transport == "ssh"
    assert tnd.endpoint.transport == "ssh"


def test_explicit_port_overrides_session_default():
    from fncollect.vendors import nokia_fx

    vendor = nokia_fx.FxVendor()
    session = vendor.create_session(
        Endpoint(hostname="h", session_type="tnd", port=2222)
    )
    assert session.endpoint.port == 2222


def test_config_overrides_port_and_prompt():
    from fncollect.vendors import mock as mock_pkg

    vendor = mock_pkg.MockVendor()
    session = vendor.create_session(Endpoint(hostname="h", session_type="cli"))
    assert session.endpoint.port == 2222  # overridden by vendor.yml

    fx = _fx_vendor()
    tnd = fx.create_session(Endpoint(hostname="h", session_type="tnd"))
    assert tnd.endpoint.port == 11130
    assert tnd.prompt_pattern == "TND[>#]"


def test_unconfigured_session_uses_class_default():
    from fncollect.vendors import nokia_fx

    vendor = nokia_fx.FxVendor()
    # a session type with no config entry falls back to class default
    session = vendor.create_session(Endpoint(hostname="h", session_type="cli"))
    assert session.endpoint.port == 22


def _fx_vendor():
    from fncollect.vendors import nokia_fx

    return nokia_fx.FxVendor()


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
