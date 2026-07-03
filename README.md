# Auto-Armlet GSI — Dota 2

Automatiza el toggle de **Armlet of Mordiggian** usando Game State Integration (GSI) oficial de Valve.

Lee el estado del juego vía HTTP local y simula presión de teclado cuando tu HP baja del umbral configurado.

## Requisitos

- Python 3.12+
- Linux nativo (no Wine/Proton)
- Dota 2 con GSI habilitado

## Instalación

```bash
cd armlet-gsi
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Configuración GSI en Dota 2

### 1. Crear archivo de integración

```
~/.steam/steam/steamapps/common/dota 2 beta/game/dota/cfg/gamestate_integration/gamestate_integration_armlet.cfg
```

Contenido:

```cfg
"Auto-Armlet GSI Configuration"
{
    "uri"               "http://127.0.0.1:3000/"
    "timeout"           "5.0"
    "buffer"            "0.1"
    "throttle"          "0.1"
    "heartbeat"         "30.0"
    "data"
    {
        "provider"      "1"
        "map"           "1"
        "hero"          "1"
        "items"         "1"
        "abilities"     "1"
    }
}
```

### 2. Launch option en Steam

Añadir a Dota 2 → Propiedades → Opciones de inicio:

```
-gamestateintegration
```

## Variables de entorno

| Variable | Default | Descripción |
|---|---|---|
| `ARMLET_THRESHOLD` | `0.25` | Umbral de HP (0.0–1.0) para activar Armlet |
| `ARMLET_KEY` | `x` | Tecla para toggle de Armlet |
| `ARMLET_DURATION` | `3.5` | Segundos antes de desactivar Armlet |
| `DRY_RUN` | `true` | `true` = solo loguea; `false` = envía input real |
| `GSI_PORT` | `3000` | Puerto del servidor HTTP |
| `LOG_FILE` | `armlet.log` | Archivo de log (rota cada 10MB) |

## Uso

```bash
# Dry-run (default)
python main.py

# Producción (envía input real)
DRY_RUN=false python main.py

# Puerto y umbral personalizados
GSI_PORT=4000 ARMLET_THRESHOLD=0.30 python main.py
```

### Endpoints

- `POST http://127.0.0.1:3000/` — Recibe payload GSI de Dota 2
- `GET http://127.0.0.1:3000/health` — Health check

## Simulación de teclado en Linux

`pynput` se usa para simular presión de teclas. Por defecto usa el backend `xorg` (funciona sin `sudo` en X11).

### Para Wayland o sin X11

```bash
# 1. Crear regla udev
echo 'KERNEL=="uinput", MODE="0660", GROUP="input"' | sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm trigger

# 2. Agregar usuario a grupos
sudo usermod -a -G input $USER
sudo usermod -a -G tty $USER

# 3. Cargar módulo uinput al inicio
echo "uinput" | sudo tee /etc/modules-load.d/uinput.conf

# 4. Cerrar sesión y volver a entrar, luego ejecutar:
PYNPUT_BACKEND_KEYBOARD=uinput PYNPUT_BACKEND_MOUSE=dummy python main.py
```

## Tests

```bash
pytest tests/ -v
```

## Estructura del proyecto

```
├── README.md
├── requirements.txt
├── config.py          # Config vía variables de entorno
├── server.py          # FastAPI server (POST /, GET /health)
├── armlet_logic.py    # Lógica de activación/desactivación
├── input_sim.py       # Abstracción de input (pynput)
├── main.py            # Punto de entrada + logging + graceful shutdown
└── tests/
    └── test_armlet_logic.py
```

## Troubleshooting

**"pynput no funciona sin sudo"**: Seguir los pasos de la sección "Para Wayland o sin X11".

**Dota 2 no envía datos**: Verificar que el archivo `.cfg` termina en `gamestate_integration_*.cfg` y está en la carpeta correcta. Verificar launch option `-gamestateintegration`.

**El servidor no arranca**: Verificar que el puerto 3000 no esté ocupado con `ss -tlnp | grep 3000`.

**Armlet no se togglea**: Verificar que la tecla configurada (`ARMLET_KEY`) es la correcta para tu bind de Armlet en Dota 2.
