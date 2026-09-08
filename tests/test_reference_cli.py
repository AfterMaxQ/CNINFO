from __future__ import annotations

import json
from pathlib import Path

from cninfo_chain.config import Settings


def _settings(tmp_path):
    return Settings(
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="collector",
        mysql_password="secret",
        mysql_database="cninfo",
        cdp_url="http://127.0.0.1:9222",
        raw_dir=tmp_path / "runs",
        export_path=tmp_path / "result.xlsx",
    )


class FakeStore:
    def __init__(self, settings):
        self.migrated = False
        self.rows = []

    def migrate(self):
        self.migrated = True

    def a_share_security_count(self):
        return len(self.rows)

    def replace_a_share_security(self, rows):
        self.rows = list(rows)
        return len(self.rows)


def test_reference_init_prints_preview_and_writes_after_confirmation(
    monkeypatch, tmp_path, capsys
):
    from cninfo_chain import __main__ as cli

    store = FakeStore(_settings(tmp_path))
    monkeypatch.setattr(cli.Settings, "from_env", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "MySQLStore", lambda settings: store)
    monkeypatch.setattr(
        cli,
        "load_akshare_rows",
        lambda: [{"代码": "sh600519", "名称": "贵州茅台"}],
    )
    monkeypatch.setattr("builtins.input", lambda _: "CONFIRM")

    assert cli.main(["reference", "init"]) == 0
    assert store.migrated is True
    assert len(store.rows) == 1
    output = capsys.readouterr()
    assert "沪=1" in output.err
    assert json.loads(output.out)["count"] == 1


def test_reference_init_does_not_write_without_confirmation(monkeypatch, tmp_path, capsys):
    from cninfo_chain import __main__ as cli

    store = FakeStore(_settings(tmp_path))
    monkeypatch.setattr(cli.Settings, "from_env", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "MySQLStore", lambda settings: store)
    monkeypatch.setattr(
        cli,
        "load_akshare_rows",
        lambda: [{"代码": "sh600519", "名称": "贵州茅台"}],
    )
    monkeypatch.setattr("builtins.input", lambda _: "CANCEL")

    assert cli.main(["reference", "init"]) == 2
    assert store.rows == []
    assert "未写入" in capsys.readouterr().err


def test_reference_init_refuses_to_overwrite_existing_rows(monkeypatch, tmp_path, capsys):
    from cninfo_chain import __main__ as cli

    store = FakeStore(_settings(tmp_path))
    store.rows = [{"full_code": "600519.SH"}]
    monkeypatch.setattr(cli.Settings, "from_env", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "MySQLStore", lambda settings: store)

    assert cli.main(["reference", "init"]) == 3
    assert "reference refresh" in capsys.readouterr().err
