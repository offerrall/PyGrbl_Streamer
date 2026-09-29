# Changelog

All notable changes to this project are documented in this file.

## 1.0.4 - 2026-09-29

### Changed

- Documentation only: the README's Documentation list links each page on the
  documentation site, so readers on GitHub and PyPI land there. The code is the same as 1.0.3.

## 1.0.3 - 2026-09-29

### Changed

- Documentation only: the README becomes a short entrance to the documentation
  site at https://offerrall.github.io/pygrbl-streamer/, and `docs/overview.md`
  holds the introduction: supported controllers, tested machines, safety and the
  compatibility policy.
- New `docs/limitations.md` gathers the unsupported controllers, the AtomStack
  Atelier and Swift caveats, the final-drain error gap and job resumption.
- `RELEASING.md` moves to `docs/releasing.md`, with generic release steps.
- Every example uses `laser` and imports what it needs; the pages describe the
  current behavior without references to earlier versions, and the default
  connection and lazy streaming are each described once.
- `pyproject.toml`: a Documentation URL, Homepage pointing to the documentation
  site, a Changelog URL, Python 3.10 to 3.14 classifiers and a description that
  matches the README.
- The code is the same as 1.0.2.

## 1.0.2 - 2026-09-29

### Changed

- Metadata only: the distribution name is spelled `pygrbl-streamer`, PyPI's
  canonical form, in `pyproject.toml` and the documentation.
  `pip install pygrbl-streamer` and `import pygrbl_streamer` are unchanged; the
  code is the same as 1.0.1.

## 1.0.1 - 2026-09-29

### Changed

- Documentation only: shorter page titles in the README, the README title without
  the version, and the release notes for maintainers moved from `docs/` to
  `RELEASING.md`.

## 1.0.0 - 2026-09-17

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

## 0.2.0 - 2026-09-09

### Added

- `GrblStreamer(..., rx_buffer_size=128)` makes the controller receive-buffer
  capacity configurable per instance. Existing callers retain the conservative
  128-byte GRBL default, while controllers advertising larger buffers can keep
  more commands in flight without changing streaming semantics.
