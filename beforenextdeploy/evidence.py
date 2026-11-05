"""Read a configured local Git worktree and a public GitHub branch.

No git add/commit/push/fetch, no deployment, no source text in room messages.
This prototype deliberately exports a *partial* set of changed text files.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
from urllib.parse import quote
import requests

MAX_ENTRIES = 500
MAX_FILE = 2 * 1024 * 1024
MAX_TOTAL = 20 * 1024 * 1024
EXTENSIONS = {'.py','.js','.jsx','.ts','.tsx','.mjs','.cjs','.json','.jsonc',
              '.css','.scss','.html','.md','.mdx','.yaml','.yml','.toml','.txt',
              '.sh','.sql','.go','.rs','.java','.kt','.rb','.php','.xml','.svg',
              '.graphql','.proto','.vue','.svelte','.tf','.lock'}
SAFE_NAMES = {'dockerfile','makefile','readme','license','changelog','.gitignore','.vercelignore','.editorconfig'}
PRIVATE_DIRS = {'.git','.venv','node_modules','.next','.cache','dist','build','coverage',
                'vendor','.model','.switch','.runtime','__pycache__'}
PRIVATE_FILE = re.compile(r'(?i)(^\.env($|\.)|\.pem$|\.key$|\.p12$|\.pfx$|\.keystore$|(^|[._-])(secret|credential|token|password)([._-]|$))')
SECRET = re.compile(rb'(?im)(-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|\bgh[opusr]_[A-Za-z0-9_]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b|\bAIza[0-9A-Za-z_-]{25,}\b|\bsk-[A-Za-z0-9_-]{20,}\b|\bxox[baprs]-[A-Za-z0-9-]{16,}\b|\b(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*[\'\"][^\'\"\s]{16,}[\'\"])')
GITHUB_COMPONENT = re.compile(r'^[A-Za-z0-9_.-]{1,100}$')
BRANCH = re.compile(r'^[A-Za-z0-9._/-]{1,150}$')
HEX40 = re.compile(r'^[0-9a-f]{40}$')


class UnsafeFile(ValueError):
    pass


def run_git(root: Path, *args: str) -> bytes:
    env = dict(os.environ, GIT_OPTIONAL_LOCKS='0', GIT_TERMINAL_PROMPT='0')
    p = subprocess.run(['git','-c','core.fsmonitor=false','-c','core.untrackedCache=false',
                        '-C', str(root), *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       env=env, timeout=20, check=False)
    if p.returncode:
        raise RuntimeError('Unable to read the configured Git worktree')
    return p.stdout


def validate_root(root: Path) -> Path:
    root = root.expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Configured path is not a directory')
    actual = Path(os.fsdecode(run_git(root,'rev-parse','--show-toplevel')).strip()).resolve()
    if actual != root:
        raise ValueError('Configure the Git worktree root, not a subdirectory')
    return root


def safe_path(path: str) -> bool:
    if not path or len(path) > 800 or '\\' in path or any(ord(c) < 32 or ord(c) == 127 for c in path):
        return False
    p = PurePosixPath(path)
    if p.is_absolute() or any(x in ('','.', '..') for x in p.parts):
        return False
    if any(x.lower() in PRIVATE_DIRS for x in p.parts):
        return False
    if any(PRIVATE_FILE.search(x) for x in p.parts):
        return False
    return p.name.lower() in SAFE_NAMES or p.suffix.lower() in EXTENSIONS


def read_beneath(root: Path, rel: str) -> bytes:
    """Open each path component without following symlinks on POSIX.

    No shell and no raw path supplied from chat. Fail closed on unsupported OS.
    """
    if not safe_path(rel) or not hasattr(os, 'O_NOFOLLOW') or not hasattr(os, 'O_DIRECTORY'):
        raise UnsafeFile('unsafe path or platform')
    parts = PurePosixPath(rel).parts
    fds: list[int] = []
    try:
        fd = os.open(str(root), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        fds.append(fd)
        for part in parts[:-1]:
            fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            fds.append(fd)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        fds.append(fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE:
            raise UnsafeFile('not a small regular file')
        chunks, total = [], 0
        while True:
            b = os.read(fd, min(65536, MAX_FILE + 1 - total))
            if not b: break
            chunks.append(b); total += len(b)
            if total > MAX_FILE: raise UnsafeFile('file too large')
        data = b''.join(chunks)
        if b'\0' in data: raise UnsafeFile('binary')
        try: data.decode('utf-8')
        except UnicodeDecodeError as exc: raise UnsafeFile('not UTF-8') from exc
        if SECRET.search(data): raise UnsafeFile('possible secret')
        return data
    finally:
        for fd in reversed(fds): os.close(fd)


def get_public_github(owner: str, repo: str, branch: str = 'main') -> dict:
    if not GITHUB_COMPONENT.fullmatch(owner) or not GITHUB_COMPONENT.fullmatch(repo) or not BRANCH.fullmatch(branch) or '..' in branch or branch.startswith('/'):
        return {'state':'UNKNOWN','reason':'invalid repository/branch configuration'}
    s = requests.Session()
    s.headers.update({'Accept':'application/vnd.github+json','User-Agent':'BeforeNextDeploy/0.1'})
    endpoint = f'https://api.github.com/repos/{quote(owner)}/{quote(repo)}/commits/{quote(branch, safe="")}'
    try:
        r = s.get(endpoint, timeout=(4,8), allow_redirects=False)
        if r.status_code != 200 or len(r.content) > 1024*1024:
            return {'state':'UNKNOWN','reason':f'GitHub returned HTTP {r.status_code}'}
        value = r.json()
        sha = str(value.get('sha','')).lower()
        if not HEX40.fullmatch(sha):
            return {'state':'UNKNOWN','reason':'GitHub response lacked a full SHA'}
        return {'state':'LIVE','sha':sha,'branch':branch,'repository':f'{owner}/{repo}'}
    except (requests.RequestException,ValueError,TypeError):
        return {'state':'UNKNOWN','reason':'GitHub request failed'}


def scan(root: Path, github: dict | None = None) -> dict:
    root = validate_root(root)
    head = os.fsdecode(run_git(root,'rev-parse','--verify','HEAD')).strip().lower()
    if not HEX40.fullmatch(head): raise ValueError('Unsupported Git object format or missing commit')
    raw = run_git(root,'status','--porcelain=v1','-z','--untracked-files=all','--no-renames')
    rows = raw.split(b'\0')
    seen: dict[str,str] = {}
    bad = 0
    for row in rows:
        if not row: continue
        if len(row)<4 or row[2:3] != b' ':
            raise ValueError('Unexpected Git status format')
        try: path = row[3:].decode('utf-8')
        except UnicodeDecodeError:
            bad += 1; continue
        status = row[:2].decode('ascii','replace')
        # If a staged deletion and untracked replacement share a path, the
        # working-file version takes precedence; no deletion is inferred.
        old = seen.get(path)
        seen[path] = '??' if status == '??' or old == '??' else status
    exclusions: dict[str,int] = {}
    def excluded(reason: str): exclusions[reason] = exclusions.get(reason,0)+1
    for _ in range(bad): excluded('unsupported filename')
    entries: list[dict] = []
    total = 0
    for index,(rel,status) in enumerate(sorted(seen.items())):
        if index >= MAX_ENTRIES:
            excluded('entry limit'); continue
        if not safe_path(rel):
            excluded('private or unsupported path'); continue
        try:
            data = read_beneath(root,rel)
        except FileNotFoundError:
            if 'D' in status and status != '??':
                entries.append({'path':rel,'kind':'deleted'})
            else: excluded('missing during scan')
            continue
        except (OSError,UnsafeFile):
            excluded('unreadable, binary, large, symlink or possible secret'); continue
        if total + len(data) > MAX_TOTAL:
            excluded('size limit'); continue
        total += len(data)
        entries.append({'path':rel,'kind':'untracked' if status=='??' else 'changed',
                        'size':len(data),'sha256':hashlib.sha256(data).hexdigest()})
    snapshot = {'schema':1,'head':head,
                'root_binding':hashlib.sha256(os.fsencode(root)).hexdigest(),
                'status_entries':len(seen)+bad,'entries':entries,'excluded':exclusions,
                'github':github or {'state':'UNKNOWN','reason':'not configured'}}
    snapshot['fingerprint'] = fingerprint(snapshot)
    return snapshot


def fingerprint(snapshot: dict) -> str:
    # GitHub is a point-in-time observation, not part of authorization for a
    # local-only bundle. HEAD, included bytes, statuses and exclusions are.
    data = {k:snapshot[k] for k in ('schema','head','root_binding','status_entries','entries','excluded')}
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def public_summary(s: dict) -> dict:
    gh = s.get('github') or {}
    return {'head':s['head'], 'remote_head':gh.get('sha'), 'remote_state':gh.get('state','UNKNOWN'),
            'local_matches_remote_head':s['head']==gh.get('sha') if gh.get('sha') else None,
            'status_entries':s['status_entries'], 'included':len(s['entries']),
            'deleted':sum(e['kind']=='deleted' for e in s['entries']),
            'untracked':sum(e['kind']=='untracked' for e in s['entries']),
            'excluded':sum(s['excluded'].values()), 'fingerprint':s['fingerprint']}
