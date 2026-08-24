"""Vendor pack registry.

Vendors declare themselves and register under a name. This is the seam that
keeps fncollect vendor-agnostic: adding a new vendor means adding one module
to the ``fncollect.vendors`` package and registering it here.
"""

from __future__ import annotations

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
    from fncollect import vendors as _pkg  # triggers module side-effects

    for module_name in _dir_modules(_pkg.__path__[0]):
        __import__(f"fncollect.vendors.{module_name}")


def _dir_modules(path: str) -> list[str]:
    from pathlib import Path

    return [
        p.stem
        for p in Path(path).glob("*.py")
        if p.stem not in {"registry", "__init__"}
    ]
