# Browser security guide

Chrome DevTools access is powerful. Anyone who can reach the debugging
endpoint can inspect tabs, navigate pages, and use the browser with the
permissions available to that profile. Treat the endpoint URL as a private
capability, not as a normal web address.

## Keep the endpoint local

Chrome Agent Bridge binds DevTools to `127.0.0.1` and chooses a fresh local
port for each launch. Keep that loopback-only binding. Do not replace it with
`0.0.0.0`, a LAN address, or a publicly reachable tunnel. Do not paste the
printed debugging URL into tickets, chat, or public logs.

## Isolate browser profiles

Use a dedicated `--profile` for each agent or purpose. Never point the bridge
at your normal Chrome profile: it may contain personal tabs, cookies, saved
sessions, extensions, and other private data. The bridge's profiles are
separate from the standard profile so an agent cannot accidentally control
your everyday browser.

When multiple agents run at once, give each one a distinct profile. Do not
share profiles between agents; separate profiles prevent competing tabs,
browser state, and shutdown commands.

## Limit the access window

Stop the profile as soon as the agent no longer needs it:

```sh
chrome-agent-bridge stop --profile agent-1
```

Close temporary tabs and windows created for a task before stopping the
profile. This reduces the chance that sensitive pages remain available to a
later task or are mistaken for part of another agent's session.

For authenticated sites, sign in yourself in the visible dedicated profile,
then stop it and restart that same profile headlessly. Do not put credentials
in agent prompts or scripts.
