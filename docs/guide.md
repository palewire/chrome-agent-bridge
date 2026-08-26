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

`mcp-config` prints a ready-to-paste configuration. The port in the example is
only illustrative:

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

With the default settings, every launch chooses a new available loopback port.
Use the snippet from the current running profile whenever you connect an MCP
client this way.

### Keep one endpoint for GitHub Copilot

If you want to configure GitHub Copilot once and reuse the same endpoint, start
the profile with an available fixed loopback port:

```sh
chrome-agent-bridge start --profile documentation --headless --port 9222
```

Then add this JSON to the GitHub Copilot MCP configuration:

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

Use this startup order whenever you need the connection:

1. Start the bridge with the same profile and port:
   `chrome-agent-bridge start --profile documentation --headless --port 9222`
2. Start or reconnect GitHub Copilot, which uses the saved MCP configuration.
3. Stop the bridge when browser access is no longer needed:
   `chrome-agent-bridge stop --profile documentation`

The bridge checks that the requested port is available on `127.0.0.1` before
launching Chrome. `status` and `mcp-config` show the verified port in use. If
the port is busy, choose another local port and update the MCP configuration,
or omit `--port` to return to random-port mode.

Fixed ports are convenient when a client stores its MCP configuration, but a
random port is preferable when you want a fresh endpoint on every launch or
when several independent profiles are started without preassigning ports.
Random ports also reduce the chance of accidentally connecting a client to a
different browser left on a predictable port.

To run without a visible window:

```sh
chrome-agent-bridge start --profile documentation --headless
```

Stop it when finished:

```sh
chrome-agent-bridge stop --profile documentation
```

## Authentication, recovery, and profiles

Chrome Agent Bridge never reads, exports, creates, or manages credentials,
cookies, or logins. It only starts Chrome with a separate data directory. Never
point it at your normal Chrome profile, and never put passwords, session data,
or the printed DevTools URL in tickets or logs.

### Sign in and resume a session

If an agent needs an authenticated site:

1. Start the dedicated profile **without** `--headless`.
2. Sign in yourself in the visible Chrome window. Complete any MFA, CAPTCHA,
   consent, or device-approval step there.
3. Close any tabs the agent should not use, stop the profile, and restart that
   same profile with `--headless`.

```sh
chrome-agent-bridge start --profile research
# Sign in and complete any verification in the visible window.
chrome-agent-bridge stop --profile research
chrome-agent-bridge start --profile research --headless
```

Headless mode cannot complete an interactive MFA, CAPTCHA, consent, or
device-approval challenge reliably. Stop it, repeat the sign-in flow in headed
mode, then resume headless operation. If the site still refuses the session,
use its supported recovery flow or contact the site; do not copy cookies or
credentials into the bridge.

### Recover an expired session

Sites can expire sessions independently of the bridge. Stop the profile,
restart it in headed mode, and sign in again. Reuse the same profile to retain
other site sessions, or create a separate profile when the site requires a
clean login.

If a profile is stuck or its state is no longer trusted, stop it first and
delete only that profile's bridge data. For example, for the `research` profile:

```sh
chrome-agent-bridge stop --profile research
rm -rf "$HOME/Library/Application Support/chrome-agent-bridge/profiles/research"
rm -f "$HOME/Library/Application Support/chrome-agent-bridge/state/research.json"
rm -f "$HOME/Library/Application Support/chrome-agent-bridge/locks/research.lock"
rm -rf "$HOME/Library/Application Support/chrome-agent-bridge/logs/research"
```

Replace `research` with the exact profile name you intend to reset. Do not
delete the whole `chrome-agent-bridge` directory or another profile. The next
`start` creates a fresh profile, so all sign-ins in the reset profile are lost.

### Revoke a site's session

To sign out one site, use that site's own **Sign out** control in the visible
dedicated profile, then stop the profile. For stronger protection, use the
site's account security page to revoke active sessions or change the password.
If the profile may have been exposed, revoke sessions from a trusted browser,
reset the dedicated profile, and do not resume automation until the account is
secure.

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
- Use one profile per account or task when sessions must not mix.
- Close temporary tabs and stop the profile when the task is complete.
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
