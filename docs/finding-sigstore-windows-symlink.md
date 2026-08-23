# Finding: Sigstore keyless signing works — the real blocker was a Windows-specific TUF library bug, not network/Fulcio access

**Date:** 2026-08-18
**Question tested:** Does Sigstore keyless signing (Fulcio + Rekor + OIDC) actually work end-to-end for a real developer?

## Answer: Yes — confirmed live. Real OIDC login, real Fulcio certificate, real Rekor entry, real verification.

## What was initially suspected (wrongly)

In this project's own development sandbox, `ClientTrustConfig.production()`
failed with `TUFError: Failed to refresh TUF metadata`. A direct connection
attempt to Fulcio separately returned HTTP 403. Both were reasonably
attributed to network policy blocking Sigstore's infrastructure — a
plausible and honestly-documented limitation at the time
(`signing/sigstore_signer.py`'s original docstring).

## What actually happened on a real machine (home network, no VPN/firewall)

The *identical* `TUFError` occurred — but the real cause, found by getting
the full traceback instead of just the wrapped exception, was:

```
OSError: [WinError 1314] A required privilege is not held by the client:
'root_history\15.root.json' -> '...\tuf\...\root.json'
```

This is Windows blocking `os.symlink()`. The `tuf` library (a dependency
of `sigstore`, used for trust-root metadata management) tries to create a
symlink in its local cache directory. Windows requires either Developer
Mode enabled or Administrator privileges to create symlinks — a standard
account without either gets exactly this error. **Nothing to do with
network reachability at all** — the sandbox's separate confirmed network
block (Fulcio returning 403) was a real, independent finding, but not
what actually blocked a normal developer on a normal machine.

## Fix

Enable Windows Developer Mode (Settings → Privacy & Security → For
Developers → Developer Mode), restart the terminal. No admin rights
needed after that. (Running as Administrator for the one command also
works, if Developer Mode isn't available.)

## Confirmed working after the fix

```
python agentguard.py sign-keyless <id> <email>
  -> Opening browser for Sigstore OIDC login...
  -> ✔ Keyless-signed -> .agentguard\attestations\<id>.sigstore.json

python agentguard.py verify-keyless <id> <email>
  -> ✔ VALID: <id>.json
  -> signature and identity verified
```

Real browser-based OIDC login completed, a real short-lived Fulcio
certificate was issued bound to the developer's real identity, the
signature was logged to Rekor's public transparency log, and verification
correctly checked both signature validity and identity match.

## Consequence for the project

Sprint 4 is now **fully confirmed complete**, not just "built but
unverified" — both signing methods (self-hosted Ed25519, Sigstore
keyless) have been proven end-to-end against real infrastructure, not
just unit-tested against synthetic data. This is also a good concrete
example for the methodology section: a suspected root cause
(network/infrastructure block) was corrected once real evidence
(the actual OSError, not just the wrapped TUFError) was obtained — same
"get the real error, don't stop at the first plausible explanation"
discipline that caught the Copilot transcript-format and OTLP endpoint
bugs earlier in this project.

**Worth noting as a real deployment consideration**, not just a one-off
quirk: any Windows-based contributor without Developer Mode enabled will
hit this exact error the first time they try keyless signing. Worth a
line in setup documentation for anyone else using this tool on Windows.
