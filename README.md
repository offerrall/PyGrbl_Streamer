# pygrbl-streamer

Stream G-code to GRBL controllers over serial, with progress callbacks,
pause/resume/stop and configurable connections. Files and generators are
consumed lazily, so a job of any size streams in constant memory.

Used daily in a professional workshop, driving several machines in production.

```python
from pygrbl_streamer import GrblStreamer

with GrblStreamer("/dev/ttyUSB0") as laser:  # "COM3" on Windows
    laser.progress_callback = lambda percent, command: print(f"{percent}%")
    if not laser.send_file("job.gcode"):
        raise RuntimeError("Job did not complete")
```

The full documentation is at https://offerrall.github.io/pygrbl-streamer/.

## Documentation

- [Overview](https://offerrall.github.io/pygrbl-streamer/): supported controllers, tested machines, safety and the compatibility policy.
- [Connections](https://offerrall.github.io/pygrbl-streamer/connections/): serial settings, handshakes, homing, retries and receive-buffer size.
- [Streaming](https://offerrall.github.io/pygrbl-streamer/streaming/): files and generators, progress, flow control, pause, resume and stop.
- [API](https://offerrall.github.io/pygrbl-streamer/api/): methods, callbacks, logging, state and troubleshooting.
- [Limitations](https://offerrall.github.io/pygrbl-streamer/limitations/): unsupported controllers, machine caveats and recovery boundaries.

### Maintaining

- [Releasing](https://offerrall.github.io/pygrbl-streamer/releasing/): CI, PyPI trusted publishing and the release steps.
