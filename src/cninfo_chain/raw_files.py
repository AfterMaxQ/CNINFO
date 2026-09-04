from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cninfo_chain.errors import SecurityBoundaryError


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\.json$")
_SENSITIVE_KEYS = {"cookie", "authorization", "token", "sign", "password"}


def assert_no_sensitive_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).casefold() in _SENSITIVE_KEYS:
                raise SecurityBoundaryError(
                    f"raw response contains sensitive key: {str(key).casefold()}"
                )
            assert_no_sensitive_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            assert_no_sensitive_keys(child)


class RawRunWriter:
    def __init__(self, root: Path, run_id: str) -> None:
        if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
            raise ValueError("run_id contains unsafe path characters")
        self.directory = root / run_id

    def write_json(self, filename: str, payload: Any) -> Path:
        if not _SAFE_NAME.fullmatch(filename):
            raise ValueError("raw filename must be a safe JSON basename")
        assert_no_sensitive_keys(payload)
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / filename
        temporary = path.with_name(path.name + ".tmp")
        try:
            with temporary.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
        return path

    def write_manifest(
        self,
        *,
        run_id: str,
        theme_count: int,
        completed_nodes: int,
        failed_nodes: int,
        status: str,
    ) -> Path:
        return self.write_json(
            "capture_manifest.json",
            {
                "run_id": run_id,
                "captured_at": datetime.now(UTC).isoformat(),
                "theme_count": theme_count,
                "completed_nodes": completed_nodes,
                "failed_nodes": failed_nodes,
                "status": status,
            },
        )
