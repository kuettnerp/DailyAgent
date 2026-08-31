---
name: skill-learning
description: Use this when the user asks you to remember how to do something, automate a recurring task, "learn" a process, or after you've just walked through a multi-step task at their request that looks like it could recur ("can you learn to do this", "just handle this for me from now on", "remember how I like this done"). Always confirm with the user before actually learning something -- never learn silently.
---

# Learning a new skill

This is the mechanism behind "it should learn new skills based on things I
ask it to do." It is opt-in and explicit every time -- never learn
something the user didn't agree to.

## When to offer

Two triggers:
1. The user directly asks you to learn/remember/automate something.
2. You notice, on your own, that you just did something multi-step and
   fairly mechanical at the user's request that seems likely to come up
   again (e.g. a specific weekly report format, a particular way they like
   emails drafted, a recurring setup routine).

In case 2, **ask, don't assume**: "Want me to learn this so I can just
handle '<thing>' the same way next time you ask?" If they say no, drop it
-- don't ask again for the same thing in the same conversation.

## Recording it

Once the user says yes, write down the concrete steps you actually took
(not vague intentions) and register it:

```
python3 "$CLAUDE_PLUGIN_ROOT/scripts/playbook_cli.py" add \
  --title "<short descriptive title>" \
  --triggers "<phrase1>,<phrase2>" \
  --step "<first concrete step>" \
  --step "<second concrete step>" \
  --step "<...>" \
  --notes "<any preferences/constraints the user mentioned>"
```

Repeat `--step` for each step -- be concrete enough that a future
conversation with no memory of this one could follow them.

This does two things: it saves a JSON entry in
`~/.patriot/learned_playbooks.json` (usable immediately, this
session, by checking it -- see below), and it writes a real `SKILL.md`
under `skills/learned/<slug>/` in this plugin. The generated skill becomes
a fully independent, auto-triggering Claude Code skill the next time the
plugin reloads (new session). Tell the user both of these things happened,
in plain language -- e.g. "got it, saved that. It'll work right away, and
next time you start a fresh session it'll trigger on its own when you say
things like '<trigger phrase>'."

## Using what's been learned

At the start of a task that might match something already learned
(especially if the user's phrasing echoes a stored trigger), check:

```
python3 "$CLAUDE_PLUGIN_ROOT/scripts/playbook_cli.py" find --query "<a few keywords from the request>"
```

If there's a good match, follow its steps, then mark it used:

```
python3 "$CLAUDE_PLUGIN_ROOT/scripts/playbook_cli.py" use --slug <slug>
```

If the steps don't quite fit anymore, do the task the way the user
actually wants this time and ask if the playbook should be updated
(editing `skills/learned/<slug>/SKILL.md` directly, or removing the old
`--step` entries and re-adding with `playbook_cli.py add` under a new
title, is fine -- there's no versioning to preserve here).

## Boundaries

- Never learn something that involves credentials, destructive actions, or
  anything sent externally (emails, messages, purchases) without also
  confirming, every single time it's used, before it acts -- "learning the
  steps" is not the same as "permission to run them unattended." Say this
  explicitly if the user tries to learn something in that category.
