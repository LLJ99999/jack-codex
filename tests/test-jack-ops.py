#!/usr/bin/env python3
"""Regression for jack-ops CLI + skill wiring. Zero third-party deps."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPS = ROOT / "codex-skills" / "jack-ops" / "scripts" / "jack_ops.py"
ROLES = (
    "jack-ops",
    "jack-commander",
    "jack-recon",
    "jack-assess",
    "jack-vuln",
    "jack-foothold",
    "jack-internal",
    "jack-preflight",
)


def run(args: list[str], env: dict[str, str], check: bool = True) -> subprocess.CompletedProcess[str]:
    cp = subprocess.run(
        [sys.executable, str(OPS), *args],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    if check and cp.returncode != 0:
        raise AssertionError(f"{args} rc={cp.returncode}\n{cp.stdout}\n{cp.stderr}")
    return cp


def load(cp: subprocess.CompletedProcess[str]) -> dict:
    return json.loads(cp.stdout)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if cond:
            print(f"ok - {name}")
        else:
            failures.append(f"{name}: {detail or 'failed'}")
            print(f"not ok - {name}: {detail}")

    check("ops script exists", OPS.is_file(), str(OPS))
    for name in ROLES:
        path = ROOT / "codex-skills" / name / "SKILL.md"
        check(f"skill {name}", path.is_file() and path.stat().st_size > 0, str(path))

    unlimited = (ROOT / "codex-skills" / "jack-unlimited" / "SKILL.md").read_text(encoding="utf-8")
    check("unlimited routes commander", "$jack-commander" in unlimited)
    pentest = (ROOT / "codex-skills" / "jack-pentest" / "SKILL.md").read_text(encoding="utf-8")
    check("pentest defers to commander", "$jack-commander" in pentest)
    chain = (ROOT / "codex-skills" / "attack-chain" / "SKILL.md").read_text(encoding="utf-8")
    check("attack-chain points at ops", "$jack-ops" in chain)

    cp = subprocess.run([sys.executable, str(OPS), "selftest"], capture_output=True, text=True)
    check("selftest rc=0", cp.returncode == 0, cp.stdout + cp.stderr)
    if cp.returncode == 0:
        data = json.loads(cp.stdout)
        check("selftest pass flag", data.get("selftest") == "pass", str(data))

    tmp = Path(tempfile.mkdtemp(prefix="jack-ops-reg-"))
    env = {**os.environ, "JACK_OPS_HOME": str(tmp)}
    try:
        open_j = load(run(["open", "回归单位", "--scope", "203.0.113.0/24"], env))
        check("open ok", open_j.get("ok") is True)
        nxt = load(run(["next"], env))
        check("next empty -> recon", nxt.get("dispatch") == "recon", str(nxt.get("dispatch")))
        run(["asset-add", "--ip", "203.0.113.10", "--ports", "8080:http", "--tool", "nmap", "--provenance", "active"], env)
        nxt = load(run(["next"], env))
        check("next 1 asset -> assess", nxt.get("dispatch") == "assess", str(nxt.get("dispatch")))
        run(["asset-assess", "--id", "1", "--priority", "high", "--potential", "web-app", "--reason", "login"], env)
        nxt = load(run(["next"], env))
        check("next assessed -> vuln", nxt.get("dispatch") == "vuln", str(nxt.get("dispatch")))
        run(["vuln-add", "--title", "default", "--severity", "high", "--status", "confirmed", "--asset", "1"], env)
        nxt = load(run(["next"], env))
        check("next confirmed -> foothold", nxt.get("dispatch") == "foothold", str(nxt.get("dispatch")))
        bad = run(["step-add", "--stage", "recon", "--title", "x", "--tool", "", "--result", "y"], env, check=False)
        check("empty tool rejected", bad.returncode != 0)
        run(["shell-add", "--url", "http://203.0.113.10/s.jsp", "--type", "behinder", "--password", "p"], env)
        run(
            [
                "tunnel-add", "--kind", "suo5", "--listen", "127.0.0.1:1080",
                "--entry-kind", "target-http", "--command", "suo5 -l 1080",
            ],
            env,
        )
        nxt = load(run(["next"], env))
        check("next foothold -> internal", nxt.get("dispatch") == "internal", str(nxt.get("dispatch")))
        self_only = load(run(
            ["tunnel-add", "--kind", "socks5", "--listen", "127.0.0.1:1081", "--entry-kind", "self-only"],
            env,
        ))
        check("self-only not legit", self_only.get("legit") is False, str(self_only.get("legit")))
        md = load(run(["report-md"], env))
        check("report-md path", Path(md["path"]).is_file(), str(md.get("path")))
        text = Path(md["path"]).read_text(encoding="utf-8")
        check("report has chain heading", "## 攻击链" in text)
        run(["poc-add", "--title", "Tomcat default", "--component", "Tomcat", "--verified"], env)
        found = load(run(["poc-search", "--q", "Tomcat"], env))
        check("poc search", found.get("count", 0) >= 1, str(found.get("count")))
        for key in ("k1", "k2", "k3"):
            run(["slot", "acquire", "--key", key], env)
        full = run(["slot", "acquire", "--key", "k4"], env, check=False)
        check("slot cap 3", full.returncode != 0)
        blocked = load(run(["next"], env))
        check("next blocked at cap", blocked.get("blocked") is True)
    finally:
        pass

    if failures:
        print(f"\n{len(failures)} jack-ops check(s) failed.")
        return 1
    print("\nAll jack-ops checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
