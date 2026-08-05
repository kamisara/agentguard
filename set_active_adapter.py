"""
Set (or clear) which adapter is allowed to write pending captures.

Usage:
    python set_active_adapter.py copilot_hook
    python set_active_adapter.py claude_code_hook
    python set_active_adapter.py clear
    python set_active_adapter.py show
"""

import sys
from pathlib import Path

from capture.active_adapter import get_active_adapter, set_active_adapter

VALID_TAGS = {"copilot_hook", "claude_code_hook"}


def main() -> None:
    valid_args = VALID_TAGS | {"clear", "show"}
    if len(sys.argv) != 2 or sys.argv[1] not in valid_args:
        print(f"Usage: python set_active_adapter.py <{'|'.join(sorted(valid_args))}>")
        sys.exit(1)

    arg = sys.argv[1]
    cwd = str(Path.cwd())

    if arg == "show":
        current = get_active_adapter(cwd)
        print(f"Active adapter: {current if current else '(none - both fire)'}")
    elif arg == "clear":
        set_active_adapter(cwd, None)
        print("Cleared - all hook handlers will fire (no restriction).")
    else:
        set_active_adapter(cwd, arg)
        print(f"Active adapter set to '{arg}' - other hook handlers will now no-op.")


if __name__ == "__main__":
    main()
