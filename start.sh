#!/bin/sh
set -eu
cd "$(dirname "$0")"
if [ ! -f .env ]; then
  python3 -c 'import secrets; print("API_TOKEN="+secrets.token_hex(32)); print("ALLOWED_ORIGINS=")' > .env
  chmod 600 .env
fi
docker compose up -d --build
printf '\nOpen http://localhost:8080 and use this API token:\n'
sed -n '/^API_TOKEN=/p' .env
