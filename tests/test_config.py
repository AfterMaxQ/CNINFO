from __future__ import annotations

import json
from pathlib import Path

import pytest


def test_settings_requires_mysql_identity() -> None:
    from cninfo_chain.config import Settings

    with pytest.raises(ValueError) as exc_info:
        Settings.from_env({})

    message = str(exc_info.value)
    assert "CNINFO_MYSQL_HOST" in message
    assert "CNINFO_MYSQL_USER" in message
    assert "CNINFO_MYSQL_PASSWORD" in message
    assert "CNINFO_MYSQL_DATABASE" in message


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
