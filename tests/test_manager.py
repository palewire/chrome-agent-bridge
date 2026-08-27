"""Tests for DevTools endpoint checks and process ownership state."""

import json
import socket
from pathlib import Path

import pytest

from chrome_agent_bridge.manager import (
    BridgeError,
    BridgeManager,
    BridgeState,
    DevToolsHealth,
    check_devtools_health,
    check_loopback_port_available,
    read_debugging_port,
)
from chrome_agent_bridge.paths import BridgePaths


@pytest.mark.unit
def test_read_debugging_port_reads_chrome_file(tmp_path):
    """The first line of Chrome's port file selects the endpoint."""
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text("41235\n/devtools/browser/abc\n", encoding="utf-8")

    assert read_debugging_port(port_file) == 41235


@pytest.mark.unit
@pytest.mark.parametrize("contents", ["0\n", "65536\n", "not-a-port\n", ""])
def test_read_debugging_port_rejects_invalid_values(tmp_path, contents):
    """Invalid port files do not become endpoint URLs."""
    port_file = tmp_path / "DevToolsActivePort"
    port_file.write_text(contents, encoding="utf-8")

    assert read_debugging_port(port_file) is None


@pytest.mark.unit
def test_check_devtools_health_requires_valid_loopback_response(monkeypatch):
    """Health checks require Chrome metadata and a websocket endpoint."""

    class Response:
        def read(self):
            return b'{"Browser": "Chrome/1", "webSocketDebuggerUrl": "ws://local"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "chrome_agent_bridge.manager.urlopen", lambda url, timeout: Response()
    )

    assert check_devtools_health(40000) == DevToolsHealth(
        port=40000,
        browser="Chrome/1",
        websocket_url="ws://local",
    )
    assert check_devtools_health(0) is None


@pytest.mark.unit
def test_check_devtools_health_rejects_incomplete_responses(monkeypatch):
    """A responding web server is not enough without Chrome metadata."""

    class Response:
        def read(self):
            return b'{"Browser": "Chrome/1"}'

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr(
        "chrome_agent_bridge.manager.urlopen", lambda url, timeout: Response()
    )

    assert check_devtools_health(40000) is None


@pytest.mark.unit
def test_check_loopback_port_available_rejects_an_occupied_port():
    """A fixed port must not already serve another local process."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        with pytest.raises(BridgeError, match=rf"DevTools port {port} is unavailable"):
            check_loopback_port_available(port)


@pytest.mark.unit
def test_start_rejects_an_occupied_fixed_port(tmp_path):
    """Start checks a fixed port before attempting to launch Chrome."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]

        with pytest.raises(BridgeError, match=rf"DevTools port {port} is unavailable"):
            manager.start(
                "agent", Path("/Applications/Chrome"), headless=False, port=port
            )


@pytest.mark.unit
def test_state_round_trip_is_private(tmp_path):
    """Owner state survives complete JSON writes."""
    state_file = tmp_path / "agent.json"
    state = BridgeState(
        pid=123,
        profile="agent",
        browser_data="/private/profile",
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=True,
        log_file="/private/log",
        port=40000,
    )

    state.write(state_file)

    assert BridgeState.from_file(state_file) == state
    assert json.loads(state_file.read_text(encoding="utf-8"))["port"] == 40000


@pytest.mark.unit
def test_state_rejects_invalid_json(tmp_path):
    """A corrupt owner record is reported instead of trusted."""
    state_file = tmp_path / "agent.json"
    state_file.write_text("{broken", encoding="utf-8")

    with pytest.raises(BridgeError, match="Cannot read"):
        BridgeState.from_file(state_file)


