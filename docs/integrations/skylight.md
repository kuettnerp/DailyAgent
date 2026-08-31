# Skylight Calendar (investigated, not wired up)

Status: **not connected, no integration code shipped**. This is purely the
investigation the user asked for. Skylight here means the physical Skylight
Calendar smart display / family-organizer app (by Ai2), which is a
separate product from Apple Calendar and Reminders.

## Two ways in, both with real tradeoffs

### 1. Official API (gated)

Ai2 publishes a formal [Skylight API Policy](https://www.skylight.global/api-policy)
and [API documentation](https://support.skylight.global/en_US/api-documentation).
Access is not self-serve: Ai2 decides case-by-case whether to grant a given
integration API access, and use is bound to their EULA. There's no public
sign-up-and-go flow as of this investigation.

- **Pros**: sanctioned, supported, won't silently break on a Skylight app
  update, no ToS risk.
- **Cons**: requires reaching out to Ai2 and getting approved before any
  code can be written against it; unknown turnaround time or acceptance
  criteria; scope of what the official API exposes (read vs. write,
  events vs. chores/rewards) isn't fully clear from public docs alone.

If long-term, supported integration matters more than speed, this is the
right path -- start by contacting Ai2 through the API policy page above.

### 2. Community reverse-engineered API

There's an existing open-source project,
[`skylight-mcp`](https://github.com/chrischall/skylight-mcp), that already
implements an MCP server against Skylight's real (undocumented) API:
events, chores, family task assignments, shopping/to-do lists, and reward
points. It authenticates with your actual Skylight email/password (issuing
a Base64 Basic-auth token) and sends a `skylight-api-version: 2026-05-01`
header to match what the official mobile app sends.

- **Pros**: works today, no approval process, already has read/write for
  most of what you'd want (events, lists).
- **Cons**: it's unofficial -- your actual account password (not a scoped,
  revocable token like an app-specific password) goes through third-party
  code; Ai2 could change the API and break it without notice; unclear ToS
  standing for automated/unofficial API use at scale.

## Recommendation

Given this repo's memory is meant to stay local and low-risk, don't wire
either of these up yet. If/when you want it:

- For something you're comfortable depending on long-term: apply for
  official API access first.
- For a quick personal experiment you accept the fragility/ToS risk on:
  `skylight-mcp` is a real, working starting point -- but keep the Skylight
  password it uses out of this repo (env var, same pattern as the iCloud
  CalDAV doc) and treat it as "may break any time," not a dependency the
  daily-planning flow relies on.

Either way, the integration point in `skills/daily-planning/SKILL.md`
(step 6, the calendar nudge) is where this would eventually plug in --
today it just asks you to confirm things are on your calendar, which
still works fine with zero integration.
