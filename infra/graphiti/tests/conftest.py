"""
Pytest configuration: put `infra/graphiti/` on sys.path so tests can import
the sidecar package regardless of which directory pytest is invoked from.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
