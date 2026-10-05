#!/usr/bin/env python3
"""Inject jack-ops/references/common.md into role SKILL.md files.

Idempotent. Marker block:
  <!-- JACK-OPS-COMMON:BEGIN -->
  ...
  <!-- JACK-OPS-COMMON:END -->
"""
from __future__ import annotations

from pathlib import Path

BEGIN = "<!-- JACK-OPS-COMMON:BEGIN -->"
END = "<!-- JACK-OPS-COMMON:END -->"
ROLES = (
    "jack-commander",
    "jack-recon",
    "jack-assess",
    "jack-vuln",
    "jack-foothold",
    "jack-internal",
    "jack-preflight",
    "jack-ops",
)


def split_block(text: str) -> tuple[str, str]:
    if BEGIN in text and END in text:
        head = text.split(BEGIN, 1)[0].rstrip() + "\n\n"
        tail = text.split(END, 1)[1].lstrip("\n")
        return head, tail
    return text.rstrip() + "\n\n", ""


def main() -> int:
    here = Path(__file__).resolve().parent
    skills = here.parents[1]  # codex-skills
    common = (here.parent / "references" / "common.md").read_text(encoding="utf-8")
    block = f"{BEGIN}\n\n{common.rstrip()}\n\n{END}\n"
    changed = 0
    for name in ROLES:
        path = skills / name / "SKILL.md"
        if not path.is_file():
            print(f"skip missing {path}")
            continue
        original = path.read_text(encoding="utf-8")
        head, tail = split_block(original)
        updated = head + block + (("\n" + tail) if tail else "")
        if updated != original:
            path.write_text(updated, encoding="utf-8")
            changed += 1
            print(f"updated {name}")
        else:
            print(f"ok {name}")
    print(f"changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
