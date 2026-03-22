# TLS Cutover

Current status on March 22, 2026:

- Public HTTP is working for `urbaninsights.site`, `www.urbaninsights.site`, and `mail.urbaninsights.site`.
- The mail stack is live and uses the self-hosted Stalwart service.
- DKIM signing is enabled on the server with selector `ui202603`.
- Public certificate issuance is currently blocked because Let's Encrypt HTTP-01 validation is being redirected to the DNSPod block page at `43.159.104.94`, instead of reaching `119.45.17.207`.

Ready-to-run artifacts:

- `scripts/enable_public_tls.py`
- `deploy/compose/docker-compose.yml`
- `deploy/compose/docker-compose.prod.yml`

What to do once the domain is no longer blocked:

1. Issue the certificate on the server:
```bash
certbot certonly --webroot -w /www/wwwroot/_letsencrypt \
  -d urbaninsights.site \
  -d www.urbaninsights.site \
  -d mail.urbaninsights.site \
  --register-unsafely-without-email \
  --agree-tos \
  --non-interactive
```

2. Apply HTTPS for the website and TLS for the mail service:
```bash
cd /opt/urban-insight
python scripts/enable_public_tls.py
```

What the script does:

- Updates the host Nginx vhost file at `/www/server/panel/vhost/nginx/urban-insight-proxy.conf`
- Enables HTTPS for:
  - `urbaninsights.site`
  - `www.urbaninsights.site`
  - `mail.urbaninsights.site`
- Adds the Stalwart `certificate."default"` block pointing to:
  - `/etc/letsencrypt/live/urbaninsights.site/fullchain.pem`
  - `/etc/letsencrypt/live/urbaninsights.site/privkey.pem`
- Reloads host Nginx
- Restarts the `mail-server` container

Still external to this repository:

- PTR / reverse DNS for `119.45.17.207 -> mail.urbaninsights.site`
- Any DNS-provider-side block caused by ICP filing or registrar policy
- Optional later hardening:
  - `TLS-RPT`
  - `MTA-STS`
  - `SRV` autoconfiguration records
