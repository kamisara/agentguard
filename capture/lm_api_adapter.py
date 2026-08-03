"""
LM API adapter - Tier 1, highest priority.

FAKE FOR NOW. This does not talk to any real model API yet. It exists so
CaptureManager's priority ordering can be tested end-to-end before the real
integration is built.

The real version depends on the outcome of the Day 4-5 feasibility spike:
does vscode.lm (or whichever agent's API) expose a genuine intercept/
subscribe hook, or only provider-registration? See README for why that
distinction matters. Until that's answered, is_available() always returns
False in any environment where FAKE_LM_API_AVAILABLE isn't explicitly set -
this adapter should never silently pretend to be real.
"""

import os
from datetime import datetime, timezone

from .interfaces import BaseAdapter
from .types import CaptureEvent

# Explicit env-var gate. Prevents this fake from being "available" by
# accident in a real run - it only activates when a test deliberately
# turns it on.
_FAKE_AVAILABLE_ENV_VAR = "AGENTGUARD_FAKE_LM_API_AVAILABLE"


class LmApiAdapter(BaseAdapter):
    """FAKE implementation. Replace capture() with a real vscode.lm (or
    equivalent) integration once the Day 4-5 spike confirms feasibility.

    priority = 0: highest fidelity when real - captures the actual prompt
    and response, not an inference (unlike GitAdapter) or a scraped log
    (unlike DebugAdapter).
    """

    priority = 0

    def is_available(self) -> bool:
        return os.environ.get(_FAKE_AVAILABLE_ENV_VAR) == "1"

    def capture(self) -> CaptureEvent:
        # TODO(Day 4-5 spike): replace with real vscode.lm interception,
        # or pivot to Tier 2 (documented hook systems) if vscode.lm only
        # exposes provider-registration, not a genuine intercept point.
        return CaptureEvent(
            adapter="lm_api",
            timestamp=datetime.now(timezone.utc),
            prompt="[FAKE] Generate a login page component",
            response="[FAKE] <LoginForm /> component code here",
            model="fake-model-v1",
            session_id="fake-session-id",
            metadata={"fake": True, "source": "LmApiAdapter placeholder"},
        )
