#!/usr/bin/env python3
"""Static verification for the PFinance handoff/release bundle."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
MIRROR = ROOT / "finance-dashboard.html"
SUMS = ROOT / "SHA256SUMS.txt"


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


def ok(message: str) -> None:
    print(f"OK:   {message}")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_html_identity() -> None:
    if not INDEX.exists() or not MIRROR.exists():
        fail("index.html or finance-dashboard.html is missing")
    if INDEX.read_bytes() != MIRROR.read_bytes():
        fail("index.html and finance-dashboard.html differ")
    ok("index.html and finance-dashboard.html are identical")


def extract_scripts(html: str) -> list[str]:
    return re.findall(r"<script(?:\s[^>]*)?>(.*?)</script>", html, flags=re.I | re.S)


def verify_javascript() -> None:
    html = INDEX.read_text(encoding="utf-8")
    scripts = extract_scripts(html)
    if not scripts:
        fail("no inline scripts found")
    with tempfile.TemporaryDirectory(prefix="pfinance-js-") as tmp:
        for i, source in enumerate(scripts, 1):
            path = Path(tmp) / f"script-{i}.js"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                ["node", "--check", str(path)],
                text=True,
                capture_output=True,
            )
            if result.returncode != 0:
                print(result.stdout)
                print(result.stderr)
                fail(f"JavaScript syntax error in inline script #{i}")
    ok(f"JavaScript syntax is valid in {len(scripts)} inline script block(s)")


def verify_security_and_dependencies() -> None:
    html = INDEX.read_text(encoding="utf-8")
    lowered = html.lower()
    forbidden = ["service_role", "supabase_service", "private_key"]
    found = [token for token in forbidden if token in lowered]
    if found:
        fail("forbidden secret markers found: " + ", ".join(found))

    script_srcs = re.findall(r"<script[^>]+src=[\"']([^\"']+)", html, flags=re.I)
    unexpected = [src for src in script_srcs if "supabase" not in src]
    if unexpected:
        fail("unexpected external JavaScript dependencies: " + ", ".join(unexpected))

    dynamic_imports = re.findall(r"import\([\"']([^\"']+)[\"']\)", html)
    unexpected_imports = [src for src in dynamic_imports if "@supabase/supabase-js" not in src]
    if unexpected_imports:
        fail("unexpected dynamic imports: " + ", ".join(unexpected_imports))

    ok("no service-role markers and no unexpected external JavaScript dependencies")


def verify_checksums() -> None:
    if not SUMS.exists():
        fail("SHA256SUMS.txt is missing")
    errors: list[str] = []
    checked = 0
    for raw in SUMS.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        match = re.match(r"^([0-9a-fA-F]{64})\s+\*?(.+)$", raw)
        if not match:
            errors.append(f"invalid checksum line: {raw}")
            continue
        expected, rel = match.groups()
        rel = rel[2:] if rel.startswith("./") else rel
        path = ROOT / rel
        if not path.exists():
            errors.append(f"missing file: {rel}")
            continue
        actual = sha256(path)
        checked += 1
        if actual.lower() != expected.lower():
            errors.append(f"checksum mismatch: {rel}")
    if errors:
        fail("; ".join(errors))
    ok(f"SHA-256 checksums match for {checked} file(s)")


def verify_version() -> None:
    version_file = ROOT / "VERSION.txt"
    if not version_file.exists():
        fail("VERSION.txt is missing")
    version = version_file.read_text(encoding="utf-8").strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        fail(f"invalid version: {version!r}")
    ok(f"version is {version}")


def main() -> None:
    verify_html_identity()
    verify_javascript()
    verify_security_and_dependencies()
    verify_version()
    verify_checksums()
    print("\nPFinance bundle verification passed.")


if __name__ == "__main__":
    try:
        main()
    except FileNotFoundError as exc:
        fail(f"required tool is missing: {exc.filename}")
