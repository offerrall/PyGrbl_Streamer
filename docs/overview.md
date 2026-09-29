# Overview

pygrbl-streamer sends G-code to a GRBL controller and keeps the controller's
receive buffer full without overflowing it (character-counting flow control).
The G-code can come from a file or from any Python iterable, such as a
generator that computes the job on the fly. One `GrblStreamer` owns one serial
connection; run one per machine to drive several machines from one computer.

The companion library [pygrbl-build](https://offerrall.github.io/pygrbl-build/)
generates G-code from images and SVGs; its line iterators can be streamed
directly.

## What it provides

- **Lazy streaming.** `stream()` accepts any iterable of commands and
  `send_file()` reads a file line by line.
- **Progress.** A callback driven by acknowledged commands, with an exact
  percentage for files and for streams of known length.
- **Job control.** Pause (feed hold), resume (cycle start) and stop (feed hold
  followed by soft reset) from another thread while a job streams.
- **Configurable connections.** Baud rate, DTR/RTS levels, initialization
  handshakes, bounded connection retries and the controller's receive-buffer
  size are keyword arguments; the default connection needs none of them.
- **Explicit failure handling.** Failures raise or return `False`; nothing is
  retried or resumed behind the caller's back.
- **Callbacks, not a logging framework.** State, alarm, error, raw traffic,
  disconnection and diagnostics are callbacks the application wires as it wants.

## Supported controllers

GRBL 1.1 and compatible controllers, such as grblHAL: diode laser engravers,
CNC routers, pen plotters and drag-knife cutters. See
[Limitations](limitations.md#unsupported-controllers) for the machines it does
not drive.

## Tested machines

It drives several lasers concurrently from a Raspberry Pi 4 in production.
Tested on:

- Acmer P1S
- Acmer P2
- Longer Ray5 20W
- AtomStack A24 Pro
- AtomStack Atelier, a diode **galvo** running GRBL (unlike the gantry machines
  above); see [its unlock caveat](limitations.md#atomstack-atelier-unlock)

Reports of it working, or not, on other machines are welcome as
[issues](https://github.com/offerrall/PyGrbl_Streamer/issues).

## Safety

Streaming a job executes it on the machine: the examples in this documentation
move the machine and fire the laser.

- Laser users: verify `$32=1` (laser mode) so the beam is disabled during feed hold.
- The library streams G-code; it does not validate it. Garbage in, garbage out.

## Compatibility policy

The 1.x public API keeps existing calls compatible. Controller-specific
behavior is added through optional keyword arguments whose defaults preserve
the existing behavior. A breaking change to the public API requires a new major
version.
