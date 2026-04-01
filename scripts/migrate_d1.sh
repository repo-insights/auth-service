#!/usr/bin/env bash

set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <d1_database_name> [--local|--remote]"
  exit 1
fi

db_name="$1"
mode="${2:---local}"

case "$mode" in
  --local|--remote)
    ;;
  *)
    echo "Invalid mode: $mode"
    echo "Usage: $0 <d1_database_name> [--local|--remote]"
    exit 1
    ;;
esac

exec npx wrangler d1 migrations apply "$db_name" "$mode"
