# PyGrbl_Streamer 0.0.1

[![PyPI](https://img.shields.io/pypi/v/pygrbl_streamer.svg)](https://pypi.org/project/pygrbl_streamer/)

Robust, source-agnostic G-code streamer for GRBL controllers over serial.

Part of the **pygrbl** family, a set of libraries to manage GRBL.
Companion to [`pygrbl_build`](https://github.com/offerrall/pygrbl_build)

> **v0.0.1** — Complete rewrite. The API is not compatible with previous internal versions and may change before 0.1.0.

## Features

- Stream from any source: lists, generators, files, network — `stream()` accepts any iterable of commands
- Constant memory and instant start: files of any size are read lazily in a single pass — no preloading, no counting pass
- Zero-cost progress: file progress is derived from bytes consumed vs file size, accurate to within a few commands
- Character-counting streaming protocol against GRBL's 128-byte RX buffer
- Clean connect/disconnect lifecycle — threads are joined, nothing hangs
- Physical disconnection detection with automatic reconnect support
- Real-time job control: pause, resume, stop
- Event callbacks for progress, state changes, alarms, errors, raw I/O, and internal diagnostics
- Every blocking wait is bounded by a timeout
- Lightweight: runs multiple machines concurrently on a Raspberry Pi

## Installation

```bash
pip install pygrbl-streamer
```

Requires Python 3.10+ and `pyserial`.

## Quick start

```python
from pygrbl_streamer import GrblStreamer

g = GrblStreamer(port='/dev/ttyUSB0')  # 'COM3' on Windows
g.progress_callback = lambda pct, cmd: print(f'{pct}%')

g.connect()
g.send_file('job.gcode')   # any size, constant memory, starts instantly
g.disconnect()
```

## Streaming from any source

`stream()` consumes commands lazily from any iterable. Your application decides where the G-code comes from:

```python
def square(size=10, power=300, feed=1000):
    yield 'G90 G21'
    yield f'M4 S{power}'
    yield f'G1 X{size} F{feed}'
    yield f'G1 Y{size}'
    yield 'G1 X0'
    yield 'G1 Y0'
    yield 'M5'

g.stream(square(), total=7)
```

Chain chunks back-to-back without stopping the machine between them:

```python
g.stream(chunk_1, wait_for_idle=False)
g.stream(chunk_2, wait_for_idle=False)
g.stream(final_chunk)   # only the last chunk waits for Idle
```

## Progress reporting

`progress_callback(percent, command)` fires on *acknowledged* commands. The percentage source, in order of precedence:

1. **Source-provided** — if your iterable exposes a `percent()` method returning 0–100, it is the authority. `send_file()` uses this internally (bytes read vs file size).
2. **`total`** — pass the command count to `stream()` for exact 0–100%.
3. **Heartbeat** — with neither, the callback fires every 100 acked commands with `percent=-1`.

## Job control

Streaming calls are blocking. Run them in a thread to control the job from elsewhere:

```python
import threading

threading.Thread(target=g.send_file, args=('job.gcode',)).start()

g.pause()   # immediate feed hold (!)
g.resume()  # cycle start (~)
g.stop()    # abort: feed hold + soft reset
```

## API overview

| Method | Description |
|---|---|
| `connect()` / `disconnect()` | open/close the session; safe to call repeatedly |
| `stream(commands, total=None, ...)` | stream any iterable of commands |
| `send_file(path, ...)` | stream a file lazily; same options as `stream()` |
| `command(cmd)` | send one command interactively, wait for ok/error |
| `pause()` / `resume()` / `stop()` | real-time job control |
| `unlock()` / `home()` | `$X` / `$H` |
| `reconnect(retries, delay)` | retry loop after a physical disconnect |

## Callbacks

Assign as attributes or override in a subclass. All callbacks run on a dedicated thread and can never block serial communication. If one of your callbacks raises, the exception is reported through `log_callback` instead of being silently swallowed.

| Callback | Signature | Fires on |
|---|---|---|
| `progress_callback` | `(percent, command)` | acknowledged command progress (`-1` for unbounded streams) |
| `state_callback` | `(state)` | state machine transitions |
| `alarm_callback` | `(line)` | GRBL `ALARM:n` |
| `error_callback` | `(line)` | GRBL `error:n` or internal errors |
| `send_callback` / `receive_callback` | `(data)` | raw serial traffic |
| `disconnect_callback` | `(reason)` | physical disconnection |
| `log_callback` | `(level, message)` | internal diagnostics (`'debug'`/`'info'`/`'warning'`) |

### Logging integration

The library imposes no logging framework. Wire the callbacks to Python's standard `logging` in your application:

```python
import logging
log = logging.getLogger('laser1')

g.log_callback = lambda lv, m: getattr(log, lv)(m)
g.error_callback = lambda l: log.warning('GRBL error: %s', l)
g.alarm_callback = lambda l: log.error('ALARM: %s', l)
g.disconnect_callback = lambda r: log.critical('disconnected: %s', r)
g.receive_callback = lambda l: log.debug('<< %s', l)
g.send_callback = lambda d: log.debug('>> %s', d.strip())
```

## States

`DISCONNECTED → CONNECTING → IDLE ⇄ STREAMING ⇄ PAUSED`, plus `ALARM`.

An alarm aborts the running job and is **never cleared automatically** — call `unlock()` explicitly. After `stop()`, machine position is untrusted: run `home()` before the next job.

## Compatibility

Works with any GRBL 1.1 (or compatible, e.g. grblHAL) controller: diode laser engravers, CNC routers, pen plotters, drag-knife cutters.

Not supported: Ruida-based CO2 lasers, galvo fiber lasers (EZCad/BJJCZ controllers — entirely different protocol), and Marlin-based machines (no character-counting buffer or real-time commands).

I use this library daily in production, driving several lasers concurrently from a Raspberry Pi 4. Tested so far on:

- Acmer P1S
- Acmer P2
- Longer Ray5 20W
- AtomStack A24 Pro
- AtomStack Atelier — a diode **galvo** running GRBL (unlike the gantry machines above)

The Atelier streams identically to the rest, with one current caveat: the machine ships locked and, for now, has to be connected once through LightBurn or lasergrbl to get unlocked before pygrbl_streamer can connect and drive it normally — the same unlock step lasergrbl performs on its own first connection. Reproducing that unlock handshake directly from the library is a work in progress.

Reports of it working (or not) on other machines are welcome via issues.

## Safety notes

- Laser users: verify `$32=1` (laser mode) so the beam is disabled during feed hold.
- Commands longer than GRBL's RX buffer (127 chars) are skipped with an error event instead of deadlocking the stream.
- This library streams G-code; it does not validate it. Garbage in, garbage out.

## License

MIT