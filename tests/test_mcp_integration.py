"""Optional end-to-end coverage for Chrome DevTools MCP through the bridge."""

import json
import os
import platform
import select
import shlex
import shutil
import signal
import subprocess
import sys
import time
from typing import Any

import pytest

from chrome_agent_bridge.browser import find_browser
from chrome_agent_bridge.manager import BridgeError, BridgeManager
from chrome_agent_bridge.paths import BridgePaths

E2E_ENVIRONMENT_VARIABLE = "CHROME_AGENT_BRIDGE_RUN_MCP_E2E"
MCP_COMMAND_ENVIRONMENT_VARIABLE = "CHROME_DEVTOOLS_MCP_COMMAND"
MCP_TIMEOUT_SECONDS = 30


class McpClient:
    """Minimal newline-delimited JSON-RPC client for a local MCP stdio server."""

    def __init__(self, command: tuple[str, ...]) -> None:
        self.process = subprocess.Popen(  # noqa: S603 - Explicit local test command.
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        self._next_request_id = 1

    def initialize(self) -> dict[str, Any]:
        """Initialize the MCP session and return its advertised tools."""
        self.request(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "chrome-agent-bridge-tests", "version": "0.1.0"},
            },
        )
        self.notify("notifications/initialized")
        return self.request("tools/list", {})

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one request and return its JSON-RPC result."""
        request_id = self._next_request_id
        self._next_request_id += 1
        self._send(
            {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        )
        response = self._read_response(request_id)
        if error := response.get("error"):
            raise AssertionError(f"MCP {method} failed: {error}")
        result = response.get("result")
        if not isinstance(result, dict):
            raise AssertionError(
                f"MCP {method} returned a non-object result: {result!r}"
            )
        return result

    def notify(self, method: str) -> None:
        """Send a JSON-RPC notification."""
        self._send({"jsonrpc": "2.0", "method": method})

    def close(self) -> None:
        """Stop the MCP process and every child it started."""
        if self.process.poll() is not None:
            return
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            self.process.wait(timeout=5)

    def _send(self, message: dict[str, Any]) -> None:
        if self.process.poll() is not None:
            raise AssertionError(
                self._process_error("exited before receiving a request")
            )
        assert self.process.stdin is not None
        self.process.stdin.write(f"{json.dumps(message)}\n")
        self.process.stdin.flush()

    def _read_response(self, request_id: int) -> dict[str, Any]:
        assert self.process.stdout is not None
        deadline = time.monotonic() + MCP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            remaining = deadline - time.monotonic()
            readable, _, _ = select.select([self.process.stdout], [], [], remaining)
            if not readable:
                break
            line = self.process.stdout.readline()
            if not line:
                raise AssertionError(self._process_error("closed its output"))
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(message, dict):
                raise AssertionError(f"MCP returned a non-object message: {message!r}")
            if message.get("id") == request_id:
                return message
        raise AssertionError(
            self._process_error(f"did not answer request {request_id}")
        )

    def _process_error(self, detail: str) -> str:
        if self.process.poll() is None:
            return f"chrome-devtools-mcp {detail}."
        assert self.process.stderr is not None
        stderr = self.process.stderr.read().strip()
        return f"chrome-devtools-mcp {detail}. stderr: {stderr or '(none)'}"


def _mcp_command() -> tuple[str, ...]:
    configured_command = os.environ.get(MCP_COMMAND_ENVIRONMENT_VARIABLE)
    if configured_command:
        if command := tuple(shlex.split(configured_command)):
            return command
        pytest.skip(f"{MCP_COMMAND_ENVIRONMENT_VARIABLE} must not be empty.")
    if npx := shutil.which("npx"):
        return (npx, "--no-install", "chrome-devtools-mcp")
    pytest.skip("Node's npx is required for the MCP end-to-end test.")


def _require_mcp_command(command: tuple[str, ...]) -> None:
    """Skip when the explicitly opted-in test has no local MCP executable."""
    try:
        result = subprocess.run(  # noqa: S603 - Explicit local test command.
            (*command, "--help"),
            check=False,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        pytest.skip(f"chrome-devtools-mcp is not available: {error}")
    if result.returncode != 0:
        pytest.skip(
            "chrome-devtools-mcp is not available locally. "
            f"Set {MCP_COMMAND_ENVIRONMENT_VARIABLE} to its executable, or install it "
            f"before running this test. ({result.stderr.strip()})"
        )


@pytest.mark.e2e
@pytest.mark.timeout(90)
def test_bridge_connects_chrome_devtools_mcp_to_owned_chrome(tmp_path):
    """The bridge endpoint lets MCP open a local page and read its title."""
    if os.environ.get(E2E_ENVIRONMENT_VARIABLE) != "1":
        pytest.skip(f"Set {E2E_ENVIRONMENT_VARIABLE}=1 to run this optional test.")
    if platform.system() != "Darwin":
        pytest.skip("Chrome Agent Bridge supports this end-to-end test on macOS only.")

    try:
        browser = find_browser()
    except BridgeError as error:
        pytest.skip(str(error))
    command = _mcp_command()
    _require_mcp_command(command)

    manager = BridgeManager(BridgePaths(tmp_path / "bridge"))
    client: McpClient | None = None
    try:
        health = manager.start("mcp-e2e", browser, headless=True)
        client = McpClient((*command, "--browser-url", health.browser_url))
        tools = client.initialize()["tools"]
        tool_names = {
            tool["name"]
            for tool in tools
            if isinstance(tool, dict) and isinstance(tool.get("name"), str)
        }
        assert {"new_page", "evaluate_script"} <= tool_names

        client.request(
            "tools/call",
            {
                "name": "new_page",
                "arguments": {
                    "url": (
                        "data:text/html,<title>Chrome Agent Bridge MCP Test</title>"
                        "<p>local test page</p>"
                    )
                },
            },
        )
        title_result = client.request(
            "tools/call",
            {
                "name": "evaluate_script",
                "arguments": {"function": "() => document.title"},
            },
        )
        title_text = "\n".join(
            item["text"]
            for item in title_result.get("content", [])
            if isinstance(item, dict) and isinstance(item.get("text"), str)
        )
        assert "Chrome Agent Bridge MCP Test" in title_text
    finally:
        if client is not None:
            client.close()
        manager.stop("mcp-e2e")


@pytest.mark.unit
def test_mcp_client_uses_the_stdio_protocol():
    """The test client initializes a local newline-delimited MCP server."""
    server = """
import json
import sys

for line in sys.stdin:
    message = json.loads(line)
    if "id" not in message:
        continue
    if message["method"] == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {}}
    elif message["method"] == "tools/list":
        result = {"tools": [{"name": "new_page"}, {"name": "evaluate_script"}]}
    else:
        result = {}
    print(json.dumps({"jsonrpc": "2.0", "id": message["id"], "result": result}), flush=True)
"""
    client = McpClient((sys.executable, "-u", "-c", server))
    try:
        assert client.initialize()["tools"] == [
            {"name": "new_page"},
            {"name": "evaluate_script"},
        ]
    finally:
        client.close()
