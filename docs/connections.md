# Connections

`GrblStreamer(port).connect()` opens the default connection: 115200 baud,
DTR/RTS low, one connection attempt, soft reset and automatic unlock (`$X`).
Every other option is a keyword argument; no profile object or subclass is
required.

## Connection lifecycle

`connect()` closes any previous session, configures the serial port, opens it
exclusively and starts one reader and one callback dispatcher. Old banners and
status reports are discarded before the new connection. By default it sends a
soft reset, waits for a GRBL banner, checks responsiveness if needed, and sends
`$X`. `connect(reset=False)` skips the soft reset; `auto_unlock=False` skips
`$X`. These are separate choices.

A successful `connect()` returns `None`; failure raises. `disconnect()` closes
the session and can be called repeatedly. Always arrange cleanup, with a
context manager or with `try/finally`. Entering the context manager calls the
default `connect()` unless the streamer is already connected; with a custom
reset policy, connect explicitly before entering it, or use `try/finally` as in
the handshake example below.

Initialization errors and timeouts, interrupts and failed serial setup close
the port. Do not run command, homing or connection operations concurrently with
a job; one session owns both serial I/O and acknowledgements.

## Handshake connections

Some controllers need a handshake, for example the AtomStack Swift:

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

This example **moves the machine**. See
[Limitations](limitations.md#atomstack-swift) for what has been verified on the
Swift.

- `dtr=False`, `rts=False`: signal levels set before opening the serial port.
- `init_commands=()`: single-line ASCII commands, sent after the optional reset
  and before status verification, using the streamer's own reader.
  Each must return `ok` within `init_timeout=3.0` seconds. Use only idempotent
  connection handshakes, never motion or engraving: retries repeat this sequence.
- With initialization commands, connection always requires a fresh status.
  `Idle`, `Alarm`, `Hold` and `Door` are accepted; other states fail connection.
  Without automatic unlock, alarm, hold and door remain `State.ALARM`: connected
  does not mean ready to stream.

## Homing

`home(timeout=60, wait_idle=False)` sends `$H` once and, by default, waits only
for its acknowledgement. `wait_idle=True` requires `ok` followed by a new `Idle`
status, within one timeout budget. There is no retry and no implicit unlock or
reset. Failure returns `False`; the caller decides whether to stop the machine.

## Retries and reconnection

`connect(..., attempts=1, retry_delay=2.0, status_timeout=2.0)` retries serial
connection failures, with a fully closed session between attempts. `attempts`
counts total attempts, including the first. Only serial and OS failures are
retried, after cleanup and `retry_delay` seconds; initialization rejection or
timeout counts as a serial connection failure. No delay follows the last failed
attempt, and the final failure raises. Interrupts and programming errors are not
retried. Each attempt repeats the selected reset policy and all initialization
commands, so an acknowledgement lost during initialization can cause that
command to be sent again.

A successful connection ends the retry loop. Later errors in `home()`,
`command()` or `stream()` do not reconnect or replay anything; retries are
explicit connection retries, not recovery of running jobs.

`reconnect(retries=5, delay=2, reset=True)` is an explicit helper that returns a
boolean. `reset=False` reuses a handshake connection without a soft reset. The
reset policy is not remembered from an earlier call: pass it on each
`connect()` and `reconnect()`.

## Receive-buffer size

`rx_buffer_size` is the controller's receive capacity, not a host-side queue
size. The default is 128 bytes, the GRBL default, with one byte reserved as a
margin. Set a larger value only when the controller's capacity is known:

```python
from pygrbl_streamer import GrblStreamer

laser = GrblStreamer("/dev/ttyUSB0", 460800, rx_buffer_size=4096)
```

See [Streaming](streaming.md#flow-control-and-completion) for flow control and
completion semantics.
