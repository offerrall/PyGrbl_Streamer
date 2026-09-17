# Streaming, progress and job control

[Back to README](../README.md)

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

## Flow control and completion

`stream()` consumes commands lazily, strips comments and blank lines, and keeps
track of commands awaiting `ok` or `error` responses. It limits the bytes in
flight to `rx_buffer_size - 1`. Status reports are handled separately from
acknowledgements.

`ack_timeout=30` bounds acknowledgement waits. With the default
`wait_for_idle=True`, the streamer also polls for `Idle` after acknowledgements
have drained; `completion_timeout=600` bounds that final wait. Acknowledgement
means the controller accepted a command, not necessarily that motion ended.
Status is not polled by the streamer while commands are in flight.

`wait_for_idle=False` is useful for consecutive chunks, but returning `True`
then does not confirm physical completion. The final chunk should wait for
Idle. `send_file(path, **kwargs)` uses the same streaming options and reads the
file lazily; it does not load the whole file into memory.

Oversized commands produce an error event. By default they are skipped;
`stop_on_error=True` aborts on an oversized command and on errors encountered
while waiting for room in the receive buffer. In the current implementation,
GRBL error responses during the final acknowledgement drain are not checked
by that option. Applications should also consume `error_callback`; do not
interpret the boolean return alone as proof that every command was accepted.

Invalid streaming state raises `RuntimeError`; stream failures can return
`False`. Python errors from a command source can propagate. Always close the
session in `finally`, and decide explicitly how to handle a failed job.

## Job control

Streaming is blocking. Run it in a worker thread if the application must remain
responsive. Once the worker is streaming, user actions can call:

```python
g.pause()   # feed hold (!) while streaming
g.resume()  # cycle start (~) while paused
g.stop()    # abort: feed hold followed by soft reset
```

Use one job worker per connection. Do not run `command()`, `home()`, `sync()` or
another stream concurrently with that worker; acknowledgements have one owner.
Callbacks run on a separate dispatcher thread and should not take over the
connection. Pause/resume/stop are the intended concurrent controls.

A stop does not preserve a resumable job. It flushes controller buffers and
leaves position untrusted; establish position again before another job.

## Laser operation

- Laser users: verify `$32=1` (laser mode) so the beam is disabled during feed hold.
- This library streams G-code; it does not validate it. Garbage in, garbage out.
