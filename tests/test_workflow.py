from __future__ import annotations
import json, os, subprocess, tempfile, threading, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from beforenextdeploy import agent, ai, bundle, evidence, workflow
from beforenextdeploy.store import Store

def git(root,*args):
    return subprocess.run(['git','-C',str(root),*args],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE).stdout

class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.dir=Path(self.tmp.name);self.repo=self.dir/'repo';self.repo.mkdir()
        git(self.repo,'init','-q');git(self.repo,'config','user.email','demo@example.invalid');git(self.repo,'config','user.name','demo')
        (self.repo/'app.js').write_text('export const price = 1;\n')
        (self.repo/'gone.js').write_text('old\n')
        (self.repo/'.gitignore').write_text('ignored.js\n')
        git(self.repo,'add','.');git(self.repo,'commit','-qm','base')
        (self.repo/'app.js').write_text('export const price = 2;\n')
        (self.repo/'gone.js').unlink()
        (self.repo/'new.js').write_text('export const fix = true;\n')
        (self.repo/'ignored.js').write_text('ignored\n')
        (self.repo/'.env').write_text('PASSWORD=private\n')
        self.state=self.dir/'state';self.state.mkdir()
        self.store=Store(self.state/'cases.sqlite3')
        self.w=workflow.Workflow(self.store,self.repo,self.state,frozenset({'demo'}),lambda:{'state':'UNKNOWN'})
        self.owner={'sender_kind':'user','sender_role':'owner','sender_name':'demo'}

    def test_live_git_scope_and_exclusions(self):
        s=evidence.scan(self.repo)
        by={e['path']:e for e in s['entries']}
        self.assertEqual(set(by),{'app.js','new.js','gone.js'})
        self.assertEqual(by['gone.js']['kind'],'deleted')
        self.assertEqual(by['new.js']['kind'],'untracked')
        self.assertEqual(s['excluded'],{'private or unsupported path':1})
        self.assertNotIn('ignored.js',str(s))
        self.assertEqual(s['fingerprint'],evidence.fingerprint(s))

    def test_staged_changes_are_included(self):
        git(self.repo,'add','app.js');s=evidence.scan(self.repo)
        self.assertIn('app.js',[e['path'] for e in s['entries']])

    def test_staged_and_working_versions_use_working_bytes(self):
        git(self.repo,'add','app.js')
        (self.repo/'app.js').write_text('export const price = 1;\n')
        snapshot=evidence.scan(self.repo);p=self.state/'index-caveat.zip'
        bundle.create_bundle(self.repo,p,snapshot)
        with zipfile.ZipFile(p) as z:
            self.assertEqual(z.read('changes/app.js'),b'export const price = 1;\n')
        self.assertNotEqual(git(self.repo,'show',':app.js'),b'export const price = 1;\n')

    def test_secret_content_and_symlink_excluded(self):
        (self.repo/'key.js').write_text('api_key = "'+('s'*20)+'"\n')
        (self.repo/'link.js').symlink_to(self.repo/'app.js')
        s=evidence.scan(self.repo)
        self.assertNotIn('key.js',[e['path'] for e in s['entries']])
        self.assertNotIn('link.js',[e['path'] for e in s['entries']])
        self.assertGreaterEqual(sum(s['excluded'].values()),3)

    def test_path_traversal_or_credential_names_rejected(self):
        for p in ('../a.js','/a.js','a/../x.js','a\\x.js','.git/config','.env','test.pem','token.json','x\n.js'):
            self.assertFalse(evidence.safe_path(p),p)

    def test_partial_bundle_extracts_and_checks_selected_bytes(self):
        s=evidence.scan(self.repo);p=self.state/'bundles'/'case.zip'
        r=bundle.create_bundle(self.repo,p,s)
        self.assertEqual(r['verified_files'],2)
        self.assertEqual(r['recorded_deletions'],1)
        self.assertGreaterEqual(r['base_text_files'],3)
        self.assertEqual(r['restored_changed_files'],2)
        self.assertEqual(r['restored_deletions'],1)
        with zipfile.ZipFile(p) as z:
            self.assertEqual(set(z.namelist()),{'MANIFEST.json','changes/app.js','changes/new.js'})
            self.assertEqual(z.read('changes/app.js'),(self.repo/'app.js').read_bytes())
        self.assertEqual(bundle.verify_bundle(p,s)['zip_sha256'],r['zip_sha256'])
        self.assertEqual(p.stat().st_mode & 0o777,0o600)

    def test_inside_worktree_is_refused(self):
        with self.assertRaises(ValueError):bundle.create_bundle(self.repo,self.repo/'save.zip',evidence.scan(self.repo))

    def test_stale_scan_refuses_output(self):
        s=evidence.scan(self.repo);(self.repo/'new.js').write_text('changed after review')
        p=self.state/'bundles'/'case.zip'
        with self.assertRaises(bundle.StaleSnapshot):bundle.create_bundle(self.repo,p,s)
        self.assertFalse(p.exists())

    def test_tampered_archive_fails(self):
        s=evidence.scan(self.repo);p=self.state/'case.zip';bundle.create_bundle(self.repo,p,s)
        with zipfile.ZipFile(p,'a') as z:z.writestr('changes/extra.js','bad')
        with self.assertRaises(ValueError):bundle.verify_bundle(p,s)

    def test_authorization_reject_and_replay(self):
        case,_=self.w.new_case('demo')
        self.assertIn('Not authorized',self.w.save(case,{'sender_role':'member','sender_name':'demo'})[0])
        self.assertIn('Not authorized',self.w.save(case,{'sender_role':'owner','sender_name':'attacker'})[0])
        self.assertIn('Not authorized',self.w.save(case,{**self.owner,'on_behalf_of':'agent'})[0])
        self.assertIn('Not authorized',self.w.save(case,{**self.owner,'sender_kind':'agent'})[0])
        self.assertIn('has not completed',self.w.save(case,self.owner)[0])
        self.assertIn('NOT REVIEWED',self.w.review(case,doc_verified=False))
        self.assertIn('Keeper reviewed',self.w.review(case,doc_verified=True))
        msg,ok=self.w.save(case,self.owner);self.assertTrue(ok,msg)
        self.assertIn('SAVED',self.w.save(case,self.owner)[0])
        self.assertIn('VERIFIED AGAIN',self.w.verify(case))

    def test_rejected_is_final(self):
        case,_=self.w.new_case('demo')
        self.assertIn('REJECTED',self.w.reject(case,self.owner))
        self.assertIn('REJECTED',self.w.save(case,self.owner)[0])
        self.assertFalse((self.state/'bundles'/f'{case}.zip').exists())

    def test_stale_review_does_not_save(self):
        case,_=self.w.new_case('demo');(self.repo/'new.js').write_text('new contents')
        self.assertIn('STALE',self.w.review(case,doc_verified=True))
        self.assertIn('STALE',self.w.save(case,self.owner)[0])

    def test_expired_review_cannot_be_saved(self):
        case,_=self.w.new_case('demo')
        self.assertIn('Keeper reviewed',self.w.review(case,doc_verified=True))
        with self.store.db() as c:c.execute('UPDATE cases SET created=0 WHERE id=?',(case,))
        message,ok=self.w.save(case,self.owner)
        self.assertFalse(ok);self.assertIn('EXPIRED',message)
        self.assertFalse((self.state/'bundles'/f'{case}.zip').exists())

    def test_duplicate_message_dedup(self):
        self.assertTrue(self.store.once('message-1'));self.assertFalse(self.store.once('message-1'))
        self.assertFalse(self.store.once(''))

    def test_concurrent_claim_only_one(self):
        case,_=self.w.new_case('demo');snap=self.store.get(case)['snapshot'];out=[]
        threads=[threading.Thread(target=lambda:out.append(self.store.transition(case,'SAVING','demo',snap['fingerprint']))) for _ in range(6)]
        for t in threads:t.start()
        for t in threads:t.join()
        self.assertEqual(out.count('CLAIMED'),1)
        self.assertEqual(sum(e['action']=='SAVING' for e in self.store.recent()),1)

    def test_looking_at_remote_head_does_not_claim_worktree_clean(self):
        head=evidence.scan(self.repo)['head']
        self.w.github_fn=lambda:{'state':'LIVE','sha':head,'branch':'main','repository':'demo/repo'}
        _,msg=self.w.new_case('demo')
        self.assertIn('uncommitted status entries',msg);self.assertIn('not necessarily staged versions',msg);self.assertIn('Production source: UNKNOWN',msg)

    def test_switch_shared_note_missing_or_mismatched_fails_closed(self):
        case,_=self.w.new_case('demo');item=self.store.get(case)
        a=agent.Agent.__new__(agent.Agent);a.store=self.store;a.room='room';a.conn='connection'
        class Client:
            def __init__(self,docs,body):self.docs=docs;self.body=body
            def op(self,name,params,conn):
                if name=='connect_to_room':return {'documents':self.docs}
                if name=='load_internal_documents':return [{'content':self.body}]
                raise RuntimeError('unexpected operation')
        a.client=Client([],'')
        self.assertFalse(a.check_shared_note(case))
        a.client=Client([{'name':agent.DOC,'id':'doc'}],'case='+case+' fingerprint=wrong state=PENDING')
        self.assertFalse(a.check_shared_note(case))
        a.client=Client([{'name':agent.DOC,'id':'doc'}],f"case={case} fingerprint={item['snapshot']['fingerprint']} state=PENDING")
        self.assertTrue(a.check_shared_note(case))
        self.assertFalse(a.check_shared_note('not-a-real-case'))

    def test_restore_drill_reports_filtered_base_omissions(self):
        git(self.repo,'config','user.email','demo@example.invalid')
        (self.repo/'large.bin').write_bytes(b'\x00binary')
        (self.repo/'secret.txt').write_text('password = "'+('x'*20)+'"\n')
        git(self.repo,'add','large.bin','secret.txt');git(self.repo,'commit','-qm','add unsafe base files')
        snapshot=evidence.scan(self.repo);p=self.state/'restore-test.zip'
        result=bundle.create_bundle(self.repo,p,snapshot)
        self.assertGreaterEqual(result['base_omitted'],2)
        self.assertEqual(result['restored_changed_files'],2)
        self.assertEqual(result['restored_deletions'],1)
        with zipfile.ZipFile(p) as z:
            self.assertNotIn('changes/secret.txt',z.namelist())
            self.assertNotIn('changes/large.bin',z.namelist())

    def test_ai_rejects_nonloopback(self):
        with patch.dict(os.environ,{'BND_MODEL_URL':'https://example.com'}):
            with self.assertRaises(ValueError):ai.explain({'status_entries':1,'included':1,'excluded':0})

    def test_github_configuration_does_not_allow_arbitrary_url(self):
        self.assertEqual(evidence.get_public_github('https://example.com','foo')['state'],'UNKNOWN')

    def test_root_must_be_git_root(self):
        (self.repo/'nested').mkdir()
        with self.assertRaises(ValueError):evidence.scan(self.repo/'nested')

if __name__=='__main__':unittest.main()
