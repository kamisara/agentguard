"""
Debug adapter - Tier 4, opportunistic enrichment.

FAKE FOR NOW. The real version scrapes chat/debug view logs (e.g. VS Code's
internal chatdebugview output) to recover prompt/response pairs when no
documented hook exists. That parsing logic isn't built yet - this fake
exists purely to validate CaptureManager's priority ordering.

Same env-var gate pattern as LmApiAdapter: never silently "available"
unless a test explicitly turns it on.
"""

import os
from datetime import datetime, timezone

from .interfaces import BaseAdapter
from .types import CaptureEvent

_FAKE_AVAILABLE_ENV_VAR = "AGENTGUARD_FAKE_DEBUG_AVAILABLE"


class DebugAdapter(BaseAdapter):
    """FAKE implementation. Replace capture() with real chat/debug-view log
    parsing once that format has been reverse-engineered.

    priority = 10: below LM API (0) since this is scraped/opportunistic
    rather than a direct hook, but above Git (100) since it still captures
    an explicit prompt rather than inferring intent after the fact.
    """

    priority = 10

    def is_available(self) -> bool:
        return os.environ.get(_FAKE_AVAILABLE_ENV_VAR) == "1"

    def capture(self) -> CaptureEvent:
        # TODO: replace with real chatdebugview log parsing.
        return CaptureEvent(
            adapter="debug",
            timestamp=datetime.now(timezone.utc),
            prompt="[FAKE] scraped prompt from debug view",
            response="[FAKE] scraped response from debug view",
            metadata={"fake": True, "source": "DebugAdapter placeholder"},
        )
