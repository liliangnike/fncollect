"""Per-device single-task lock.

For a Fixed Network device, only one log-collect task may run at a time.
Each fncollect process is separate, so we use an advisory OS file lock
(``fcntl.flock``) keyed by the device identifier (e.g. its IP). Another
process targeting the same device fails fast with ``DeviceLockedError``.

``flock`` locks are released automatically when the process exits (even on
crash), so a stale ``.lock`` file on disk never blocks future runs.
"""

from __future__ import annotations

import fcntl
import re
from pathlib import Path


class DeviceLockedError(RuntimeError):
    """Raised when another task already holds the lock for this device."""


class DeviceLock:
    def __init__(self, lock_dir: str | Path, device_key: str) -> None:
        self.lock_dir = Path(lock_dir)
        self.device_key = device_key
        sanitized = re.sub(r"[^\w.-]", "_", device_key)
        self.path = self.lock_dir / f"{sanitized}.lock"
        self._fd = None

    def acquire(self) -> None:
        """Try to lock the device non-blocking; raise if another task runs."""
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        fd = open(self.path, "w")  # noqa: SIM115 - handle intentionally kept open for flock
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fd.close()
            raise DeviceLockedError(self.device_key) from None
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            try:
                fcntl.flock(self._fd, fcntl.LOCK_UN)
            except OSError:
                pass
            self._fd.close()
            self._fd = None

    def __enter__(self) -> DeviceLock:  # noqa: PYI034
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
