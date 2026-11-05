"""Create private demo settings from Switch's generated local secrets."""
from pathlib import Path
import os
import sys

switch_env = Path(sys.argv[1])
target = Path(sys.argv[2])
values = {}
for line in switch_env.read_text(encoding="utf-8").splitlines():
    if line and not line.lstrip().startswith("#") and "=" in line:
        k, v = line.split("=", 1); values[k.strip()] = v.strip()
for key in ["AGENT_REGISTRATION_TOKEN", "GATEWAY_ADMIN_EMAIL", "GATEWAY_ADMIN_PASSWORD", "MATTERMOST_USER_PASSWORD"]:
    if not values.get(key): raise SystemExit("Required Switch secret missing: " + key)
if target.exists():
    print("Keeping existing private .env settings.")
    raise SystemExit(0)
out = {
    "SWITCH_URL": "http://127.0.0.1:18000",
    "AGENT_REGISTRATION_TOKEN": values["AGENT_REGISTRATION_TOKEN"],
    "GATEWAY_ADMIN_EMAIL": values["GATEWAY_ADMIN_EMAIL"],
    "GATEWAY_ADMIN_PASSWORD": values["GATEWAY_ADMIN_PASSWORD"],
    "MATTERMOST_URL": "http://127.0.0.1:18065",
    "MATTERMOST_TEAM": values.get("MATTERMOST_TEAM_NAME", "switch"),
    "MATTERMOST_USER": values.get("MATTERMOST_USER", "user"),
    "MATTERMOST_USER_PASSWORD": values["MATTERMOST_USER_PASSWORD"],
    "BND_APPROVERS": values.get("MATTERMOST_USER", "user"),
    "BND_MODEL_URL": "http://127.0.0.1:18099",
}
fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "w", encoding="utf-8") as f:
    f.write("# Private local-demo settings; never commit or share.\n")
    for k, v in out.items():
        if "\n" in v or "\r" in v: raise SystemExit("Invalid generated secret")
        f.write(f"{k}={v}\n")
print("Wrote private local settings to .env (not shown).")