@pytest.mark.unit
def test_mcp_config_uses_verified_browser_url(monkeypatch, tmp_path):
    """MCP configuration uses the health-checked loopback URL."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    paths = manager.paths.create_private_directories("agent")
    BridgeState(
        pid=123,
        profile="agent",
        browser_data=str(paths.browser_data),
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=False,
        log_file="/private/log",
        port=43123,
        requested_port=43123,
    ).write(paths.state_file)
    monkeypatch.setattr(
        "chrome_agent_bridge.manager.command_for_pid",
        lambda pid: (
            f"Chrome --user-data-dir={paths.browser_data} "
            "--remote-debugging-address=127.0.0.1 --remote-debugging-port=43123"
        ),
    )
    monkeypatch.setattr(
        "chrome_agent_bridge.manager.check_devtools_health",
        lambda port: DevToolsHealth(port, "Chrome/1", "ws://local"),
    )

    config = manager.mcp_config("agent")

    assert (
        config["mcpServers"]["chrome-devtools"]["args"][-1] == "http://127.0.0.1:43123"
    )


@pytest.mark.unit
def test_status_does_not_trust_a_non_bridge_process(monkeypatch, tmp_path):
    """A state file alone cannot authorize controlling another process."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    paths = manager.paths.create_private_directories("agent")
    BridgeState(
        pid=123,
        profile="agent",
        browser_data=str(paths.browser_data),
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=False,
        log_file="/private/log",
    ).write(paths.state_file)
    monkeypatch.setattr(
        "chrome_agent_bridge.manager.command_for_pid", lambda pid: "unrelated-process"
    )

    status = manager.status("agent")

    assert not status.owned
    assert not status.is_running


@pytest.mark.unit
def test_launch_command_keeps_debugging_on_loopback(tmp_path):
    """Every Chrome launch asks Chrome to choose a loopback-only port."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))

    command = manager._launch_command(
        Path("/Applications/Chrome"), tmp_path / "data", True, port=None
    )

    assert "--remote-debugging-address=127.0.0.1" in command
    assert "--remote-debugging-port=0" in command
    assert "--headless=new" in command


@pytest.mark.unit
def test_launch_command_uses_requested_loopback_port(tmp_path):
    """A fixed port still binds Chrome DevTools only to loopback."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))

    command = manager._launch_command(
        Path("/Applications/Chrome"), tmp_path / "data", False, port=9222
    )

    assert "--remote-debugging-address=127.0.0.1" in command
    assert "--remote-debugging-port=9222" in command


@pytest.mark.unit
def test_start_records_the_verified_dynamic_port(monkeypatch, tmp_path):
    """Starting stores only the port returned by Chrome's health check."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    health = DevToolsHealth(41777, "Chrome/1", "ws://local")

    class Process:
        pid = 456

    monkeypatch.setattr(
        "chrome_agent_bridge.manager.subprocess.Popen",
        lambda *args, **kwargs: Process(),
    )
    monkeypatch.setattr(
        manager, "_wait_for_health", lambda process, paths, requested_port: health
    )

    assert manager.start("agent", Path("/Applications/Chrome"), headless=True) == health
    state = BridgeState.from_file(manager.paths.for_profile("agent").state_file)
    assert state is not None
    assert state.port == 41777
    assert state.headless


@pytest.mark.unit
def test_start_records_a_requested_fixed_port(monkeypatch, tmp_path):
    """A fixed port is retained for process ownership checks after launch."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    health = DevToolsHealth(41777, "Chrome/1", "ws://local")

    class Process:
        pid = 456

    monkeypatch.setattr(
        "chrome_agent_bridge.manager.subprocess.Popen",
        lambda *args, **kwargs: Process(),
    )
    monkeypatch.setattr(
        manager, "_wait_for_health", lambda process, paths, requested_port: health
    )

    assert (
        manager.start("agent", Path("/Applications/Chrome"), headless=True, port=41777)
        == health
    )
    state = BridgeState.from_file(manager.paths.for_profile("agent").state_file)
    assert state is not None
    assert state.port == 41777
    assert state.requested_port == 41777


