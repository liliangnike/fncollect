"""fncollect command-line interface."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

from fncollect.config import ToolConfig, available_config_paths, guess_project_root
from fncollect.dcp import parse_dcp
from fncollect.device_lock import DeviceLockedError
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
    run.add_argument("--device", default=None, help="device IP or SN (single device)")
    run.add_argument("--devices", default=None, help="comma-separated device IPs (run the DCP concurrently)")
    run.add_argument("--dcp", default=None, help="path to a DCP YAML file")
    run.add_argument("--procedure", default=None, help="built-in procedure name for the vendor")
    run.add_argument("--config", default=None, help="path to config file")
    run.add_argument("--user", default=None, help="login username")
    run.add_argument("--password", default=None, help="login password")
    run.add_argument("--no-progress", action="store_true", help="disable progress bars")
    run.add_argument("--no-lock", action="store_true", help="do not enforce the per-device single-task lock")

    collect = sub.add_parser("collect", help="run a semantic action across devices")
    collect.add_argument("--vendor", default=None, help="vendor pack name")
    collect.add_argument("--action", default="inventory", help="action name (inventory, run_commands)")
    collect.add_argument("--devices", default=None, help="comma-separated device IPs")
    collect.add_argument("--commands", default=None, help="comma-separated commands (for run_commands)")
    collect.add_argument("--user", default=None, help="login username")
    collect.add_argument("--password", default=None, help="login password")
    collect.add_argument("--no-progress", action="store_true", help="disable progress bars")
    collect.add_argument("--no-lock", action="store_true", help="do not enforce the per-device single-task lock")

    sub.add_parser("interact", help="interactive guided menu (launch)")
    sub.add_parser("init", help="scaffold local user/ config tree")
    sub.add_parser("vendors", help="list registered vendor packs")

    procedures = sub.add_parser("procedures", help="list built-in procedures for a vendor")
    procedures.add_argument("--vendor", default=None, help="vendor pack name")

    wizard = sub.add_parser("wizard", help="interactive procedure builder (no coding)")
    wizard.add_argument("--vendor", default=None, help="vendor pack name")
    wizard.add_argument("--out", default="user/procedures/custom.yml", help="output YAML procedure file")
    wizard.add_argument("--device", default=None, help="device IP")
    wizard.add_argument("--user", default=None, help="login username")
    wizard.add_argument("--password", default=None, help="login password")

    sub.add_parser("actions", help="list registered action types")

    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")
    return parser


def cmd_init(root: Path) -> int:
    user_dir = root / "user"
    user_dir.mkdir(parents=True, exist_ok=True)
    (user_dir / ".gitkeep").touch(exist_ok=True)
    hosts = root / "user" / "hosts.yml"
    if not hosts.exists():
        example = root / "config" / "hosts.example.yml"
        if example.exists():
            (root / "user" / "hosts.yml").write_text(example.read_text())
    print(f"scaffolded user config tree at {user_dir} (edit user/hosts.yml for credentials)")
    return 0


def cmd_vendors() -> int:
    discover_vendors()
    for name in registry.names():
        print(name)
    return 0


def cmd_procedures(args) -> int:
    discover_vendors()
    root = guess_project_root()
    config = ToolConfig.load_defaults([root / "config" / "fncollect.yml"])
    vendor_name = args.vendor or config.vendor
    vendor = registry.get(vendor_name)()
    for name in sorted(vendor.list_procedures()):
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

    dcp = None
    if args.procedure:
        dcp = vendor.load_procedure(args.procedure)
    elif args.dcp:
        dcp = parse_dcp(_load_dcp_text(args.dcp))

    # Multi-device DCP run: one DCP across comma-separated OLTs, concurrently.
    device_str = getattr(args, "devices", None)
    if dcp is not None and device_str:
        return await _run_dcp_many(
            args, root, config, run, log, vendor, dcp,
            [d.strip() for d in device_str.split(",") if d.strip()],
        )

    info = vendor.device_info()
    ip = (args.device or "127.0.0.1").strip()
    info.ip = ip
    device = vendor.create_device(
        info, credentials=_resolve_device_credentials(ip, vendor_name, args.user, args.password)
    )

    locks = _acquire_locks(root, config, [ip], getattr(args, "no_lock", False))
    try:
        await device.connect()
        log.info("connected to %s (%s)", vendor_name, ip)

        if dcp is not None:
            log.info("running DCP %r with %d steps", dcp.name, len(dcp.steps))
            progress = _progress(args)
            results = await _run_dcp(dcp, run, device, progress)
            run.record_meta({"dcp": dcp.name, "vendor": vendor_name})
            _summarize(results, log)
        else:
            results = {"steps": []}
            log.info("no DCP/procedure provided; nothing to collect")
    finally:
        _release_locks(locks)
        await device.disconnect()

    manifest = run.finalize({"vendor": vendor_name, "device": ip})
    print(f"\nrun complete -> {run.dir}")
    print(f"manifest    -> {manifest}")
    return 0 if results["steps"] else 1


async def _run_dcp_many(args, root, config, run, log, vendor, dcp, ips: list[str]):
    from fncollect.engine import ConcurrentRunner, DeviceResult
    from fncollect.progress import Progress
    from fncollect.report import build_and_write
    from fncollect.session_ctx import sanitize

    devices = [
        vendor.create_device(
            _ip_info(vendor, ip),
            credentials=_resolve_device_credentials(ip, vendor.name, args.user, args.password),
        )
        for ip in ips
    ]
    locks = _acquire_locks(root, config, ips, getattr(args, "no_lock", False))

    def make_work(dcp, run, config):
        from fncollect.config import RunConfig
        from fncollect.dcp import execute_dcp

        async def work(device, base_run, params):
            base = Path(base_run.dir) / "devices"
            dev_config = RunConfig(
                output_dir=str(base),
                session_dir_prefix=sanitize(device.info.ip),
            )
            dev_run = RunContext(dev_config, base, logger=base_run.logger)
            results = await execute_dcp(dcp, device, dev_run, progress=None)
            artifacts = [s.get("artifact") for s in results["steps"] if s.get("artifact")]
            ok = bool(results["steps"]) and all(
                s.get("ok") or s.get("skipped") for s in results["steps"]
            )
            return DeviceResult(
                device=device.info.ip, ok=ok, action=dcp.name, artifacts=artifacts,
                detail={"steps": results["steps"]},
            )

        return work

    try:
        runner = ConcurrentRunner(config.concurrency.max_parallel_devices)
        results = await runner.run(
            devices,
            make_work(dcp, run, config),
            run,
            progress=(None if getattr(args, "no_progress", False) else Progress()),
        )
    finally:
        _release_locks(locks)

    summary = runner.summarize(results)
    meta = {"vendor": vendor.name, "dcp": dcp.name, "devices": ips}
    run.record_meta(meta)
    build_and_write(run, summary, meta)
    manifest = run.finalize(meta)

    for device in summary["devices"]:
        status = "OK" if device["ok"] else "FAILED"
        log.info("%s %s: %s", device["device"], device["action"], status)
    print(f"\nrun complete (dcp {dcp.name} on {len(ips)} device(s)) -> {run.dir}")
    print(f"manifest -> {manifest}")
    return 0 if summary["failed"] == 0 else 1


def _ip_info(vendor, ip):
    info = vendor.device_info()
    info.ip = ip.strip()
    return info


async def _run_dcp(dcp, run, device, progress=None):
    from fncollect.dcp import execute_dcp

    return await execute_dcp(dcp, device, run, progress=progress)


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


def execute_collect(
    vendor_name: str,
    action: str,
    devices: str,
    commands: str | None = None,
    user: str | None = None,
    password: str | None = None,
    no_progress: bool = False,
    no_lock: bool = False,
) -> int:
    """Shared entry: run an action across comma-separated device IPs."""
    return asyncio.run(
        _collect(vendor_name, action, devices, commands, user, password, no_progress, no_lock)
    )


async def _collect(
    vendor_name: str,
    action: str,
    devices: str,
    commands: str | None = None,
    user: str | None = None,
    password: str | None = None,
    no_progress: bool = False,
    no_lock: bool = False,
) -> int:
    from fncollect.actions import action_work
    from fncollect.engine import ConcurrentRunner
    from fncollect.progress import Progress
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
    per_ip_creds = {
        ip: _resolve_device_credentials(ip, vendor_name, user, password) for ip in ips
    }
    mock_devices = []
    for ip in ips:
        info = vendor.device_info()
        info.ip = ip
        mock_devices.append(
            vendor.create_device(info, credentials=per_ip_creds[ip])
        )

    locks = _acquire_locks(root, config, ips, no_lock)
    try:
        params = {"commands": commands.split(",")} if commands else None
        runner = ConcurrentRunner(config.concurrency.max_parallel_devices)
        results = await runner.run(
            mock_devices,
            action_work(vendor, action),
            run,
            params,
            progress=(None if no_progress else Progress()),
        )
    finally:
        _release_locks(locks)
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


def _lock_dir(root: Path, config) -> Path:
    return (root / config.run.output_dir) / "locks"


def _acquire_locks(root: Path, config, devices: list[str], no_lock: bool = False) -> list:
    """Acquire per-device locks; returns the locks held (or empty)."""
    from fncollect.device_lock import DeviceLock, DeviceLockedError

    if no_lock or not config.run.lock_enabled:
        return []
    locks = []
    for ip in dict.fromkeys(devices):  # unique, preserve order
        lock = DeviceLock(_lock_dir(root, config), ip)
        try:
            lock.acquire()
        except DeviceLockedError:
            for held in locks:
                held.release()
            raise
        locks.append(lock)
    return locks


def _release_locks(locks: list) -> None:
    for lock in locks:
        lock.release()


def _progress(args) -> object | None:
    from fncollect.progress import Progress

    return None if getattr(args, "no_progress", False) else Progress()


class CredentialsError(RuntimeError):
    pass


def _interactive() -> bool:
    try:
        return bool(getattr(sys.stdin, "isatty", lambda: False)())
    except Exception:  # noqa: BLE001
        return False


def _masked_password(prompt: str) -> str:
    """Prompt for a password, masking each typed character with '*'."""
    try:
        import pwinput

        return pwinput.maskinput(prompt, mask="*")
    except ImportError:  # pragma: no cover - pwinput is a hard dependency
        import getpass

        return getpass.getpass(prompt)


def _needs_credentials(vendor_name: str) -> bool:
    # Real devices authenticate over SSH; the mock vendor does not.
    return vendor_name and vendor_name != "mock"


def _base_credentials(user: str | None, password: str | None) -> tuple[str | None, str | None]:
    import os

    return (
        user or os.environ.get("FNCOLLECT_USER"),
        password or os.environ.get("FNCOLLECT_PASSWORD"),
    )


def _resolve_device_credentials(
    device_key: str,
    vendor_name: str,
    user: str | None = None,
    password: str | None = None,
) -> dict[str, str]:
    """Resolve credentials for one device.

    ``device_key`` is the device IP or ONT serial (or name). Precedence:
    flag > matching host entry (user/hosts.yml) > hosts defaults >
    environment > interactive prompt.
    """
    u, p = user, password
    try:
        from fncollect.config import HostsConfig

        hosts = HostsConfig.load()
        if hosts is not None:
            merged = hosts.resolve(device_key, vendor_name)
            u = u or merged.get("username")
            p = p or merged.get("password")
    except Exception:  # noqa: BLE001, S110 - a bad hosts file should not block
        pass
    u = u or None
    p = p or None
    fallback_u, fallback_p = _base_credentials(None, None)
    u = u or fallback_u
    p = p or fallback_p
    if _needs_credentials(vendor_name) and (not u or not p):
        if not _interactive():
            raise CredentialsError(
                f"device login credentials are missing for {device_key} (vendor "
                f"{vendor_name!r}); add an entry to user/hosts.yml, or provide "
                "--user/--password, or set FNCOLLECT_USER / FNCOLLECT_PASSWORD"
            )
        if not u:
            u = input(f"Username for {device_key}: ").strip()
        if not p:
            p = _masked_password(f"Password for {device_key}: ")
    return {"username": u or "", "password": p or ""}


def _credentials(
    user: str | None, password: str | None, vendor_name: str | None
) -> dict[str, str]:
    """Resolve credentials from flags/env; prompt interactively when needed.

    Raises CredentialsError with a clear message if a real device needs
    credentials and there is no interactive terminal to ask for them.
    """
    u, p = _base_credentials(user, password)
    if _needs_credentials(vendor_name) and (not u or not p):
        if not _interactive():
            raise CredentialsError(
                "device login credentials are missing for vendor "
                f"{vendor_name!r}; provide --user/--password or set "
                "FNCOLLECT_USER / FNCOLLECT_PASSWORD"
            )
        if not u:
            u = input("Username: ").strip()
        if not p:
            p = _masked_password("Password: ")
    return {"username": u or "", "password": p or ""}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = guess_project_root()
    if args.command == "init":
        return cmd_init(root)
    if args.command == "vendors":
        return cmd_vendors()
    if args.command == "procedures":
        return cmd_procedures(args)
    if args.command == "actions":
        return cmd_actions()
    if args.command == "wizard":
        from fncollect.wizard import build

        return asyncio.run(
            build(args.vendor or "mock", args.out,
                  _credentials(args.user, args.password, args.vendor or "mock"))
        )
    if args.command == "interact":
        from fncollect.menu import run_interactive

        return run_interactive()
    if args.command == "run":
        try:
            return asyncio.run(cmd_run(args))
        except DeviceLockedError as exc:
            print(f"device busy: another task is already running on {exc}", file=sys.stderr)
            return 3
        except CredentialsError as exc:
            print(f"credentials error: {exc}", file=sys.stderr)
            return 2
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    if args.command == "collect":
        try:
            return execute_collect(
                args.vendor or "mock",
                args.action,
                args.devices or "",
                args.commands,
                args.user,
                args.password,
                args.no_progress,
                args.no_lock,
            )
        except KeyError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        except CredentialsError as exc:
            print(f"credentials error: {exc}", file=sys.stderr)
            return 2
        except DeviceLockedError as exc:
            print(f"device busy: another task is already running on {exc}", file=sys.stderr)
            return 3
    build_parser().print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
