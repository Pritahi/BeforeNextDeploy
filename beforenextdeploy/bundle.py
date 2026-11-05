"""Create and independently check a LIMITED change bundle; never deploy or push."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
import zipfile
from . import evidence


class StaleSnapshot(ValueError):
    pass


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify_bundle(path: Path, expected: dict) -> dict:
    """Read ZIP, compare against approved manifest, safely extract and re-hash.

    This verifies selected included bytes, not runtime behavior, secret absence,
    missing files, complete recoverability, or equivalence to production.
    """
    files = [e for e in expected['entries'] if e['kind'] != 'deleted']
    allowed = {'MANIFEST.json'} | {'changes/' + e['path'] for e in files}
    with zipfile.ZipFile(path,'r') as z:
        infos = z.infolist()
        names = [x.filename for x in infos]
        if len(names) != len(set(names)) or set(names) != allowed:
            raise ValueError('Unexpected or duplicate bundle entries')
        if sum(i.file_size for i in infos) > evidence.MAX_TOTAL + 2*1024*1024:
            raise ValueError('Bundle is too large')
        m = json.loads(z.read('MANIFEST.json'))
        if m.get('fingerprint') != expected['fingerprint'] or m.get('head') != expected['head'] or m.get('entries') != expected['entries']:
            raise ValueError('Manifest does not match the approved scan')
        with tempfile.TemporaryDirectory(prefix='beforedeploy-check-') as temp:
            target = Path(temp)
            for e in files:
                rel = e['path']
                if not evidence.safe_path(rel): raise ValueError('Unsafe bundle path')
                info = z.getinfo('changes/' + rel)
                if info.is_dir() or info.file_size != e['size'] or info.file_size > evidence.MAX_FILE:
                    raise ValueError('Unexpected bundle file size')
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symlink in bundle')
                data = z.read(info)
                if sha(data) != e['sha256']: raise ValueError('Bundled bytes do not match')
                output = target.joinpath(*rel.split('/'))
                output.parent.mkdir(parents=True,exist_ok=True)
                with open(output,'xb') as f: f.write(data)
                if sha(output.read_bytes()) != e['sha256']:
                    raise ValueError('Extracted bytes do not match')
    return {'verified_files':len(files),'recorded_deletions':sum(e['kind']=='deleted' for e in expected['entries']),
            'zip_sha256':sha(path.read_bytes())}


def drill_restore(root: Path, path: Path, approved: dict) -> dict:
    """Reconstruct a *filtered* base plus selected changes in a temp directory.

    Never runs the project. Omitted files, dependencies, environment and file
    modes mean this is not a full recovery/deployability test.
    """
    verify_bundle(path,approved)
    root=evidence.validate_root(root)
    raw=evidence.run_git(root,'ls-tree','-r','-z','--full-tree',approved['head'])
    entries=raw.split(b'\0');base_count=0;base_omitted=0;total=0
    with tempfile.TemporaryDirectory(prefix='beforedeploy-restore-') as temp, zipfile.ZipFile(path) as z:
        out=Path(temp)
        for row in entries:
            if not row:continue
            try:
                meta, raw_name=row.split(b'\t',1)
                mode,typ,obj=meta.decode('ascii').split(' ')
                rel=raw_name.decode('utf-8')
                if mode not in {'100644','100755'} or typ!='blob' or not evidence.HEX40.fullmatch(obj) or not evidence.safe_path(rel):
                    base_omitted+=1;continue
                if base_count>=500:
                    base_omitted+=1;continue
                size=int(evidence.run_git(root,'cat-file','-s',obj).strip())
                if size>evidence.MAX_FILE or total+size>evidence.MAX_TOTAL:
                    base_omitted+=1;continue
                data=evidence.run_git(root,'cat-file','blob',obj)
                if len(data)!=size or b'\0' in data or evidence.SECRET.search(data):
                    base_omitted+=1;continue
                data.decode('utf-8')
                dest=out.joinpath(*rel.split('/'));dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(data);base_count+=1;total+=size
            except (ValueError,UnicodeError,RuntimeError,OSError):
                base_omitted+=1;continue
        for entry in approved['entries']:
            rel=entry['path'];dest=out.joinpath(*rel.split('/'))
            if entry['kind']=='deleted':
                if dest.exists():dest.unlink()
                if dest.exists():raise ValueError('Deletion was not applied in restore drill')
                continue
            data=z.read('changes/'+rel)
            dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
            if sha(dest.read_bytes())!=entry['sha256']:
                raise ValueError('Restored changed file does not match approved bytes')
    return {'base_text_files':base_count,'base_omitted':base_omitted,
            'restored_changed_files':sum(e['kind']!='deleted' for e in approved['entries']),
            'restored_deletions':sum(e['kind']=='deleted' for e in approved['entries'])}


def create_bundle(root: Path, target: Path, approved: dict) -> dict:
    root = evidence.validate_root(root)
    # Check before even creating a directory: never write inside the worktree.
    if target.resolve().is_relative_to(root):
        raise ValueError('Choose a private bundle directory outside the scanned worktree')
    target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if target.exists(): raise FileExistsError('Bundle already exists')
    before = evidence.scan(root,approved.get('github'))
    if before['fingerprint'] != approved['fingerprint']:
        raise StaleSnapshot('The worktree changed after the human reviewed it')
    if not approved['entries']:
        raise ValueError('Nothing eligible to save; see exclusions')
    fd, tmp_name = tempfile.mkstemp(prefix='.partial-',suffix='.zip',dir=target.parent)
    os.fchmod(fd,0o600)
    os.close(fd)
    tmp = Path(tmp_name)
    try:
        manifest = {'schema':1,'created_utc':datetime.now(timezone.utc).isoformat(),
                    'head':approved['head'],'fingerprint':approved['fingerprint'],
                    'entries':approved['entries'],'excluded_counts':approved['excluded'],
                    'warning':'Partial changed-file bundle. Not a full backup or proof of deployed source. Review for secrets. Requires base commit for reconstruction.'}
        with zipfile.ZipFile(tmp,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            z.writestr('MANIFEST.json',json.dumps(manifest,indent=2,ensure_ascii=True)+'\n')
            for e in approved['entries']:
                if e['kind']=='deleted': continue
                try: data = evidence.read_beneath(root,e['path'])
                except (OSError,evidence.UnsafeFile) as exc: raise StaleSnapshot('Included file changed or became unreadable') from exc
                if len(data) != e['size'] or sha(data) != e['sha256']:
                    raise StaleSnapshot('Included file changed after approval')
                z.writestr('changes/'+e['path'],data)
        after = evidence.scan(root,approved.get('github'))
        if after['fingerprint'] != approved['fingerprint']:
            raise StaleSnapshot('The worktree changed while the bundle was made')
        result = verify_bundle(tmp,approved)
        result.update(drill_restore(root,tmp,approved))
        # exclusive hard-link avoids silently overwriting another artifact
        os.link(tmp,target)
        os.chmod(target,0o600)
        return result
    finally:
        tmp.unlink(missing_ok=True)
