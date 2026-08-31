---
name: task-timer
description: Use this when the user wants to time how long a task takes -- starting, stopping, checking, or cancelling a timer ("start timing this", "I'm starting X now", "stop the timer", "how long have I been on this", "I just finished X" without a running timer). This feeds actual durations back into the estimate-learning history used by daily-planning.
---

# Task timer

Run everything through:

```
python3 "$CLAUDE_PLUGIN_ROOT/scripts/timer_cli.py" <command> ...
```

Only one timer runs at a time.

## Starting

When the user says they're starting a task, run:

```
timer_cli.py start --task "<title>" [--task-id <id>] [--date <YYYY-MM-DD>]
```

If the task is already on today's plan (check with `plan_cli.py show` if
unsure), pass `--task-id` so the timer links back to it and updates it on
stop. If a timer is already running, tell the user what's currently running
and ask whether to stop it first or cancel it (don't silently override).

## Stopping

```
timer_cli.py stop [--mark-done]
```

This prints the elapsed minutes. Tell the user how long it took. If the
timer was linked to a plan task, ask if it's actually done (pass
`--mark-done` if so) or just paused. If there was an estimate for that
task, it's worth a quick honest comparison ("that took 35 min vs. the 20 you
estimated -- I'll factor that in next time") -- keep it light, not a
scorecard.

## No timer was running but the user just finished something

Don't lose the data. Ask "roughly how long did that take?" and log it with:

```
timer_cli.py log-manual --title "<title>" --minutes <n> [--task-id <id>] [--mark-done]
```

## Checking status

```
timer_cli.py status
```

Reports what's running and elapsed minutes so far, or `{"running": false}`.

## Cancelling

If the user started a timer by mistake or wants to throw away the reading
(so it doesn't pollute future estimates), use `timer_cli.py cancel` --
this discards it without recording anything to history.
