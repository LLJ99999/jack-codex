#!/usr/bin/env python3
"""Jack Ops — local engagement fact store for Codex.

Zero third-party deps. JSON on stdout. Unlogged findings do not exist.
Root: $JACK_OPS_HOME or $CODEX_HOME/.jack-ops or ~/.codex/.jack-ops
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STAGES = ("recon", "internet", "boundary", "internal", "target")
STAGE_NEXT = {
    "recon": "assess",
    "assess": "vuln",
    "vuln": "foothold",
    "foothold": "internal",
    "internal": "done",
}
ROLES = ("plan", "recon", "assess", "vuln", "foothold", "internal")
TEST_STATUS = ("untested", "testing", "tested", "blocked", "abandoned", "no_surface")
PRIORITIES = ("high", "medium", "low")
ENTRY_KINDS = ("target-outbound", "target-http", "target-agent", "self-only")
SHELL_TYPES = ("behinder", "godzilla", "antsword", "other")
POC_KINDS = ("poc", "exp", "script", "template", "payload")
MAX_SLOTS_DEFAULT = 3

DDL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;

CREATE TABLE IF NOT EXISTS meta (
  k TEXT PRIMARY KEY,
  v TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ip TEXT,
  name TEXT,
  state TEXT DEFAULT 'unknown',
  scope TEXT DEFAULT 'external',
  ports TEXT DEFAULT '[]',
  url TEXT,
  title TEXT,
  banner TEXT,
  fingerprint TEXT,
  provenance TEXT,
  tool TEXT,
  priority TEXT,
  potential TEXT,
  assess_reason TEXT,
  assessed_by TEXT,
  test_status TEXT DEFAULT 'untested',
  test_notes TEXT,
  surface TEXT,
  blocked_count INTEGER DEFAULT 0,
  first_seen TEXT,
  last_seen TEXT,
  UNIQUE(ip, name, url)
);

CREATE TABLE IF NOT EXISTS vuln (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id INTEGER,
  cve TEXT,
  title TEXT NOT NULL,
  severity TEXT NOT NULL,
  status TEXT DEFAULT 'candidate',
  target TEXT,
  evidence TEXT,
  gained TEXT,
  source TEXT,
  agent TEXT,
  found_at TEXT
);

CREATE TABLE IF NOT EXISTS credential (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id INTEGER,
  host TEXT,
  username TEXT,
  secret_type TEXT DEFAULT 'password',
  secret_value TEXT,
  privilege TEXT,
  source TEXT,
  tool TEXT,
  note TEXT,
  agent TEXT,
  found_at TEXT,
  UNIQUE(host, username, secret_type)
);

CREATE TABLE IF NOT EXISTS access_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id INTEGER,
  host TEXT,
  username TEXT,
  method TEXT,
  privilege TEXT,
  session_ref TEXT,
  note TEXT,
  agent TEXT,
  obtained_at TEXT
);

CREATE TABLE IF NOT EXISTS webshell (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id INTEGER,
  url TEXT NOT NULL,
  shell_type TEXT,
  pass_key TEXT,
  privilege TEXT,
  status TEXT DEFAULT 'unknown',
  note TEXT,
  agent TEXT,
  created_at TEXT,
  UNIQUE(url, pass_key)
);

CREATE TABLE IF NOT EXISTS tunnel (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  asset_id INTEGER,
  webshell_id INTEGER,
  kind TEXT,
  listen TEXT,
  entry TEXT,
  reach TEXT,
  entry_kind TEXT,
  status TEXT DEFAULT 'unknown',
  command TEXT,
  note TEXT,
  agent TEXT,
  created_at TEXT
);

CREATE TABLE IF NOT EXISTS http_evidence (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  vuln_id INTEGER,
  asset_id INTEGER,
  label TEXT,
  method TEXT,
  url TEXT,
  status INTEGER,
  request TEXT,
  response TEXT,
  note TEXT,
  captured_at TEXT
);

CREATE TABLE IF NOT EXISTS step (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  seq INTEGER,
  stage TEXT,
  title TEXT NOT NULL,
  detail TEXT,
  tool TEXT,
  result TEXT,
  agent TEXT,
  asset_id INTEGER,
  vuln_id INTEGER,
  recorded_at TEXT
);

CREATE TABLE IF NOT EXISTS slot (
  key TEXT PRIMARY KEY,
  role TEXT,
  label TEXT,
  acquired_at TEXT
);

CREATE INDEX IF NOT EXISTS ix_asset_ip ON asset(ip);
CREATE INDEX IF NOT EXISTS ix_asset_prio ON asset(priority);
CREATE INDEX IF NOT EXISTS ix_asset_test ON asset(test_status);
CREATE INDEX IF NOT EXISTS ix_vuln_asset ON vuln(asset_id);
CREATE INDEX IF NOT EXISTS ix_vuln_status ON vuln(status);
CREATE INDEX IF NOT EXISTS ix_step_seq ON step(seq);
CREATE INDEX IF NOT EXISTS ix_cred_host ON credential(host);
"""

KB_DDL = """
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
CREATE TABLE IF NOT EXISTS poc (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  kind TEXT,
  category TEXT,
  cve TEXT,
  component TEXT,
  versions TEXT,
  severity TEXT,
  language TEXT,
  source TEXT,
  source_url TEXT,
  description TEXT,
  usage TEXT,
  content TEXT,
  verified INTEGER DEFAULT 0,
  verified_note TEXT,
  used_count INTEGER DEFAULT 0,
  created_at TEXT,
  updated_at TEXT
);
CREATE INDEX IF NOT EXISTS ix_poc_cve ON poc(cve);
CREATE INDEX IF NOT EXISTS ix_poc_comp ON poc(component);
"""


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def slugify(name: str) -> str:
    s = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", name.strip(), flags=re.UNICODE)
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    return s[:80] or "engagement"


def ops_root() -> Path:
    env = os.environ.get("JACK_OPS_HOME")
    if env:
        return Path(env).expanduser()
    codex = os.environ.get("CODEX_HOME")
    if codex:
        return Path(codex).expanduser() / ".jack-ops"
    return Path.home() / ".codex" / ".jack-ops"


def emit(obj: Any, code: int = 0) -> int:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    return code


def fail(msg: str, **extra: Any) -> int:
    return emit({"ok": False, "error": msg, **extra}, 1)


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(DDL)
    return con


def kb_connect(root: Path) -> sqlite3.Connection:
    path = root / "knowledge.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.executescript(KB_DDL)
    return con


def current_file(root: Path) -> Path:
    return root / "current"


def engagement_dir(root: Path, slug: str) -> Path:
    return root / "engagements" / slug


