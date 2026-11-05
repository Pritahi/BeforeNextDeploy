"""Optional local AI explanation of *counts only*, never code or credentials."""
from __future__ import annotations
import os
from pathlib import Path
from urllib.parse import urlsplit
import requests
from . import settings

def explain(summary: dict) -> str:
    base=os.environ.get('BND_MODEL_URL','http://127.0.0.1:18099')
    u=urlsplit(base)
    if u.scheme!='http' or u.hostname!='127.0.0.1' or u.port!=18099 or u.path not in ('','/') or u.query or u.fragment or u.username or u.password:
        raise ValueError('AI must use the configured numeric loopback endpoint')
    key=Path(os.environ.get('BND_MODEL_KEY_FILE',str(settings.state_dir()/'model.key'))).read_text().strip()
    if not key or '\n' in key:raise ValueError('Invalid local model key')
    facts=(f"Git reports {summary['status_entries']} status entries. "
           f"A proposed partial bundle selects {summary['included']} entries and excludes {summary['excluded']}. "
           "It uses current working-file bytes, not necessarily staged versions. "
           "The deployed source has NOT been verified. A person must review the bundle for secrets. "
           "This bundle is not a complete backup. Nothing has been deployed.")
    session=requests.Session();session.trust_env=False
    r=session.post(base.rstrip('/')+'/v1/chat/completions',headers={'Authorization':'Bearer '+key},
        json={'model':'local','messages':[{'role':'system','content':
          'Explain the provided facts to a nontechnical teammate in two short sentences. Do not invent facts. Use only the input.'},
          {'role':'user','content':facts}], 'temperature':0.1,'max_tokens':100,'stream':False},
        timeout=(3,90),allow_redirects=False)
    if r.status_code!=200:raise RuntimeError('Local model unavailable')
    text=str(r.json()['choices'][0]['message']['content']).strip().replace('@','@\u200b')[:800]
    if not text:raise RuntimeError('Empty AI answer')
    return text
