# Changelog

All notable changes to this project are documented in this file.

## 0.2.0 - 2026-09-04

### Added

- `GrblStreamer(..., rx_buffer_size=128)` makes the controller receive-buffer
  capacity configurable per instance. Existing callers retain the conservative
  128-byte GRBL default, while controllers advertising larger buffers can keep
  more commands in flight without changing streaming semantics.
