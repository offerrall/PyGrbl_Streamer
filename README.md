# pygrbl_streamer

[![PyPI](https://img.shields.io/pypi/v/pygrbl_streamer.svg)](https://pypi.org/project/pygrbl_streamer/)

Stream G-code to GRBL controllers over serial, with progress callbacks,
pause/resume/stop and configurable connections. Files and generators are
consumed lazily, keeping memory use low.

Used daily for a year in a professional workshop, operating multiple machines
in production.

Requires Python 3.10+. Part of the **pygrbl** family alongside
[`pygrbl_build`](https://github.com/offerrall/pygrbl_build).

## Install

```bash
pip install pygrbl-streamer
```

## Use

```python
from pygrbl_streamer import GrblStreamer

with GrblStreamer("/dev/ttyUSB0") as laser:  # "COM3" on Windows
    laser.progress_callback = lambda percent, command: print(f"{percent}%")
    if not laser.send_file("job.gcode"):
        raise RuntimeError("Job did not complete")
```

This executes the file on the machine. Default connection: 115200 baud,
soft reset and automatic unlock. Existing 0.2.0 calls remain supported;
new connection options are optional.

## Documentation

- [Connections](docs/connections.md): serial settings, retries and controller compatibility.
- [Streaming](docs/streaming.md): sending files and generators, progress, pause, resume and stop.
- [API](docs/api.md): the class, its callbacks and its state.
- [Changelog](CHANGELOG.md)
- [Versioning and publishing](RELEASING.md)

MIT — see [LICENSE](LICENSE).
