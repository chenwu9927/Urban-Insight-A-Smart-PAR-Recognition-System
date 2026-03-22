from __future__ import annotations

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path("/opt/urban-insight")
DOMAIN = "urbaninsights.site"
MAIL_DOMAIN = f"mail.{DOMAIN}"
WWW_DOMAIN = f"www.{DOMAIN}"

LE_LIVE_DIR = Path("/etc/letsencrypt/live") / DOMAIN
FULLCHAIN_PATH = LE_LIVE_DIR / "fullchain.pem"
PRIVKEY_PATH = LE_LIVE_DIR / "privkey.pem"

NGINX_BIN = Path("/www/server/nginx/sbin/nginx")
NGINX_MAIN_CONF = Path("/www/server/nginx/conf/nginx.conf")
NGINX_VHOST_CONF = Path("/www/server/panel/vhost/nginx/urban-insight-proxy.conf")
STALWART_CONFIG = Path("/var/lib/docker/volumes/urban-insight_mail-server-data/_data/etc/config.toml")

NGINX_START = "# BEGIN URBAN-INSIGHT TLS"
NGINX_END = "# END URBAN-INSIGHT TLS"
STALWART_START = "# BEGIN URBAN-INSIGHT CERTIFICATE"
STALWART_END = "# END URBAN-INSIGHT CERTIFICATE"


def ensure_file(path: Path, label: str) -> None:
    if not path.exists():
        raise SystemExit(f"{label} not found: {path}")


def replace_managed_block(path: Path, start_marker: str, end_marker: str, body: str) -> None:
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    managed = f"{start_marker}\n{body.rstrip()}\n{end_marker}\n"
    if start_marker in existing and end_marker in existing:
        start = existing.index(start_marker)
        end = existing.index(end_marker, start) + len(end_marker)
        if end < len(existing) and existing[end] == "\n":
            end += 1
        updated = existing[:start] + managed + existing[end:]
    else:
        prefix = existing.rstrip()
        updated = f"{prefix}\n\n{managed}" if prefix else managed
    path.write_text(updated, encoding="utf-8")


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def render_nginx_conf() -> str:
    fullchain = str(FULLCHAIN_PATH).replace("\\", "/")
    privkey = str(PRIVKEY_PATH).replace("\\", "/")
    return f"""server {{
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    location /.well-known/acme-challenge/ {{
        root /www/wwwroot/_letsencrypt;
    }}

    location / {{
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }}
}}

server {{
    listen 80;
    listen [::]:80;
    server_name {DOMAIN} {WWW_DOMAIN};

    location /.well-known/acme-challenge/ {{
        root /www/wwwroot/_letsencrypt;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}

server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {DOMAIN} {WWW_DOMAIN};

    ssl_certificate {fullchain};
    ssl_certificate_key {privkey};

    location / {{
        proxy_pass http://127.0.0.1:8081;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection $connection_upgrade;
    }}
}}

server {{
    listen 80;
    listen [::]:80;
    server_name {MAIL_DOMAIN};

    location /.well-known/acme-challenge/ {{
        root /www/wwwroot/_letsencrypt;
    }}

    location / {{
        return 301 https://$host$request_uri;
    }}
}}

server {{
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name {MAIL_DOMAIN};

    ssl_certificate {fullchain};
    ssl_certificate_key {privkey};

    location / {{
        proxy_pass http://127.0.0.1:8082;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""


def render_stalwart_cert_block() -> str:
    fullchain = str(FULLCHAIN_PATH).replace("\\", "/")
    privkey = str(PRIVKEY_PATH).replace("\\", "/")
    return f"""[certificate."default"]
cert = "%{{file:{fullchain}}}%"
private-key = "%{{file:{privkey}}}%"
default = true
"""


def main() -> int:
    ensure_file(FULLCHAIN_PATH, "TLS certificate")
    ensure_file(PRIVKEY_PATH, "TLS private key")
    ensure_file(NGINX_BIN, "nginx binary")
    ensure_file(NGINX_MAIN_CONF, "nginx main config")
    ensure_file(STALWART_CONFIG, "Stalwart config")

    replace_managed_block(NGINX_VHOST_CONF, NGINX_START, NGINX_END, render_nginx_conf())
    replace_managed_block(STALWART_CONFIG, STALWART_START, STALWART_END, render_stalwart_cert_block())

    run([str(NGINX_BIN), "-t", "-c", str(NGINX_MAIN_CONF)])
    run([str(NGINX_BIN), "-s", "reload", "-c", str(NGINX_MAIN_CONF)])
    run(
        [
            "docker",
            "compose",
            "--profile",
            "mail",
            "--env-file",
            ".env",
            "-f",
            "deploy/compose/docker-compose.yml",
            "-f",
            "deploy/compose/docker-compose.prod.yml",
            "restart",
            "mail-server",
        ]
    )

    print("TLS cutover applied successfully.")
    print(f"Website domains: https://{DOMAIN} and https://{WWW_DOMAIN}")
    print(f"Mail admin: https://{MAIL_DOMAIN}")
    return 0


if __name__ == "__main__":
    if Path.cwd() != PROJECT_ROOT:
        try:
            Path.chdir(PROJECT_ROOT)  # type: ignore[attr-defined]
        except AttributeError:
            import os

            os.chdir(PROJECT_ROOT)
    raise SystemExit(main())
