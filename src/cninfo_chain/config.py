from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_SENSITIVE_KEYS = {"cookie", "authorization", "token", "sign", "password"}
_CNINFO_PAGE_SIZE = 15
_DEFAULT_CONFIG: dict[str, dict[str, Any]] = {
    "mysql": {
        "host": "127.0.0.1",
        "port": 3306,
        "user": "root",
        "password": "12345",
        "database": "cninfo_chain",
    },
    "chrome": {"cdp_url": "http://127.0.0.1:9222"},
    "paths": {"raw_dir": "data/runs", "export_path": "export/result.xlsx"},
}
_ENV_BINDINGS = {
    "CNINFO_MYSQL_HOST": ("mysql", "host"),
    "CNINFO_MYSQL_PORT": ("mysql", "port"),
    "CNINFO_MYSQL_USER": ("mysql", "user"),
    "CNINFO_MYSQL_PASSWORD": ("mysql", "password"),
    "CNINFO_MYSQL_DATABASE": ("mysql", "database"),
    "CNINFO_CDP_URL": ("chrome", "cdp_url"),
    "CNINFO_RAW_DIR": ("paths", "raw_dir"),
    "CNINFO_EXPORT_PATH": ("paths", "export_path"),
}


def _load_yaml_config(path: Path) -> Mapping[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except OSError as error:
        raise ValueError(f"cannot read config file: {path}") from error
    except yaml.YAMLError as error:
        raise ValueError(f"invalid YAML config file: {path}") from error
    if payload is None:
        return {}
    if not isinstance(payload, Mapping):
        raise ValueError("config YAML root must be a mapping")
    return payload


def _merged_config(values: Mapping[str, str]) -> dict[str, dict[str, Any]]:
    config = {section: dict(items) for section, items in _DEFAULT_CONFIG.items()}
    config_name = values.get("CNINFO_CONFIG_FILE", "config.yaml") or "config.yaml"
    config_path = Path(config_name)
    if not config_path.is_absolute():
        config_path = Path.cwd() / config_path
    payload = _load_yaml_config(config_path)
    for section in config:
        section_payload = payload.get(section, {})
        if section_payload is None:
            continue
        if not isinstance(section_payload, Mapping):
            raise ValueError(f"config section must be a mapping: {section}")
        config[section].update(section_payload)
    for env_name, (section, key) in _ENV_BINDINGS.items():
        if env_name in values:
            config[section][key] = values[env_name]
    return config


def _required_text(value: Any, name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise ValueError(f"config value must not be empty: {name}")
    return text


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
        config = _merged_config(values)
        mysql = config["mysql"]
        chrome = config["chrome"]
        paths = config["paths"]
        try:
            mysql_port = int(mysql["port"])
        except (TypeError, ValueError) as error:
            raise ValueError("mysql.port must be an integer") from error
        if not 1 <= mysql_port <= 65535:
            raise ValueError("mysql.port must be between 1 and 65535")
        return cls(
            mysql_host=_required_text(mysql["host"], "mysql.host"),
            mysql_port=mysql_port,
            mysql_user=_required_text(mysql["user"], "mysql.user"),
            mysql_password=_required_text(mysql["password"], "mysql.password"),
            mysql_database=_required_text(mysql["database"], "mysql.database"),
            cdp_url=_required_text(chrome["cdp_url"], "chrome.cdp_url"),
            raw_dir=Path(_required_text(paths["raw_dir"], "paths.raw_dir")),
            export_path=Path(_required_text(paths["export_path"], "paths.export_path")),
            page_size=_CNINFO_PAGE_SIZE,
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