@pytest.mark.unit
def test_start_removes_state_when_chrome_never_becomes_healthy(monkeypatch, tmp_path):
    """An unsuccessful launch does not leave an owner record behind."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))

    class Process:
        pid = 456

    stopped = []
    monkeypatch.setattr(
        "chrome_agent_bridge.manager.subprocess.Popen",
        lambda *args, **kwargs: Process(),
    )
    monkeypatch.setattr(
        manager, "_wait_for_health", lambda process, paths, requested_port: None
    )
    monkeypatch.setattr(
        manager, "_stop_local_process", lambda process: stopped.append(process.pid)
    )

    with pytest.raises(BridgeError, match="did not expose"):
        manager.start("agent", Path("/Applications/Chrome"), headless=False)

    assert stopped == [456]
    assert BridgeState.from_file(manager.paths.for_profile("agent").state_file) is None


@pytest.mark.unit
def test_wait_for_health_checks_only_the_requested_fixed_port(monkeypatch, tmp_path):
    """A fixed port does not depend on Chrome's dynamic-port file."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    paths = manager.paths.create_private_directories("agent")
    paths.active_port_file.write_text(
        "41111\n/devtools/browser/other\n", encoding="utf-8"
    )
    health = DevToolsHealth(9222, "Chrome/1", "ws://127.0.0.1:9222/devtools/browser/a")
    checked_ports = []

    class Process:
        def poll(self):
            return None

    def fake_health_check(port):
        checked_ports.append(port)
        return health if port == 9222 else None

    monkeypatch.setattr(
        "chrome_agent_bridge.manager.check_devtools_health", fake_health_check
    )

    assert manager._wait_for_health(Process(), paths, 9222) == health
    assert checked_ports == [9222]


@pytest.mark.unit
def test_start_reuses_a_healthy_owned_profile(monkeypatch, tmp_path):
    """A second start leaves an already healthy bridge process alone."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    paths = manager.paths.create_private_directories("agent")
    BridgeState(
        pid=456,
        profile="agent",
        browser_data=str(paths.browser_data),
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=False,
        log_file="/private/log",
        port=41777,
    ).write(paths.state_file)
    health = DevToolsHealth(41777, "Chrome/1", "ws://local")
    monkeypatch.setattr(manager, "_is_owned_process", lambda state: True)
    monkeypatch.setattr(
        "chrome_agent_bridge.manager.check_devtools_health", lambda port: health
    )

    assert (
        manager.start("agent", Path("/Applications/Chrome"), headless=False) == health
    )


@pytest.mark.unit
def test_start_refuses_to_replace_an_unhealthy_owned_profile(monkeypatch, tmp_path):
    """A live owner record must be explicitly stopped before replacement."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    paths = manager.paths.create_private_directories("agent")
    BridgeState(
        pid=456,
        profile="agent",
        browser_data=str(paths.browser_data),
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=False,
        log_file="/private/log",
    ).write(paths.state_file)
    monkeypatch.setattr(manager, "_is_owned_process", lambda state: True)

    with pytest.raises(BridgeError, match="already owned"):
        manager.start("agent", Path("/Applications/Chrome"), headless=False)


@pytest.mark.unit
def test_stop_only_signals_the_owned_process(monkeypatch, tmp_path):
    """Stop removes state after the owned process exits."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    paths = manager.paths.create_private_directories("agent")
    BridgeState(
        pid=456,
        profile="agent",
        browser_data=str(paths.browser_data),
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=False,
        log_file="/private/log",
    ).write(paths.state_file)
    signals = []
    monkeypatch.setattr(manager, "_is_owned_process", lambda state: True)
    monkeypatch.setattr(
        manager,
        "_signal_process_group",
        lambda pid, number: signals.append((pid, number)),
    )
    monkeypatch.setattr("chrome_agent_bridge.manager.command_for_pid", lambda pid: None)

    assert manager.stop("agent")
    assert signals
    assert BridgeState.from_file(paths.state_file) is None


@pytest.mark.unit
def test_stop_removes_stale_state_without_signaling(monkeypatch, tmp_path):
    """A stale record cannot authorize a signal to a replacement process."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    paths = manager.paths.create_private_directories("agent")
    BridgeState(
        pid=456,
        profile="agent",
        browser_data=str(paths.browser_data),
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=False,
        log_file="/private/log",
    ).write(paths.state_file)
    monkeypatch.setattr(manager, "_is_owned_process", lambda state: False)

    assert not manager.stop("agent")
    assert BridgeState.from_file(paths.state_file) is None


@pytest.mark.unit
def test_manager_reports_stopped_and_rejects_unhealthy_mcp_config(tmp_path):
    """A stopped profile has no MCP endpoint to print."""
    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))

    assert manager.status("agent").state is None
    assert not manager.stop("agent")
    with pytest.raises(BridgeError, match="not running"):
        manager.mcp_config("agent")
