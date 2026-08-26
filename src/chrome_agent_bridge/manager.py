"""Local process management for a dedicated Chrome DevTools endpoint."""

from __future__ import annotations

import fcntl
import json
import os
import signal
import socket
import subprocess
import time
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from json import JSONDecodeError
from typing import TYPE_CHECKING
from urllib.error import URLError
from urllib.request import urlopen

from .paths import BridgePaths, ProfilePaths

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

START_TIMEOUT_SECONDS = 15
STOP_TIMEOUT_SECONDS = 10


class BridgeError(RuntimeError):
    """Raised when the bridge cannot safely manage a browser."""


@dataclass(frozen=True, slots=True)
class DevToolsHealth:
    """A verified local DevTools endpoint."""

    port: int
    browser: str
    websocket_url: str

    @property
    def browser_url(self) -> str:
        """Return the HTTP address used by Chrome DevTools MCP."""
        return f"http://127.0.0.1:{self.port}"


@dataclass(frozen=True, slots=True)
class BridgeState:
    """Persisted ownership information for a launched browser."""

    pid: int
    profile: str
    browser_data: str
    browser: str
    started_at: str
    headless: bool
    log_file: str
    port: int | None = None
    requested_port: int | None = None

    @classmethod
    def from_file(cls, state_file: Path) -> BridgeState | None:
        """Load state from a private state file when it exists."""
        if not state_file.is_file():
            return None
        try:
            payload = json.loads(state_file.read_text(encoding="utf-8"))
        except (JSONDecodeError, OSError) as error:
            raise BridgeError(
                f"Cannot read bridge state at {state_file}: {error}"
            ) from error
        if not isinstance(payload, dict):
            raise BridgeError(f"Bridge state at {state_file} is not an object.")
        try:
            return cls(
                pid=int(payload["pid"]),
                profile=str(payload["profile"]),
                browser_data=str(payload["browser_data"]),
                browser=str(payload["browser"]),
                started_at=str(payload["started_at"]),
                headless=bool(payload["headless"]),
                log_file=str(payload["log_file"]),
                port=int(payload["port"]) if payload["port"] is not None else None,
                requested_port=(
                    int(payload["requested_port"])
                    if payload.get("requested_port") is not None
                    else None
                ),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise BridgeError(f"Bridge state at {state_file} is incomplete.") from error

    def write(self, state_file: Path) -> None:
        """Write state privately, replacing the previous complete record."""
        temporary_file = state_file.with_suffix(".tmp")
        temporary_file.write_text(
            f"{json.dumps(asdict(self), indent=2, sort_keys=True)}\n",
            encoding="utf-8",
        )
        temporary_file.chmod(0o600)
        temporary_file.replace(state_file)


@dataclass(frozen=True, slots=True)
class BridgeStatus:
    """Current state and health for a bridge profile."""

    state: BridgeState | None
    owned: bool
    health: DevToolsHealth | None

    @property
    def is_running(self) -> bool:
        """Return whether the owned process is healthy."""
        return self.owned and self.health is not None


@contextmanager
def profile_lock(lock_file: Path) -> Iterator[None]:
    """Serialize short state transitions for one profile."""
    descriptor = os.open(lock_file, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise BridgeError(
                "Another bridge command is changing this profile."
            ) from error
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def read_debugging_port(active_port_file: Path) -> int | None:
    """Read Chrome's dynamically selected debugging port."""
    try:
        first_line = active_port_file.read_text(encoding="utf-8").splitlines()[0]
        port = int(first_line)
    except (FileNotFoundError, IndexError, OSError, ValueError):
        return None
    return port if 1 <= port <= 65535 else None


def check_devtools_health(port: int, timeout: float = 1.0) -> DevToolsHealth | None:
    """Return endpoint metadata only when the loopback DevTools endpoint responds."""
    if not 1 <= port <= 65535:
        return None
    url = f"http://127.0.0.1:{port}/json/version"
    try:
        with urlopen(url, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (JSONDecodeError, OSError, TimeoutError, URLError):
        return None
    if not isinstance(payload, dict):
        return None
    browser = payload.get("Browser")
    websocket_url = payload.get("webSocketDebuggerUrl")
    if not isinstance(browser, str) or not isinstance(websocket_url, str):
        return None
    return DevToolsHealth(port=port, browser=browser, websocket_url=websocket_url)


def check_loopback_port_available(port: int) -> None:
    """Raise when a port cannot be used for a loopback DevTools endpoint."""
    if not 1 <= port <= 65535:
        raise BridgeError("DevTools port must be between 1 and 65535.")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        try:
            listener.bind(("127.0.0.1", port))
        except OSError as error:
            raise BridgeError(
                f"DevTools port {port} is unavailable on 127.0.0.1. "
                "Choose another port or omit --port to let Chrome choose one."
            ) from error


def command_for_pid(pid: int) -> str | None:
    """Return a process command line on macOS, or None when it is gone."""
    result = subprocess.run(  # noqa: S603 - `pid` is an integer from private state
        ("/bin/ps", "-p", str(pid), "-o", "command="),
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() if result.returncode == 0 else None


class BridgeManager:
    """Safely start, inspect, and stop one dedicated Chrome profile."""

    def __init__(self, paths: BridgePaths | None = None) -> None:
        """Create a manager rooted in the current user's private data directory."""
        self.paths = paths or BridgePaths.for_current_user()

    def status(self, profile: str) -> BridgeStatus:
        """Return the stored owner record and current endpoint health."""
        paths = self.paths.for_profile(profile)
        state = BridgeState.from_file(paths.state_file)
        if state is None:
            return BridgeStatus(state=None, owned=False, health=None)
        owned = self._is_owned_process(state)
        health = (
            check_devtools_health(state.port)
            if owned and state.port is not None
            else None
        )
        return BridgeStatus(state=state, owned=owned, health=health)

    def start(
        self, profile: str, browser: Path, *, headless: bool, port: int | None = None
    ) -> DevToolsHealth:
        """Launch Chrome with a private profile and wait for a healthy endpoint."""
        paths = self.paths.create_private_directories(profile)
        with profile_lock(paths.lock_file):
            existing = self.status(paths.profile)
            if existing.is_running:
                assert existing.health is not None
                if (
                    port is not None
                    and existing.state is not None
                    and existing.state.requested_port != port
                ):
                    raise BridgeError(
                        f"Profile '{paths.profile}' is already running on "
                        f"DevTools port {existing.health.port}. Stop it before "
                        "choosing a different port."
                    )
                return existing.health
            if existing.owned:
                assert existing.state is not None
                raise BridgeError(
                    f"Profile '{paths.profile}' is already owned by PID "
                    f"{existing.state.pid}, but its DevTools endpoint is unhealthy. "
                    "Run doctor or stop before starting again."
                )
            if existing.state is not None:
                self._remove_stale_state(paths)

            if port is not None:
                check_loopback_port_available(port)
            paths.active_port_file.unlink(missing_ok=True)
            log_file = self._new_log_file(paths)
            command = self._launch_command(
                browser, paths.browser_data, headless, port=port
            )
            with log_file.open("w", encoding="utf-8") as log_handle:
                process = subprocess.Popen(  # noqa: S603 - browser executable is validated
                    command,
                    stdout=log_handle,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
            state = BridgeState(
                pid=process.pid,
                profile=paths.profile,
                browser_data=str(paths.browser_data),
                browser=str(browser),
                started_at=datetime.now(UTC).isoformat(),
                headless=headless,
                log_file=str(log_file),
                requested_port=port,
            )
            state.write(paths.state_file)
            health = self._wait_for_health(process, paths)
            if health is None:
                self._stop_local_process(process)
                paths.state_file.unlink(missing_ok=True)
                raise BridgeError(
                    f"Chrome did not expose a healthy DevTools endpoint. See {log_file}."
                )
            replace(state, port=health.port).write(paths.state_file)
            return health

    def stop(self, profile: str) -> bool:
        """Stop the browser owned by this profile and remove its state."""
        paths = self.paths.create_private_directories(profile)
        with profile_lock(paths.lock_file):
            state = BridgeState.from_file(paths.state_file)
            if state is None:
                return False
            if not self._is_owned_process(state):
                self._remove_stale_state(paths)
                return False
            self._signal_process_group(state.pid, signal.SIGTERM)
            deadline = time.monotonic() + STOP_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if command_for_pid(state.pid) is None:
                    self._remove_stale_state(paths)
                    return True
                time.sleep(0.1)
            self._signal_process_group(state.pid, signal.SIGKILL)
            time.sleep(0.1)
            if command_for_pid(state.pid) is not None:
                raise BridgeError(f"Chrome process {state.pid} did not stop.")
            self._remove_stale_state(paths)
            return True

    def mcp_config(self, profile: str) -> dict[str, object]:
        """Return a Chrome DevTools MCP configuration for a healthy profile."""
        status = self.status(profile)
        if not status.is_running:
            raise BridgeError(
                f"Profile '{profile}' is not running with a healthy DevTools endpoint."
            )
        assert status.health is not None
        return {
            "mcpServers": {
                "chrome-devtools": {
                    "command": "npx",
                    "args": [
                        "-y",
                        "chrome-devtools-mcp@latest",
                        "--browser-url",
                        status.health.browser_url,
                    ],
                }
            }
        }

    def _is_owned_process(self, state: BridgeState) -> bool:
        command = command_for_pid(state.pid)
        if command is None:
            return False
        expected_data_directory = f"--user-data-dir={state.browser_data}"
        return (
            expected_data_directory in command
            and "--remote-debugging-address=127.0.0.1" in command
            and f"--remote-debugging-port={state.requested_port or 0}" in command
        )

    def _launch_command(
        self, browser: Path, browser_data: Path, headless: bool, *, port: int | None
    ) -> tuple[str, ...]:
        command = [
            str(browser),
            f"--user-data-dir={browser_data}",
            "--remote-debugging-address=127.0.0.1",
            f"--remote-debugging-port={port or 0}",
            "--no-first-run",
            "--no-default-browser-check",
            "--new-window",
            "about:blank",
        ]
        if headless:
            command.insert(-1, "--headless=new")
        return tuple(command)

    def _new_log_file(self, paths: ProfilePaths) -> Path:
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        return paths.log_directory / f"chrome-{timestamp}.log"

    def _wait_for_health(
        self, process: subprocess.Popen[bytes], paths: ProfilePaths
    ) -> DevToolsHealth | None:
        deadline = time.monotonic() + START_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                return None
            port = read_debugging_port(paths.active_port_file)
            if port is not None and (health := check_devtools_health(port)):
                return health
            time.sleep(0.1)
        return None

    def _stop_local_process(self, process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            self._signal_process_group(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=STOP_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self._signal_process_group(process.pid, signal.SIGKILL)
                process.wait(timeout=STOP_TIMEOUT_SECONDS)

    @staticmethod
    def _signal_process_group(pid: int, signal_number: signal.Signals) -> None:
        try:
            os.killpg(pid, signal_number)
        except ProcessLookupError:
            return

    @staticmethod
    def _remove_stale_state(paths: ProfilePaths) -> None:
        paths.state_file.unlink(missing_ok=True)
        paths.active_port_file.unlink(missing_ok=True)
