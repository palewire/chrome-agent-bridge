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

The bridge does not collect, read, export, or manage credentials, cookies, or
logins. The dedicated profile remains under your macOS Application Support
folder and must not be your standard Chrome profile.

## Security

- DevTools listens only on `127.0.0.1` and uses a new port each start.
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
