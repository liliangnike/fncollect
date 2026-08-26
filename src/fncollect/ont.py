"""ONT devices, specialised by management SoC/chipset.

An ONT's management plane runs on vendor-specific silicon (MediaTek, Broadcom,
Realtek, ...). Different chipsets speak different CLI dialects, so each is a
distinct device class. ``ont_device_for`` dispatches an ONT to the class for
its chipset (falling back to a generic ONT).
"""

from __future__ import annotations

from fncollect.sessions import Session
from fncollect.vendor import BaseDevice, DeviceInfo, DeviceRole


class OntDevice(BaseDevice):
    """An optical network terminal (ONT)."""

    chipset: str = "generic"

    def __init__(self, info: DeviceInfo, session: Session) -> None:
        super().__init__(info, session)
        self.role = DeviceRole.ONT


class RealtekOnt(OntDevice):
    chipset = "realtek"


class MediaTekOnt(OntDevice):
    chipset = "mediatek"


class BroadcomOnt(OntDevice):
    chipset = "bcm"


class BelizeOnt(OntDevice):
    chipset = "belize"


_CHIPSETS: dict[str, type[OntDevice]] = {
    "realtek": RealtekOnt,
    "mediatek": MediaTekOnt,
    "mtk": MediaTekOnt,
    "bcm": BroadcomOnt,
    "broadcom": BroadcomOnt,
    "belize": BelizeOnt,
}


def ont_device_for(
    chipset: str | None, info: DeviceInfo, session: Session
) -> OntDevice:
    cls = _CHIPSETS.get((chipset or "").lower())
    if cls is None:
        cls = OntDevice
    return cls(info, session)
