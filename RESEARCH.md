# Research, comparison and judging fit

Research snapshot: 5 November 2026 IST. This is a limited search, not evidence of uniqueness or a prediction of winning.

## Rules and criteria

The [official WeMakeDevs rules](https://www.wemakedevs.org/hackathons/switch/rules) describe 18+/age-of-majority eligibility, sanctions and other exclusions, solo or teams up to four, genuine individual participation, and no automated registration or submission. AI development tools are permitted. Their [event FAQ](https://www.wemakedevs.org/hackathons/switch) gives a 7 November 2026, 11:59 PM IST submission deadline and says the workflow and Switch setup must be built during the event. The user must verify current rules and manually register and submit.

The [DevTools Academy event page](https://www.devtoolsacademy.com/hackathons/flip-the-switch) lists these judging weights: Switch centrality 30%, technical execution/reproducibility 25%, creativity/impact 25%, and presentation/documentation 20%. It asks for a public repository, a short video of the running workflow and a README showing the agents, channel and setup. It describes a joint panel from Switch, DevTools Academy and WeMakeDevs; individual judges were not named on the page when checked. The co-host pages have differed about some prize details, so confirm before relying on a prize amount.

## FallbackDesk vs. BeforeNextDeploy

| Dimension | FallbackDesk | BeforeNextDeploy |
|---|---|---|
| Observable problem | AI-provider quota incident was a clearly labeled simulation; the prototype did not observe/control a real provider router. | Reads actual Git status and a public GitHub branch, while still using a labeled synthetic worktree for the safe demo. Production source remains unknown. |
| Switch's role | One agent, human approval and real team-chat messages. A shared note was created but was not independently read as a gate. | Two distinct agents exchange real messages; the second must independently read and match the Switch shared note before a save. |
| Execution | Real Mattermost/Switch/local-Qwen E2E, rejection/replay/stale checks and unit tests. | Real Mattermost/Switch/local-Qwen E2E, rejection/replay/stale checks, a partial ZIP hash check and filtered restore drill, plus isolated fresh-bootstrap test. |
| Demo risk | A hypothetical fallback can look less compelling than an observed incident; an actual gateway/router is not controlled. | Stronger observable file-state story, but it is still not a complete backup, deployed-source verification or production-ready access control. |
| AI role | Qwen drafts a message; deterministic logic provides guardrails. | Qwen drafts an explanation; deterministic logic provides guardrails. AI is not used to choose, approve or modify files. |
| Prior art | Multiple quota/fallback controls and adjacent workflow tools exist. | Deployment drift checks, source rescue and verified bundles already exist; the combination is not proven new. |

**Assessment:** BeforeNextDeploy is the more compelling *current* Best Business Workflow candidate because Switch-mediated coordination is more central and the demonstrated file/GitHub checks are real. This is a judgment call, not a measured judging score or a guarantee. Its biggest remaining weaknesses are a small model limited to explanation, a partial—not complete—recovery artifact, no deployment-provider evidence and prototype-grade authorization.

## Related work and why it matters

- [Vercel CLI deployment provenance issue](https://github.com/vercel/vercel/issues/15577) illustrates that Git metadata is not always available for a deployment. [Vercel's deployment-file API](https://vercel.com/docs/rest-api/deployments/list-deployment-files) describes a file tree, not necessarily a complete original checkout. These support using **UNKNOWN**, not inventing a production SHA.
- [Agent worktree issue](https://github.com/daniel-ospina/agent-infra/issues/2834), [PatchHarbor](https://github.com/cdoehn/patch-harbor) and [Ship Studio](https://github.com/ship-studio/ship-studio) show adjacent discussions/tools around agent worktrees, snapshots or preserving work. PatchHarbor's README describes a much more complete snapshot including staged, unstaged and non-ignored untracked files; we did not independently test that claim. BeforeNextDeploy is narrower and must not claim superior backup coverage. Its particular angle is the Switch-mediated human decision and shared-note gate. The broad concept is not unique.
- [Existing drift-guard example](https://github.com/somvannda/camroxa/pull/473) and [Vercel Agent](https://vercel.com/agent) are adjacent deployment/release automation. BeforeNextDeploy deliberately does not claim to detect deployed-source drift.
- [OpenCode model fallback](https://github.com/mino29/opencode-model-fallback) and [LLM proxy](https://github.com/marfrit/llm-proxy) are examples of existing routing/fallback mechanisms relevant to FallbackDesk. Capabilities and maintenance can change; the comparison is directional, not a feature-by-feature audit.
- Public projects [Shipdesk](https://github.com/Sahil689172/Shipdesk), [switch-preflight](https://github.com/Asmit-Rai/switch-preflight), [another Switch project](https://github.com/sarath-ppt/switch-hackathon-project), [canary](https://github.com/adeyanjufuhad/canary), and [docdesk](https://github.com/suhailult777/docdesk) describe related Switch work. They are not verified winners and cannot tell us the final competition field.

## Submission honesty checklist

- Say “synthetic repository changes, real local workflow” for the video.
- Say “partial bundle, filtered restore drill, production identity unknown.”
- Say the demo user was scripted and waits were trimmed; the Mattermost final view is a same-case still.
- Do not claim a Vercel integration, source parity, paid-user traction, independent human approval in the recording, novelty, judge endorsement or winning likelihood.
- Review the public source/video for confidential material and third-party terms. Registration, repository publication, video hosting and form submission have not been done by this project.
