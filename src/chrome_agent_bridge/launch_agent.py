"""Install and remove macOS LaunchAgents for bridge profiles."""

from __future__ import annotations

import os
import platform
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .manager import BridgeError, BridgeManager, profile_lock

LAUNCH_AGENT_LABEL_PREFIX = "com.palewire.chrome-agent-bridge"


@dataclass(frozen=True, slots=True)
class LaunchAgentPaths:
    """Filesystem paths and launchd domain for one bridge profile."""

    label: str
    plist_file: Path
    domain: str


class LaunchAgentManager:
    """Safely install and remove bridge-owned macOS LaunchAgents."""

    def __init__(
        self,
        bridge_manager: BridgeManager | None = None,
        launch_agents_directory: Path | None = None,
    ) -> None:
        """Create a manager using the current user's LaunchAgents directory."""
        self.bridge_manager = bridge_manager or BridgeManager()
        self.launch_agents_directory = (
            launch_agents_directory or Path.home() / "Library" / "LaunchAgents"
        )

    def paths(self, profile: str) -> LaunchAgentPaths:
        """Return validated paths for a profile's LaunchAgent."""
        profile_paths = self.bridge_manager.paths.for_profile(profile)
        label = f"{LAUNCH_AGENT_LABEL_PREFIX}.{profile_paths.profile}"
        return LaunchAgentPaths(
            label=label,
            plist_file=self.launch_agents_directory / f"{label}.plist",
            domain=f"gui/{os.getuid()}",
        )

    def install(
        self,
        profile: str,
        browser: Path,
        *,
        headless: bool,
    ) -> LaunchAgentPaths:
        """Install and load a LaunchAgent that starts one private profile."""
        self._require_macos()
        agent_paths = self.paths(profile)
        profile_paths = self.bridge_manager.paths.create_private_directories(profile)
        with profile_lock(profile_paths.lock_file):
            agent_paths.plist_file.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            agent_paths.plist_file.parent.chmod(0o700)

            if agent_paths.plist_file.is_file():
                self._bootout(agent_paths)

            payload = {
                "Label": agent_paths.label,
                "ProgramArguments": self._program_arguments(
                    profile_paths.profile, browser, headless
                ),
                "ProcessType": "Background",
                "RunAtLoad": True,
                "KeepAlive": False,
                "StandardOutPath": str(
                    profile_paths.log_directory / "launch-agent.log"
                ),
                "StandardErrorPath": str(
                    profile_paths.log_directory / "launch-agent.log"
                ),
            }
            temporary_file = agent_paths.plist_file.with_suffix(".plist.tmp")
            temporary_file.write_bytes(
                plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=True)
            )
            temporary_file.chmod(0o600)
            temporary_file.replace(agent_paths.plist_file)

            try:
                self._run_launchctl(
                    ("bootstrap", agent_paths.domain, str(agent_paths.plist_file))
                )
            except BridgeError:
                agent_paths.plist_file.unlink(missing_ok=True)
                raise
        return agent_paths

    def uninstall(self, profile: str) -> bool:
        """Unload a profile's LaunchAgent, stop its owned browser, and remove it."""
        self._require_macos()
        agent_paths = self.paths(profile)
        installed = agent_paths.plist_file.is_file()
        if installed:
            profile_paths = self.bridge_manager.paths.create_private_directories(
                profile
            )
            with profile_lock(profile_paths.lock_file):
                self._bootout(agent_paths)
                agent_paths.plist_file.unlink(missing_ok=True)
        self.bridge_manager.stop(profile)
        return installed

    @staticmethod
    def _program_arguments(profile: str, browser: Path, headless: bool) -> list[str]:
        arguments = [
            sys.executable,
            "-m",
            "chrome_agent_bridge",
            "start",
            "--profile",
            profile,
            "--browser",
            str(browser),
        ]
        if headless:
            arguments.append("--headless")
        return arguments

    @staticmethod
    def _require_macos() -> None:
        if platform.system() != "Darwin":
            raise BridgeError("LaunchAgent management is supported on macOS only.")

    def _bootout(self, agent_paths: LaunchAgentPaths) -> None:
        result = self._run_launchctl(
            ("bootout", agent_paths.domain, agent_paths.label),
            check=False,
        )
        if result.returncode != 0 and not any(
            message in result.stderr
            for message in ("No such process", "Could not find service")
        ):
            raise BridgeError(
                f"Could not unload LaunchAgent {agent_paths.label}: "
                f"{result.stderr.strip() or 'launchctl failed'}"
            )

    @staticmethod
    def _run_launchctl(
        arguments: tuple[str, ...],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        try:
            result = subprocess.run(  # noqa: S603 - launchctl arguments are internal
                ("/bin/launchctl", *arguments),
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as error:
            raise BridgeError(f"Could not run launchctl: {error}") from error
        if check and result.returncode != 0:
            raise BridgeError(
                f"launchctl {' '.join(arguments)} failed: "
                f"{result.stderr.strip() or 'launchctl failed'}"
            )
        return result
