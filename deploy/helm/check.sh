#!/usr/bin/env bash
# Checks the chart without a cluster: helm lint, then every value combination we use is
# rendered and validated against the Kubernetes schemas (kubeconform, strict: unknown
# fields fail, e.g. a misspelt `readinesProbe` the cluster would silently ignore).
# Used by CI; run it locally the same way (needs helm and kubeconform).
set -euo pipefail
cd "$(dirname "$0")"
CHART=actie
KUBERNETES=1.35.0  # the version the schemas are taken from

render() {  # render <name> <helm args...>
  local name=$1; shift
  echo "--- $name"
  helm template actie "$CHART" "$@" |
    kubeconform -strict -summary -kubernetes-version "$KUBERNETES" -
}

helm lint "$CHART"
helm lint "$CHART" --values "$CHART/values-kind.yaml"
render "production defaults" --set image.tag=sha-0000000
render "kind" --values "$CHART/values-kind.yaml"
render "external database" --set postgres.enabled=false
render "TLS, everything optional off" \
  --set ingress.tls=true,law.load=false,retention.enabled=false,networkPolicy.enabled=false
