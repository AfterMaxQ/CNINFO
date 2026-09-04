from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_REQUIRED_MYSQL_KEYS = (
    "CNINFO_MYSQL_HOST",
    "CNINFO_MYSQL_USER",
    "CNINFO_MYSQL_PASSWORD",
    "CNINFO_MYSQL_DATABASE",
)
_SENSITIVE_KEYS = {"cookie", "authorization", "token", "sign", "password"}


@dataclass(frozen=True, slots=True, repr=False)
class Settings:
    mysql_host: str
    mysql_port: int
    mysql_user: str
    mysql_password: str
    mysql_database: str
    cdp_url: str
    raw_dir: Path
    export_path: Path
    page_size: int = 15

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        values = os.environ if env is None else env
        missing = [key for key in _REQUIRED_MYSQL_KEYS if not values.get(key)]
        if missing:
            raise ValueError("missing environment variables: " + ", ".join(missing))
        try:
            mysql_port = int(values.get("CNINFO_MYSQL_PORT", "3306"))
            page_size = int(values.get("CNINFO_PAGE_SIZE", "15"))
        except ValueError as error:
            raise ValueError("CNINFO_MYSQL_PORT and CNINFO_PAGE_SIZE must be integers") from error
        if not 1 <= mysql_port <= 65535:
            raise ValueError("CNINFO_MYSQL_PORT must be between 1 and 65535")
        if page_size <= 0:
            raise ValueError("CNINFO_PAGE_SIZE must be positive")
        return cls(
            mysql_host=values["CNINFO_MYSQL_HOST"],
            mysql_port=mysql_port,
            mysql_user=values["CNINFO_MYSQL_USER"],
            mysql_password=values["CNINFO_MYSQL_PASSWORD"],
            mysql_database=values["CNINFO_MYSQL_DATABASE"],
            cdp_url=values.get("CNINFO_CDP_URL", "http://127.0.0.1:9222"),
            raw_dir=Path(values.get("CNINFO_RAW_DIR", "data/runs")),
            export_path=Path(values.get("CNINFO_EXPORT_PATH", "export/result.xlsx")),
            page_size=page_size,
        )

    def safe_summary(self) -> dict[str, Any]:
        return {
            "mysql_host": self.mysql_host,
            "mysql_port": self.mysql_port,
            "mysql_user": self.mysql_user,
            "mysql_database": self.mysql_database,
            "cdp_url": self.cdp_url,
            "raw_dir": str(self.raw_dir),
            "export_path": str(self.export_path),
            "page_size": self.page_size,
        }

    def __repr__(self) -> str:
        return f"Settings({self.safe_summary()!r})"


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: "[REDACTED]" if str(key).casefold() in _SENSITIVE_KEYS else redact_sensitive(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive(item) for item in value)
    return value
