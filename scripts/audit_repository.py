"""Fail when tracked files contain secrets, local artifacts, or oversized data."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

MAX_TRACKED_BYTES = 5 * 1024 * 1024

BLOCKED_PATHS = {
    "environment file": re.compile(r"(?i)(^|/)\.env(?:\..+)?$"),
    "Streamlit secrets": re.compile(r"(?i)(^|/)secrets?\.toml$"),
    "credential file": re.compile(
        r"(?i)(^|/)(?:credentials?.*|service-account.*)\.json$"
    ),
    "private key or certificate": re.compile(r"(?i)\.(?:pem|key|p12|pfx)$"),
    "generated cache": re.compile(
        r"(?i)(^|/)(?:\.cache|cache|__pycache__|\.pytest_cache|\.ruff_cache)(?:/|$)"
    ),
    "local database or pickle": re.compile(r"(?i)\.(?:pkl|db|sqlite|sqlite3)$"),
    "generated route HTML": re.compile(
        r"(?i)(^|/)(?:mapa_base|ruta_simple_emergencia|ruta_multiple_emergencia)\.html$"
    ),
}

SECRET_PATTERNS = {
    "private key": re.compile(
        rb"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"
    ),
    "GitHub token": re.compile(rb"gh[pousr]_[A-Za-z0-9]{20,}"),
    "OpenAI key": re.compile(rb"sk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "AWS access key": re.compile(rb"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{35}"),
    "Slack token": re.compile(rb"xox[baprs]-[0-9A-Za-z-]{20,}"),
    "credential assignment": re.compile(
        rb"(?i)(?:password|passwd|api[_-]?key|client[_-]?secret|access[_-]?token)"
        rb"\s*[:=]\s*[\"'][^\"'\r\n]{8,}[\"']"
    ),
    "credential in URL": re.compile(rb"https?://[^/\s:@]+:[^/\s@]+@"),
}


def git_output(*arguments: str) -> bytes:
    completed = subprocess.run(
        ["git", *arguments],
        check=True,
        capture_output=True,
    )
    return completed.stdout


def check_path(normalized: str, label: str, findings: set[str]) -> None:
    for description, pattern in BLOCKED_PATHS.items():
        if pattern.search(normalized):
            findings.add(f"{label}: blocked {description}")


def check_content(label: str, data: bytes, findings: set[str]) -> None:
    size = len(data)
    if size > MAX_TRACKED_BYTES:
        findings.add(
            f"{label}: tracked file is {size} bytes; limit is {MAX_TRACKED_BYTES}"
        )

    for description, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(data):
            line = data.count(b"\n", 0, match.start()) + 1
            findings.add(f"{label}:{line}: possible {description}")


def tracked_files() -> list[Path]:
    return [
        Path(raw.decode("utf-8", errors="replace"))
        for raw in git_output("ls-files", "-z").split(b"\0")
        if raw
    ]


def audit_current(findings: set[str]) -> None:
    for path in tracked_files():
        normalized = path.as_posix()
        check_path(normalized, normalized, findings)

        if path.is_symlink():
            findings.add(f"{normalized}: tracked symbolic link")
            continue
        if not path.is_file():
            findings.add(f"{normalized}: tracked path is not a regular file")
            continue

        check_content(normalized, path.read_bytes(), findings)


def audit_history(findings: set[str]) -> None:
    scanned_blobs: set[str] = set()
    commits = git_output("rev-list", "--all").decode("ascii").splitlines()

    for commit in commits:
        records = git_output("ls-tree", "-rz", "--full-tree", commit).split(b"\0")
        for record in records:
            if not record:
                continue

            metadata, raw_path = record.split(b"\t", maxsplit=1)
            mode, object_type, object_id = metadata.decode("ascii").split()
            normalized = raw_path.decode("utf-8", errors="replace")
            label = f"history:{commit[:12]}:{normalized}"
            check_path(normalized, label, findings)

            if mode == "120000":
                findings.add(f"{label}: tracked symbolic link")
                continue
            if object_type != "blob" or object_id in scanned_blobs:
                continue

            scanned_blobs.add(object_id)
            data = git_output("cat-file", "blob", object_id)
            check_content(label, data, findings)


def audit(include_history: bool = False) -> list[str]:
    findings: set[str] = set()
    audit_current(findings)
    if include_history:
        audit_history(findings)
    return sorted(findings)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--history",
        action="store_true",
        help="also inspect every blob reachable from the local Git history",
    )
    arguments = parser.parse_args()

    findings = audit(include_history=arguments.history)
    if findings:
        print("Repository privacy audit failed:", file=sys.stderr)
        for finding in findings:
            print(f"- {finding}", file=sys.stderr)
        return 1
    print("Repository privacy audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
