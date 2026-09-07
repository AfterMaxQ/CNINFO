from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_settings_use_builtin_defaults_without_config_file(tmp_path: Path) -> None:
    from cninfo_chain.config import Settings

    settings = Settings.from_env(
        {"CNINFO_CONFIG_FILE": str(tmp_path / "missing-config.yaml")}
    )

    assert settings.mysql_host == "127.0.0.1"
    assert settings.mysql_port == 3306
    assert settings.mysql_user == "root"
    assert settings.mysql_password == "12345"
    assert settings.mysql_database == "cninfo_chain"


def test_settings_load_yaml_and_environment_overrides(tmp_path: Path) -> None:
    from cninfo_chain.config import Settings

    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
mysql:
  host: db.internal
  port: 3307
  user: yaml_user
  password: yaml_password
  database: yaml_db
chrome:
  cdp_url: http://127.0.0.1:9222
paths:
  raw_dir: yaml-runs
  export_path: yaml-result.xlsx
""".strip(),
        encoding="utf-8",
    )

    settings = Settings.from_env(
        {
            "CNINFO_CONFIG_FILE": str(config_path),
            "CNINFO_MYSQL_USER": "env_user",
            "CNINFO_PAGE_SIZE": "100",
        }
    )

    assert settings.mysql_host == "db.internal"
    assert settings.mysql_port == 3307
    assert settings.mysql_user == "env_user"
    assert settings.mysql_password == "yaml_password"
    assert settings.mysql_database == "yaml_db"
    assert settings.raw_dir == Path("yaml-runs")
    assert settings.export_path == Path("yaml-result.xlsx")
    assert settings.page_size == 15


def test_settings_reject_invalid_yaml_root(tmp_path: Path) -> None:
    from cninfo_chain.config import Settings

    config_path = tmp_path / "config.yaml"
    config_path.write_text("- not-a-mapping\n", encoding="utf-8")

    with pytest.raises(ValueError, match="config YAML root must be a mapping"):
        Settings.from_env({"CNINFO_CONFIG_FILE": str(config_path)})


def test_settings_defaults_and_repr_hide_password(tmp_path: Path) -> None:
    from cninfo_chain.config import Settings

    env = {
        "CNINFO_MYSQL_HOST": "127.0.0.1",
        "CNINFO_MYSQL_USER": "collector",
        "CNINFO_MYSQL_PASSWORD": "top-secret",
        "CNINFO_MYSQL_DATABASE": "cninfo_chain",
        "CNINFO_RAW_DIR": str(tmp_path / "runs"),
        "CNINFO_EXPORT_PATH": str(tmp_path / "result.xlsx"),
    }

    settings = Settings.from_env(env)

    assert settings.mysql_port == 3306
    assert settings.cdp_url == "http://127.0.0.1:9222"
    assert settings.page_size == 15
    assert "top-secret" not in repr(settings)
    assert "top-secret" not in json.dumps(settings.safe_summary(), ensure_ascii=False)


def test_redact_sensitive_recurses_without_changing_business_fields() -> None:
    from cninfo_chain.config import redact_sensitive

    value = {
        "node_id": "A02n019",
        "nested": {"token": "secret", "count": 15},
        "items": [{"Authorization": "bearer secret"}, "plain"],
    }

    assert redact_sensitive(value) == {
        "node_id": "A02n019",
        "nested": {"token": "[REDACTED]", "count": 15},
        "items": [{"Authorization": "[REDACTED]"}, "plain"],
    }
