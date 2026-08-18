#!/usr/bin/env python3
"""
AgentGuard - Sprint 4: Cryptographic Signing & Verification

Two signing methods, per the proposal's "Sigstore/Cosign, with support for
self-hosted key infrastructure" line:
  - Local Ed25519 keypair (self-hosted) - automatic, on every
    auto-capture/otel-listen. Proves "whoever holds this key signed this".
  - Sigstore keyless (identity-bound, publicly logged to Rekor) - opt-in,
    since it needs an interactive browser OIDC login. Proves a specific
    real identity signed this, and it's publicly auditable.

Usage:
    python agentguard.py capture                 # Sprint 1: manual entry (still works)
    python agentguard.py auto-capture <source>    # Sprint 3+4: automatic capture, signed (local key)
    python agentguard.py otel-listen [seconds]    # Sprint 3+4: listen for real OTel spans, signed (local key)
    python agentguard.py list                     # list all recorded attestations (both schemas)
    python agentguard.py show <id>                # print one attestation in full
    python agentguard.py verify <id>               # verify local-key signature
    python agentguard.py verify-all                # verify every local-key-signed attestation
    python agentguard.py sign-keyless <id> <identity> # Sigstore keyless sign (opens browser)
    python agentguard.py verify-keyless <id> <identity> # Sigstore keyless verify
"""

import json
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ATTESTATION_DIR = Path(".agentguard") / "attestations"


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _ensure_dir():
    ATTESTATION_DIR.mkdir(parents=True, exist_ok=True)


def _prompt(label, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"{label}{suffix}: ").strip()
    return val or default or ""


def capture():
    """Interactively simulate one AI generation event and record it."""
    print("=== AgentGuard capture (Sprint 1: simulated interaction) ===\n")

    developer_intent = _prompt("Developer intent (what were you trying to do)")
    prompt_text = _prompt("Prompt sent to the AI")
    model = _prompt("AI model / agent name", default="simulated-model")
    provider = _prompt("Provider", default="simulated-provider")
    ai_output_summary = _prompt("Short summary of what the AI returned")
    reviewed = _prompt("Did a human review the output before commit? (y/n)", default="n")

    attestation_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())

    record = {
        "schema_version": "sprint1-v0",
        "attestation_id": attestation_id,
        "session_id": session_id,
        "timestamp": _now_iso(),
        "developer_intent": developer_intent,
        "prompt": prompt_text,
        "agent_identity": {
            "model": model,
            "provider": provider,
        },
        "ai_output_summary": ai_output_summary,
        "human_review_status": {
            "reviewed": reviewed.lower().startswith("y"),
            "reviewer": None,
        },
    }

    _ensure_dir()
    out_path = ATTESTATION_DIR / f"{attestation_id}.json"
    with open(out_path, "w") as f:
        json.dump(record, f, indent=2)

    print(f"\n✔ Attestation captured -> {out_path}")
    return record


def list_attestations():
    _ensure_dir()
    files = sorted(ATTESTATION_DIR.glob("*.json"))
    if not files:
        print("No attestations recorded yet. Run: python agentguard.py capture")
        return
    for f in files:
        try:
            with open(f) as fh:
                record = json.load(fh)
        except (json.JSONDecodeError, OSError) as e:
            print(f"⚠ {f.name}: unreadable ({e}), skipping")
            continue

        attestation_id = record.get("attestation_id", f.stem)
        timestamp = record.get("timestamp", "unknown time")
        intent = record.get("developer_intent", "(no developer_intent field)")
        print(f"{attestation_id}  {timestamp}  intent=\"{intent[:50]}\"")


def show(attestation_id):
    _ensure_dir()
    matches = list(ATTESTATION_DIR.glob(f"{attestation_id}*.json"))
    if not matches:
        print(f"No attestation found matching id: {attestation_id}")
        return
    with open(matches[0]) as f:
        print(json.dumps(json.load(f), indent=2))


