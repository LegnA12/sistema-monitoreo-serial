# CLAUDE.md — Sistema de Monitoreo Serial v5

Contexto esencial para trabajar en este proyecto.
El análisis completo, historial de bugs y mejoras futuras está en `CONTEXTO.md`.

---

## Qué es este proyecto

Aplicación de escritorio (Python + PySide6 + Matplotlib) para visualizar en
tiempo real datos seriales de microcontroladores (ESP32, Arduino).
Origen: refactorización del archivo monolítico `PLOTTER.py` ubicado en el
directorio padre (`../PLOTTER.py`).

**Versión activa: v5.** Las carpetas `v1`, `fixed`, `v2`, `v3`, `v4` en el
directorio padre son versiones anteriores — no modificarlas.

---

## Cómo ejecutar

```bash
cd sistema_monitoreo_serial_modular_v5
python main.py
```

Dependencias: `pip install PySide6 matplotlib pyserial`

---

## Arquitectura — 3 archivos

```
main.py          → solo arranca QApplication y RealTimePlot
serial_reader.py → SerialReader: lectura serial en hilo daemon
main_window.py   → RealTimePlot: UI, parseo, gráfico, lógica completa
```

### Flujo de datos

```
SerialReader._read_serial_data()  [hilo daemon]
  └─ Signal(str) línea cruda
       └─ RealTimePlot.handle_raw_data()  [hilo Qt]
            └─ _parse_line() → dict {campo: float}
                 └─ _add_data_point(float) → deque
                      └─ FuncAnimation._update_plot_frame()  [100ms]
```

---

## Convenciones del código

| Patrón | Aplicado en |
|--------|-------------|
| Métodos internos con prefijo `_` | `_parse_line`, `_add_data_point`, `_update_plot_frame`, etc. |
| `setup_ui` dividido en helpers `_create_*` | `_create_serial_group()`, `_create_graph_panel()`, etc. |
| Atributos UI declarados como `None` en `__init__` | Antes de llamar `setup_ui()` |
| `blockSignals(True/False)` al limpiar combos | `refresh_com_ports`, `_update_available_fields` |
| `deque(maxlen=N)` para buffers | `data_buffer`, `time_buffer` |
| `threading.Event` para control de hilo | `SerialReader._stop_event` |

---

## Bugs críticos que YA están corregidos — no reintroducir

| Bug | Descripción | Cómo se puede reintroducir accidentalmente |
|-----|-------------|-------------------------------------------|
| B01/B02 | `closeEvent` y métodos de UI fuera de la clase | Pegar código de v1/fixed sin revisar indentación |
| B05 | Usar `bool` para controlar hilo serial | Reemplazar `_stop_event` por un atributo booleano |
| B07 | `QMessageBox` en `on_serial_error` | Llamar `show_error(..., show_dialog=True)` desde señales del hilo |
| B08 | Cambiar key de QSettings | Modificar los strings en `QSettings("AngelMaldonado", "SistemaMonitoreoSerial")` |
| B10 | `cache_frame_data=True` en FuncAnimation | Omitir `cache_frame_data=False` al tocar `start_animation()` |

---

## Señales y conexiones clave

```python
# serial_reader.py emite:
data_received  = Signal(str)   # línea cruda — conectada a handle_raw_data
status_update  = Signal(str)   # conectada a update_status
error_signal   = Signal(str)   # conectada a on_serial_error (NO show_error)

# Importante: error_signal → on_serial_error, no → show_error
# on_serial_error solo loguea; show_error con show_dialog=True
# abre QMessageBox con debounce de 3 s.
```

---

## Formatos de trama soportados

| Formato | Ejemplo de entrada | Campo generado |
|---------|-------------------|----------------|
| Simple  | `25.4\n`          | `{"valor": 25.4}` |
| CSV     | `25.4,60,1013\n`  | `{"ch1": 25.4, "ch2": 60.0, "ch3": 1013.0}` |
| JSON    | `{"temp":25.4,"hum":60}\n` | `{"temp": 25.4, "hum": 60.0}` |

El parseo vive en `_parse_line()` en `main_window.py`.
Para agregar un nuevo formato: añadir rama `if self.current_format == "NuevoFormato"`
en `_parse_line()` y su opción en `format_type_combo`.

---

## Limitaciones activas (documentadas en CONTEXTO.md)

- **L01** — Datos durante pausa se descartan (no hay buffer secundario).
- **L02** — Exportación CSV solo exporta los últimos `max_data_points` puntos.
- **L03** — Backend `Qt5Agg`; para matplotlib ≥ 3.5 migrar a `QtAgg`.
- **L04** — Solo un campo graficado a la vez (no multi-canal).
- **L06** — `scan_serial_devices` bloquea la UI brevemente.

---

## Tareas frecuentes

### Agregar un nuevo formato de trama
1. Añadir la opción en `_create_format_group()` → `format_type_combo.addItems(...)`.
2. Agregar rama en `_parse_line()` que retorne `dict {str: float}`.
3. Documentar en `CONTEXTO.md` sección 8 (mejoras) o 4 (historial).

### Agregar un nuevo campo al panel de control
1. Crear widget en el helper `_create_*` correspondiente.
2. Declarar el atributo como `None` en `__init__` antes de `setup_ui()`.
3. Conectar la señal dentro del mismo helper.

### Persistir un nuevo ajuste
1. Agregar `self.settings.setValue("clave", valor)` en `save_settings()`.
2. Agregar la lectura correspondiente en `load_settings()`.

### Reportar un bug nuevo
Agregar fila en la tabla de `CONTEXTO.md` → sección **5. Registro de bugs**
con estado `⚠️ Pendiente` hasta que se corrija.

---

## Qué NO hacer

- No modificar `serial_reader.py` para que parsee datos — ese es trabajo de `main_window.py`.
- No conectar `error_signal` a `show_error` directamente — usar `on_serial_error`.
- No usar `canvas.draw()` — usar `canvas.draw_idle()` para no bloquear el event loop.
- No poner código de instancia fuera de métodos (bug de v2).
- No cambiar la key de `QSettings` sin implementar migración de datos.
