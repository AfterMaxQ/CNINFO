from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib.resources import files
from typing import Any, Sequence

import pymysql

from cninfo_chain.config import Settings
from cninfo_chain.errors import IdentityConflict, NodeSetMismatch, SchemaChanged, SchemaConflict
from cninfo_chain.models import ChainNode, ChainSeed, MergedCompany


TABLE_NAMES = (
    "crawl_run",
    "industry_chain",
    "industry_chain_node",
    "company",
    "industry_chain_company",
    "crawl_node_task",
)
EXPECTED_COLUMN_COUNT = 45
TERMINAL_TASK_STATUSES = {"committed", "committed_empty"}
TASK_STATUSES = {
    "pending",
    "fetching",
    "validating",
    "committed",
    "committed_empty",
    "failed",
}
RUN_STATUSES = {"running", "paused", "paused_auth", "partial", "complete", "failed"}

EXPORT_QUERY = """
SELECT
    c.chain_name,
    c.sort_no AS chain_sort_no,
    n.node_name,
    n.business_zone,
    n.sort_no AS node_sort_no,
    n.path_json,
    n.source_url,
    r.sort_no AS company_sort_no,
    co.company_name,
    co.company_short_name,
    r.listing_status
FROM industry_chain AS c
JOIN industry_chain_node AS n
  ON n.industry_chain_id = c.id
LEFT JOIN industry_chain_company AS r
  ON r.industry_chain_node_id = n.id
LEFT JOIN company AS co
  ON co.id = r.company_id
WHERE c.enabled = 1
  AND n.data_status IN ('complete', 'no_industry_code')
ORDER BY c.sort_no, n.sort_no, r.sort_no
""".strip()


def _utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def aggregate_listing_status(signals: Sequence[int]) -> int:
    observed = set(signals) - {9}
    if 2 in observed or ({0, 1} <= observed):
        return 2
    if 1 in observed:
        return 1
    if 0 in observed:
        return 0
    return 9


