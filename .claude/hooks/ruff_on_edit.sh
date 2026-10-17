#!/bin/sh
# PostToolUse: ruff format + check na edytowanym pliku .py (ADR 0020).
file=$(python3 -c 'import json,sys; print((json.load(sys.stdin).get("tool_input") or {}).get("file_path",""))')
case "$file" in
  *.py)
    cd "$CLAUDE_PROJECT_DIR" || exit 0
    uv run --quiet ruff format "$file" >/dev/null 2>&1
    uv run --quiet ruff check --fix "$file" 1>&2 || exit 2
    ;;
esac
exit 0
