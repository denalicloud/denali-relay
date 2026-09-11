# Denali PRO — SMTP Relay with Monthly Quota

A Dockerized SMTP relay with SASL authentication, DKIM signing, per-user monthly
sending quota, and a web dashboard.

## Stack

| Container | Image | Role |
|-----------|-------|------|
| `relay-postfix-1` | `massmux/relay-postfix` | SMTP relay — ports 25, 465, 587 |
| `relay-policy-daemon-1` | `massmux/relay-policy-daemon` | Checks/increments monthly quota counters |
| `relay-dkim-milter-1` | `massmux/relay-dkim-milter` | DKIM signing, dynamic per-domain `d=` |
| `relay-log-parser-1` | `massmux/relay-log-parser` | Tails Postfix log → SQLite (`data/relay.db`) |
| `relay-webui-1` | `massmux/relay-webui` | Flask dashboard, port 8080 |
| `relay-redis-1` | `redis:7-alpine` | Monthly counters, auto-expire after 35 days |

## Requirements

- Docker + Docker Compose plugin
- A valid hostname with PTR record configured
- Port 25 open at your provider (some block it by default)

## Setup

### 1. Clone the repository

```
git clone https://github.com/denalicloud/denali-relay.git /opt/relay
cd /opt/relay
```

### 2. Create config files from templates

```
cp postfix/sasl/sasl_passwd.example postfix/sasl/sasl_passwd
cp policy-daemon/quota.conf.example policy-daemon/quota.conf
cp redis/redis.conf.example redis/redis.conf
cp .env.example .env
```

### 3. Edit config files with real credentials

| File | Description |
|------|-------------|
| `postfix/sasl/sasl_passwd` | SASL users — tab-separated: `user@domain<TAB>password` |
| `policy-daemon/quota.conf` | Monthly quotas per user and Redis password |
| `redis/redis.conf` | Redis password — must match `quota.conf` |
| `.env` | `SECRET_KEY` for the webui — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |

### 4. Update hostname in main.cf

Edit `postfix/main.cf` and replace with your actual hostname:

```
myhostname = your.hostname.com
mydomain = hostname.com
```

### 5. Generate the DKIM key

```
opendkim-genkey -b 2048 -s mail -D opendkim/keys/
```

