#!/usr/bin/env python3
"""Fail when publishable files contain common secrets or private-workspace paths."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
PATTERNS = {
    "absolute user path": re.compile(r"/(?:Users|home)/[^/\s]+/"),
    "OpenAI-style secret": re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "likely phone number": re.compile(r"(?<!\d)\+?\d[\d ()-]{9,}\d(?!\d)"),
}


def publishable_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / item for item in completed.stdout.splitlines() if item]


def main() -> None:
    findings: list[str] = []
    for path in publishable_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in PATTERNS.items():
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                findings.append(f"{path.relative_to(ROOT)}:{line}: {name}")
    if findings:
        raise SystemExit("privacy check failed:\n" + "\n".join(findings))
    print(f"Privacy check passed for {len(publishable_files())} publishable files.")


if __name__ == "__main__":
    main()
