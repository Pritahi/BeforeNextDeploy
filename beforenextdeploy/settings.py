"""Private local settings. Never accept worktree paths from chat."""
from __future__ import annotations
import os
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def load_env():
    path=Path(os.environ.get('BND_ENV',str(ROOT/'.env')))
    if path.exists():
        for raw in path.read_text(encoding='utf-8').splitlines():
            line=raw.strip()
            if line and not line.startswith('#') and '=' in line:
                key,value=line.split('=',1)
                os.environ.setdefault(key.strip(),value.strip())

def state_dir():
    p=Path(os.environ.get('BND_STATE_DIR',str(ROOT/'.runtime'))).expanduser().resolve()
    p.mkdir(mode=0o700,parents=True,exist_ok=True)
    return p

def repo_root():
    return Path(os.environ.get('BND_REPO_ROOT',str(state_dir()/'demo-source'))).expanduser()

def github_config():
    return (os.environ.get('BND_GITHUB_OWNER','octocat'),
            os.environ.get('BND_GITHUB_REPO','Hello-World'),
            os.environ.get('BND_GITHUB_BRANCH','master'))

def switch_url():return os.environ.get('SWITCH_URL','http://127.0.0.1:18000').rstrip('/')
def approvers():return frozenset(x.strip().casefold() for x in os.environ.get('BND_APPROVERS','user').split(',') if x.strip())
