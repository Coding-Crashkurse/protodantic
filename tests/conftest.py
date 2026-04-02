"""Pytest configuration — adds the tests directory to sys.path so that
the a2a_pb2 fixture module is importable directly by test files."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
