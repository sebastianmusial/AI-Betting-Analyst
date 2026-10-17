"""PreToolUse: blokuje edycję sekretów i produkcyjnej bazy (ADR 0016, 0020)."""

import json
import sys

PROTECTED = (".env", "data/betting.duckdb")

payload = json.load(sys.stdin)
path = (payload.get("tool_input") or {}).get("file_path", "")
if path.endswith(PROTECTED) and not path.endswith(".env.example"):
    print(f"Zablokowano edycję chronionego pliku: {path}", file=sys.stderr)
    sys.exit(2)
