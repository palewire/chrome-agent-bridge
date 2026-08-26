"""Find an installed macOS Chrome or Chromium executable."""

from __future__ import annotations

import platform
import shutil
from pathlib import Path

from .manager import BridgeError

MACOS_BROWSER_PATHS = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
    Path("/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"),
)


def find_browser(requested_browser: Path | None = None) -> Path:
    """Return a usable macOS browser executable."""
    if platform.system() != "Darwin":
        raise BridgeError("chrome-agent-bridge v0.1.0 supports macOS only.")

    if requested_browser is not None:
        if requested_browser.is_file() and requested_browser.stat().st_mode & 0o111:
            return requested_browser
        raise BridgeError(f"Browser executable is not usable: {requested_browser}")

    for candidate in MACOS_BROWSER_PATHS:
        if candidate.is_file() and candidate.stat().st_mode & 0o111:
            return candidate

    for command in ("google-chrome", "chromium", "chromium-browser"):
        if executable := shutil.which(command):
            return Path(executable)

    raise BridgeError(
        "Could not find Google Chrome or Chromium. Install one, or pass "
        "--browser /path/to/browser."
    )
