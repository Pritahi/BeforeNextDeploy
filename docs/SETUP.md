# Setup and operating guide

## Scope and prerequisites

This is a **local experimental demo**, not a backup or production tool. Use a disposable machine/account and a Git checkout with no confidential material. Keep independent backups. It does not deploy or push. The browser interface is synthetic-demo-only and all its visitors share one local Mattermost user.

Tested: Linux x86-64, Python 3.13, Docker Engine with Compose v2 and CPU inference. Required: Python 3.10+, Python venv/pip support, Git, curl, Docker/Compose and internet access for the initial downloads and public GitHub lookup. Allow several GB of free disk; the model alone is about 397 MB, and container downloads are larger. In the constrained test environment the model could time out while browser video recording competed for resources; its explanation is optional and marked as a draft.

macOS runtime downloads are included in the script but have not been tested. Native Windows and Windows/WSL have not been tested. Availability and terms of upstream images, binaries and models can change.

## Run the synthetic demo

1. Start Docker and obtain this repository, then open a terminal in its folder.
2. Run `bash scripts/start.sh`. The script installs a small Python dependency, downloads a pinned Switch checkout, starts self-hosted Switch/Mattermost/Postgres, creates isolated demo credentials and agents, clones the public test repository, and starts a local Qwen model and demo relay. First run may take several minutes.
3. Open `http://127.0.0.1:18778` **on the same machine**.
4. Click **Scan the demo**, wait until Keeper has reviewed the Switch note, then click **Approve partial bundle** or **Reject**. If approved, **Re-check ZIP** repeats verification.
5. Stop with `bash scripts/stop.sh`. This stops the services but deliberately keeps private state and Docker volumes. Don't delete those volumes if you want to keep previous demo cases.

The private ZIP is at `.runtime/bundles/<case-id>.zip` on the machine hosting the agents. It is **not uploaded** or provided as a public download. It contains source paths and content, so inspect it locally before sharing. The approved base commit must be stored independently; the ZIP is not a complete project snapshot.

## Using the actual Mattermost channel

1. Open `http://127.0.0.1:18065` on the same machine, choose **View in Browser** if prompted, and log in with the local demo user and generated password from your private `.env`. **Never publish or send the password**.
2. Open the private `before-next-deploy` channel.
3. Send `@lookout check` and wait for the case number and Keeper's review.
4. To approve, send `@keeper save <case-id>`; to reject, send `@keeper reject <case-id>`. Only the configured Switch owner/admin name is accepted. Later send `@keeper verify <case-id>` to re-check a saved ZIP.

The visual relay simply sends these real room commands via the one shared local demo account and displays case-specific real messages. The scripted E2E uses the same Mattermost API route, not a fake replay.

## Advanced worktree experiment

For developers only, in a disposable local checkout and private room. This mode is **not security-hardened**. Do not use real secrets, rely on its ZIP as a backup, or run the shared visual relay against your own worktree.

1. Run the synthetic setup first so Switch, the model and the registered agents exist.
2. Stop the synthetic visual relay and the two-agent process by running `bash scripts/stop.sh`; this also stops containers but retains their volumes and state.
3. Start the pinned local Switch stack with `bash scripts/start_switch.sh`. Start the local model through your own trusted loopback setup using the checked model assets and the private key in `.runtime/model.key`, as shown in `scripts/start.sh`. Do not expose the model endpoint publicly.
4. Set these local process environment variables before starting `.venv/bin/python -m beforenextdeploy.agent`: `BND_REPO_ROOT` (absolute Git worktree root), `BND_GITHUB_OWNER`, `BND_GITHUB_REPO`, `BND_GITHUB_BRANCH`, and `BND_APPROVERS` (comma-separated Switch sender names). The GitHub API lookup supports **public** repositories only. Do not put credentials in these fields. `start.sh` intentionally refuses these custom settings because it is demo-only.
5. Use the Mattermost commands above. The synthetic visual relay refuses a custom root. The authorized name-and-role check is only a prototype, not strong identity verification.

No remote branch is fetched, committed, modified or pushed by the scanner. The GitHub branch is read through the public GitHub API. The scanner reads Git status and eligible current working-file bytes; it does not independently capture a different staged index. It performs no deployment-provider check.

## Tests and troubleshooting

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/e2e.py
```

The E2E requires the local services to be running and only operates on the marked synthetic demo checkout. It temporarily modifies a synthetic demo file for a stale-decision test and restores it. It sends real messages in the local private room.

- **Docker unavailable:** start Docker and ensure the current user may access it; the script does not ask for sudo.
- **Port already in use:** stop the conflicting local service and retry. Ports include 13000, 15432, 18000, 18065, 18099 and 18778. Do not forward these services to the public internet.
- **GitHub says UNKNOWN:** network outage, rate limits or a changed upstream branch can prevent the public API lookup. No production inference follows from this.
- **Keeper never reviews:** the mutable Switch document must be available and match the case fingerprint. A failed review cannot be approved. Check private `.runtime/agent.log` for local troubleshooting, but review it before sharing.
- **Changed after review:** the scan becomes stale; run a new scan. The decision window is 20 minutes.
- **Model unavailable or slow:** deterministic scan/decision checks still work; the optional explanation may be absent. Do not treat model text as an authoritative source.
- **Setup fails midway:** rerun `bash scripts/start.sh`; existing private state is reused. Inspect `.runtime/*.log` privately. Existing local state can contain filenames and other sensitive metadata.

The test suite does not establish production security, complete recovery, build success, deployed-source identity, Windows/macOS behavior or all possible race conditions.
