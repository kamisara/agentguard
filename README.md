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
      **Live-session finding, confirmed and fixed:** the hook *envelope*
      matches Claude Code's, but the transcript *body* format does not -
      real Copilot transcripts use `{"type": "assistant.message", "data":
      {"content": ...}}`, not Claude Code's `{"type": "assistant",
      "message": {"content": ...}}`. Transcript parsing is no longer
      shared between agents - each hook handler supplies its own parser
      (`capture/claude_code_hooks/transcript_parser.py`,
      `capture/copilot_hooks/transcript_parser.py`). See
      `docs/finding-copilot-transcript-format.md`.
- [x] Automatic zero-config agent detection - the real fix for the
      cross-registration bug above. Each hook handler checks whether the
      transcript it was actually handed matches its OWN agent's known
      shape (`transcript_looks_like_copilot`/`transcript_looks_like_claude_code`)
      before writing anything - no developer action required, works out
      of the box. Proven against the exact real bug scenario, zero manual
      config, in `test_auto_agent_detection.py`. `active_adapter.py` /
      `set_active_adapter.py` still exist as an optional manual override
      for testing, not required in normal operation.
- [x] `OtelGenAiTelemetrySource` - the first REAL `TelemetrySource` (not
      the generic `FakeTelemetrySource` used to test `CaptureManager`'s
      branching). Runs a real local OTLP/HTTP+JSON receiver
      (`capture/otel_telemetry_source.py`), parses GenAI semantic
      convention spans (`capture/otel_genai_parser.py`) built from
      documented `gen_ai.*` attribute names. Tested against a real HTTP
      round trip - genuine server, genuine POST request, correctly
      filters a non-GenAI span in the same payload
      (`test_otel_telemetry_source.py`). Two honesty notes in the code:
      OTLP/HTTP+JSON only (no protobuf/gRPC, to avoid that dependency),
      and the GenAI conventions are Development-status/unstable as of
      this writing, confirmed via search but not against a real emitted
      payload. **Bonus finding**: VS Code Copilot itself emits OTel GenAI
      telemetry natively, per OpenTelemetry's own docs - meaning this is
      a second, real, hook-independent path into Copilot's traffic if
      OTel export is configured.

## Layout

```
agentguard.py            <- your existing CLI (capture/list/show)
set_active_adapter.py    <- CLI helper: restrict which hook handler writes
test_git_adapter.py      <- Day 1: standalone git adapter + normalizer check
test_manager.py          <- Day 2: CaptureManager branch tests
test_priority_chain.py   <- Day 3: LM API > Debug > Git priority ordering
test_claude_code_hook.py <- Day 4: full Claude Code hook round trip (simulated)
test_copilot_hook.py     <- Day 5: Copilot hook round trip + two-agent isolation
test_active_adapter_gate.py <- Day 5: active-adapter gate, both directions
test_auto_agent_detection.py <- Day 5: automatic detection, zero manual config
test_otel_telemetry_source.py <- Day 6: real OTLP/HTTP+JSON telemetry source
docs/
    finding-lm-api-tier1.md  <- Day 4 finding: Tier 1 not viable, Tier 2 promoted
    finding-copilot-transcript-format.md <- Day 5 finding: transcript body differs per agent
