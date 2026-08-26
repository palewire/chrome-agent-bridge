# Chrome Agent Bridge

Run a dedicated local Chrome or Chromium profile for AI agents that connect
through Chrome DevTools MCP. The bridge starts Chrome with a random
**loopback-only** debugging port, tracks the process it owns, and never uses
your normal browser profile.

> **macOS only in v0.1.0.** Linux and Windows support are planned.

## Install

```sh
uv tool install chrome-agent-bridge
```

## Use

Start a dedicated, visible browser profile:

```sh
chrome-agent-bridge start --profile research
```

Sign in to sites manually in that visible browser if needed. Then stop it and
restart it for an agent in headless mode:

```sh
chrome-agent-bridge stop --profile research
chrome-agent-bridge start --profile research --headless
chrome-agent-bridge mcp-config --profile research
```

Copy the printed MCP configuration into your agent's configuration. Check or
stop a profile at any time:

```sh
chrome-agent-bridge status --profile research
chrome-agent-bridge stop --profile research
```

To start a named profile automatically at macOS login, install its LaunchAgent:

```sh
chrome-agent-bridge install-launch-agent --profile research
chrome-agent-bridge uninstall-launch-agent --profile research
```

The LaunchAgent starts the same private, loopback-only profile with a dynamic
DevTools port. Uninstalling it stops the bridge-owned browser but keeps profile
data and logs.

To keep the same endpoint across restarts, choose an available local port:

```sh
chrome-agent-bridge start --profile research --headless --port 9222
```

The bridge checks that the port is available on `127.0.0.1` before starting
Chrome. It always keeps DevTools bound to loopback, but a stable port makes the
endpoint easier to reuse, so do not use it in public logs or tickets.

The bridge does not collect, read, export, or manage credentials, cookies, or
logins. The dedicated profile remains under your macOS Application Support
folder and must not be your standard Chrome profile.

## Security

- DevTools listens only on `127.0.0.1` and uses a new port each start unless
  `start --port` selects an available local port.
- Give each person or agent a separate `--profile` name.
- Treat a running DevTools endpoint as powerful local access to that profile.
  Stop it when it is not needed.

See the [full documentation](https://palewi.re/chrome-agent-bridge/) for
troubleshooting, multi-agent guidance, and macOS launcher notes.

## Development

```sh
make bootstrap
make verify
```

### Optional MCP end-to-end test

The normal test suite does not require Chrome, Node, or network access. To run
the bridge-to-MCP test, use macOS with Chrome or Chromium and a local
`chrome-devtools-mcp` installation:

```sh
CHROME_AGENT_BRIDGE_RUN_MCP_E2E=1 uv run pytest tests/test_mcp_integration.py
```

The test starts a temporary, headless bridge profile, attaches
`chrome-devtools-mcp` through its verified DevTools URL, opens a local data
page, reads its title, and stops both processes. It uses
`npx --no-install chrome-devtools-mcp` by default, so it never downloads the
MCP server. Set `CHROME_DEVTOOLS_MCP_COMMAND` to the command for an existing
installation when it is not available to `npx`.
