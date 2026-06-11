import os
import serial
import threading
import queue
import time
import re
from enum import Enum, auto
from collections import deque
from typing import Iterable, Iterator


class State(Enum):
    DISCONNECTED = auto()
    CONNECTING = auto()
    IDLE = auto()
    STREAMING = auto()
    PAUSED = auto()
    ALARM = auto()


class _FileSource:
    """
    Lazily iterates a G-code file while tracking byte-based progress.

    Because stream() pulls commands only when GRBL's 127-byte RX buffer has
    room, the file read position trails the acknowledged position by just a
    few commands, making bytes-read an excellent progress approximation at
    zero cost (no counting pass over the file).
    """

    def __init__(self, path: str):
        self.path = path
        self.size = os.path.getsize(path) or 1
        self.read = 0

    def __iter__(self) -> Iterator[str]:
        self.read = 0
        with open(self.path, 'rb') as f:
            for raw in f:
                self.read += len(raw)
                yield raw.decode('utf-8', errors='ignore')

    def percent(self) -> int:
        # Cap at 99: the 100% event is emitted by stream() on true completion.
        return min(99, int(self.read * 100 / self.size))


class GrblStreamer:
    """Thread-safe, fault-tolerant streamer for GRBL controllers."""

    RX_BUFFER = 128          # GRBL serial RX buffer size, in characters
    RX_MARGIN = 1            # safety margin kept free in the RX buffer
    STATUS_INTERVAL = 0.3    # '?' status polling period while streaming (s)
    READ_TIMEOUT = 0.1       # serial read timeout; keeps the reader thread responsive (s)

    _STATUS_RE = re.compile(r'^<(\w+)')
    _PAREN_COMMENT_RE = re.compile(r'\([^)]*\)')

    def __init__(self, port: str = '/dev/Laser4', baudrate: int = 115200,
                 auto_unlock: bool = True):
        self.port = port
        self.baudrate = baudrate
        # Send $X after connecting. Never applied mid-job: auto-unlocking a
        # laser/CNC in the middle of a program is a safety hazard.
        self.auto_unlock = auto_unlock

        self.serial: serial.Serial | None = None
        self.state = State.DISCONNECTED
        self.last_status: dict = {}      # latest parsed <...> report: {'state','raw','time'}

        self._state_lock = threading.Lock()
        self._write_lock = threading.Lock()
        self._running = threading.Event()
        self._abort = threading.Event()
        self._paused = threading.Event()
        self._banner = threading.Event()

        self._read_thread: threading.Thread | None = None
        self._cb_thread: threading.Thread | None = None

        self._ack_queue: queue.Queue = queue.Queue()       # protocol acks only: 'ok' / 'error:N'
        self._event_queue: queue.Queue = queue.Queue(500)  # events dispatched to user callbacks

    # ------------------------------------------------------------------
    # Callbacks: override in a subclass or assign as instance attributes.
    # All callbacks run on a dedicated thread, so a slow or faulty callback
    # can never stall or crash the serial communication.
    # ------------------------------------------------------------------
    def progress_callback(self, percent: int, command: str):
        """percent is 0-100 when measurable, -1 for unbounded streams."""
    def state_callback(self, state: State): pass
    def alarm_callback(self, line: str): pass
    def error_callback(self, line: str): pass
    def send_callback(self, data: str): pass
    def receive_callback(self, data: str): pass
    def disconnect_callback(self, reason: str): pass
    def log_callback(self, level: str, message: str):
        """Internal diagnostics the other callbacks don't cover (init quirks,
        swallowed exceptions...). level is 'debug'|'info'|'warning'.
        Typical wiring: g.log_callback = lambda lv, m: getattr(log, lv)(m)"""

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------
    def connect(self, reset: bool = True):
        """Open the serial port, start worker threads, and initialize GRBL."""
        self.disconnect()  # guarantee a clean slate even if a session was open
        self._set_state(State.CONNECTING)
        try:
            s = serial.Serial()
            s.port = self.port
            s.baudrate = self.baudrate
            s.bytesize = serial.EIGHTBITS
            s.parity = serial.PARITY_NONE
            s.stopbits = serial.STOPBITS_ONE
            s.timeout = self.READ_TIMEOUT     # bounded reads -> reader thread can exit
            s.write_timeout = 1.0
            s.dtr = False                     # suppress Arduino auto-reset on open
            s.rts = False
            s.open()
            s.reset_input_buffer()
            s.reset_output_buffer()
            self.serial = s
        except (serial.SerialException, OSError):
            self.serial = None
            self._set_state(State.DISCONNECTED)
            raise

        self._abort.clear()
        self._paused.clear()
        self._running.set()
        self._read_thread = threading.Thread(target=self._read_loop, daemon=True,
                                             name='grbl-read')
        self._read_thread.start()
        self._cb_thread = threading.Thread(target=self._callback_loop, daemon=True,
                                           name='grbl-callbacks')
        self._cb_thread.start()

        if reset:
            # Soft-reset and wait for the "Grbl X.Xx ['$' for help]" banner
            # instead of sleeping blindly for a fixed interval.
            self._banner.clear()
            self._write(b'\x18')
            if not self._banner.wait(timeout=6):
                # Some GRBL clones do not emit a banner; proceed anyway.
                self._emit('log', ('warning', 'No GRBL banner after soft reset'))
            time.sleep(0.2)
            self._drain(self._ack_queue)

        if self.auto_unlock:
            self.unlock()

        self._set_state(State.IDLE)

    def disconnect(self):
        """Stop worker threads (joined, not abandoned) and close the port."""
        self._abort.set()
        self._running.clear()

        if self._cb_thread and self._cb_thread.is_alive():
            self._event_queue.put(None)       # sentinel terminates the callback thread

        current = threading.current_thread()
        for t in (self._read_thread, self._cb_thread):
            if t and t.is_alive() and t is not current:
                t.join(timeout=2)
        self._read_thread = None
        self._cb_thread = None

        if self.serial:
            try:
                self.serial.reset_output_buffer()
                self.serial.reset_input_buffer()
                self.serial.close()
            except Exception:
                pass
        self.serial = None

        self._drain(self._ack_queue)
        self._drain(self._event_queue)
        with self._state_lock:
            self.state = State.DISCONNECTED

    def reconnect(self, retries: int = 5, delay: float = 2.0) -> bool:
        """Attempt to reconnect. Intended for use after a physical disconnect."""
        for _ in range(retries):
            try:
                self.connect()
                return True
            except (serial.SerialException, OSError):
                time.sleep(delay)
        return False

    @property
    def is_connected(self) -> bool:
        return self.state not in (State.DISCONNECTED, State.CONNECTING)

    # Context-manager support:  with GrblStreamer(...) as g: ...
    def __enter__(self):
        if not self.is_connected:
            self.connect()
        return self

    def __exit__(self, *exc):
        self.disconnect()

    # ------------------------------------------------------------------
    # Reader thread
    # ------------------------------------------------------------------
    def _read_loop(self):
        buf = bytearray()
        while self._running.is_set():
            try:
                # Read whatever is available (at least 1 byte). Avoids the
                # up-to-100 ms latency of waiting for a fixed-size block.
                chunk = self.serial.read(self.serial.in_waiting or 1)
            except (serial.SerialException, OSError, AttributeError) as e:
                # Port vanished (USB unplugged, power loss, etc.)
                self._handle_disconnect(f'DEVICE_DISCONNECTED: {e}')
                return
            if not chunk:
                continue
            buf += chunk
            while b'\n' in buf:
                raw, _, rest = buf.partition(b'\n')
                buf = bytearray(rest)
                line = raw.decode('utf-8', errors='ignore').strip()
                if line:
                    self._process_line(line)

    def _process_line(self, line: str):
        """Classify an incoming line and route it to the proper channel."""
        self._emit('receive', line)

        if line == 'ok' or line.startswith('error:') or line.startswith('error '):
            if line != 'ok':
                self._emit('error', line)
            self._ack_queue.put(line)         # ONLY protocol acks enter this queue

        elif line.startswith('<') and line.endswith('>'):
            # Real-time status report, e.g. <Idle|MPos:0.000,...>
            m = self._STATUS_RE.match(line)
            if m:
                self.last_status = {'state': m.group(1), 'raw': line,
                                    'time': time.time()}

        elif line.startswith('ALARM'):
            # An alarm mid-job aborts the job. We deliberately do NOT
            # auto-unlock: clearing an alarm on a laser/CNC without operator
            # confirmation is unsafe. The user must call unlock() explicitly.
            self._abort.set()
            self._set_state(State.ALARM)
            self._emit('alarm', line)

        elif line.startswith('Grbl'):
            self._banner.set()
        # [MSG:...], $N settings, etc. are still delivered via receive_callback.

    def _handle_disconnect(self, reason: str):
        self._abort.set()
        self._running.clear()
        try:
            if self.serial:
                self.serial.close()
        except Exception:
            pass
        self.serial = None
        self._set_state(State.DISCONNECTED)
        self._emit('disconnect', reason)

    # ------------------------------------------------------------------
    # Callback dispatcher thread
    # ------------------------------------------------------------------
    def _callback_loop(self):
        while True:
            item = self._event_queue.get()
            if item is None:                  # shutdown sentinel
                return
            etype, data = item
            try:
                if etype == 'progress':
                    self.progress_callback(*data)
                elif etype == 'state':
                    self.state_callback(data)
                elif etype == 'alarm':
                    self.alarm_callback(data)
                elif etype == 'error':
                    self.error_callback(data)
                elif etype == 'send':
                    self.send_callback(data)
                elif etype == 'receive':
                    self.receive_callback(data)
                elif etype == 'disconnect':
                    self.disconnect_callback(data)
                elif etype == 'log':
                    self.log_callback(*data)
            except Exception as e:
                # A user callback raised; report it (guarded against loops:
                # a faulty log_callback is never reported through itself).
                if etype != 'log':
                    self._emit('log', ('warning', f'{etype}_callback raised: {e!r}'))

    # ------------------------------------------------------------------
    # Writing (always lock-protected: streaming, real-time commands and
    # user calls cannot interleave bytes on the wire)
    # ------------------------------------------------------------------
    def _write(self, data: bytes):
        with self._write_lock:
            if not (self.serial and self.serial.is_open):
                raise serial.SerialException('Port is not open')
            self.serial.write(data)
        self._emit('send', data.decode('utf-8', errors='ignore'))

    def write_line(self, text: str):
        self._write((text.rstrip('\r\n') + '\n').encode())

    def realtime(self, char: bytes):
        """Send a GRBL real-time command (?, !, ~, 0x18).
        These bypass the RX buffer and produce no 'ok' response."""
        self._write(char)

    def command(self, cmd: str, timeout: float = 5.0) -> bool:
        """Send a single command and wait for its ok/error response.
        For interactive use outside of a streaming job."""
        if self.state == State.STREAMING:
            raise RuntimeError('A streaming job is in progress')
        self._drain(self._ack_queue)
        self.write_line(cmd)
        try:
            return self._ack_queue.get(timeout=timeout) == 'ok'
        except queue.Empty:
            return False

    def unlock(self) -> bool:
        """$X: clear the alarm lock."""
        self._drain(self._ack_queue)
        self.write_line('$X')
        try:
            ok = self._ack_queue.get(timeout=3) == 'ok'
        except queue.Empty:
            ok = False
        if ok and self.state == State.ALARM:
            self._set_state(State.IDLE)
        return ok

    def home(self, timeout: float = 60.0) -> bool:
        """$H: run the homing cycle (may take a while)."""
        return self.command('$H', timeout=timeout)

    # ------------------------------------------------------------------
    # Job control
    # ------------------------------------------------------------------
    def pause(self):
        if self.state == State.STREAMING:
            self.realtime(b'!')               # immediate feed hold
            self._paused.set()
            self._set_state(State.PAUSED)

    def resume(self):
        if self.state == State.PAUSED:
            self.realtime(b'~')               # cycle start / resume
            self._paused.clear()
            self._set_state(State.STREAMING)

    def stop(self):
        """Abort the job: feed hold followed by soft reset (flushes GRBL's buffer)."""
        self._abort.set()
        self._paused.clear()
        try:
            self.realtime(b'!')
            time.sleep(0.3)
            self.realtime(b'\x18')
        except (serial.SerialException, OSError):
            return
        time.sleep(0.5)
        self._drain(self._ack_queue)
        # A soft reset during motion leaves GRBL in an alarm state by design.
        if self.state is not State.DISCONNECTED:
            self._set_state(State.ALARM)

    # ------------------------------------------------------------------
    # Streaming core (character-counting protocol)
    # ------------------------------------------------------------------
    def stream(self, commands: Iterable[str], total: int | None = None,
               completion_timeout: float = 600, ack_timeout: float = 30,
               stop_on_error: bool = False, wait_for_idle: bool = True) -> bool:
        """
        Stream any iterable of G-code commands: a list, a generator, lines
        arriving from a network socket... The source is consumed lazily, so
        arbitrarily large jobs run in constant memory.

        Progress reporting, in order of precedence:
            1. If the source exposes a percent() method (e.g. the internal
               file source used by send_file), it is the progress authority.
            2. Otherwise, if total is given, progress is acked/total.
            3. Otherwise, a heartbeat fires every 100 acked commands with
               percent=-1.

        Args:
            commands: iterable of command strings. Comments and blank lines
                are stripped automatically.
            total: number of commands, if known.
            completion_timeout: max seconds to wait for the machine to reach
                Idle after the last command is acknowledged.
            ack_timeout: max seconds to wait for a single ok/error.
            stop_on_error: abort the job on the first GRBL error response.
            wait_for_idle: if False, return as soon as all commands are
                acknowledged, without waiting for motion to finish. Useful
                for chaining chunks back-to-back.

        Returns True on successful completion. Blocking: run it in its own
        thread if the UI must stay responsive.
        """
        if self.state != State.IDLE:
            raise RuntimeError(f'Cannot stream while in state {self.state.name}')
        if total == 0:
            self._emit('progress', (100, 'empty_job'))
            return True

        self._abort.clear()
        self._paused.clear()
        self._drain(self._ack_queue)          # critical: stale 'ok's would corrupt counting
        self._set_state(State.STREAMING)

        # Source-provided progress (duck-typed), e.g. _FileSource.percent
        percent_fn = getattr(commands, 'percent', None)

        pending = deque()                     # byte counts of commands currently in GRBL's buffer
        acked = 0
        last_poll = 0.0
        last_mark = -1 if (percent_fn or total) else 0
        max_len = self.RX_BUFFER - self.RX_MARGIN
        ok = True

        try:
            for cmd in self._clean(commands):
                # Cooperative pause point
                while self._paused.is_set() and not self._abort.is_set():
                    time.sleep(0.05)
                if self._abort.is_set():
                    ok = False
                    break

                need = len(cmd) + 1           # +1 for the trailing '\n'
                if need > max_len:
                    # A single command larger than GRBL's RX buffer can never
                    # fit; skipping it (with an error event) beats deadlocking.
                    self._emit('error', f'COMMAND_TOO_LONG ({need} bytes): {cmd[:40]}...')
                    if stop_on_error:
                        ok = False
                        break
                    continue

                # Wait for room in GRBL's RX buffer
                while sum(pending) + need > max_len:
                    resp = self._wait_ack(ack_timeout)
                    if resp is None:
                        raise TimeoutError('GRBL is not responding (ack timeout)')
                    if pending:
                        pending.popleft()
                    acked += 1
                    if resp != 'ok' and stop_on_error:
                        self._abort.set()
                    last_mark = self._report(acked, total, percent_fn, cmd, last_mark)
                    if self._abort.is_set():
                        break
                if self._abort.is_set():
                    ok = False
                    break

                self.write_line(cmd)
                pending.append(need)

                # Real-time '?' status polling (consumes no RX buffer space)
                now = time.time()
                if now - last_poll > self.STATUS_INTERVAL:
                    self.realtime(b'?')
                    last_poll = now

            # Drain the remaining acknowledgements
            while pending and not self._abort.is_set():
                resp = self._wait_ack(ack_timeout)
                if resp is None:
                    raise TimeoutError('GRBL stopped responding while finishing')
                pending.popleft()
                acked += 1
                last_mark = self._report(acked, total, percent_fn, '', last_mark)

            # All commands acked; optionally wait for motion to finish
            if ok and wait_for_idle and not self._abort.is_set():
                ok = self._wait_idle(completion_timeout)

        except (serial.SerialException, OSError) as e:
            self._handle_disconnect(f'DEVICE_DISCONNECTED: {e}')
            return False
        except TimeoutError as e:
            self._emit('error', str(e))
            ok = False
        finally:
            if self.state in (State.STREAMING, State.PAUSED):
                self._set_state(State.IDLE)

        if ok:
            self._emit('progress', (100, 'completed'))
        return ok

    def send_file(self, file_path: str, **kwargs) -> bool:
        """
        Stream a G-code file of any size. Single lazy pass, constant memory.

        Progress is derived from bytes consumed vs file size (instant via
        os.path.getsize): there is NO counting pass over the file, so even
        multi-GB jobs start immediately. The approximation trails the truth
        by only the handful of commands that fit in GRBL's 127-byte buffer.

        Accepts the same keyword arguments as stream() (total is implicit).
        """
        return self.stream(_FileSource(file_path), **kwargs)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    @classmethod
    def _clean(cls, commands: Iterable[str]) -> Iterator[str]:
        """Lazily strip comments and blank lines from a command source."""
        for line in commands:
            line = cls._PAREN_COMMENT_RE.sub('', line)  # parenthesized comments
            line = line.split(';', 1)[0].strip()        # semicolon comments
            if line:
                yield line

    def _wait_ack(self, timeout: float) -> str | None:
        """Wait for one 'ok'/'error:N' with a hard timeout.
        Abortable and sensitive to disconnection; never hangs."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort.is_set() or self.state == State.DISCONNECTED:
                return None
            try:
                return self._ack_queue.get(timeout=0.2)
            except queue.Empty:
                continue
        return None

    def _wait_idle(self, timeout: float) -> bool:
        """Poll status until GRBL reports Idle (job physically complete)."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._abort.is_set() or self.state == State.DISCONNECTED:
                return False
            try:
                self.realtime(b'?')
            except (serial.SerialException, OSError):
                return False
            time.sleep(0.4)
            st = self.last_status.get('state', '')
            fresh = time.time() - self.last_status.get('time', 0) < 2.0
            if fresh and st == 'Idle':
                return True
            if fresh and st.startswith('Alarm'):
                return False
        return False

    def _report(self, acked: int, total: int | None, percent_fn,
                cmd: str, last_mark: int) -> int:
        """Emit progress. Authority order: source percent() > acked/total >
        heartbeat (percent=-1) every 100 acknowledged commands."""
        if percent_fn:
            pct = percent_fn()
            if pct != last_mark:
                self._emit('progress', (pct, cmd))
            return pct
        if total:
            pct = int(acked * 100 / total)
            if pct != last_mark and pct < 100:
                self._emit('progress', (pct, cmd))
            return pct
        if acked - last_mark >= 100:
            self._emit('progress', (-1, cmd))
            return acked
        return last_mark

    @staticmethod
    def _drain(q: queue.Queue):
        """Discard all items currently in a queue."""
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass

    def _set_state(self, st: State):
        with self._state_lock:
            if self.state == st:
                return
            self.state = st
        self._emit('state', st)

    def _emit(self, etype: str, data):
        """Queue an event for the callback thread; drop it if the queue is full."""
        try:
            self._event_queue.put_nowait((etype, data))
        except queue.Full:
            pass