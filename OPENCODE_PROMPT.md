# Dota 2 Auto-Armlet — Prompt para OpenCode

## Contexto
- Proyecto: Auto-Armlet para Dota 2 usando Game State Integration (GSI) oficial de Valve.
- Plataforma objetivo: Linux (Ubuntu/Debian/Arch).
- No uses Wine/Proton para esto: Dota 2 tiene build nativo Linux y GSI funciona igual.
- No se modifica memoria del juego ni se inyectan DLLs. Solo se lee JSON por HTTP local y se simula input de teclado.

## Requisitos funcionales
1. Servidor HTTP que escucha POST en `http://127.0.0.1:3000/`.
2. Parseo del payload GSI de Dota 2 (`hero.health`, `hero.max_health`, `hero.items`, `abilities`).
3. Detección del slot de Armlet en el inventario.
4. Lógica de activación:
   - Si `health < threshold` (por defecto 25% del HP máximo)
   - Y el Armlet está fuera de cooldown
   - Presionar tecla configurable (por defecto `x`)
   - Esperar `ARMELT_DURATION` segundos (por defecto 3.5)
   - Presionar tecla nuevamente para apagar
5. **Modo dry-run** (por defecto): solo loguea la acción que tomaría, no envía input real.
6. Toggle por variable de entorno o flag CLI para activar el modo producción.
7. Logging estructurado: timestamp, HP, max_hp, armlet_status, acción.
8. Health check endpoint `GET /health` para verificar que el servidor está vivo.

## Estructura del proyecto
```
/home/yura/armlet-gsi/
├── README.md
├── requirements.txt
├── config.py
├── server.py
├── armlet_logic.py
├── input_sim.py
├── main.py
└── tests/
    └── test_armlet_logic.py
```

## Detalles técnicos
- Python 3.12+
- Usar `fastapi` + `uvicorn` para el servidor HTTP.
- Usar `pydantic` para schemas del payload GSI.
- Usar `keyboard` o `pynput` para simulación de input en Linux.
  - Importante: en Linux, `keyboard` puede requerir sudo o permisos de lectura/escritura en `/dev/uinput`.
  - Documentar esto claramente en README.
- No usar `input()` ni interactive prompts en el servidor. Solo logs a stdout y archivo.
- El archivo de log se escribe en `armlet.log` (rotar si supera 10MB).
- Configuración por variables de entorno con defaults razonables:
  - `ARMLET_THRESHOLD` (float, 0.0-1.0, default 0.25)
  - `ARMLET_KEY` (str, default "x")
  - `ARMLET_DURATION` (float, default 3.5)
  - `DRY_RUN` (bool, default true)
  - `GSI_PORT` (int, default 3000)
  - `LOG_FILE` (str, default "armlet.log")

## Esquema GSI mínimo esperado
```json
{
  "hero": {
    "health": 180,
    "max_health": 850,
    "items": [
      {"item_name": "item_armlet", "cooldown": 0},
      {"item_name": "item_boots", "cooldown": 0}
    ]
  }
}
```

Nota: el schema real de Dota 2 GSI puede variar. Implementar parsing defensivo con `.get()` y defaults. Si el campo no existe, loguear warning y continuar sin crashear.

## Testing
- Escribir tests unitarios para `armlet_logic.py` cubriendo:
  - HP por encima del umbral → no activar
  - HP por debajo del umbral + Armlet lista → activar
  - HP por debajo + Armlet en cooldown → no activar
  - Dry-run vs producción
- No es necesario testear el servidor HTTP completo, solo la lógica.
- No es necesario testear `input_sim.py` en Linux real, solo mocks.

## Reglas importantes
1. No agregar features extra no pedidas (no ESP, no maphack, no aimbot).
2. No hardcodear paths de Steam. Todo configuración relativa o por env vars.
3. Documentar en README.md: cómo configurar GSI en Dota 2 launch options y cfg.
4. Manejar graceful shutdown (SIGTERM) para cerrar el servidor sin dejar hilos colgados.
5. Código limpio, type hints donde corresponda, docstrings en funciones públicas.

## Entregable
- Código funcional en `/home/yura/armlet-gsi/`
- README.md con setup, configuración y troubleshooting
- requirements.txt
- tests/
