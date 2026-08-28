"""Tests for the device inventory / bulk credentials (hosts.yml)."""


from fncollect import cli
from fncollect.config import HostsConfig


def test_host_config_defaults_and_override(tmp_path):
    p = tmp_path / "hosts.yml"
    p.write_text(
        """
defaults:
  username: isadmin
hosts:
  - {name: olt1, ip: 10.0.0.1, username: u1, password: p1}
"""
    )
    cfg = HostsConfig.load(p)
    assert cfg is not None
    merged = cfg.resolve("10.0.0.1", "isam")
    assert merged["username"] == "u1"
    assert merged["password"] == "p1"
    assert merged["vendor"] == "isam"  # host vendor set
    # an ip not listed falls back to defaults only
    other = cfg.resolve("10.0.0.99", "isam")
    assert other["username"] == "isadmin"
    assert "password" not in other


def test_ont_keyed_by_serial(tmp_path):
    p = tmp_path / "hosts.yml"
    p.write_text(
        """
defaults:
  username: isadmin
hosts:
  - {name: ont1, serial: ALCLF84C9CA0, username: ontadmin, password: p-ont}
"""
    )
    cfg = HostsConfig.load(p)
    merged = cfg.resolve("ALCLF84C9CA0", "isam")
    assert merged["username"] == "ontadmin"
    assert merged["password"] == "p-ont"
    # an IP that isn't listed does not pick up the serial-entry creds
    other = cfg.resolve("10.0.0.5", "isam")
    assert other["username"] == "isadmin"


def test_default_credentials_used_when_no_host_matches(tmp_path):
    p = tmp_path / "hosts.yml"
    p.write_text(
        """
default_credentials:
  username: isadmin
  password: defaultpass
hosts:
  - {name: olt1, ip: 10.0.0.1, username: u1, password: p1}
"""
    )
    cfg = HostsConfig.load(p)
    # unlisted device -> default credentials
    unlisted = cfg.resolve("10.0.0.77", "isam")
    assert unlisted["username"] == "isadmin"
    assert unlisted["password"] == "defaultpass"
    # listed device still overrides
    listed = cfg.resolve("10.0.0.1", "isam")
    assert listed["password"] == "p1"


def test_ont_uses_default_when_serial_unlisted(tmp_path):
    p = tmp_path / "hosts.yml"
    p.write_text(
        """
default_credentials:
  username: isadmin
  password: defaultpass
hosts:
  - {name: olt1, ip: 10.0.0.1, username: u1, password: p1}
"""
    )
    cfg = HostsConfig.load(p)
    merged = cfg.resolve("ALCLF84C9CA0", "isam")
    assert merged["username"] == "isadmin"
    assert merged["password"] == "defaultpass"


def test_host_matched_by_name(tmp_path):
    p = tmp_path / "hosts.yml"
    p.write_text(
        "hosts:\n  - {name: my-olt, ip: 10.0.0.1, username: u, password: p}\n"
    )
    cfg = HostsConfig.load(p)
    assert cfg.resolve("my-olt")["username"] == "u"


def test_load_missing_returns_none(tmp_path):
    assert HostsConfig.load(tmp_path / "nope.yml") is None


def test_mock_never_needs_credentials(tmp_path, monkeypatch):
    import fncollect.config

    monkeypatch.setattr(cli, "_interactive", lambda: False)
    # isolate from any real user/hosts.yml
    monkeypatch.setattr(fncollect.config, "guess_project_root", lambda: tmp_path)
    # mock vendor uses mock sessions; never prompts nor raises for missing creds
    creds = cli._resolve_device_credentials("127.0.0.1", "mock")
    assert isinstance(creds, dict)
    assert not cli._needs_credentials("mock")
