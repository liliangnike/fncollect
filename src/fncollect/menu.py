"""Interactive (launch) mode.

Presents a guided menu: pick a vendor, an action, then a target. Returns a
task spec that the CLI executes -- the ngalexx "launch" experience, kept
generic and vendor-agnostic.
"""

from __future__ import annotations

import sys

from fncollect.actions import registry as action_registry
from fncollect.vendors.registry import discover_vendors, registry


def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _choose(label: str, names: list[str]) -> str:
    if not names:
        print(f"No {label} available.")
        sys.exit(1)
    print(f"\nSelect {label}:")
    for i, name in enumerate(names, 1):
        print(f"  {i:>2}) {name}")
    while True:
        try:
            choice = int(_ask("Choice: "))
            if 1 <= choice <= len(names):
                return names[choice - 1]
        except ValueError:
            pass
        print("Invalid choice, try again.")


def interact() -> dict[str, str]:
    discover_vendors()
    vendor = _choose("vendor", registry.names())
    action = _choose("action", action_registry.names())
    devices = _ask("Device IP(s), comma separated: ")
    return {"vendor": vendor, "action": action, "devices": devices}


def run_interactive() -> int:
    spec = interact()
    from fncollect.cli import execute_collect

    return execute_collect(spec["vendor"], spec["action"], spec["devices"])