capture/
    __init__.py              <- public exports
    types.py                 <- CaptureEvent, NormalizedEvent, IntentSource, ToolCall
    interfaces.py            <- BaseAdapter (pull), TelemetrySource (push)
    git_adapter.py             <- capture_from_git() function + GitAdapter class (REAL)
    lm_api_adapter.py          <- LmApiAdapter class (FAKE, narrowed scope per finding)
    debug_adapter.py           <- DebugAdapter class (FAKE, env-var gated)
    active_adapter.py          <- single-active-adapter gate (marker file based)
    hook_shared.py             <- shared write-side logic (both hook handlers use this)
    hook_adapter_base.py       <- FileBridgedHookAdapter (shared read-side BaseAdapter)
    claude_code_hook_adapter.py <- ClaudeCodeHookAdapter(FileBridgedHookAdapter), priority=5
    copilot_hook_adapter.py     <- CopilotHookAdapter(FileBridgedHookAdapter), priority=6
    claude_code_hooks/
        hook_handler.py          <- script Claude Code actually invokes
        transcript_parser.py     <- Claude Code specific transcript parsing
        settings_snippet.json    <- .claude/settings.json registration example
    copilot_hooks/
        hook_handler.py          <- script Copilot actually invokes
        transcript_parser.py     <- Copilot specific transcript parsing (real format!)
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
python test_active_adapter_gate.py  # active-adapter gate, both directions
python test_auto_agent_detection.py # automatic detection, zero manual config - the real fix
python test_otel_telemetry_source.py # real OTLP/HTTP+JSON server, real GenAI span parsing
```

## Using the active-adapter gate

If you have both `.claude/settings.json` and `.github/hooks/*.json`
registered at the same time (likely, since Copilot reads both as a
documented cross-tool source), set which one should actually write
captures before starting a session:

```bash
python set_active_adapter.py copilot_hook       # only copilot_hook writes
python set_active_adapter.py claude_code_hook   # only claude_code_hook writes
python set_active_adapter.py clear              # no restriction, both write
```

This writes/clears `.agentguard/active_adapter.txt`. Both hook handlers
check it before writing anything - the non-active one silently no-ops
instead of producing a stray/empty capture.

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
   **On Windows, quote the path inside the command string** - an unquoted
   path with spaces (e.g. `D:/code pfe 2/agentguard/...`) gets split into
   multiple arguments and the hook silently fails. Use
   `"command": "python \"D:/code pfe 2/agentguard/...\""`.
2. Use Copilot CLI normally in this project (must be run through the
   actual CLI session - a VS Code chat sidebar panel is a different
   Copilot surface and does not fire `.github/hooks/*.json` hooks).
3. **Confirmed working against a real session (2026-08-04)** - prompt and
   response both captured correctly, `intent_source: explicit`.

**Cross-registration issue - now fixed with a gate, see below.** If both
`.claude/settings.json` and `.github/hooks/agentguard.json` are registered
at once, Copilot CLI fires both handlers for a single session, producing
one real capture and one stray empty one. Use the active-adapter gate
below to suppress the handler you're not using.

## Only the agent actually in use produces a capture - automatically, no config

This matters because AgentGuard's real target is a VS Code extension - a
developer should never have to run a setup command telling it which agent
they're using. Detection has to happen on its own, per session.

Copilot CLI reads `.claude/settings.json` as a documented cross-tool source,
so a single Copilot session can fire BOTH hook handlers at once. The fix is
automatic: at `Stop` time, each hook handler checks whether the transcript
it was actually handed matches ITS OWN agent's known shape
(`claude_code_hooks/transcript_parser.py::transcript_looks_like_claude_code`,
`copilot_hooks/transcript_parser.py::transcript_looks_like_copilot`). If it
doesn't match, that handler cleans up its stash and writes nothing - no
developer action, no pre-declared choice, works out of the box.

**Confirmed asymmetry, stated honestly in the code:** Copilot's shape-check
is built from a real live transcript (2026-08-04). Claude Code's still
rests on the original unverified assumption about its transcript format,
since that live test was never done. If Claude Code's real format turns
out to differ (the way Copilot's did), only
`transcript_looks_like_claude_code` needs correcting.

Proven end-to-end in `test_auto_agent_detection.py`: simulates the exact
real cross-registration bug (one Copilot session, both hooks configured,
zero manual configuration) and confirms only the correct adapter produces
a capture.

`capture/active_adapter.py` / `set_active_adapter.py` still exist as an
**optional manual override** - useful for testing, or forcing a choice when
you want it - but nothing in normal operation requires it anymore:

```bash
python set_active_adapter.py copilot_hook       # force only Copilot's hook to write
python set_active_adapter.py clear              # remove the override (default state)
python set_active_adapter.py show               # check current setting
```

## Using OtelGenAiTelemetrySource for real (not simulated)

```python
from capture import OtelGenAiTelemetrySource, CaptureManager

source = OtelGenAiTelemetrySource()  # localhost:4318/v1/traces, OTLP's standard port
manager = CaptureManager(telemetry_sources=[source], native_adapters=[...])
manager.start(on_event=lambda e: ...)  # subscribes, starts the local receiver
```

Point any OTel SDK's default OTLP/HTTP JSON exporter at `localhost:4318` (or
configure an OTel Collector to forward there) and real GenAI spans will
start flowing in. **Not yet tested against a real exporter** - only against
a hand-built payload matching the documented attribute names. If a real
exporter's message-content shape differs from what
`otel_genai_parser._messages_to_text` expects, only that function needs
adjusting - same isolation pattern used throughout this project.

## Next: Day 7+

- Fold `ClaudeCodeHookAdapter`, `CopilotHookAdapter`, `GitAdapter`, and
  `OtelGenAiTelemetrySource` into `agentguard.py`'s real CLI instead of
  standalone test scripts.
- Real `DebugAdapter` (log/chat-view scraping) stays deferred - lowest
  priority now that two real Tier 2 adapters and one real Telemetry
  Source exist.
- Update proposal Section 4.2 with the Tier 1 -> Tier 2 finding AND the
  "Tier 2 is a property of the agent harness, not the model" framing -
  add an Agent x Tier coverage matrix (Claude Code: Tier 2 real, Copilot:
  Tier 2 real AND Telemetry Source real (native OTel emission) - both
  verified against live sessions/data, Codex CLI/Windsurf: unconfirmed,
  Qwen/Mistral: depends on harness, not applicable directly).
- Worth a line in the evaluation/methodology section: the Copilot
  transcript-format finding (`docs/finding-copilot-transcript-format.md`)
  is a good concrete example of "assumption tested and corrected" for the
  design science research writeup. The GenAI semantic convention
  instability (Development-status, no 1.0 release) is worth a line too -
  a real methodological risk for anyone building on it right now, not
  just this project.
- Validate `OtelGenAiTelemetrySource` against a real OTel-instrumented
  app or Collector once one is available - same "confirm before trusting"
  discipline applied to the hook adapters.

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


