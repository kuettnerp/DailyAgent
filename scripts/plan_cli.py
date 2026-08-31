#!/usr/bin/env python3
"""CLI for day plans: tasks, priorities, carry-over, and estimate suggestions.

Always prints JSON to stdout so the calling skill can read structured
results and phrase things conversationally. Run with -h for usage, or
subcommand -h, e.g. `plan_cli.py add-task -h`.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def cmd_show(args):
    date_str = args.date or lib.today_str()
    day = lib.load_day(date_str)
    prev = lib.latest_previous_day(date_str)
    carryover = []
    if prev:
        prev_day = lib.load_day(prev)
        carryover = [t for t in prev_day["tasks"] if t.get("status") != "done"]
    print(json.dumps({
        "day": day,
        "previous_day": prev,
        "carryover_candidates": carryover,
    }, indent=2))


def cmd_carry_over(args):
    date_str = args.date or lib.today_str()
    prev = lib.latest_previous_day(date_str)
    if not prev:
        print(json.dumps({"applied": False, "reason": "no previous day found", "tasks": []}))
        return
    prev_day = lib.load_day(prev)
    unfinished = [t for t in prev_day["tasks"] if t.get("status") != "done"]
    if not args.apply:
        print(json.dumps({"applied": False, "previous_day": prev, "tasks": unfinished}, indent=2))
        return
    day = lib.load_day(date_str)
    existing_titles = {lib.normalize_title(t["title"]) for t in day["tasks"]}
    added = []
    for t in unfinished:
        if lib.normalize_title(t["title"]) in existing_titles:
            continue
        new_task = dict(t)
        new_task["id"] = lib.new_id()
        new_task["status"] = "pending"
        new_task["actual_minutes"] = None
        note = f"(carried over from {prev})"
        new_task["notes"] = f'{t.get("notes", "")} {note}'.strip()
        day["tasks"].append(new_task)
        added.append(new_task)
    lib.save_day(day)
    print(json.dumps({"applied": True, "previous_day": prev, "added": added}, indent=2))


def cmd_add_task(args):
    date_str = args.date or lib.today_str()
    day = lib.load_day(date_str)
    suggestion = lib.suggest_estimate(args.title)
    estimate = args.estimate
    estimate_source = "user"
    if estimate is None:
        estimate = suggestion["minutes"]
        estimate_source = "history" if estimate is not None else "none"
    task = {
        "id": lib.new_id(),
        "title": args.title,
        "estimate_minutes": estimate,
        "estimate_source": estimate_source,
        "actual_minutes": None,
        "priority": args.priority,
        "deadline": args.deadline,
        "status": "pending",
        "notes": args.notes or "",
        "calendar_suggested": False,
        "calendar_confirmed": False,
    }
    day["tasks"].append(task)
    lib.save_day(day)
    print(json.dumps({"task": task, "estimate_suggestion": suggestion}, indent=2))


def cmd_update_task(args):
    date_str = args.date or lib.today_str()
    day = lib.load_day(date_str)
    task = next((t for t in day["tasks"] if t["id"] == args.id), None)
    if task is None:
        print(json.dumps({"error": f"no task with id {args.id} on {date_str}"}), file=sys.stderr)
        sys.exit(1)

    if args.title is not None:
        task["title"] = args.title
    if args.status is not None:
        task["status"] = args.status
    if args.priority is not None:
        task["priority"] = args.priority
    if args.estimate is not None:
        task["estimate_minutes"] = args.estimate
        task["estimate_source"] = "user"
    if args.deadline is not None:
        task["deadline"] = args.deadline
    if args.notes is not None:
        task["notes"] = args.notes
    if args.calendar_suggested is not None:
        task["calendar_suggested"] = args.calendar_suggested
    if args.calendar_confirmed is not None:
        task["calendar_confirmed"] = args.calendar_confirmed
    if args.actual is not None:
        task["actual_minutes"] = args.actual
        lib.record_actual(task["title"], date_str, task.get("estimate_minutes"), args.actual)

    lib.save_day(day)
    print(json.dumps({"task": task}, indent=2))


def cmd_suggest_estimate(args):
    print(json.dumps(lib.suggest_estimate(args.title), indent=2, default=str))


def cmd_list_history(args):
    print(json.dumps({"entries": lib.task_history(args.title)}, indent=2))


def cmd_reflect(args):
    date_str = args.date or lib.today_str()
    day = lib.load_day(date_str)
    day["reflections"] = args.text
    lib.save_day(day)
    print(json.dumps({"day": day}, indent=2))


def parse_bool(s):
    return s.lower() in ("1", "true", "yes", "y")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("show", help="Show a day's plan plus unfinished carry-over candidates")
    s.add_argument("--date")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("carry-over", help="List (or apply) unfinished tasks from the previous day")
    s.add_argument("--date")
    s.add_argument("--apply", action="store_true")
    s.set_defaults(func=cmd_carry_over)

    s = sub.add_parser("add-task", help="Add a task to a day's plan")
    s.add_argument("--title", required=True)
    s.add_argument("--date")
    s.add_argument("--estimate", type=float, help="Minutes; omit to auto-fill from history")
    s.add_argument("--priority", type=int)
    s.add_argument("--deadline")
    s.add_argument("--notes")
    s.set_defaults(func=cmd_add_task)

    s = sub.add_parser("update-task", help="Update fields on an existing task")
    s.add_argument("--id", required=True)
    s.add_argument("--date")
    s.add_argument("--title")
    s.add_argument("--status", choices=["pending", "in_progress", "done", "dropped"])
    s.add_argument("--priority", type=int)
    s.add_argument("--estimate", type=float)
    s.add_argument("--actual", type=float, help="Actual minutes spent; also records to history")
    s.add_argument("--deadline")
    s.add_argument("--notes")
    s.add_argument("--calendar-suggested", type=parse_bool)
    s.add_argument("--calendar-confirmed", type=parse_bool)
    s.set_defaults(func=cmd_update_task)

    s = sub.add_parser("suggest-estimate", help="Suggest a time estimate for a task from history")
    s.add_argument("--title", required=True)
    s.set_defaults(func=cmd_suggest_estimate)

    s = sub.add_parser("list-history", help="Show past estimate/actual entries for a task")
    s.add_argument("--title", required=True)
    s.set_defaults(func=cmd_list_history)

    s = sub.add_parser("reflect", help="Save end-of-day reflections/notes")
    s.add_argument("--text", required=True)
    s.add_argument("--date")
    s.set_defaults(func=cmd_reflect)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
