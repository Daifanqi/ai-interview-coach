"""
Puts the project root on sys.path so `import backend...` / `import
models...` resolve regardless of the working directory pytest is invoked
from -- mirrors the same sys.path setup scripts/test_conversation_live.py
does for the same reason.
"""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