def auto_capture(source: str):
    """Sprint 3: pull a real event from an adapter, normalize, generate
    and store an attestation automatically. Replaces manual typing for
    the sources that support pull-based capture (git, the two hook
    adapters). OTel is push-based - see otel_listen() instead.

    Sprint 4: also signs the attestation by default - a real capture
    pipeline should produce tamper-evident output without a separate
    manual step to remember."""
    from capture.git_adapter import GitAdapter
    from capture.claude_code_hook_adapter import ClaudeCodeHookAdapter
    from capture.copilot_hook_adapter import CopilotHookAdapter
    from capture.normalizer import normalize
    from attestation.generator import generate_attestation
    from attestation.store import write_and_sign_attestation

    adapters = {
        "git": GitAdapter(),
        "claude_code_hook": ClaudeCodeHookAdapter(),
        "copilot_hook": CopilotHookAdapter(),
    }

    adapter = adapters.get(source)
    if adapter is None:
        print(f"Unknown source '{source}'. Valid: {sorted(adapters)}")
        return

    if not adapter.is_available():
        print(f"No capture available from '{source}' right now.")
        if source in ("claude_code_hook", "copilot_hook"):
            print("(Nothing pending in .agentguard/pending_captures/ for this adapter.)")
        return

    event = adapter.capture()
    normalized = normalize(event)
    attestation = generate_attestation(normalized)
    out_path, sig_path = write_and_sign_attestation(attestation)

    print(f"✔ Attestation generated automatically from '{source}' -> {out_path}")
    print(f"  signed -> {sig_path}")
    print(f"  intent_source: {attestation.intent_source}")
    print(f"  developer_intent: {attestation.developer_intent[:80]}")
    if attestation.tool_invocations:
        print(f"  tool_invocations: {len(attestation.tool_invocations)}")
    if attestation.retrieved_context:
        print(f"  retrieved_context: {len(attestation.retrieved_context)}")


def otel_listen(seconds: int = 60):
    """Sprint 3: OTel is push-based (subscribe, not pull), so this starts
    the real receiver, listens for the given duration, and automatically
    attests every GenAI span that arrives - no manual entry, and no
    polling loop needed since CaptureManager's callback fires per event.

    Sprint 4: also signs each attestation, same as auto_capture()."""
    from capture.otel_telemetry_source import OtelGenAiTelemetrySource
    from capture.normalizer import normalize
    from attestation.generator import generate_attestation
    from attestation.store import write_and_sign_attestation

    count = 0

    def on_event(event):
        nonlocal count
        normalized = normalize(event)
        attestation = generate_attestation(normalized)
        out_path, sig_path = write_and_sign_attestation(attestation)
        count += 1
        print(f"✔ [{count}] Attestation from otel_genai -> {out_path} (signed)")
        print(f"    developer_intent: {attestation.developer_intent[:80]}")

    source = OtelGenAiTelemetrySource()
    source.subscribe(on_event)
    print(f"Listening for real OTel GenAI spans at http://localhost:4318/v1/traces")
    print(f"({seconds}s - point your OTel-enabled agent's exporter here, then use it)")
    try:
        time.sleep(seconds)
    except KeyboardInterrupt:
        pass
    finally:
        source.stop()
    print(f"\nStopped. {count} attestation(s) generated and signed automatically this session.")


def verify(attestation_id: str):
    """Sprint 4: verify one attestation's signature. Reports WHY it
    failed if it did - missing sig file (never signed, e.g. anything from
    Sprint 1's manual `capture` or Sprint 3 before signing existed),
    tampered content, or wrong/missing key."""
    from signing.signer import verify_signature_file

    _ensure_dir()
    matches = list(ATTESTATION_DIR.glob(f"{attestation_id}*.json"))
    if not matches:
        print(f"No attestation found matching id: {attestation_id}")
        return

    result = verify_signature_file(matches[0])
    status = "✔ VALID" if result["valid"] else "✘ INVALID"
    print(f"{status}: {matches[0].name}")
    print(f"  {result['reason']}")
    if result.get("algorithm"):
        print(f"  algorithm: {result['algorithm']}")
        print(f"  public key: {result['public_key_path']}")


