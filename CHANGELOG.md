# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- Adopted the `src/` layout and split the public API (`__init__.py`) from the
  implementation (`streamer.py`).
- Added a `py.typed` marker (PEP 561) so downstream type checkers honor the
  shipped type hints.

## [0.0.1] - 2026-06-11

### Added
- Initial release: `GrblStreamer`, a thread-safe, fault-tolerant, source-agnostic
  G-code streamer for GRBL controllers.
