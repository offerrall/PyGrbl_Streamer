import serial
import time
import threading
import queue
from .test2 import ArcToLinearConverter

class GrblStreamer:

    def __init__(self,
                 port: str = '/dev/Laser4',
                 baudrate: int = 115200,
                 convert_arcs: bool = False,
                 arc_tolerance: float = 0.01):

        self.port = port
        self.baudrate = baudrate
        self.serial: serial.Serial | None = None
        self.read_queue = queue.Queue()
        self.running = False

        # Control de conversión de arcos
        self.convert_arcs = convert_arcs
        if self.convert_arcs:
            self.arc_converter = ArcToLinearConverter(
                chord_tolerance=arc_tolerance,
                max_segment_degrees=10.0,
                decimals=4
            )
        else:
            self.arc_converter = None

        # Serie
        self.DTR_ENABLE = False
        self.RTS_ENABLE = False
        self.WRITE_TIMEOUT = 1.0

        # Callbacks
        self.callback_queue = queue.Queue(100)

    # ---------- Callbacks (sobrescribir si quieres) ----------
    def progress_callback(self, percent: int, command: str): pass
    def alarm_callback(self, line: str): pass
    def error_callback(self, line: str): pass
    def send_callback(self, data: str): pass
    def receive_callback(self, data: str): pass

    # =========================================================
    #                           IO
    # =========================================================
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
            self.read_thread = threading.Thread(target=self._read_loop, daemon=True)
            self.read_thread.start()

            self.callback_thread = threading.Thread(target=self._callback_loop, daemon=True)
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
        # Soft reset
        self.write(b'\x18')
        time.sleep(2)

        if self.serial:
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

        # Desbloquear
        self.write_line("$X")
        time.sleep(0.5)

        # Resetear posición del convertidor si está activo
        if self.arc_converter:
            self.arc_converter.reset_position()

    def _read_loop(self):
        buffer = ""
        while self.running:
            try:
                if self.serial and self.serial.is_open:
                    ch = self.serial.read(1)
                    if not ch:
                        continue
                    buffer += ch.decode('utf-8', errors='ignore')
                    if not buffer.endswith('\n'):
                        continue
                    line = buffer.strip()
                    buffer = ""
                    if line:
                        try:
                            self.callback_queue.put_nowait(('receive', line))
                        except queue.Full:
                            pass
                        self._process_line(line)
            except Exception as e:
                if self.running:
                    print(f"Error in read loop: {e}")

    def _process_line(self, line: str):
        if 'ALARM' in line:
            # Desbloqueo inmediato (opcional)
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
                elif event_type == 'send':
                    self.send_callback(data)
                elif event_type == 'receive':
                    self.receive_callback(data)
            except queue.Empty:
                continue
            except:
                pass

    def write(self, data):
        if self.serial and self.serial.is_open:
            if isinstance(data, str):
                data_str = data
                data = data.encode()
            else:
                data_str = data.decode('utf-8', errors='ignore')
            self.serial.write(data)
            try:
                self.callback_queue.put_nowait(('send', data_str))
            except queue.Full:
                pass

    def write_line(self, text):
        if not text.endswith('\n'):
            text += '\n'
        self.write(text)

    def read_line_blocking(self):
        try:
            return self.read_queue.get(timeout=5)
        except queue.Empty:
            return None

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

    def send_file(self, file_path: str, completion_timeout: int = 300):
        """
        Lee archivo y envía al controlador gestionando el buffer.
        Si convert_arcs=True, convierte G2/G3 a G1 usando el módulo externo.
        """
        with open(file_path, 'r') as f:
            raw_lines = f.readlines()

        # Resetear posición del convertidor si está activo
        if self.arc_converter:
            self.arc_converter.reset_position()

        # Procesar líneas con o sin conversión
        if self.convert_arcs and self.arc_converter:
            # Usar el módulo externo para convertir arcos
            processed_lines = []
            for raw_line in raw_lines:
                converted = self.arc_converter.convert_line(raw_line.strip())
                processed_lines.extend(converted)
            lines = processed_lines
        else:
            # Procesamiento original (sin conversión de arcos)
            lines = raw_lines

        # Limpiar líneas y preparar comandos
        commands = []
        for line in lines:
            line = line.strip() if isinstance(line, str) else line
            if ';' in line:
                line = line[:line.index(';')]
            if '(' in line:
                line = line[:line.index('(')]
            line = line.strip()
            
            if line:
                commands.append(line)

        # ---------- Envío con control de buffer ----------
        grbl_buffer = 0
        BUFFER_SIZE = 127
        sent_commands = []
        total_commands = len(commands)

        for i, cmd in enumerate(commands, 1):
            # Manejo del buffer (optimista)
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

            # Progreso
            if i % 10 == 0 and total_commands > 0:
                percent = int((i / total_commands) * 100)
                if percent < 100:
                    try:
                        self.callback_queue.put_nowait(('progress', (percent, cmd)))
                    except queue.Full:
                        pass

        # ---------- Esperar fin ----------
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