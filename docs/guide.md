# User guide

## What it does

Chrome Agent Bridge starts Chrome or Chromium with a profile that belongs only
to the bridge. It gives Chrome a randomly selected local debugging port and
waits for `http://127.0.0.1:<port>/json/version` to respond before reporting
success.

The command never starts the standard Chrome profile. It stores all profiles,
process records, and logs in:

```text
~/Library/Application Support/chrome-agent-bridge/
```

The bridge is **macOS only** in v0.1.0. Linux and Windows support are on the
roadmap.

## Install

Install the published tool with `uv`:

```sh
uv tool install chrome-agent-bridge
```

For a checkout of this repository, run commands without installation:

```sh
uv run chrome-agent-bridge --help
```

Chrome Agent Bridge detects Google Chrome, Chromium, and Chrome Canary in their
usual macOS locations. Use `--browser` for another executable:

```sh
chrome-agent-bridge start --browser "/Applications/Chromium.app/Contents/MacOS/Chromium"
```

## Start and connect

Choose a meaningful profile name. Names can contain letters, numbers, dots,
underscores, and hyphens.

```sh
chrome-agent-bridge start --profile documentation
chrome-agent-bridge status --profile documentation
chrome-agent-bridge mcp-config --profile documentation
```

`mcp-config` prints a snippet such as:

```json
{
  "mcpServers": {
    "chrome-devtools": {
      "command": "npx",
      "args": [
        "-y",
        "chrome-devtools-mcp@latest",
        "--browser-url",
        "http://127.0.0.1:9222"
      ]
    }
  }
}
```

The displayed port is an example. Always use the snippet from your running
profile; every launch chooses a new available loopback port.

To keep the same endpoint after restarting Chrome, select an available local
port:

```sh
chrome-agent-bridge start --profile documentation --headless --port 9222
```

The bridge checks that the requested port is available on `127.0.0.1` before
launching Chrome. `status` and `mcp-config` show the verified port in use. If
the port is busy, choose another one or omit `--port` to let Chrome select a
random port.

To run without a visible window:

```sh
chrome-agent-bridge start --profile documentation --headless
```

Stop it when finished:

```sh
chrome-agent-bridge stop --profile documentation
```

## Authentication and profiles

Chrome Agent Bridge does not read, export, create, or manage credentials,
cookies, or logins. It also must not be pointed at your normal Chrome profile.

If an agent needs an authenticated site, start the dedicated profile **without**
`--headless`, sign in yourself in the visible Chrome window, stop it, then
restart that same dedicated profile with `--headless`. Keep the profile private
and use a separate profile for each purpose that needs a different session.

## Security and multi-agent use

DevTools can control the browser profile it reaches. Treat its address like a
powerful local capability:

- The bridge always passes `--remote-debugging-address=127.0.0.1`; it never
  listens on a network interface.
- It uses Chrome's dynamic port selection by default. `--port` can reserve a
  stable endpoint for a profile, but a predictable local endpoint should not
  be shared in public logs or tickets.
- Give every concurrently running agent a distinct `--profile` name.
- Do not share a profile across agents. The bridge records its owner and Chrome
  also locks active profile data, but separate profiles avoid competing tabs,
  state, and shutdowns.
- Run `stop` once an agent no longer needs browser access.
- Do not put the printed browser URL in public logs or tickets.

The bridge keeps a private owner record and only sends signals to a process
whose command line proves it was launched with the matching dedicated data
directory and loopback debugging settings.

## Troubleshooting

Use `doctor` for a concise local check:

```sh
chrome-agent-bridge doctor --profile documentation
```

If Chrome does not start, pass its executable explicitly with `--browser`.
`doctor` and `start` print the profile's log path when Chrome fails to expose
DevTools. If `status` reports a stale owner record, its process has already
ended; a later `start` or `stop` safely removes that record.

### macOS Launcher behavior

The macOS `open -a "Google Chrome"` launcher reuses an existing browser
instance and does not reliably preserve the command-line DevTools settings this
tool requires. Chrome Agent Bridge starts Chrome's executable inside the app
bundle directly. Do not replace it with `open`, and do not use a Dock-launched
Chrome window as the agent browser.

## Roadmap

- Linux browser discovery and system-appropriate data directories.
- Windows browser discovery and application-data paths.
- Optional richer diagnostics for browser crash reports.
