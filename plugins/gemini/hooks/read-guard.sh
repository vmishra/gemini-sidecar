#!/bin/sh
# Opt-in guard for whole-file reads of large files. Off unless GEMINI_SIDECAR_READ_GUARD is
# "suggest" or "block", so by default it exits immediately and the read proceeds unchanged.
case "${GEMINI_SIDECAR_READ_GUARD:-off}" in
  suggest|block) exec python3 "$(dirname "$0")/read_guard.py" ;;
  *) exit 0 ;;
esac
