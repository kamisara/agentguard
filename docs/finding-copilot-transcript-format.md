# Finding: Copilot's hook payload envelope matches Claude Code's, but the transcript body format does not.

**Date:** Sprint 2B, Day 5 (live-session test)
**Source:** real Copilot CLI session, `events.jsonl`, 2026-08-04.

## What was confirmed

Copilot's `UserPromptSubmit`/`Stop` hook **envelope** fields (`session_id`,
`cwd`, `transcript_path`, `hook_event_name`) are genuinely identical to
Claude Code's, as documented. That part of the earlier assumption held.

## What was wrong

The transcript **body** format is not shared. Real Copilot transcript
entries for assistant turns look like:

```json
{"type": "assistant.message", "data": {"content": "...", "toolRequests": [...]}}
```

Claude Code's format:

```json
{"type": "assistant", "message": {"content": "..."}}
```

Different `type` value (`assistant.message` vs `assistant`), different
nesting (`data.content` vs `message.content`), and Copilot's `content` is
always a plain string - no content-block-list variant for mixed tool-use +
text turns like Claude Code has.

## What broke, and how it surfaced

`CopilotHookAdapter` initially reused `hook_shared._extract_last_assistant_message`
(built for Claude Code's format). Against real data, it silently returned
an empty `response` field - no error, no crash, just a blank capture. This
is exactly the failure mode to watch for elsewhere: a malformed/mismatched
transcript parser doesn't fail loud, it fails quiet.

## Fix

Transcript parsing is no longer shared between agents. Each hook handler
now supplies its own parser to `hook_shared.handle_stop()`:

- `capture/claude_code_hooks/transcript_parser.py` - unchanged logic, just
  relocated out of the shared module.
- `capture/copilot_hooks/transcript_parser.py` - new, built directly from
  the real `events.jsonl` excerpt, not from documentation or inference.

The stash/pair mechanism (`hook_shared.py`) stays genuinely shared - only
transcript body parsing needed to split.

## Consequence for the architecture / proposal

This is worth stating plainly in Section 4.2 or the evaluation section:
**a documented "compatible" hook envelope does not imply a compatible
transcript format.** Any future agent integration (a third Tier-2 adapter)
should assume the transcript body needs its own verification pass against
real output, even if the envelope fields look identical on paper. This is
a genuine, defensible methodological point for the thesis - the project
caught its own wrong assumption via testing rather than shipping it
silently.
