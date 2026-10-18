"""Convenience launcher for running from a source checkout."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from astrbot_conversation_manager.app import main

if __name__ == "__main__":
    main()
