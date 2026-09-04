from __future__ import annotations

import pytest

from cninfo_chain.config import Settings
from cninfo_chain.models import ChainNode
from cninfo_chain.storage import EXPORT_QUERY, MySQLStore, aggregate_listing_status


class FakeConnection:
    def __init__(self) -> None:
        self.begun = 0
        self.committed = 0
        self.rolled_back = 0
        self.closed = 0

    def begin(self) -> None:
        self.begun += 1

    def commit(self) -> None:
        self.committed += 1

    def rollback(self) -> None:
        self.rolled_back += 1

    def close(self) -> None:
        self.closed += 1


@pytest.fixture
def settings(tmp_path):
    return Settings(
        mysql_host="127.0.0.1",
        mysql_port=3306,
        mysql_user="collector",
        mysql_password="secret",
        mysql_database="cninfo_test",
        cdp_url="http://127.0.0.1:9222",
        raw_dir=tmp_path / "raw",
        export_path=tmp_path / "result.xlsx",
    )


def test_transaction_commits_and_closes(monkeypatch, settings):
    connection = FakeConnection()
    monkeypatch.setattr("cninfo_chain.storage.pymysql.connect", lambda **_: connection)

    store = MySQLStore(settings)
    with store.transaction() as actual:
        assert actual is connection

    assert (connection.begun, connection.committed, connection.rolled_back) == (1, 1, 0)
    assert connection.closed == 1


def test_transaction_rolls_back_and_never_leaks_password(monkeypatch, settings):
    connection = FakeConnection()
    captured = {}

    def connect(**kwargs):
        captured.update(kwargs)
        return connection

    monkeypatch.setattr("cninfo_chain.storage.pymysql.connect", connect)
    store = MySQLStore(settings)

    with pytest.raises(RuntimeError, match="boom"):
        with store.transaction():
            raise RuntimeError("boom")

    assert connection.rolled_back == 1
    assert connection.committed == 0
    assert connection.closed == 1
    assert captured["charset"] == "utf8mb4"
    assert "secret" not in repr(store)


@pytest.mark.parametrize(
    ("signals", "expected"),
    [([], 9), ([0], 0), ([1], 1), ([0, 1], 2), ([2], 2), ([9], 9)],
)
def test_listing_status_aggregation(signals, expected):
    assert aggregate_listing_status(signals) == expected


def test_node_commit_uses_one_rollback_boundary(monkeypatch, settings):
    connection = FakeConnection()
    monkeypatch.setattr("cninfo_chain.storage.pymysql.connect", lambda **_: connection)
    store = MySQLStore(settings)
    node = ChainNode(
        chain_id="lsx019",
        node_id="A02n019",
        parent_node_id=None,
        node_name="生物乙醇",
        node_definition=None,
        business_zone="中游",
        sort_no=1,
        path=("生物乙醇",),
        industry_code="A02n080",
        industry_name="生物乙醇",
        source_url="https://pis.cninfo.com.cn/ics/index.html#/industryChain/test",
    )

    def fail_after_entering_transaction(*_):
        raise RuntimeError("database write failed")

    monkeypatch.setattr(store, "_commit_node_in_transaction", fail_after_entering_transaction)
    with pytest.raises(RuntimeError, match="database write failed"):
        store.commit_node("run-1", 7, node, [])

    assert (connection.committed, connection.rolled_back, connection.closed) == (0, 1, 1)


def test_export_query_keeps_empty_nodes_and_uses_all_four_business_tables():
    assert "FROM industry_chain AS c" in EXPORT_QUERY
    assert "JOIN industry_chain_node AS n" in EXPORT_QUERY
    assert "LEFT JOIN industry_chain_company AS r" in EXPORT_QUERY
    assert "LEFT JOIN company AS co" in EXPORT_QUERY
    assert "n.data_status IN ('complete', 'no_industry_code')" in EXPORT_QUERY


def test_information_schema_table_name_is_case_insensitive(settings):
    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, *_):
            pass

        def fetchall(self):
            return [{"TABLE_NAME": "crawl_run"}, {"TABLE_NAME": "company"}]

    class Connection:
        def cursor(self):
            return Cursor()

    assert MySQLStore(settings)._existing_target_tables(Connection()) == {
        "crawl_run",
        "company",
    }