def db_path(root: Path, slug: str) -> Path:
    return engagement_dir(root, slug) / "ops.db"


def read_current(root: Path) -> str | None:
    p = current_file(root)
    if not p.is_file():
        return None
    v = p.read_text(encoding="utf-8").strip()
    return v or None


def write_current(root: Path, slug: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    current_file(root).write_text(slug + "\n", encoding="utf-8")


def require_db(root: Path, slug: str | None = None) -> tuple[str, sqlite3.Connection]:
    slug = slug or read_current(root)
    if not slug:
        raise SystemExit(fail("no engagement open; run: jack_ops.py open TARGET"))
    path = db_path(root, slug)
    if not path.is_file():
        raise SystemExit(fail(f"engagement db missing: {path}"))
    return slug, connect(path)


def row_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    out = dict(row)
    ports = out.get("ports")
    if isinstance(ports, str):
        try:
            out["ports"] = json.loads(ports)
        except json.JSONDecodeError:
            pass
    return out


def rows(cur: sqlite3.Cursor) -> list[dict[str, Any]]:
    return [row_dict(r) for r in cur.fetchall()]  # type: ignore[misc]


def parse_ports(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    items = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if "/" in part:
            port_s, proto = part.split("/", 1)
        else:
            port_s, proto = part, "tcp"
        if ":" in port_s:
            port_s, service = port_s.split(":", 1)
        else:
            service = None
        items.append({"port": int(port_s), "proto": proto, "service": service})
    return items


def merge_ports(old: str | None, added: list[dict[str, Any]]) -> str:
    try:
        cur = json.loads(old or "[]")
    except json.JSONDecodeError:
        cur = []
    seen = {(int(p.get("port", 0)), str(p.get("proto", "tcp"))) for p in cur}
    for item in added:
        key = (int(item["port"]), str(item.get("proto", "tcp")))
        if key in seen:
            for p in cur:
                if (int(p.get("port", 0)), str(p.get("proto", "tcp"))) == key:
                    if item.get("service") and not p.get("service"):
                        p["service"] = item["service"]
            continue
        seen.add(key)
        cur.append(item)
    return json.dumps(cur, ensure_ascii=False)


def meta_map(con: sqlite3.Connection) -> dict[str, str]:
    return {r["k"]: r["v"] for r in con.execute("SELECT k,v FROM meta")}


def tunnel_legit(entry_kind: str | None) -> bool | None:
    if not entry_kind:
        return None
    if entry_kind == "self-only":
        return False
    if entry_kind in ENTRY_KINDS:
        return True
    return None


# ── commands ────────────────────────────────────────────────────────────────


def cmd_open(args: argparse.Namespace) -> int:
    root = ops_root()
    slug = slugify(args.target)
    d = engagement_dir(root, slug)
    d.mkdir(parents=True, exist_ok=True)
    (d / "runs").mkdir(exist_ok=True)
    (d / "evidence").mkdir(exist_ok=True)
    con = connect(db_path(root, slug))
    ts = now()
    con.execute(
        "INSERT INTO meta(k,v) VALUES('target',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
        (args.target,),
    )
    con.execute(
        "INSERT INTO meta(k,v) VALUES('opened_at',?) ON CONFLICT(k) DO NOTHING",
        (ts,),
    )
    if args.scope:
        con.execute(
            "INSERT INTO meta(k,v) VALUES('scope',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (args.scope,),
        )
    con.execute(
        "INSERT INTO meta(k,v) VALUES('stage',?) ON CONFLICT(k) DO NOTHING",
        ("recon",),
    )
    con.execute(
        "INSERT INTO meta(k,v) VALUES('max_slots',?) ON CONFLICT(k) DO NOTHING",
        (str(MAX_SLOTS_DEFAULT),),
    )
    con.commit()
    write_current(root, slug)
    meta = meta_map(con)
    con.close()
    return emit({"ok": True, "engagement": slug, "root": str(d), "meta": meta})


def cmd_info(_args: argparse.Namespace) -> int:
    root = ops_root()
    slug, con = require_db(root)
    meta = meta_map(con)
    counts = {
        "assets": con.execute("SELECT COUNT(*) FROM asset").fetchone()[0],
        "vulns": con.execute("SELECT COUNT(*) FROM vuln").fetchone()[0],
        "creds": con.execute("SELECT COUNT(*) FROM credential").fetchone()[0],
        "shells": con.execute("SELECT COUNT(*) FROM webshell").fetchone()[0],
        "tunnels": con.execute("SELECT COUNT(*) FROM tunnel").fetchone()[0],
        "steps": con.execute("SELECT COUNT(*) FROM step").fetchone()[0],
        "slots": con.execute("SELECT COUNT(*) FROM slot").fetchone()[0],
    }
    unassessed = con.execute(
        "SELECT COUNT(*) FROM asset WHERE priority IS NULL OR priority=''"
    ).fetchone()[0]
    untested = con.execute(
        "SELECT COUNT(*) FROM asset WHERE test_status='untested'"
    ).fetchone()[0]
    confirmed = con.execute(
        "SELECT COUNT(*) FROM vuln WHERE status IN ('confirmed','exploited')"
    ).fetchone()[0]
    con.close()
    return emit(
        {
            "ok": True,
            "engagement": slug,
            "root": str(engagement_dir(root, slug)),
            "meta": meta,
            "counts": counts,
            "todo": {"unassessed": unassessed, "untested": untested, "confirmed_vulns": confirmed},
        }
    )


def cmd_asset_add(args: argparse.Namespace) -> int:
    if not (args.ip or args.name or args.url):
        return fail("asset add needs --ip or --name or --url")
    slug, con = require_db(ops_root())
    ports = parse_ports(args.ports)
    ts = now()
    existing = None
    if args.ip:
        existing = con.execute("SELECT * FROM asset WHERE ip=?", (args.ip,)).fetchone()
    if existing is None and args.url:
        existing = con.execute("SELECT * FROM asset WHERE url=?", (args.url,)).fetchone()
    if existing is None and args.name and not args.ip:
        existing = con.execute("SELECT * FROM asset WHERE name=?", (args.name,)).fetchone()
    if existing:
        aid = existing["id"]
        merged = merge_ports(existing["ports"], ports)
        con.execute(
            """UPDATE asset SET
                 name=COALESCE(?, name), url=COALESCE(?, url), title=COALESCE(?, title),
                 banner=COALESCE(?, banner), fingerprint=COALESCE(?, fingerprint),
                 tool=COALESCE(?, tool), provenance=COALESCE(?, provenance),
                 scope=COALESCE(?, scope), ports=?, last_seen=?
               WHERE id=?""",
            (
                args.name, args.url, args.title, args.banner, args.fingerprint,
                args.tool, args.provenance, args.scope, merged, ts, aid,
            ),
        )
        con.commit()
        row = con.execute("SELECT * FROM asset WHERE id=?", (aid,)).fetchone()
        con.close()
        return emit({"ok": True, "updated": True, "asset": row_dict(row)})
    con.execute(
        """INSERT INTO asset(ip,name,state,scope,ports,url,title,banner,fingerprint,
                             provenance,tool,first_seen,last_seen)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            args.ip, args.name, args.state or "live", args.scope or "external",
            json.dumps(ports, ensure_ascii=False), args.url, args.title, args.banner,
            args.fingerprint, args.provenance or "active", args.tool, ts, ts,
        ),
    )
    con.commit()
    aid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = con.execute("SELECT * FROM asset WHERE id=?", (aid,)).fetchone()
    con.close()
    return emit({"ok": True, "created": True, "asset": row_dict(row), "engagement": slug})


def cmd_asset_list(args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    sql = "SELECT * FROM asset WHERE 1=1"
    params: list[Any] = []
    if args.q:
        sql += " AND (ip LIKE ? OR name LIKE ? OR url LIKE ? OR title LIKE ? OR fingerprint LIKE ?)"
        q = f"%{args.q}%"
        params.extend([q, q, q, q, q])
    if args.priority:
        sql += " AND priority=?"
        params.append(args.priority)
    if args.status:
        sql += " AND test_status=?"
        params.append(args.status)
    if args.todo:
        sql += " AND (priority IS NULL OR priority='')"
    sql += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 WHEN 'low' THEN 2 ELSE 3 END, id"
    if args.limit:
        sql += " LIMIT ?"
        params.append(int(args.limit))
    items = rows(con.execute(sql, params))
    con.close()
    return emit({"ok": True, "engagement": slug, "count": len(items), "assets": items})


def cmd_asset_assess(args: argparse.Namespace) -> int:
    if args.priority not in PRIORITIES:
        return fail(f"priority must be {PRIORITIES}")
    slug, con = require_db(ops_root())
    cur = con.execute(
        "UPDATE asset SET priority=?, potential=?, assess_reason=?, assessed_by=? WHERE id=?",
        (args.priority, args.potential, args.reason, args.agent or "assess", args.id),
    )
    if cur.rowcount == 0:
        con.close()
        return fail(f"asset {args.id} not found")
    con.commit()
    row = con.execute("SELECT * FROM asset WHERE id=?", (args.id,)).fetchone()
    con.close()
    return emit({"ok": True, "asset": row_dict(row), "engagement": slug})


def cmd_asset_test(args: argparse.Namespace) -> int:
    if args.status not in TEST_STATUS:
        return fail(f"status must be {TEST_STATUS}")
    slug, con = require_db(ops_root())
    row = con.execute("SELECT * FROM asset WHERE id=?", (args.id,)).fetchone()
    if not row:
        con.close()
        return fail(f"asset {args.id} not found")
    notes = row["test_notes"] or ""
    if args.test:
        stamp = now()
        notes = (notes + "\n" if notes else "") + f"[{stamp}] {args.test}"
    blocked = row["blocked_count"] or 0
    if args.blocked:
        blocked += 1
    surface = args.surface if args.surface is not None else row["surface"]
    con.execute(
        "UPDATE asset SET test_status=?, test_notes=?, surface=?, blocked_count=?, last_seen=? WHERE id=?",
        (args.status, notes, surface, blocked, now(), args.id),
    )
    con.commit()
    row = con.execute("SELECT * FROM asset WHERE id=?", (args.id,)).fetchone()
    con.close()
    return emit({"ok": True, "asset": row_dict(row), "engagement": slug})


def cmd_vuln_add(args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    con.execute(
        """INSERT INTO vuln(asset_id,cve,title,severity,status,target,evidence,gained,source,agent,found_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (
            args.asset, args.cve, args.title, args.severity, args.status or "candidate",
            args.target, args.evidence, args.gained, args.source, args.agent or "vuln", now(),
        ),
    )
    con.commit()
    vid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = con.execute("SELECT * FROM vuln WHERE id=?", (vid,)).fetchone()
    con.close()
    return emit({"ok": True, "vuln": row_dict(row), "engagement": slug})


def cmd_vuln_list(args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    sql = "SELECT * FROM vuln WHERE 1=1"
    params: list[Any] = []
    if args.status:
        sql += " AND status=?"
        params.append(args.status)
    if args.asset:
        sql += " AND asset_id=?"
        params.append(args.asset)
    sql += " ORDER BY CASE severity WHEN 'critical' THEN 0 WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END, id"
    items = rows(con.execute(sql, params))
    con.close()
    return emit({"ok": True, "engagement": slug, "count": len(items), "vulns": items})


def cmd_cred_add(args: argparse.Namespace) -> int:
    if not args.host:
        return fail("cred add needs --host")
    slug, con = require_db(ops_root())
    con.execute(
        """INSERT INTO credential(asset_id,host,username,secret_type,secret_value,privilege,source,tool,note,agent,found_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(host,username,secret_type) DO UPDATE SET
             secret_value=excluded.secret_value, privilege=excluded.privilege,
             source=excluded.source, tool=excluded.tool, note=excluded.note, found_at=excluded.found_at""",
        (
            args.asset, args.host, args.user, args.type or "password", args.secret,
            args.privilege, args.source, args.tool, args.note, args.agent, now(),
        ),
    )
    con.commit()
    row = con.execute(
        "SELECT * FROM credential WHERE host=? AND username=? AND secret_type=?",
        (args.host, args.user, args.type or "password"),
    ).fetchone()
    con.close()
    return emit({"ok": True, "credential": row_dict(row), "engagement": slug})


def cmd_access_add(args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    con.execute(
        """INSERT INTO access_session(asset_id,host,username,method,privilege,session_ref,note,agent,obtained_at)
           VALUES(?,?,?,?,?,?,?,?,?)""",
        (
            args.asset, args.host, args.user, args.method, args.privilege,
            args.ref, args.note, args.agent, now(),
        ),
    )
    con.commit()
    aid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = con.execute("SELECT * FROM access_session WHERE id=?", (aid,)).fetchone()
    con.close()
    return emit({"ok": True, "access": row_dict(row), "engagement": slug})


def cmd_shell_add(args: argparse.Namespace) -> int:
    if args.type and args.type not in SHELL_TYPES:
        return fail(f"shell type must be {SHELL_TYPES}")
    slug, con = require_db(ops_root())
    con.execute(
        """INSERT INTO webshell(asset_id,url,shell_type,pass_key,privilege,status,note,agent,created_at)
           VALUES(?,?,?,?,?,?,?,?,?)
           ON CONFLICT(url,pass_key) DO UPDATE SET
             shell_type=excluded.shell_type, privilege=excluded.privilege,
             status=excluded.status, note=excluded.note""",
        (
            args.asset, args.url, args.type, args.password, args.privilege,
            args.status or "unknown", args.note, args.agent, now(),
        ),
    )
    con.commit()
    row = con.execute(
        "SELECT * FROM webshell WHERE url=? AND IFNULL(pass_key,'')=IFNULL(?, '')",
        (args.url, args.password),
    ).fetchone()
    warn = None
    if args.type not in ("behinder", "godzilla"):
        warn = "non-behinder/godzilla shell: operator may not be able to connect"
    con.close()
    return emit({"ok": True, "webshell": row_dict(row), "warning": warn, "engagement": slug})


def cmd_tunnel_add(args: argparse.Namespace) -> int:
    if args.entry_kind and args.entry_kind not in ENTRY_KINDS:
        return fail(f"entry_kind must be {ENTRY_KINDS}")
    slug, con = require_db(ops_root())
    legit = tunnel_legit(args.entry_kind)
    con.execute(
        """INSERT INTO tunnel(asset_id,webshell_id,kind,listen,entry,reach,entry_kind,status,command,note,agent,created_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            args.asset, args.webshell, args.kind, args.listen, args.entry, args.reach,
            args.entry_kind, args.status or "unknown", args.command, args.note, args.agent, now(),
        ),
    )
    con.commit()
    tid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = con.execute("SELECT * FROM tunnel WHERE id=?", (tid,)).fetchone()
    warn = None
    if legit is False:
        warn = "self-only tunnel does not count as boundary breach"
    elif legit is None:
        warn = "entry_kind empty: mark pending, not a breach until updated"
    con.close()
    return emit({"ok": True, "tunnel": row_dict(row), "legit": legit, "warning": warn, "engagement": slug})


def cmd_sessions(_args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    tunnels = rows(con.execute("SELECT * FROM tunnel ORDER BY id"))
    for t in tunnels:
        t["legit"] = tunnel_legit(t.get("entry_kind"))
    out = {
        "ok": True,
        "engagement": slug,
        "shells": rows(con.execute("SELECT * FROM webshell ORDER BY id")),
        "tunnels": tunnels,
        "creds": rows(con.execute("SELECT * FROM credential ORDER BY id")),
        "access": rows(con.execute("SELECT * FROM access_session ORDER BY id")),
    }
    con.close()
    return emit(out)


def cmd_step_add(args: argparse.Namespace) -> int:
    if args.stage not in STAGES:
        return fail(f"stage must be one of {STAGES}")
    if not args.tool or not args.result:
        return fail("step add needs --tool (exact command) and --result (output)")
    slug, con = require_db(ops_root())
    seq = con.execute("SELECT IFNULL(MAX(seq),0)+1 FROM step").fetchone()[0]
    con.execute(
        """INSERT INTO step(seq,stage,title,detail,tool,result,agent,asset_id,vuln_id,recorded_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            seq, args.stage, args.title, args.detail, args.tool, args.result,
            args.agent, args.asset, args.vuln, now(),
        ),
    )
    con.commit()
    sid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = con.execute("SELECT * FROM step WHERE id=?", (sid,)).fetchone()
    con.close()
    return emit({"ok": True, "step": row_dict(row), "engagement": slug})


def cmd_evidence_add(args: argparse.Namespace) -> int:
    if not args.request:
        return fail("evidence add needs --request (raw HTTP)")
    slug, con = require_db(ops_root())
    con.execute(
        """INSERT INTO http_evidence(vuln_id,asset_id,label,method,url,status,request,response,note,captured_at)
           VALUES(?,?,?,?,?,?,?,?,?,?)""",
        (
            args.vuln, args.asset, args.label, args.method, args.url, args.status,
            args.request, args.response, args.note, now(),
        ),
    )
    con.commit()
    eid = con.execute("SELECT last_insert_rowid()").fetchone()[0]
    row = con.execute("SELECT * FROM http_evidence WHERE id=?", (eid,)).fetchone()
    con.close()
    return emit({"ok": True, "evidence": row_dict(row), "engagement": slug})


def cmd_chain(_args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    steps = rows(con.execute("SELECT * FROM step ORDER BY seq, id"))
    by_stage: dict[str, list] = {s: [] for s in STAGES}
    for st in steps:
        by_stage.setdefault(st["stage"], []).append(st)
    current = None
    for s in STAGES:
        if by_stage.get(s):
            current = s
    meta = meta_map(con)
    con.close()
    return emit(
        {
            "ok": True,
            "engagement": slug,
            "stage": meta.get("stage", current or "recon"),
            "counts": {s: len(by_stage.get(s, [])) for s in STAGES},
            "steps": steps,
        }
    )


def cmd_stage(args: argparse.Namespace) -> int:
    if args.set and args.set not in STAGES:
        return fail(f"stage must be one of {STAGES}")
    slug, con = require_db(ops_root())
    if args.set:
        con.execute(
            "INSERT INTO meta(k,v) VALUES('stage',?) ON CONFLICT(k) DO UPDATE SET v=excluded.v",
            (args.set,),
        )
        con.commit()
    meta = meta_map(con)
    con.close()
    return emit({"ok": True, "engagement": slug, "stage": meta.get("stage")})


def collect_report(con: sqlite3.Connection, slug: str) -> dict[str, Any]:
    meta = meta_map(con)
    assets = rows(con.execute("SELECT * FROM asset ORDER BY id"))
    vulns = rows(con.execute("SELECT * FROM vuln WHERE status IN ('confirmed','exploited') ORDER BY id"))
    steps = rows(con.execute("SELECT * FROM step ORDER BY seq, id"))
    shells = rows(con.execute("SELECT * FROM webshell ORDER BY id"))
    tunnels = rows(con.execute("SELECT * FROM tunnel ORDER BY id"))
    for t in tunnels:
        t["legit"] = tunnel_legit(t.get("entry_kind"))
    creds = rows(con.execute(
        "SELECT id,host,username,secret_type,privilege,source,tool FROM credential ORDER BY id"
    ))
    incomplete = []
    for st in steps:
        missing = [k for k in ("tool", "result", "stage") if not st.get(k)]
        if missing:
            incomplete.append({"id": st["id"], "title": st["title"], "missing": missing})
    return {
        "ok": True,
        "engagement": slug,
        "target": meta.get("target"),
        "stage": meta.get("stage"),
        "assets": assets,
        "vulns": vulns,
        "steps": steps,
        "shells": shells,
        "tunnels": tunnels,
        "creds": creds,
        "incomplete": incomplete,
    }


def cmd_report(_args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    out = collect_report(con, slug)
    con.close()
    return emit(out)


def render_markdown(data: dict[str, Any]) -> str:
    lines = [
        f"# Jack Ops 报告 — {data.get('target') or data.get('engagement')}",
        "",
        f"- 靶标: `{data.get('engagement')}`",
        f"- 阶段: `{data.get('stage')}`",
        f"- 资产 {len(data.get('assets') or [])} / 已确认漏洞 {len(data.get('vulns') or [])} / 步骤 {len(data.get('steps') or [])}",
        "",
        "## 入口",
        "",
    ]
    shells = data.get("shells") or []
    if shells:
        for s in shells:
            lines.append(
                f"- shell #{s['id']} `{s.get('shell_type')}` {s.get('url')} priv={s.get('privilege')} status={s.get('status')}"
            )
    else:
        lines.append("- （无 WebShell）")
    tunnels = data.get("tunnels") or []
    if tunnels:
        for t in tunnels:
            flag = "突破" if t.get("legit") else ("不算突破" if t.get("legit") is False else "待确认")
            lines.append(
                f"- tunnel #{t['id']} {t.get('kind')} listen=`{t.get('listen')}` entry_kind={t.get('entry_kind')} [{flag}]"
            )
            if t.get("command"):
                lines.append(f"  - cmd: `{t['command']}`")
    else:
        lines.append("- （无隧道）")
    lines += ["", "## 攻击链", ""]
    steps = data.get("steps") or []
    if not steps:
        lines.append("- （无步骤）")
    for st in steps:
        lines.append(f"### {st.get('seq')}. [{st.get('stage')}] {st.get('title')}")
        lines.append(f"- agent: `{st.get('agent')}`")
        lines.append(f"- tool: `{st.get('tool')}`")
        lines.append(f"- result: {st.get('result')}")
        if st.get("detail"):
            lines.append(f"- detail: {st['detail']}")
        lines.append("")
    lines += ["## 已确认漏洞", ""]
    vulns = data.get("vulns") or []
    if not vulns:
        lines.append("- （无）")
    for v in vulns:
        lines.append(
            f"- #{v['id']} [{v.get('severity')}/{v.get('status')}] {v.get('title')} @ `{v.get('target')}` gained={v.get('gained')}"
        )
        if v.get("evidence"):
            lines.append(f"  - evidence: {v['evidence']}")
    lines += ["", "## 凭据（无明文）", ""]
    creds = data.get("creds") or []
    if not creds:
        lines.append("- （无）")
    for c in creds:
        lines.append(
            f"- #{c['id']} {c.get('host')} / {c.get('username')} ({c.get('secret_type')}) priv={c.get('privilege')} src={c.get('source')}"
        )
    incomplete = data.get("incomplete") or []
    lines += ["", "## 复现缺口", ""]
    if incomplete:
        for item in incomplete:
            lines.append(f"- step #{item['id']} {item.get('title')} missing={item.get('missing')}")
    else:
        lines.append("- 无")
    lines.append("")
    return "\n".join(lines)


def cmd_report_md(args: argparse.Namespace) -> int:
    root = ops_root()
    slug, con = require_db(root)
    data = collect_report(con, slug)
    con.close()
    text = render_markdown(data)
    out = Path(args.out) if args.out else engagement_dir(root, slug) / "report.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return emit({"ok": True, "path": str(out), "incomplete": data["incomplete"], "engagement": slug})


def cmd_next(_args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    meta = meta_map(con)
    n_asset = con.execute("SELECT COUNT(*) FROM asset").fetchone()[0]
    unassessed = con.execute(
        "SELECT COUNT(*) FROM asset WHERE priority IS NULL OR priority=''"
    ).fetchone()[0]
    confirmed = con.execute(
        "SELECT COUNT(*) FROM vuln WHERE status IN ('confirmed','exploited')"
    ).fetchone()[0]
    shells = rows(con.execute("SELECT * FROM webshell"))
    tunnels = rows(con.execute("SELECT * FROM tunnel"))
    slots = con.execute("SELECT COUNT(*) FROM slot").fetchone()[0]
    max_slots = int(meta.get("max_slots") or MAX_SLOTS_DEFAULT)
    deliverable_shell = any(s.get("shell_type") in ("behinder", "godzilla") for s in shells)
    legit_tunnel = any(tunnel_legit(t.get("entry_kind")) is True for t in tunnels)
    reason = []
    role = None
    if n_asset == 0:
        role, reason = "recon", ["no assets logged"]
    elif unassessed > 0:
        role, reason = "assess", [f"{unassessed} assets unassessed"]
    elif confirmed == 0:
        role, reason = "vuln", ["no confirmed/exploited vulns"]
    elif not deliverable_shell or not legit_tunnel:
        missing = []
        if not deliverable_shell:
            missing.append("no behinder/godzilla shell")
        if not legit_tunnel:
            missing.append("no legit tunnel (entry_kind not target-*)")
        role, reason = "foothold", missing
    else:
        role, reason = "internal", ["foothold ready; enumerate internal segments"]
    blocked = slots >= max_slots
    con.close()
    return emit(
        {
            "ok": True,
            "engagement": slug,
            "dispatch": None if blocked else role,
            "skill": None if blocked else f"jack-{role}",
            "blocked": blocked,
            "reason": (["slot full"] if blocked else reason),
            "counts": {
                "assets": n_asset,
                "unassessed": unassessed,
                "confirmed_vulns": confirmed,
                "shells": len(shells),
                "tunnels": len(tunnels),
                "slots": slots,
                "max_slots": max_slots,
            },
        }
    )


def which(name: str) -> str | None:
    return shutil.which(name)


def cmd_preflight(_args: argparse.Namespace) -> int:
    bins = [
        "nmap", "masscan", "nuclei", "sqlmap", "ffuf", "feroxbuster", "gobuster",
        "hydra", "hashcat", "whatweb", "httpx", "subfinder", "dnsx", "naabu",
        "curl", "python3", "frida", "adb",
    ]
    tools = []
    missing = []
    for b in bins:
        p = which(b)
        item = {"name": b, "path": p, "ok": bool(p)}
        tools.append(item)
        if not p:
            missing.append(b)
    env_need = ["FOFA_KEY"]
    env = []
    for k in env_need:
        present = bool(os.environ.get(k))
        env.append({"name": k, "ok": present})
        if not present:
            missing.append(k)
    vps = bool(os.environ.get("REDTEAM_VPS_HOST") or os.environ.get("JACK_VPS_HOST"))
    if not vps:
        missing.append("VPS_HOST")
    status = "ready" if not missing else "degraded"
    return emit(
        {
            "ok": True,
            "status": status,
            "tools": tools,
            "env": env,
            "vps": vps,
            "missing": missing,
            "fallback": {
                "FOFA_KEY": "crt.sh + subfinder + dnsx",
                "VPS_HOST": "account/data/unauth only; no reverse shell / no inbound tunnel",
                "nuclei": "manual request replay via curl",
                "ffuf": "python wordlist loop or gobuster",
            },
        }
    )


def cmd_slot(args: argparse.Namespace) -> int:
    slug, con = require_db(ops_root())
    max_slots = int(
        (con.execute("SELECT v FROM meta WHERE k='max_slots'").fetchone() or ["3"])[0]
    )
    if args.action == "status":
        used = rows(con.execute("SELECT * FROM slot ORDER BY acquired_at"))
        con.close()
        return emit(
            {
                "ok": True,
                "engagement": slug,
                "max": max_slots,
                "used": len(used),
                "free": max(0, max_slots - len(used)),
                "slots": used,
            }
        )
    if args.action == "acquire":
        used = con.execute("SELECT COUNT(*) FROM slot").fetchone()[0]
        if used >= max_slots:
            con.close()
            return fail("slot full", max=max_slots, used=used)
        key = args.key or f"{args.role or 'exec'}-{int(datetime.now().timestamp())}"
        try:
            con.execute(
                "INSERT INTO slot(key,role,label,acquired_at) VALUES(?,?,?,?)",
                (key, args.role, args.label, now()),
            )
        except sqlite3.IntegrityError:
            con.close()
            return fail(f"slot key already held: {key}")
        con.commit()
        used = con.execute("SELECT COUNT(*) FROM slot").fetchone()[0]
        con.close()
        return emit({"ok": True, "key": key, "used": used, "max": max_slots, "engagement": slug})
    if args.action == "release":
        if args.key:
            cur = con.execute("DELETE FROM slot WHERE key=?", (args.key,))
        else:
            row = con.execute("SELECT key FROM slot ORDER BY acquired_at LIMIT 1").fetchone()
            if not row:
                con.close()
                return fail("no slot to release")
            cur = con.execute("DELETE FROM slot WHERE key=?", (row["key"],))
            args.key = row["key"]
        con.commit()
        used = con.execute("SELECT COUNT(*) FROM slot").fetchone()[0]
        con.close()
        if cur.rowcount == 0:
            return fail(f"slot not found: {args.key}")
        return emit({"ok": True, "released": args.key, "used": used, "max": max_slots})
    return fail("slot action must be status|acquire|release")


def poc_code(title: str, cve: str | None) -> str:
    if cve:
        return slugify(cve).lower()
    return slugify(title).lower()


def cmd_poc_add(args: argparse.Namespace) -> int:
    root = ops_root()
    con = kb_connect(root)
    code = args.code or poc_code(args.title, args.cve)
    ts = now()
    con.execute(
        """INSERT INTO poc(code,title,kind,category,cve,component,versions,severity,language,
                           source,source_url,description,usage,content,verified,verified_note,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(code) DO UPDATE SET
             title=excluded.title, kind=excluded.kind, category=excluded.category,
             cve=excluded.cve, component=excluded.component, versions=excluded.versions,
             severity=excluded.severity, language=excluded.language, source=excluded.source,
             source_url=excluded.source_url, description=excluded.description, usage=excluded.usage,
             content=COALESCE(excluded.content, poc.content),
             verified=excluded.verified, verified_note=COALESCE(excluded.verified_note, poc.verified_note),
             updated_at=excluded.updated_at""",
        (
            code, args.title, args.kind, args.category, args.cve, args.component, args.versions,
            args.severity, args.language, args.source, args.source_url, args.description,
            args.usage, args.content, 1 if args.verified else 0, args.verified_note, ts, ts,
        ),
    )
    con.commit()
    row = con.execute("SELECT * FROM poc WHERE code=?", (code,)).fetchone()
    con.close()
    return emit({"ok": True, "poc": row_dict(row)})


def cmd_poc_search(args: argparse.Namespace) -> int:
    con = kb_connect(ops_root())
    sql = "SELECT id,code,title,kind,category,cve,component,severity,verified,used_count FROM poc WHERE 1=1"
    params: list[Any] = []
    if args.q:
        sql += " AND (title LIKE ? OR cve LIKE ? OR component LIKE ? OR description LIKE ? OR content LIKE ?)"
        q = f"%{args.q}%"
        params.extend([q, q, q, q, q])
    if args.cve:
        sql += " AND cve=?"
        params.append(args.cve)
    if args.component:
        sql += " AND component LIKE ?"
        params.append(f"%{args.component}%")
    sql += " ORDER BY verified DESC, used_count DESC, id DESC LIMIT ?"
    params.append(int(args.limit or 50))
    items = rows(con.execute(sql, params))
    con.close()
    return emit({"ok": True, "count": len(items), "pocs": items})


def cmd_poc_get(args: argparse.Namespace) -> int:
    con = kb_connect(ops_root())
    if args.id:
        row = con.execute("SELECT * FROM poc WHERE id=?", (args.id,)).fetchone()
    else:
        row = con.execute("SELECT * FROM poc WHERE code=?", (args.code,)).fetchone()
    con.close()
    if not row:
        return fail("poc not found")
    return emit({"ok": True, "poc": row_dict(row)})


def cmd_poc_use(args: argparse.Namespace) -> int:
    con = kb_connect(ops_root())
    if args.id:
        cur = con.execute("UPDATE poc SET used_count=used_count+1, updated_at=? WHERE id=?", (now(), args.id))
    else:
        cur = con.execute("UPDATE poc SET used_count=used_count+1, updated_at=? WHERE code=?", (now(), args.code))
    if cur.rowcount == 0:
        con.close()
        return fail("poc not found")
    con.commit()
    con.close()
    return emit({"ok": True, "used_on": args.used_on})


def cmd_selftest(_args: argparse.Namespace) -> int:
    import tempfile

    tmp = Path(tempfile.mkdtemp(prefix="jack-ops-"))
    os.environ["JACK_OPS_HOME"] = str(tmp)
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"{name}: {detail or 'failed'}")

    class NS:
        def __init__(self, **kw: Any) -> None:
            self.__dict__.update(kw)

    buf: list[str] = []
    orig_write = sys.stdout.write

    def grab(s: str) -> int:
        buf.append(s)
        return len(s)

    sys.stdout.write = grab  # type: ignore[method-assign]
    try:
        cmd_open(NS(target="示例单位", scope="203.0.113.0/24"))
        cmd_asset_add(NS(
            ip="203.0.113.10", name="oa.example.test", url="http://203.0.113.10:8080/login",
            title="OA", ports="8080:http", tool="nmap", provenance="active",
            banner=None, fingerprint="Tomcat", state="live", scope="external",
        ))
        nxt = json.loads("".join(buf).strip().split("\n{")[-1] if False else "null")
        buf.clear()
        cmd_next(NS())
        nxt = json.loads("".join(buf))
        check("next after 1 asset is assess", nxt.get("dispatch") == "assess", str(nxt.get("dispatch")))
        buf.clear()
        cmd_asset_assess(NS(id=1, priority="high", potential="web-app", reason="Tomcat login", agent="assess"))
        buf.clear()
        cmd_next(NS())
        nxt = json.loads("".join(buf))
        check("next after assess is vuln", nxt.get("dispatch") == "vuln", str(nxt.get("dispatch")))
        buf.clear()
        cmd_vuln_add(NS(
            title="Tomcat default creds", severity="high", target="http://203.0.113.10:8080",
            evidence="tomcat/tomcat 200", asset=1, cve=None, status="confirmed",
            gained="web-app", source="manual", agent="vuln",
        ))
        rc_bad = cmd_step_add(NS(
            stage="recon", title="scan", tool=None, result=None, detail=None,
            agent="recon", asset=1, vuln=None,
        ))
        check("step rejects missing tool", rc_bad != 0)
        buf.clear()
        cmd_step_add(NS(
            stage="recon", title="nmap oa", tool="nmap -sV 203.0.113.10",
            result="8080/tcp open http-proxy", detail="login page", agent="recon", asset=1, vuln=None,
        ))
        buf.clear()
        cmd_next(NS())
        nxt = json.loads("".join(buf))
        check("next after vuln is foothold", nxt.get("dispatch") == "foothold", str(nxt.get("dispatch")))
        buf.clear()
        cmd_shell_add(NS(
            url="http://203.0.113.10:8080/shell.jsp", type="behinder", password="pass",
            privilege="www-data", asset=1, status="online", note="ok", agent="foothold",
        ))
        cmd_tunnel_add(NS(
            kind="suo5", listen="127.0.0.1:1080", entry="http://203.0.113.10:8080/shell.jsp",
            entry_kind="target-http", reach="10.0.0.0/8", asset=1, webshell=1,
            status="active", command="suo5 -t http://203.0.113.10:8080/shell.jsp -l 1080",
            note=None, agent="foothold",
        ))
        buf.clear()
        cmd_next(NS())
        nxt = json.loads("".join(buf))
        check("next after foothold is internal", nxt.get("dispatch") == "internal", str(nxt.get("dispatch")))
        buf.clear()
        cmd_slot(NS(action="acquire", role="recon", label="c-class", key="s1"))
        cmd_slot(NS(action="acquire", role="assess", label="rank", key="s2"))
        cmd_slot(NS(action="acquire", role="vuln", label="nday", key="s3"))
        rc_full = cmd_slot(NS(action="acquire", role="foothold", label="extra", key="s4"))
        check("slot full rejects 4th", rc_full != 0)
        buf.clear()
        cmd_next(NS())
        nxt = json.loads("".join(buf))
        check("next blocked when slots full", nxt.get("blocked") is True)
        buf.clear()
        cmd_poc_add(NS(
            title="Tomcat default", kind="poc", category="weak-password", cve=None,
            component="Tomcat", versions="8/9", severity="high", language="http",
            source="self", source_url=None, description="default creds", usage="curl -u tomcat:tomcat",
            content="tomcat:tomcat", verified=True, verified_note="lab 203.0.113.10", code=None,
        ))
        buf.clear()
        cmd_poc_search(NS(q="Tomcat", cve=None, component="Tomcat", limit=10))
        found = json.loads("".join(buf))
        check("poc search hits", found.get("count", 0) >= 1, str(found.get("count")))
        buf.clear()
        cmd_report_md(NS(out=None))
        md = json.loads("".join(buf))
        check("report.md written", Path(md["path"]).is_file(), md.get("path", ""))
        cmd_info(NS())
    finally:
        sys.stdout.write = orig_write  # type: ignore[method-assign]

    slug, con = require_db(Path(os.environ["JACK_OPS_HOME"]))
    n_asset = con.execute("SELECT COUNT(*) FROM asset").fetchone()[0]
    n_step = con.execute("SELECT COUNT(*) FROM step").fetchone()[0]
    n_shell = con.execute("SELECT COUNT(*) FROM webshell").fetchone()[0]
    n_slot = con.execute("SELECT COUNT(*) FROM slot").fetchone()[0]
    check("asset upserted", n_asset == 1, str(n_asset))
    check("step stored", n_step == 1, str(n_step))
    check("shell stored", n_shell == 1, str(n_shell))
    check("slots at cap", n_slot == 3, str(n_slot))
    con.close()
    shutil.rmtree(tmp, ignore_errors=True)
    os.environ.pop("JACK_OPS_HOME", None)
    if failures:
        return emit({"ok": False, "failures": failures}, 1)
    return emit({"ok": True, "selftest": "pass", "checks": 12})


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="jack_ops.py", description="Jack Ops local fact store")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("open")
    sp.add_argument("target")
    sp.add_argument("--scope")
    sp.set_defaults(func=cmd_open)

    sub.add_parser("info").set_defaults(func=cmd_info)
    sub.add_parser("next").set_defaults(func=cmd_next)

    sp = sub.add_parser("asset-add")
    sp.add_argument("--ip")
    sp.add_argument("--name")
    sp.add_argument("--url")
    sp.add_argument("--title")
    sp.add_argument("--ports", help="8080:http,443/tcp")
    sp.add_argument("--banner")
    sp.add_argument("--fingerprint")
    sp.add_argument("--tool")
    sp.add_argument("--provenance", choices=("passive", "active"))
    sp.add_argument("--state")
    sp.add_argument("--scope", choices=("external", "internal"))
    sp.set_defaults(func=cmd_asset_add)

    sp = sub.add_parser("asset-list")
    sp.add_argument("--q")
    sp.add_argument("--priority", choices=PRIORITIES)
    sp.add_argument("--status", choices=TEST_STATUS)
    sp.add_argument("--todo", action="store_true")
    sp.add_argument("--limit", type=int)
    sp.set_defaults(func=cmd_asset_list)

    sp = sub.add_parser("asset-assess")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--priority", required=True, choices=PRIORITIES)
    sp.add_argument("--potential", required=True)
    sp.add_argument("--reason", required=True)
    sp.add_argument("--agent")
    sp.set_defaults(func=cmd_asset_assess)

    sp = sub.add_parser("asset-test")
    sp.add_argument("--id", type=int, required=True)
    sp.add_argument("--status", required=True, choices=TEST_STATUS)
    sp.add_argument("--test")
    sp.add_argument("--surface")
    sp.add_argument("--blocked", action="store_true")
    sp.set_defaults(func=cmd_asset_test)

    sp = sub.add_parser("vuln-add")
    sp.add_argument("--title", required=True)
    sp.add_argument("--severity", required=True, choices=("critical", "high", "medium", "low", "info"))
    sp.add_argument("--target")
    sp.add_argument("--evidence")
    sp.add_argument("--cve")
    sp.add_argument("--asset", type=int)
    sp.add_argument("--status", choices=("candidate", "confirmed", "exploited", "false-positive"))
    sp.add_argument("--gained")
    sp.add_argument("--source")
    sp.add_argument("--agent")
    sp.set_defaults(func=cmd_vuln_add)

    sp = sub.add_parser("vuln-list")
    sp.add_argument("--status")
    sp.add_argument("--asset", type=int)
    sp.set_defaults(func=cmd_vuln_list)

    sp = sub.add_parser("cred-add")
    sp.add_argument("--host", required=True)
    sp.add_argument("--user")
    sp.add_argument("--secret")
    sp.add_argument("--type", dest="type")
    sp.add_argument("--privilege")
    sp.add_argument("--source")
    sp.add_argument("--tool")
    sp.add_argument("--note")
    sp.add_argument("--asset", type=int)
    sp.add_argument("--agent")
    sp.set_defaults(func=cmd_cred_add)

    sp = sub.add_parser("access-add")
    sp.add_argument("--host")
    sp.add_argument("--user")
    sp.add_argument("--method", required=True)
    sp.add_argument("--privilege")
    sp.add_argument("--ref")
    sp.add_argument("--note")
    sp.add_argument("--asset", type=int)
    sp.add_argument("--agent")
    sp.set_defaults(func=cmd_access_add)

    sp = sub.add_parser("shell-add")
    sp.add_argument("--url", required=True)
    sp.add_argument("--type")
    sp.add_argument("--password")
    sp.add_argument("--privilege")
    sp.add_argument("--status")
    sp.add_argument("--note")
    sp.add_argument("--asset", type=int)
    sp.add_argument("--agent")
    sp.set_defaults(func=cmd_shell_add)

    sp = sub.add_parser("tunnel-add")
    sp.add_argument("--kind", required=True)
    sp.add_argument("--listen", required=True)
    sp.add_argument("--entry")
    sp.add_argument("--entry-kind", dest="entry_kind")
    sp.add_argument("--reach")
    sp.add_argument("--command")
    sp.add_argument("--status")
    sp.add_argument("--note")
    sp.add_argument("--asset", type=int)
    sp.add_argument("--webshell", type=int)
    sp.add_argument("--agent")
    sp.set_defaults(func=cmd_tunnel_add)

    sub.add_parser("sessions").set_defaults(func=cmd_sessions)

    sp = sub.add_parser("step-add")
    sp.add_argument("--stage", required=True, choices=STAGES)
    sp.add_argument("--title", required=True)
    sp.add_argument("--tool", required=True)
    sp.add_argument("--result", required=True)
    sp.add_argument("--detail")
    sp.add_argument("--agent")
    sp.add_argument("--asset", type=int)
    sp.add_argument("--vuln", type=int)
    sp.set_defaults(func=cmd_step_add)

    sp = sub.add_parser("evidence-add")
    sp.add_argument("--request", required=True)
    sp.add_argument("--response")
    sp.add_argument("--url")
    sp.add_argument("--method")
    sp.add_argument("--status", type=int)
    sp.add_argument("--label")
    sp.add_argument("--note")
    sp.add_argument("--vuln", type=int)
    sp.add_argument("--asset", type=int)
    sp.set_defaults(func=cmd_evidence_add)

    sub.add_parser("chain").set_defaults(func=cmd_chain)
    sub.add_parser("report").set_defaults(func=cmd_report)
    sp = sub.add_parser("report-md")
    sp.add_argument("--out")
    sp.set_defaults(func=cmd_report_md)

    sp = sub.add_parser("stage")
    sp.add_argument("--set", dest="set", choices=STAGES)
    sp.set_defaults(func=cmd_stage)

    sub.add_parser("preflight").set_defaults(func=cmd_preflight)

    sp = sub.add_parser("slot")
    sp.add_argument("action", choices=("status", "acquire", "release"))
    sp.add_argument("--role")
    sp.add_argument("--label")
    sp.add_argument("--key")
    sp.set_defaults(func=cmd_slot)

    sp = sub.add_parser("poc-add")
    sp.add_argument("--title", required=True)
    sp.add_argument("--kind", choices=POC_KINDS)
    sp.add_argument("--category")
    sp.add_argument("--cve")
    sp.add_argument("--component")
    sp.add_argument("--versions")
    sp.add_argument("--severity")
    sp.add_argument("--language")
    sp.add_argument("--source")
    sp.add_argument("--source-url", dest="source_url")
    sp.add_argument("--description")
    sp.add_argument("--usage")
    sp.add_argument("--content")
    sp.add_argument("--verified", action="store_true")
    sp.add_argument("--verified-note", dest="verified_note")
    sp.add_argument("--code")
    sp.set_defaults(func=cmd_poc_add)

    sp = sub.add_parser("poc-search")
    sp.add_argument("--q")
    sp.add_argument("--cve")
    sp.add_argument("--component")
    sp.add_argument("--limit", type=int, default=50)
    sp.set_defaults(func=cmd_poc_search)

    sp = sub.add_parser("poc-get")
    sp.add_argument("--id", type=int)
    sp.add_argument("--code")
    sp.set_defaults(func=cmd_poc_get)

    sp = sub.add_parser("poc-use")
    sp.add_argument("--id", type=int)
    sp.add_argument("--code")
    sp.add_argument("--used-on", dest="used_on")
    sp.set_defaults(func=cmd_poc_use)

    sub.add_parser("selftest").set_defaults(func=cmd_selftest)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args) or 0)
    except SystemExit as e:
        if isinstance(e.code, int):
            return e.code
        raise
    except sqlite3.Error as e:
        return fail(f"sqlite: {e}")


if __name__ == "__main__":
    sys.exit(main())
