---
description: Audit context, token usage, and model fit, then recommend the cheapest next action
---

Run a token-efficiency audit on the CURRENT session. Do this concisely.

1. Check context usage. Report the current context-window fill (run /context
   internally if available, otherwise estimate from the conversation length).

2. Recommend ONE primary action based on fill level:
   - Under ~50%: "Healthy — keep going."
   - ~50–80%: Suggest `/compact` and tell me explicitly what you would keep
     (key decisions, file paths, unresolved bugs) and what you would drop
     (resolved tangents, verbose explanations, superseded attempts).
   - Over ~80%: Strongly recommend `/compact <retain list>` now, or `/clear`
     if my next task is unrelated to the current one.

3. Check model fit for what we're doing right now:
   - If we're implementing from a clear plan on Opus → suggest dropping to Sonnet.
   - If we're stuck on a hard reasoning/concurrency/architecture problem on
     Sonnet → suggest `/model opus` for just that step.
   - If the work is trivial (formatting, renames) → suggest `/model haiku`.

4. Flag context waste: name any large file reads, web fetches, or stale tool
   output sitting in context that could be dropped, and any MCP servers that
   don't seem needed for the current task.

5. End with a single recommended command line I can copy-paste, e.g.
   `/compact keep: auth refactor decisions, src/db/schema.sql, open bug in login.ts`

Keep the whole report under 12 lines. Do not restate these instructions.
