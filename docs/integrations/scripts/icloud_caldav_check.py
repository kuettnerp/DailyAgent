#!/usr/bin/env python3
"""Reference-only iCloud CalDAV script (Calendar events + Reminders/VTODO).

NOT wired into any skill or hook -- run it manually, on your own machine,
once you have an app-specific password set up. See
docs/integrations/apple-calendar-caldav.md for the full explanation.

Requires:  pip install caldav icalendar

Credentials come ONLY from environment variables, never from arguments or
files in this repo:

    export ICLOUD_APPLE_ID="you@icloud.com"
    export ICLOUD_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"

Usage:
    python3 icloud_caldav_check.py events [--days 7]
    python3 icloud_caldav_check.py reminders
    python3 icloud_caldav_check.py add-event --summary "..." --start ISO --end ISO --yes
"""
import argparse
import os
import sys
from datetime import datetime, timedelta

CALDAV_URL = "https://caldav.icloud.com"


def _connect():
    try:
        import caldav
    except ImportError:
        print("Missing dependency. Run: pip install caldav icalendar", file=sys.stderr)
        sys.exit(1)

    apple_id = os.environ.get("ICLOUD_APPLE_ID")
    app_password = os.environ.get("ICLOUD_APP_PASSWORD")
    if not apple_id or not app_password:
        print("Set ICLOUD_APPLE_ID and ICLOUD_APP_PASSWORD in your environment first.",
              file=sys.stderr)
        sys.exit(1)

    client = caldav.DAVClient(url=CALDAV_URL, username=apple_id, password=app_password)
    return client.principal()


def cmd_events(args):
    principal = _connect()
    now = datetime.now()
    end = now + timedelta(days=args.days)
    for cal in principal.calendars():
        try:
            events = cal.date_search(start=now, end=end, event=True)
        except Exception as e:
            print(f"[{cal.name}] could not search: {e}", file=sys.stderr)
            continue
        for ev in events:
            print(f"[{cal.name}] {ev.instance.vevent.summary.value} @ "
                  f"{ev.instance.vevent.dtstart.value}")


def cmd_reminders(args):
    principal = _connect()
    for cal in principal.calendars():
        try:
            todos = cal.todos()
        except Exception as e:
            print(f"[{cal.name}] could not list todos: {e}", file=sys.stderr)
            continue
        for t in todos:
            vtodo = t.instance.vtodo
            status = getattr(vtodo, "status", None)
            status_val = status.value if status else "NEEDS-ACTION"
            print(f"[{cal.name}] {vtodo.summary.value} ({status_val})")


def cmd_add_event(args):
    if not args.yes:
        print(f"Would create: '{args.summary}' from {args.start} to {args.end}. "
              "Re-run with --yes to actually create it.")
        return
    principal = _connect()
    calendars = principal.calendars()
    if not calendars:
        print("No calendars found.", file=sys.stderr)
        sys.exit(1)
    target = next((c for c in calendars if c.name == args.calendar), calendars[0]) if args.calendar else calendars[0]
    ical = (
        "BEGIN:VCALENDAR\nVERSION:2.0\nBEGIN:VEVENT\n"
        f"SUMMARY:{args.summary}\nDTSTART:{args.start}\nDTEND:{args.end}\n"
        "END:VEVENT\nEND:VCALENDAR\n"
    )
    target.save_event(ical)
    print(f"Created '{args.summary}' on calendar '{target.name}'.")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("events")
    s.add_argument("--days", type=int, default=7)
    s.set_defaults(func=cmd_events)

    s = sub.add_parser("reminders")
    s.set_defaults(func=cmd_reminders)

    s = sub.add_parser("add-event")
    s.add_argument("--summary", required=True)
    s.add_argument("--start", required=True, help="ICS datetime, e.g. 20260901T140000")
    s.add_argument("--end", required=True)
    s.add_argument("--calendar", help="Calendar name; defaults to the first one found")
    s.add_argument("--yes", action="store_true", help="Actually create it (default: dry run)")
    s.set_defaults(func=cmd_add_event)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
