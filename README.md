# Meshradar

Public LongFast mesh view from the perspective of your receiver node.

The UI shows:

- a live map of node locations heard on the primary channel
- a read-only broadcast chat feed for LongFast text messages
- a recent LongFast packet activity table

Set `MESHRADAR_LOCAL_NODE_NUM` if you want the UI and API to identify which node is the point of view. If it is not set, Meshradar will try to detect the local node number from the connected Meshtastic interface.

Meshradar treats the receiver's primary channel as LongFast and filters packets and nodes to that scope.

Run the server with `./start.sh`. Meshradar loads `.env` on startup if it exists, so local defaults can live there. Use `.env.example` as the committed template, or override bind host, port, database path, Meshtastic host, local node, and autotrace settings with the corresponding `MESHRADAR_*` environment variables before starting it.

## Headless Preview

For a browser-renderable demo without live radio hardware:

1. Install the dev environment: `uv sync --extra dev`
2. Install Chromium for Playwright once: `uv run --extra dev playwright install chromium`
3. Render the seeded demo dashboard and save screenshots:

```bash
uv run --extra dev python scripts/headless_capture.py
```

This writes a full dashboard screenshot to `artifacts/headless/dashboard.png` and a map panel crop to `artifacts/headless/map-panel.png`.

If you want to keep the seeded demo app running for manual inspection, start it with:

```bash
uv run meshradar-demo --port 8765
```

Then point the capture script at that URL or any other Meshradar instance:

```bash
uv run --extra dev python scripts/headless_capture.py --url http://127.0.0.1:8765/
```

## Passive Data

Meshradar persists:

- all received primary-channel packets in SQLite
- the latest known state for each heard node
- passive route data that can be extracted from observed `TRACEROUTE_APP` and route-reply packets

The map only draws route lines when Meshradar has a usable ordered hop list. If a packet only contains an ACK or an error without route hops, the map will stay line-free for that attempt.

## Auto-Traceroute

Auto-traceroute is the one intentional active backend feature. The portal remains read-only for users, but the backend can be told to send controlled traceroute requests through the connected radio.

When enabled, Meshradar:

- sends at most one traceroute every `MESHRADAR_AUTOTRACE_INTERVAL_SECONDS`
- only targets recent RF nodes heard within `MESHRADAR_AUTOTRACE_TARGET_WINDOW_HOURS`
- excludes the local node
- excludes nodes marked `via_mqtt`
- excludes nodes without a known `hops_away`
- skips any node that had a local traceroute attempt in the last `MESHRADAR_AUTOTRACE_COOLDOWN_HOURS`
- retries `ack_only` nodes with stepped backoff: `6h`, `12h`, `18h`, then `24h` using `MESHRADAR_AUTOTRACE_ACK_ONLY_COOLDOWN_HOURS` as the base step
- also skips nodes that already produced an observed route in that same cooldown window
- derives the hop limit from `hops_away`, capped at `7`

Default settings:

- `MESHRADAR_AUTOTRACE_ENABLED=false`
- `MESHRADAR_AUTOTRACE_INTERVAL_SECONDS=300`
- `MESHRADAR_AUTOTRACE_TARGET_WINDOW_HOURS=24`
- `MESHRADAR_AUTOTRACE_COOLDOWN_HOURS=24`
- `MESHRADAR_AUTOTRACE_ACK_ONLY_COOLDOWN_HOURS=6`
- `MESHRADAR_AUTOTRACE_RESPONSE_TIMEOUT_SECONDS=20`

Auto-traceroute now respects `MESHRADAR_AUTOTRACE_ENABLED` during process startup. The runtime API still works for turning it on or off after boot, but it is mounted only when `MESHRADAR_ADMIN_BEARER_TOKEN` is set. The repository `.env` and `.env.example` set it to `true` as the local default template.

### Runtime API

Endpoints:

- `GET /api/admin/health`
- `GET /api/admin/mesh/autotrace`
- `POST /api/admin/mesh/autotrace/enable`
- `POST /api/admin/mesh/autotrace/disable`
- `GET /api/admin/mesh/links`
- `GET /api/admin/nodes`
- `GET /api/admin/packets/{packet_id}`

Example:

```bash
export MESHRADAR_ADMIN_BEARER_TOKEN='replace-me'

curl -H "Authorization: Bearer ${MESHRADAR_ADMIN_BEARER_TOKEN}" \
  http://127.0.0.1:8000/api/admin/mesh/autotrace

curl -X POST \
  -H "Authorization: Bearer ${MESHRADAR_ADMIN_BEARER_TOKEN}" \
  http://127.0.0.1:8000/api/admin/mesh/autotrace/enable

curl -X POST \
  -H "Authorization: Bearer ${MESHRADAR_ADMIN_BEARER_TOKEN}" \
  http://127.0.0.1:8000/api/admin/mesh/autotrace/disable
```

These endpoints are intended for a protected local-only surface. Meshradar requires `Authorization: Bearer <token>` on every admin request and does not mount the admin routes unless `MESHRADAR_ADMIN_BEARER_TOKEN` is configured. The public dashboard does not expose auto-traceroute status or controls.

### Status Model

`GET /api/admin/mesh/autotrace` returns:

- whether the scheduler is enabled and running
- the resolved local node number
- the interval, cooldown, target window, and response timeout
- the shorter `ack_only` retry cooldown
- the current number of eligible targets
- the last attempt
- a recent attempt list

Each attempt is recorded in the `traceroute_attempts` table with request time, completion time, hop limit, status, request packet id, response packet id, and optional detail text.

Attempt statuses:

- `success`: Meshradar received a traceroute or route-reply payload with usable route data
- `ack_only`: the radio responded, but only with a routing ACK and no route payload
- `no_route`: the radio responded with a routing error such as `NO_ROUTE`
- `timeout`: no response arrived before the configured timeout
- `error`: the send path or response decoding failed unexpectedly

A failed attempt still enters cooldown. This is intentional so the scheduler stays conservative and does not hammer the mesh.

### Route Visibility Caveat

`success` means Meshradar saw a route-bearing reply and can usually feed the traceroute map. `ack_only` means the radio responded, but there was no route payload to extract, so no map line will appear even though the attempt itself was recorded successfully enough to count for cooldown.

Production deployment notes for the public dashboard plus local-only admin topology live in [deployment.md](/home/juan/dev/meshradar/deployment.md).
