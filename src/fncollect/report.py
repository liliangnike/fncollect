"""Report generation for a run.

Builds human-readable and machine-readable summaries on top of the raw
artifacts a run produced: ``summary.md``, ``results.json`` and an optional
CSV export (device, action, artifact) -- the ngalexx "SONAR"/report analogue.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any


def build_and_write(run, results: dict[str, Any], meta: dict[str, Any] | None = None) -> dict[str, Path]:
    """Write summary.md, results.json and results.csv into the run dir."""
    run.report_root.mkdir(parents=True, exist_ok=True)
    meta = meta or {}
    summary_path = run.report_root / "summary.md"
    summary_path.write_text(_summary_md(results, meta))
    run.register_artifact(summary_path, "report")

    results_path = run.report_root / "results.json"
    results_path.write_text(json.dumps(results, indent=2, sort_keys=True))
    run.register_artifact(results_path, "report")

    csv_path = run.report_root / "results.csv"
    _write_csv(csv_path, results)
    run.register_artifact(csv_path, "report")
    return {"summary": summary_path, "results": results_path, "csv": csv_path}


def _summary_md(results: dict[str, Any], meta: dict[str, Any]) -> str:
    lines = ["# fncollect run summary", ""]
    if meta:
        lines += [f"- **{k}**: `{v}`" for k, v in meta.items()]
        lines.append("")
    devices = results.get("devices", [])
    lines.append(f"- Devices: {results.get('total', len(devices))} "
                 f"(ok {results.get('ok', 0)} / failed {results.get('failed', 0)})")
    lines.append("")
    lines.append("| device | action | status | artifacts |")
    lines.append("| --- | --- | --- | --- |")
    for device in devices:
        status = "OK" if device.get("ok") else "FAILED"
        error = device.get("error") or ""
        artifacts = "; ".join(device.get("artifacts", [])) or "-"
        lines.append(
            f"| {device.get('device')} | {device.get('action') or '-'} | "
            f"{status} | {artifacts} |"
        )
        if error:
            lines.append(f"\n> {device.get('device')}: {error}")
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, results: dict[str, Any]) -> None:
    devices = results.get("devices", [])
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["device", "action", "ok", "artifact", "error"])
        for device in devices:
            artifacts = device.get("artifacts") or [None]
            for artifact in artifacts:
                writer.writerow(
                    [
                        device.get("device"),
                        device.get("action"),
                        device.get("ok"),
                        artifact,
                        device.get("error"),
                    ]
                )
        if not devices:
            writer.writerow([])
