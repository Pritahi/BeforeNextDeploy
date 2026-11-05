#!/usr/bin/env bash
# Stops this demo only. Docker volumes and private local state are retained.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)";cd "$ROOT"
for pair in 'demo:beforenextdeploy.demo_web' 'agent:beforenextdeploy.agent' 'model:llama-server'; do
 name="${pair%%:*}";expected="${pair#*:}";file=".runtime/$name.pid"
 if [ -f "$file" ];then
  pid="$(cat "$file")"
  if kill -0 "$pid" 2>/dev/null && ps -p "$pid" -o args= | grep -Fq "$expected";then kill "$pid" || true;fi
  rm -f "$file"
 fi
done
PROJECT="${BND_COMPOSE_PROJECT:-beforenextdeploy}"
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]] || { echo 'Invalid Compose project name.' >&2; exit 1; }
if [ -f .switch/deploy/local/standalone-docker-compose.yml ];then
 docker compose -p "$PROJECT" --project-directory "$ROOT/.switch" -f "$ROOT/.switch/deploy/local/standalone-docker-compose.yml" --profile collab --profile gateway down
fi
echo 'Stopped. Private state and Docker volumes remain on this machine.'
