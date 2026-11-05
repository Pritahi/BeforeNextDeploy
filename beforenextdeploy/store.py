"""SQLite state; atomic claim prevents duplicate/replayed human approvals."""
from __future__ import annotations
import json, os, sqlite3, time
from contextlib import contextmanager
from pathlib import Path

TTL = 20 * 60

class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
        self.path = path
        with self.db() as c:
            c.executescript('''
                CREATE TABLE IF NOT EXISTS cases (
                  id TEXT PRIMARY KEY, snapshot TEXT NOT NULL, state TEXT NOT NULL,
                  created REAL NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE IF NOT EXISTS messages (id TEXT PRIMARY KEY, seen REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS reviews (case_id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, reviewed REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS events (time REAL NOT NULL, case_id TEXT NOT NULL,
                    action TEXT NOT NULL, actor TEXT NOT NULL, details TEXT NOT NULL);
            ''')
        os.chmod(path,0o600)

    @contextmanager
    def db(self):
        c=sqlite3.connect(self.path,timeout=10)
        c.row_factory=sqlite3.Row
        try:
            with c: yield c
        finally:
            c.close()

    def once(self, message_id: str) -> bool:
        if not message_id: return False
        with self.db() as c:
            cur=c.execute('INSERT OR IGNORE INTO messages VALUES (?,?)',(message_id,time.time()))
            return cur.rowcount == 1

    def create(self, case_id: str, snapshot: dict, actor: str):
        with self.db() as c:
            c.execute('INSERT INTO cases VALUES (?,?,?,?,?,?)',
                      (case_id,json.dumps(snapshot,sort_keys=True),'PENDING',time.time(),actor,''))
            c.execute('INSERT INTO events VALUES (?,?,?,?,?)',(time.time(),case_id,'PENDING',actor,'Scan recorded'))

    def get(self, case_id: str) -> dict | None:
        with self.db() as c:
            row=c.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
        if not row:return None
        x=dict(row);x['snapshot']=json.loads(x['snapshot']);return x

    def mark_reviewed(self,case_id: str,fingerprint: str) -> bool:
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT state,snapshot FROM cases WHERE id=?',(case_id,)).fetchone()
            if not row or row['state']!='PENDING' or json.loads(row['snapshot'])['fingerprint']!=fingerprint:
                return False
            c.execute('INSERT OR REPLACE INTO reviews VALUES (?,?,?)',(case_id,fingerprint,time.time()))
            c.execute('INSERT INTO events VALUES (?,?,?,?,?)',(time.time(),case_id,'REVIEWED','keeper','Switch note and local snapshot matched'))
            return True

    def is_reviewed(self,case_id: str,fingerprint: str) -> bool:
        with self.db() as c:
            return bool(c.execute('SELECT 1 FROM reviews WHERE case_id=? AND fingerprint=?',(case_id,fingerprint)).fetchone())

    def transition(self, case_id: str, target: str, actor: str, expected_fingerprint: str | None=None, details='') -> str:
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=c.execute('SELECT * FROM cases WHERE id=?',(case_id,)).fetchone()
            if not row:return 'NOT FOUND'
            state=row['state']
            if state != 'PENDING':return state
            snapshot=json.loads(row['snapshot'])
            if time.time()-row['created'] > TTL:
                target, details = 'EXPIRED','Decision window expired'
            elif expected_fingerprint is not None and snapshot['fingerprint'] != expected_fingerprint:
                target, details = 'STALE','Worktree changed after review'
            if target not in {'SAVING','REJECTED','STALE','EXPIRED'}:raise ValueError('invalid transition')
            c.execute('UPDATE cases SET state=?,details=? WHERE id=?',(target,details[:200],case_id))
            c.execute('INSERT INTO events VALUES (?,?,?,?,?)',(time.time(),case_id,target,actor,details[:200]))
            return 'CLAIMED' if target == 'SAVING' else target

    def finish(self,case_id: str,state: str,actor: str,details: str='') -> bool:
        if state not in {'SAVED','STALE','FAILED'}:raise ValueError('invalid final state')
        with self.db() as c:
            c.execute('BEGIN IMMEDIATE')
            cur=c.execute('UPDATE cases SET state=?, details=? WHERE id=? AND state=?',
                          (state,details[:200],case_id,'SAVING'))
            if cur.rowcount:
                c.execute('INSERT INTO events VALUES (?,?,?,?,?)',(time.time(),case_id,state,actor,details[:200]))
            return cur.rowcount==1

    def recent(self,limit=15):
        with self.db() as c:
            return [dict(x) for x in c.execute('SELECT * FROM events ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()]
