"""Make the repo root importable so `pytest -q` works from inside eval/.

The harness is run as `python -m eval.runner` from the repository root, so its own imports are
`from eval...`. Without this, collecting the tests here would fail on `import eval.dataset`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
