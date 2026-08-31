"""Shared storage helpers for Patriot, the daily-assistant plugin.

All persistent state lives under a single directory (default
``~/.patriot``, overridable via the ``PATRIOT_HOME`` env var so it can be
pointed at a scratch directory during tests). Nothing here ever touches the
git repo the plugin code ships in -- this is per-user memory, not plugin
source.

Layout under that directory:

    days/YYYY-MM-DD.json     one day's plan (tasks + reflections)
    task_history.json        per-task estimate/actual history, for learning
    timer_state.json         the currently running timer, if any
    learned_playbooks.json   registry of skills the user asked us to learn
"""

from __future__ import annotations

import json
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import Any


def home_dir() -> Path:
    override = os.environ.get("PATRIOT_HOME")
    base = Path(override) if override else Path.home() / ".patriot"
    (base / "days").mkdir(parents=True, exist_ok=True)
    return base


def days_dir() -> Path:
    return home_dir() / "days"


def day_path(date_str: str) -> Path:
    return days_dir() / f"{date_str}.json"


def history_path() -> Path:
    return home_dir() / "task_history.json"


def timer_path() -> Path:
    return home_dir() / "timer_state.json"


def playbooks_path() -> Path:
    return home_dir() / "learned_playbooks.json"


def today_str() -> str:
    return date.today().isoformat()


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:8]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=False)
        f.write("\n")
    tmp.replace(path)


def empty_day(date_str: str) -> dict:
    return {"date": date_str, "tasks": [], "reflections": ""}


def load_day(date_str: str) -> dict:
    return load_json(day_path(date_str), empty_day(date_str))


def save_day(day: dict) -> None:
    save_json(day_path(day["date"]), day)


def latest_previous_day(before_date_str: str) -> str | None:
    """Most recent day file strictly before ``before_date_str``, if any."""
    candidates = sorted(p.stem for p in days_dir().glob("*.json"))
    earlier = [d for d in candidates if d < before_date_str]
    return earlier[-1] if earlier else None


def normalize_title(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


# ---- task history / estimate learning -------------------------------------------------

def _load_history() -> dict:
    return load_json(history_path(), {"tasks": {}})


def _save_history(hist: dict) -> None:
    save_json(history_path(), hist)


def record_actual(title: str, date_str: str, estimate_minutes: float | None,
                   actual_minutes: float) -> None:
    hist = _load_history()
    key = normalize_title(title)
    hist["tasks"].setdefault(key, {"display_title": title, "entries": []})
    hist["tasks"][key]["display_title"] = title
    hist["tasks"][key]["entries"].append({
        "date": date_str,
        "estimate_minutes": estimate_minutes,
        "actual_minutes": actual_minutes,
    })
    _save_history(hist)


def task_history(title: str) -> list[dict]:
    hist = _load_history()
    key = normalize_title(title)
    exact = hist["tasks"].get(key)
    if exact:
        return exact["entries"]
    # fall back to substring match against any known task name
    matches: list[dict] = []
    for k, v in hist["tasks"].items():
        if key in k or k in key:
            matches.extend(v["entries"])
    return matches


def suggest_estimate(title: str, max_samples: int = 5) -> dict:
    """Suggest a minutes estimate from history.

    Returns {"minutes": float|None, "sample_count": int, "samples": [...]}.
    Recent actuals are weighted more heavily than older ones.
    """
    entries = task_history(title)
    entries_with_actual = [e for e in entries if e.get("actual_minutes") is not None]
    entries_with_actual.sort(key=lambda e: e["date"])
    recent = entries_with_actual[-max_samples:]
    if not recent:
        return {"minutes": None, "sample_count": 0, "samples": []}
    weights = list(range(1, len(recent) + 1))  # oldest=1 ... newest=len
    weighted_sum = sum(w * e["actual_minutes"] for w, e in zip(weights, recent))
    minutes = weighted_sum / sum(weights)
    # round to nearest 5 minutes for a sane-sounding suggestion
    minutes = round(minutes / 5.0) * 5
    return {
        "minutes": minutes,
        "sample_count": len(entries_with_actual),
        "samples": recent,
    }


# ---- timer -------------------------------------------------------------------------

def load_timer() -> dict | None:
    data = load_json(timer_path(), None)
    return data or None


def save_timer(data: dict | None) -> None:
    if data is None:
        if timer_path().exists():
            timer_path().unlink()
        return
    save_json(timer_path(), data)


# ---- learned playbooks ---------------------------------------------------------------

def load_playbooks() -> dict:
    return load_json(playbooks_path(), {"playbooks": []})


def save_playbooks(data: dict) -> None:
    save_json(playbooks_path(), data)


def slugify(title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.strip().lower()).strip("-")
    return slug or "playbook"
