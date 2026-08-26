"""Tests for macOS browser executable discovery."""

from pathlib import Path

import pytest

from chrome_agent_bridge.browser import find_browser
from chrome_agent_bridge.manager import BridgeError


@pytest.mark.unit
def test_find_browser_rejects_non_macos(monkeypatch):
    """The first release does not claim to support another platform."""
    monkeypatch.setattr("chrome_agent_bridge.browser.platform.system", lambda: "Linux")

    with pytest.raises(BridgeError, match="macOS only"):
        find_browser()


@pytest.mark.unit
def test_find_browser_accepts_executable_requested_by_user(monkeypatch, tmp_path):
    """An explicit executable takes precedence over automatic discovery."""
    browser = tmp_path / "Chromium"
    browser.write_text("", encoding="utf-8")
    browser.chmod(0o700)
    monkeypatch.setattr("chrome_agent_bridge.browser.platform.system", lambda: "Darwin")

    assert find_browser(browser) == browser


@pytest.mark.unit
def test_find_browser_rejects_non_executable_requested_by_user(monkeypatch, tmp_path):
    """A clear error prevents attempting to launch an arbitrary file."""
    browser = tmp_path / "Chromium"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setattr("chrome_agent_bridge.browser.platform.system", lambda: "Darwin")

    with pytest.raises(BridgeError, match="not usable"):
        find_browser(browser)


@pytest.mark.unit
def test_find_browser_uses_path_fallback(monkeypatch):
    """PATH discovery supports a nonstandard Chromium installation."""
    monkeypatch.setattr("chrome_agent_bridge.browser.platform.system", lambda: "Darwin")
    monkeypatch.setattr("chrome_agent_bridge.browser.MACOS_BROWSER_PATHS", ())
    monkeypatch.setattr(
        "chrome_agent_bridge.browser.shutil.which",
        lambda command: "/opt/homebrew/bin/chromium" if command == "chromium" else None,
    )

    assert find_browser() == Path("/opt/homebrew/bin/chromium")


@pytest.mark.unit
def test_find_browser_explains_when_no_browser_is_found(monkeypatch):
    """Missing supported browsers produce an actionable message."""
    monkeypatch.setattr("chrome_agent_bridge.browser.platform.system", lambda: "Darwin")
    monkeypatch.setattr("chrome_agent_bridge.browser.MACOS_BROWSER_PATHS", ())
    monkeypatch.setattr(
        "chrome_agent_bridge.browser.shutil.which", lambda command: None
    )

    with pytest.raises(BridgeError, match="Could not find"):
        find_browser()
