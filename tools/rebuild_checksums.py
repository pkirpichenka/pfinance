#!/usr/bin/env python3
"""Rebuild SHA256SUMS.txt for all project files except the checksum file itself."""

from __future__ import annotations

import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "SHA256SUMS.txt"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


files = sorted(
    p for p in ROOT.rglob("*")
    if p.is_file() and p != OUT and ".git" not in p.parts
)
OUT.write_text(
    "".join(f"{digest(path)}  ./{path.relative_to(ROOT).as_posix()}\n" for path in files),
    encoding="utf-8",
)
print(f"Wrote {OUT} with {len(files)} entries")
