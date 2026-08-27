"""Interactive procedure builder (no programming required).

Guides a non-programmer to define a probe/collection step:
  1. connect to a device (or use the mock vendor)
  2. run a command
  3. see the real output, choose the line and the value they want
  4. auto-generate the regex (no regex knowledge needed) and verify it
  5. name the variable and append the step to a YAML procedure file

Power users can still hand-write YAML; this is the friendly path.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from fncollect.processors import auto_regex, extract_values
from fncollect.vendors.registry import discover_vendors, registry


def _ask(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except EOFError:
        return ""


def _ask_choice(prompt: str, options: list[str]) -> str:
    for i, opt in enumerate(options, 1):
        print(f"  {i}) {opt}")
    while True:
        choice = _ask(prompt)
        if choice.isdigit() and 1 <= int(choice) <= len(options):
            return options[int(choice) - 1]
        if choice:
            return choice


async def build(vendor_name: str, out_file: str, credentials: dict[str, str]) -> int:
    discover_vendors()
    vendor_cls = registry.get(vendor_name)
    vendor = vendor_cls()

    target = _ask(f"Device IP (Enter for {vendor_name} default): ") or "127.0.0.1"
    info = vendor.device_info()
    info.ip = target
    device = vendor.create_device(info, credentials=credentials)


    out_path = Path(out_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    await device.connect()
    print(f"\nConnected to {target} ({vendor_name}). Enter commands to explore.")
    steps: list[dict] = []
    try:
        while True:
            command = _ask("\nCommand to run (empty = finish): ")
            if not command:
                break
            result = await device.exec_cmd(command)
            text = result.output.replace("\r", "")
            print("\n--- output ---")
            for i, line in enumerate(text.splitlines()):
                if line.strip():
                    print(f"{i:>4}: {line}")
            print("--- end ---")

            line_no = _ask("Line number containing the value: ")
            value = _ask("Exact value (e.g. 6.6.02): ")
            if line_no.isdigit() and value:
                lines = [l for l in text.splitlines()]
                idx = int(line_no)
                if idx < len(lines):
                    line = lines[idx]
                    pattern = auto_regex(line, value)
                    if pattern:
                        got = extract_values(text, [{"name": "_v", "regex": pattern}])
                        print(f"auto-regex generated: {pattern}")
                        print(f"verified extraction -> {got.get('_v')!r}")
                    else:
                        print("! could not auto-generate a regex for that value")
                        continue
                else:
                    print("! line number out of range")
                    continue

            name = _ask("Variable name (e.g. sw_version): ")
            step = {
                "id": f"step{len(steps) + 1}",
                "command": command,
            }
            if line_no.isdigit() and value:
                step["extract"] = [{"name": name or "value", "regex": pattern}]
            steps.append(step)

    finally:
        await device.disconnect()

    if not steps:
        print("No steps captured; nothing written.")
        return 1

    doc = {"name": out_path.stem, "vendor": vendor_name, "steps": steps}
    out_path.write_text(yaml.safe_dump(doc, sort_keys=False))
    print(f"\nWrote procedure to {out_path}")
    print(f"Run it with: fncollect run --vendor {vendor_name} --procedure {out_path.stem}")
    return 0
