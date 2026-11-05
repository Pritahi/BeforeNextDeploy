"""Scripted demo user → Mattermost → Switch → two real agents → local bundle.
Only the disposable demo repository is modified. Credentials are never printed.
"""
from __future__ import annotations
import os,re,sys,time
from pathlib import Path
import requests
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from beforenextdeploy import settings
settings.load_env()

class Mattermost:
    def __init__(self):
        self.base=os.environ.get('MATTERMOST_URL','http://127.0.0.1:18065').rstrip('/')
        self.s=requests.Session();self.s.trust_env=False
        r=self.s.post(self.base+'/api/v4/users/login',json={'login_id':os.environ.get('MATTERMOST_USER','user'),
            'password':os.environ['MATTERMOST_USER_PASSWORD']},timeout=20);r.raise_for_status()
        self.s.headers['Authorization']='Bearer '+r.headers['Token'];self.my_id=r.json()['id']
        r=self.s.get(self.base+'/api/v4/teams/name/'+os.environ.get('MATTERMOST_TEAM','switch'),timeout=20);r.raise_for_status()
        team=r.json()['id']
        r=self.s.get(self.base+f'/api/v4/users/me/teams/{team}/channels',timeout=20);r.raise_for_status()
        ch=next(x for x in r.json() if x.get('name')=='before-next-deploy')
        assert ch['type']=='P','Expected a private channel'
        self.channel=ch['id'];self.consumed=set();self.start=int(time.time()*1000)-1000
    def send(self,text):
        r=self.s.post(self.base+'/api/v4/posts',json={'channel_id':self.channel,'message':text},timeout=20);r.raise_for_status()
    def wait(self,needle,case=None,seconds=120):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            r=self.s.get(self.base+f'/api/v4/channels/{self.channel}/posts',params={'since':self.start},timeout=20);r.raise_for_status()
            for p in sorted(r.json().get('posts',{}).values(),key=lambda x:x.get('create_at',0)):
                text=p.get('message','')
                if p.get('id') not in self.consumed and p.get('user_id')!=self.my_id and needle in text and (not case or case in text):
                    self.consumed.add(p['id']);print('PASS',needle,case or '',flush=True);return text
            time.sleep(1)
        raise TimeoutError(f'No post matched {needle!r} for case {case!r}')
    def scan(self):
        self.send('@lookout check');report=self.wait('WORKTREE REVIEW')
        case=re.search(r'CASE ([0-9a-f]{16})',report).group(1)
        assert 'GitHub' in report and 'Production source: UNKNOWN' in report
        self.wait('Keeper reviewed',case)
        return case,report

def main():
    demo=settings.state_dir()/'demo-source'
    if demo.resolve()!=settings.repo_root().resolve() or not (demo/'.bnd-demo').is_file():
        raise SystemExit('E2E must only run on the marked synthetic demo repository.')
    mm=Mattermost();case,report=mm.scan()
    assert 'live, read-only' in report, 'Public GitHub query was not live'
    mm.send('@keeper save '+case)
    done=mm.wait('PARTIAL BUNDLE SAVED & CHECKED',case)
    mm.wait('Lookout handoff',case)
    assert (settings.state_dir()/'bundles'/f'{case}.zip').is_file()
    mm.send('@keeper save '+case);mm.wait('No second bundle',case)
    mm.send('@keeper verify '+case);mm.wait('VERIFIED AGAIN',case)
    ai=mm.wait('Local AI explanation for',case,seconds=120)
    assert 'draft' in ai,ai
    case2,_=mm.scan();mm.send('@keeper reject '+case2);mm.wait('REJECTED',case2)
    mm.send('@keeper save '+case2);mm.wait('No second bundle',case2)
    assert not (settings.state_dir()/'bundles'/f'{case2}.zip').exists()
    case3,_=mm.scan()
    f=demo/'hotfix.js';orig=f.read_bytes()
    try:
        f.write_bytes(orig+b'// changed after the review\n')
        mm.send('@keeper save '+case3);mm.wait('STALE',case3)
        assert not (settings.state_dir()/'bundles'/f'{case3}.zip').exists()
    finally:f.write_bytes(orig)
    print('END-TO-END PASS: scripted demo user -> private Mattermost -> Switch -> Lookout -> shared note -> Keeper -> scripted demo-user approval -> local checked ZIP -> Switch -> Lookout; reject and stale refused.',flush=True)
if __name__=='__main__':main()
