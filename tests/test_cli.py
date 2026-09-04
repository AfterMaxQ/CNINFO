from __future__ import annotations

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


def test_export_now_never_connects_to_browser(monkeypatch, tmp_path):
    from cninfo_chain import __main__ as cli

    calls = []

    class Store:
        def __init__(self, settings):
            calls.append("store")

        def migrate(self):
            calls.append("migrate")

    class Exporter:
        def __init__(self, store, target):
            calls.append(("exporter", Path(target)))

        def export(self, run_id=None):
            calls.append(("export", run_id))
            return tmp_path / "result.xlsx"

    monkeypatch.setattr(cli.Settings, "from_env", lambda: _settings(tmp_path))
    monkeypatch.setattr(cli, "MySQLStore", Store)
    monkeypatch.setattr(cli, "XlsxExporter", Exporter)
    monkeypatch.setattr(
        cli, "connect_browser", lambda *_: (_ for _ in ()).throw(AssertionError("browser used"))
    )

    assert cli.main(["--export-now"]) == 0
    assert calls == [
        "store",
        "migrate",
        ("exporter", tmp_path / "result.xlsx"),
        ("export", None),
    ]


def test_missing_configuration_returns_startup_exit_code(monkeypatch, capsys):
    from cninfo_chain import __main__ as cli

    monkeypatch.setattr(
        cli.Settings,
        "from_env",
        lambda: (_ for _ in ()).throw(ValueError("missing CNINFO_MYSQL_PASSWORD")),
    )
    assert cli.main(["--export-now"]) == 4
    assert "CNINFO_MYSQL_PASSWORD" in capsys.readouterr().err

