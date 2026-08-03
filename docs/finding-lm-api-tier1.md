# Finding: Tier 1 (LM API interception) is not viable for closed agents. Tier 2 (documented hooks) is the real primary path.

**Date:** Sprint 2B, Day 4
**Question tested:** Can AgentGuard capture Copilot's real chat traffic by hooking `vscode.lm`?

## Answer: No.

`vscode.lm`'s public surface has exactly three mechanisms, none of which observe another extension's traffic:

1. **`selectChatModels()` + `sendRequest()`** — lets your own extension *call* a model. Only sees requests your own code makes.
2. **`registerLanguageModelChatProvider()`** — lets your extension *become* a provider (this is what `ryonakae/vscode-lm-proxy` and BYOK integrations use). Only sees traffic when a caller explicitly selects your vendor — not Copilot's real internal traffic.
3. **Chat Participant API** — lets you implement your own `@agentguard` participant. Only sees prompts addressed to *your* participant.

Copilot's actual chat session runs entirely inside the private `vscode-copilot-chat` extension. No public event exposes it.

## Consequence for the architecture

Tier 1, as scoped in the original proposal ("intercept Copilot's internal generation events via VS Code extension"), does not exist as a buildable mechanism. It gets narrowed to: *captures traffic your own extension or chat participant explicitly initiates* — a real but smaller claim.

**Tier 2 (documented agent hook systems) becomes the actual primary path for real-time capture**, not a fallback below Tier 1. Claude Code's hook system is real, documented, and genuinely observes session traffic:

- Hooks are shell commands registered in `.claude/settings.json`, invoked by Claude Code itself at fixed lifecycle points (`UserPromptSubmit`, `Stop`, `PreToolUse`, `PostToolUse`, and ~25 others).
- Every hook receives JSON on stdin with `session_id`, `transcript_path`, `cwd`, `hook_event_name`.
- `UserPromptSubmit` carries the actual prompt text directly.
- `transcript_path` points to a JSONL file — the full session transcript — readable at any point, including after a `Stop` event.

This is not an outbound proxy or a provider registration — it's Claude Code *calling out to us* at defined points, which is exactly the observation model Tier 2 was designed around.

## Action

Build `ClaudeCodeHookAdapter` as the first real (non-git) capture adapter, `priority=5` — above `DebugAdapter` (still fake, scraping is unexplored) and well above `GitAdapter` (100), but not `0`, since `LmApiAdapter`'s narrowed scope (capturing your own extension/participant traffic) may still have a legitimate, if smaller, place in the priority chain later.

**Section 4.2 impact:** the tier ordering needs updating to reflect Tier 2 as primary for closed agents. Draft this once the hook adapter is validated against realistic hook payloads.

docs/finding-lm-api-tier1.md (or a new short note) that ClaudeCodeHookAdapter is validated against realistic simulated payloads but not yet against a live session, due to API cost — this is an honest, defensible statement for a proposal, not a weakness you need to hide. Move on to folding the adapters into agentguard.py's real CLI, and come back to the live test later if/when you have Console credits for other reasons (e.g. once you're doing real development work that needs Claude Code anyway).