#!/usr/bin/env bash
# Smoke test of the running Compose stack (docker compose up -d --wait first): the UI,
# the proxy to the API and the database, the security headers, and the rules the images
# must keep: non-root users, no ingestion packages in the API, size budgets.
# Makes no model calls. Used by CI; run it locally the same way.
set -euo pipefail
WEB="http://localhost:${WEB_PORT:-8080}"
# Compressed, as a pull downloads it: the same on every Docker storage backend (unpacked
# sizes are not). Today about 164 and 26 MB; torch alone would add over 1 GB.
API_BUDGET_MB=250
WEB_BUDGET_MB=40
failed=0
check() {  # check <description> <command...>
  if "${@:2}" >/dev/null 2>&1; then echo "ok    $1"; else echo "FAIL  $1"; failed=1; fi
}
status() {  # status <path> <expected>
  [ "$(curl -s -o /dev/null -w '%{http_code}' "$WEB$1")" = "$2" ]
}

check "UI page"                         status / 200
check "client route falls back to UI"   status /a/00000000-0000-4000-8000-000000000000 200
check "API through the proxy"           status /api/health 200
check "API liveness (no database)"      status /api/livez 200
check "API reaches the database"        status /api/assessments/00000000-0000-4000-8000-000000000000 404
check "nginx health"                    status /healthz 200
check "security policy on the page"     sh -c "curl -sI '$WEB/' | grep -qi '^content-security-policy:.*default-src .self.'"
check "no referrer (the URL holds the id)" sh -c "curl -sI '$WEB/' | grep -qi '^referrer-policy: no-referrer'"
check "API runs as non-root"            sh -c "[ \"\$(docker compose exec -T api id -u)\" != 0 ]"
check "UI runs as non-root"             sh -c "[ \"\$(docker compose exec -T web id -u)\" != 0 ]"
check "no ingestion packages in the API" docker compose exec -T api python -c \
  "import importlib.util as u, sys; sys.exit(any(u.find_spec(m) for m in ('torch', 'sentence_transformers', 'bs4', 'lxml', 'pgvector')))"
# A request claiming to come from 203.0.113.9: the address nginx logs first must be the
# real caller's. Wait for the log line (it arrives a moment later); no line is a failure.
spoof_ignored() {
  local tag="spoof-$RANDOM" address=""
  curl -s -o /dev/null -H "X-Forwarded-For: 203.0.113.9" "$WEB/api/livez?$tag"
  for _ in $(seq 20); do
    address=$(docker compose logs --no-log-prefix web 2>/dev/null | grep "$tag" | awk '{print $1}')
    [ -n "$address" ] && break
    sleep 0.25
  done
  [ -n "$address" ] && [ "$address" != 203.0.113.9 ]
}
check "a spoofed client address is ignored" spoof_ignored
check "API port published nowhere"      sh -c "! docker compose ps api --format '{{.Ports}}' | grep -q -- '->'"

for service in api web; do
  image="actie-$service:local"  # the names docker-compose.yml gives the built images
  mb=$(( $(docker save "$image" | gzip -1 | wc -c) / 1000000 ))
  budget=$([ "$service" = api ] && echo $API_BUDGET_MB || echo $WEB_BUDGET_MB)
  check "$service image ${mb} MB (budget ${budget} MB)" test "$mb" -le "$budget"
done

exit $failed
