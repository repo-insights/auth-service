#!/usr/bin/env bash
# scripts/generate_keys.sh
# ─────────────────────────
# Generates an RSA-4096 key pair for JWT signing.
# Run once before starting the service for the first time.
# Keys are written to ./keys/ which is git-ignored.

set -euo pipefail

KEYS_DIR="$(dirname "$0")/../keys"
mkdir -p "$KEYS_DIR"

PRIVATE_KEY="$KEYS_DIR/private.pem"
PUBLIC_KEY="$KEYS_DIR/public.pem"

if [[ -f "$PRIVATE_KEY" ]]; then
  echo "⚠  Keys already exist at $KEYS_DIR. Delete them first if you want to regenerate."
  exit 0
fi

echo "🔑 Generating RSA-4096 key pair..."

# Generate private key
openssl genrsa -out "$PRIVATE_KEY" 4096

# Extract public key
openssl rsa -in "$PRIVATE_KEY" -pubout -out "$PUBLIC_KEY"

# Restrict permissions: owner read-only
chmod 600 "$PRIVATE_KEY"
chmod 644 "$PUBLIC_KEY"

echo "✅ Keys generated:"
echo "   Private: $PRIVATE_KEY"
echo "   Public:  $PUBLIC_KEY"
echo ""
echo "📋 Add these to your .env:"
echo "   JWT_PRIVATE_KEY_PATH=./keys/private.pem"
echo "   JWT_PUBLIC_KEY_PATH=./keys/public.pem"
