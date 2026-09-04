from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

import pytest


@pytest.fixture
def raw_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data" / "raw"


@pytest.fixture
def load_json() -> Callable[[Path], dict[str, Any]]:
    def _load(path: Path) -> dict[str, Any]:
        return json.loads(path.read_text(encoding="utf-8"))

    return _load
