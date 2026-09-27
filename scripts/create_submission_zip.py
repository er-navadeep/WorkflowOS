"""
WorkFlowOS Submission Package Generator
=======================================
Creates a clean, reproducible, zero-leakage ZIP archive of the complete
WorkFlowOS project for submission.
"""

from __future__ import annotations

import hashlib
import os
import re
import sys
import zipfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_ZIP = os.path.join(PROJECT_ROOT, "WorkFlowOS_Submission.zip")

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    ".pytest_cache",
    "__pycache__",
    "downloads",
}

EXCLUDE_FILES = {
    ".env",
    "credentials.json",
    ".gmail_token.local",
    "token.json",
}

EXCLUDE_EXTS = {
    ".pyc",
    ".pyo",
    ".log",
    ".zip",
}

REQUIRED_DIRS = {
    "backend",
    "frontend",
    "activity-agent",
    "scripts",
    "tests",
    "docs",
    "config",
}

CRITICAL_FILES = {
    "README.md",
    ".env.example",
    ".gitignore",
    "requirements.txt",
    "backend/requirements.txt",
    "frontend/package.json",
    "frontend/package-lock.json",
}


def should_exclude(rel_path: str) -> bool:
    """Return True if rel_path matches any security or build exclusion pattern."""
    parts = rel_path.split("/")
    filename = parts[-1]
    _, ext = os.path.splitext(filename)

    # Directory exclusions
    for part in parts[:-1]:
        if part in EXCLUDE_DIRS:
            return True

    # Secret files exclusions
    if filename in EXCLUDE_FILES:
        return True
    if filename.startswith(".env") and filename != ".env.example":
        return True
    if filename.startswith("client_secret"):
        return True
    if ext in {".token", ".credentials"}:
        return True

    # Compilation & archive exclusions
    if ext in EXCLUDE_EXTS:
        return True

    return False


def collect_files() -> list[tuple[str, str]]:
    """Collect (full_path, arcname) for all files to be included."""
    files_to_pack = []
    for dirpath, dirnames, filenames in os.walk(PROJECT_ROOT):
        # Prune excluded directories in-place so os.walk does not descend
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIRS and not d.endswith(".egg-info")]

        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, PROJECT_ROOT).replace(os.sep, "/")

            if should_exclude(rel_path):
                continue

            # Prefix archive entry with project directory name for clean extraction
            arcname = f"WorkFlowOS/{rel_path}"
            files_to_pack.append((full_path, arcname, rel_path))

    return files_to_pack


def create_submission_zip() -> None:
    print("=" * 80)
    print("WorkFlowOS: Generating Submission Package")
    print("=" * 80)

    files = collect_files()
    print(f"Total files candidate for packaging: {len(files)}")

    # Audit exclusions
    for full_path, arcname, rel_path in files:
        if should_exclude(rel_path):
            raise RuntimeError(f"FATAL: Excluded file would be included: {rel_path}")

    # Remove existing zip if present
    if os.path.exists(OUTPUT_ZIP):
        os.remove(OUTPUT_ZIP)

    print(f"Creating ZIP archive: {OUTPUT_ZIP}")
    with zipfile.ZipFile(OUTPUT_ZIP, "w", zipfile.ZIP_DEFLATED) as zf:
        for full_path, arcname, rel_path in files:
            zf.write(full_path, arcname)

    # Verification of ZIP contents
    print("\nVerifying ZIP archive integrity...")
    with zipfile.ZipFile(OUTPUT_ZIP, "r") as zf:
        namelist = zf.namelist()

        # Check for forbidden files
        for name in namelist:
            parts = name.split("/")
            base = parts[-1]
            if base in EXCLUDE_FILES or (base.startswith(".env") and base != ".env.example"):
                raise RuntimeError(f"SECURITY VIOLATION: Forbidden file in ZIP: {name}")
            if any(part in EXCLUDE_DIRS for part in parts[:-1]):
                raise RuntimeError(f"BUILD POLLUTION: Excluded directory in ZIP: {name}")

        # Check for required directories
        top_dirs = {p.split("/")[1] for p in namelist if "/" in p}
        for req in REQUIRED_DIRS:
            if req not in top_dirs:
                raise RuntimeError(f"MISSING DIRECTORY: Required directory '{req}' not in ZIP")

        # Check for critical files
        for crit in CRITICAL_FILES:
            expected_arc = f"WorkFlowOS/{crit}"
            if expected_arc not in namelist:
                raise RuntimeError(f"MISSING FILE: Critical file '{expected_arc}' not in ZIP")

    # Compute sha256 checksum
    h = hashlib.sha256()
    with open(OUTPUT_ZIP, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    sha256 = h.hexdigest()
    zip_size = os.path.getsize(OUTPUT_ZIP)

    print("=" * 80)
    print("SUBMISSION ZIP CREATION & VERIFICATION SUCCESSFUL")
    print(f"  Exact ZIP Path : {OUTPUT_ZIP}")
    print(f"  File Size      : {zip_size:,} bytes ({zip_size / (1024 * 1024):.2f} MB)")
    print(f"  File Count     : {len(namelist)} files")
    print(f"  SHA-256 Checksum: {sha256}")
    print("=" * 80)


if __name__ == "__main__":
    create_submission_zip()
