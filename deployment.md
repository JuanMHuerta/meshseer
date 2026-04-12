# Meshradar Production Deployment

This document describes the production topology Meshradar now expects:

- the dashboard is public and read-only
- `/ws/events` is public
- admin routes stay local to the origin machine
- Cloudflare Tunnel exposes only the public dashboard surface

## Origin layout

Run Meshradar only on loopback:

- `MESHRADAR_BIND_HOST=127.0.0.1`
- `MESHRADAR_BIND_PORT=8000`
- `MESHRADAR_ADMIN_BEARER_TOKEN=<long-random-secret>`

Operational rules:

- Keep the app reachable only from localhost. Do not bind Meshradar directly to a public interface.
- Keep normal inbound firewall policy closed. Cloudflare Tunnel uses outbound connections; the Cloudflare docs recommend blocking unsolicited ingress for a positive security model.
- Use the bearer token only for local admin calls such as `curl` on the machine or over SSH port-forwarding. Do not place this token in browser code, Cloudflare headers, or public tunnel config.

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
- The `path` field supports regular expressions; use it to block `/api/admin/*`, `/docs`, `/redoc`, and `/openapi.json` before requests ever reach Meshradar.
- Validate the tunnel config before rollout:

```bash
cloudflared tunnel ingress validate
cloudflared tunnel ingress rule https://mesh.example.com/api/admin/health
```

The `/api/admin/...` probe should match the `http_status:404` rule, not the app origin.

## Cloudflare settings

Set the public hostname up as a normal proxied application with these expectations:

- WebSockets must be enabled. Cloudflare supports proxied WebSocket connections, but the setting should still be confirmed in the dashboard.
- Expect occasional WebSocket reconnects. Cloudflare documents that WebSocket connections can be terminated during network restarts, so the client must reconnect automatically.
- Do not apply edge caching to the Meshradar hostname. The app is live telemetry, not cacheable static content.
- Keep TLS on the public hostname. Cloudflare terminates TLS at the edge and forwards through the tunnel to the local HTTP origin.

Reference:

- WebSockets support and restart behavior: <https://developers.cloudflare.com/network/websockets/>

## Admin access

Admin traffic is intentionally not part of the public Cloudflare surface.

Use one of these workflows instead:

- SSH into the origin machine and call `http://127.0.0.1:8000/api/admin/...`
- SSH port-forward `127.0.0.1:8000` and call admin routes through the tunnelled localhost session

Every admin request must include:

```http
Authorization: Bearer <MESHRADAR_ADMIN_BEARER_TOKEN>
```

If `MESHRADAR_ADMIN_BEARER_TOKEN` is unset, Meshradar does not mount the admin API at all.

## Production checks

Before exposing the public hostname:

1. Confirm `curl https://mesh.example.com/api/admin/health` returns Cloudflare’s `404` response.
2. Confirm `curl https://mesh.example.com/docs` and `/openapi.json` return `404`.
3. Confirm `curl https://mesh.example.com/api/health` succeeds and does not reveal the database path.
4. Confirm the browser can load the dashboard and sustain websocket reconnects across a `cloudflared` restart.
5. Confirm local admin works only with the configured bearer token.

## Not in this topology

These are intentionally out of scope for the current production design:

- a public admin hostname
- Cloudflare Access protecting admin routes
- Cloudflare service tokens for admin automation

If remote admin is needed later, use a separate admin hostname behind Cloudflare Access and keep the Meshradar bearer-token check in place as a second control.
