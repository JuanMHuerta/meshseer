# Meshseer Production Deployment

This document describes the production topology Meshseer now expects:

- the dashboard is public and read-only
- `/api/status` is public for lightweight UI bootstrap state
- `/api/health` stays local-only for origin probes
- `/ws/events` is public but same-origin only
- admin routes stay local to the origin machine
- Cloudflare Tunnel exposes only the public dashboard surface

## Origin layout

Run Meshseer only on loopback:

- `MESHSEER_ENV=production`
- `MESHSEER_BIND_HOST=127.0.0.1`
- `MESHSEER_BIND_PORT=8000`
- `MESHSEER_ADMIN_BEARER_TOKEN=<long-random-secret>`

This differs from a development box that you may temporarily expose on a trusted LAN with `MESHSEER_BIND_HOST=0.0.0.0`. Do not carry that override into production.

Operational rules:

- Keep the app reachable only from localhost. Do not bind Meshseer directly to a public interface.
- Production mode disables FastAPI's `/docs`, `/redoc`, and `/openapi.json` routes in the origin app. Keep the Cloudflare path blocks anyway as defense in depth.
- Keep normal inbound firewall policy closed. Cloudflare Tunnel uses outbound connections; the Cloudflare docs recommend blocking unsolicited ingress for a positive security model.
- Use the bearer token only for local admin calls such as `curl` on the machine or over SSH port-forwarding. Do not place this token in browser code, Cloudflare headers, or public tunnel config.
- Meshseer now enables SQLite `WAL` mode and a fixed `busy_timeout` automatically on repository-managed connections. No extra production knob is required for that baseline tuning.
- Meshseer also prunes retained packet, node metric, and traceroute history on startup and during normal write activity. Tune that with the `MESHSEER_RETENTION_*` env vars if your host needs a different retention window.
- The shipped UI vendors its Leaflet and font assets locally. The only remaining external browser dependency is the CARTO/OpenStreetMap basemap tile service.

References:

- Cloudflare Tunnel overview: <https://developers.cloudflare.com/tunnel/>
- Tunnel configuration and ingress matching: <https://developers.cloudflare.com/tunnel/advanced/local-management/configuration-file/>
- Tunnel configuration overview and ingress-blocking note: <https://developers.cloudflare.com/tunnel/configuration/>

## Public tunnel

Use a named `cloudflared` tunnel with a config file similar to:

```yaml
tunnel: <tunnel-id>
credentials-file: /etc/cloudflared/<tunnel-id>.json

ingress:
  - hostname: mesh.example.com
    path: '^/api/health$'
    service: http_status:404
  - hostname: mesh.example.com
    path: '^/api/admin(?:/.*)?$'
    service: http_status:404
  - hostname: mesh.example.com
    path: '^/(docs|redoc|openapi\\.json)$'
    service: http_status:404
  - hostname: mesh.example.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

Important details:

- Rule order matters. `cloudflared` evaluates ingress rules from top to bottom.
- The final catch-all `http_status:404` rule is required.
- The `path` field supports regular expressions; use it to block `/api/health`, `/api/admin/*`, `/docs`, `/redoc`, and `/openapi.json` before requests ever reach Meshseer.
- Preserve the public `Host` header and `X-Forwarded-Proto` so Meshseer can validate websocket origins correctly.
- Validate the tunnel config before rollout:

```bash
cloudflared tunnel ingress validate
cloudflared tunnel ingress rule https://mesh.example.com/api/admin/health
```

The `/api/admin/...` and `/api/health` probes should match the `http_status:404` rule, not the app origin.

## Cloudflare settings

Set the public hostname up as a normal proxied application with these expectations:

- WebSockets must be enabled. Cloudflare supports proxied WebSocket connections, but the setting should still be confirmed in the dashboard.
- Expect occasional WebSocket reconnects. Cloudflare documents that WebSocket connections can be terminated during network restarts, so the client must reconnect automatically.
- Tune websocket limits with `MESHSEER_WS_MAX_CONNECTIONS`, `MESHSEER_WS_QUEUE_SIZE`, `MESHSEER_WS_SEND_TIMEOUT_SECONDS`, `MESHSEER_WS_PING_INTERVAL_SECONDS`, and `MESHSEER_WS_PING_TIMEOUT_SECONDS` if your expected browser concurrency differs from the defaults.
- Do not apply edge caching to the Meshseer hostname. The app is live telemetry, not cacheable static content.
- Keep TLS on the public hostname. Cloudflare terminates TLS at the edge and forwards through the tunnel to the local HTTP origin.
- Add a WAF custom rule to block requests for this hostname on ports other than `80` and `443`. Cloudflare proxies several alternate HTTP(S) ports by default unless you block them at layer 7.

Reference:

- WebSockets support and restart behavior: <https://developers.cloudflare.com/network/websockets/>

## Admin access

Admin traffic is intentionally not part of the public Cloudflare surface.

Use one of these workflows instead:

- SSH into the origin machine and call `http://127.0.0.1:8000/api/admin/...`
- SSH port-forward `127.0.0.1:8000` and call admin routes through the tunnelled localhost session

Every admin request must include:

```http
Authorization: Bearer <MESHSEER_ADMIN_BEARER_TOKEN>
```

If `MESHSEER_ADMIN_BEARER_TOKEN` is unset, Meshseer does not mount the admin API at all.

## Production checks

Before exposing the public hostname:

1. Confirm `curl https://mesh.example.com/api/admin/health` returns Cloudflare’s `404` response.
2. Confirm `curl https://mesh.example.com/docs`, `/redoc`, and `/openapi.json` return `404`.
3. Confirm `curl https://mesh.example.com/api/health` returns Cloudflare's `404` response.
4. Confirm `curl https://mesh.example.com/api/status` succeeds.
5. Confirm the browser can load the dashboard and sustain websocket reconnects across a `cloudflared` restart.
6. Confirm local admin works only with the configured bearer token.

## Not in this topology

These are intentionally out of scope for the current production design:

- a public admin hostname
- Cloudflare Access protecting admin routes
- Cloudflare service tokens for admin automation

If remote admin is needed later, use a separate admin hostname behind Cloudflare Access and keep the Meshseer bearer-token check in place as a second control.
