"""Per-device single-task lock (cross-platform).

For a Fixed Network device, only one log-collect task may run at a time.
Each fncollect process is separate, so we use an advisory OS file lock keyed
by the device identifier (e.g. its IP). Another process targeting the same
device fails fast with ``DeviceLockedError``.

Implementation is cross-platform:
  * POSIX (Linux/macOS): ``fcntl.flock``
  * Windows: ``msvcrt.locking``

Locked regions are released automatically when the process exits (even on a
crash), so a stale ``.lock`` file on disk never blocks future runs.
"""

from __future__ import annotations

import errno
import os
import re
from pathlib import Path


class DeviceLockedError(RuntimeError):
    """Raised when another task already holds the lock for this device."""


def _acquire(fd: int) -> bool:
    """Try a non-blocking exclusive lock; return True if acquired."""
    if os.name == "nt":  # Windows
        import msvcrt

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EDEADLK):
                return False
            raise
        return True
    # POSIX
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            return False
        raise
    return True


def _release(fd: int) -> None:
    try:
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


class DeviceLock:
    def __init__(self, lock_dir: str | Path, device_key: str) -> None:
        self.lock_dir = Path(lock_dir)
        self.device_key = device_key
        sanitized = re.sub(r"[^\w.-]", "_", device_key)
        self.path = self.lock_dir / f"{sanitized}.lock"
        self._fd: int | None = None

    def acquire(self) -> None:
        """Try to lock the device non-blocking; raise if another task runs."""
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o666)
        try:
            # ensure the file has at least one byte (robust locking on
            # Windows, which locks a byte region).
            if os.fstat(fd).st_size == 0:
                os.write(fd, b" ")
            os.lseek(fd, 0, os.SEEK_SET)
        except OSError:
            pass
        if not _acquire(fd):
            os.close(fd)
            raise DeviceLockedError(self.device_key) from None
        self._fd = fd

    def release(self) -> None:
        if self._fd is not None:
            _release(self._fd)
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> DeviceLock:  # noqa: PYI034
        self.acquire()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
