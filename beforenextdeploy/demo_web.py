"""Optional synthetic-only visual relay for the real Switch/Mattermost workflow.

Every visitor uses the *same isolated demo Mattermost account*. This is not an
authentication boundary and must never be pointed at a real team's data.
"""
from __future__ import annotations
import argparse,hmac,json,logging,os,re,secrets,threading,time
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit
import requests
from . import settings,evidence
from .store import Store

LOCK=threading.RLock();SESSIONS={};MAX_SESSIONS=100
PAGE=Path(__file__).with_name('demo_ui.html')

class Room:
    def __init__(self):
        self.base=os.environ.get('MATTERMOST_URL','http://127.0.0.1:18065').rstrip('/')
        self.http=requests.Session();self.http.trust_env=False;self.lock=threading.RLock();self.names={}
        r=self.http.post(self.base+'/api/v4/users/login',json={'login_id':os.environ.get('MATTERMOST_USER','user'),
            'password':os.environ['MATTERMOST_USER_PASSWORD']},timeout=20);r.raise_for_status()
        self.http.headers['Authorization']='Bearer '+r.headers['Token'];self.me=r.json()['id']
        r=self.http.get(self.base+'/api/v4/teams/name/'+os.environ.get('MATTERMOST_TEAM','switch'),timeout=20);r.raise_for_status()
        team=r.json()['id'];r=self.http.get(self.base+f'/api/v4/users/me/teams/{team}/channels',timeout=20);r.raise_for_status()
        ch=next(x for x in r.json() if x.get('name')=='before-next-deploy')
        if ch.get('type')!='P':raise RuntimeError('Expected a private demo channel')
        self.channel=ch['id']
    def post(self,text):
        with self.lock:
            r=self.http.post(self.base+'/api/v4/posts',json={'channel_id':self.channel,'message':text},timeout=20)
            r.raise_for_status();return r.json()['id']
    def posts(self,since):
        with self.lock:
            r=self.http.get(self.base+f'/api/v4/channels/{self.channel}/posts',params={'since':since},timeout=15);r.raise_for_status()
            posts=sorted(r.json().get('posts',{}).values(),key=lambda p:p.get('create_at',0))
            for p in posts:
                uid=p.get('user_id')
                if uid and uid!=self.me and uid not in self.names:
                    try:
                        u=self.http.get(self.base+f'/api/v4/users/{uid}',timeout=5)
                        self.names[uid]=u.json().get('username','Agent') if u.status_code==200 else 'Agent'
                    except Exception:self.names[uid]='Agent'
            return posts
    def actor(self,post):
        if post.get('user_id')==self.me:return 'You · shared demo user'
        name=self.names.get(post.get('user_id'),'Agent')
        return {'lookout':'Lookout · scan agent','keeper':'Keeper · review agent'}.get(name,'Switch room')

class DemoServer(ThreadingHTTPServer):
    daemon_threads=True;allow_reuse_address=True
    def __init__(self,host,port):
        demo=(settings.state_dir()/'demo-source').resolve()
        if settings.repo_root().resolve()!=demo or not (demo/'.bnd-demo').is_file() or settings.github_config()!=('octocat','Hello-World','master'):
            raise SystemExit('The visual relay is restricted to the marked synthetic demo and public test repository.')
        super().__init__((host,port),Handler)
        self.room=Room();self.store=Store(settings.state_dir()/'cases.sqlite3')

