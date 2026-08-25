"""Vendor pack registry.

Vendors self-register when imported. Discovery walks the ``fncollect.vendors``
package for both modules and subpackages, importing each so its side-effect
registration runs. Adding a new vendor is just creating one directory with an
``__init__.py`` that registers itself.
"""

from __future__ import annotations

from pathlib import Path

from fncollect.vendor import Vendor


class VendorRegistry:
    def __init__(self) -> None:
        self._vendors: dict[str, type[Vendor]] = {}

    def register(self, cls: type[Vendor]) -> type[Vendor]:
        name = getattr(cls, "name", cls.__name__.lower())
        self._vendors[name] = cls
        return cls

    def get(self, name: str) -> type[Vendor]:
        try:
            return self._vendors[name]
        except KeyError:
            raise KeyError(
                f"unknown vendor {name!r}; known: {sorted(self._vendors)}"
            ) from None

    def names(self) -> list[str]:
        return sorted(self._vendors)


registry = VendorRegistry()


def discover_vendors() -> None:
    pkg_dir = Path(__file__).parent
    for entry in sorted(pkg_dir.iterdir()):
        stem = entry.name
        if stem in {"__init__", "registry"}:
            continue
        if entry.is_file() and entry.suffix == ".py":
            __import__(f"fncollect.vendors.{entry.stem}")
        elif entry.is_dir() and (entry / "__init__.py").exists():
            __import__(f"fncollect.vendors.{stem}")
