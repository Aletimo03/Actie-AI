#!/usr/bin/env bash
# The whole app on a local Kubernetes cluster (kind), at http://actie.localhost:8088.
# Idempotent: run it again after a change. Needs Docker, kind, kubectl, helm and a .env
# with ANTHROPIC_API_KEY. Delete everything with: kind delete cluster --name actie
set -euo pipefail
cd "$(dirname "$0")/../.."
CLUSTER=actie
TRAEFIK_CHART=41.7.1  # Traefik v3.7.14, at least 14 days old like every other pin

kind get clusters 2>/dev/null | grep -qx "$CLUSTER" ||
  kind create cluster --config deploy/kind/cluster.yaml

# Tag images with the commit, plus a hash of any uncommitted changes: a new tag changes
# the Deployments, so a rebuild rolls the pods instead of being silently ignored, and two
# different uncommitted states never share a tag.
TAG="local-$(git rev-parse --short HEAD)"
git diff --quiet HEAD -- . || TAG="$TAG-$(git diff HEAD -- . | shasum | cut -c1-7)"
docker build -q -t "actie-api:$TAG" -f backend/Dockerfile . >/dev/null
docker build -q -t "actie-web:$TAG" frontend >/dev/null
kind load docker-image "actie-api:$TAG" "actie-web:$TAG" --name "$CLUSTER"

helm upgrade --install traefik traefik --repo https://traefik.github.io/charts \
  --version "$TRAEFIK_CHART" --namespace traefik --create-namespace \
  --values deploy/kind/traefik-values.yaml --wait

kubectl create namespace actie --dry-run=client -o yaml | kubectl apply -f - >/dev/null

# The Secret is created once and then kept: Postgres was initialised with its password.
# Values go through a file only this user can read, never the command line.
if ! kubectl --namespace actie get secret actie-secrets >/dev/null 2>&1; then
  secrets=$(mktemp)
  chmod 600 "$secrets"
  trap 'rm -f -- "$secrets"' EXIT
  {
    grep -E '^ANTHROPIC_API_KEY=' .env
    echo "QUOTA_SECRET=$(openssl rand -hex 32)"
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"
  } >"$secrets"
  kubectl --namespace actie create secret generic actie-secrets --from-env-file="$secrets"
fi

helm upgrade --install actie deploy/helm/actie --namespace actie \
  --values deploy/helm/actie/values-kind.yaml --set image.tag="$TAG" --wait --timeout 5m

echo "Actie AI on kind: http://actie.localhost:8088 (images $TAG)"
