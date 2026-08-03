# agentguard — capture layer, Sprint 2B

## Status

- [x] `CaptureEvent` / `NormalizedEvent` types (`capture/types.py`)
- [x] Real git adapter, tested against real commits: first commit (no
      parent — empty-tree diff fallback), multi-line commit body, normal
      commit with parent (`capture/git_adapter.py`)
- [x] Context Normalizer with `intent_source` (explicit/inferred) tagging
      (`capture/normalizer.py`)
- [x] `BaseAdapter` / `TelemetrySource` interfaces — pull vs push, kept
      separate deliberately (`capture/interfaces.py`)
- [x] `GitAdapter` class wrapping the tested `capture_from_git()` function,
      `priority=100` (last resort) — logic unchanged, only `is_available()`
      is new (`capture/git_adapter.py`)
- [x] `CaptureManager`: telemetry-first, priority-ordered native fallback,
      tested against both branches with fakes (`capture/manager.py`,
      `capture/fakes.py`, `test_manager.py`)
- [x] `LmApiAdapter` and `DebugAdapter` — still fake, env-var gated so they
      never silently report available, but real `BaseAdapter` subclasses
      with correct priorities (0 and 10 respectively). Full three-adapter
      priority chain (LM API > Debug > Git) tested end-to-end
      (`capture/lm_api_adapter.py`, `capture/debug_adapter.py`,
      `test_priority_chain.py`)
- [x] **LM API feasibility spike — RESOLVED.** `vscode.lm` has no
      intercept/observe hook; see `docs/finding-lm-api-tier1.md`. Tier 1
      narrowed in scope, Tier 2 (documented hooks) promoted to primary
      real-time capture path.
- [x] `ClaudeCodeHookAdapter` — the first genuinely REAL non-git adapter.
      `priority=5`. Bridges Claude Code's push-based hooks
      (`UserPromptSubmit`, `Stop`) to the pull-based `BaseAdapter` contract
      via the filesystem (`.agentguard/pending_captures/`). Tested against
      a realistic simulated hook round trip, including a transcript with
      tool-call lines interleaved to confirm the parser correctly finds
      the final assistant text
      (`capture/claude_code_hook_adapter.py`,
      `capture/claude_code_hooks/hook_handler.py`,
      `test_claude_code_hook.py`)
- [x] `CopilotHookAdapter` — `priority=6`. GitHub Copilot's hooks reference
      documents a "VS Code compatible" payload format (PascalCase event
      names) with field names identical to Claude Code's - confirmed from
      Copilot's own docs, not assumed. Both adapters now share
      `hook_shared.py` (write side) and `hook_adapter_base.py` (read side)
      instead of duplicating logic.
      **Bug fixed while building this:** `ClaudeCodeHookAdapter`'s original
      file glob had no adapter-tag prefix, so if a second agent ever wrote
      into the same `pending_captures/` directory, captures could be
      cross-picked and mislabeled. Fixed by tagging every pending-capture
      filename with its adapter (`<tag>__<session_id>__...`). Verified with
      a dedicated two-agent isolation test.
      (`capture/copilot_hook_adapter.py`, `capture/copilot_hooks/`,
      `capture/hook_shared.py`, `capture/hook_adapter_base.py`,
      `test_copilot_hook.py`)
      **Not yet verified:** whether Copilot's real transcript file uses the
      same JSONL schema as Claude Code's - only the payload *envelope*
      fields are confirmed identical, not the transcript body format.

## Layout

```
agentguard.py           <- your existing CLI (capture/list/show)
test_git_adapter.py     <- Day 1: standalone git adapter + normalizer check
test_manager.py         <- Day 2: CaptureManager branch tests
test_priority_chain.py  <- Day 3: LM API > Debug > Git priority ordering
test_claude_code_hook.py <- Day 4: full Claude Code hook round trip (simulated)
test_copilot_hook.py     <- Day 5: Copilot hook round trip + two-agent isolation
docs/
    finding-lm-api-tier1.md  <- Day 4 finding: Tier 1 not viable, Tier 2 promoted
capture/
    __init__.py              <- public exports
    types.py                 <- CaptureEvent, NormalizedEvent, IntentSource, ToolCall
    interfaces.py            <- BaseAdapter (pull), TelemetrySource (push)
    git_adapter.py             <- capture_from_git() function + GitAdapter class (REAL)
    lm_api_adapter.py          <- LmApiAdapter class (FAKE, narrowed scope per finding)
    debug_adapter.py           <- DebugAdapter class (FAKE, env-var gated)
    hook_shared.py             <- shared write-side logic (both hook handlers use this)
    hook_adapter_base.py       <- FileBridgedHookAdapter (shared read-side BaseAdapter)
    claude_code_hook_adapter.py <- ClaudeCodeHookAdapter(FileBridgedHookAdapter), priority=5
    copilot_hook_adapter.py     <- CopilotHookAdapter(FileBridgedHookAdapter), priority=6
    claude_code_hooks/
        hook_handler.py          <- script Claude Code actually invokes
        settings_snippet.json    <- .claude/settings.json registration example
    copilot_hooks/
        hook_handler.py          <- script Copilot actually invokes
        hooks_config_snippet.json <- .github/hooks/*.json registration example
    normalizer.py             <- CaptureEvent -> NormalizedEvent
    manager.py                <- CaptureManager (telemetry-first, priority fallback)
    fakes.py                  <- FakeAdapter, FakeTelemetrySource (test-only, generic)
```

