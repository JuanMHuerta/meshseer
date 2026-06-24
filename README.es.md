# Meshseer

[English](README.md) | [Español](README.es.md)

[![Tests](https://github.com/JuanMHuerta/meshseer/actions/workflows/tests.yml/badge.svg)](https://github.com/JuanMHuerta/meshseer/actions/workflows/tests.yml) [![Release](https://img.shields.io/github/v/release/JuanMHuerta/meshseer)](https://github.com/JuanMHuerta/meshseer/releases)

Meshseer es una vista web del tráfico LongFast de un receptor Meshtastic. Muestra lo que un receptor escuchó en el canal primario: mapa de nodos, chat broadcast, paquetes recientes y datos pasivos de rutas.

Pruébalo:

- Sitio en vivo: <https://meshseer.nemexix.com/>
- Imagen de contenedor: `ghcr.io/juanmhuerta/meshseer`

[![Panel de Meshseer](docs/images/meshseer-dashboard.png)](https://meshseer.nemexix.com/)

## Alcance Actual

- solo perspectiva del receptor; no es una vista autoritativa de toda la mesh
- solo canal primario
- hoy solo interfaz TCP de Meshtastic
- la UI pública es solo lectura
- auto-traceroute es opcional, solo local, y está deshabilitado por defecto
- cuando auto-traceroute está habilitado, los paquetes de posición recientes pueden subir la prioridad de tracing de un nodo, pero los envíos siguen limitados por intervalo
- los assets del frontend están vendorizados localmente; los tiles del mapa base por defecto siguen viniendo de CARTO/OpenStreetMap

## Inicio Rápido Con Docker

Requisitos:

- Docker con soporte de Compose
- un nodo Meshtastic accesible por TCP, normalmente en el puerto `4403`

1. Copia la plantilla de entorno:

```bash
cp .env.example .env
```

2. Edita `.env` y configura al menos:

```dotenv
MESHSEER_MESHTASTIC_HOST=192.168.1.50
MESHSEER_MESHTASTIC_PORT=4403
MESHSEER_ENV=production
```

Opcionalmente elige el tema UI por defecto:

```dotenv
MESHSEER_UI_DEFAULT_STYLE=amber-monochrome
```

3. Descarga la imagen publicada:

```bash
docker pull ghcr.io/juanmhuerta/meshseer:latest
```

4. Inicia Meshseer:

```bash
docker run --name meshseer \
  --env-file .env \
  -e MESHSEER_BIND_HOST=0.0.0.0 \
  -e MESHSEER_BIND_PORT=8000 \
  -e MESHSEER_DB_PATH=/data/meshseer.db \
  -p 127.0.0.1:8000:8000 \
  -v meshseer-data:/data \
  --restart unless-stopped \
  -d ghcr.io/juanmhuerta/meshseer:latest
```

5. Abre `http://127.0.0.1:8000/`

6. Chequeo opcional:

```bash
curl http://127.0.0.1:8000/api/status
```

Notas:

- El contenedor guarda datos SQLite en el volumen Docker `meshseer-data`.
- El contenedor escucha internamente en `0.0.0.0:8000` y se publica en `127.0.0.1:8000` por defecto.
- Si quieres rutas admin solo locales, configura también `MESHSEER_ADMIN_BEARER_TOKEN` en `.env`.
- El soporte Docker actualmente asume Meshtastic TCP. USB serial passthrough y BLE no están implementados.
- Si prefieres Compose, usa [`compose.yaml`](compose.yaml) como punto de partida o reemplaza el paso local `build:` por `image: ghcr.io/juanmhuerta/meshseer:latest`.

## Ejecutar Desde Código Fuente

Requisitos:

- `uv`
- Python `3.13` si administras el intérprete por tu cuenta

Configurar y ejecutar:

```bash
uv sync
cp .env.example .env
./start.sh
```

`start.sh` carga `.env` si existe, crea el directorio de base de datos si hace falta y ejecuta un preflight pequeño antes de iniciar Uvicorn.

Para pruebas en LAN confiable en una máquina de desarrollo, configura:

```dotenv
MESHSEER_BIND_HOST=0.0.0.0
MESHSEER_BIND_PORT=8000
MESHSEER_ENV=development
```

Para producción, deja `MESHSEER_BIND_HOST` sin configurar o configúralo explícitamente como `127.0.0.1`.

## Configuración

Usa [.env.example](.env.example) como base. Las opciones más importantes son:

- `MESHSEER_MESHTASTIC_HOST`: hostname o IP TCP de Meshtastic. Por defecto `localhost`.
- `MESHSEER_MESHTASTIC_PORT`: puerto TCP de Meshtastic. Por defecto `4403`.
- `MESHSEER_DB_PATH`: ruta de la base SQLite. Por defecto `./data/meshseer.db` al ejecutar localmente.
- `MESHSEER_LOCAL_NODE_NUM`: override opcional para el número de nodo receptor mostrado en la UI y API.
- `MESHSEER_ENV`: `development` o `production`. Production deshabilita `/docs`, `/redoc` y `/openapi.json`.
- `MESHSEER_UI_DEFAULT_STYLE`: tema base por defecto de la UI. Valores permitidos: `classic`, `classic-dark`, `amber-monochrome`. Por defecto `amber-monochrome`.
- `MESHSEER_BIND_HOST`, `MESHSEER_BIND_PORT`: configuración de bind HTTP.
- `MESHSEER_ADMIN_BEARER_TOKEN`: habilita la API admin solo local.

Opciones adicionales soportadas:

- ajuste de websocket: `MESHSEER_WS_MAX_CONNECTIONS`, `MESHSEER_WS_QUEUE_SIZE`, `MESHSEER_WS_SEND_TIMEOUT_SECONDS`, `MESHSEER_WS_PING_INTERVAL_SECONDS`, `MESHSEER_WS_PING_TIMEOUT_SECONDS`
- retención y pruning: `MESHSEER_RETENTION_PACKETS_DAYS`, `MESHSEER_RETENTION_NODE_METRIC_HISTORY_DAYS`, `MESHSEER_RETENTION_TRACEROUTE_ATTEMPTS_DAYS`, `MESHSEER_RETENTION_PRUNE_INTERVAL_SECONDS`
- autotrace: `MESHSEER_AUTOTRACE_ENABLED`, `MESHSEER_AUTOTRACE_INTERVAL_SECONDS`, `MESHSEER_AUTOTRACE_TARGET_WINDOW_HOURS`, `MESHSEER_AUTOTRACE_COOLDOWN_HOURS`, `MESHSEER_AUTOTRACE_ACK_ONLY_COOLDOWN_HOURS`, `MESHSEER_AUTOTRACE_RESPONSE_TIMEOUT_SECONDS`
- prioridad de autotrace asistida por posición: `MESHSEER_AUTOTRACE_POSITION_PRIORITY_WINDOW_MINUTES`, `MESHSEER_AUTOTRACE_POSITION_MOVEMENT_DISTANCE_METERS`, `MESHSEER_AUTOTRACE_POSITION_MOVEMENT_COOLDOWN_MINUTES`

## Qué Guarda Meshseer

Meshseer persiste:

- paquetes del canal primario recibidos por el receptor conectado
- el último estado conocido de cada nodo escuchado
- información pasiva de rutas derivada de paquetes `TRACEROUTE_APP` y respuestas de ruta observadas
- registros de intentos de traceroute si auto-traceroute está habilitado

La capa de rutas solo aparece cuando Meshseer tiene una lista ordenada de hops para dibujar. Respuestas solo ACK o con error no crean una ruta visible.

## Demo Y Preview Headless

Si quieres inspeccionar la UI sin hardware de radio en vivo:

1. Instala el entorno de desarrollo:

```bash
uv sync --extra dev
```

2. Instala Chromium para Playwright una vez:

```bash
uv run --extra dev playwright install chromium
```

3. Inicia la app demo con datos:

```bash
uv run meshseer-demo --port 8765
```

4. Captura screenshots:

```bash
uv run --extra dev python scripts/headless_capture.py --url http://127.0.0.1:8765/
```

Esto escribe screenshots en `artifacts/headless/`.

## Auto-Traceroute

Auto-traceroute es la única función backend intencionalmente activa. Permanece deshabilitada por defecto y está pensada para uso protegido, solo local.

Cuando está habilitada, Meshseer:

- envía como máximo un traceroute por intervalo configurado
- apunta solo a nodos RF recientes
- trata paquetes de posición frescos del canal primario como pistas de tracing de alta prioridad, sin enviar inmediatamente
- promueve first-fix, movimiento y updates de posición con ruta vieja por encima de candidatos de fondo
- omite el nodo local, nodos MQTT y nodos sin `hops_away`
- aplica cooldowns después de intentos, incluidos los fallidos
- permite que los retraces por movimiento salten el cooldown largo normal después de una ventana de retry más corta y acotada
- registra cada intento en SQLite con timestamps, hop limit, status y packet IDs cuando están disponibles

Valores por defecto:

- `MESHSEER_AUTOTRACE_ENABLED=false`
- `MESHSEER_AUTOTRACE_INTERVAL_SECONDS=300`
- `MESHSEER_AUTOTRACE_TARGET_WINDOW_HOURS=24`
- `MESHSEER_AUTOTRACE_COOLDOWN_HOURS=24`
- `MESHSEER_AUTOTRACE_ACK_ONLY_COOLDOWN_HOURS=6`
- `MESHSEER_AUTOTRACE_RESPONSE_TIMEOUT_SECONDS=20`
- `MESHSEER_AUTOTRACE_POSITION_PRIORITY_WINDOW_MINUTES=15`
- `MESHSEER_AUTOTRACE_POSITION_MOVEMENT_DISTANCE_METERS=150`
- `MESHSEER_AUTOTRACE_POSITION_MOVEMENT_COOLDOWN_MINUTES=60`

La API admin se monta solo cuando `MESHSEER_ADMIN_BEARER_TOKEN` está configurado.

Endpoints admin:

- `GET /api/admin/health`
- `GET /api/admin/mesh/autotrace`
- `POST /api/admin/mesh/autotrace/enable`
- `POST /api/admin/mesh/autotrace/disable`
- `GET /api/admin/mesh/links`
- `GET /api/admin/nodes`
- `GET /api/admin/packets/{packet_id}`

Ejemplo:

```bash
export MESHSEER_ADMIN_BEARER_TOKEN='replace-me'

curl -H "Authorization: Bearer ${MESHSEER_ADMIN_BEARER_TOKEN}"   http://127.0.0.1:8000/api/admin/mesh/autotrace
```

Estados de intento:

- `success`: se recibió una respuesta con ruta
- `ack_only`: se recibió un ACK de routing sin datos de ruta
- `no_route`: la radio respondió con un error de routing como `NO_ROUTE`
- `timeout`: no llegó respuesta antes del timeout
- `error`: falló inesperadamente el envío o la decodificación de respuesta

`ack_only` cuenta como intento, pero no produce una línea de ruta en el mapa.

## Notas De Producción

- Mantén la app vinculada a loopback en producción.
- `/ws/events` acepta solo conexiones browser same-origin.
- Las rutas admin deben mantenerse solo locales detrás de `MESHSEER_ADMIN_BEARER_TOKEN`.
- El dashboard público usa `/api/status`; `/api/health` es principalmente para health checks locales.

Las notas de deployment del dashboard público y la topología admin solo local están en [deployment.md](deployment.md).

## Licencia

Meshseer tiene licencia `GPL-3.0-only`. Ver [LICENSE](LICENSE).

Los avisos de assets de terceros y los textos de licencia upstream incluidos están en [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
