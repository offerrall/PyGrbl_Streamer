# API, callbacks and state

[Back to README](../README.md)

## Methods

| Method | Description |
|---|---|
| `connect()` / `disconnect()` | open/close the session; safe to call repeatedly |
| `stream(commands, total=None, ...)` | stream any iterable of commands |
| `send_file(path, ...)` | stream a file lazily; same options as `stream()` |
| `command(cmd)` | send one command interactively, wait for ok/error |
| `pause()` / `resume()` / `stop()` | real-time job control |
| `unlock()` / `home()` | `$X` / `$H` |
| `reconnect(retries, delay, reset=...)` | explicitly retry connection after a disconnect |
| `sync(timeout=2)` | query the controller and update local state |
| `reset(unlock=True)` | soft reset, optionally unlock, then synchronize |

See [connection options and homing](connections.md) and [streaming options](streaming.md) for parameters and failure handling.

## Callbacks

Assign as attributes or override in a subclass. Callbacks run on a dedicated dispatcher thread. Keep them short: a slow callback delays later callbacks, although serial reading continues separately. If one of your callbacks raises, the exception is reported through `log_callback` instead of being silently swallowed.

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

## State and recovery

`State` contains `DISCONNECTED`, `CONNECTING`, `IDLE`, `STREAMING`, `PAUSED`
and `ALARM`. `is_connected` is true for states other than `DISCONNECTED` and
`CONNECTING`; it does not guarantee that a job can start. `stream()` requires
local state `IDLE`.

`last_status` holds the latest parsed status report: `state` is the firmware
state string, `raw` is the complete report and `time` is its reception time.
A previously received report can be stale. Firmware state and the streamer's
local state are different: a local `IDLE` is not itself fresh evidence that
physical motion has finished.

`sync(timeout=2)` requests a fresh status. Alarm, Hold and Door map to local
`ALARM`; other firmware states, including Run, Jog and Home, map to local
`IDLE`. During a local stream or pause it returns the existing state without
querying. On an unresponsive controller it reports disconnection. Use the raw
status when the distinction between physically idle and moving matters.

An `ALARM` message aborts a running stream; it is not automatically cleared
mid-job. `unlock()` explicitly sends `$X`. The default `connect()` and
`reset(unlock=True)` also request unlock, as part of their startup/recovery
sequence. Set `auto_unlock=False` for a connection that must preserve alarms.

`reset()` aborts streaming, sends a soft reset and synchronizes after optional
unlock. Its boolean result reflects the mapped local state, not restored
position or a resumable job. Homing is separate; see `home(wait_idle=True)` in
[connections](connections.md) for acknowledgement plus fresh-Idle confirmation.

## Diagnostics

- No connection: check port ownership, baud rate, DTR/RTS and the initialization
  sequence. Log received lines and connection errors before changing options.
- Connected but unable to stream: inspect local state and `last_status`; do not
  clear an alarm solely to suppress an error message.
- Homing returns `False`: inspect alarm/error callbacks and distinguish missing
  acknowledgement from missing final Idle. It does not retry or stop itself.
- Interrupted job: reconnecting establishes a new session, not continuation of
  the old motion. Decide recovery in the application.
