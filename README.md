# Sistema de Monitoreo Serial

Aplicación de escritorio para visualizar y registrar datos seriales en tiempo real desde cualquier dispositivo USB/COM — ESP32, Arduino, sensores industriales, PLCs, módulos GPS, y más.

**Desarrollado por Angel Maldonado Fuentes**

---

## Características

| Funcionalidad | Descripción |
|---|---|
| Multi-canal | Grafica todos los campos detectados simultáneamente, cada uno con su color |
| Formatos | Simple (float), CSV y JSON con detección automática de campos |
| Historial de sesión | Acumula todos los datos desde la conexión, exporta sesión completa o ventana visible |
| Buffer en pausa | Los datos no se pierden al pausar — se incorporan al reanudar |
| Auto-reconexión | Reintenta la conexión automáticamente si el dispositivo se desconecta |
| Bidireccional | Envía comandos o texto al dispositivo desde la interfaz |
| Configuración persistente | Recuerda puerto, baudrate, escala y geometría de la ventana |

---

## Instalación

**Requisitos:** Python 3.10+ (probado con 3.11.5 / Anaconda)

```bash
git clone https://github.com/LegnA12/sistema-monitoreo-serial.git
cd sistema-monitoreo-serial
pip install -r requirements.txt
python main.py
```

> Si usas un entorno virtual:
> ```bash
> python -m venv venv
> venv\Scripts\activate
> pip install -r requirements.txt
> ```

---

## Formatos de trama soportados

```
Simple:  25.4
CSV:     25.4,60.1,1013.2
JSON:    {"temp": 25.4, "hum": 60.1, "presion": 1013.2}
```

Los campos se detectan automáticamente al recibir el primer dato.  
También puedes definir una plantilla manual desde el panel de control.

---

## Estructura del proyecto

```
├── main.py            # Punto de entrada
├── serial_reader.py   # Lectura/escritura serial en hilo separado
├── main_window.py     # Interfaz gráfica, parseo y lógica
├── requirements.txt   # Dependencias con versiones verificadas
├── CONTEXTO.md        # Documentación técnica completa del proyecto
└── CLAUDE.md          # Contexto para asistente IA (Claude Code)
```

> El historial de versiones, registro de bugs, decisiones de arquitectura
> y puntos de mejora futura están documentados en [`CONTEXTO.md`](CONTEXTO.md).

---

## Stack

- [PySide6](https://doc.qt.io/qtforpython/) — Interfaz gráfica
- [Matplotlib](https://matplotlib.org/) — Gráficos en tiempo real
- [PySerial](https://pyserial.readthedocs.io/) — Comunicación serial
