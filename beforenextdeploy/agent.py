"""Two actual Switch agents: Lookout scans; Keeper verifies and saves on approval."""
from __future__ import annotations
import argparse, json, logging, os, re, threading, uuid
from pathlib import Path
import requests
from . import ai,evidence,settings
from .store import Store
from .switch_client import SwitchClient
from .workflow import Workflow,is_human

log=logging.getLogger('beforedeploy')
NAMES=('lookout','keeper')
DOC='BeforeNextDeploy decision notes'

def read_state():
    return json.loads((settings.state_dir()/'agents.json').read_text(encoding='utf-8'))

def save_state(state):
    path=settings.state_dir()/'agents.json'
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w',encoding='utf-8') as f:json.dump(state,f,indent=2)
    os.chmod(path,0o600)

def bootstrap():
    path=settings.state_dir()/'agents.json'
    state=read_state() if path.exists() else {'agents':{}}
    token=os.environ['AGENT_REGISTRATION_TOKEN']
    for name in NAMES:
        if name not in state['agents']:
            agent_id,key=SwitchClient.register(settings.switch_url(),token,name)
            state['agents'][name]={'agent_id':agent_id,'api_key':key,'connection_id':str(uuid.uuid4())}
            save_state(state)
    s=requests.Session()
    r=s.post(settings.switch_url()+'/gateway/auth/login',json={'email':os.environ['GATEWAY_ADMIN_EMAIL'],
        'password':os.environ['GATEWAY_ADMIN_PASSWORD']},timeout=20);r.raise_for_status()
    for name in NAMES:
        agent_id=state['agents'][name]['agent_id']
        r=s.put(settings.switch_url()+f'/gateway/agents/{agent_id}/addressing-policy',json={'policy':None},timeout=20)
        r.raise_for_status()
    if not state.get('room_id'):
        a=state['agents']['lookout'];client=SwitchClient(settings.switch_url(),a['agent_id'],a['api_key'])
        conn=str(uuid.uuid4());stream=client.events(conn)
        try:
            frame=next(stream)
            if frame.kind!='connection_state':raise RuntimeError('No Switch connection state')
            room=client.op('create_room',{'name':'before-next-deploy',
                'description':'People and two agents inspect and preserve local changes before a release.',
                'agent_names':list(NAMES),'user_names':[os.environ.get('MATTERMOST_USER','user')],
                'channel_type':'channel_private',
                'instructions':'Never deploy or push. Keeper may create a local partial bundle only after configured human approval.'},conn)
            state['room_id']=room['id'];save_state(state)
        finally:stream.close()
    print('Two Switch agents and a private Mattermost room are registered. Keys are private.')

