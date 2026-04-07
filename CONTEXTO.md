# CONTEXTO — Sistema de Monitoreo Serial

> Documento de referencia técnica del proyecto.  
> Registra el historial de versiones, bugs encontrados, decisiones de diseño
> y puntos de mejora para versiones futuras.  
> **Actualizar este archivo cada vez que se haga un cambio significativo.**

---

## Índice

1. [Descripción del proyecto](#1-descripción-del-proyecto)
2. [Stack técnico](#2-stack-técnico)
3. [Estructura de archivos](#3-estructura-de-archivos)
4. [Historial de versiones](#4-historial-de-versiones)
5. [Registro de bugs](#5-registro-de-bugs)
6. [Decisiones de arquitectura](#6-decisiones-de-arquitectura)
7. [Limitaciones conocidas (v5)](#7-limitaciones-conocidas-v5)
8. [Puntos de mejora para versiones futuras](#8-puntos-de-mejora-para-versiones-futuras)
9. [Notas de dependencias](#9-notas-de-dependencias)

---

## 1. Descripción del proyecto

Aplicación de escritorio para monitoreo en tiempo real de datos seriales
provenientes de microcontroladores (ESP32, Arduino, etc.).

Permite:
- Conectarse a un puerto COM a baudrate configurable.
- Recibir tramas en formato **Simple** (float), **CSV** o **JSON**.
- Graficar el campo seleccionado en tiempo real.
- Detectar automáticamente qué puertos tienen actividad de datos.
- Exportar los datos visibles a CSV.
- Recordar la configuración entre sesiones (QSettings).

Origen: refactorización del archivo monolítico `PLOTTER.py`.

---

## 2. Stack técnico

| Componente       | Librería          | Versión mínima |
|------------------|-------------------|----------------|
| Interfaz gráfica | PySide6           | 6.x            |
| Gráficos         | Matplotlib        | 3.3+           |
| Comunicación     | PySerial          | 3.x            |
| Lenguaje         | Python            | 3.10+          |

### Instalar dependencias

```bash
pip install PySide6 matplotlib pyserial
```

### Ejecutar

```bash
cd sistema_monitoreo_serial_modular_v5
python main.py
```

---

## 3. Estructura de archivos

```
sistema_monitoreo_serial_modular_v5/
├── main.py          # Punto de entrada — crea QApplication y lanza la ventana
├── serial_reader.py # Clase SerialReader — lectura serial en hilo separado
├── main_window.py   # Clase RealTimePlot — UI, gráfico, parseo, lógica
└── CONTEXTO.md      # Este archivo
```

### Flujo de datos

```
[ESP32/Arduino]
      │  bytes por puerto serial
      ▼
 SerialReader._read_serial_data()   ← hilo daemon
      │  Signal(str) — línea cruda
      ▼
 RealTimePlot.handle_raw_data()     ← hilo Qt (main)
      │  _parse_line() → dict
      ▼
 _add_data_point(float)
      │  deque(maxlen=N)
      ▼
 FuncAnimation._update_plot_frame() ← timer Qt 100ms
      │
      ▼
 Canvas matplotlib
```

---

## 4. Historial de versiones

### v1 — `sistema_monitoreo_serial_modular/`
Primera extracción modular de `PLOTTER.py`.

- `serial_reader.py`: `Signal(float)` — el lector parsea el dato a float.
- `main_window.py`: funcionalidad básica, configuración persistente.
- **Bugs críticos**: `toggle_pause` y `closeEvent` definidos fuera de la clase.

---

### fixed — `sistema_monitoreo_serial_modular_fixed/`
Intento de corrección de v1.

- Corrige la indentación de `toggle_pause` ✓
- `closeEvent` **sigue fuera de la clase** ✗
- Código idéntico a v1 en todo lo demás.

---

### v2 — `sistema_monitoreo_serial_modular_v2/`
Intento de agregar soporte para tramas CSV y JSON.

- `serial_reader.py`: cambia a `Signal(str)` — correcto.
- `main_window.py`: código duplicado y mezclado sin indentación en `__init__`
  y `setup_ui`. La aplicación **no puede ejecutarse**.
- Diseño correcto, implementación rota.

---

### v3 — `sistema_monitoreo_serial_modular_v3/`
Reescritura limpia de v2. **Primera versión completamente funcional.**

- Todos los métodos correctamente dentro de la clase.
- Atributos UI declarados explícitamente como `None` antes de `setup_ui()`.
- `start_animation()` como método separado.
- `blockSignals(True/False)` al actualizar combo de puertos.
- `canvas.draw_idle()` en lugar de `canvas.draw()`.
- `blit=False` — más estable en distintos sistemas.
- Intervalo de animación: 100ms (10 fps).
- Parseo completo Simple / CSV / JSON vía `parse_line_to_dict()`.
- `scan_serial_devices` funcional.
- Barra de estado Qt (`statusBar()`).
- Rango de spinboxes ampliado a ±100,000.

---

### v4 — `sistema_monitoreo_serial_modular_v4/`
Refactorización estructural de v3.

- `setup_ui` dividido en métodos helper `create_*` → mayor cohesión.
- `serial_reader.py` más limpio: eliminó imports innecesarios.
- **Regresión**: QSettings cambió de key →
  `("SistemaMonitoreoSerial", "Config")` en lugar de
  `("AngelMaldonado", "SistemaMonitoreoSerial")` — rompe configuración guardada.
- `QTimer()` sin padre → gestión de memoria menos segura.

---

### v5.0 — `sistema_monitoreo_serial_modular_v5/`
Unificación de lo mejor de cada versión anterior.

**Mejoras respecto a v4:**
- `serial_reader.py`: `threading.Event` en lugar de `bool` para control del hilo.
- `closeEvent` correctamente dentro de la clase (bug de v1/fixed corregido).
- `deque(maxlen=N)` para buffers — elimina recorte manual y simplifica el código.
- `on_serial_error` separado de `show_error` — errores seriales solo se loguean.
- `show_error` con debounce de 3 s — evita spam de diálogos.
- QSettings conserva key de v3 — compatibilidad con configuraciones anteriores.
- `refresh_com_ports` se omite si hay conexión activa — evita interferencia.
- `cache_frame_data=False` en `FuncAnimation` — evita memory leak en sesiones largas.
- `QTimer(self)` con padre — gestión de memoria correcta.
- Prefijo `_` en métodos internos.

---

### v5.1 — `sistema_monitoreo_serial_modular_v5/` (versión actual)
Implementación de las 4 mejoras de prioridad alta. Compatible con cualquier
dispositivo USB/COM (ESP32, Arduino, sensores industriales, PLCs, GPS…).

**Nuevas funcionalidades:**

#### 1. Multi-canal simultáneo
- `channel_buffers: dict[str, deque]` — un buffer por campo detectado.
- `channel_lines: dict[str, Line2D]` — una línea matplotlib por canal activo.
- `active_channels: set[str]` — canales visibles, controlados por checkboxes.
- `_update_plot_frame` itera sobre todos los canales activos.
- `_update_stats` muestra estadísticas de cada canal con su color.
- `_channel_color(field)` asigna colores consistentes de la paleta `_CHANNEL_COLORS`.
- En la UI: `QListWidget` con checkboxes reemplaza el `QComboBox` de campo único.

#### 2. Historial de sesión + buffer durante pausa
- `_session_times: list` y `_session_data: dict[str, list]` acumulan toda la sesión.
- `_pause_queue: list[(timestamp, dict)]` almacena datos recibidos mientras se pausa.
- Al reanudar, `_on_pause_toggled` vuelca la cola con timestamps originales
  (sin saltos temporales en el gráfico).
- Exportación pregunta: "Sesión completa" vs "Ventana visible".
- CSV multi-columna: `Tiempo(s) | canal1 | canal2 | …`

#### 3. Auto-reconexión
- `_reconnect_timer: QTimer(self)` arranca con intervalo de 3 s al detectar error serial.
- `_try_reconnect()` intenta `connect_serial` con el último puerto/baudrate conocido.
- Máximo `_max_reconnect_attempts = 10` intentos (30 s total).
- Se cancela automáticamente al reconectar o al hacer `disconnect_serial` manual.
- `_last_port` se limpia en desconexión manual para evitar reconexión no deseada.

#### 4. Envío bidireccional al dispositivo
- `serial_reader.write_data(data: str) -> bool` — envía bytes bajo `self.lock`.
- UI: grupo "Enviar al dispositivo" con `QLineEdit` + selector de terminador + botón.
- `Enter` en el campo también dispara el envío.
- Terminadores disponibles: `\n (LF)`, `\r\n (CRLF)`, `\r (CR)`, sin terminador.
- `send_btn` habilitado/deshabilitado según estado de conexión.

**Otros cambios internos:**
- `_process_data_point(timestamp, data_dict)` centraliza la escritura en buffers.
- `handle_raw_data` detecta y registra campos nuevos automáticamente.
- `_on_max_points_changed` redimensiona todos los `channel_buffers` en sincronía.
- `clear_plot` limpia también sesión, cola de pausa y líneas matplotlib.
- Baudrates ampliados: se agregaron 1200, 2400 y 4800 para sensores lentos.

---

## 5. Registro de bugs

| ID  | Descripción | Encontrado en | Estado en v5 | Notas |
|-----|-------------|:---:|:---:|-------|
| B01 | `toggle_pause` fuera de la clase (indentación 0) | v1 | ✅ Corregido | `fixed` lo corrigió parcialmente |
| B02 | `closeEvent` fuera de la clase | v1, fixed | ✅ Corregido | No guardaba config ni desconectaba serial |
| B03 | Código sin indentación en `__init__` y `setup_ui` | v2 | ✅ N/A | v2 inutilizable; v3 reescribió limpio |
| B04 | `serial_reader.py` importa `list_ports` y `datetime` sin usarlos | v1–v3 | ✅ Corregido | Imports eliminados en v4/v5 |
| B05 | `bool` para controlar hilo serial (race condition potencial) | v1–v4 | ✅ Corregido | Reemplazado por `threading.Event` |
| B06 | `closeEvent` no detiene el timer ni la animación | v1, fixed | ✅ Corregido | v5 detiene ambos correctamente |
| B07 | `show_error` llama `QMessageBox` bloqueante por errores seriales | v1–v4 | ✅ Corregido | `on_serial_error` solo loguea |
| B08 | QSettings con keys distintas entre v3 y v4 | v4 | ✅ Corregido | v5 restaura keys de v1–v3 |
| B09 | `QTimer()` sin padre en v4 | v4 | ✅ Corregido | `QTimer(self)` en v5 |
| B10 | `cache_frame_data=True` (default) — memory leak en sesiones largas | v3, v4 | ✅ Corregido | `cache_frame_data=False` en v5 |
| B11 | `refresh_com_ports` corre mientras está conectado | v1–v4 | ✅ Corregido | v5 retorna early si `is_connected()` |
| B12 | Exportación CSV sin avisar que solo exporta N puntos visibles | v1–v4 | ✅ Corregido | Mensaje explícito en log y diálogo |
| B13 | Backend matplotlib `Qt5Agg` — subóptimo para PySide6 moderno | v1–v5 | ⚠️ Pendiente | Ver mejoras futuras |
| B14 | Datos descartados durante pausa sin aviso | v1–v5.0 | ✅ Corregido en v5.1 | Cola `_pause_queue` acumula y vuelca al reanudar |
| B15 | `disconnect()` timeout de 1 s — insuficiente para baudrates lentos | v1–v3 | ✅ Corregido | Aumentado a 2 s en v5 |
| B16 | Sin reconexión automática ante desconexión inesperada | v1–v5.0 | ✅ Corregido en v5.1 | `_reconnect_timer` con 10 intentos cada 3 s |
| B17 | Solo un canal graficado simultáneamente | v1–v5.0 | ✅ Corregido en v5.1 | `channel_buffers` + `channel_lines` multi-canal |
| B18 | Exportación sin historial de sesión completa | v1–v5.0 | ✅ Corregido en v5.1 | `_session_data` acumula todo; exportación pregunta |

---

## 6. Decisiones de arquitectura

### Por qué `Signal(str)` en lugar de `Signal(float)`
El lector serial no debe saber qué formato tiene el dato. Al emitir la línea
cruda, el parseo queda centralizado en `main_window.py`, donde están los
controles de formato. Esto permite soportar CSV, JSON y otros formatos futuros
sin tocar `serial_reader.py`.

### Por qué `threading.Event` en lugar de `bool`
`threading.Event` es la primitiva correcta para señalizar entre hilos en Python.
Aunque el GIL protege operaciones de bool en la práctica, `Event` hace la
intención explícita y es más seguro en versiones futuras del intérprete (GIL
libre en Python 3.13+).

### Por qué `deque(maxlen=N)` en lugar de listas con recorte manual
```python
# Antes (v1-v4): recorte manual en cada punto
if len(self.data_buffer) > self.max_data_points:
    self.data_buffer = self.data_buffer[-self.max_data_points:]

# Ahora (v5): deque descarta automáticamente el dato más antiguo
self.data_buffer = deque(maxlen=self.max_data_points)
self.data_buffer.append(value)  # O(1), sin copias
```

### Por qué separar `on_serial_error` de `show_error`
Los errores seriales pueden ocurrir muchas veces por segundo cuando el
dispositivo se desconecta inesperadamente. Un `QMessageBox` por cada error
bloquea el event loop y apila diálogos que el usuario no puede cerrar.
`on_serial_error` solo registra en el log y rehabilita los botones.
`show_error` con `show_dialog=True` se reserva para errores iniciados
por el usuario (connect, export) y tiene debounce de 3 s.

### Por qué `blit=False` en FuncAnimation
`blit=True` requiere que el artist devuelto sea el único que cambia en el
canvas. Con títulos dinámicos (`ax.set_title`) esto falla en algunos backends
porque el título no está incluido en los artists retornados. `blit=False`
es más lento (~5%) pero correcto en todos los sistemas.

### Por qué conservar la key de QSettings de v3
Cambiar la organización/nombre en QSettings invalida silenciosamente todas
las configuraciones guardadas por el usuario. Si hay una razón de negocio
para cambiarla, se debe hacer con migración explícita.

---

## 7. Limitaciones conocidas (v5)

### L01 — ~~Pérdida de datos durante pausa~~ ✅ Resuelto en v5.1
Los datos se acumulan en `_pause_queue` con su timestamp original.
Al reanudar se incorporan al gráfico sin saltos temporales.

### L02 — Exportación solo exporta ventana visible
El CSV contiene únicamente los últimos `max_data_points` puntos, no toda
la sesión.  
**Workaround**: se informa en el log y en el mensaje del diálogo.  
**Solución futura**: buffer histórico ilimitado (en memoria o en archivo).

### L03 — Backend matplotlib `Qt5Agg`
`Qt5Agg` funciona con PySide6 pero el backend moderno es `QtAgg`
(matplotlib >= 3.5). Con versiones muy recientes puede producir warnings.  
**Solución futura**: detección automática de backend (ver mejoras #F01).

### L04 — ~~Un solo canal graficado simultáneamente~~ ✅ Resuelto en v5.1
Multi-canal implementado con `channel_buffers` y `channel_lines`.
Checkboxes permiten activar/desactivar canales individualmente.

### L05 — ~~Sin reconexión automática~~ ✅ Resuelto en v5.1
Auto-reconexión implementada con `_reconnect_timer` (3 s, 10 intentos).
Se cancela automáticamente al desconectar manualmente.

### L06 — `scan_serial_devices` bloquea la UI
El escaneo de puertos hace `time.sleep` en el hilo principal. Con muchos
puertos o baudrates lentos, la ventana se congela brevemente.  
**Solución futura**: mover el escaneo a un `QThread` o `ThreadPoolExecutor`.

---

## 8. Puntos de mejora para versiones futuras

### F01 — Backend matplotlib adaptativo
```python
import matplotlib
try:
    matplotlib.use('QtAgg')
    from matplotlib.backends.backend_qtagg import (
        FigureCanvasQTAgg as FigureCanvas,
        NavigationToolbar2QT as NavigationToolbar,
    )
except Exception:
    matplotlib.use('Qt5Agg')
    from matplotlib.backends.backend_qt5agg import (
        FigureCanvasQTAgg as FigureCanvas,
        NavigationToolbar2QT as NavigationToolbar,
    )
```

### F02 — Buffer histórico ilimitado (archivo temporal)
Mantener un archivo `.csv` temporal en `tempfile.gettempdir()` que acumule
todos los datos de la sesión. La exportación puede elegir entre "datos
visibles" o "sesión completa".

### F03 — Buffer durante pausa
```python
self._pause_buffer: deque = deque()

def _add_data_point(self, value):
    if self.is_paused:
        self._pause_buffer.append(value)  # acumular
        return
    # Al reanudar: volcar _pause_buffer al gráfico
```

### F04 — Graficar múltiples campos simultáneamente
- Agregar `QListWidget` con selección múltiple para campos.
- Crear una línea matplotlib por campo seleccionado.
- Usar un solo buffer de tiempo y un dict `{campo: deque}`.

### F05 — Reconexión automática
```python
# En on_serial_error, arrancar un QTimer de reintento
self._reconnect_timer = QTimer(self)
self._reconnect_timer.setSingleShot(True)
self._reconnect_timer.timeout.connect(self._try_reconnect)
self._reconnect_timer.start(3000)  # reintentar en 3 s
```

### F06 — `scan_serial_devices` en hilo separado
Usar `QThread` o `concurrent.futures.ThreadPoolExecutor` para que el
escaneo no bloquee la UI. Mostrar un `QProgressDialog` mientras escanea.

### F07 — Modo oscuro
Agregar opción en Menú > Vista > Modo oscuro que cambie:
- `app.setStyle('Fusion')` con paleta oscura.
- Colores del gráfico matplotlib (fondo `#1e1e1e`, líneas más brillantes).

### F08 — Estadísticas avanzadas
Agregar en el panel de estadísticas:
- Desviación estándar.
- Frecuencia de muestreo estimada (puntos/segundo).
- Indicador de pérdida de tramas (líneas que no se pudieron parsear).

### F09 — Zoom con teclado
Atajos de teclado para zoom rápido:
- `Ctrl++` / `Ctrl+-` para escala Y manual.
- `Ctrl+0` para resetear escala a automática.

### F10 — Soporte para tramas con etiqueta clave:valor
Muchos proyectos Arduino envían datos como `"temp:25.4 hum:60\n"`.
Agregar modo de parseo `"Key:Value"` que detecte patrones `palabra:número`.

### F11 — Test de regresión
Agregar `test_serial_reader.py` y `test_parse.py` con `pytest` para
verificar que el parseo de tramas funciona correctamente en todos los formatos,
especialmente al añadir nuevos formatos.

---

## 9. Notas de dependencias

### PySerial
- `serial.tools.list_ports` se usa en `main_window.py` (no en `serial_reader.py`).
- El puerto serial se abre con `timeout=1` para que el hilo no quede bloqueado
  indefinidamente en `read()` si no llegan datos.

### Matplotlib + PySide6
- Matplotlib debe importarse y configurar el backend **antes** de importar
  `pyplot`. De lo contrario puede usar el backend por defecto (TkAgg o Agg)
  y no renderizar en la ventana Qt.
- `FuncAnimation` con `blit=False` y `cache_frame_data=False` es la
  configuración más segura para gráficos en tiempo real.

### PySide6
- `QTextCursor.MoveOperation.End` es la forma correcta del enum en PySide6
  (no `QTextCursor.End` que es PyQt5).
- `QSettings("AngelMaldonado", "SistemaMonitoreoSerial")` guarda en el registro
  de Windows bajo `HKCU\Software\AngelMaldonado\SistemaMonitoreoSerial`.

### Python 3.10+
- Se usa la sintaxis `float | None` para type hints (disponible desde 3.10).
- Si se necesita compatibilidad con 3.9: usar `Optional[float]` de `typing`.

---

*Última actualización: 2026-04-06 — versión v5*
