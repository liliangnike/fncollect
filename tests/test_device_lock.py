"""Tests for the per-device single-task lock."""

import pytest

from fncollect.device_lock import DeviceLock, DeviceLockedError


def test_lock_prevents_concurrent(tmp_path):
    a = DeviceLock(tmp_path, "10.10.10.10")
    b = DeviceLock(tmp_path, "10.10.10.10")
    with a, pytest.raises(DeviceLockedError):
        b.acquire()
    # released -> re-acquirable
    b.acquire()
    b.release()


def test_lock_is_keyed_by_device(tmp_path):
    a = DeviceLock(tmp_path, "10.10.10.10")
    other = DeviceLock(tmp_path, "10.10.10.11")
    with a:
        other.acquire()  # different device unaffected
        other.release()
