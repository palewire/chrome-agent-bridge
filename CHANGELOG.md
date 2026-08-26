# Changelog

All notable changes to this project are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Support an optional, checked loopback DevTools port with `start --port`.

### Changed

### Fixed

### Removed

### Security

- Document headed authentication, session recovery, safe profile reset, and
  site-session revocation guidance.
- Add a browser security guide covering DevTools access, loopback binding,
  profile isolation, multi-agent separation, and temporary tab cleanup.

## [0.1.0] - 2026-08-26

### Added

- Introduce `chrome-agent-bridge`, a macOS CLI that safely manages a dedicated,
  loopback-only Chrome DevTools endpoint for AI agents.

### Changed

### Fixed

### Removed

### Security

[Unreleased]: https://github.com/palewire/chrome-agent-bridge/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/palewire/chrome-agent-bridge/releases/tag/v0.1.0
