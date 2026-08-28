"""Real interactive SSH session.

Nokia ISAM-style devices do not accept a plain ``exec`` request: they need
an interactive PTY shell, prompt detection, paging (``--more--``) handling
and support for the context-based CLI navigation. This module provides a
session that meets those needs.

It also works around the SSH ``ssh-rsa`` (RSA-SHA1) legacy host-key issue:
older fixed-network devices only offer SHA-1 signatures, which modern
paramiko disables. ``enable_legacy_ssh`` re-enables those algorithms where
paramiko still implements them.
"""

from __future__ import annotations

import re
import time

try:  # paramiko is an optional dependency (the `net` extra)
    import paramiko
except ImportError:  # pragma: no cover
    paramiko = None  # type: ignore[assignment]

from fncollect.sessions import CommandResult, Session

_ANSI = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_PAGING = ("--more--", "--more (q to quit)", "press enter", "--more")


def _paramiko_major() -> int:
    if paramiko is None:
        return 0
    try:
        return int(paramiko.__version__.split(".")[0])
    except (AttributeError, ValueError):  # pragma: no cover
        return 0


def enable_legacy_ssh() -> None:
    """Re-enable legacy host-key/public-key algorithms where possible."""
    if paramiko is None:  # pragma: no cover
        raise ImportError("paramiko is required; install the 'net' extra")
    try:
        preferred = list(paramiko.Transport._preferred_keys)
        for algo in ("ssh-rsa", "ssh-dss"):
            if algo not in preferred:
                preferred.append(algo)
        paramiko.Transport._preferred_keys = tuple(preferred)
        key_info = dict(paramiko.Transport._key_info)
        if "ssh-rsa" not in key_info:
            key_info["ssh-rsa"] = paramiko.RSAKey
        paramiko.Transport._key_info = key_info
    except Exception:  # noqa: BLE001, S110 - best effort
        pass


class InteractiveSshSession(Session):
    """Interactive PTY-based SSH session with prompt + paging handling.

    ``exec_cmd`` accepts a multi-line command string. Each non-empty line is
    sent as a CLI token; this supports context-based navigation such as
    ``"show\\nsystem\\nentry"``. Before running, the session returns to the
    root prompt so each command is a full path from root.
    """

    default_port = 22
    #: The base prompt as seen at the top of the tree (no sub-context).
    base_prompt = "typ:isadmin>#"
    #: Regex matching any (nested) prompt; group 1 captures the token before '#'.
    prompt_pattern = r"typ:[\w-]+(?:>[^>#]+)*#"

    def __init__(self, endpoint) -> None:
        super().__init__(endpoint)
        self._client: paramiko.SSHClient | None = None
        self._chan = None
        self.prompt: str | None = None
        self._prompt_re = re.compile(r"(" + self.prompt_pattern + r")\s*$")

    def _connect_blocking(self) -> None:
        if paramiko is None:  # pragma: no cover
            raise ImportError("paramiko is required; install the 'net' extra")
        enable_legacy_ssh()
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                hostname=self.endpoint.hostname,
                port=self.endpoint.port,
                username=self.endpoint.username,
                password=self.endpoint.password,
                timeout=25,
                look_for_keys=False,
                allow_agent=False,
            )
        except paramiko.ssh_exception.SSHException as exc:
            if _paramiko_major() >= 3:
                raise RuntimeError(
                    "This device uses legacy RSA-SHA1 SSH, which paramiko "
                    f"v{paramiko.__version__} cannot authenticate. Install "
                    "paramiko 2.x: 'pip install \"paramiko>=2,<3\"'."
                ) from exc
            raise
        self._client = client
        self._chan = client.invoke_shell()

    async def connect(self) -> None:
        self._connect_blocking()
        self._read_until_prompt(timeout=12)  # consume banner, land at root

    def _depth(self) -> int:
        # top-level prompt (typ:isadmin>#) has one '>'; nested contexts add more.
        if not self.prompt:
            return 1
        return self.prompt.count(">")

    def _reset_to_root(self) -> None:
        guard = 0
        while self._depth() > 1 and guard < 10:
            if self._chan is None:
                return
            try:
                self._chan.send("exit\n")
            except Exception:  # noqa: BLE001
                return
            self._read_until_prompt(timeout=3)
            guard += 1

    def _read_until_prompt(self, timeout: float = 5.0) -> str:
        if self._chan is None:
            return ""
        buf = b""
        end = time.time() + timeout
        while time.time() < end:
            while self._chan.recv_ready():
                buf += self._chan.recv(65535)
            text = _ANSI.sub("", buf.decode(errors="replace"))
            lower = text.lower()
            if any(marker in lower for marker in _PAGING):
                self._chan.send(" ")
                time.sleep(0.2)
                continue
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
            if lines:
                match = self._prompt_re.search(lines[-1])
                if match:
                    self.prompt = match.group(1)
                    return text
            time.sleep(0.1)
        return text

    async def exec_cmd(self, command: str) -> CommandResult:
        if self._chan is None:
            raise RuntimeError("session not connected")
        lines = [ln for ln in command.split("\n") if ln.strip()]
        if not lines:
            return CommandResult(command=command, output="")
        output = ""
        self._reset_to_root()
        for line in lines:
            self._chan.send(line + "\n")
            output += self._read_until_prompt()
        return CommandResult(command=command, output=_ANSI.sub("", output))

    async def close(self) -> None:
        if self._chan is not None:
            try:
                self._chan.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._chan = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:  # noqa: BLE001, S110
                pass
            self._client = None
