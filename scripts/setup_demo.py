"""Create a disposable, clearly labelled local demo based on a public GitHub repo."""
from pathlib import Path
import os, subprocess, sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from beforenextdeploy import settings
settings.load_env()
target=settings.state_dir()/'demo-source'
if target.exists():
    if not (target/'.bnd-demo').is_file():
        raise SystemExit('Demo path already exists and is not marked as ours; refusing to touch it.')
    print('Keeping existing disposable demo worktree.')
    raise SystemExit(0)
subprocess.run(['git','clone','--quiet','--depth','1','https://github.com/octocat/Hello-World.git',str(target)],check=True,timeout=90)
(target/'.bnd-demo').write_text('Synthetic training scenario; not a customer project.\n')
(target/'README').write_text('Hello World!\n\nDEMO: a local hotfix exists here but is not on GitHub.\n')
(target/'hotfix.js').write_text('// SYNTHETIC DEMO: local change not committed\nexport const customerMessage = "Thanks for your order.";\n')
(target/'.env').write_text('DEMO_ONLY=not-a-real-secret\n')
print('Created synthetic local changes on a real public GitHub repository. Nothing was pushed.')
