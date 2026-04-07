import time
import csv
import json
import re
from collections import deque
from datetime import datetime

import serial
import serial.tools.list_ports

import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.backends.backend_qt5agg import NavigationToolbar2QT as NavigationToolbar

from PySide6.QtCore import Qt, QTimer, Slot, QSettings
from PySide6.QtGui import QAction, QFont, QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from serial_reader import SerialReader


# Paleta de colores para canales (hasta 8 simultáneos)
_CHANNEL_COLORS = [
    "#2980b9", "#e74c3c", "#27ae60", "#f39c12",
    "#8e44ad", "#16a085", "#d35400", "#2c3e50",
]

# Terminadores de línea para envío
_LINE_ENDINGS = {
    "\\n  (LF)":    "\n",
    "\\r\\n (CRLF)": "\r\n",
    "\\r  (CR)":    "\r",
    "Sin terminador": "",
}


class RealTimePlot(QMainWindow):
    """
    Ventana principal del sistema de monitoreo serial.

    Funcionalidades v5.1:
    - Multi-canal: grafica todos los campos detectados simultáneamente.
    - Historial de sesión: acumula todos los datos desde la conexión.
    - Buffer durante pausa: los datos no se pierden al pausar.
    - Auto-reconexión: reintenta la conexión si el dispositivo se desconecta.
    - Envío bidireccional: envía comandos/texto al dispositivo conectado.
    - Compatible con cualquier dispositivo USB/COM (ESP32, Arduino, sensores, PLCs…).
    """

    # ------------------------------------------------------------------
    # Inicialización
    # ------------------------------------------------------------------

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Sistema de Monitoreo Serial v5.1")
        self.resize(1300, 750)

        self.settings = QSettings("AngelMaldonado", "SistemaMonitoreoSerial")
        self.serial_reader = SerialReader()

        # --- Buffers de visualización (ventana deslizante) ---
        self.max_data_points = 100
        self.time_buffer: deque = deque(maxlen=self.max_data_points)
        # Un deque por canal: {campo: deque(maxlen=N)}
        self.channel_buffers: dict = {}
        self.start_time: float | None = None

        # --- Historial completo de sesión ---
        self._session_times: list = []
        self._session_data:  dict = {}   # {campo: [valores…]}

        # --- Cola de datos recibidos durante pausa ---
        self._pause_queue: list = []     # [(timestamp, {campo: valor})]

        # --- Estado del gráfico ---
        self.auto_scale   = True
        self.y_min        = -10.0
        self.y_max        = 10.0
        self.is_paused    = False
        self.animation    = None

        # Líneas matplotlib por canal: {campo: Line2D}
        self.channel_lines: dict = {}
        # Canales actualmente visibles (controlado por checkboxes)
        self.active_channels: set = set()

        # --- Formato de tramas ---
        self.current_format   = "Simple"
        self.available_fields: list = []

        # --- Auto-reconexión ---
        self._last_port:             str   = ""
        self._last_baudrate:         int   = 9600
        self._reconnect_attempts:    int   = 0
        self._max_reconnect_attempts: int  = 10
        self._reconnect_timer: QTimer | None = None

        # --- Anti-spam de errores ---
        self._last_error_time: float = 0.0
        self._last_error_msg:  str   = ""

        # --- Atributos de UI ---
        self.com_port_combo:       QComboBox    | None = None
        self.refresh_btn:          QPushButton  | None = None
        self.scan_btn:             QPushButton  | None = None
        self.baudrate_combo:       QComboBox    | None = None
        self.connect_btn:          QPushButton  | None = None
        self.disconnect_btn:       QPushButton  | None = None
        self.write_edit:           QLineEdit    | None = None
        self.line_ending_combo:    QComboBox    | None = None
        self.send_btn:             QPushButton  | None = None
        self.auto_scale_check:     QCheckBox    | None = None
        self.y_min_spin:           QDoubleSpinBox | None = None
        self.y_max_spin:           QDoubleSpinBox | None = None
        self.data_points_spin:     QSpinBox     | None = None
        self.pause_btn:            QPushButton  | None = None
        self.format_type_combo:    QComboBox    | None = None
        self.format_template_edit: QLineEdit    | None = None
        self.channel_list:         QListWidget  | None = None
        self.apply_format_btn:     QPushButton  | None = None
        self.status_text:          QTextEdit    | None = None
        self.graph_title:          QLabel       | None = None
        self.stats_label:          QLabel       | None = None
        self.figure   = None
        self.ax       = None
        self.canvas:  FigureCanvas | None = None
        self.toolbar  = None
        self.refresh_timer: QTimer | None = None

        # Construir
        self.setup_ui()
        self.setup_menu()
        self.setup_plot()

        # Señales del lector
        self.serial_reader.data_received.connect(self.handle_raw_data)
        self.serial_reader.status_update.connect(self.update_status)
        self.serial_reader.error_signal.connect(self.on_serial_error)

        # Timer de refresco de puertos
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_com_ports)
        self.refresh_timer.start(2000)

        # Timer de auto-reconexión (arranca solo ante error)
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.timeout.connect(self._try_reconnect)

        self.refresh_com_ports()
        self.load_settings()
        self.start_animation()

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------

    def setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter)

        # Panel izquierdo — controles
        ctrl_panel  = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_panel)
        ctrl_layout.setContentsMargins(8, 8, 8, 8)
        ctrl_layout.setSpacing(8)

        title = QLabel("SISTEMA DE MONITOREO SERIAL — Angel Maldonado Fuentes")
        title.setAlignment(Qt.AlignCenter)
        title.setFont(QFont("Arial", 11, QFont.Bold))
        title.setStyleSheet(
            "color:#2c3e50; padding:8px; background:#ecf0f1; border-radius:5px;"
        )
        ctrl_layout.addWidget(title)
        ctrl_layout.addWidget(self._create_serial_group())
        ctrl_layout.addWidget(self._create_write_group())
        ctrl_layout.addWidget(self._create_graph_config_group())
        ctrl_layout.addWidget(self._create_format_group())
        ctrl_layout.addWidget(self._create_log_group())
        ctrl_layout.addStretch()

        # Panel derecho — gráfico
        graph_panel = self._create_graph_panel()

        splitter.addWidget(ctrl_panel)
        splitter.addWidget(graph_panel)
        splitter.setSizes([400, 900])
        self.statusBar().showMessage("Listo — sin conexión")

    def _create_serial_group(self) -> QGroupBox:
        group  = QGroupBox("Configuración Serial")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QGridLayout(group)
        layout.setSpacing(7)

        layout.addWidget(QLabel("Puerto COM:"), 0, 0)
        self.com_port_combo = QComboBox()
        self.com_port_combo.setMinimumWidth(160)
        layout.addWidget(self.com_port_combo, 0, 1)

        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setToolTip("Actualizar lista de puertos")
        self.refresh_btn.setMaximumWidth(36)
        self.refresh_btn.clicked.connect(self.refresh_com_ports)
        layout.addWidget(self.refresh_btn, 0, 2)

        layout.addWidget(QLabel("Baudrate:"), 1, 0)
        self.baudrate_combo = QComboBox()
        self.baudrate_combo.addItems(
            ["1200", "2400", "4800", "9600", "19200", "38400", "57600", "115200", "250000"]
        )
        self.baudrate_combo.setCurrentText("9600")
        layout.addWidget(self.baudrate_combo, 1, 1, 1, 2)

        self.scan_btn = QPushButton("Buscar dispositivos activos")
        self.scan_btn.setToolTip("Escanear puertos y detectar actividad de datos")
        self.scan_btn.clicked.connect(self.scan_serial_devices)
        layout.addWidget(self.scan_btn, 2, 0, 1, 3)

        self.connect_btn = QPushButton("Conectar")
        self.connect_btn.clicked.connect(self.connect_serial)
        self.connect_btn.setStyleSheet(
            "QPushButton{background:#27ae60;color:white;font-weight:bold;padding:6px;}"
            "QPushButton:hover{background:#219653;}"
        )
        self.disconnect_btn = QPushButton("Desconectar")
        self.disconnect_btn.clicked.connect(self.disconnect_serial)
        self.disconnect_btn.setEnabled(False)
        self.disconnect_btn.setStyleSheet(
            "QPushButton{background:#c0392b;color:white;font-weight:bold;padding:6px;}"
            "QPushButton:hover{background:#a93226;}"
            "QPushButton:disabled{background:#95a5a6;}"
        )
        row = QHBoxLayout()
        row.addWidget(self.connect_btn)
        row.addWidget(self.disconnect_btn)
        layout.addLayout(row, 3, 0, 1, 3)
        return group

    def _create_write_group(self) -> QGroupBox:
        """Grupo para enviar datos/comandos al dispositivo conectado."""
        group  = QGroupBox("Enviar al dispositivo")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QHBoxLayout(group)
        layout.setSpacing(6)

        self.write_edit = QLineEdit()
        self.write_edit.setPlaceholderText("Escribe un comando y presiona Enter o Enviar…")
        self.write_edit.returnPressed.connect(self._send_data)

        self.line_ending_combo = QComboBox()
        self.line_ending_combo.addItems(list(_LINE_ENDINGS.keys()))
        self.line_ending_combo.setCurrentText("\\n  (LF)")
        self.line_ending_combo.setMaximumWidth(110)
        self.line_ending_combo.setToolTip("Terminador que se añade al final del mensaje")

        self.send_btn = QPushButton("Enviar")
        self.send_btn.clicked.connect(self._send_data)
        self.send_btn.setEnabled(False)
        self.send_btn.setMaximumWidth(70)
        self.send_btn.setStyleSheet(
            "QPushButton{background:#2980b9;color:white;font-weight:bold;padding:5px;}"
            "QPushButton:hover{background:#2471a3;}"
            "QPushButton:disabled{background:#95a5a6;}"
        )

        layout.addWidget(self.write_edit)
        layout.addWidget(self.line_ending_combo)
        layout.addWidget(self.send_btn)
        return group

    def _create_graph_config_group(self) -> QGroupBox:
        group  = QGroupBox("Configuración del Gráfico")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QGridLayout(group)
        layout.setSpacing(7)

        self.auto_scale_check = QCheckBox("Escala automática")
        self.auto_scale_check.setChecked(True)
        self.auto_scale_check.stateChanged.connect(self._on_scale_mode_changed)
        layout.addWidget(self.auto_scale_check, 0, 0, 1, 3)

        layout.addWidget(QLabel("Mín:"), 1, 0)
        self.y_min_spin = QDoubleSpinBox()
        self.y_min_spin.setRange(-100000, 100000)
        self.y_min_spin.setValue(-10.0)
        self.y_min_spin.setSingleStep(0.5)
        self.y_min_spin.setEnabled(False)
        self.y_min_spin.valueChanged.connect(self._on_manual_scale_changed)
        layout.addWidget(self.y_min_spin, 1, 1, 1, 2)

        layout.addWidget(QLabel("Máx:"), 2, 0)
        self.y_max_spin = QDoubleSpinBox()
        self.y_max_spin.setRange(-100000, 100000)
        self.y_max_spin.setValue(10.0)
        self.y_max_spin.setSingleStep(0.5)
        self.y_max_spin.setEnabled(False)
        self.y_max_spin.valueChanged.connect(self._on_manual_scale_changed)
        layout.addWidget(self.y_max_spin, 2, 1, 1, 2)

        layout.addWidget(QLabel("Puntos visibles:"), 3, 0)
        self.data_points_spin = QSpinBox()
        self.data_points_spin.setRange(10, 10000)
        self.data_points_spin.setValue(100)
        self.data_points_spin.setSingleStep(50)
        self.data_points_spin.setSuffix(" pts")
        self.data_points_spin.valueChanged.connect(self._on_max_points_changed)
        layout.addWidget(self.data_points_spin, 3, 1, 1, 2)

        clear_btn = QPushButton("Limpiar")
        clear_btn.clicked.connect(self.clear_plot)
        clear_btn.setStyleSheet(
            "QPushButton{background:#3498db;color:white;font-weight:bold;padding:5px;}"
        )
        self.pause_btn = QPushButton("Pausar")
        self.pause_btn.setCheckable(True)
        self.pause_btn.clicked.connect(self._on_pause_toggled)
        self.pause_btn.setStyleSheet(
            "QPushButton{background:#f39c12;color:white;font-weight:bold;padding:5px;}"
            "QPushButton:checked{background:#7f8c8d;}"
        )
        row = QHBoxLayout()
        row.addWidget(clear_btn)
        row.addWidget(self.pause_btn)
        layout.addLayout(row, 4, 0, 1, 3)
        return group

    def _create_format_group(self) -> QGroupBox:
        group  = QGroupBox("Formato de Datos / Canales")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QGridLayout(group)
        layout.setSpacing(7)

        layout.addWidget(QLabel("Tipo:"), 0, 0)
        self.format_type_combo = QComboBox()
        self.format_type_combo.addItems(["Simple", "CSV", "JSON"])
        self.format_type_combo.currentTextChanged.connect(self._on_format_type_changed)
        layout.addWidget(self.format_type_combo, 0, 1, 1, 2)

        layout.addWidget(QLabel("Plantilla:"), 1, 0, 1, 3)
        self.format_template_edit = QLineEdit()
        self.format_template_edit.setPlaceholderText("Ej: temp,hum,presion  o  V;I;P")
        layout.addWidget(self.format_template_edit, 2, 0, 1, 3)

        layout.addWidget(QLabel("Canales a graficar:"), 3, 0, 1, 3)
        self.channel_list = QListWidget()
        self.channel_list.setMaximumHeight(90)
        self.channel_list.setToolTip("Marca o desmarca canales para mostrar/ocultar en el gráfico")
        self.channel_list.itemChanged.connect(self._on_channel_selection_changed)
        layout.addWidget(self.channel_list, 4, 0, 1, 3)

        self.apply_format_btn = QPushButton("Aplicar plantilla")
        self.apply_format_btn.clicked.connect(self.apply_frame_format)
        layout.addWidget(self.apply_format_btn, 5, 0, 1, 3)
        return group

    def _create_log_group(self) -> QGroupBox:
        group  = QGroupBox("Mensajes")
        group.setFont(QFont("Arial", 10, QFont.Bold))
        layout = QVBoxLayout(group)
        self.status_text = QTextEdit()
        self.status_text.setReadOnly(True)
        self.status_text.setMaximumHeight(130)
        self.status_text.setStyleSheet(
            "QTextEdit{background:#f8f9fa;font-family:'Courier New';font-size:9pt;}"
        )
        layout.addWidget(self.status_text)
        return group

    def _create_graph_panel(self) -> QWidget:
        panel  = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(5)

        self.graph_title = QLabel("GRÁFICO EN TIEMPO REAL — DATOS SERIALES")
        self.graph_title.setAlignment(Qt.AlignCenter)
        self.graph_title.setFont(QFont("Arial", 13, QFont.Bold))
        self.graph_title.setStyleSheet(
            "color:#2c3e50;padding:7px;background:#ecf0f1;border-radius:5px;"
        )
        layout.addWidget(self.graph_title)

        self.stats_label = QLabel("Estadísticas: esperando datos…")
        self.stats_label.setFont(QFont("Arial", 9))
        self.stats_label.setStyleSheet(
            "color:#555;padding:4px;background:#f8f9fa;border-radius:3px;"
        )
        layout.addWidget(self.stats_label)

        self.figure, self.ax = plt.subplots(figsize=(10, 6), dpi=100)
        self.canvas  = FigureCanvas(self.figure)
        self.toolbar = NavigationToolbar(self.canvas, self)
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas)
        return panel

    def setup_menu(self):
        mb = self.menuBar()

        fm = mb.addMenu("Archivo")
        ea = QAction("Exportar datos CSV…", self)
        ea.triggered.connect(self.export_data)
        ea.setShortcut("Ctrl+S")
        fm.addAction(ea)
        fm.addSeparator()
        qa = QAction("Salir", self)
        qa.triggered.connect(self.close)
        qa.setShortcut("Ctrl+Q")
        fm.addAction(qa)

        hm = mb.addMenu("Ayuda")
        aa = QAction("Acerca de…", self)
        aa.triggered.connect(self.show_about)
        hm.addAction(aa)

    # ------------------------------------------------------------------
    # Gráfico
    # ------------------------------------------------------------------

    def setup_plot(self):
        """Inicializar / reiniciar ejes y limpiar líneas registradas."""
        self.channel_lines.clear()
        self.ax.clear()
        self.ax.set_xlabel("Tiempo (s)", fontsize=10)
        self.ax.set_ylabel("Valor", fontsize=10)
        self.ax.set_title("Esperando datos…", fontsize=11)
        self.ax.grid(True, alpha=0.3, linestyle="--")
        self.ax.set_facecolor("#f8f9fa")
        self.ax.set_xlim(0, 10)
        self.ax.set_ylim(self.y_min, self.y_max)
        self.figure.tight_layout()
        self.canvas.draw_idle()

    def start_animation(self):
        if self.animation is not None:
            self.animation.event_source.stop()
        self.animation = FuncAnimation(
            self.figure,
            self._update_plot_frame,
            interval=100,
            blit=False,
            cache_frame_data=False,
        )

    def _update_plot_frame(self, _frame):
        """Actualizar todas las líneas activas en el gráfico."""
        try:
            if not self.time_buffer or not self.channel_buffers:
                return
            t_list = list(self.time_buffer)

            for field in list(self.active_channels):
                if field not in self.channel_buffers:
                    continue
                d_list = list(self.channel_buffers[field])

                # Crear línea si no existe aún
                if field not in self.channel_lines:
                    color = self._channel_color(field)
                    line, = self.ax.plot([], [], lw=1.5, color=color, label=field)
                    self.channel_lines[field] = line
                    self.ax.legend(loc="upper right", fontsize=8, framealpha=0.7)

                self.channel_lines[field].set_data(t_list, d_list)

            # Eje X
            if len(t_list) > 1:
                x_rng = t_list[-1] - t_list[0] or 1.0
                self.ax.set_xlim(t_list[0] - x_rng * 0.02, t_list[-1] + x_rng * 0.02)

            # Eje Y
            if self.auto_scale:
                all_v = [
                    v for f in self.active_channels
                    if f in self.channel_buffers
                    for v in self.channel_buffers[f]
                    if v == v  # excluir NaN
                ]
                if all_v:
                    dmin, dmax = min(all_v), max(all_v)
                    m = (dmax - dmin) * 0.1 if dmax != dmin else (abs(dmin * 0.1) or 1.0)
                    self.ax.set_ylim(dmin - m, dmax + m)
            else:
                self.ax.set_ylim(self.y_min, self.y_max)

            # Título dinámico
            if self.active_channels and self.channel_buffers:
                parts = []
                for f in self.available_fields:
                    if f in self.active_channels and f in self.channel_buffers:
                        d = self.channel_buffers[f]
                        if d:
                            parts.append(f"{f}={list(d)[-1]:.3f}")
                if parts:
                    self.ax.set_title("  |  ".join(parts), fontsize=10)

            self.canvas.draw_idle()
        except Exception as e:
            print(f"[update_plot_frame] {e}")

    def _channel_color(self, field: str) -> str:
        """Asignar color consistente a cada canal según su índice."""
        try:
            idx = self.available_fields.index(field)
        except ValueError:
            idx = 0
        return _CHANNEL_COLORS[idx % len(_CHANNEL_COLORS)]

    # ------------------------------------------------------------------
    # Recepción y procesamiento de datos
    # ------------------------------------------------------------------

    @Slot(str)
    def handle_raw_data(self, line: str):
        """Recibir línea cruda, parsear y encolar o acumular."""
        try:
            data_dict = self._parse_line(line)
            if not data_dict:
                return

            # Registrar campos nuevos detectados
            new_fields = [f for f in data_dict if f not in self.available_fields]
            if new_fields:
                self._update_available_fields(self.available_fields + new_fields)

            ts = time.time()

            if self.is_paused:
                self._pause_queue.append((ts, data_dict))
                return

            self._process_data_point(ts, data_dict)

        except ValueError as e:
            self.update_status(f"Trama no válida ({e}): {line}")
        except Exception as e:
            self.update_status(f"Error procesando dato: {e}")

    def _process_data_point(self, timestamp: float, data_dict: dict):
        """Agregar punto a buffers de visualización y de sesión."""
        if not self.time_buffer:
            self.start_time = timestamp
        ref = self.start_time or timestamp
        t   = timestamp - ref

        self.time_buffer.append(t)

        # Asegurar que todos los canales conocidos tienen un deque
        for field in self.available_fields:
            if field not in self.channel_buffers:
                self.channel_buffers[field] = deque(
                    [float("nan")] * len(self.time_buffer),
                    maxlen=self.max_data_points
                )

        for field in self.channel_buffers:
            value = data_dict.get(field, float("nan"))
            self.channel_buffers[field].append(value)

        # Historial de sesión (ilimitado, crece durante la sesión)
        self._session_times.append(t)
        for field, value in data_dict.items():
            self._session_data.setdefault(field, []).append(value)

        if len(self.time_buffer) % 10 == 0:
            self._update_stats()

    def _update_stats(self):
        """Mostrar estadísticas de todos los canales activos."""
        try:
            parts = []
            for field in self.available_fields:
                if field not in self.active_channels:
                    continue
                if field not in self.channel_buffers:
                    continue
                vals = [v for v in self.channel_buffers[field] if v == v]
                if not vals:
                    continue
                color = self._channel_color(field)
                parts.append(
                    f"<span style='color:{color}'><b>{field}</b></span>: "
                    f"act={vals[-1]:.3f} "
                    f"<span style='color:#e74c3c'>↓{min(vals):.3f}</span> "
                    f"<span style='color:#27ae60'>↑{max(vals):.3f}</span>"
                )
            self.stats_label.setText(
                "  |  ".join(parts) if parts else "Estadísticas: esperando datos…"
            )
        except Exception as e:
            print(f"[update_stats] {e}")

    # ------------------------------------------------------------------
    # Parseo de tramas
    # ------------------------------------------------------------------

    def _parse_line(self, line: str) -> dict:
        """
        Parsear línea según self.current_format.
        Retorna dict {campo: float}. Lanza ValueError si no puede parsear.
        Compatible con cualquier dispositivo USB/COM que use texto ASCII.
        """
        line = line.strip()
        if not line:
            return {}

        if self.current_format == "Simple":
            try:
                return {"valor": float(line.replace(",", "."))}
            except ValueError:
                raise ValueError("No se pudo interpretar como número.")

        if self.current_format == "CSV":
            parts  = re.split(r"[;,]", line)
            values = []
            for p in parts:
                try:
                    values.append(float(p.strip().replace(",", ".")))
                except ValueError:
                    continue
            if not values:
                raise ValueError("Sin valores numéricos en línea CSV.")
            names = self.available_fields or [f"ch{i+1}" for i in range(len(values))]
            return {names[i]: values[i] for i in range(min(len(names), len(values)))}

        if self.current_format == "JSON":
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"JSON inválido: {e}")
            if not isinstance(obj, dict):
                raise ValueError("El JSON debe ser un objeto {}.")
            keys = self.available_fields or list(obj.keys())
            data = {}
            for k in keys:
                if k in obj:
                    try:
                        data[k] = float(str(obj[k]).replace(",", "."))
                    except ValueError:
                        continue
            if not data:
                raise ValueError("Sin campos numéricos en JSON.")
            return data

        raise ValueError(f"Formato no soportado: {self.current_format}")

    # ------------------------------------------------------------------
    # Formato y canales
    # ------------------------------------------------------------------

    def _on_format_type_changed(self, text: str):
        self.current_format = text or "Simple"
        self.available_fields = []
        self.channel_list.blockSignals(True)
        self.channel_list.clear()
        self.channel_list.blockSignals(False)
        self.active_channels.clear()

    def _on_channel_selection_changed(self, item: QListWidgetItem):
        """Activar/desactivar canal según checkbox."""
        field = item.text()
        if item.checkState() == Qt.Checked:
            self.active_channels.add(field)
        else:
            self.active_channels.discard(field)
            if field in self.channel_lines:
                self.channel_lines[field].remove()
                del self.channel_lines[field]
            handles = [self.channel_lines[f] for f in self.channel_lines]
            labels  = list(self.channel_lines.keys())
            if handles:
                self.ax.legend(handles, labels, loc="upper right", fontsize=8)
            else:
                leg = self.ax.get_legend()
                if leg:
                    leg.remove()

    @Slot()
    def apply_frame_format(self):
        try:
            template = self.format_template_edit.text().strip()
            if not template:
                self.available_fields = []
                self.active_channels.clear()
                self.channel_list.blockSignals(True)
                self.channel_list.clear()
                self.channel_list.blockSignals(False)
                self.update_status("Plantilla limpiada. Campos se autodetectarán.")
                return
            fields = [f.strip() for f in re.split(r"[;,]", template) if f.strip()]
            if not fields:
                QMessageBox.warning(self, "Formato", "Sin campos válidos en la plantilla.")
                return
            self._update_available_fields(fields)
            self.update_status("Plantilla aplicada: " + ", ".join(fields))
        except Exception as e:
            self.show_error(f"Error aplicando plantilla: {e}", show_dialog=True)

    def _update_available_fields(self, fields: list):
        """Agregar campos al selector de canales (sin eliminar los ya existentes)."""
        existing = {
            self.channel_list.item(i).text()
            for i in range(self.channel_list.count())
        }
        self.available_fields = list(dict.fromkeys(self.available_fields + fields))

        self.channel_list.blockSignals(True)
        for field in fields:
            if field not in existing:
                item = QListWidgetItem(field)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
                # Color visual del canal
                color = self._channel_color(field)
                item.setForeground(
                    __import__("PySide6.QtGui", fromlist=["QColor"]).QColor(color)
                )
                self.channel_list.addItem(item)
                self.active_channels.add(field)
        self.channel_list.blockSignals(False)

    # ------------------------------------------------------------------
    # Conexión serial
    # ------------------------------------------------------------------

    @Slot()
    def refresh_com_ports(self):
        if self.serial_reader.is_connected():
            return
        try:
            cur = self.com_port_combo.currentData()
            self.com_port_combo.blockSignals(True)
            self.com_port_combo.clear()
            for p in serial.tools.list_ports.comports():
                self.com_port_combo.addItem(f"{p.device} — {p.description}", p.device)
            if cur:
                idx = self.com_port_combo.findData(cur)
                if idx >= 0:
                    self.com_port_combo.setCurrentIndex(idx)
            self.com_port_combo.blockSignals(False)
        except Exception as e:
            self.com_port_combo.blockSignals(False)
            self.show_error(f"Error al buscar puertos: {e}")

    @Slot()
    def connect_serial(self):
        try:
            if self.serial_reader.is_connected():
                QMessageBox.information(self, "Conexión", "Ya está conectado.")
                return
            port = self.com_port_combo.currentData()
            if not port:
                QMessageBox.warning(self, "Conexión", "Selecciona un puerto COM.")
                return
            baudrate = int(self.baudrate_combo.currentText())
            self.update_status(f"Conectando a {port} @ {baudrate}…")
            if self.serial_reader.connect_serial(port, baudrate):
                self._last_port    = port
                self._last_baudrate = baudrate
                self._reconnect_timer.stop()
                self._reconnect_attempts = 0
                self.connect_btn.setEnabled(False)
                self.disconnect_btn.setEnabled(True)
                self.com_port_combo.setEnabled(False)
                self.baudrate_combo.setEnabled(False)
                self.send_btn.setEnabled(True)
                self.statusBar().showMessage(f"Conectado a {port} @ {baudrate}", 0)
            else:
                QMessageBox.warning(self, "Conexión", "No se pudo conectar.")
        except Exception as e:
            self.show_error(f"Error al conectar: {e}", show_dialog=True)

    @Slot()
    def disconnect_serial(self):
        # Limpiar último puerto para evitar auto-reconexión tras desconexión manual
        self._last_port = ""
        self._reconnect_timer.stop()
        self._reconnect_attempts = 0
        try:
            if self.serial_reader.is_connected():
                self.serial_reader.disconnect()
            self.connect_btn.setEnabled(True)
            self.disconnect_btn.setEnabled(False)
            self.com_port_combo.setEnabled(True)
            self.baudrate_combo.setEnabled(True)
            self.send_btn.setEnabled(False)
            self.statusBar().showMessage("Desconectado", 0)
        except Exception as e:
            self.show_error(f"Error al desconectar: {e}", show_dialog=True)

    @Slot()
    def scan_serial_devices(self):
        """Escanear puertos y detectar cuáles tienen actividad de datos."""
        try:
            ports = list(serial.tools.list_ports.comports())
            if not ports:
                QMessageBox.information(self, "Búsqueda", "No se encontraron puertos.")
                return
            baud = int(self.baudrate_combo.currentText())
            self.update_status(f"Escaneando {len(ports)} puerto(s) @ {baud}…")
            results = []
            for port in ports:
                has_data = False
                try:
                    with serial.Serial(port.device, baudrate=baud, timeout=0.3) as ser:
                        deadline = time.time() + 1.5
                        buf = ""
                        while time.time() < deadline and not has_data:
                            if ser.in_waiting > 0:
                                buf += ser.read(ser.in_waiting).decode("utf-8", errors="ignore")
                                while "\n" in buf:
                                    ln, buf = buf.split("\n", 1)
                                    if ln.strip():
                                        has_data = True
                                        break
                            else:
                                time.sleep(0.1)
                except Exception as ex:
                    results.append(f"{port.device}: error ({ex})")
                    continue
                estado = "actividad detectada ✓" if has_data else "sin datos"
                results.append(f"{port.device}: {estado}")
                self.update_status(f"{port.device} → {estado}")
            QMessageBox.information(self, "Resultado del escaneo", "\n".join(results))
        except Exception as e:
            self.show_error(f"Error en escaneo: {e}", show_dialog=True)

    # ------------------------------------------------------------------
    # Envío de datos al dispositivo
    # ------------------------------------------------------------------

    @Slot()
    def _send_data(self):
        """Enviar texto al dispositivo con el terminador seleccionado."""
        text = self.write_edit.text()
        if not text:
            return
        ending = _LINE_ENDINGS.get(self.line_ending_combo.currentText(), "\n")
        if self.serial_reader.write_data(text + ending):
            self.update_status(f"→ Enviado: {repr(text + ending)}")
            self.write_edit.clear()

    # ------------------------------------------------------------------
    # Auto-reconexión
    # ------------------------------------------------------------------

    @Slot(str)
    def on_serial_error(self, message: str):
        """Errores seriales: solo log + rehabilitar botones + iniciar reconexión."""
        self.update_status(f"ERROR SERIAL: {message}")
        self.connect_btn.setEnabled(True)
        self.disconnect_btn.setEnabled(False)
        self.com_port_combo.setEnabled(True)
        self.baudrate_combo.setEnabled(True)
        self.send_btn.setEnabled(False)
        self.statusBar().showMessage("Conexión perdida — intentando reconectar…", 0)

        if self._last_port and not self._reconnect_timer.isActive():
            self._reconnect_attempts = 0
            self._reconnect_timer.start(3000)
            self.update_status(
                f"Auto-reconexión activa: intentando cada 3 s "
                f"(máx {self._max_reconnect_attempts} intentos)…"
            )

    @Slot()
    def _try_reconnect(self):
        self._reconnect_attempts += 1
        if self._reconnect_attempts > self._max_reconnect_attempts:
            self._reconnect_timer.stop()
            self.update_status(
                "Auto-reconexión fallida tras "
                f"{self._max_reconnect_attempts} intentos. Conecta manualmente."
            )
            self.statusBar().showMessage("Auto-reconexión fallida", 0)
            return

        self.update_status(
            f"Reconexión intento {self._reconnect_attempts}/"
            f"{self._max_reconnect_attempts} → {self._last_port}"
        )
        if self.serial_reader.connect_serial(self._last_port, self._last_baudrate):
            self._reconnect_timer.stop()
            self._reconnect_attempts = 0
            self.connect_btn.setEnabled(False)
            self.disconnect_btn.setEnabled(True)
            self.com_port_combo.setEnabled(False)
            self.baudrate_combo.setEnabled(False)
            self.send_btn.setEnabled(True)
            self.update_status(f"Reconectado exitosamente a {self._last_port}")
            self.statusBar().showMessage(
                f"Reconectado a {self._last_port} @ {self._last_baudrate}", 0
            )

    # ------------------------------------------------------------------
    # Controles del gráfico
    # ------------------------------------------------------------------

    @Slot()
    def clear_plot(self):
        try:
            self.time_buffer.clear()
            self.channel_buffers.clear()
            self._session_times.clear()
            self._session_data.clear()
            self._pause_queue.clear()
            self.start_time = None
            self.setup_plot()
            self.stats_label.setText("Estadísticas: esperando datos…")
            self.update_status("Gráfico y sesión limpiados.")
        except Exception as e:
            self.show_error(f"Error limpiando gráfico: {e}")

    @Slot()
    def _on_pause_toggled(self):
        self.is_paused = self.pause_btn.isChecked()
        if self.is_paused:
            self.pause_btn.setText("Reanudar")
            self.update_status("Gráfico pausado — datos en cola.")
        else:
            self.pause_btn.setText("Pausar")
            n = len(self._pause_queue)
            if n:
                self.update_status(f"Reanudando — procesando {n} puntos en cola…")
                for ts, data_dict in self._pause_queue:
                    self._process_data_point(ts, data_dict)
                self._pause_queue.clear()
                self.update_status(f"{n} puntos incorporados al gráfico.")
            else:
                self.update_status("Gráfico reanudado.")

    @Slot(int)
    def _on_scale_mode_changed(self, _state):
        self.auto_scale = self.auto_scale_check.isChecked()
        self.y_min_spin.setEnabled(not self.auto_scale)
        self.y_max_spin.setEnabled(not self.auto_scale)

    @Slot()
    def _on_manual_scale_changed(self):
        self.y_min = self.y_min_spin.value()
        self.y_max = self.y_max_spin.value()
        if self.y_min >= self.y_max:
            self.y_max = self.y_min + 0.1
            self.y_max_spin.setValue(self.y_max)

    @Slot()
    def _on_max_points_changed(self):
        new_max = self.data_points_spin.value()
        self.max_data_points = new_max
        self.time_buffer = deque(self.time_buffer, maxlen=new_max)
        for field in self.channel_buffers:
            self.channel_buffers[field] = deque(
                self.channel_buffers[field], maxlen=new_max
            )

    # ------------------------------------------------------------------
    # Exportación
    # ------------------------------------------------------------------

    @Slot()
    def export_data(self):
        if not self._session_times and not self.time_buffer:
            QMessageBox.warning(self, "Sin datos", "No hay datos para exportar.")
            return

        n_visible = len(self.time_buffer)
        n_session = len(self._session_times)
        reply = QMessageBox.question(
            self,
            "Exportar datos",
            f"¿Qué datos deseas exportar?\n\n"
            f"  • Sí  → Sesión completa ({n_session} puntos)\n"
            f"  • No  → Solo ventana visible ({n_visible} puntos)",
            QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
        )
        if reply == QMessageBox.Cancel:
            return

        use_session = (reply == QMessageBox.Yes)
        times  = self._session_times if use_session else list(self.time_buffer)
        fields = list(self._session_data.keys() if use_session else self.channel_buffers.keys())

        file_name, _ = QFileDialog.getSaveFileName(
            self, "Exportar datos", "datos_serial.csv", "CSV Files (*.csv)"
        )
        if not file_name:
            return
        try:
            with open(file_name, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Tiempo(s)"] + fields)
                for i, t in enumerate(times):
                    row = [f"{t:.6f}"]
                    for field in fields:
                        src  = self._session_data if use_session else {
                            k: list(v) for k, v in self.channel_buffers.items()
                        }
                        vals = src.get(field, [])
                        row.append(f"{vals[i]:.6f}" if i < len(vals) else "")
                    writer.writerow(row)
            self.update_status(
                f"Exportados {len(times)} puntos ({len(fields)} canales) → {file_name}"
            )
            QMessageBox.information(
                self, "Exportación exitosa",
                f"Exportados {len(times)} puntos con {len(fields)} canal(es)."
            )
        except Exception as e:
            self.show_error(f"Error exportando: {e}", show_dialog=True)

    # ------------------------------------------------------------------
    # Estado / mensajes
    # ------------------------------------------------------------------

    @Slot(str)
    def update_status(self, message: str):
        try:
            ts = datetime.now().strftime("%H:%M:%S")
            self.status_text.append(f"[{ts}] {message}")
            lines = self.status_text.toPlainText().split("\n")
            if len(lines) > 200:
                self.status_text.setPlainText("\n".join(lines[-200:]))
            cur = self.status_text.textCursor()
            cur.movePosition(QTextCursor.MoveOperation.End)
            self.status_text.setTextCursor(cur)
        except Exception as e:
            print(f"[update_status] {e}")

    def show_error(self, message: str, show_dialog: bool = False):
        self.update_status(f"ERROR: {message}")
        if not show_dialog:
            return
        now = time.time()
        if now - self._last_error_time > 3.0 or message != self._last_error_msg:
            self._last_error_time = now
            self._last_error_msg  = message
            QMessageBox.critical(self, "Error", message)

    @Slot()
    def show_about(self):
        QMessageBox.about(
            self, "Acerca de",
            """
            <h3>Sistema de Monitoreo Serial v5.1</h3>
            <p><b>Angel Maldonado Fuentes</b></p>
            <p>Monitoreo en tiempo real de dispositivos USB/COM:<br>
            ESP32, Arduino, sensores industriales, PLCs, GPS, y más.</p>
            <p><b>Funcionalidades:</b></p>
            <ul>
                <li>Multi-canal simultáneo (Simple, CSV, JSON)</li>
                <li>Historial completo de sesión + exportación</li>
                <li>Buffer durante pausa (sin pérdida de datos)</li>
                <li>Auto-reconexión ante desconexiones inesperadas</li>
                <li>Envío bidireccional de comandos al dispositivo</li>
                <li>Búsqueda de dispositivos activos</li>
                <li>Configuración persistente</li>
            </ul>
            <p>Python · PySide6 · Matplotlib · PySerial</p>
            """,
        )

    # ------------------------------------------------------------------
    # Configuración persistente
    # ------------------------------------------------------------------

    def load_settings(self):
        try:
            geom = self.settings.value("geometry")
            if geom:
                self.restoreGeometry(geom)
            baud = self.settings.value("baudrate")
            if baud:
                self.baudrate_combo.setCurrentText(str(baud))
            pts = self.settings.value("max_points")
            if pts:
                try:
                    self.data_points_spin.setValue(int(pts))
                except ValueError:
                    pass
            auto = self.settings.value("auto_scale")
            if auto is not None:
                self.auto_scale_check.setChecked(str(auto).lower() in ("true", "1"))
            for attr, key in [("y_min_spin", "y_min"), ("y_max_spin", "y_max")]:
                val = self.settings.value(key)
                if val is not None:
                    try:
                        getattr(self, attr).setValue(float(val))
                    except ValueError:
                        pass
            last = self.settings.value("last_port")
            if last:
                idx = self.com_port_combo.findData(last)
                if idx < 0:
                    idx = self.com_port_combo.findText(str(last))
                if idx >= 0:
                    self.com_port_combo.setCurrentIndex(idx)
        except Exception as e:
            print(f"[load_settings] {e}")

    def save_settings(self):
        try:
            self.settings.setValue("geometry",   self.saveGeometry())
            self.settings.setValue("baudrate",   self.baudrate_combo.currentText())
            self.settings.setValue("max_points", self.data_points_spin.value())
            self.settings.setValue("auto_scale", self.auto_scale_check.isChecked())
            self.settings.setValue("y_min",      self.y_min_spin.value())
            self.settings.setValue("y_max",      self.y_max_spin.value())
            port = self.com_port_combo.currentData() or self.com_port_combo.currentText()
            if port:
                self.settings.setValue("last_port", port)
        except Exception as e:
            print(f"[save_settings] {e}")

    # ------------------------------------------------------------------
    # Cierre limpio
    # ------------------------------------------------------------------

    def closeEvent(self, event):
        try:
            self.save_settings()
            if self._reconnect_timer:
                self._reconnect_timer.stop()
            if self.animation:
                self.animation.event_source.stop()
            if self.refresh_timer:
                self.refresh_timer.stop()
            if self.serial_reader:
                self.serial_reader.disconnect()
        except Exception as e:
            print(f"[closeEvent] {e}")
        finally:
            event.accept()
