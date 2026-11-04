#!/usr/bin/env python3
"""PreToolUse hook for Claude Code's Read tool (opt-in).

GEMINI_SIDECAR_READ_GUARD=suggest  allow the read, and add a note pointing to the Gemini tools
GEMINI_SIDECAR_READ_GUARD=block    refuse whole-file reads of large files; partial reads still pass
GEMINI_SIDECAR_READ_GUARD_LINES    line threshold (default 400)

Reads with offset or limit always pass, because edits need exact lines. Images, PDFs, notebooks
and staged Gemini output pass too. Any error lets the read proceed.
"""

import json
import os
import sys

SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg", ".pdf", ".ipynb"}
MAX_SCAN_BYTES = 8_000_000


def exceeds(path: str, threshold: int) -> bool:
    """True if the file has more than `threshold` lines (stops reading as soon as it knows)."""
    lines = 0
    read = 0
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            lines += chunk.count(b"\n")
            read += len(chunk)
            if lines > threshold or read > MAX_SCAN_BYTES:
                return True
    return False


def main() -> int:
    mode = os.environ.get("GEMINI_SIDECAR_READ_GUARD", "off").strip().lower()
    if mode not in ("suggest", "block"):
        return 0
    try:
        threshold = int(os.environ.get("GEMINI_SIDECAR_READ_GUARD_LINES", "400"))
    except ValueError:
        threshold = 400
    event = json.load(sys.stdin)
    if event.get("tool_name") != "Read":
        return 0
    tool_input = event.get("tool_input") or {}
    if tool_input.get("offset") is not None or tool_input.get("limit") is not None:
        return 0
    path = str(tool_input.get("file_path") or "")
    if not path or not os.path.isfile(path):
        return 0
    if os.path.splitext(path)[1].lower() in SKIP_SUFFIXES or "/.gemini4-staging/" in path.replace(os.sep, "/"):
        return 0
    if not exceeds(path, threshold):
        return 0
    # The file name is deliberately not echoed: names are attacker-controlled in an untrusted repo.
    advice = (
        f"This file has more than {threshold:,} lines. To answer a question about it, use gemini4_analyze_codebase "
        "(or /gemini:analyze): it reads the file outside this conversation and returns only the answer. "
        "Reading the whole file in chunks costs the same as one full read, so don't. To edit, find the spot "
        "first (for example with Grep) and read only those lines with offset and limit."
    )
    if mode == "block":
        decision = {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "gemini-sidecar read guard: " + advice
            + " (Set GEMINI_SIDECAR_READ_GUARD=off to disable.)",
        }
    else:
        # No permissionDecision: the guard only adds advice and never approves a read on its own,
        # so the user's normal permission rules still decide.
        decision = {"hookEventName": "PreToolUse", "additionalContext": advice}
    json.dump({"hookSpecificOutput": decision}, sys.stdout)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # never block a read because the guard itself failed
        sys.exit(0)
