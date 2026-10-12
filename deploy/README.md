# Vārtā deploy runbook

One VPS, two instances from one codebase, fronted by Caddy:

| Instance | URL | Reachable from | Plaid | LLM |
|---|---|---|---|---|
| demo | `https://<DEMO_DOMAIN>` | public internet | Sandbox | OpenRouter (own key, small cap) |
| owner | `https://<OWNER_HOST>` | tailnet only | Production Trial | OpenRouter (own key, own cap) |

Both use `anthropic/claude-haiku-4.5`. No Ollama. Only Caddy publishes ports: demo on `<PUBLIC_IP>:80/443`, owner on `<OWNER_TS_IP>:443`.

Never paste secrets into chat or issues. Edit env files on the server with an editor.

## 1. Prerequisites

- VPS: Hetzner CX22 class (2 vCPU / 4 GB), Ubuntu 24.04. Check the live price.
- Demo domain or subdomain with an A record to the VPS public IP.
- Tailscale account.
- Two OpenRouter keys (demo, owner). Set a monthly spend cap on each in the OpenRouter dashboard (demo small, e.g. $5).
- Plaid Sandbox keys (demo) and Production Trial keys (owner).

## 2. Server setup

```bash
# as root: non-root user with your SSH key, then lock down SSH
adduser --disabled-password --gecos "" varta
usermod -aG sudo varta
mkdir -p /home/varta/.ssh && cp ~/.ssh/authorized_keys /home/varta/.ssh/ && chown -R varta: /home/varta/.ssh
echo 'varta ALL=(ALL) NOPASSWD:ALL' > /etc/sudoers.d/varta
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config && systemctl reload ssh
ufw allow 22,80,443/tcp && ufw enable
```

Log in as `varta` from here on.

```bash
# Docker Engine + compose plugin (official apt repo)
sudo apt-get update && sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list
sudo apt-get update && sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
sudo usermod -aG docker varta   # re-login to apply

# Tailscale
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up --ssh
tailscale ip -4                 # -> OWNER_TS_IP
```

In the Tailscale admin console enable **MagicDNS** and **HTTPS Certificates**. `OWNER_HOST` is `<vps-hostname>.<tailnet>.ts.net`.

**Reboot ordering.** Docker publishes on the Tailscale IP, which fails if docker starts before tailscaled has it:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
sudo tee /etc/systemd/system/docker.service.d/override.conf <<'CONF'
[Unit]
After=tailscaled.service
Wants=tailscaled.service
CONF
sudo systemctl daemon-reload
```

## 3. Deploy

```bash
git clone <repo-url> varta && cd varta
for f in demo owner caddy; do cp deploy/$f.env.example deploy/$f.env; chmod 600 deploy/$f.env; done
```

Edit each file with an editor (`nano deploy/demo.env`, ...):

- `caddy.env`: `ACME_EMAIL`, `DEMO_DOMAIN`, `OWNER_HOST`, `OWNER_TS_IP`, `PUBLIC_IP`. Compose fails closed if `PUBLIC_IP`/`OWNER_TS_IP` are unset; Caddy crash-loops if `ACME_EMAIL`/`DEMO_DOMAIN`/`OWNER_HOST` are empty.
- `demo.env`: Sandbox Plaid keys, demo OpenRouter key.
- `owner.env`: Production Plaid keys, owner OpenRouter key.

Define the compose command once (every command below uses it; `--env-file` is needed for the IP interpolation):

```bash
dc="docker compose -f deploy/compose.yaml --env-file deploy/caddy.env --profile demo --profile owner"
```

Generate a different `TOKEN_ENCRYPTION_KEY` per instance. Delete the empty `TOKEN_ENCRYPTION_KEY=` line in each file first (last one wins, so duplicates hide mistakes), then append:

```bash
$dc build
$dc run --rm --no-deps api-demo  python -m scripts.new_token_key >> deploy/demo.env
$dc run --rm --no-deps api-owner python -m scripts.new_token_key >> deploy/owner.env
```

Back these keys up somewhere safe. Losing one makes stored Plaid tokens unreadable (re-link accounts).

```bash
$dc up -d --build
$dc ps
```

## 4. First data

- Demo: `$dc exec worker-demo python -m scripts.reset_demo`
- Owner: open `https://<OWNER_HOST>` from a tailnet device, then Accounts -> Link.

## 5. Verify

```bash
curl -i https://<DEMO_DOMAIN>/healthz            # 200 (Caddy routes to api-demo)
curl -m 5 https://<OWNER_HOST>                   # from OFF the tailnet: must fail/not answer
$dc logs -f worker-demo                          # JSON lines
```

Rate limit: send 21 `POST https://<DEMO_DOMAIN>/api/chat` requests within an hour from one IP; the 21st returns 429 (`CHAT_RATE_PER_HOUR=20`).

Worker schedule (local `VARTA_TZ`): sync every 6h, news every 15m, alerts hourly, briefing 07:00, backup 02:30, demo reset 03:00 (demo only).

## 6. Operations

```bash
# update
git pull && $dc up -d --build

# rotate a key: edit the env file, then recreate that instance
$dc up -d

# restart / logs
$dc restart api-demo worker-demo
$dc logs --tail 100 api-owner
```

**Backups** are written daily to `/data/backups` in the `demo-data` / `owner-data` volumes (7 kept). Copy one off-box:

```bash
$dc exec worker-owner ls /data/backups
$dc cp worker-owner:/data/backups/varta-YYYYMMDD-HHMM.db ./owner-backup.db
```

**Restore** (owner shown; same for demo):

```bash
$dc stop api-owner worker-owner
$dc cp ./owner-backup.db worker-owner:/data/varta.db   # works on stopped containers
$dc start api-owner worker-owner
```

If the copied file's owner is wrong, run `$dc run --rm --no-deps --user root api-owner chown varta /data/varta.db`. Stale `varta.db-wal`/`-shm` files left from the old DB should be removed the same way before starting.

**Monitoring:** UptimeRobot HTTP monitor on `https://<DEMO_DOMAIN>/healthz`.

## 7. Security notes

- Secrets live only in `deploy/*.env` on the server (mode 600, never committed).
- The owner instance has no public route; it is bound to the Tailscale IP only.
- Demo and owner sit on separate Docker networks; Caddy is the only bridge.
- Each OpenRouter key has its own spend cap.
- Follow-up (not a step): Plaid Production Link for OAuth banks may need an HTTPS redirect URI on the owner host; see `docs/superpowers/STATUS.md` open items.
