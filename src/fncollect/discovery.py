"""Hardware-type auto-discovery.

Mirrors the ngalexx approach of dispatching to a concrete hardware class by
import path, so that adding a new hardware board is a single-file change with
no core edits. Given a vendor package import path and a hardware type string,
this resolves and imports the matching class.

Convention: for vendor ``foo`` with hardware type ``ABC-1``, the class is
``fncollect.vendors.foo.hardware.ABC_1``.
"""

from __future__ import annotations

import importlib
import importlib.util
from typing import TypeVar

from fncollect.sessions import DeviceConnectionError

T = TypeVar("T")


def _snake(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def discover_hardware(
    vendor_module: str,
    hardware_type: str,
    base_cls: type[T],
) -> type[T] | None:
    """Resolve a concrete hardware class for a board type, if supported."""
    if not hardware_type:
        return None
    class_name = _snake(hardware_type)
    module_name = f"{vendor_module}.hardware.{_snake(hardware_type).lower()}"
    if importlib.util.find_spec(module_name) is None:
        return None
    module = importlib.import_module(module_name)
    cls = getattr(module, class_name, None)
    if cls is None or not issubclass(cls, base_cls):
        raise DeviceConnectionError(
            f"hardware type {hardware_type!r} is not a valid {base_cls.__name__}"
        )
    return cls


def normalize_type(hardware_type: str) -> str:
    return _snake(hardware_type)