class Agent:
    def __init__(self,name,state):
        self.name=name;self.root_state=state;self.room=state['room_id'];cfg=state['agents'][name]
        self.client=SwitchClient(settings.switch_url(),cfg['agent_id'],cfg['api_key']);self.conn=cfg['connection_id']
        self.generation=None;self.connected=threading.Event();self.stop=threading.Event();self.last_id=None
        self.store=Store(settings.state_dir()/'cases.sqlite3')
        self.workflow=Workflow(self.store,settings.repo_root(),settings.state_dir(),settings.approvers(),
                               lambda:evidence.get_public_github(*settings.github_config()))
        self.doc_id=None

    def heartbeat(self):
        while not self.stop.is_set():
            if self.connected.is_set():
                try:self.client.beat(self.conn,self.generation)
                except requests.HTTPError as exc:
                    log.warning('%s heartbeat refused HTTP %s',self.name,exc.response.status_code if exc.response is not None else '?')
                except requests.RequestException:log.warning('%s heartbeat unavailable',self.name)
            self.stop.wait(2)

    def connect(self):
        info=self.client.op('connect_to_room',{'room_id':self.room},self.conn)
        if self.name=='lookout':
            for doc in info.get('documents') or []:
                if doc.get('name')==DOC:self.doc_id=doc.get('id') or doc.get('document_id')
        log.info('%s connected; %s participants',self.name,len(info.get('participants') or []))

    def update_doc(self):
        if self.name!='lookout':return False
        rows=self.store.recent(20)
        if not rows:return False
        content='BeforeNextDeploy decision notes (prototype, mutable; not a compliance audit).\n\n'
        seen=set()
        for event in rows:
            case=event['case_id']
            if case in seen:continue
            seen.add(case);item=self.store.get(case)
            if item:
                content+=f"case={case} fingerprint={item['snapshot']['fingerprint']} state={item['state']}\n"
        content+='\nRecent events:\n'+'\n'.join(f"- {e['case_id']} · {e['action']} · {e['details']}" for e in rows)
        try:
            if self.doc_id:
                self.client.op('update_room_document',{'document_id':self.doc_id,'content':content},self.conn)
            else:
                result=self.client.op('create_room_document',{'name':DOC,
                    'description':'Recent local partial-bundle decisions; no source files are stored here.',
                    'instructions':'Mutable prototype notes; not an immutable audit log.','content':content},self.conn)
                self.doc_id=result.get('document_id')
            return bool(self.doc_id)
        except Exception as exc:
            log.warning('Shared notes unavailable (%s)',type(exc).__name__)
            return False

    def check_shared_note(self,case):
        try:
            item=self.store.get(case)
            if not item:return False
            info=self.client.op('connect_to_room',{'room_id':self.room},self.conn)
            docs=info.get('documents') or []
            doc=next(d for d in docs if d.get('name')==DOC)
            doc_id=doc.get('id') or doc.get('document_id')
            loaded=self.client.op('load_internal_documents',{'ids':[doc_id]},self.conn)
            marker=f"case={case} fingerprint={item['snapshot']['fingerprint']} state=PENDING"
            return isinstance(loaded,list) and any(marker in str(d.get('content','')) for d in loaded)
        except Exception as exc:
            log.warning('Keeper could not read Switch note (%s)',type(exc).__name__)
            return False

    def explain_later(self,case):
        def worker():
            try:
                item=self.store.get(case)
                answer=ai.explain(evidence.public_summary(item['snapshot']))
                self.client.post(self.room,f'**Local AI explanation for `{case}` (draft; verify against the facts above):**\n> '+answer.replace('\n','\n> '))
            except Exception as exc:
                log.warning('Optional local AI unavailable (%s)',type(exc).__name__)
                try:self.client.post(self.room,f'Local AI explanation for `{case}` unavailable. The recorded facts and human decision remain available.')
                except Exception:pass
        threading.Thread(target=worker,daemon=True).start()

    def process(self,payload):
        body=str(payload.get('body') or '').strip()
        match=re.match(rf'(?is)^@?{self.name}(?:\s+|$)(.*)$',body)
        if not match:return
        cmdline=match.group(1).strip();cmd,_,args=cmdline.partition(' ');cmd=cmd.casefold();args=args.strip().lower()
        if self.name=='lookout':
            if cmd in ('','help'):
                self.client.post(self.room,'**BeforeNextDeploy** · `@lookout check` scans the configured Git worktree and public GitHub branch. Keeper checks the case; an authorized human may save a limited local bundle. No deploy or push.');return
            if cmd=='check':
                if not is_human(payload):self.client.post(self.room,'A claimed workspace human must start a scan.');return
                if args and not re.fullmatch(r'[0-9a-f]{16}',args):
                    self.client.post(self.room,'Use `@lookout check` without extra text.');return
                case,msg=self.workflow.new_case(str(payload.get('sender_name') or 'unknown'),args)
                self.client.post(self.room,msg)
                if self.update_doc():
                    self.client.post(self.room,f'@keeper review {case}')
                else:
                    self.client.post(self.room,f'**{case}:** Switch room note unavailable; no save is permitted. Try a fresh scan when it is available.')
                self.explain_later(case);return
            if cmd=='complete':
                item=self.store.get(args)
                if item and item['state']=='SAVED':
                    self.client.post(self.room,f'**Lookout handoff `{args}`:** partial bundle recorded. Review exclusions and secrets, and keep the base commit. Production-source identity remains unknown.')
                    self.update_doc()
                return
        else:
            if cmd in ('','help'):
                self.client.post(self.room,'**Keeper** · `@keeper review <case>`, `@keeper save <case>`, `@keeper reject <case>`, `@keeper verify <case>`. Only an authorized human can save or reject.');return
            if cmd=='review':
                verified=self.check_shared_note(args)
                self.client.post(self.room,self.workflow.review(args,doc_verified=verified));return
            if cmd=='save':
                message,saved=self.workflow.save(args,payload)
                self.client.post(self.room,message)
                if saved:self.client.post(self.room,f'@lookout complete {args}')
                return
            if cmd=='reject':self.client.post(self.room,self.workflow.reject(args,payload));return
            if cmd=='verify':self.client.post(self.room,self.workflow.verify(args));return
        self.client.post(self.room,f'Unknown command. Try `@{self.name} help`.')

    def run(self):
        threading.Thread(target=self.heartbeat,daemon=True).start()
        while not self.stop.is_set():
            try:
                for e in self.client.events(self.conn,self.room,self.last_id):
                    if e.event_id:self.last_id=e.event_id
                    if e.kind=='connection_state':
                        self.generation=e.data.get('generation');self.connected.set();self.connect()
                        log.info('%s ready',self.name)
                    elif e.kind=='message' and e.data.get('room_id')==self.room:
                        p=e.data.get('payload') or {}
                        if not p.get('addressed') or not self.store.once(str(p.get('message_id') or '')):continue
                        try:self.process(p)
                        except Exception as exc:
                            log.warning('%s failed safely (%s)',self.name,type(exc).__name__)
                            try:self.client.post(self.room,'Request failed safely. No deployment or push was attempted.')
                            except Exception:pass
                    elif e.kind=='evicted':break
            except Exception as exc:log.warning('%s stream disconnected (%s)',self.name,type(exc).__name__)
            self.connected.clear();self.stop.wait(1)

def main():
    settings.load_env();logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s')
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',action='store_true');args=p.parse_args()
    if args.bootstrap:bootstrap();return
    state=read_state()
    agents=[Agent(n,state) for n in NAMES]
    for a in agents:threading.Thread(target=a.run,daemon=True).start()
    try:threading.Event().wait()
    except KeyboardInterrupt:
        for a in agents:a.stop.set()

if __name__=='__main__':main()
