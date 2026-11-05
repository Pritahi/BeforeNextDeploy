# BeforeNextDeploy

### The local fix that never made it to the repository

A team can see a matching local and GitHub **commit** and still have uncommitted work on disk. BeforeNextDeploy asks two Switch teammates to surface that difference, check a shared room note, and let a person decide whether to preserve a **limited local change bundle** before the next release.

> **Prototype, not a backup product.** A partial ZIP and a filtered restore drill are not a complete backup, a deployability test, or proof of what is deployed. No push, upload, rollback or deployment is performed. Secret filtering is heuristic. Production-source identity remains **unknown**.

**[Watch the 51-second demo](demo/BeforeNextDeploy-Demo.mp4)** · [Same case in Mattermost](evidence/mattermost-same-case.png) · [Setup](docs/SETUP.md) · [Tests and boundaries](TESTING.md) · [Research](RESEARCH.md)

The video uses synthetic local edits on the real public `octocat/Hello-World` repository and a scripted demo user. GitHub lookup, Mattermost/Switch messages, Qwen inference, agent review, ZIP checks and the restore drill actually ran. Waiting time was cut; the final Mattermost view is a labeled still of **the same case**. An explanatory opening and closing card were added to the original recording. The video is silent and captioned.

## How the team works

```text
Person in Mattermost (or synthetic demo UI)
    │  @lookout check
    ▼
Lookout ── read local Git status + live public GitHub branch
    │     post redacted facts; write case + fingerprint to a Switch room document
    │     request Keeper review in the room
    ▼
Keeper ── independently load that Switch document and re-scan local files
    │     mark the matching snapshot reviewed; otherwise no save
    ▼
Authorized owner/admin ── approve or reject in the Switch room
    │
    ▼
Keeper ── verify the approved working-file bytes, make a local partial ZIP,
    │     re-extract/re-hash it and run a filtered, temporary restore drill
    ▼
Lookout ── return a handoff in the same room
```

The agents use the actual Switch agent protocol, events and operations—not a visual-only imitation. The mutable Switch document is a **gate**: Keeper must load the note and match the case and fingerprint; a missing or mismatched note blocks saving. Switch also delivers the requests, agent-to-agent handoffs, human decision and room history. If Switch is unavailable, this chat workflow and its review gate do not operate.

Lookout also asks the locally hosted **Qwen3 0.6B Q4** model to explain sanitized counts and caveats. It does not receive repository file contents, repository filenames or credentials. The small model's text is explicitly labeled a draft and may be wrong; deterministic checks and the human decision, not the model, control the save. The AI explanation is optional: the safety path can continue if local inference is unavailable.

## Try the isolated demo

The shortest route requires a Linux x86-64 machine with Python 3.10+, Git, curl, Docker Engine and Compose v2. Docker must already be running. The first run downloads Switch/Mattermost container images, a pinned Switch source revision, a CPU runtime and a ~397 MB model. Allow several GB of disk and time for downloads. No paid model/API key is needed; network/data or electricity costs may still apply.

```bash
git clone https://github.com/Pritahi/BeforeNextDeploy.git BeforeNextDeploy
cd BeforeNextDeploy
bash scripts/start.sh
```

Then open **http://127.0.0.1:18778** on that same machine:

1. Select **Scan the demo**.
2. Wait for **Keeper checks the shared note** to finish.
3. Select **Approve partial bundle** or **Reject**. Approval creates a local ZIP; it does not deploy.
4. If approved, select **Re-check ZIP** to verify the selected file hashes again.

`start.sh` creates fresh private credentials automatically for a self-hosted demo; do not put `.env`, `.runtime`, `.switch` or `.model` in a public repository. Stop the demo with `bash scripts/stop.sh`. Stopping retains private state and Docker volumes.

The visual relay is strictly limited to the marked synthetic repository. **All its visitors share one demo Mattermost account; it is not an authentication boundary. Do not expose it to untrusted users or connect it to a real team.** The normal start binds to loopback. The optional preview mode is for an isolated synthetic demonstration only.

The automated setup was tested on Linux x86-64. The script contains macOS download options, but macOS and Windows/WSL were **not tested**. An additional clean Linux sandbox test downloaded the images, Switch source, model and runtime afresh, then passed the end-to-end flow. That sandbox used a `sudo docker` wrapper; see [TESTING.md](TESTING.md) for the exact scope and limitations.

## What gets preserved—and what does not

- The scanner includes eligible, small, UTF-8 **current working-file versions** for tracked/staged/untracked status entries. If the staged index differs from the working file, the staged version is **not** separately captured.
- Eligible deletions are recorded in the manifest. The ZIP is not a copy of the base repository; preserve the referenced Git commit separately.
- Ignored files, unsupported extensions, binaries, large files, symlinks, paths or contents that look secret, and over-limit entries are omitted. The filters can miss secrets and can exclude necessary files.
- The ZIP contains selected content and repository paths; the local SQLite database contains paths and hashes. They are sensitive even though repository filenames and contents are not put into room messages or the model prompt. Review the artifact before sharing it.
- The temporary restore drill reads a **filtered subset** of the local Git base, overlays selected ZIP entries and checks changed bytes/deletions. It runs no project code and does not test dependencies, configuration, file modes, build success, production behavior or future availability of the base commit.
- GitHub HEAD is a point-in-time public API lookup; it does not prove local worktree equality, ancestry or what is running on a hosting provider. This prototype has **no Vercel/deployment-provider integration**.
- Authorization currently trusts a Switch-provided owner/admin role plus an allowlisted sender name. It is not immutable-identity authorization or a production security boundary. The mutable room note and SQLite event log are not tamper-proof compliance records.

For developer experimentation against a configured local worktree, see [advanced configuration](docs/SETUP.md#advanced-worktree-experiment). Do not use the synthetic public relay for that. Keep an independent real backup.

Related tools already exist: for example, [PatchHarbor](https://github.com/cdoehn/patch-harbor) describes a more complete repository snapshot, including staged and unstaged changes; that claim has not been independently tested here. Our prototype is deliberately narrower and focuses on a Switch-mediated team decision, not superior backup coverage. See [RESEARCH.md](RESEARCH.md).

## Verification

On 5 November 2026, **21 unit tests** passed; they cover exclusion, safe paths, staged/working differences, bundle integrity, restore omissions, stale changes, a missing/mismatched Switch note, rejection and replay/concurrency. A real end-to-end test used a scripted demo user and the self-hosted Mattermost → Switch → Lookout → shared note → Keeper flow, including approval, ZIP checking, duplicate refusal, verification, rejection, stale refusal and a real local-Qwen draft. A clean sandbox setup generated new credentials, database and agents, downloaded the images and model assets afresh, and passed the E2E and all 21 unit tests. See [TESTING.md](TESTING.md).

## Credits and licenses

Our project source is MIT-licensed; see [LICENSE](LICENSE). Switch is downloaded separately and has an Apache 2.0 license **limited by a modified Commons Clause**, including restrictions on selling; see its [license](https://github.com/sandbox-quantum/switch/blob/b09e7ce4cb6abfad3783d3d7d75f45a09608dc45/LICENSE). Qwen3 GGUF, llama.cpp, Mattermost, Docker images and Python dependencies have their own terms. See [NOTICE.md](NOTICE.md); review third-party terms before redistribution or commercial use.
