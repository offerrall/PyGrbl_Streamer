import serial
import time
import threading
import queue

class GrblStreamer:

    def __init__(self,
                 port: str = '/dev/Laser4',
                 baudrate: int = 115200):

        self.port = port
        self.baudrate = baudrate
        self.serial: serial.Serial | None = None
        self.read_queue = queue.Queue()
        self.running = False

        self.DTR_ENABLE = False
        self.RTS_ENABLE = False
        self.WRITE_TIMEOUT = 1.0
        
        self.callback_queue = queue.Queue(100)

    def progress_callback(self, percent: int, command: str):
        """Callback for progress updates during file sending, overridden by user."""
        pass
    
    def alarm_callback(self, line: str):
        """Callback for GRBL alarms, overridden by user."""
        pass
        
    def error_callback(self, line: str):
        """Callback for GRBL errors, overridden by user."""
        pass

    def open(self):

        try:
            self.close()
        except:
            pass

        try:
            self.serial = serial.Serial()
            self.serial.port = self.port
            self.serial.baudrate = self.baudrate
            self.serial.bytesize = serial.EIGHTBITS
            self.serial.parity = serial.PARITY_NONE
            self.serial.stopbits = serial.STOPBITS_ONE
            self.serial.timeout = None
            self.serial.write_timeout = self.WRITE_TIMEOUT
            self.serial.xonxoff = False
            self.serial.rtscts = False
            self.serial.dsrdtr = False

            self.serial.dtr = self.DTR_ENABLE
            self.serial.rts = self.RTS_ENABLE

            self.serial.open()

            self.serial.reset_output_buffer()
            self.serial.reset_input_buffer()

            self.running = True
            self.read_thread = threading.Thread(target=self._read_loop)
            self.read_thread.daemon = True
            self.read_thread.start()
            
            self.callback_thread = threading.Thread(target=self._callback_loop)
            self.callback_thread.daemon = True
            self.callback_thread.start()

            self._initialize_grbl()

        except serial.SerialException as e:
            if len(self.port) > 4 and self.port[-2:].isdigit():
                try:
                    self.serial.port = self.port[:-1]
                    self.serial.open()
                    self.serial.reset_output_buffer()
                    self.serial.reset_input_buffer()
                except:
                    raise e
            else:
                raise e

    def _initialize_grbl(self):
        if True:
            self.write(b'\x18')  # Ctrl-X
            time.sleep(2)

        if self.serial:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

        self.write_line("$X")
        time.sleep(0.5)

    def _read_loop(self):
        buffer = ""

        while self.running:
            try:
                if self.serial and self.serial.is_open:
                    char = self.serial.read(1)
                    if not char:
                        continue
                    buffer += char.decode('utf-8', errors='ignore')
                    if not buffer.endswith('\n'):
                        continue
                    line = buffer.strip()
                    buffer = ""
                    if line:
                        self._process_line(line)

            except Exception as e:
                if self.running:
                    print(f"Error in read loop: {e}")
                    
    def _process_line(self, line):
        if 'ALARM' in line:
            self.write_line("$X")
            try:
                self.callback_queue.put_nowait(('alarm', line))
            except queue.Full:
                pass

        elif 'error' in line.lower():
            try:
                self.callback_queue.put_nowait(('error', line))
            except queue.Full:
                pass

        self.read_queue.put(line)
    
    def _callback_loop(self):
        while self.running:
            try:
                event_type, data = self.callback_queue.get(timeout=1)
                
                if event_type == 'progress':
                    percent, command = data
                    self.progress_callback(percent, command)
                elif event_type == 'alarm':
                    self.alarm_callback(data)
                elif event_type == 'error':
                    self.error_callback(data)
                    
            except queue.Empty:
                continue
            except:
                pass

    def write(self, data):
        if self.serial and self.serial.is_open:
            if isinstance(data, str):
                data = data.encode()
            self.serial.write(data)

    def write_line(self, text):
        if not text.endswith('\n'):
            text += '\n'
        self.write(text)

    def read_line_blocking(self):
        try:
            return self.read_queue.get(timeout=5)
        except queue.Empty:
            return None

    def send_file(self, file_path: str, completion_timeout: int = 300):

        with open(file_path, 'r') as f:
            lines = f.readlines()

        commands = []
        for line in lines:
            line = line.strip()
            if ';' in line:
                line = line[:line.index(';')]
            if '(' in line:
                line = line[:line.index('(')]
            line = line.strip()
            
            if line:
                commands.append(line)        

        grbl_buffer = 0
        BUFFER_SIZE = 127
        sent_commands = []

        for i, cmd in enumerate(commands, 1):

            while grbl_buffer + len(cmd) + 1 > BUFFER_SIZE - 5:
                response = self.read_line_blocking()
                if response == 'ok' and sent_commands:
                    sent_cmd = sent_commands.pop(0)
                    grbl_buffer -= (len(sent_cmd) + 1)
                elif response and 'error' in response.lower():
                    if sent_commands:
                        sent_cmd = sent_commands.pop(0)
                        grbl_buffer -= (len(sent_cmd) + 1)
    
            self.write_line(cmd)
            sent_commands.append(cmd)
            grbl_buffer += len(cmd) + 1

            if i % 10 == 0:
                percent = int((i / len(commands)) * 100)
                if percent == 100:
                    continue
                try:
                    self.callback_queue.put_nowait(('progress', (percent, cmd)))
                except queue.Full:
                    pass

        start_time = time.time()
        while True:
            if time.time() - start_time > completion_timeout:
                break
                
            self.write_line("?")
            time.sleep(2)
            response = self.read_line_blocking()
            if response and 'Idle' in response:
                break
                
        self.progress_callback(100, 'completed')

    def close(self):
        self.running = False

        if self.serial and self.serial.is_open:
            try:
                self.serial.reset_output_buffer()
                self.serial.reset_input_buffer()
                self.serial.close()
            except:
                pass

        self.serial = None