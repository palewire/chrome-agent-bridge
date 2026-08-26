"""Click command line interface for Chrome Agent Bridge."""

from __future__ import annotations

import json
from pathlib import Path
from typing import NoReturn

import click

from .browser import find_browser
from .launch_agent import LaunchAgentManager
from .manager import BridgeError, BridgeManager
from .paths import InvalidProfileNameError


def _manager() -> BridgeManager:
    """Create the bridge manager for one CLI invocation."""
    return BridgeManager()


def _launch_agent_manager() -> LaunchAgentManager:
    """Create the LaunchAgent manager for one CLI invocation."""
    return LaunchAgentManager(_manager())


def _handle_error(error: Exception) -> NoReturn:
    """Convert expected bridge errors to consistent Click messages."""
    raise click.ClickException(str(error)) from error


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
def main() -> None:
    """Safely manage a dedicated local Chrome DevTools endpoint."""


@main.command()
@click.option(
    "--profile", default="default", show_default=True, help="Dedicated profile name."
)
@click.option(
    "--browser",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Chrome or Chromium executable. Detected automatically when omitted.",
)
@click.option(
    "--headless/--headed",
    default=False,
    show_default=True,
    help="Run Chrome without a visible window.",
)
def start(profile: str, browser: Path | None, *, headless: bool) -> None:
    """Start Chrome and print its private DevTools URL."""
    try:
        health = _manager().start(profile, find_browser(browser), headless=headless)
    except (BridgeError, InvalidProfileNameError) as error:
        _handle_error(error)
    click.echo(f"Chrome is ready at {health.browser_url}")
    click.echo(f"Browser: {health.browser}")


@main.command()
@click.option(
    "--profile", default="default", show_default=True, help="Dedicated profile name."
)
def stop(profile: str) -> None:
    """Stop Chrome when this bridge owns the selected profile."""
    try:
        stopped = _manager().stop(profile)
    except (BridgeError, InvalidProfileNameError) as error:
        _handle_error(error)
    click.echo("Chrome stopped." if stopped else "Chrome is not running.")


@main.command()
@click.option(
    "--profile", default="default", show_default=True, help="Dedicated profile name."
)
def status(profile: str) -> None:
    """Show the selected profile's owner record and endpoint health."""
    try:
        bridge_status = _manager().status(profile)
    except (BridgeError, InvalidProfileNameError) as error:
        _handle_error(error)
    if bridge_status.state is None:
        click.echo("Status: stopped")
        return
    click.echo(f"Profile: {bridge_status.state.profile}")
    click.echo(f"PID: {bridge_status.state.pid}")
    click.echo(f"Started: {bridge_status.state.started_at}")
    if bridge_status.is_running:
        assert bridge_status.health is not None
        click.echo("Status: running")
        click.echo(f"DevTools: {bridge_status.health.browser_url}")
    elif bridge_status.owned:
        click.echo("Status: starting or unhealthy")
    else:
        click.echo("Status: stale owner record")


@main.command()
@click.option(
    "--profile", default="default", show_default=True, help="Dedicated profile name."
)
@click.option(
    "--browser",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Chrome or Chromium executable to check.",
)
def doctor(profile: str, browser: Path | None) -> None:
    """Check browser detection, profile paths, ownership, and endpoint health."""
    manager = _manager()
    try:
        paths = manager.paths.create_private_directories(profile)
        detected_browser = find_browser(browser)
        bridge_status = manager.status(profile)
    except (BridgeError, InvalidProfileNameError) as error:
        _handle_error(error)
    click.echo(f"Data directory: {manager.paths.root}")
    click.echo(f"Profile directory: {paths.browser_data}")
    click.echo(f"Browser: {detected_browser}")
    if bridge_status.is_running:
        assert bridge_status.health is not None
        click.echo(f"DevTools health: healthy ({bridge_status.health.browser_url})")
    elif bridge_status.state is None:
        click.echo("DevTools health: stopped")
    else:
        click.echo("DevTools health: unhealthy")


@main.command(name="mcp-config")
@click.option(
    "--profile", default="default", show_default=True, help="Dedicated profile name."
)
def mcp_config(profile: str) -> None:
    """Print a Chrome DevTools MCP configuration for a running profile."""
    try:
        config = _manager().mcp_config(profile)
    except (BridgeError, InvalidProfileNameError) as error:
        _handle_error(error)
    click.echo(json.dumps(config, indent=2))


@main.command(name="install-launch-agent")
@click.option(
    "--profile", default="default", show_default=True, help="Dedicated profile name."
)
@click.option(
    "--browser",
    type=click.Path(path_type=Path, dir_okay=False),
    help="Chrome or Chromium executable. Detected automatically when omitted.",
)
@click.option(
    "--headless/--headed",
    default=True,
    show_default=True,
    help="Start the profile without a visible window at login.",
)
def install_launch_agent(profile: str, browser: Path | None, *, headless: bool) -> None:
    """Install and immediately load a profile's macOS LaunchAgent."""
    try:
        detected_browser = find_browser(browser)
        agent_paths = _launch_agent_manager().install(
            profile, detected_browser, headless=headless
        )
    except (BridgeError, InvalidProfileNameError) as error:
        _handle_error(error)
    click.echo(f"LaunchAgent installed: {agent_paths.label}")
    click.echo(f"Profile: {profile}")
    click.echo("Use uninstall-launch-agent to stop the owned browser and remove it.")


@main.command(name="uninstall-launch-agent")
@click.option(
    "--profile", default="default", show_default=True, help="Dedicated profile name."
)
def uninstall_launch_agent(profile: str) -> None:
    """Unload and remove a profile's macOS LaunchAgent."""
    try:
        removed = _launch_agent_manager().uninstall(profile)
    except (BridgeError, InvalidProfileNameError) as error:
        _handle_error(error)
    if removed:
        click.echo(f"LaunchAgent removed for profile '{profile}'.")
    else:
        click.echo(f"No LaunchAgent installed for profile '{profile}'.")
