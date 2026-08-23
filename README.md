#testestlolo
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
      branching). Runs a real local OTLP/HTTP receiver
      (`capture/otel_telemetry_source.py`) supporting BOTH real OTLP
      encodings: **protobuf** (`application/x-protobuf`, decoded via the
      official `opentelemetry-proto` generated classes - genuine
      wire-format compatibility, the actual default almost every OTel
      exporter uses) and **JSON** (`application/json`, hand-parsed,
      secondary encoding). GenAI span extraction
      (`capture/otel_genai_parser.py`) is shared between both encodings -
      only decoding differs (`capture/otlp_protobuf_parser.py`). Tested
      against a real HTTP round trip for both encodings - the protobuf
      test payload is built using the OFFICIAL OTel classes
      (`ExportTraceServiceRequest`), the same way a real SDK would
      construct it, not a hand-rolled byte guess
      (`test_otel_telemetry_source.py`). Correctly filters a non-GenAI
      span present in the same payload, in both encodings.
      **First and only external dependency in the capture layer**
      (`opentelemetry-proto`, see `requirements.txt`) - deliberate,
      everything else is stdlib-only.
      Honesty notes still standing: no gRPC support (port 4317, the other
      common OTel default - would need `grpcio`, out of scope for now),
      GenAI conventions are Development-status/unstable as of this
      writing, and the exact message-content shape isn't confirmed
      against a real exporter's output, only against the documented
      attribute names. **Bonus finding**: VS Code Copilot itself emits
      OTel GenAI telemetry natively via protobuf by default, per
      OpenTelemetry's own docs - meaning the protobuf path here is what
      actually matters for a second, hook-independent path into Copilot's
      real traffic, if OTel export is configured.

## Layout

```
agentguard.py            <- your existing CLI (capture/list/show)
requirements.txt         <- opentelemetry-proto (only external dependency)
set_active_adapter.py    <- CLI helper: restrict which hook handler writes
test_git_adapter.py      <- Day 1: standalone git adapter + normalizer check
test_manager.py          <- Day 2: CaptureManager branch tests
test_priority_chain.py   <- Day 3: LM API > Debug > Git priority ordering
test_claude_code_hook.py <- Day 4: full Claude Code hook round trip (simulated)
test_copilot_hook.py     <- Day 5: Copilot hook round trip + two-agent isolation
test_active_adapter_gate.py <- Day 5: active-adapter gate, both directions
test_auto_agent_detection.py <- Day 5: automatic detection, zero manual config
test_otel_telemetry_source.py <- Day 6: real OTLP receiver, protobuf + JSON
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
    active_adapter.py          <- single-active-adapter gate (marker file based, optional)
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
    otel_telemetry_source.py   <- OtelGenAiTelemetrySource (REAL), local OTLP HTTP receiver
    otel_genai_parser.py       <- shared GenAI span extraction (JSON path decodes here too)
    otlp_protobuf_parser.py    <- REAL OTLP protobuf decoding (official opentelemetry-proto classes)
    normalizer.py             <- CaptureEvent -> NormalizedEvent
    manager.py                <- CaptureManager (telemetry-first, priority fallback)
    fakes.py                  <- FakeAdapter, FakeTelemetrySource (test-only, generic)
```

## Run it

**One-time setup:** `pip install -r requirements.txt` (only needed for
`test_otel_telemetry_source.py` - the OTel telemetry source is the one
piece with a real external dependency; everything else is stdlib-only).

```bash
python test_git_adapter.py       # git adapter + normalizer, against this repo's real history
python test_manager.py           # CaptureManager: both branches, using generic fakes
python test_priority_chain.py    # LM API > Debug > Git, using real adapter classes (fake capture())
python test_claude_code_hook.py  # full hook round trip, simulated stdin + realistic transcript
python test_copilot_hook.py      # Copilot hook round trip + two-agent isolation test
python test_active_adapter_gate.py  # active-adapter gate, both directions
python test_auto_agent_detection.py # automatic detection, zero manual config - the real fix
python test_otel_telemetry_source.py # real OTLP receiver, both protobuf (official classes) and JSON encodings
python test_otel_real_payload_shape.py # message parsing against the CONFIRMED real Copilot payload shape
python test_attestation_generation.py # Sprint 3: attestation generation against real git + real Copilot data
python test_tool_call_extraction.py   # Sprint 3 Day 2: tool call parsing, against real Copilot transcript data
python test_tool_calls_end_to_end.py  # Sprint 3 Day 2: full pipeline, hook subprocess -> attestation
python test_attestation_classification.py # Sprint 3 Day 3: retrieved_context/tool_invocations split, prompt_lineage
python test_signing.py                # Sprint 4 Day 1: local-key signing, tamper detection, wrong-key rejection, portability
python test_sigstore_keyless.py       # Sprint 4 Day 2: Sigstore keyless module - imports/naming/error-handling only, see docstring
python test_git_notes.py              # Sprint 5 Day 1: git notes, against this repo's real commits
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

**Setup (one-time):**
```powershell
PS D:\code pfe 2\agentguard> pip install -r requirements.txt
```

```python
from capture import OtelGenAiTelemetrySource, CaptureManager

