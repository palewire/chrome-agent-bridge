"""Tests for safe dedicated profile paths."""

import pytest

from chrome_agent_bridge.paths import (
    BridgePaths,
    InvalidProfileNameError,
    validate_profile_name,
)


@pytest.mark.unit
@pytest.mark.parametrize("profile", ["default", "agent-1", "docs.v2", "A_b"])
def test_validate_profile_name_accepts_safe_names(profile):
    """Safe profile names are preserved."""
    assert validate_profile_name(profile) == profile


@pytest.mark.unit
@pytest.mark.parametrize("profile", ["", "../normal", "/tmp/profile", "two words", "."])
def test_validate_profile_name_rejects_paths_and_spaces(profile):
    """Profile names cannot escape the private data directory."""
    with pytest.raises(InvalidProfileNameError):
        validate_profile_name(profile)


@pytest.mark.unit
def test_create_private_directories(tmp_path):
    """Profile paths live below a private bridge root."""
    bridge_paths = BridgePaths(tmp_path / "bridge")

    paths = bridge_paths.create_private_directories("agent-1")

    assert paths.browser_data == tmp_path / "bridge" / "profiles" / "agent-1"
    assert paths.state_file == tmp_path / "bridge" / "state" / "agent-1.json"
    assert paths.active_port_file == paths.browser_data / "DevToolsActivePort"
    assert paths.browser_data.is_dir()
    assert paths.log_directory.is_dir()
