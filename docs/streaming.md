# Streaming

## Streaming from any source

`stream()` consumes commands lazily from any iterable: a list, a generator,
lines arriving from a network socket. The application decides where the G-code
comes from:

```python
from pygrbl_streamer import GrblStreamer

def square(size=10, power=300, feed=1000):
    yield 'G90 G21'
    yield f'M4 S{power}'
    yield f'G1 X{size} F{feed}'
    yield f'G1 Y{size}'
    yield 'G1 X0'
    yield 'G1 Y0'
    yield 'M5'

with GrblStreamer("/dev/ttyUSB0") as laser:
    laser.stream(square(), total=7)
```

`send_file(path, **kwargs)` streams a file with the same options, reading it
line by line; it never loads the whole file into memory.

Chain chunks back-to-back without stopping the machine between them:

```python
laser.stream(chunk_1, wait_for_idle=False)
laser.stream(chunk_2, wait_for_idle=False)
laser.stream(final_chunk)   # only the last chunk waits for Idle
```

## Progress reporting

`progress_callback(percent, command)` fires on *acknowledged* commands. The
percentage source, in order of precedence:

1. **Source-provided**: if the iterable exposes a `percent()` method returning
   0 to 100, it is the authority. `send_file()` uses this internally (bytes
   read against file size).
2. **`total`**: pass the command count to `stream()` for an exact 0 to 100%.
3. **Heartbeat**: with neither, the callback fires every 100 acknowledged
   commands with `percent=-1`.

## Flow control and completion

`stream()` strips comments and blank lines, and keeps track of commands
awaiting `ok` or `error` responses. It limits the bytes in flight to
`rx_buffer_size - 1`. Status reports are handled separately from
acknowledgements, and status is not polled while commands are in flight.

`ack_timeout=30` bounds each acknowledgement wait. With the default
`wait_for_idle=True`, the streamer also polls for `Idle` after acknowledgements
have drained; `completion_timeout=600` bounds that final wait. Acknowledgement
means the controller accepted a command, not that motion ended.

`wait_for_idle=False` is useful for consecutive chunks, but returning `True`
then does not confirm physical completion. The final chunk should wait for Idle.

Oversized commands produce an error event. By default they are skipped;
`stop_on_error=True` aborts on an oversized command and on errors received
while waiting for room in the receive buffer or draining the final
acknowledgements. It returns `False` without waiting for Idle or emitting the
`completed` progress event. Commands already buffered by the controller may
still run; this policy does not send a feed hold or reset. Applications should
also consume `error_callback`; with the default `stop_on_error=False`, the
boolean return alone does not prove that every command was accepted.

Invalid streaming state raises `RuntimeError`; stream failures can return
`False`. Python errors from a command source can propagate. Always close the
session in `finally`, and decide explicitly how to handle a failed job.

## Job control

Streaming is blocking. Run it in a worker thread if the application must remain
responsive. While the worker streams, user actions can call:

```python
laser.pause()   # feed hold (!) while streaming
laser.resume()  # cycle start (~) while paused
laser.stop()    # abort: feed hold followed by soft reset
```

Use one job worker per connection. Do not run `command()`, `home()`, `sync()` or
another stream concurrently with that worker; acknowledgements have one owner.
Callbacks run on a separate dispatcher thread and should not take over the
connection. Pause, resume and stop are the intended concurrent controls.

A stop flushes the controller's buffers and leaves the position untrusted:
establish position again before another job. A stopped job cannot be resumed
(see [Limitations](limitations.md#no-job-resumption)).
