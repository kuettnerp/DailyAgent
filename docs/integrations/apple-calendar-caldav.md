# Apple Calendar & Reminders via CalDAV (investigated, not wired up)

Status: **not connected**. This is the investigation the user asked for,
plus a ready-to-use script, but nothing in this plugin calls it
automatically and no credentials are stored anywhere in this repo.

## What CalDAV is

CalDAV (RFC 4791) is the open, HTTP-based protocol Apple's own Calendar.app
and Reminders.app use to sync with iCloud. `caldav.icloud.com` is Apple's
real sync server -- this is the same channel Apple's apps use, not a
workaround.

- **Calendar events**: fully supported over CalDAV, widely used by
  third-party apps (Fantastical, DAVx5, Thunderbird, etc.).
- **Reminders**: exposed as CalDAV "VTODO" collections under the same
  account. Third-party task apps (2Do, GoodTask) do sync Reminders this
  way today, but Apple has occasionally been inconsistent about
  third-party VTODO access on newer OS versions -- treat this as "probably
  works" rather than guaranteed, and smoke-test it once real credentials
  are in place.

## Authentication

Apple requires an **app-specific password** for any non-Apple CalDAV
client:

1. Sign in at https://appleid.apple.com
2. Sign-In and Security → App-Specific Passwords → generate one, label it
   something like "patriot caldav"
3. It's scoped (can't touch Keychain, purchases, or reset the Apple ID) and
   revocable independently of the main password at any time.

**Never commit this password, never paste it into a chat session, never
put it directly in a script.** Use an environment variable set locally on
whatever machine actually runs this (e.g. in your shell profile, or a
gitignored `.env` loaded by direnv), read at runtime only:

```
export ICLOUD_APPLE_ID="you@icloud.com"
export ICLOUD_APP_PASSWORD="xxxx-xxxx-xxxx-xxxx"
```

## Reference script

`docs/integrations/scripts/icloud_caldav_check.py` (bundled here, not
under `scripts/` or any skill, so nothing triggers it automatically)
implements read access using the `caldav` Python package:

```
pip install caldav icalendar
python3 docs/integrations/scripts/icloud_caldav_check.py events --days 7
python3 docs/integrations/scripts/icloud_caldav_check.py reminders
```

It only reads by default. Writing an event is a separate, explicit
subcommand (`add-event`) that prints what it's about to create and asks
for a `--yes` flag -- deliberately not a one-liner, since writing to a
real calendar shouldn't be a casual action.

## If you want to actually wire this into the plugin later

The natural integration point is the calendar-nudge step in
`skills/daily-planning/SKILL.md` (step 6): instead of only asking "have
you added this to your calendar," a skill could call this script to check
directly and skip the question when it's already there, or offer to create
it after an explicit "yes, add it." That was intentionally left undone for
now -- do it once you've smoke-tested read access on your own machine.

## Skylight

The Skylight *device/app* is a different product from Apple
Calendar/Reminders (it's a family calendar display), and is covered
separately in `docs/integrations/skylight.md`.
