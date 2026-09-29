# Changelog

All notable changes to this project are documented in this file.

## 1.0.1

### Changed

- Documentation only: shorter page titles in the README, the README title without
  the version, and the release notes for maintainers moved from `docs/` to
  `RELEASING.md`.

## 1.0.0

### Added

- Stable public API with the existing 0.2.0 defaults and positional arguments.
- Optional keyword-only DTR/RTS levels and acknowledged initialization commands.
- Bounded connection retries, per-command initialization timeout and status
  timeout; handshake connections preserve alarm states without auto-unlock.
- Optional fresh-Idle confirmation for homing, sharing its timeout with the
  acknowledgement wait; homing and jobs are never automatically retried.
- Optional reset policy for `reconnect()`.

### Fixed

- Discard stale banners/status before opening a new connection.
- Always attempt to close the serial port even when setup or buffer cleanup
  fails; failed connection attempts and interrupts release the session.

## 0.2.0 - 2026-09-04

### Added

- `GrblStreamer(..., rx_buffer_size=128)` makes the controller receive-buffer
  capacity configurable per instance. Existing callers retain the conservative
  128-byte GRBL default, while controllers advertising larger buffers can keep
  more commands in flight without changing streaming semantics.
