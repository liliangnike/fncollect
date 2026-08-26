"""Multi-device concurrent collection engine.

Runs a collection against many devices in parallel, bounded by a semaphore
(``max_parallel_devices``). Each device is handled by its own coroutine:
connect -> do work -> disconnect -> report. Results are aggregated so a run
can summarize success/failure per device.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Iterable
from dataclasses import dataclass, field
from typing import Any

from fncollect.session_ctx import RunContext
from fncollect.vendor import Device

log = logging.getLogger("fncollect.engine")


@dataclass
class DeviceResult:
    device: str
    ok: bool
    action: str = ""
    artifacts: list[str] = field(default_factory=list)
    error: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)


WorkFn = Callable[[Device, RunContext, dict[str, Any]], Awaitable[DeviceResult]]


class ConcurrentRunner:
    def __init__(self, max_parallel: int = 4) -> None:
        self.max_parallel = max_parallel

    def _rating(self) -> asyncio.Semaphore:
        return asyncio.Semaphore(self.max_parallel)

    async def run(
        self,
        devices: Iterable[Device],
        work: WorkFn,
        run: RunContext,
        params: dict[str, Any] | None = None,
    ) -> list[DeviceResult]:
        results: list[DeviceResult] = []
        semaphore = self._rating()

        async def _one(device: Device) -> DeviceResult:
            async with semaphore:
                try:
                    await device.connect()
                    result = await work(device, run, {**(params or {})})
                    return result
                except Exception as exc:  # noqa: BLE001
                    return DeviceResult(
                        device=device.info.ip, ok=False, error=str(exc)
                    )
                finally:
                    try:
                        await device.disconnect()
                    except Exception:  # noqa: BLE001
                        log.warning("disconnect failed for %s", device.info.ip)

        results = await asyncio.gather(*(_one(d) for d in devices))
        return list(results)

    @staticmethod
    def summarize(results: Iterable[DeviceResult]) -> dict[str, Any]:
        ok = sum(1 for r in results if r.ok)
        failed = sum(1 for r in results if not r.ok)
        return {
            "total": ok + failed,
            "ok": ok,
            "failed": failed,
            "devices": [
                {
                    "device": r.device,
                    "ok": r.ok,
                    "action": r.action,
                    "artifacts": r.artifacts,
                    "error": r.error,
                }
                for r in results
            ],
        }
