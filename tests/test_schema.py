from __future__ import annotations

import re
from importlib.resources import files


EXPECTED_COLUMNS = {
    "crawl_run": 6,
    "industry_chain": 7,
    "industry_chain_node": 14,
    "company": 8,
    "industry_chain_company": 4,
    "crawl_node_task": 6,
}


def _migration_sql() -> str:
    return (
        files("cninfo_chain")
        .joinpath("migrations", "001_initial.sql")
        .read_text(encoding="utf-8")
    )


def test_migration_has_six_commented_mysql_tables_and_45_commented_columns():
    sql = _migration_sql()
    assert "sqlite" not in sql.casefold()

    table_blocks = re.findall(
        r"CREATE TABLE `(\w+)` \((.*?)\) ENGINE=InnoDB.*?COMMENT='([^']+)'",
        sql,
        flags=re.DOTALL,
    )
    assert {name for name, _, _ in table_blocks} == set(EXPECTED_COLUMNS)

    column_count = 0
    for table_name, body, table_comment in table_blocks:
        assert table_comment
        column_lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip().startswith("`")
        ]
        assert len(column_lines) == EXPECTED_COLUMNS[table_name]
        assert all(" COMMENT '" in line for line in column_lines)
        column_count += len(column_lines)

    assert column_count == 45


def test_migration_declares_the_required_table_links():
    sql = _migration_sql()
    required_links = {
        "`industry_chain_node`": (
            "FOREIGN KEY (`industry_chain_id`) REFERENCES `industry_chain` (`id`)",
            "FOREIGN KEY (`parent_id`) REFERENCES `industry_chain_node` (`id`)",
        ),
        "`industry_chain_company`": (
            "FOREIGN KEY (`industry_chain_node_id`) REFERENCES `industry_chain_node` (`id`)",
            "FOREIGN KEY (`company_id`) REFERENCES `company` (`id`)",
        ),
        "`crawl_node_task`": (
            "FOREIGN KEY (`run_id`) REFERENCES `crawl_run` (`run_id`)",
            "FOREIGN KEY (`industry_chain_node_id`) REFERENCES `industry_chain_node` (`id`)",
        ),
    }
    for table_name, links in required_links.items():
        assert f"CREATE TABLE {table_name}" in sql
        assert all(link in sql for link in links)

