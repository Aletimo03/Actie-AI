#!/usr/bin/env bash
# Puts the model key into SSM Parameter Store (encrypted), where only the server can read it.
# Run it yourself, once: deploy/aws/put-secret.sh   (reads ANTHROPIC_API_KEY from .env)
# The key goes through a file only you can read, never the command line or the terminal.
set -euo pipefail
cd "$(dirname "$0")/../.."
REGION=$(aws configure get region)
value=$(mktemp)
chmod 600 "$value"
trap 'rm -f -- "$value"' EXIT
grep -E '^ANTHROPIC_API_KEY=' .env | cut -d= -f2- | tr -d '\n' >"$value"
[ -s "$value" ] || { echo "no ANTHROPIC_API_KEY in .env" >&2; exit 1; }
aws ssm put-parameter --region "$REGION" --name /actie/anthropic-api-key --type SecureString \
  --value "file://$value" --overwrite --output text >/dev/null
echo "stored /actie/anthropic-api-key in $REGION (encrypted)"
