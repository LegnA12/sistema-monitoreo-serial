import threading
import time
import serial

from PySide6.QtCore import QObject, Signal


class SerialReader(QObject):
    """
    Lector/escritor serial en hilo separado.

    Responsabilidad única: abrir el puerto, leer bytes, emitir líneas crudas
    y permitir el envío de datos. El parseo es responsabilidad de la UI.
    """

    data_received = Signal(str)
    status_update = Signal(str)
    error_signal  = Signal(str)

    def __init__(self):
        super().__init__()
        self.serial_port  = None
        self._stop_event  = threading.Event()
        self.read_thread  = None
        self.baudrate     = 9600
        self.lock         = threading.Lock()

    # ------------------------------------------------------------------
    # Conexión
    # ------------------------------------------------------------------

    def connect_serial(self, port_name: str, baudrate: int = 9600) -> bool:
        """Abrir puerto y arrancar hilo de lectura. Retorna True si ok."""
        try:
            with self.lock:
                if self.serial_port and self.serial_port.is_open:
                    self.disconnect()

                self.serial_port = serial.Serial(
                    port=port_name,
                    baudrate=baudrate,
                    bytesize=serial.EIGHTBITS,
                    parity=serial.PARITY_NONE,
                    stopbits=serial.STOPBITS_ONE,
                    timeout=1,
                )
                self.baudrate = baudrate
                self._stop_event.clear()

                self.read_thread = threading.Thread(
                    target=self._read_serial_data, daemon=True
                )
                self.read_thread.start()
                self.status_update.emit(f"Conectado a {port_name} @ {baudrate} baudios")
                return True

        except serial.SerialException as e:
            self.error_signal.emit(f"Error de conexión: {e}")
            return False
        except Exception as e:
            self.error_signal.emit(f"Error inesperado al conectar: {e}")
            return False

    def disconnect(self):
        """Señalar al hilo que se detenga, esperar y cerrar el puerto."""
        self._stop_event.set()
        if self.read_thread and self.read_thread.is_alive():
            self.read_thread.join(timeout=2.0)
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except Exception:
                pass
        self.status_update.emit("Desconectado del puerto serial")

    def is_connected(self) -> bool:
        return (
            not self._stop_event.is_set()
            and self.serial_port is not None
            and self.serial_port.is_open
        )

    # ------------------------------------------------------------------
    # Escritura hacia el dispositivo (bidireccional)
    # ------------------------------------------------------------------

    def write_data(self, data: str) -> bool:
        """
        Enviar texto al dispositivo conectado.
        Retorna True si se envió correctamente.
        El terminador de línea debe venir incluido en 'data'.
        """
        if not self.is_connected():
            self.error_signal.emit("No hay conexión activa para enviar datos.")
            return False
        try:
            with self.lock:
                self.serial_port.write(data.encode("utf-8"))
            return True
        except serial.SerialException as e:
            self.error_signal.emit(f"Error al enviar datos: {e}")
            return False
        except Exception as e:
            self.error_signal.emit(f"Error inesperado al enviar: {e}")
            return False

    # ------------------------------------------------------------------
    # Hilo de lectura
    # ------------------------------------------------------------------

    def _read_serial_data(self):
        """Loop de lectura ejecutado en hilo daemon."""
        buffer = ""
        while not self._stop_event.is_set():
            try:
                if self.serial_port and self.serial_port.is_open:
                    if self.serial_port.in_waiting > 0:
                        raw = self.serial_port.read(self.serial_port.in_waiting)
                        buffer += raw.decode("utf-8", errors="ignore")
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            if line:
                                self.data_received.emit(line)
                    else:
                        time.sleep(0.001)
                else:
                    time.sleep(0.1)

            except serial.SerialException as e:
                self.error_signal.emit(f"Error de lectura: {e}")
                self._stop_event.set()
                break
            except Exception as e:
                self.error_signal.emit(f"Error inesperado en hilo: {e}")
                self._stop_event.set()
                break
