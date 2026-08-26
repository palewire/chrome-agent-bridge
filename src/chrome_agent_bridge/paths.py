"""Safe paths for dedicated browser profiles and their bridge state."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

PROFILE_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}\Z")


class InvalidProfileNameError(ValueError):
    """Raised when a profile name cannot safely become a file name."""


def validate_profile_name(profile: str) -> str:
    """Return a safe profile name or raise an explanatory error."""
    if not PROFILE_PATTERN.fullmatch(profile) or profile in {".", ".."}:
        message = (
            "Profile names must be 1-64 letters, numbers, dots, underscores, "
            "or hyphens, and must start with a letter or number."
        )
        raise InvalidProfileNameError(message)
    return profile


@dataclass(frozen=True, slots=True)
class ProfilePaths:
    """Filesystem paths owned by one bridge profile."""

    profile: str
    browser_data: Path
    state_file: Path
    lock_file: Path
    active_port_file: Path
    log_directory: Path


@dataclass(frozen=True, slots=True)
class BridgePaths:
    """Top-level location for all private Chrome Agent Bridge files."""

    root: Path

    @classmethod
    def for_current_user(cls) -> BridgePaths:
        """Return the private macOS Application Support location."""
        return cls(
            Path.home() / "Library" / "Application Support" / "chrome-agent-bridge"
        )

    def for_profile(self, profile: str) -> ProfilePaths:
        """Return the paths for a validated profile name."""
        safe_profile = validate_profile_name(profile)
        return ProfilePaths(
            profile=safe_profile,
            browser_data=self.root / "profiles" / safe_profile,
            state_file=self.root / "state" / f"{safe_profile}.json",
            lock_file=self.root / "locks" / f"{safe_profile}.lock",
            active_port_file=self.root
            / "profiles"
            / safe_profile
            / "DevToolsActivePort",
            log_directory=self.root / "logs" / safe_profile,
        )

    def create_private_directories(self, profile: str) -> ProfilePaths:
        """Create the private directories for a profile and return its paths."""
        paths = self.for_profile(profile)
        for directory in (
            self.root,
            paths.browser_data,
            paths.state_file.parent,
            paths.lock_file.parent,
            paths.log_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True, mode=0o700)
            directory.chmod(0o700)
        return paths
