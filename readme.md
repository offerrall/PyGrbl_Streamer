# pygrbl_streamer

A simple and minimalist library for controlling CNC machines with GRBL firmware from Python. (250 lines of code)

## Features

- **Simple**: Just inherit the class and override the callbacks you need
- **Non-blocking**: Callbacks execute in separate threads without affecting laser control
- **Safe**: Intelligent GRBL buffer management and automatic alarm recovery
- **Efficient**: Low CPU and memory consumption
- **Flexible**: Callbacks for progress, alarms, and errors
- **Auto-disconnect detection**: Automatically detects device disconnection and terminates cleanly

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

# Direct usage
streamer = GrblStreamer('/dev/ttyUSB0')  # Or 'COM3' on Windows
streamer.open()
streamer.send_file('my_file.gcode') # or 'my_file.nc'
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
        if "DEVICE_DISCONNECTED" in line:
            print(f"Device disconnected: {line}")
            # Handle disconnection gracefully
            return
        print(f"ERROR: {line}")

streamer = MyStreamer('/dev/ttyUSB0')
streamer.open()
streamer.send_file('project.gcode')
streamer.close()
```

## API Reference

### Constructor
```python
GrblStreamer(port='/dev/Laser4', baudrate=115200)
```

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
Executed when GRBL reports an error or device disconnection.
- `line`: Complete error line from GRBL or "DEVICE_DISCONNECTED: ..." for disconnections

## Technical Features

- **Intelligent buffer management**: Respects GRBL's 127-byte limit
- **Automatic recovery**: Auto-recovery from alarms with `$X`
- **Non-blocking threads**: Callbacks execute in separate threads
- **Fault tolerant**: Callback errors do not affect machine control
- **Automatic cleanup**: Daemon threads close automatically
- **Disconnect detection**: Detects device disconnection after 10 consecutive failed reads

## Device Disconnection Handling

The library automatically detects when a device is physically disconnected or powered off. After 10 consecutive failed read attempts, it will:

1. Send a "DEVICE_DISCONNECTED" error to the `error_callback`
2. Stop the read loop to prevent infinite error logging
3. Allow for graceful cleanup in your application

```python
def error_callback(self, line: str):
    if "DEVICE_DISCONNECTED" in line:
        print("Device was disconnected - cleaning up...")
        self.cleanup_and_exit()  # Your cleanup logic
        return
    # Handle other errors...
```

## Slow callbacks
Callbacks execute in separate threads, but if they are very slow they may accumulate events in the queue. The queue has a limit of 100 events and automatically discards if it fills up.

## Contributing

Found a bug or want to add a feature? Pull requests welcome!

## License

MIT License - use the library freely in commercial and personal projects.