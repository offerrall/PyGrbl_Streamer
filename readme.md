# pygrbl_streamer

A simple and minimalist library for controlling CNC machines with GRBL firmware from Python. (~300 lines of code)

## Features

- **Simple**: Just inherit the class and override the callbacks you need
- **Non-blocking**: Callbacks execute in separate threads without affecting laser control
- **Safe**: Intelligent GRBL buffer management and automatic alarm recovery
- **Efficient**: Low CPU and memory consumption
- **Flexible**: Callbacks for progress, alarms, and errors
- **Arc conversion**: Optional G2/G3 to G1 conversion to avoid GRBL error:33

## Installation

```bash
git clone https://github.com/offerrall/pygrbl_streamer.git
cd pygrbl_streamer
pip install .
```

## Basic Usage

### Simple example
```python
from pygrbl_streamer import GrblStreamer

# Direct usage (standard mode)
streamer = GrblStreamer('/dev/ttyUSB0')  # Or 'COM3' on Windows
streamer.open()
streamer.send_file('my_file.gcode') # or 'my_file.nc'
streamer.close()

# With arc conversion enabled
streamer = GrblStreamer('/dev/ttyUSB0', convert_arcs=True, arc_tolerance=0.01)
streamer.open()
streamer.send_file('my_file.gcode')  # G2/G3 commands will be converted to G1
streamer.close()
```

### With custom callbacks
```python
from pygrbl_streamer import GrblStreamer

class MyStreamer(GrblStreamer):
    
    def progress_callback(self, percent: int, command: str):
        print(f"Progress: {percent}% - {command}")
    
    def alarm_callback(self, line: str):
        print(f"ALARM: {line}")
    
    def error_callback(self, line: str):
        print(f"ERROR: {line}")

# Enable arc conversion with custom tolerance
streamer = MyStreamer('/dev/ttyUSB0', convert_arcs=True, arc_tolerance=0.02)
streamer.open()
streamer.send_file('project.gcode')
streamer.close()
```

## Arc Conversion

When `convert_arcs=True`, the library automatically converts circular interpolation commands (G2/G3) to linear movements (G1) to prevent GRBL error:33 on controllers that don't support arcs properly.

**Benefits:**
- Eliminates error:33 on arc-incompatible GRBL versions
- Maintains geometric accuracy within specified tolerance
- Preserves all other G-code commands (M, S, F, etc.)
- Handles both I/J and R arc formats

**Parameters:**
- `convert_arcs`: Enable/disable arc conversion (default: False)
- `arc_tolerance`: Maximum deviation from original arc in mm (default: 0.02)

## API Reference

### Constructor
```python
GrblStreamer(port='/dev/Laser4', baudrate=115200, convert_arcs=False, arc_tolerance=0.02)
```

**Parameters:**
- `port`: Serial port path
- `baudrate`: Communication speed (default: 115200)
- `convert_arcs`: Enable G2/G3 to G1 conversion (default: False)
- `arc_tolerance`: Chord tolerance in mm for arc segmentation (default: 0.02)

### Main methods
- `open()` - Opens serial connection and initializes GRBL
- `send_file(filename)` - Sends a G-code file to the machine
- `close()` - Closes connection and cleans up resources
- `write_line(text)` - Sends an individual command to GRBL
- `read_line_blocking()` - Reads a response from GRBL (5s timeout)

### Callbacks (override as needed)

#### `progress_callback(percent: int, command: str)`
Executed every 10 commands during file sending.
- `percent`: Completion percentage (0-100)
- `command`: Last command sent

#### `alarm_callback(line: str)`
Executed when GRBL reports an alarm.
- `line`: Complete alarm line from GRBL

#### `error_callback(line: str)`
Executed when GRBL reports an error.
- `line`: Complete error line from GRBL

## Technical Features

- **Intelligent buffer management**: Respects GRBL's 127-byte limit with optimistic sending strategy
- **Automatic recovery**: Auto-recovery from alarms with `$X`
- **Non-blocking threads**: Callbacks execute in separate threads
- **Fault tolerant**: Callback errors do not affect machine control
- **Automatic cleanup**: Daemon threads close automatically
- **Arc conversion**: Uses separate `ArcToLinearConverter` module for clean architecture

## Arc Conversion Details

The arc conversion feature uses a dedicated module that:
- Maintains modal state (G90/G91, G90.1/G91.1)
- Tracks current position accurately
- Segments arcs based on chord tolerance
- Preserves feedrates and auxiliary commands
- Handles both absolute and incremental positioning

**Chord tolerance**: Maximum distance between the original arc and the segmented line approximation. Smaller values create smoother curves but more G1 commands.

## Slow callbacks
Callbacks execute in separate threads, but if they are very slow they may accumulate events in the queue. The queue has a limit of 100 events and automatically discards if it fills up.

## Dependencies

- `pyserial` - For serial communication
- `arc_to_linear_converter` - For G2/G3 conversion (included)

## Contributing

Found a bug or want to add a feature? Pull requests welcome!

## License

MIT License - use the library freely in commercial and personal projects.