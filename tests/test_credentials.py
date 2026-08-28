"""Tests for credential resolution / prompting logic."""

from fncollect import cli


def test_needs_credentials_only_for_real_vendors():
    assert cli._needs_credentials("isam") is True
    assert cli._needs_credentials("nokia_fx") is True
    assert cli._needs_credentials("mock") is False
    assert not cli._needs_credentials("")


def test_base_credentials_uses_flags_and_env(monkeypatch):
    monkeypatch.delenv("FNCOLLECT_USER", raising=False)
    monkeypatch.delenv("FNCOLLECT_PASSWORD", raising=False)
    assert cli._base_credentials("u", "p") == ("u", "p")
    assert cli._base_credentials(None, None) == (None, None)


def test_base_credentials_uses_env(monkeypatch):
    monkeypatch.setenv("FNCOLLECT_USER", "envu")
    monkeypatch.setenv("FNCOLLECT_PASSWORD", "envp")
    assert cli._base_credentials(None, None) == ("envu", "envp")


def test_no_prompt_for_mock_without_creds(monkeypatch):
    monkeypatch.delenv("FNCOLLECT_USER", raising=False)
    monkeypatch.delenv("FNCOLLECT_PASSWORD", raising=False)
    assert cli._credentials(None, None, "mock") == {"username": "", "password": ""}


def test_missing_creds_real_vendor_noninteractive_raises(monkeypatch):
    monkeypatch.setattr(cli, "_interactive", lambda: False)
    monkeypatch.delenv("FNCOLLECT_USER", raising=False)
    monkeypatch.delenv("FNCOLLECT_PASSWORD", raising=False)
    import pytest

    with pytest.raises(cli.CredentialsError):
        cli._credentials(None, None, "isam")


def test_prompts_when_interactive(monkeypatch):
    monkeypatch.delenv("FNCOLLECT_USER", raising=False)
    monkeypatch.delenv("FNCOLLECT_PASSWORD", raising=False)
    monkeypatch.setattr(cli, "_interactive", lambda: True)
    monkeypatch.setattr("builtins.input", lambda *a: "typeduser")
    monkeypatch.setattr(cli, "_masked_password", lambda *a: "typedpass")
    assert cli._credentials(None, None, "isam") == {
        "username": "typeduser",
        "password": "typedpass",
    }
