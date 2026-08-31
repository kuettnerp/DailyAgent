#!/usr/bin/env python3
"""CLI for learned playbooks: things the user explicitly asked the
assistant to learn how to handle.

`add` does two things at once:
  1. Records the playbook in learned_playbooks.json (picked up immediately,
     same session, by any skill that checks it).
  2. Writes a real SKILL.md under skills/learned/<slug>/ in this plugin, so
     it becomes a first-class, independently-triggered Claude Code skill
     the next time the plugin is loaded/reloaded.

Prints JSON to stdout.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import lib  # noqa: E402

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
LEARNED_SKILLS_DIR = PLUGIN_ROOT / "skills" / "learned"


def cmd_list(args):
    print(json.dumps(lib.load_playbooks(), indent=2))


def cmd_find(args):
    data = lib.load_playbooks()
    query = args.query.lower()
    words = [w for w in query.split() if w]
    matches = []
    for pb in data["playbooks"]:
        haystack = " ".join([
            pb["title"].lower(),
            " ".join(t.lower() for t in pb.get("triggers", [])),
            " ".join(s.lower() for s in pb.get("steps", [])),
        ])
        score = sum(haystack.count(w) for w in words)
        if score > 0:
            matches.append({**pb, "_score": score})
    matches.sort(key=lambda m: -m["_score"])
    print(json.dumps({"matches": matches}, indent=2))


def _write_skill_md(slug: str, title: str, triggers: list[str], steps: list[str], notes: str) -> Path:
    skill_dir = LEARNED_SKILLS_DIR / slug
    skill_dir.mkdir(parents=True, exist_ok=True)
    trigger_phrase_list = ", ".join(f'"{t}"' for t in triggers) if triggers else "(none given)"
    description = (
        f"Use this skill to {title.rstrip('.').lower()}. "
        f"The user asked the daily-assistant to learn this. Triggers include: {trigger_phrase_list}. "
        "Follow the steps below; if the user's request diverges from them, do the steps that still apply "
        "and ask before improvising anything destructive or externally visible."
    )
    steps_md = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(steps))
    notes_md = f"\n## Notes\n\n{notes}\n" if notes else ""
    content = f"""---
name: learned-{slug}
description: {description}
---

# {title}

This skill was learned from a conversation with the user on {lib.today_str()},
via the daily-assistant plugin's skill-learning flow. It is plain text you
(and the user) can edit freely -- nothing about it is magic.

## Steps

{steps_md}
{notes_md}
"""
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")
    return skill_dir / "SKILL.md"


def cmd_add(args):
    triggers = [t.strip() for t in (args.triggers or "").split(",") if t.strip()]
    steps = args.step or []
    if not steps:
        print(json.dumps({"error": "at least one --step is required"}), file=sys.stderr)
        sys.exit(1)

    slug = lib.slugify(args.title)
    data = lib.load_playbooks()
    if any(pb["slug"] == slug for pb in data["playbooks"]):
        print(json.dumps({"error": f"a playbook with slug '{slug}' already exists"}), file=sys.stderr)
        sys.exit(1)

    skill_path = _write_skill_md(slug, args.title, triggers, steps, args.notes or "")

    entry = {
        "slug": slug,
        "title": args.title,
        "triggers": triggers,
        "steps": steps,
        "notes": args.notes or "",
        "created": lib.today_str(),
        "last_used": None,
        "use_count": 0,
        "skill_path": str(skill_path.relative_to(PLUGIN_ROOT)),
    }
    data["playbooks"].append(entry)
    lib.save_playbooks(data)
    print(json.dumps({"playbook": entry, "skill_file_written": str(skill_path)}, indent=2))


def cmd_use(args):
    data = lib.load_playbooks()
    entry = next((pb for pb in data["playbooks"] if pb["slug"] == args.slug), None)
    if entry is None:
        print(json.dumps({"error": f"no playbook with slug '{args.slug}'"}), file=sys.stderr)
        sys.exit(1)
    entry["use_count"] += 1
    entry["last_used"] = lib.today_str()
    lib.save_playbooks(data)
    print(json.dumps({"playbook": entry}, indent=2))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("list", help="List all learned playbooks")
    s.set_defaults(func=cmd_list)

    s = sub.add_parser("find", help="Search learned playbooks by keyword")
    s.add_argument("--query", required=True)
    s.set_defaults(func=cmd_find)

    s = sub.add_parser("add", help="Learn a new playbook (registry entry + generated SKILL.md)")
    s.add_argument("--title", required=True)
    s.add_argument("--triggers", help="Comma-separated trigger phrases")
    s.add_argument("--step", action="append", help="One step; repeat --step for each")
    s.add_argument("--notes")
    s.set_defaults(func=cmd_add)

    s = sub.add_parser("use", help="Mark a playbook as used (bumps use_count/last_used)")
    s.add_argument("--slug", required=True)
    s.set_defaults(func=cmd_use)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