## Run it

```bash
python test_git_adapter.py       # git adapter + normalizer, against this repo's real history
python test_manager.py           # CaptureManager: both branches, using generic fakes
python test_priority_chain.py    # LM API > Debug > Git, using real adapter classes (fake capture())
python test_claude_code_hook.py  # full hook round trip, simulated stdin + realistic transcript
python test_copilot_hook.py      # Copilot hook round trip + two-agent isolation test
```

## Using ClaudeCodeHookAdapter for real (not simulated)

1. Copy `capture/claude_code_hooks/settings_snippet.json` into your
   `.claude/settings.json`, replacing the placeholder path with the real
   absolute path to `hook_handler.py` on your machine.
2. Use Claude Code normally in this project. Every prompt/response pair
   will land in `.agentguard/pending_captures/` automatically.
3. `ClaudeCodeHookAdapter().capture()` (via `CaptureManager`) picks up the
   oldest pending capture on demand.

## Using CopilotHookAdapter for real (not simulated)

1. Copy `capture/copilot_hooks/hooks_config_snippet.json` into
   `.github/hooks/agentguard.json` in this repo, replacing the placeholder
   path with the real absolute path to `copilot_hooks/hook_handler.py`.
2. Use Copilot CLI or Copilot cloud agent normally in this project.
3. **Before trusting this against a real session**, check whether the
   transcript file Copilot actually writes matches the JSONL "type":
   "assistant" schema `hook_shared._extract_last_assistant_message()`
   assumes. If it doesn't, only that one function needs adjusting.

## Next: Day 6+

- Fold `ClaudeCodeHookAdapter`, `CopilotHookAdapter`, and `GitAdapter` into
  `agentguard.py`'s real CLI (`capture --source <name>`) instead of
  standalone test scripts.
- Real `DebugAdapter` (log/chat-view scraping) stays deferred - lowest
  priority now that two real Tier 2 adapters exist.
- Update proposal Section 4.2 with the Tier 1 -> Tier 2 finding AND the
  "Tier 2 is a property of the agent harness, not the model" framing -
  add an Agent x Tier coverage matrix (Claude Code: Tier 2 real, Copilot:
  Tier 2 real, Codex CLI/Windsurf: unconfirmed, Qwen/Mistral: depends on
  harness, not applicable directly).
- Verify the Copilot transcript-format assumption against a real session
  once Console credits are available for other work anyway.
- Consider a real telemetry source (OTel/Langfuse) as the next piece, now
  that both branches of `CaptureManager` have at least one real adapter
  behind them, and two real adapters exist in the native fallback chain.

## Design notes worth remembering

- **`BaseAdapter` and `TelemetrySource` are separate interfaces, not one.**
  Native adapters are pull-based (`is_available()` then `capture()`).
  Telemetry sources are push-based (`subscribe(callback)`, events arrive on
  their own schedule). Forcing telemetry through `BaseAdapter.capture()`
  would mean polling a buffer or arbitrarily blocking on the first span —
  see `capture/interfaces.py` docstring, and proposal Section 4.2.

- **`GitAdapter` is a thin wrapper, not a rewrite.** `capture_from_git()`
  was validated against real commits before the class existed. Refactoring
  into `BaseAdapter` only added `is_available()` — the capture logic itself
  didn't change, on purpose, since it was already tested.

- **`priority` is fidelity-based, not arbitrary.** Git = 100 (last resort,
  produces only `inferred` intent). LM API and Debug adapters, when built,
  should get lower numbers (0, 10) since they capture explicit prompts.

- **`CaptureManager.start()` only handles telemetry sources.**
  Native adapters are pull-based and have no "start listening" concept —
  they get triggered on demand via `capture_once()` (e.g. from a git
  post-commit hook, or a CLI command), not from `start()`.

- **`fakes.py` is test-only scaffolding**, same reasoning as ChatGPT's
  original fake-adapter suggestion — it exists to prove `CaptureManager`'s
  branching logic works before real Debug/LM API adapters exist, not to
  ship as part of the library.

- **`LmApiAdapter` and `DebugAdapter` are different from `fakes.py`.**
  `fakes.py` is throwaway (`FakeAdapter`, used only in `test_manager.py`).
  `LmApiAdapter`/`DebugAdapter` are the real classes that will keep their
  names and priorities once `capture()` is replaced with a working
  integration — only the internals change. This is the "replace one fake
  at a time" step from the original plan: the class stays, the fake body
  gets swapped out.

- **Both fakes are gated behind an env var**
  (`AGENTGUARD_FAKE_LM_API_AVAILABLE=1`, `AGENTGUARD_FAKE_DEBUG_AVAILABLE=1`),
  not hardcoded to `return True`. This means running the CLI normally never
  accidentally routes through fake data — a fake can only "win" if a test
  deliberately turns it on. When real integrations replace these, this gate
  gets deleted, not left in as dead code.


