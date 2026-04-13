# Meshseer on Proxmox

This is the recommended deployment shape for this app on Proxmox:

- run Meshseer in a small Debian 12 LXC
- keep Meshseer bound to `127.0.0.1:8000`
- run `cloudflared` in the same container
- expose only `meshseer.nemexix.com` through the tunnel
- keep admin routes local-only and use SSH for admin access

## Why This Shape

Meshseer is a single FastAPI process with:

- a built-in static frontend
- a websocket endpoint at `/ws/events`
- a local SQLite database
- an outbound TCP dependency to a Meshtastic host

That makes Docker unnecessary unless you already standardize on it. A plain `systemd` service inside an LXC is simpler, easier to debug, and fits SQLite well.

Use a VM instead of an LXC only if you plan to attach radio hardware directly over USB or you need a stricter isolation boundary.

## Recommended Proxmox Container

- Debian 12
- unprivileged LXC
- 1 vCPU
- 512 MB RAM minimum, 1 GB preferred
- 4 GB disk minimum, 8+ GB preferred if you want longer SQLite retention
- static DHCP lease or fixed IP on your LAN

Network requirements:

- outbound internet access for `cloudflared`
- outbound TCP access to your Meshtastic host on port `4403` unless you override it
- no inbound port-forwarding required

## Suggested Layout

- app checkout: `/opt/meshseer/app`
- app user: `meshseer`
- env file: `/etc/meshseer/meshseer.env`
- SQLite data: `/var/lib/meshseer/meshseer.db`
- systemd unit: `/etc/systemd/system/meshseer.service`
- cloudflared config: `/etc/cloudflared/config.yml`

## Initial Host Prep

```bash
apt update
apt install -y curl ca-certificates git

useradd --system --create-home --home-dir /opt/meshseer --shell /usr/sbin/nologin meshseer
mkdir -p /opt/meshseer /etc/meshseer /var/lib/meshseer
chown -R meshseer:meshseer /opt/meshseer /var/lib/meshseer
chmod 750 /etc/meshseer
```

Install `uv`:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
ln -sf /root/.local/bin/uv /usr/local/bin/uv
```

If you install as a non-root admin user, adjust the `uv` path accordingly.

## App Install

```bash
git clone https://github.com/<your-org-or-user>/meshradar.git /opt/meshseer/app
cd /opt/meshseer/app
uv sync --frozen
chown -R meshseer:meshseer /opt/meshseer/app
```

If this repo is private, clone it with your normal Git credentials flow first.

## App Env

Start from [meshseer.env.example](/home/juan/dev/meshradar/deploy/proxmox/meshseer.env.example).

At minimum, set:

- `MESHSEER_ENV=production`
- `MESHSEER_BIND_HOST=127.0.0.1`
- `MESHSEER_BIND_PORT=8000`
- `MESHSEER_DB_PATH=/var/lib/meshseer/meshseer.db`
- `MESHSEER_MESHTASTIC_HOST=<your-radio-hostname-or-ip>`
- `MESHSEER_ADMIN_BEARER_TOKEN=<long-random-secret>`

Do not bind the app to `0.0.0.0` in production.

## Systemd Service

Copy [meshseer.service](/home/juan/dev/meshradar/deploy/proxmox/meshseer.service) to `/etc/systemd/system/meshseer.service`, then:

```bash
systemctl daemon-reload
systemctl enable --now meshseer.service
systemctl status meshseer.service
```

The unit must execute the installed `meshseer` console script. Do not use
`python -m meshseer.main` here: that only imports the module and exits without
starting Uvicorn.

Basic checks:

```bash
curl http://127.0.0.1:8000/api/health
journalctl -u meshseer -n 100 --no-pager
```

Important:

- The service must use `ExecStart=/opt/meshseer/app/.venv/bin/meshseer`
- Do not use `python -m meshseer.main` in `systemd`; that only imports the module and exits cleanly
- If `systemctl status meshseer` shows `Deactivated successfully` immediately after start, you are almost certainly using the wrong `ExecStart`

## Cloudflare Tunnel

Install `cloudflared` using Cloudflare's package instructions for Debian, then create a named tunnel and route `meshseer.nemexix.com` to it.

Use [cloudflared-config.yml.example](/home/juan/dev/meshradar/deploy/proxmox/cloudflared-config.yml.example) as the starting config.

After you place the real tunnel ID and credentials file:

```bash
cloudflared tunnel ingress validate
cloudflared tunnel ingress rule https://meshseer.nemexix.com/api/admin/health
cloudflared tunnel ingress rule https://meshseer.nemexix.com/api/health
cloudflared --config /etc/cloudflared/config.yml service install
systemctl enable --now cloudflared
```

The `/api/admin/...` and `/api/health` probes must match the `http_status:404` rule, not the Meshseer origin. The public UI uses `/api/status` instead.

## DNS And Public Hostname

In Cloudflare:

1. Create or select a named tunnel.
2. Add a public hostname:
   `meshseer.nemexix.com` -> `http://127.0.0.1:8000`
3. Keep the hostname proxied.
4. Confirm WebSockets are allowed.
5. Add a WAF custom rule to block requests on ports other than `80` and `443`.
6. Do not enable edge caching for this hostname.

## Admin Access

Keep admin local-only.

Examples:

```bash
curl -H "Authorization: Bearer <token>" \
  http://127.0.0.1:8000/api/admin/health
```

Or from your workstation:

```bash
ssh -L 8000:127.0.0.1:8000 root@<proxmox-lxc-ip>
curl -H "Authorization: Bearer <token>" \
  http://127.0.0.1:8000/api/admin/health
```

## Backups

Back up at least:

- `/etc/meshseer/meshseer.env`
- `/var/lib/meshseer/meshseer.db`
- `/etc/cloudflared/`

If the container is dedicated to Meshseer, Proxmox snapshot backups are a good fit.

## Rollout Checklist

1. `systemctl status meshseer` is healthy.
2. `curl http://127.0.0.1:8000/api/health` works inside the container.
3. `curl https://meshseer.nemexix.com/api/health` returns Cloudflare `404`.
4. `curl https://meshseer.nemexix.com/api/status` works publicly.
5. `curl https://meshseer.nemexix.com/api/admin/health` returns Cloudflare `404`.
6. `curl https://meshseer.nemexix.com/docs` returns `404`.
7. The dashboard loads and `/ws/events` stays connected.
