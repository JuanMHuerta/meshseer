# Production Readiness Checklist

Status: not ready for internet-reachable production in current form.

## High severity

- [x] Add authentication and authorization for all non-public routes. Non-public routes now live under `/api/admin/*`, require a bearer token, and are not mounted unless `MESHRADAR_ADMIN_BEARER_TOKEN` is set. Public dashboard routes and `/ws/events` remain intentionally anonymous. See [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py:187) and [src/meshradar/config.py](/home/juan/dev/meshradar/src/meshradar/config.py:29).
- [ ] Protect the Cloudflare Tunnel with Cloudflare Access default-deny. Do not expose this app as a public tunnel without identity enforcement.
- [x] Harden `/ws/events`. It now enforces same-origin admission, caps concurrent subscribers, uses bounded per-client queues, and disconnects slow consumers instead of buffering without bound. See [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py:348) and [src/meshradar/events.py](/home/juan/dev/meshradar/src/meshradar/events.py:11).

## Medium severity

- [x] Disable `/docs`, `/redoc`, and `/openapi.json` in production. FastAPI now disables them when `MESHRADAR_ENV=production`. See [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py:160) and [tests/test_main.py](/home/juan/dev/meshradar/tests/test_main.py:33).
- [x] Remove sensitive operational detail from `/api/health`. The public health response now omits the SQLite path and collector detail text; detailed health moved to the admin API. See [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py:226).
- [x] Reduce data exposure from API responses. Public packet payloads now expose only UI-facing summary fields plus a derived path summary, and `/api/chat` uses a dedicated sender/path summary payload instead of the general packet schema. See [src/meshradar/public_api.py](/home/juan/dev/meshradar/src/meshradar/public_api.py) and [src/meshradar/app.py](/home/juan/dev/meshradar/src/meshradar/app.py).
- [ ] Change the bind default from `0.0.0.0` to `127.0.0.1` for a tunnel-based deployment. Current defaults expose the process on all interfaces. See [src/meshradar/config.py](/home/juan/dev/meshradar/src/meshradar/config.py:47) and [start.sh](/home/juan/dev/meshradar/start.sh:19).
- [ ] Add security response headers and a production CSP. Current responses do not set common headers such as `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, or app-level cache policy.
- [x] Validate websocket origin and add connection limits, idle timeouts, and backpressure handling.
- [ ] Add audit logging for auth decisions, websocket connects/disconnects, autotrace enable/disable events, and repeated failed access attempts. The codebase currently has almost no application logging. See [src/meshradar/startup.py](/home/juan/dev/meshradar/src/meshradar/startup.py:70).
- [ ] Review third-party frontend asset loading. The page pulls fonts from Google Fonts and Leaflet CSS/JS from `unpkg`, which introduces external dependency and supply-chain availability risk for a locally hosted app. See [src/meshradar/static/index.html](/home/juan/dev/meshradar/src/meshradar/static/index.html:7).

## Performance and availability

- [ ] Add retention and pruning for `packets`, `node_metric_history`, and `traceroute_attempts`. Data currently only grows. See [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:383) and [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1282).
- [ ] Optimize whole-table analytics before long-term use. `get_mesh_summary`, `get_mesh_routes`, `list_nodes_roster`, and autotrace eligibility/status logic scan and aggregate large portions of the database. See [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:811), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1054), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1559), [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py:1813), [src/meshradar/autotrace.py](/home/juan/dev/meshradar/src/meshradar/autotrace.py:157).
- [x] Reduce client-side refetch storms. Live websocket events now update packet, chat, and roster state locally in the browser, while summary, routes, and selected-node detail use debounced single-flight refreshes instead of immediate fanout reloads. See [src/meshradar/static/app.js](/home/juan/dev/meshradar/src/meshradar/static/app.js).
- [x] Enable SQLite production tuning for concurrent read/write load. Repository-managed connections now force `WAL` mode at startup and apply a fixed `busy_timeout` on every connection. See [src/meshradar/storage.py](/home/juan/dev/meshradar/src/meshradar/storage.py).

## Dead code and cleanup

- [ ] Remove or fix stale screenshot scripts. They reference DOM IDs that no longer exist and are effectively dead. See [scripts/screenshot.py](/home/juan/dev/meshradar/scripts/screenshot.py:23) and [scripts/screenshot.js](/home/juan/dev/meshradar/scripts/screenshot.js:14).
- [x] Review unused API endpoints and narrow the public surface. `/api/mesh/links`, `/api/nodes`, and `/api/packets/{packet_id}` are no longer part of the anonymous public surface and now live behind `/api/admin/*`.

## Validation notes

- Test suite passed during review: `64 passed`.
- Coverage report during review: `84%`.
- No obvious SQL injection, command execution, or stored-XSS issue was found in the current code paths reviewed.
