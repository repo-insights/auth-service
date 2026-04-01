#!/usr/bin/env bash

set -euo pipefail

if [ ! -f "wrangler.toml" ]; then
  echo "Run this script from the project root."
  exit 1
fi

secrets_file="${1:-.env.cloudflare}"

if [ ! -f "$secrets_file" ]; then
  echo "Missing $secrets_file file. Create it first."
  exit 1
fi

echo "Uploading secrets from $secrets_file ..."
./node_modules/.bin/wrangler secret bulk "$secrets_file"

echo "Applying remote D1 migrations ..."
db_name="$(awk -F'=' '/database_name/ {gsub(/[ "]/, "", $2); print $2}' wrangler.toml | head -n 1)"
if [ -z "${db_name:-}" ]; then
  echo "Could not determine database_name from wrangler.toml"
  exit 1
fi

./node_modules/.bin/wrangler d1 migrations apply "$db_name" --remote

echo "Deploying Worker ..."
./node_modules/.bin/wrangler deploy
