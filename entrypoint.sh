#!/bin/bash
set -euo pipefail

mkdir -p /app/data/uploads
chown app:app /app/data /app/data/uploads

gosu app python -m app.migrate

# --proxy-headers honors X-Forwarded-Proto/For from the tunnel so generated
# links use https. Trusting all peers is safe here: the container is only
# meant to be reached via Cloudflare Tunnel, not exposed directly.
exec gosu app uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log \
    --proxy-headers --forwarded-allow-ips='*'
