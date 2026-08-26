"""ONT cutthrough.

An ONT's management plane is not directly reachable: it is reached *through*
the OLT. Before any ONT session can open, the OLT side must be provisioned
(prepare a debug/vlan path, push the workstation client IP, register the
ONT serial, etc.) and often restored afterwards.

This module models that as a precondition-gated workflow:

    prepare (OLT-side provisioning)
        -> open ONT session (now reachable)
        -> run commands / collect
    restore (OLT-side cleanup, optional)

The precondition is enforced inside ``OntCutthroughSession.connect``: you
cannot reach the ONT until the OLT has been prepared.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from fncollect.sessions import CommandResult, Endpoint, Session
from fncollect.vendor import Device


@dataclass
class OntTarget:
    """The ONT we want to reach via the OLT."""

    serial: str
    vlan: int = 0
    client_ip: str = ""
    lt: str = ""
    pon: str = ""
    chipset: str = "generic"
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class OntAccess:
    """The reachable ONT session details produced by OLT-side provisioning."""

    ip: str
    username: str = ""
    password: str = ""
    serial: str = ""
    chipset: str = "generic"
    extra: dict[str, Any] = field(default_factory=dict)


class CutthroughProvider(ABC):
    """Per-vendor recipe for OLT-side provisioning/restore of an ONT session."""

    @abstractmethod
    async def prepare(self, olt: Device, target: OntTarget) -> OntAccess:
        """Provision the OLT so the ONT becomes reachable.

        This is the mandatory precondition for any ONT cutthrough session.
        Returns the details needed to open the ONT session.
        """

    async def restore(self, olt: Device, target: OntTarget) -> None:
        """Optionally undo OLT-side changes after the session closes (default: no-op)."""


class OntCutthroughSession(Session):
    """A session to an ONT that requires OLT-side preparation first.

    ``connect`` runs ``provider.prepare`` before opening the actual ONT
    transport, so the precondition ordering is enforced by the API.
    """

    default_port = 22

    def __init__(
        self,
        endpoint: Endpoint,
        olt: Device,
        provider: CutthroughProvider,
        target: OntTarget,
        inner_session_cls: type[Session],
    ) -> None:
        super().__init__(endpoint)
        self.olt = olt
        self.provider = provider
        self.target = target
        self._inner_cls = inner_session_cls
        self.access: OntAccess | None = None
        self._inner: Session | None = None
        self._restored = False

    async def connect(self) -> None:
        # PRECONDITION: the OLT must be provisioned first.
        self.access = await self.provider.prepare(self.olt, self.target)
        self._inner = self._inner_cls(
            Endpoint(
                hostname=self.access.ip,
                username=self.access.username,
                password=self.access.password,
            )
        )
        await self._inner.connect()

    async def exec_cmd(self, command: str) -> CommandResult:
        if self._inner is None:
            raise RuntimeError(
                "cannot exec_cmd on an unconnected ONT cutthrough session; "
                "call connect() first (OLT must be prepared)"
            )
        return await self._inner.exec_cmd(command)

    async def close(self) -> None:
        if self._inner is not None:
            await self._inner.close()
        if not self._restored:
            await self.provider.restore(self.olt, self.target)
            self._restored = True
