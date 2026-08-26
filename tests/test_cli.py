"""Tests for the user-facing command line interface."""

import runpy
import sys

import pytest
from click.testing import CliRunner

from chrome_agent_bridge.cli import main
from chrome_agent_bridge.manager import (
    BridgeError,
    BridgeState,
    BridgeStatus,
    DevToolsHealth,
)
from chrome_agent_bridge.paths import BridgePaths


@pytest.mark.unit
def test_start_prints_private_endpoint(monkeypatch):
    """Start reports the verified endpoint rather than a guessed fixed port."""

    class Manager:
        def start(self, profile, browser, *, headless):
            assert profile == "research"
            assert headless
            return DevToolsHealth(41000, "Chrome/1", "ws://local")

    monkeypatch.setattr("chrome_agent_bridge.cli._manager", lambda: Manager())
    monkeypatch.setattr(
        "chrome_agent_bridge.cli.find_browser", lambda browser: "/Chrome"
    )

    result = CliRunner().invoke(main, ["start", "--profile", "research", "--headless"])

    assert result.exit_code == 0
    assert "http://127.0.0.1:41000" in result.output


@pytest.mark.unit
def test_mcp_config_reports_unhealthy_profile(monkeypatch):
    """MCP configuration fails clearly before printing an unusable endpoint."""

    class Manager:
        def mcp_config(self, profile):
            raise BridgeError(f"Profile '{profile}' is not running")

    monkeypatch.setattr("chrome_agent_bridge.cli._manager", lambda: Manager())

    result = CliRunner().invoke(main, ["mcp-config", "--profile", "research"])

    assert result.exit_code != 0
    assert "not running" in result.output


@pytest.mark.unit
def test_stop_and_status_report_stopped_profile(monkeypatch):
    """Stopped profiles produce clear, successful command output."""

    class Manager:
        def stop(self, profile):
            return False

        def status(self, profile):
            return BridgeStatus(None, False, None)

    monkeypatch.setattr("chrome_agent_bridge.cli._manager", lambda: Manager())

    stop_result = CliRunner().invoke(main, ["stop", "--profile", "research"])
    status_result = CliRunner().invoke(main, ["status", "--profile", "research"])

    assert stop_result.exit_code == 0
    assert stop_result.output == "Chrome is not running.\n"
    assert status_result.exit_code == 0
    assert status_result.output == "Status: stopped\n"


@pytest.mark.unit
def test_status_and_doctor_report_a_healthy_profile(monkeypatch, tmp_path):
    """The status commands present the loopback health result."""
    health = DevToolsHealth(41000, "Chrome/1", "ws://local")
    state = BridgeState(
        pid=123,
        profile="research",
        browser_data="/private/profile",
        browser="/Applications/Chrome",
        started_at="2026-01-01T00:00:00+00:00",
        headless=False,
        log_file="/private/log",
        port=41000,
    )

    class Manager:
        paths = BridgePaths(tmp_path / "bridge")

        def status(self, profile):
            return BridgeStatus(state, True, health)

    monkeypatch.setattr("chrome_agent_bridge.cli._manager", lambda: Manager())
    monkeypatch.setattr(
        "chrome_agent_bridge.cli.find_browser", lambda browser: "/Applications/Chrome"
    )

    status_result = CliRunner().invoke(main, ["status", "--profile", "research"])
    doctor_result = CliRunner().invoke(main, ["doctor", "--profile", "research"])

    assert status_result.exit_code == 0
    assert "Status: running" in status_result.output
    assert doctor_result.exit_code == 0
    assert "DevTools health: healthy (http://127.0.0.1:41000)" in doctor_result.output


@pytest.mark.unit
def test_mcp_config_prints_json(monkeypatch):
    """The command prints a ready-to-paste Chrome DevTools MCP snippet."""

    class Manager:
        def mcp_config(self, profile):
            return {
                "mcpServers": {
                    "chrome-devtools": {
                        "args": ["--browser-url", "http://127.0.0.1:41000"]
                    }
                }
            }

    monkeypatch.setattr("chrome_agent_bridge.cli._manager", lambda: Manager())

    result = CliRunner().invoke(main, ["mcp-config", "--profile", "research"])

    assert result.exit_code == 0
    assert '"--browser-url"' in result.output


@pytest.mark.unit
def test_module_entry_point_shows_help(monkeypatch):
    """The ``python -m`` entry point delegates to the Click CLI."""
    monkeypatch.setattr(sys, "argv", ["chrome_agent_bridge", "--help"])

    with pytest.raises(SystemExit) as result:
        runpy.run_module("chrome_agent_bridge.__main__", run_name="__main__")

    assert result.value.code == 0
