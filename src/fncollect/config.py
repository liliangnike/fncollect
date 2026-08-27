"""Configuration loading and validation for fncollect using Pydantic.

Config is resolved by layering:
    defaults -> fncollect.local.yml (user overrides) -> CLI flags
All resolved values are recorded into each run's run_meta.json for
reproducibility.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, field_validator


class LoggingConfig(BaseModel):
    level: str = "INFO"
    console: bool = True
    file: bool = True
    log_dir: str = "fncollect_out"
    max_bytes: int = 10 * 1024 * 1024
    backup_count: int = 5
    redact: list[str] = Field(default_factory=list)


class RetentionConfig(BaseModel):
    keep_days: int = 30
    enabled: bool = True


class RunConfig(BaseModel):
    output_dir: str = "fncollect_out"
    session_dir_prefix: str = "run"
    retention: RetentionConfig = Field(default_factory=RetentionConfig)
    lock_enabled: bool = True


class ConcurrencyConfig(BaseModel):
    max_parallel_devices: int = 4
    command_timeout_sec: float = 30.0


class SessionProfile(BaseModel):
    """Overridable connection characteristics for a session type.

    ``None`` values mean "fall back to the session class default".
    """

    port: int | None = None
    prompt: str | None = None


class VendorConfig(BaseModel):
    """Declarative description of a vendor pack (config/vendors/<name>/vendor.yml)."""

    vendor: str
    description: str = ""
    transport: str = "ssh"
    device_types: list[str] = Field(default_factory=list)
    sessions: dict[str, SessionProfile] = Field(default_factory=dict)
    actions: list[str] = Field(default_factory=list)
    commands: dict[str, list[str]] = Field(default_factory=dict)
    dcps: list[str] = Field(default_factory=list)
    probe: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def load(cls, name: str, project_root: Path) -> VendorConfig | None:
        path = project_root / "config" / "vendors" / name / "vendor.yml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text()) or {}
        data.setdefault("vendor", name)
        return cls.model_validate(data)


class ToolConfig(BaseModel):
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    run: RunConfig = Field(default_factory=RunConfig)
    concurrency: ConcurrencyConfig = Field(default_factory=ConcurrencyConfig)
    vendor: str = "mock"

    @classmethod
    def load(cls, path: Path | None = None) -> ToolConfig:
        data: dict[str, Any] = {}
        if path is not None and path.exists():
            data = yaml.safe_load(path.read_text()) or {}
        return cls.model_validate(data)

    @classmethod
    def load_defaults(cls, paths: list[Path]) -> ToolConfig:
        merged: dict[str, Any] = {}
        for path in paths:
            if path.exists():
                loaded = yaml.safe_load(path.read_text()) or {}
                deep_merge(merged, loaded)
        return cls.model_validate(merged)

    @field_validator("logging")
    @classmethod
    def _upper_level(cls, v: LoggingConfig) -> LoggingConfig:
        v.level = v.level.upper()
        return v


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge override into base (override wins)."""
    for key, value in override.items():
        if (
            key in base
            and isinstance(base[key], dict)
            and isinstance(value, dict)
        ):
            deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def available_config_paths(project_root: Path) -> list[Path]:
    return [
        project_root / "config" / "fncollect.yml",
        project_root / "user" / "fncollect.local.yml",
    ]


def guess_project_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent
