"""Run context: per-run directory and artifact manifest.

Each invocation produces a timestamped, id-suffixed directory under the
configured output root. Everything the tool collects or writes is recorded
into a machine-readable manifest.json so downstream tooling and AI can
consume results without knowing the exact layout.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fncollect.config import RunConfig


def sanitize(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]", "_", name)


@dataclass
class RunContext:
    config: RunConfig
    root: Path
    logger: logging.Logger = field(repr=False)
    session_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])

    def __post_init__(self) -> None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dir_name = sanitize(
            f"{self.config.session_dir_prefix}-{stamp}-{self.session_id}"
        )
        self.dir: Path = self.root / dir_name
        self.dir.mkdir(parents=True, exist_ok=True)
        self.device_root = self.dir / "devices"
        self.report_root = self.dir / "reports"
        self._manifest: dict[str, Any] = {
            "session_id": self.session_id,
            "started_at": stamp,
            "artifacts": [],
        }

    def record_meta(self, meta: dict[str, Any]) -> None:
        self._manifest.update(meta)

    def register_artifact(
        self,
        path: Path,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        entry: dict[str, Any] = {
            "path": str(path.relative_to(self.dir)),
            "kind": kind,
            "size": path.stat().st_size,
        }
        entry["sha256"] = _sha256(path)
        if metadata:
            entry.update(metadata)
        self._manifest["artifacts"].append(entry)

    def write_text(
        self,
        rel_dir: Path,
        filename: str,
        content: str,
        kind: str,
        metadata: dict[str, Any] | None = None,
    ) -> Path:
        target_dir = self.dir / rel_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        path = target_dir / sanitize(filename)
        path.write_text(content)
        self.register_artifact(path, kind, metadata)
        return path

    def append_session_log(
        self,
        command: str,
        output: str,
        session: str | None = None,
        exit_code: int = 0,
    ) -> Path:
        """Append one command and its output to a session log file.

        Mirrors ngalexx's device-session logs: every executed command and its
        captured output is preserved, with one log file per session type
        (e.g. ``device_session_cli.log`` for OLT CLI, ``device_session_tnd.log``
        for NT_TND). Falls back to ``device_session.log`` when no session name
        is known.
        """
        filename = "device_session.log"
        if session:
            filename = f"device_session_{sanitize(session)}.log"
        path = self.dir / filename
        with path.open("a", encoding="utf-8", errors="replace") as handle:
            handle.write(f">>> {command}\n")
            if output and not output.endswith("\n"):
                output = output + "\n"
            handle.write(output)
            handle.write(f"[exit {exit_code}]\n")
        return path

    def finalize(self, meta: dict[str, Any] | None = None) -> Path:
        if meta:
            self._manifest.update(meta)
        self._manifest["finished_at"] = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ"
        )
        manifest_path = self.dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(self._manifest, indent=2, sort_keys=True)
        )
        self.register_artifact(manifest_path, "manifest")
        return manifest_path

    def prune_old_runs(self) -> None:
        if not self.config.retention.enabled:
            return
        cutoff = datetime.now(timezone.utc).timestamp() - (
            self.config.retention.keep_days * 86400
        )
        for child in self.root.iterdir():
            if not child.is_dir():
                continue
            mtime = child.stat().st_mtime
            if mtime < cutoff:
                shutil.rmtree(child, ignore_errors=True)
                self.logger.info("pruned old run dir: %s", child)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()
