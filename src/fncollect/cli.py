"""fncollect command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from fncollect.config import ToolConfig, available_config_paths, guess_project_root
from fncollect.dcp import parse_dcp
from fncollect.logging_setup import build_logger
from fncollect.session_ctx import RunContext
from fncollect.vendors.registry import discover_vendors, registry


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fncollect",
        description="Fixed Network (FN) OLT/ONT log collector and "
        "troubleshooting assistant.",
    )
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="run a collection DCP against a device")
    run.add_argument("--vendor", default=None, help="vendor pack name")
    run.add_argument("--device", default=None, help="device IP or SN")
    run.add_argument("--dcp", default=None, help="path to a DCP YAML file")
    run.add_argument("--config", default=None, help="path to config file")

    collect = sub.add_parser("collect", help="run a semantic action across devices")
    collect.add_argument("--vendor", default=None, help="vendor pack name")
    collect.add_argument("--action", default="inventory", help="action name (inventory, run_commands)")
    collect.add_argument("--devices", default=None, help="comma-separated device IPs")
    collect.add_argument("--commands", default=None, help="comma-separated commands (for run_commands)")

    sub.add_parser("interact", help="interactive guided menu (launch)")
    sub.add_parser("init", help="scaffold local user/ config tree")
    sub.add_parser("vendors", help="list registered vendor packs")

    sub.add_parser("actions", help="list registered action types")

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    return parser


def cmd_init(root: Path) -> int:
    user_dir = root / "user"
    hosts = root / "config" / "hosts.example.yml"
    (user_dir / ".gitkeep").touch(exist_ok=True)
    if not hosts.exists():
        hosts.write_text("# Add your devices here, e.g.:\n# - name: olt-1\n#   ip: 10.0.0.1\n")
    print(f"scaffolded user config tree at {user_dir}")
    return 0


def cmd_vendors() -> int:
    discover_vendors()
    for name in registry.names():
        print(name)
    return 0


def cmd_actions() -> int:
    from fncollect.actions import registry as action_registry

    for name in action_registry.names():
        print(name)
    return 0


async def cmd_run(args: argparse.Namespace) -> int:
    root = guess_project_root()
    config = ToolConfig.load_defaults([root / "config" / "fncollect.yml"])
    if args.config:
        config = ToolConfig.load_defaults(available_config_paths(root) + [Path(args.config)])

    output_root = (root / config.run.output_dir).resolve()
    run = RunContext(config.run, output_root, logger=build_logger(run_dir=None))
    log = build_logger(run_dir=run.dir, config=config.logging)
    run.logger = log

    discover_vendors()
    vendor_name = args.vendor or config.vendor
    vendor_cls = registry.get(vendor_name)
    vendor = vendor_cls()

    info = vendor.device_info()
    if args.vendor and args.device:
        info.ip = args.device
    device = vendor.create_device(info)

    await device.connect()
    log.info("connected to %s (%s)", vendor_name, info.ip)

    dcp_text = _load_dcp_text(args.dcp)
    if dcp_text:
        dcp = parse_dcp(dcp_text)
        log.info("running DCP %r with %d steps", dcp.name, len(dcp.steps))
        results = await _run_dcp(dcp, run, device)
        run.record_meta({"dcp": dcp.name, "vendor": vendor_name})
        _summarize(results, log)
    else:
        results = {"steps": []}
        log.info("no DCP provided; nothing to collect")

    await device.disconnect()
    manifest = run.finalize({"vendor": vendor_name, "device": info.ip})
    print(f"\nrun complete -> {run.dir}")
    print(f"manifest    -> {manifest}")
    return 0 if results["steps"] else 1


async def _run_dcp(dcp, run, device):
    from fncollect.dcp import execute_dcp

    return await execute_dcp(dcp, device, run)


def _load_dcp_text(path: str | None) -> str | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        raise SystemExit(f"DCP file not found: {p}")
    return p.read_text()


def _summarize(results, log) -> None:
    ok = sum(1 for s in results["steps"] if s.get("ok"))
    skipped = sum(1 for s in results["steps"] if s.get("skipped"))
    failed = sum(1 for s in results["steps"] if s.get("error"))
    log.info("steps: ok=%d skipped=%d failed=%d", ok, skipped, failed)
    for step in results["steps"]:
        if step.get("error"):
            log.error("step %s failed: %s", step.get("id"), step.get("error"))


def execute_collect(vendor_name: str, action: str, devices: str, commands: str | None = None) -> int:
    """Shared entry: run an action across comma-separated device IPs."""
    return asyncio.run(_collect(vendor_name, action, devices, commands))


async def _collect(
    vendor_name: str, action: str, devices: str, commands: str | None = None
) -> int:
    from fncollect.actions import action_work
    from fncollect.engine import ConcurrentRunner
    from fncollect.report import build_and_write

    root = guess_project_root()
    config = ToolConfig.load_defaults([root / "config" / "fncollect.yml"])
    output_root = (root / config.run.output_dir).resolve()
    run = RunContext(config.run, output_root, logger=build_logger(run_dir=None))
    log = build_logger(run_dir=run.dir, config=config.logging)
    run.logger = log

    discover_vendors()
    vendor_cls = registry.get(vendor_name)
    vendor = vendor_cls()

    ips = [d.strip() for d in devices.split(",") if d.strip()] or ["127.0.0.1"]
    mock_devices = []
    for ip in ips:
        info = vendor.device_info()
        info.ip = ip
        mock_devices.append(vendor.create_device(info))

    params = {"commands": commands.split(",")} if commands else None
    runner = ConcurrentRunner(config.concurrency.max_parallel_devices)
    results = await runner.run(mock_devices, action_work(vendor, action), run, params)
    summary = runner.summarize(results)
    meta = {"vendor": vendor_name, "action": action, "devices": ips}
    run.record_meta(meta)
    reports = build_and_write(run, summary, meta)
    manifest = run.finalize(meta)

    for device in summary["devices"]:
        status = "OK" if device["ok"] else "FAILED"
        log.info("%s %s: %s", device["device"], device["action"], status)
        if device.get("error"):
            log.error("%s: %s", device["device"], device["error"])
    print(f"\ncollect complete -> {run.dir}")
    for name, path in reports.items():
        print(f"  {name} -> {path}")
    print(f"manifest      -> {manifest}")
    return 0 if summary["failed"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = guess_project_root()
    if args.command == "init":
        return cmd_init(root)
    if args.command == "vendors":
        return cmd_vendors()
    if args.command == "actions":
        return cmd_actions()
    if args.command == "interact":
        from fncollect.menu import run_interactive

        return run_interactive()
    if args.command == "run":
        try:
            return asyncio.run(cmd_run(args))
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.command == "collect":
        try:
            return execute_collect(
                args.vendor or "mock", args.action, args.devices or "", args.commands
            )
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
