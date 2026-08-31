"""Progress bars for stages/steps/procedures/command executions.

Built on ``tqdm`` (for frame management / stacking) and styled to look like
a Linux package-installation progress bar: a fixed square-bracket bar with a
percentage that fills left-to-right with ``=`` and a guaranteed ``>`` tip at
the leading edge (e.g. ``[======>        ] 33%``).

Nested levels are rendered as stacked tqdm bars; inner bars collapse when
finished so the outer stage/step bars remain visible, like a detailed
install log.
"""

from __future__ import annotations

import sys

from tqdm import tqdm

BAR_WIDTH = 22
DESC_WIDTH = 34


def _render(desc: str, frac: float) -> str:
    """Build the full line: desc + percentage + ``[======>     ]`` bar."""
    if frac <= 0:
        seg = " " * BAR_WIDTH
    elif frac >= 1:
        seg = "=" * BAR_WIDTH
    else:
        filled = int(frac * BAR_WIDTH)
        seg = "=" * (filled - 1) + ">" + " " * (BAR_WIDTH - filled)
    return f"{desc:<{DESC_WIDTH}}{frac * 100:3.0f}%[{seg}]"


def _tty() -> bool:
    try:
        return bool(getattr(sys.stdout, "isatty", lambda: False)())
    except Exception:  # noqa: BLE001
        return False


class Progress:
    """One root device/procedure progress group with nested bars."""

    def __init__(self, enabled: bool | None = None, ncols: int = 80) -> None:
        if enabled is None:
            enabled = _tty()
        self.enabled = enabled
        self.ncols = ncols
        self._level = 0

    def _bar(self, desc: str, total: int, leave: bool, unit: str) -> tqdm:
        return tqdm(
            total=int(total),
            desc=desc,
            unit=unit,
            leave=leave,
            position=self._level,
            bar_format="{desc}",
            ncols=self.ncols,
            disable=not self.enabled,
        )

    def stage(self, name: str, total_steps: int) -> _Bar:
        """A stage bar (e.g. prepare/collect/post); advances per step."""
        bar = self._bar(f"({self._level}) {name}", total_steps, leave=True, unit="step")
        self._level += 1
        return _Bar(bar, self)

    def steps(self, name: str, total: int) -> _Bar:
        """A procedure/step bar; advances per command execution."""
        bar = self._bar(f"    {name}", total, leave=False, unit="cmd")
        return _Bar(bar, self)

    def command(self, name: str, total: int = 1) -> _Bar:
        bar = self._bar(f"        {name}", total, leave=False, unit="")
        return _Bar(bar, self)

    def down(self) -> None:
        if self._level > 0:
            self._level -= 1


class _Bar:
    def __init__(self, tq: tqdm, prog: Progress) -> None:
        self._tq = tq
        self._prog = prog
        self._desc = tq.desc or ""

    def _refresh(self) -> None:
        total = self._tq.total or 1
        frac = self._tq.n / total
        self._tq.set_description_str(_render(self._desc, frac), refresh=True)

    def update(self, n: int = 1) -> None:
        self._tq.update(n)
        self._refresh()

    def set_desc(self, text: str) -> None:
        self._desc = text
        self._refresh()

    def close(self) -> None:
        # redraw once at full before closing, so the final state is correct
        self._tq.n = self._tq.total
        self._refresh()
        self._tq.close()
        if self.enabled and self._tq.leave is False:
            self._prog.down()

    @property
    def enabled(self) -> bool:
        return self._prog.enabled