source = OtelGenAiTelemetrySource()  # localhost:4318/v1/traces, OTLP's standard port
manager = CaptureManager(telemetry_sources=[source], native_adapters=[...])
manager.start(on_event=lambda e: ...)  # subscribes, starts the local receiver
```

Point any OTel SDK's default OTLP/HTTP exporter at `localhost:4318` (or
configure an OTel Collector to forward there) and real GenAI spans will
start flowing in - the receiver handles the exporter's default protobuf
encoding correctly, not just JSON. **Not yet tested against a real
exporter's live output** - update: it WAS tested, live, against a real
Copilot session (2026-08-08/09) - see `docs/finding-otel-live-validation.md`.
Two infrastructure bugs and one parser-shape bug were found and fixed as a
result; this note originally said "not yet tested" before that happened.

**For VS Code Copilot specifically:** confirmed working end-to-end against
a real live session. Settings that worked:
```json
{
  "github.copilot.chat.otel.enabled": true,
  "github.copilot.chat.otel.exporterType": "otlp-http",
  "github.copilot.chat.otel.otlpEndpoint": "http://localhost:4318",
  "github.copilot.chat.otel.captureContent": true
}
```
Note: no `/v1/traces` suffix on the endpoint - the exporter appends it
itself; adding it manually causes a doubled path and a 404 (this was one
of the two bugs found). Must go through a genuinely fresh Copilot CLI
session (env vars are forwarded at session launch, not live) - the VS
Code chat sidebar is a different surface and won't route through this
setting at all.

## Sprint 3: Automatic Attestation Generation

- [x] `ContextualAttestation` schema (`attestation/types.py`) - fields
      follow the proposal's Section 4.3 list (developer intent, prompt
      lineage, agent identity, execution environment, tool invocations,
      retrieved context, human review status, policy compliance flags).
      `retrieved_context`, `human_review_status`, `policy_compliance_flags`
      are explicit placeholders, not guessed at - `retrieved_context`
      needs a way to distinguish RAG calls from other tool calls (not
      built yet), `human_review_status` needs a review workflow
      (future/dashboard scope), `policy_compliance_flags` is explicitly
      Sprint 8 scope.
- [x] `generate_attestation()` (`attestation/generator.py`) -
      `NormalizedEvent -> ContextualAttestation`, fully automatic, no
      manual entry. This is the actual Sprint 3 deliverable: Sprint 1's
      `capture` command asked the developer to type in intent/prompt/model
      by hand; `auto-capture` replaces that entirely.
- [x] `attestation/store.py` - writes to the SAME `.agentguard/attestations/`
      convention Sprint 1's `capture` command already used. Old
      (`sprint1-v0`) and new (`sprint3-v1`) records coexist; `list`/`show`
      in `agentguard.py` read fields common to both without needing to
      know which schema a given file uses.
- [x] `agentguard.py auto-capture <git|claude_code_hook|copilot_hook>` -
      pulls a real event from the matching Sprint 2B adapter, normalizes,
      generates and writes an attestation automatically. Tested against a
      real commit from this repo's own history AND a real restored
      Copilot session capture from an actual live session (2026-08-08) -
      not invented fixtures (`test_attestation_generation.py`).
- [x] `agentguard.py otel-listen [seconds]` - OTel is push-based, so this
      starts the real receiver, listens for the given duration (default
      60s), and auto-attests every GenAI span that arrives via the
      `CaptureManager` callback - no polling loop needed.
- [x] **Bug found and fixed:** `test_git_adapter.py` (written Day 1,
      before the attestation schema existed) was also writing into
      `.agentguard/attestations/`, using an ad-hoc shape with no
      `attestation_id` field. Running it polluted the real attestation
      store and crashed `agentguard.py list`. Fixed at the root: that
      script no longer writes there at all (it only validates the
      capture pipeline now - `auto-capture` is the real attestation path).
      `list_attestations()` also hardened to skip malformed/foreign files
      gracefully instead of crashing, regardless of cause.

### Day 2: real tool-call data in `tool_invocations`

- [x] `tool_invocations` is now REAL for both hook adapters, not just
      `otel_genai`. `capture/copilot_hooks/transcript_parser.py::extract_tool_calls`
      is built against a **real** transcript excerpt (the actual events.jsonl
      content from live debugging, 2026-08-04) - `assistant.message`
      events carry `data.toolRequests`, `tool.execution_complete` events
      carry the matching `data.result`, paired by `toolCallId`. Confirmed
      field names, not inferred.
      `capture/claude_code_hooks/transcript_parser.py::extract_tool_calls`
      is built against the documented/assumed content-block shape
      (`{"type": "tool_use", ...}`) - **explicitly flagged unconfirmed**,
      same standing caveat as the rest of Claude Code's transcript
      parsing in this project (never live-tested). Output pairing isn't
      implemented there since the result-shape was never confirmed either
      - args are captured, `output` is always `None` for Claude Code
      until that gap is closed with real data.
- [x] `hook_shared.handle_stop()` takes an optional `tool_call_extractor`
      parameter; `hook_adapter_base.py` reads `tool_calls` back out when
      reconstructing a `CaptureEvent`, backward compatible with any
      pending-capture file written before this change (defaults to `[]`
      via `.get()`, doesn't crash on old files missing the field).
- [x] **Full pipeline proven, not just the isolated function** -
      `test_tool_calls_end_to_end.py` runs a real hook subprocess round
      trip (including a real tool call in the transcript) through to
      `ContextualAttestation.tool_invocations`, confirming the data
      survives every hop: hook subprocess -> pending capture file ->
      `CopilotHookAdapter.capture()` -> `CaptureEvent.tool_calls` ->
      `NormalizedEvent.tool_invocations` -> attestation.
      (`test_tool_call_extraction.py` covers the parser functions in
      isolation, against the same real Copilot data.)

### Day 3: `retrieved_context` and `prompt_lineage`, both real now

- [x] `retrieved_context` vs `tool_invocations` split by a NAME-PATTERN
      HEURISTIC (`attestation/generator.py::_is_retrieval_tool`) - tool
      calls whose name contains `view`/`read`/`search`/`grep`/`list`/
      `glob`/`fetch`/`get` land in `retrieved_context`; everything else
      stays in `tool_invocations`. **Stated honestly as a heuristic, not
      a confirmed signal** - no transcript from any agent tested so far
      carries an explicit "this was retrieval" field. Both directions
      tested (`test_attestation_classification.py`): a retrieval call
      (`view`, using real Copilot data) and a non-retrieval call (`edit`)
      both land where expected, plus a mixed batch.
      `test_tool_calls_end_to_end.py` updated accordingly - `view` now
      correctly lands in `retrieved_context`, not `tool_invocations`
      (this was the fix working, not a regression).
- [x] `prompt_lineage` - a `{"role", "content"}` list. Includes a
      `system` entry ONLY when the source adapter actually captured one
      (currently: `otel_genai`, via the confirmed
      `gen_ai.system_instructions` attribute), plus the user prompt.
      Hook-sourced events get a user-only lineage - stated honestly,
      hooks don't capture system prompt content at all right now.
      **Still partial**: doesn't yet include injected tool outputs
      mid-chain (the proposal's fuller definition) - that needs
      multi-turn conversation tracking this project doesn't do yet.

## Sprint 4, Day 1: Cryptographic Signing & Verification

**Scoping decision, stated upfront:** the proposal allows two paths -
Sigstore's keyless flow (Fulcio-issued short-lived certs tied to an OIDC
identity, logged to the public Rekor transparency log) or self-hosted key
infrastructure. This sprint implements the **self-hosted** path - real
Ed25519 asymmetric cryptography (the `cryptography` package), fully
testable locally with no network calls, browser OIDC flow, or external
Sigstore infrastructure. Keyless signing is a real, documented future
extension (see "Next" below), not silently skipped or faked.

- [x] `signing/keys.py` - Ed25519 keypair generation, stored PEM-encoded
      in `.agentguard/keys/`. `get_or_create_keypair()` generates on first
      use; `generate_keypair()` (explicit, separate function) overwrites -
      deliberately not the default path, so nobody silently invalidates
      every existing signature by accident.
- [x] `signing/signer.py` - signs over **canonical JSON**
      (`sort_keys=True, separators=(",", ":")`), not raw text - the same
      logical content can serialize to different bytes depending on key
      order/whitespace, which would produce false "tampered" verdicts
      that have nothing to do with actual tampering. Detached signature
      pattern: a sibling `<id>.sig` file, not embedded in the attestation
      JSON - keeps the attestation file's shape unchanged for anything
      that already reads it (agentguard.py list/show, every existing
      test).
- [x] `attestation/store.py::write_and_sign_attestation()` - composes
      writing + signing. `write_attestation()` (unsigned) still exists
      standalone, matching the proposal's own architecture table, which
      lists "Contextual Attestation generation" and "Cosign signing" as
      distinct sub-steps.
- [x] `agentguard.py auto-capture` / `otel-listen` now sign by default -
      a real pipeline shouldn't require a separate manual step to
      remember. New commands: `verify <id>`, `verify-all`.
- [x] **The actual point of signing, proven, not assumed:**
      `test_signing.py` signs an attestation, verifies it's valid,
      **tampers with the content, and confirms verification now fails** -
      both in-memory and by editing a real file on disk after signing.
      Also confirms verifying against the wrong public key is rejected.
      Manually re-confirmed against the real CLI: tampered a real signed
      attestation file, ran `verify-all`, got `✘ INVALID`
      (`signature does NOT match content`) - and confirmed unsigned
      records (Sprint 1's manual `capture`) are reported separately as
      `— UNSIGNED`, not silently skipped or crashed on.
      Full pipeline also tested against a real git commit capture, not
      just synthetic data.

## Sprint 4, Day 1 bugfix (portability)

**Real bug found and fixed via live testing (2026-08-16):** the original
`verify_signature_file()` trusted the `public_key_path` recorded inside
the `.sig` file at signing time - an ABSOLUTE path from wherever signing
happened. This broke immediately on a real machine: a `.sig` generated in
one environment (this sandbox) and shipped inside the delivery zip had a
recorded path like `/home/claude/inspect/agentguard/.agentguard/keys/...`,
meaningless on Windows. `verify-all` correctly reported these as
`✘ INVALID` - not silently wrong, but not useful either, since the
signatures were never actually tampered with.

**Fixed properly, not patched around:** `verify_signature_file()` now
derives the key location from the standard directory convention
(`.agentguard/keys/` as a sibling of `.agentguard/attestations/`,
computed relative to the attestation file's own current location) BEFORE
falling back to the recorded path. This means verification only depends
on `.agentguard/keys/` and `.agentguard/attestations/` staying together -
true as long as both move as part of the same directory, which they
always do. The recorded path in the `.sig` file is now just informational,
not load-bearing.

**Proven, not assumed:** `test_portable_across_machines()` deliberately
corrupts the recorded path to a nonexistent location and confirms
verification still succeeds via the standard-location lookup. Beyond the
unit test, manually reproduced the exact real scenario - copied the whole
project to a different absolute path (`/tmp/simulated_different_machine`)
and confirmed `verify-all` still reports `✔ VALID` for attestations signed
at the original path.


## Sprint 4, Day 2: Sigstore keyless signing — CONFIRMED WORKING LIVE

**Update (2026-08-18):** confirmed end-to-end on a real machine (home
network, no VPN/corporate firewall). Real browser OIDC login, real
Fulcio-issued certificate bound to a real identity, real Rekor
transparency log entry, real verification - all successful. The real
blocker turned out to be a **Windows-specific bug**, not network
access - `os.symlink()` failing with `OSError: [WinError 1314]` inside
the `tuf` library's trust-root cache management, requiring Developer Mode
(or Administrator) to fix. Full root-cause writeup, including how the
initial "network blocked" theory was corrected with real evidence:
`docs/finding-sigstore-windows-symlink.md`.



Two signing methods now exist, per the proposal's "Sigstore/Cosign, with
support for self-hosted key infrastructure" line - Day 1 built self-hosted
(local Ed25519 keys), Day 2 adds keyless.

**Real code, real (installed) API - honestly bounded by what could
actually be executed here.** `signing/sigstore_signer.py` uses the actual
`sigstore` Python package's real API, confirmed via runtime inspection of
the installed version (`sigstore==4.5.0`) rather than assumed from
memory - this library's public surface has changed across versions
(`SigningContext.production()` doesn't exist in this version; the real
path is `ClientTrustConfig.production()` + `SigningContext.from_trust_config()`),
and guessing wrong here would repeat the exact class of bug this project
has already hit and fixed twice (Copilot's transcript format, OTel's
message shape).

**What could NOT be executed in this environment, confirmed by directly
trying, not assumed:**
- A direct connection attempt to Fulcio (`fulcio.sigstore.dev`) returned
  HTTP 403 - blocked by network policy, not a DNS/timeout issue.
- Even `Verifier.production()` / `ClientTrustConfig.production()` alone
  (before any signing/verification happens) fails with `TUFError: Failed
  to refresh TUF metadata` - the trust-root fetch itself is blocked too.
- Keyless signing also requires an interactive browser OIDC login
  (`Issuer.identity_token()` blocks and opens a browser) - not something
  that can run headlessly in any sandbox, by design, since the whole
  point is binding to a real interactively-verified identity.

**What WAS tested here, safely** (`test_sigstore_keyless.py`): module
imports against the real API, the `.sigstore.json` bundle naming
convention (matches standard cosign/sigstore tooling), and that a missing
bundle fails with a clear message rather than crashing. The CLI commands
(`sign-keyless`/`verify-keyless`) also catch the confirmed real
TUF/network failure mode and print an actionable explanation instead of a
raw traceback - manually tested against the actual blocked network in
this environment, not simulated.

**To actually test keyless signing for real**, on a machine with normal
internet access (not this restricted sandbox):
```powershell
python agentguard.py auto-capture git
python agentguard.py sign-keyless <attestation-id> your-email@example.com
```
This opens a browser for an OIDC login (GitHub/Google/Microsoft). After
completing it, a `<id>.sigstore.json` bundle appears next to the
attestation. Then:
```powershell
python agentguard.py verify-keyless <attestation-id> your-email@example.com
```

## Sprint 5, Day 1: Git Integration

- [x] `git_integration/notes.py` - attaches attestation references to a
      specific commit via `git notes --ref=refs/notes/agentguard`
      (a dedicated ref, doesn't collide with git's default notes usage).
      Uses `git notes append`, not `add` - multiple AI-assisted edits
      before one commit is a real case, and append doesn't overwrite a
      prior entry. Each reference stored as one JSON line, so multiple
      entries stay individually parseable.
- [x] `agentguard.py auto-capture git` now automatically attaches a note
      to the exact commit it captured from - no separate manual step.
      Hook/OTel-sourced attestations deliberately do NOT get this (they
      aren't tied to one specific commit - may span several, or none
      committed yet), so this only fires for `source == "git"`, not
      silently applied everywhere.
- [x] New command: `agentguard.py git-note-show <commit>` - looks up and
      prints every attestation attached to a given commit.
- [x] **Tested against real commits in this repo**, not a mock repo:
      attach + retrieve, multiple attestations on the same commit
      (append behavior), a commit with genuinely no note (returns `[]`,
      not an error - the normal case for any commit not made through
      AgentGuard), and the full pipeline through `agentguard.py`'s real
      `auto_capture()` function, not just the notes module in isolation
      (`test_git_notes.py`).

## Next: Sprint 5, Day 2+ / Sprint 6

- Sprint 5 per the original plan also mentions in-toto layout
  integration more broadly (AI generation steps as first-class in-toto
  link types) - git notes is the commit-attachment half; a full in-toto
  layout/link-type mapping is still open.
- Key rotation / multi-key trust for the local-key signing path
  (currently: one keypair, generated once, used for everything - fine
  for a solo dev prototype, not a real multi-contributor deployment).
- Remaining honest gap from Sprint 3: confirming Claude Code's tool-call
  output pairing against a real live session - the one standing
  "unconfirmed" flag left from Day 2/3, since Claude Code has never been
  live-tested in this project the way Copilot has (hooks, OTel, and now
  Sigstore keyless signing).
- `retrieved_context` in the attestation schema still uses a naming
  heuristic (Sprint 3 Day 3), not a confirmed semantic signal - worth
  revisiting if a real transcript ever exposes an explicit
  retrieval-vs-action field.
- Sprint 6 per the original plan: CI/CD Enforcement.

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


