---
name: research-assistant
description: Use this when the user asks you to look something up, research a topic, compare options, or find information for a task or decision ("can you research X", "look into Y for me", "find out about Z", "what are people saying about..."). Produces a structured summary with sourced findings and links, not just a raw answer.
---

# Web research

Use the `WebSearch` and `WebFetch` tools to gather information, then report
back in this shape (as chat text, not a file, unless the user asks to save
it):

1. **Bottom line** -- 1-3 sentences answering the actual question first.
2. **Key findings** -- bullet points, each grounded in something you
   actually found (not general knowledge), each with an inline source link.
3. **Sources** -- the links you drew on, as a short list.
4. **My take** -- a brief, clearly-labeled opinion/insight if you have one
   (tradeoffs, what you'd personally lean toward), kept separate from the
   sourced findings so the user can tell fact from judgment.

Guidelines:
- Do at least 2-3 distinct searches/fetches for anything non-trivial rather
  than reporting the first result. Cross-check surprising or high-stakes
  claims against a second source.
- Prefer primary/official sources over aggregator blog posts when both are
  available.
- If the topic is time-sensitive (pricing, availability, current events),
  say so and note when you searched.
- If results conflict, say what conflicts rather than picking one silently.

## Tying research back to the day plan

If this research was for a task that's on today's plan (check with
`python3 "$CLAUDE_PLUGIN_ROOT/scripts/plan_cli.py" show` if unsure), offer
to attach a short pointer to it:

```
python3 "$CLAUDE_PLUGIN_ROOT/scripts/plan_cli.py" update-task --id <id> --notes "<one-line summary + top link>"
```

## Saving a longer write-up

Only if the user asks to keep it (not by default -- don't clutter their
disk), save the full findings as markdown to
`~/.patriot/research/<YYYY-MM-DD>-<short-slug>.md` and tell them
the path.
