#!/usr/bin/env bash
# One-time downloads are large. No paid provider accounts are used.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SWITCH="$ROOT/.switch"
COMMIT="b09e7ce4cb6abfad3783d3d7d75f45a09608dc45"
for cmd in docker git python3; do command -v "$cmd" >/dev/null || { echo "Missing dependency: $cmd" >&2; exit 1; }; done
docker info >/dev/null 2>&1 || { echo "Docker is not running or your account cannot access it." >&2; exit 1; }
docker compose version >/dev/null 2>&1 || { echo "Docker Compose v2 is required." >&2; exit 1; }
if [ ! -d "$SWITCH/.git" ]; then
  echo "Downloading pinned Switch source..."
  mkdir -p "$SWITCH"
  git -C "$SWITCH" init -q
  git -C "$SWITCH" remote add origin https://github.com/sandbox-quantum/switch.git
  git -C "$SWITCH" fetch -q --depth 1 origin "$COMMIT"
  git -C "$SWITCH" checkout -q --detach FETCH_HEAD
fi
[ "$(git -C "$SWITCH" rev-parse HEAD)" = "$COMMIT" ] || { echo "Unexpected Switch source revision. Stop and inspect .switch." >&2; exit 1; }
if [ ! -f "$SWITCH/.env" ]; then
  umask 077
  cp "$SWITCH/.env.example" "$SWITCH/.env"
  bash "$SWITCH/deploy/local/generate-env-secrets.sh" "$SWITCH/.env" local >/dev/null
fi
python3 - "$SWITCH/.env" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); lines=p.read_text().splitlines()
changes={'SWITCH_VERSION':'0.31.0','SWITCH_BIND_ADDR':'127.0.0.1','API_HOST_PORT':'18000',
         'GATEWAY_HOST_PORT':'13000','MATTERMOST_HOST_PORT':'18065','POSTGRES_HOST_PORT':'15432'}
seen=set();out=[]
for line in lines:
 k=line.split('=',1)[0]
 if k in changes: out.append(k+'='+changes[k]);seen.add(k)
 else: out.append(line)
for k,v in changes.items():
 if k not in seen: out.append(k+'='+v)
p.write_text('\n'.join(out)+'\n');p.chmod(0o600)
PY
PROJECT="${BND_COMPOSE_PROJECT:-beforenextdeploy}"
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]{0,62}$ ]] || { echo 'Invalid Compose project name.' >&2; exit 1; }
COMPOSE=(docker compose -p "$PROJECT" --project-directory "$SWITCH" -f "$SWITCH/deploy/local/standalone-docker-compose.yml" --profile collab --profile gateway)
echo "Starting Switch, Mattermost and Postgres..."
"${COMPOSE[@]}" up -d
setup="$("${COMPOSE[@]}" ps -a -q setup)"
[ -n "$setup" ] || { echo "Switch setup container not found." >&2; exit 1; }
code="$(docker wait "$setup")"
[ "$code" = 0 ] || { echo "Switch setup failed; inspect the setup container privately." >&2; exit 1; }
python3 "$ROOT/scripts/write_env.py" "$SWITCH/.env" "$ROOT/.env"
echo "Switch/Mattermost started on loopback."
