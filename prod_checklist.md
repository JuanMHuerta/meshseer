# Production Readiness Checklist

Status: not ready for internet-reachable production in current form.

## High severity

- [x] Add authentication and authorization for all non-public routes. Non-public routes now live under `/api/admin/*`, require a bearer token, and are not mounted unless `MESHSEER_ADMIN_BEARER_TOKEN` is set. Public dashboard routes and `/ws/events` remain intentionally anonymous. See [src/meshseer/app.py](/home/juan/dev/meshradar/src/meshseer/app.py:187) and [src/meshseer/config.py](/home/juan/dev/meshradar/src/meshseer/config.py:29).
- [ ] Protect the Cloudflare Tunnel with Cloudflare Access default-deny. Do not expose this app as a public tunnel without identity enforcement.
- [x] Harden `/ws/events`. It now enforces same-origin admission, caps concurrent subscribers, uses bounded per-client queues, and disconnects slow consumers instead of buffering without bound. See [src/meshseer/app.py](/home/juan/dev/meshradar/src/meshseer/app.py:348) and [src/meshseer/events.py](/home/juan/dev/meshradar/src/meshseer/events.py:11).

## Medium severity

- [x] Disable `/docs`, `/redoc`, and `/openapi.json` in production. FastAPI now disables them when `MESHSEER_ENV=production`. See [src/meshseer/app.py](/home/juan/dev/meshradar/src/meshseer/app.py:160) and [tests/test_main.py](/home/juan/dev/meshradar/tests/test_main.py:33).
- [x] Remove sensitive operational detail from `/api/health`. The public health response now omits the SQLite path and collector detail text; detailed health moved to the admin API. See [src/meshseer/app.py](/home/juan/dev/meshradar/src/meshseer/app.py:226).
- [x] Reduce data exposure from API responses. Public packet payloads now expose only UI-facing summary fields plus a derived path summary, and `/api/chat` uses a dedicated sender/path summary payload instead of the general packet schema. See [src/meshseer/public_api.py](/home/juan/dev/meshradar/src/meshseer/public_api.py) and [src/meshseer/app.py](/home/juan/dev/meshradar/src/meshseer/app.py).
- [x] Change the bind default from `0.0.0.0` to `127.0.0.1` for a tunnel-based deployment. Runtime settings and `start.sh` now default to loopback unless the operator overrides them explicitly. See [src/meshseer/config.py](/home/juan/dev/meshradar/src/meshseer/config.py:47) and [start.sh](/home/juan/dev/meshradar/start.sh:19).
- [x] Add security response headers and a production CSP. App responses now emit `Content-Security-Policy`, `X-Content-Type-Options`, `Referrer-Policy`, `Permissions-Policy`, `X-Frame-Options`, and explicit cache policy headers. See [src/meshseer/app.py](/home/juan/dev/meshradar/src/meshseer/app.py).
- [x] Validate websocket origin and add connection limits, idle timeouts, and backpressure handling.
- [x] Add audit logging for auth decisions, websocket connects/disconnects, autotrace enable/disable events, and repeated failed access attempts. Meshseer now emits structured audit logs for those events via the `meshseer.audit` logger. See [src/meshseer/audit.py](/home/juan/dev/meshradar/src/meshseer/audit.py) and [src/meshseer/app.py](/home/juan/dev/meshradar/src/meshseer/app.py).
- [x] Review third-party frontend asset loading. Google Fonts and `unpkg` Leaflet assets are now vendored under `/static/vendor`; the remaining map tile dependency is the CARTO basemap service used by the live map. See [src/meshseer/static/index.html](/home/juan/dev/meshradar/src/meshseer/static/index.html:7) and [src/meshseer/static/vendor](/home/juan/dev/meshradar/src/meshseer/static/vendor).

## Performance and availability

- [x] Add retention and pruning for `packets`, `node_metric_history`, and `traceroute_attempts`. Repository-managed retention now prunes those tables on startup and during normal write activity, then rebuilds derived analytics state. See [src/meshseer/storage.py](/home/juan/dev/meshradar/src/meshseer/storage.py).
- [x] Optimize whole-table analytics before long-term use. Route queries now use indexed time-bounded fetches from the shipped client, autotrace candidate counting/selection moved into SQL, and repository indexes were tightened for primary-channel hot paths. See [src/meshseer/storage.py](/home/juan/dev/meshradar/src/meshseer/storage.py) and [src/meshseer/static/app.js](/home/juan/dev/meshradar/src/meshseer/static/app.js).
- [x] Reduce client-side refetch storms. Live websocket events now update packet, chat, and roster state locally in the browser, while summary, routes, and selected-node detail use debounced single-flight refreshes instead of immediate fanout reloads. See [src/meshseer/static/app.js](/home/juan/dev/meshradar/src/meshseer/static/app.js).
- [x] Enable SQLite production tuning for concurrent read/write load. Repository-managed connections now force `WAL` mode at startup and apply a fixed `busy_timeout` on every connection. See [src/meshseer/storage.py](/home/juan/dev/meshradar/src/meshseer/storage.py).

## Dead code and cleanup

- [x] Remove or fix stale screenshot scripts. The stale Playwright scripts were removed, and the maintained headless capture entrypoint now targets the current DOM. See [scripts/headless_capture.py](/home/juan/dev/meshradar/scripts/headless_capture.py).
- [x] Review unused API endpoints and narrow the public surface. `/api/mesh/links`, `/api/nodes`, and `/api/packets/{packet_id}` are no longer part of the anonymous public surface and now live behind `/api/admin/*`.

## Validation notes

- Test suite passed after repo remediation: `83 passed`.
- Coverage report during review: `84%`.
- No obvious SQL injection, command execution, or stored-XSS issue was found in the current code paths reviewed.
