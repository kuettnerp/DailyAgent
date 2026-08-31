#!/usr/bin/env python3
"""SessionStart hook: quietly surfaces yesterday's unfinished tasks (if any)
as extra context, so the model can naturally offer a daily check-in instead
of the user having to remember to ask. Never prints anything on first run
or when there's nothing carried over -- this should be unobtrusive.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

try:
    import lib  # noqa: E402
except Exception:
    # If memory isn't set up yet (e.g. no HOME writable), fail silent and quiet.
    sys.exit(0)


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        data = {}

    source = data.get("source", "startup")
    if source not in ("startup", "resume"):
        sys.exit(0)

    try:
        today = lib.today_str()
        prev = lib.latest_previous_day(today)
        if not prev:
            sys.exit(0)
        prev_day = lib.load_day(prev)
        unfinished = [t for t in prev_day["tasks"] if t.get("status") not in ("done", "dropped")]
        if not unfinished:
            sys.exit(0)
        titles = ", ".join(t["title"] for t in unfinished[:5])
        more = f" (+{len(unfinished) - 5} more)" if len(unfinished) > 5 else ""
        context = (
            "daily-assistant plugin memory: the user has "
            f"{len(unfinished)} unfinished task(s) carried over from {prev}: "
            f"{titles}{more}. If it fits naturally, offer a daily check-in "
            "(the daily-planning skill) rather than assuming -- don't force it "
            "if the user has a specific, unrelated request right now."
        )
        print(json.dumps({"hookSpecificOutput": {"additionalContext": context}}))
    except Exception:
        sys.exit(0)


if __name__ == "__main__":
    main()
