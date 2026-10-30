---
name: handoff
description: Write a handoff doc for the current chat (docs/HANDOFF_<date>.md) so the next session or Andrew can pick the work up cold, and point the RESUME HERE memory at it. Use when Andrew asks for a handoff, a handoff doc, a wrap-up / end-of-session write-up, "write down where we are", or says he is closing the chat and wants the state saved.
---

# Handoff doc for the current chat

The doc is for whoever picks the work up next: a fresh Claude session with no memory of this chat, or Andrew coming
back days later. It must stand on its own. Model it on `docs/HANDOFF_2026-10-26.md`: state first, then what changed
in plain words, then numbers, then what is open.

## 1. Gather the facts (read-only)

Don't write from memory of the chat alone. Early parts may have been summarized away, so check the record:

- **Session id:** the newest transcript, `ls -t ~/.claude/projects/-Users-user-Documents-code-petey-2/*.jsonl | head -1`
  (the first 8 characters of the file name, as in "session 363984ad").
- **Branch and commits:** `git branch --show-current`; commits not pushed, `git log --oneline @{u}..` (if there is no
  upstream, compare with `origin/<branch>` or say so); this session's commits by their messages.
- **Uncommitted:** `git status --short`. Sort each file into **this session's work** or **someone else's** (Andrew's
  saves, another session). Don't claim a file you didn't touch; say "not this session's" when unsure.
- **Tests:** `make test`, and quote the last line (e.g. "310 passed"). If something fails, say which and why.
- **Left running or left behind:** background tasks, test servers (`lsof -nP -iTCP -sTCP:LISTEN | grep -i python`),
  drafts or records this chat created under `runs/` (test copies discarded? backups restored?), scratch files that
  matter, and caches that went stale ([[feedback-track-caches]]).
- **The previous handoff** (`ls docs/HANDOFF_*`) and the RESUME HERE memory: say what this doc supersedes.

## 2. Write `docs/HANDOFF_<YYYY-MM-DD>.md`

If today's file already exists from another session, don't overwrite it. Use `docs/HANDOFF_<date>_<topic>.md`
with a one- or two-word topic (e.g. `HANDOFF_2026-10-26_groups.md`).

Sections, in this order (leave out any that would be empty):

1. **Title and lead.** `# Handoff <date>[: topic]`, then one paragraph: the session id, the branch, the review page
   address, and what the session was about.
2. **State of the branch.** Commits since the last push, one bullet each (hash, area, what). Then uncommitted work,
   split into this session's and others'. Then the test count, and anything left running.
3. **What changed, in plain words.** One short bold-led paragraph per change: what it does as Andrew sees it on the
   review page, and why, with his words quoted and dated where he gave the reason. Include bugs found and fixed along
   the way, and anything tried and reverted, with the reason.
4. **Numbers.** Measurements made this session, **per field** ([[feedback-per-page]]): times, costs, counts,
   before/after. Say what each was measured on. A table if there are several.
5. **Tested and not tested.** What was checked end to end (browser, real form), and what was only unit-tested or
   not exercised at all. Don't let "tests pass" stand in for "it works".
6. **Open, in rough order.** Numbered. Each item gives the next step and whether it waits on Andrew.
7. **Andrew's open calls.** Decisions only he makes; don't act without him. Link each form and field.
8. **Working agreements from this session.** New preferences or corrections Andrew gave. Those also go into memory
   as feedback (step 3).

## Style

- Plain words; say what Andrew sees, not internal function names. Code paths only where the next session needs
  them to find the code.
- Link every form, field, grid and block to the review page: `http://localhost:5005/#review/<id>`,
  `#review/<id>/<field code>`, `#grids/<id>/<grid id>`, `#blocks/<id>/<block id>` ([[feedback-link-forms]]).
  Name forms by review-page id and fields by code ([[feedback-field-codes]]).
- Say "field", not "box" ([[feedback-terminology]]).
- Put a blank line before list items. No emoji.
- Don't hedge what was verified, and don't present what wasn't as done.

## 3. Point memory at it

- In `memory/project-resume-here.md`, add a new top line: `**<date> END: read docs/HANDOFF_<...>.md first**`,
  followed by a one-sentence summary of the state (pushed or not, what's uncommitted, what's next).
- Update the RESUME HERE line in `MEMORY.md` to match.
- Save any new working agreement as its own feedback memory, or update the existing one that covers it.

## 4. Finish

Don't commit the doc unless Andrew asks. In the reply, give the doc's path, the three or four things that most need
him (unpushed commits, uncommitted work, open calls), and the line saying who it was written for.