def verify_all():
    """Sprint 4: verify every attestation that has a .sig file.
    Attestations without one (unsigned - e.g. sprint1-v0 manual records,
    or anything written with write_attestation() instead of
    write_and_sign_attestation()) are reported separately, not silently
    skipped - a verification tool should account for everything it sees."""
    from signing.signer import verify_signature_file, sig_path_for

    _ensure_dir()
    files = sorted(ATTESTATION_DIR.glob("*.json"))
    if not files:
        print("No attestations recorded yet.")
        return

    valid_count = 0
    invalid_count = 0
    unsigned_count = 0

    for f in files:
        if not sig_path_for(f).exists():
            unsigned_count += 1
            print(f"— UNSIGNED: {f.name}")
            continue
        result = verify_signature_file(f)
        if result["valid"]:
            valid_count += 1
            print(f"✔ VALID:   {f.name}")
        else:
            invalid_count += 1
            print(f"✘ INVALID: {f.name}  ({result['reason']})")

    print(f"\n{valid_count} valid, {invalid_count} invalid, {unsigned_count} unsigned "
          f"(out of {len(files)} total)")


def sign_keyless(attestation_id: str, expected_identity: str):
    """Sprint 4, Day 2: Sigstore keyless signing. Opens a browser for
    OIDC login - this is NOT automatic like local-key signing, by design
    (see agentguard.py's module docstring for why).

    Wrapped to catch the specific failure mode CONFIRMED via direct
    testing during development: on a network that blocks Sigstore's
    infrastructure (this happened in the sandbox this was built in - a
    real, not hypothetical, scenario also plausible on restricted
    corporate networks), even constructing the trust config fails with a
    TUFError. Catching this here means the person running it gets a
    clear explanation, not a raw traceback."""
    from signing.sigstore_signer import sign_attestation_file_keyless

    _ensure_dir()
    matches = list(ATTESTATION_DIR.glob(f"{attestation_id}*.json"))
    if not matches:
        print(f"No attestation found matching id: {attestation_id}")
        return

    print("Opening browser for Sigstore OIDC login...")
    try:
        bundle_path = sign_attestation_file_keyless(matches[0])
    except Exception as e:
        print(f"✘ Keyless signing failed: {type(e).__name__}: {e}")
        print(
            "  If this says something about TUF metadata or a network "
            "error, Sigstore's infrastructure (fulcio.sigstore.dev, "
            "rekor.sigstore.dev, oauth2.sigstore.dev, tuf.sigstore.dev) "
            "is likely blocked on this network - confirmed to happen on "
            "some restricted/corporate networks, not just a bug."
        )
        return

    print(f"✔ Keyless-signed -> {bundle_path}")
    print(f"  Identity used for verification: {expected_identity}")


def verify_keyless(attestation_id: str, expected_identity: str):
    from signing.sigstore_signer import verify_attestation_file_keyless

    _ensure_dir()
    matches = list(ATTESTATION_DIR.glob(f"{attestation_id}*.json"))
    if not matches:
        print(f"No attestation found matching id: {attestation_id}")
        return

    try:
        result = verify_attestation_file_keyless(matches[0], expected_identity)
    except Exception as e:
        print(f"✘ Keyless verification failed: {type(e).__name__}: {e}")
        print("  (Same possible network cause as sign-keyless - see its output.)")
        return

    status = "✔ VALID" if result["valid"] else "✘ INVALID"
    print(f"{status}: {matches[0].name}")
    print(f"  {result['reason']}")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]
    if cmd == "capture":
        capture()
    elif cmd == "auto-capture" and len(sys.argv) >= 3:
        auto_capture(sys.argv[2])
    elif cmd == "otel-listen":
        seconds = int(sys.argv[2]) if len(sys.argv) >= 3 else 60
        otel_listen(seconds)
    elif cmd == "list":
        list_attestations()
    elif cmd == "show" and len(sys.argv) >= 3:
        show(sys.argv[2])
    elif cmd == "verify" and len(sys.argv) >= 3:
        verify(sys.argv[2])
    elif cmd == "verify-all":
        verify_all()
    elif cmd == "sign-keyless" and len(sys.argv) >= 4:
        sign_keyless(sys.argv[2], sys.argv[3])
    elif cmd == "verify-keyless" and len(sys.argv) >= 4:
        verify_keyless(sys.argv[2], sys.argv[3])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()