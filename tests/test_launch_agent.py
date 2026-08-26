"""Tests for macOS LaunchAgent management."""

import plistlib
import subprocess
import sys

import pytest

from chrome_agent_bridge.launch_agent import LaunchAgentManager
from chrome_agent_bridge.manager import BridgeError, BridgeManager
from chrome_agent_bridge.paths import BridgePaths


@pytest.mark.unit
def test_install_writes_private_dynamic_profile_agent(monkeypatch, tmp_path):
    """Install writes a launchd plist that delegates to the safe bridge start."""
    monkeypatch.setattr(
        "chrome_agent_bridge.launch_agent.platform.system", lambda: "Darwin"
    )
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr("chrome_agent_bridge.launch_agent.subprocess.run", run)
    manager = LaunchAgentManager(
        bridge_manager=BridgeManager(BridgePaths(tmp_path / "bridge")),
        launch_agents_directory=tmp_path / "LaunchAgents",
    )

    agent_paths = manager.install("research", tmp_path / "Google Chrome", headless=True)

    payload = plistlib.loads(agent_paths.plist_file.read_bytes())
    arguments = payload["ProgramArguments"]
    assert payload["Label"] == "com.palewire.chrome-agent-bridge.research"
    assert arguments[0] == sys.executable
    assert arguments[1:7] == [
        "-m",
        "chrome_agent_bridge",
        "start",
        "--profile",
        "research",
        "--browser",
    ]
    assert arguments[-1] == "--headless"
    assert "--remote-debugging-port=9222" not in arguments
    assert "--user-data-dir" not in arguments
    assert calls[0][0][1] == "bootstrap"
    assert agent_paths.plist_file.stat().st_mode & 0o777 == 0o600


@pytest.mark.unit
def test_install_replaces_existing_loaded_agent(monkeypatch, tmp_path):
    """Reinstalling one owned label unloads it before replacing its plist."""
    monkeypatch.setattr(
        "chrome_agent_bridge.launch_agent.platform.system", lambda: "Darwin"
    )
    calls = []
    monkeypatch.setattr(
        "chrome_agent_bridge.launch_agent.subprocess.run",
        lambda command, **kwargs: (
            calls.append(command) or subprocess.CompletedProcess(command, 0, "", "")
        ),
    )
    manager = LaunchAgentManager(
        bridge_manager=BridgeManager(BridgePaths(tmp_path / "bridge")),
        launch_agents_directory=tmp_path / "LaunchAgents",
    )
    agent_paths = manager.paths("research")
    agent_paths.plist_file.parent.mkdir()
    agent_paths.plist_file.write_bytes(b"old")

    manager.install("research", tmp_path / "Chrome", headless=False)

    assert calls[0][1] == "bootout"
    assert calls[1][1] == "bootstrap"


@pytest.mark.unit
def test_uninstall_unloads_agent_stops_owned_profile_and_removes_plist(
    monkeypatch, tmp_path
):
    """Uninstall controls only the named service and its owned browser."""
    monkeypatch.setattr(
        "chrome_agent_bridge.launch_agent.platform.system", lambda: "Darwin"
    )
    calls = []
    monkeypatch.setattr(
        "chrome_agent_bridge.launch_agent.subprocess.run",
        lambda command, **kwargs: (
            calls.append(command) or subprocess.CompletedProcess(command, 0, "", "")
        ),
    )
    manager = LaunchAgentManager(
        bridge_manager=BridgeManager(BridgePaths(tmp_path / "bridge")),
        launch_agents_directory=tmp_path / "LaunchAgents",
    )
    agent_paths = manager.paths("research")
    agent_paths.plist_file.parent.mkdir()
    agent_paths.plist_file.write_bytes(b"plist")
    stopped = []
    monkeypatch.setattr(
        manager.bridge_manager, "stop", lambda profile: stopped.append(profile)
    )

    assert manager.uninstall("research")

    assert calls[0][1] == "bootout"
    assert stopped == ["research"]
    assert not agent_paths.plist_file.exists()


@pytest.mark.unit
def test_launch_agent_management_requires_macos(monkeypatch, tmp_path):
    """LaunchAgent commands fail clearly on unsupported platforms."""
    monkeypatch.setattr(
        "chrome_agent_bridge.launch_agent.platform.system", lambda: "Linux"
    )
    manager = LaunchAgentManager(launch_agents_directory=tmp_path)

    with pytest.raises(BridgeError, match="macOS only"):
        manager.uninstall("research")
