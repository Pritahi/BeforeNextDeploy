"""Two-team-member workflow over one explicitly configured local repository."""
from __future__ import annotations
import re, secrets
from pathlib import Path
from . import bundle, evidence
from .store import Store

CASE = re.compile(r'^[0-9a-f]{16}$')

def safe_text(value, limit=80):
    return str(value).replace('@','@\u200b').replace('\n',' ')[:limit]

def is_human(payload: dict) -> bool:
    # Switch 0.31 can omit sender_kind on legacy bridge messages. Its
    # server-supplied role must still identify a claimed human workspace user.
    return (payload.get('sender_kind') in (None,'user') and payload.get('sender_role') in {'owner','admin','member'}
            and not payload.get('on_behalf_of'))

def can_approve(payload: dict, approvers: frozenset[str]) -> bool:
    return (payload.get('sender_kind') in (None,'user') and payload.get('sender_role') in {'owner','admin'}
            and not payload.get('on_behalf_of') and str(payload.get('sender_name') or '').casefold() in approvers)

class Workflow:
    def __init__(self, store: Store, root: Path, state: Path, approvers: frozenset[str], github_fn):
        self.store,self.root,self.state,self.approvers,self.github_fn=store,root,state,approvers,github_fn

    def new_case(self, actor: str, correlation: str='') -> tuple[str,str]:
        if correlation and not CASE.fullmatch(correlation):raise ValueError('Invalid correlation tag')
        github=self.github_fn()
        s=evidence.scan(self.root,github)
        case=secrets.token_hex(8)
        self.store.create(case,s,actor)
        summary=evidence.public_summary(s)
        if github.get('sha'):
            gh=f"GitHub `{safe_text(github.get('repository'))}` `{safe_text(github.get('branch'))}`: `{github['sha'][:12]}` (live, read-only)."
            compare=('Local **HEAD matches** that branch, but Git reports uncommitted status entries. Selected files reflect working-tree bytes, not necessarily staged versions.'
                if summary['local_matches_remote_head'] else 'Local HEAD and this GitHub branch have different SHAs; ancestry was not checked. Selected files reflect working-tree bytes, not necessarily staged versions.')
        else:
            gh='GitHub branch: **UNKNOWN** (unavailable or not configured).'
            compare='No conclusion about GitHub is possible.'
        tag_note=f"Demo correlation `{correlation}`.\n" if correlation else ''
        msg=(f"**CASE {case} · WORKTREE REVIEW**\n"
          f"{tag_note}Local HEAD `{s['head'][:12]}`. {gh}\n{compare}\n\n"
          f"**{summary['status_entries']} Git status entries** · {summary['included']} eligible for a *partial* change bundle "
          f"({summary['untracked']} untracked, {summary['deleted']} recorded deletions) · {summary['excluded']} excluded.\n"
          f"Snapshot fingerprint `{s['fingerprint'][:16]}`.\n\n"
          "**Production source: UNKNOWN.** This scan does not establish which code is deployed. "
          "Ignored files, binary/large files and likely secrets are omitted; secret detection is incomplete. "
          "No repository contents, repository filenames or credentials are sent to chat or the AI model.\n"
          "Keeper will independently re-check the case before a human decision.")
        return case,msg

    def review(self,case: str,doc_verified: bool=False) -> str:
        if not CASE.fullmatch(case):return 'Give the exact 16-character case ID.'
        item=self.store.get(case)
        if not item:return 'Case not found.'
        if item['state']!='PENDING':return f"Case `{case}` is {item['state']}."
        if not doc_verified:
            return f"**{case} NOT REVIEWED.** The Switch room note could not be matched. No bundle can be saved."
        current=evidence.scan(self.root,item['snapshot'].get('github'))
        if current['fingerprint']!=item['snapshot']['fingerprint']:
            self.store.transition(case,'STALE','keeper',current['fingerprint'])
            return f"**{case} STALE.** Files changed since review; request a fresh scan. No bundle was written."
        if not self.store.mark_reviewed(case,current['fingerprint']):
            return f"**{case} NOT REVIEWED.** The case is no longer pending."
        return (f"**Keeper reviewed `{case}`:** the Switch room note and selected local files still match the scan. "
                "I have not written a bundle. This is not production-source proof. "
                f"A configured owner/admin can type `@keeper save {case}` or `@keeper reject {case}`.")

    def save(self,case: str,payload: dict) -> tuple[str,bool]:
        if not can_approve(payload,self.approvers):return ('Not authorized: only a configured Switch owner/admin can decide.',False)
        if not CASE.fullmatch(case):return ('Give the exact 16-character case ID.',False)
        item=self.store.get(case)
        if not item:return ('Case not found.',False)
        if item['state']!='PENDING':return (f"Cannot save `{case}`: **{item['state']}**. No second bundle was created.",False)
        if not self.store.is_reviewed(case,item['snapshot']['fingerprint']):
            return (f"Cannot save `{case}`: Keeper has not completed the Switch-note review. No bundle was created.",False)
        actor=safe_text(payload.get('sender_name','unknown'))
        current=evidence.scan(self.root,item['snapshot'].get('github'))
        claim=self.store.transition(case,'SAVING',actor,current['fingerprint'])
        if claim!='CLAIMED':return (f"Cannot save `{case}`: **{claim}**. No new bundle was created.",False)
        path=self.state/'bundles'/f'{case}.zip'
        try:
            result=bundle.create_bundle(self.root,path,item['snapshot'])
            self.store.finish(case,'SAVED',actor,f"{result['verified_files']} files verified")
        except bundle.StaleSnapshot:
            self.store.finish(case,'STALE',actor,'Worktree changed during save')
            return (f"**{case} STALE.** Files changed while saving; no bundle was published. Run a fresh scan.",False)
        except Exception as exc:
            self.store.finish(case,'FAILED',actor,type(exc).__name__)
            return (f"**{case} FAILED.** No upload or deployment was attempted. Check private state for a local partial file ({type(exc).__name__}).",False)
        return (f"**{case} · PARTIAL BUNDLE SAVED & CHECKED**\n"
            f"Approved by {safe_text(actor)}. {result['verified_files']} selected file(s) extracted in a temporary directory "
            f"and matched their scan hashes; {result['recorded_deletions']} deletion(s) recorded in the manifest.\n"
            f"Isolated restore drill: {result['base_text_files']} filtered base text file(s) + "
            f"{result['restored_changed_files']} changed file(s), {result['restored_deletions']} deletion(s); "
            f"{result['base_omitted']} base item(s) omitted. No project code was run.\n"
            f"ZIP SHA-256 `{result['zip_sha256']}`.\n"
            f"Private local file: `bundles/{case}.zip` inside the agent's state directory. No upload or deployment occurred.\n"
            "**Not a full backup.** Review for secrets; excluded files, future base-commit availability, environments and production parity are not verified.",True)

    def reject(self,case: str,payload: dict) -> str:
        if not can_approve(payload,self.approvers):return 'Not authorized: only a configured Switch owner/admin can decide.'
        if not CASE.fullmatch(case):return 'Give the exact 16-character case ID.'
        state=self.store.transition(case,'REJECTED',safe_text(payload.get('sender_name','unknown')))
        return f"**{case} {state}.** No bundle was created."

    def verify(self,case: str) -> str:
        if not CASE.fullmatch(case):return 'Give the exact 16-character case ID.'
        item=self.store.get(case)
        if not item or item['state']!='SAVED':return 'No saved bundle for that case.'
        try:result=bundle.verify_bundle(self.state/'bundles'/f'{case}.zip',item['snapshot'])
        except Exception:return f'**{case} VERIFICATION FAILED.** Do not rely on the bundle.'
        return f"**{case} VERIFIED AGAIN:** {result['verified_files']} selected files match their approved hashes. This is not a complete backup."