This creates `opendkim/keys/mail.private` (kept out of git via `.gitignore`) and
`opendkim/keys/mail.txt` (the public key to publish in each customer's DNS).
The milter signs every message with `d=<domain of the From: address>`, so the
same key/selector works for every domain relayed through this instance — each
customer domain must publish a `mail._domainkey.<domain>` TXT record with the
same public key.

### 6. Obtain a TLS certificate

```
apt install certbot
ufw allow 80/tcp
ufw allow 25/tcp
ufw allow 465/tcp
ufw allow 587/tcp
certbot certonly --standalone -d your.hostname.com
```

Update the certificate paths in `postfix/main.cf` accordingly. If port 80 is
already used by a webserver on the host (e.g. to serve the dashboard on its own
domain), use `--webroot` or add `pre_hook`/`post_hook` to stop/start it instead
of `--standalone`. Postfix also needs a `deploy_hook` on renewal to reload the
certificate inside the container:

```
deploy_hook = docker exec relay-postfix-1 postfix reload
```

### 7. Start the stack

```
docker compose up -d
docker compose ps
```

All six containers should show status `Up`.

## User Management

All user management is handled via `relay-admin.sh`:

```
# List all users and their quotas
./relay-admin.sh list

# Show current month sending stats
./relay-admin.sh stats

# Add a user (quota defaults to 1000 if not specified)
./relay-admin.sh add user@domain.com password 2000

# Remove a user
./relay-admin.sh remove user@domain.com

# Change a user's password
./relay-admin.sh passwd user@domain.com newpassword

# Change a user's monthly quota
./relay-admin.sh quota user@domain.com 5000

# Reset current month counter for a user
./relay-admin.sh reset user@domain.com
```

## Web Dashboard

The webui (port 8080, typically reverse-proxied by a host nginx on its own
hostname) shows delivered/deferred/bounced/dropped messages and a monthly chart.
Login uses the **same SASL credentials** as the relay itself (`sasl_passwd`) —
each `user@domain` logs in with their existing SASL password and sees only
their own sending history.

## How Quota Works

Each outbound message increments a Redis counter keyed by `quota:YYYY-MM:user@domain`.
The counter expires automatically after 35 days, so the monthly reset is fully automatic.

When a user reaches their quota, Postfix rejects the message at end-of-data with:

```
554 5.7.1 Monthly quota exceeded (N/N). Contact support@denali.pro
```

Quota changes in `quota.conf` take effect immediately after restarting the policy daemon — no Redis intervention needed. The counter stores the raw send count; the threshold is always read from the config file.

If you need to manually reset a counter (e.g. after a plan upgrade):

```
./relay-admin.sh reset user@domain.com
```

## Directory Structure

```
/opt/relay/
├── docker-compose.yml
├── relay-admin.sh
├── .env                          # real SECRET_KEY — not committed
├── .env.example                  # template
├── postfix/
│   ├── Dockerfile
│   ├── main.cf
│   ├── master.cf
│   ├── sasl/
│   │   ├── sasl_passwd           # real credentials — not committed
│   │   ├── sasl_passwd.example   # template
│   │   └── smtpd.conf
│   └── scripts/
│       └── entrypoint.sh
├── policy-daemon/
│   ├── Dockerfile
│   ├── policy.py
│   ├── quota.conf                # real config — not committed
│   └── quota.conf.example        # template
├── redis/
│   ├── redis.conf                # real config — not committed
│   └── redis.conf.example        # template
├── opendkim/
│   ├── Dockerfile
│   ├── opendkim.conf
│   └── keys/
│       ├── mail.private          # real private key — not committed
│       └── mail.txt               # public key, safe to publish/commit
├── dkim-milter/
│   ├── Dockerfile
│   └── dkim_milter.py
├── log-parser/
│   ├── Dockerfile
│   └── parser.py
├── webui/
│   ├── Dockerfile
│   ├── app.py
│   ├── requirements.txt
│   └── templates/
├── data/
│   └── relay.db                  # SQLite, populated at runtime — not committed
└── host-config/                  # reference configs applied on the host, not in Docker
    ├── fail2ban/
    └── systemd/
```

## Docker Images

Pre-built images are available on Docker Hub:

- [`massmux/relay-postfix`](https://hub.docker.com/r/massmux/relay-postfix)
- [`massmux/relay-policy-daemon`](https://hub.docker.com/r/massmux/relay-policy-daemon)
- [`massmux/relay-dkim-milter`](https://hub.docker.com/r/massmux/relay-dkim-milter)
- [`massmux/relay-log-parser`](https://hub.docker.com/r/massmux/relay-log-parser)
- [`massmux/relay-webui`](https://hub.docker.com/r/massmux/relay-webui)

To rebuild locally from source:

```
docker compose build --no-cache
```

## Security Notes

- `sasl_passwd`, `quota.conf`, `redis.conf`, `.env` and `opendkim/keys/mail.private` are excluded via `.gitignore` — never commit them
- Redis listens only on the internal Docker network — not exposed to the host
- Port 587 enforces STARTTLS (`smtpd_tls_security_level = encrypt` in `master.cf`); port 465 uses implicit TLS (`smtpd_tls_wrappermode = yes`)
- Unauthenticated connections are rejected on ports 465 and 587
- The policy daemon rejects messages with no `sasl_username` regardless of network origin
- The DKIM private key is shared across all customer domains relayed through this instance — if it is ever exposed, rotate it and republish the new public key in every customer's DNS

## License

MIT — Denali PRO SA, Roveredo, Switzerland — https://denali.pro
