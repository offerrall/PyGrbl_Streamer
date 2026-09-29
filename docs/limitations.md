# Limitations

## Unsupported controllers

- Ruida-based CO2 lasers.
- Galvo fiber lasers with EZCad/BJJCZ controllers, which use an entirely
  different protocol.
- Marlin-based machines, which have no character-counting buffer and no
  real-time commands.

## AtomStack Atelier unlock

The AtomStack Atelier ships locked. It has to be connected once through
LightBurn or LaserGRBL, which perform the unlock handshake on their first
connection; after that, pygrbl-streamer connects and drives it like any other
tested machine. The library does not perform that unlock handshake itself.

## AtomStack Swift

The Swift's serial handshake and homing sequence (the
[handshake example](connections.md#handshake-connections)) were verified with a
standalone script, not through this library's API. Swift engraving,
pause/resume and its receive-buffer capacity are unverified.

## Errors during the final drain

`stop_on_error=True` does not check GRBL error responses received while the
last acknowledgements drain at the end of a stream. Those errors still reach
`error_callback`.

## No job resumption

A stopped, alarmed or disconnected job cannot be continued. `stop()` and
`reset()` flush the controller's buffers, and `reconnect()` establishes a new
session, not a continuation of the old motion. The application decides how to
recover an interrupted job.
