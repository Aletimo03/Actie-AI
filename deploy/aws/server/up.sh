#!/usr/bin/env bash
# Runs one release on the server: the images sha-<commit> and this commit's server files.
#   sudo /opt/actie/up.sh <full-commit-sha>
# Called at first boot (bootstrap.sh) and for every release (deploy/aws/deploy.sh via SSM).
set -euo pipefail
cd /opt/actie
RELEASE=${1:-$(cat release)}
[[ $RELEASE =~ ^[0-9a-f]{40}$ ]] || { echo "not a full commit SHA: $RELEASE" >&2; exit 1; }

# This release's server files, from the commit itself: config and code always match.
base="https://raw.githubusercontent.com/Aletimo03/Actie-AI/$RELEASE/deploy/aws/server"
for file in compose.yaml Caddyfile up.sh actie-retention.service actie-retention.timer; do
  curl -fsSL "$base/$file" -o "$file.new" && mv "$file.new" "$file"
done
chmod 755 up.sh

umask 077
# Generated once, on the server, never seen anywhere else: the database was created with
# this password, and every API process must share the quota secret.
if [ ! -f secrets.env ]; then
  printf 'QUOTA_SECRET=%s\nPOSTGRES_PASSWORD=%s\n' "$(openssl rand -hex 32)" "$(openssl rand -hex 24)" >secrets.env
fi
# shellcheck source=/dev/null
. ./secrets.env
key=$(aws ssm get-parameter --region "$(cat region)" --name /actie/anthropic-api-key \
  --with-decryption --query Parameter.Value --output text)
cat >.env <<ENV
IMAGE_TAG=sha-$RELEASE
SITE_ADDRESS=$(cat site)
ANTHROPIC_API_KEY=$key
QUOTA_SECRET=$QUOTA_SECRET
POSTGRES_USER=actie
POSTGRES_PASSWORD=$POSTGRES_PASSWORD
POSTGRES_DB=actie
LLM_MODEL=anthropic/claude-haiku-5-5
LLM_FALLBACKS=
LLM_REASONING_EFFORT=
QUOTA_PER_HOUR=10
QUOTA_PER_DAY=50
ENV

docker compose pull --quiet
docker compose up -d --wait db
docker compose run --rm law  # skips a version of the law already loaded
docker compose up -d --wait --remove-orphans
echo "$RELEASE" >release

install -m 644 actie-retention.service actie-retention.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now actie-retention.timer
# Every image no container uses, tagged ones too: each release leaves a ~190 MB image behind
# on a 20 GB disk. A rollback pulls its images again.
docker image prune -af >/dev/null
echo "release $RELEASE is up at https://$(cat site)"
