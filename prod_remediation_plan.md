# Production Remediation Plan

Objective: make Meshradar safe enough for a small internet-reachable deployment on local hardware behind a Cloudflare Tunnel.

Rule: do not expose the app publicly until Phase 1 is complete.

## Phase 1: Access Control and Safe Defaults

Priority: P0

Tasks:
- Put the tunnel behind Cloudflare Access with default-deny and an explicit allow policy for approved users.
- Add server-side access control for all API and websocket routes. Do not rely on the tunnel alone.
- Disable `/docs`, `/redoc`, and `/openapi.json` in production.
- Change bind defaults to `127.0.0.1`.
- Change committed defaults so `MESHRADAR_AUTOTRACE_ENABLED=false`.
- Remove `database.path` and other internal details from `/api/health`.
- Reduce API responses to the fields the UI actually needs.
- Add production security headers and a CSP.

Acceptance criteria:
- Unauthenticated requests to protected endpoints fail.
- Websocket connections require the same trust boundary as HTTP.
- The process is no longer listening on all interfaces by default.
- Docs and schema endpoints are not exposed in production.

## Phase 2: Websocket and Availability Hardening

Priority: P0

Tasks:
- Validate websocket origin.
- Add bounded websocket queues and disconnect slow consumers.
- Add connection limits, idle timeouts, and heartbeat handling.
- Add audit logging for auth decisions, websocket lifecycle, and autotrace state changes.
- Add SQLite production tuning: `WAL`, `busy_timeout`, and startup validation for DB health.
- Add retention and pruning for `packets`, `node_metric_history`, and `traceroute_attempts`.

Acceptance criteria:
- A slow or abusive websocket client cannot grow memory without bound.
- Concurrent reads and writes do not regularly fail with SQLite lock errors.
- Stored data has explicit retention limits.
- Security-relevant actions are visible in logs.

## Phase 3: Performance and Query Reduction

Priority: P1

Tasks:
- Optimize `get_mesh_summary`, `get_mesh_routes`, `list_nodes_roster`, and autotrace eligibility/status logic to avoid whole-table work on hot paths.
- Add tighter route/time limits or cached summaries for expensive analytics.
- Reduce client-side refetch storms after websocket events.
- Prefer incremental UI updates over full reloads of packets, chat, routes, and summaries.

Acceptance criteria:
- Dashboard latency stays stable as the packet table grows.
- Live events do not cause N-clients times M-endpoints fanout behavior.
- Autotrace status remains fast even with a larger history.

## Phase 4: Surface Reduction and Cleanup

Priority: P2

Tasks:
- Remove or fix stale screenshot scripts.
- Review whether `/api/mesh/links`, `/api/nodes`, and `/api/packets/{packet_id}` should remain exposed.
- Vendor or pin third-party frontend assets if you want a more self-contained deployment.
- Run dependency audit tooling as part of release checks.

Acceptance criteria:
- Dead code is removed or clearly marked non-production.
- The public API surface matches actual product needs.
- Frontend boot does not depend on avoidable third-party CDNs.

## Release Validation

Before calling the app production-ready:
- Run the full test suite and add tests for auth, websocket rejection, and production config behavior.
- Verify Cloudflare Access policy enforcement against the real hostname.
- Test websocket abuse cases: many idle clients, slow clients, reconnect loops.
- Test retention and database growth with a seeded large dataset.
- Review logs for sensitive data leakage.

## Suggested Order

1. Complete Phase 1.
2. Complete websocket protections and DB tuning from Phase 2.
3. Complete retention and performance work from Phases 2 and 3.
4. Finish cleanup and release validation in Phase 4.

Linked issue register: [prod_checklist.md](/home/juan/dev/meshradar/prod_checklist.md)
