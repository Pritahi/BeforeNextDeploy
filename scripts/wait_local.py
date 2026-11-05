"""Wait for an authenticated local model or local API, with a hard deadline."""
import sys,time,urllib.request,urllib.error
from pathlib import Path
url=sys.argv[1]; key=Path(sys.argv[2]).read_text().strip() if len(sys.argv)>2 else None
end=time.monotonic()+120
while time.monotonic()<end:
    try:
        request=urllib.request.Request(url,headers={"Authorization":"Bearer "+key} if key else {})
        with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(request,timeout=3) as response:
            if response.status==200: raise SystemExit(0)
    except (urllib.error.URLError, TimeoutError):
        time.sleep(1)
raise SystemExit("Local service did not become ready within 120 seconds.")
