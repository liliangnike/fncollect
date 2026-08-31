"""Tests for the real interactive SSH session and ISAM vendor wiring."""

import pytest

paramiko = pytest.importorskip("paramiko")

from fncollect.config import VendorConfig, guess_project_root
from fncollect.net import InteractiveSshSession, enable_legacy_ssh
from fncollect.sessions import Endpoint
from fncollect.vendor import DeviceRole
from fncollect.vendors.isam import IsamVendor


def test_enable_legacy_ssh_reenables_ssh_rsa():
    enable_legacy_ssh()
    assert "ssh-rsa" in paramiko.Transport._preferred_keys


def test_isam_vendor_config_catalog():
    cfg = VendorConfig.load("isam", guess_project_root())
    assert cfg is not None
    assert "show system entry" in cfg.commands["inventory"]


def test_isam_device_uses_interactive_session():
    vendor = IsamVendor()
    session = vendor.create_session(
        Endpoint(hostname="10.0.0.1", session_type="cli", username="u", password="p")
    )
    assert isinstance(session, InteractiveSshSession)
    assert session.endpoint.port == 22


def test_isam_device_role():
    vendor = IsamVendor()
    device = vendor.create_device(credentials={"username": "u", "password": "p"})
    assert device.info.role == DeviceRole.OLT
