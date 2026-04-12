# Production Readiness Checklist

Status: not ready for internet-reachable production in current form.

## High severity

- [x] Add authentication and authorization for all non-public routes. Non-public routes now live under `/api/admin/*`, require a bearer token, and are not mounted unless `MESHRADAR_ADMIN_BEARER_TOKEN` is set. Public dashboard routes and `/ws/events` remain intentionally anonymous. See [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py:187) and [src/meshradar/config.py](/home/juan/dev/meshradar/src/meshradar/config.py:29).
- [ ] Protect the Cloudflare Tunnel with Cloudflare Access default-deny. Do not expose this app as a public tunnel without identity enforcement.
- [ ] Harden `/ws/events`. It currently accepts every connection and uses unbounded per-client queues, which creates a memory-exhaustion and connection-flooding risk. See [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py:302) and [src/meshradar/events.py](/home/juan/dev/meshradar/src/meshradar/events.py:10).

## Medium severity

- [ ] Disable `/docs`, `/redoc`, and `/openapi.json` in production. They are reachable by default and reveal the full API surface.
- [x] Remove sensitive operational detail from `/api/health`. The public health response now omits the SQLite path and collector detail text; detailed health moved to the admin API. See [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py:226).
- [ ] Reduce data exposure from API responses. Packet and chat endpoints return `raw_json`, `payload_base64`, node IDs, and other low-level radio metadata that the UI does not need. See [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1402), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1462), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1491), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1504).
- [ ] Change the bind default from `0.0.0.0` to `127.0.0.1` for a tunnel-based deployment. Current defaults expose the process on all interfaces. See [src/meshradar/config.py](/home/juan/dev/meshradar/src/meshradar/config.py:47) and [start.sh](/home/juan/dev/meshradar/start.sh:19).
- [ ] Change autotrace defaults to off in committed templates. Both the repo `.env` and `.env.example` enable it today. See [.env.example](/home/juan/dev/meshradar/.env.example:1) and [.env](/home/juan/dev/meshradar/.env:1).
- [ ] Add security response headers and a production CSP. Current responses do not set common headers such as `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, or app-level cache policy.
- [ ] Validate websocket origin and add connection limits, idle timeouts, and backpressure handling.
- [ ] Add audit logging for auth decisions, websocket connects/disconnects, autotrace enable/disable events, and repeated failed access attempts. The codebase currently has almost no application logging. See [src/meshradar/startup.py](/home/juan/dev/meshradar/src/meshradar/startup.py:70).
- [ ] Review third-party frontend asset loading. The page pulls fonts from Google Fonts and Leaflet CSS/JS from `unpkg`, which introduces external dependency and supply-chain availability risk for a locally hosted app. See [src/meshradar/static/index.html](/home/juan/dev/meshradar/src/meshradar/static/index.html:7).

## Performance and availability

- [ ] Add retention and pruning for `packets`, `node_metric_history`, and `traceroute_attempts`. Data currently only grows. See [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:383) and [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1282).
- [ ] Optimize whole-table analytics before long-term use. `get_mesh_summary`, `get_mesh_routes`, `list_nodes_roster`, and autotrace eligibility/status logic scan and aggregate large portions of the database. See [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:811), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1054), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1559), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1813), [src/meshradar/autotrace.py](/home/juan/dev/meshradar/src/meshradar/autotrace.py:157).
- [ ] Reduce client-side refetch storms. Each live websocket event can trigger extra REST reloads for packets, chat, summary, routes, and node details across every connected browser. See [src/meshradar/static/app.js](/home/juan/dev/meshradar/src/meshradar/static/app.js:2714), [src/meshradar/static/app.js](/home/juan/dev/meshradar/src/meshradar/static/app.js:2723), [src/meshradar/static/app.js](/home/juan/dev/meshradar/src/meshradar/static/app.js:2737), [src/meshradar/static/app.js](/home/juan/dev/meshradar/src/meshradar/static/app.js:2885).
- [ ] Enable SQLite production tuning for concurrent read/write load, at minimum `WAL` mode and a `busy_timeout`.

## Dead code and cleanup

- [ ] Remove or fix stale screenshot scripts. They reference DOM IDs that no longer exist and are effectively dead. See [scripts/screenshot.py](/home/juan/dev/meshradar/scripts/screenshot.py:23) and [scripts/screenshot.js](/home/juan/dev/meshradar/scripts/screenshot.js:14).
- [x] Review unused API endpoints and narrow the public surface. `/api/mesh/links`, `/api/nodes`, and `/api/packets/{packet_id}` are no longer part of the anonymous public surface and now live behind `/api/admin/*`.

## Validation notes

- Test suite passed during review: `64 passed`.
- Coverage report during review: `84%`.
- No obvious SQL injection, command execution, or stored-XSS issue was found in the current code paths reviewed.