class Handler(BaseHTTPRequestHandler):
    server:DemoServer;protocol_version='HTTP/1.1'
    def setup(self):super().setup();self.connection.settimeout(10)
    def log_message(self,*args):return
    def reply(self,status,data,mime):
        self.send_response(status);self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer');self.send_header('Connection','close');self.close_connection=True
        self.end_headers()
        try:self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):pass
    def js(self,status,obj):self.reply(status,json.dumps(obj,ensure_ascii=False).encode(),'application/json; charset=utf-8')
    def session(self,create=False):
        sid=self.headers.get('X-BND-Session','')
        with LOCK:
            now=time.time()
            for k in list(SESSIONS):
                if now-SESSIONS[k]['seen']>1800:del SESSIONS[k]
            if sid in SESSIONS:SESSIONS[sid]['seen']=now;return sid,SESSIONS[sid]
            if create and len(SESSIONS)<MAX_SESSIONS:
                sid=secrets.token_hex(32);SESSIONS[sid]={'csrf':secrets.token_hex(32),'seen':now};return sid,SESSIONS[sid]
            return '',None
    def valid_origin(self):
        origin=self.headers.get('Origin')
        if not origin:return True
        u=urlsplit(origin);host=self.headers.get('Host','').lower();allowed={host}
        sandbox=os.environ.get('E2B_SANDBOX_ID','')
        if sandbox and re.fullmatch(r'[a-z0-9-]+',sandbox):allowed.add(f'{self.server.server_address[1]}-{sandbox}.e2b.app'.lower())
        return u.scheme in {'http','https'} and u.netloc.lower() in allowed
    def authorized(self,s):
        return bool(s and self.valid_origin() and hmac.compare_digest(self.headers.get('X-BND-CSRF',''),s['csrf']))
    def do_GET(self):
        if self.path=='/':self.reply(200,PAGE.read_bytes(),'text/html; charset=utf-8');return
        if self.path=='/api/session':
            sid,s=self.session(True)
            if not s:self.js(503,{'error':'Demo is busy'});return
            self.js(200,{'session':sid,'csrf':s['csrf']});return
        if self.path=='/api/state':
            _,s=self.session()
            if not s:self.js(401,{'error':'Session expired'});return
            with LOCK:tag=s.get('tag');since=s.get('since',0);case=s.get('case');start_id=s.get('start_id');sent=s.get('decision_sent',False)
            posts=[]
            if tag:
                try:posts=self.server.room.posts(since)
                except requests.RequestException:pass
                if not case:
                    for p in posts:
                        txt=p.get('message','')
                        match=re.search(r'CASE ([0-9a-f]{16}) · WORKTREE REVIEW',txt)
                        if match and f'Demo correlation `{tag}`' in txt:
                            case=match.group(1)
                            with LOCK:s['case']=case
                            break
            item=self.server.store.get(case) if case else None
            state=item['state'] if item else ('SCANNING' if tag else 'READY')
            reviewed=bool(item and self.server.store.is_reviewed(case,item['snapshot']['fingerprint']))
            selected=[]
            for p in posts:
                text=p.get('message','')
                if (case and case in text) or p.get('id')==start_id:
                    selected.append({'actor':self.server.room.actor(p),'content':text[:5000],'time':p.get('create_at',0)})
            summary=evidence.public_summary(item['snapshot']) if item else None
            self.js(200,{'state':state,'case_id':case,'reviewed':reviewed,'summary':summary,'messages':selected[-12:],'decision_sent':sent});return
        self.js(404,{'error':'Not found'})
    def do_POST(self):
        _,s=self.session()
        if not self.authorized(s):self.js(403,{'error':'Session or origin not authorized'});return
        if self.headers.get('Transfer-Encoding'):self.js(400,{'error':'Unsupported body'});return
        try:n=int(self.headers.get('Content-Length','0'))
        except ValueError:n=-1
        if n<0 or n>256:self.js(400,{'error':'Unsupported body'});return
        if n:self.rfile.read(n)
        if self.path=='/api/start':
            with LOCK:
                if time.time()-s.get('last_start',0)<5:self.js(429,{'error':'Please wait a few seconds.'});return
                old=self.server.store.get(s.get('case','')) if s.get('case') else None
                if old and old['state'] in {'PENDING','SAVING'}:self.js(409,{'error':'Decide the current case first.'});return
                if s.get('tag') and not s.get('case'):self.js(409,{'error':'A scan is already starting.'});return
                tag=secrets.token_hex(8);s.update({'tag':tag,'since':int(time.time()*1000)-500,'case':None,'start_id':None,'last_start':time.time(),'decision_sent':False})
            try:pid=self.server.room.post('@lookout check '+tag)
            except Exception:
                with LOCK:s['tag']=None
                self.js(503,{'error':'Could not reach the demo room.'});return
            with LOCK:s['start_id']=pid
            self.js(202,{'ok':True});return
        if self.path in {'/api/save','/api/reject','/api/verify'}:
            with LOCK:case=s.get('case');item=self.server.store.get(case) if case else None
            action=self.path.rsplit('/',1)[-1]
            if not item:self.js(409,{'error':'No case in this session.'});return
            if action in {'save','reject'}:
                if item['state']!='PENDING' or s.get('decision_sent'):
                    self.js(409,{'error':'There is no pending decision.'});return
                if action=='save' and not self.server.store.is_reviewed(case,item['snapshot']['fingerprint']):
                    self.js(409,{'error':'Keeper has not finished reviewing the shared note.'});return
                with LOCK:s['decision_sent']=True
            if action=='verify' and item['state']!='SAVED':self.js(409,{'error':'No saved bundle to verify.'});return
            try:self.server.room.post(f'@keeper {action} {case}')
            except Exception:
                if action in {'save','reject'}:
                    with LOCK:s['decision_sent']=False
                self.js(503,{'error':'Could not post to the demo room.'});return
            self.js(202,{'ok':True});return
        self.js(404,{'error':'Not found'})

def main():
    settings.load_env();p=argparse.ArgumentParser();p.add_argument('--port',type=int,default=18778)
    p.add_argument('--public-preview',action='store_true',help='bind all interfaces; synthetic isolated demo only')
    a=p.parse_args();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    server=DemoServer('0.0.0.0' if a.public_preview else '127.0.0.1',a.port)
    logging.info('Synthetic demo ready on port %s',a.port)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=='__main__':main()
