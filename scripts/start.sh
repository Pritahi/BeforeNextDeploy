#!/usr/bin/env bash
# One-command, synthetic-only local demo. Does not deploy or push anything.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
for cmd in python3 git curl docker; do command -v "$cmd" >/dev/null || { echo "Missing dependency: $cmd" >&2; exit 1; }; done
python3 - <<'PY'
import os,sys
if sys.version_info < (3,10):raise SystemExit('Python 3.10+ is required.')
if not hasattr(os,'O_NOFOLLOW'):raise SystemExit('This prototype requires POSIX O_NOFOLLOW support.')
PY
if [ -n "${BND_STATE_DIR:-}" ] || [ -n "${BND_ENV:-}" ]; then echo 'start.sh is for the default isolated demo; unset BND_STATE_DIR/BND_ENV.' >&2; exit 1; fi
umask 077; mkdir -p .runtime; chmod 700 .runtime
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
.venv/bin/python -m pip install -q -r requirements.txt
bash scripts/start_switch.sh
.venv/bin/python scripts/setup_demo.py
.venv/bin/python - <<'PY'
from beforenextdeploy import settings
settings.load_env()
demo=(settings.state_dir()/'demo-source').resolve()
if settings.repo_root().resolve()!=demo or settings.github_config()!=('octocat','Hello-World','master'):
 raise SystemExit('start.sh is synthetic-demo only. Remove custom BND_REPO_ROOT/BND_GITHUB_* settings first.')
PY
bash scripts/model_assets.sh
.venv/bin/python - <<'PY'
from pathlib import Path
import os,secrets
p=Path('.runtime/model.key')
if not p.exists():
 fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
 with os.fdopen(fd,'w') as f:f.write(secrets.token_urlsafe(32)+'\n')
PY
live() { [ -f ".runtime/$1.pid" ] && kill -0 "$(cat ".runtime/$1.pid")" 2>/dev/null && ps -p "$(cat ".runtime/$1.pid")" -o args= | grep -Fq "$2"; }
port_free() { .venv/bin/python - "$1" <<'PY'
import socket,sys
s=socket.socket();s.settimeout(1)
if s.connect_ex(('127.0.0.1',int(sys.argv[1])))==0:raise SystemExit('Port already in use; stop the conflicting service before starting.')
s.close()
PY
}
if ! live model "$ROOT/.model/llama-b11669/llama-server"; then
  port_free 18099; echo 'Starting authenticated local model...'
  nohup "$ROOT/.model/llama-b11669/llama-server" -m "$ROOT/.model/qwen3-0.6b-q4_k_m.gguf" --host 127.0.0.1 --port 18099 --api-key-file "$ROOT/.runtime/model.key" --no-webui -c 2048 -t 2 -b 128 -ub 64 --parallel 1 --reasoning off >>"$ROOT/.runtime/model.log" 2>&1 &
  echo $! >.runtime/model.pid
fi
.venv/bin/python scripts/wait_local.py http://127.0.0.1:18099/v1/models .runtime/model.key
if [ ! -f .runtime/agents.json ] || ! .venv/bin/python -c "import json;assert json.load(open('.runtime/agents.json')).get('room_id')" >/dev/null 2>&1; then
  .venv/bin/python -m beforenextdeploy.agent --bootstrap
fi
if ! live agent "$ROOT/.venv/bin/python"; then
  echo 'Starting Lookout and Keeper...'; : >.runtime/agent.log
  nohup "$ROOT/.venv/bin/python" -m beforenextdeploy.agent >>"$ROOT/.runtime/agent.log" 2>&1 &
  echo $! >.runtime/agent.pid
  .venv/bin/python scripts/wait_agent.py .runtime/agent.log "$(cat .runtime/agent.pid)"
fi
if ! live demo "$ROOT/.venv/bin/python"; then
  port_free 18778; echo 'Starting synthetic visual demo...'
  nohup "$ROOT/.venv/bin/python" -m beforenextdeploy.demo_web >>"$ROOT/.runtime/demo.log" 2>&1 &
  echo $! >.runtime/demo.pid
fi
.venv/bin/python scripts/wait_local.py http://127.0.0.1:18778/
kill -0 "$(cat .runtime/demo.pid)" 2>/dev/null || { echo 'Demo process exited.' >&2; exit 1; }
printf '\nReady! Open http://127.0.0.1:18778 in a browser.\n'
printf 'This is a synthetic demo account; do not put confidential files in it.\n'
printf 'The Mattermost demo account credentials are in private .env; never publish that file.\n'
