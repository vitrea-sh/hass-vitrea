"""Test setup: make the bundled vitrea_integration library importable.

The protocol library lives inside the custom component; adding that
directory to sys.path lets the connection layer be tested without a
Home Assistant installation.
"""

import sys
from pathlib import Path

sys.path.insert(
    0, str(Path(__file__).resolve().parents[1] / "custom_components" / "vitrea")
)
