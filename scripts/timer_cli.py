#!/usr/bin/env python3
"""CLI for timing tasks: start/stop a stopwatch, or log a duration after the
fact. Every completed duration is fed into task_history.json so future
estimates for that task get smarter automatically.

Prints JSON to stdout.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402


def cmd_start(args):
    existing = lib.load_timer()
    if existing:
        print(json.dumps({
            "error": "a timer is already running",
            "running": existing,
        }), file=sys.stderr)
        sys.exit(1)
    timer = {
        "task_title": args.task,
        "task_id": args.task_id,
        "date": args.date or lib.today_str(),
        "start_iso": lib.now_iso(),
    }
    lib.save_timer(timer)
    print(json.dumps({"started": timer}, indent=2))


def cmd_status(args):
    timer = lib.load_timer()
    if not timer:
        print(json.dumps({"running": False}))
        return
    started = datetime.fromisoformat(timer["start_iso"])
    elapsed_minutes = round((datetime.now() - started).total_seconds() / 60.0, 1)
    print(json.dumps({"running": True, "timer": timer, "elapsed_minutes": elapsed_minutes}, indent=2))


def cmd_stop(args):
    timer = lib.load_timer()
    if not timer:
        print(json.dumps({"error": "no timer is running"}), file=sys.stderr)
        sys.exit(1)
    started = datetime.fromisoformat(timer["start_iso"])
    elapsed_minutes = round((datetime.now() - started).total_seconds() / 60.0, 1)
    lib.save_timer(None)

    estimate_minutes = None
    if timer.get("task_id"):
        day = lib.load_day(timer["date"])
        task = next((t for t in day["tasks"] if t["id"] == timer["task_id"]), None)
        if task:
            estimate_minutes = task.get("estimate_minutes")
            task["actual_minutes"] = elapsed_minutes
            if args.mark_done:
                task["status"] = "done"
            lib.save_day(day)

    lib.record_actual(timer["task_title"], timer["date"], estimate_minutes, elapsed_minutes)
    print(json.dumps({
        "stopped": timer,
        "elapsed_minutes": elapsed_minutes,
        "estimate_minutes": estimate_minutes,
    }, indent=2))


def cmd_log_manual(args):
    date_str = args.date or lib.today_str()
    estimate_minutes = None
    if args.task_id:
        day = lib.load_day(date_str)
        task = next((t for t in day["tasks"] if t["id"] == args.task_id), None)
        if task:
            estimate_minutes = task.get("estimate_minutes")
            task["actual_minutes"] = args.minutes
            if args.mark_done:
                task["status"] = "done"
            lib.save_day(day)
    lib.record_actual(args.title, date_str, estimate_minutes, args.minutes)
    print(json.dumps({
        "logged": {"title": args.title, "date": date_str, "minutes": args.minutes},
        "estimate_minutes": estimate_minutes,
    }, indent=2))


def cmd_cancel(args):
    timer = lib.load_timer()
    lib.save_timer(None)
    print(json.dumps({"cancelled": timer}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("start", help="Start timing a task")
    s.add_argument("--task", required=True, help="Task title (for history matching)")
    s.add_argument("--task-id", help="Optional id of a task on today's plan to link this to")
    s.add_argument("--date", help="Plan date the task-id belongs to, default today")
    s.set_defaults(func=cmd_start)

    s = sub.add_parser("status", help="Show the currently running timer, if any")
    s.set_defaults(func=cmd_status)

    s = sub.add_parser("stop", help="Stop the running timer and record the actual duration")
    s.add_argument("--mark-done", action="store_true", help="Also mark the linked plan task done")
    s.set_defaults(func=cmd_stop)

    s = sub.add_parser("log-manual", help="Record a duration without having used start/stop")
    s.add_argument("--title", required=True)
    s.add_argument("--minutes", type=float, required=True)
    s.add_argument("--task-id")
    s.add_argument("--date")
    s.add_argument("--mark-done", action="store_true")
    s.set_defaults(func=cmd_log_manual)

    s = sub.add_parser("cancel", help="Discard the running timer without recording anything")
    s.set_defaults(func=cmd_cancel)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
