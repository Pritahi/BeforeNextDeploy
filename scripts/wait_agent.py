"""Wait for both agents, without displaying private credentials."""
from pathlib import Path
import os,sys,time
log=Path(sys.argv[1]);pid=int(sys.argv[2]);end=time.monotonic()+60
while time.monotonic()<end:
    try:os.kill(pid,0)
    except OSError:raise SystemExit('Agent exited before connecting. Inspect .runtime/agent.log privately.')
    if log.is_file():
        text=log.read_text(errors='replace')
        if 'lookout ready' in text and 'keeper ready' in text:raise SystemExit(0)
    time.sleep(.5)
raise SystemExit('Both agents did not connect within 60 seconds; inspect .runtime/agent.log privately.')