class MySQLStore:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def __repr__(self) -> str:
        return f"MySQLStore(settings={self.settings!r})"

    def _connect(self):
        return pymysql.connect(
            host=self.settings.mysql_host,
            port=self.settings.mysql_port,
            user=self.settings.mysql_user,
            password=self.settings.mysql_password,
            database=self.settings.mysql_database,
            charset="utf8mb4",
            autocommit=False,
            cursorclass=pymysql.cursors.DictCursor,
        )

    @contextmanager
    def connection(self) -> Iterator[Any]:
        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    @contextmanager
    def transaction(self) -> Iterator[Any]:
        with self.connection() as connection:
            connection.begin()
            try:
                yield connection
            except BaseException:
                connection.rollback()
                raise
            else:
                connection.commit()

    def migrate(self) -> None:
        with self.connection() as connection:
            existing = self._existing_target_tables(connection)
            if existing and existing != set(TABLE_NAMES):
                raise SchemaConflict(
                    "target schema contains only part of the CNINFO tables: "
                    + ", ".join(sorted(existing))
                )
            if not existing:
                statements = self._migration_statements()
                try:
                    with connection.cursor() as cursor:
                        for statement in statements:
                            cursor.execute(statement)
                    connection.commit()
                except BaseException:
                    connection.rollback()
                    raise
        self.assert_schema_current()

    def create_run(self, run_id: str) -> None:
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO crawl_run "
                "(run_id, status, started_at, finished_at, export_path, last_error_message) "
                "VALUES (%s, 'running', %s, NULL, NULL, NULL)",
                (run_id, _utc_now()),
            )

    def set_run_status(
        self,
        run_id: str,
        status: str,
        *,
        export_path: str | None = None,
        error_message: str | None = None,
    ) -> None:
        if status not in RUN_STATUSES:
            raise ValueError(f"unknown run status: {status}")
        finished_at = None if status == "running" else _utc_now()
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE crawl_run SET status=%s, finished_at=%s, "
                "export_path=COALESCE(%s, export_path), last_error_message=%s "
                "WHERE run_id=%s",
                (status, finished_at, export_path, error_message, run_id),
            )

    def sync_catalog(
        self,
        run_id: str,
        chains: Sequence[ChainSeed],
        nodes: Sequence[ChainNode],
    ) -> dict[tuple[str, str], int]:
        now = _utc_now()
        chain_db_ids: dict[str, int] = {}
        node_db_ids: dict[tuple[str, str], int] = {}
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute("UPDATE industry_chain SET enabled=0, updated_at=%s", (now,))
            for chain in chains:
                cursor.execute(
                    "INSERT INTO industry_chain "
                    "(chain_id, chain_name, menu_name, sort_no, enabled, updated_at) "
                    "VALUES (%s, %s, %s, %s, 1, %s) "
                    "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id), chain_name=VALUES(chain_name), "
                    "menu_name=VALUES(menu_name), sort_no=VALUES(sort_no), enabled=1, updated_at=VALUES(updated_at)",
                    (chain.chain_id, chain.chain_name, chain.menu_name, chain.sort_no, now),
                )
                chain_db_ids[chain.chain_id] = int(cursor.lastrowid)

            for node in sorted(nodes, key=lambda item: (item.chain_id, item.sort_no)):
                chain_db_id = chain_db_ids.get(node.chain_id)
                if chain_db_id is None:
                    raise NodeSetMismatch(f"node references unknown chain: {node.chain_id}")
                parent_db_id = None
                if node.parent_node_id:
                    parent_db_id = node_db_ids.get((node.chain_id, node.parent_node_id))
                    if parent_db_id is None:
                        raise NodeSetMismatch(
                            f"parent node must be stored before child: {node.parent_node_id}"
                        )
                cursor.execute(
                    "INSERT INTO industry_chain_node "
                    "(industry_chain_id, node_id, parent_id, node_name, node_definition, business_zone, "
                    "sort_no, path_json, industry_code, industry_name, source_url, data_status, updated_at) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s) "
                    "ON DUPLICATE KEY UPDATE id=LAST_INSERT_ID(id), parent_id=VALUES(parent_id), "
                    "node_name=VALUES(node_name), node_definition=VALUES(node_definition), "
                    "business_zone=VALUES(business_zone), sort_no=VALUES(sort_no), "
                    "path_json=VALUES(path_json), source_url=VALUES(source_url), updated_at=VALUES(updated_at)",
                    (
                        chain_db_id,
                        node.node_id,
                        parent_db_id,
                        node.node_name,
                        node.node_definition,
                        node.business_zone,
                        node.sort_no,
                        json.dumps(node.path, ensure_ascii=False),
                        node.industry_code,
                        node.industry_name,
                        node.source_url,
                        now,
                    ),
                )
                node_db_id = int(cursor.lastrowid)
                node_db_ids[(node.chain_id, node.node_id)] = node_db_id
                cursor.execute(
                    "INSERT INTO crawl_node_task "
                    "(run_id, industry_chain_node_id, status, retry_count, error_message, updated_at) "
                    "VALUES (%s, %s, 'pending', 0, NULL, %s)",
                    (run_id, node_db_id, now),
                )
        return node_db_ids

    def set_task_status(
        self,
        run_id: str,
        node_db_id: int,
        status: str,
        *,
        error_message: str | None = None,
        increment_retry: bool = False,
    ) -> None:
        if status not in TASK_STATUSES:
            raise ValueError(f"unknown task status: {status}")
        retry_sql = "retry_count + 1" if increment_retry else "retry_count"
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE crawl_node_task SET status=%s, retry_count={retry_sql}, "
                "error_message=%s, updated_at=%s "
                "WHERE run_id=%s AND industry_chain_node_id=%s",
                (status, error_message, _utc_now(), run_id, node_db_id),
            )

    def pending_nodes(self, run_id: str) -> list[dict[str, Any]]:
        return [
            row
            for row in self.run_nodes(run_id)
            if row["status"] not in TERMINAL_TASK_STATUSES
        ]

    def run_nodes(self, run_id: str) -> list[dict[str, Any]]:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.industry_chain_node_id, t.status, t.retry_count, "
                "c.chain_id, c.chain_name, n.node_id, p.node_id AS parent_node_id, "
                "n.node_name, n.node_definition, n.business_zone, n.sort_no, n.path_json, "
                "n.industry_code, n.industry_name, n.source_url "
                "FROM crawl_node_task AS t "
                "JOIN industry_chain_node AS n ON n.id=t.industry_chain_node_id "
                "JOIN industry_chain AS c ON c.id=n.industry_chain_id "
                "LEFT JOIN industry_chain_node AS p ON p.id=n.parent_id "
                "WHERE t.run_id=%s "
                "ORDER BY c.sort_no, n.sort_no",
                (run_id,),
            )
            return list(cursor.fetchall())

    def disable_missing_nodes(self, chain_id: str, active_node_ids: Sequence[str]) -> None:
        if not active_node_ids:
            raise NodeSetMismatch(f"cannot disable nodes from an empty theme: {chain_id}")
        placeholders = ", ".join(["%s"] * len(active_node_ids))
        with self.transaction() as connection, connection.cursor() as cursor:
            cursor.execute(
                "UPDATE industry_chain_node AS n "
                "JOIN industry_chain AS c ON c.id=n.industry_chain_id "
                "SET n.data_status='disabled', n.updated_at=%s "
                "WHERE c.chain_id=%s AND n.node_id NOT IN (" + placeholders + ")",
                (_utc_now(), chain_id, *active_node_ids),
            )

    def run_summary(self, run_id: str) -> dict[str, int]:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT COUNT(*) AS total_nodes, "
                "SUM(status IN ('committed', 'committed_empty')) AS completed_nodes, "
                "SUM(status = 'failed') AS failed_nodes "
                "FROM crawl_node_task WHERE run_id=%s",
                (run_id,),
            )
            row = cursor.fetchone() or {}
        return {
            "total_nodes": int(row.get("total_nodes") or 0),
            "completed_nodes": int(row.get("completed_nodes") or 0),
            "failed_nodes": int(row.get("failed_nodes") or 0),
        }

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM crawl_run WHERE run_id=%s", (run_id,))
            row = cursor.fetchone()
        if row is None:
            return None
        return {**row, **self.run_summary(run_id)}

    def commit_node(
        self,
        run_id: str,
        node_db_id: int,
        node: ChainNode,
        companies: Sequence[MergedCompany],
    ) -> None:
        with self.transaction() as connection:
            self._commit_node_in_transaction(connection, run_id, node_db_id, node, companies)

    def _commit_node_in_transaction(
        self,
        connection: Any,
        run_id: str,
        node_db_id: int,
        node: ChainNode,
        companies: Sequence[MergedCompany],
    ) -> None:
        now = _utc_now()
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT company_id FROM industry_chain_company WHERE industry_chain_node_id=%s",
                (node_db_id,),
            )
            affected_company_ids = {int(row["company_id"]) for row in cursor.fetchall()}
            company_rows: list[tuple[int, MergedCompany]] = []
            for company in companies:
                company_id = self._upsert_company(cursor, company, now)
                affected_company_ids.add(company_id)
                company_rows.append((company_id, company))

            cursor.execute(
                "DELETE FROM industry_chain_company WHERE industry_chain_node_id=%s",
                (node_db_id,),
            )
            for company_id, company in company_rows:
                cursor.execute(
                    "INSERT INTO industry_chain_company "
                    "(industry_chain_node_id, company_id, listing_status, sort_no) "
                    "VALUES (%s, %s, %s, %s)",
                    (node_db_id, company_id, company.listing_status, company.source_order),
                )

            data_status = "complete" if node.industry_code else "no_industry_code"
            cursor.execute(
                "UPDATE industry_chain_node SET node_definition=%s, industry_code=%s, "
                "industry_name=%s, data_status=%s, updated_at=%s WHERE id=%s",
                (
                    node.node_definition,
                    node.industry_code,
                    node.industry_name,
                    data_status,
                    now,
                    node_db_id,
                ),
            )
            task_status = "committed" if companies else "committed_empty"
            cursor.execute(
                "UPDATE crawl_node_task SET status=%s, error_message=NULL, updated_at=%s "
                "WHERE run_id=%s AND industry_chain_node_id=%s",
                (task_status, now, run_id, node_db_id),
            )

            for company_id in affected_company_ids:
                cursor.execute(
                    "SELECT listing_status FROM industry_chain_company WHERE company_id=%s",
                    (company_id,),
                )
                status = aggregate_listing_status(
                    [int(row["listing_status"]) for row in cursor.fetchall()]
                )
                cursor.execute(
                    "UPDATE company SET listing_status=%s, updated_at=%s WHERE id=%s",
                    (status, now, company_id),
                )

    @staticmethod
    def _upsert_company(cursor: Any, company: MergedCompany, now: datetime) -> int:
        clauses: list[str] = []
        values: list[str] = []
        if company.cninfo_company_id:
            clauses.append("cninfo_company_id=%s")
            values.append(company.cninfo_company_id)
        if company.stock_code:
            clauses.append("stock_code=%s")
            values.append(company.stock_code)
        clauses.append("normalized_name=%s")
        values.append(company.normalized_name)
        cursor.execute(
            "SELECT id FROM company WHERE " + " OR ".join(clauses) + " FOR UPDATE",
            tuple(values),
        )
        matches = {int(row["id"]) for row in cursor.fetchall()}
        if len(matches) > 1:
            raise IdentityConflict(
                f"company identifiers match multiple records: {company.company_name}"
            )
        if matches:
            company_id = matches.pop()
            cursor.execute(
                "UPDATE company SET cninfo_company_id=COALESCE(cninfo_company_id, %s), "
                "stock_code=COALESCE(stock_code, %s), "
                "company_short_name=COALESCE(%s, company_short_name), updated_at=%s WHERE id=%s",
                (
                    company.cninfo_company_id,
                    company.stock_code,
                    company.company_short_name,
                    now,
                    company_id,
                ),
            )
            return company_id
        cursor.execute(
            "INSERT INTO company "
            "(cninfo_company_id, stock_code, company_name, company_short_name, normalized_name, "
            "listing_status, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                company.cninfo_company_id,
                company.stock_code,
                company.company_name,
                company.company_short_name,
                company.normalized_name,
                company.listing_status,
                now,
            ),
        )
        return int(cursor.lastrowid)

    def export_rows(self) -> list[dict[str, Any]]:
        with self.connection() as connection, connection.cursor() as cursor:
            cursor.execute(EXPORT_QUERY)
            return list(cursor.fetchall())

    def assert_schema_current(self) -> None:
        with self.connection() as connection:
            tables = self._existing_target_tables(connection)
            if tables != set(TABLE_NAMES):
                raise SchemaChanged("CNINFO schema must contain exactly the six required tables")
            placeholders = ", ".join(["%s"] * len(TABLE_NAMES))
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COUNT(*) AS total, "
                    "SUM(CASE WHEN column_comment = '' THEN 1 ELSE 0 END) AS missing_comments "
                    "FROM information_schema.columns "
                    "WHERE table_schema = %s AND table_name IN (" + placeholders + ")",
                    (self.settings.mysql_database, *TABLE_NAMES),
                )
                columns = cursor.fetchone()
                cursor.execute(
                    "SELECT COUNT(*) AS total, "
                    "SUM(CASE WHEN table_comment = '' THEN 1 ELSE 0 END) AS missing_comments "
                    "FROM information_schema.tables "
                    "WHERE table_schema = %s AND table_name IN (" + placeholders + ")",
                    (self.settings.mysql_database, *TABLE_NAMES),
                )
                tables_summary = cursor.fetchone()
        if columns["total"] != EXPECTED_COLUMN_COUNT or columns["missing_comments"]:
            raise SchemaChanged("CNINFO schema columns or Chinese comments do not match")
        if tables_summary["total"] != len(TABLE_NAMES) or tables_summary["missing_comments"]:
            raise SchemaChanged("CNINFO table comments do not match")

    def _existing_target_tables(self, connection: Any) -> set[str]:
        placeholders = ", ".join(["%s"] * len(TABLE_NAMES))
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = %s AND table_name IN (" + placeholders + ")",
                (self.settings.mysql_database, *TABLE_NAMES),
            )
            return {row["table_name"] for row in cursor.fetchall()}

    @staticmethod
    def _migration_statements() -> list[str]:
        sql = (
            files("cninfo_chain")
            .joinpath("migrations", "001_initial.sql")
            .read_text(encoding="utf-8")
        )
        return [statement.strip() for statement in sql.split(";") if statement.strip()]
