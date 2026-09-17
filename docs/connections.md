# Connections and controller compatibility

[Back to README](../README.md)

The usual `GrblStreamer(port).connect()` still uses 115200 baud, DTR/RTS
low, one connection attempt, soft reset and automatic unlock. New constructor
options are keyword-only; no profile object or subclass is required.

For controllers that need a handshake, for example the AtomStack Swift:

```python
from pygrbl_streamer import GrblStreamer

laser = GrblStreamer(
    "/dev/ttyUSB0", baudrate=460800, auto_unlock=False,
    dtr=True, rts=False, init_commands=("$i2",),
)
try:
    laser.connect(reset=False, attempts=3, retry_delay=2, status_timeout=3)
    if not laser.home(timeout=120, wait_idle=True):
        laser.stop()  # best effort; a disconnected controller cannot receive it
        raise RuntimeError("Homing was not confirmed")
finally:
    laser.disconnect()
```

This example **moves the machine**. The serial handshake and homing sequence
were verified with a standalone Swift script; integration through this API
still needs hardware verification. This does not establish support for Swift
engraving, pause/resume or its receive-buffer capacity.

- `dtr=False`, `rts=False`: signal levels set before opening the serial port.
- `init_commands=()`: single-line ASCII commands, sent after the optional reset
  and before status verification, using the streamer's existing reader.
  Each must return `ok` within `init_timeout=3.0` seconds. Use only idempotent
  connection handshakes, never motion or engraving: retries repeat this sequence.
- `connect(..., attempts=1, retry_delay=2.0, status_timeout=2.0)`: retry serial
  connection failures with a fully closed session between attempts. The final
  failure raises; interrupts and programming errors are not retried. These are
  explicit connection retries, not automatic recovery of running jobs.
- With initialization commands, connection always requires a fresh status.
  `Idle`, `Alarm`, `Hold` and `Door` are accepted; other states fail connection.
  Without automatic unlock, alarm/hold/door remain `State.ALARM`. Connected
  does not mean ready to stream. The default path retains its existing behavior.
- `home(timeout=60, wait_idle=False)` retains its acknowledgement-only default.
  `wait_idle=True` requires `ok` followed by a new `Idle` status, within one
  timeout budget. It sends `$H` once, with no retry or implicit unlock/reset.
  Failure returns `False`; the caller decides whether to stop the machine.
- `reconnect(retries=5, delay=2, reset=False)` can reuse a handshake without
  sending a soft reset. Its default remains `reset=True`. Explicitly pass the
  reset policy on each connect/reconnect; it is not remembered from an earlier
  call, and context-manager entry uses the default `connect()`.

Initialization errors/timeouts, interrupts and failed serial setup close the
port. Old banners/status reports are discarded before a new connection.
Do not run command, homing or connection operations concurrently with a job;
one session owns both serial I/O and acknowledgements.

## Connection lifecycle

`connect()` closes any previous session, configures the serial port, opens it
exclusively and starts one reader and one callback dispatcher. By default it
sends a soft reset, waits for a GRBL banner, checks responsiveness if needed,
and sends `$X`. `connect(reset=False)` skips the soft reset; `auto_unlock=False`
skips `$X`. These are separate choices.

A successful `connect()` returns `None`; failure raises. `disconnect()` closes
the session and can be called repeatedly. Always arrange cleanup with
`try/finally`. A context manager is convenient for the default connection:

```python
from pygrbl_streamer import GrblStreamer

with GrblStreamer("/dev/ttyUSB0") as laser:
    if not laser.send_file("job.gcode"):
        raise RuntimeError("Job did not complete")
```

With a custom reset policy, explicitly connect before entering the context
manager or use `try/finally` as in the Swift example above.

## Retry boundaries

`attempts` counts total attempts, including the first. Only serial/OS failures
are retried, after cleanup and `retry_delay` seconds. Initialization rejection
or timeout is treated as a serial connection failure. No delay follows the
last failed attempt. Each attempt repeats the selected reset policy and all
initialization commands, so an acknowledgement lost during initialization can
cause that command to be sent again.

A successful connection ends the retry loop. Later errors in `home()`,
`command()` or `stream()` do not reconnect or replay anything. `reconnect()` is
an explicit helper returning a boolean; the application must call it and decide
what to do with an interrupted job.

## Receive-buffer size

`rx_buffer_size` is the controller's receive capacity, not a host-side queue
size. The default is 128 bytes, with one byte reserved as a margin. Set a larger
value only when the controller's capacity is known:

```python
laser = GrblStreamer("/dev/ttyUSB0", 460800, rx_buffer_size=4096)
```

The Swift handshake alone does not establish that it supports this larger
buffer. See [streaming](streaming.md) for flow control and completion semantics.

## Compatibility

Targets GRBL 1.1 and compatible controllers, such as grblHAL: diode laser engravers, CNC routers, pen plotters, drag-knife cutters.

Not supported: Ruida-based CO2 lasers, galvo fiber lasers (EZCad/BJJCZ controllers — entirely different protocol), and Marlin-based machines (no character-counting buffer or real-time commands).

I use this library daily in production, driving several lasers concurrently from a Raspberry Pi 4. Tested so far on:

- Acmer P1S
- Acmer P2
- Longer Ray5 20W
- AtomStack A24 Pro
- AtomStack Atelier — a diode **galvo** running GRBL (unlike the gantry machines above)

The Atelier streams identically to the rest, with one current caveat: the machine ships locked and, for now, has to be connected once through LightBurn or lasergrbl to get unlocked before pygrbl_streamer can connect and drive it normally — the same unlock step lasergrbl performs on its own first connection. Reproducing that unlock handshake directly from the library is a work in progress.

Reports of it working (or not) on other machines are welcome via issues.
