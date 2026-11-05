# Test report and known limits

## Observed on 5 November 2026 (IST)

| Check | Observed result | Qualification |
|---|---|---|
| Unit tests | 21 passed | Local synthetic Git fixtures; not a security audit |
| Live integration | Pass | Scripted user → private Mattermost → Switch → Lookout → Switch shared note → Keeper → scripted approval → checked local ZIP → Lookout. Also duplicate approval refused, verification repeated, rejection and stale case refused, and real local Qwen draft returned. |
| Clean first-download bootstrap | Pass | Extracted source ZIP into an empty directory in a Linux sandbox with a fresh Docker data store. Pulled the Switch, gateway, setup, Mattermost and PostgreSQL images; fetched the pinned Switch source; downloaded and checksum-checked the local model and runtime; created fresh credentials, databases and agents. All 21 unit tests and the real scripted E2E passed. Docker required a sandbox-only `sudo docker` wrapper. |
| Visual interface | Pass | Automated desktop approval and mobile rejection against real local services; mobile test checked horizontal overflow. Shared synthetic user, not an authorization test for real visitors. |
| Foreign origin / local model | Pass | Demo POST from wrong origin returned 403; unauthenticated model request returned 401. This does not prove the services are hardened against all attacks. |
| Recording | Pass | Case `618bb2b2bc0c8c28` used real Switch messages, model output and ZIP verification on synthetic changes. The approximately 51-second silent captioned video cuts waits; its labeled Mattermost still shows the same case. Opening and closing title cards were added to the original recording. |

The earlier fresh-copy run reused downloaded assets and ran the first 20 unit tests. The later first-download run described above ran all 21. Both used Linux x86-64, Python 3.13, Docker 26.1.5, Compose v2, pinned Switch source and Switch 0.31.0 images, CPU Qwen3 0.6B Q4 and llama.cpp b11669. Existing model weights are re-hashed on start; the runtime archive is checksum-checked on initial download, not re-hashed on every subsequent run.

A browser recording running concurrently with CPU inference caused one local-model read timeout in the constrained environment. The demonstration was then recorded in two segments around the wait; the successful model answer in the final video is from that same case. The workflow does not require the AI draft to authorize or verify the ZIP.

## Run the tests

```bash
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python scripts/e2e.py
```

The E2E requires the local stack and a marked synthetic checkout. It creates local cases and partial ZIPs, sends real Mattermost messages, temporarily changes `hotfix.js` for the stale test and restores its previous bytes. Never point the E2E at a real worktree.

## Important non-guarantees

- A **partial ZIP is not a backup**. It excludes many files, records deletion paths, does not include the base Git commit or environment, and can contain secrets the heuristic misses. Keep a separate tested backup.
- The restore drill uses a filtered base reconstructed into a temporary directory, overlays selected files, checks hashes/deletions and runs no project code. It cannot prove complete recovery, buildability or deployability.
- GitHub HEAD equality does not establish a clean worktree or deployed-source parity. Vercel/production source is not queried and remains unknown.
- Saved content is the current working-file version. Distinct staged versions are not separately captured. Ignored files, binaries, symlinks, unknown extensions, large files, likely secrets and over-limit entries are omitted.
- The model is small and can invent or omit details. Its explanation is a draft; it never authorizes the action.
- The Switch shared note is mutable, and the SQLite log is not a tamper-proof audit. Approval uses a Switch-reported role and configured name, not a verified immutable identity. The synthetic relay shares one demo account. Not suitable for untrusted users or production teams.
- An unexpected failure or interruption after writing starts can leave a private local partial file; inspect local state. No upload or deployment is attempted by this project.
- GitHub, Docker registries, model hosts or download URLs may be unavailable or change. Images use version tags, not digest pins. Cross-platform behavior, long-duration heartbeat reliability, complete supply-chain security, accessibility and all possible races were not established.
