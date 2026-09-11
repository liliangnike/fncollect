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


def test_procedure_catalog_has_default_collection():

    vendor = IsamVendor()
    names = vendor.list_procedures()
    for name in ("default_collect", "nt_tnd_default_collect", "lt_tnd_default_collect"):
        assert name in names
    dcp = vendor.load_procedure("nt_tnd_default_collect")
    assert dcp.steps and all(s.session == "tnd" or True for s in dcp.steps)


def test_default_collect_is_full_shelf():
    from pathlib import Path

    from fncollect.dcp import parse_dcp

    p = Path(guess_project_root()) / "config" / "vendors" / "isam" / "dcps" / "default_collect.yml"
    dcp = parse_dcp(p.read_text())
    assert dcp.name == "isam_default_collect"
    assert dcp.log_dir == "default_collect"
    assert len(dcp.steps) == 93
    sessions = {s.session for s in dcp.steps}
    assert sessions == {"cli", "tnd"}  # OLT CLI + NT/LT TND legs


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
