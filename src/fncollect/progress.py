"""Progress bars for stages/steps/procedures/command executions.

Built on ``tqdm`` and styled to look like a Linux package-installation
progress bar: a fixed square-bracket bar with a percentage and a description
of the current unit (stage -> procedure -> step -> command).

Nested levels are rendered as stacked tqdm bars; inner bars collapse when
finished so the outer stage/step bars remain visible, like a detailed
install log.
"""

from __future__ import annotations

import sys

from tqdm import tqdm

# Linux-install-style bar: "[=====>      ] 57%"
BAR_FORMAT = "{desc:<38}{percentage:3.0f}%[{bar}]"
ASCII = "=> "


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
            bar_format=BAR_FORMAT,
            ascii=ASCII,
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

    def update(self, n: int = 1) -> None:
        self._tq.update(n)

    def set_desc(self, text: str) -> None:
        self._tq.set_description_str(text, refresh=True)

    def close(self) -> None:
        self._tq.close()
        if self.enabled and self._tq.leave is False:
            self._prog.down()

    @property
    def enabled(self) -> bool:
        return self._prog.enabled
