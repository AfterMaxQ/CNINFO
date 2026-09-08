from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cninfo_chain.securities import clean_cninfo_stock_code
from cninfo_chain.storage import MySQLStore


@dataclass(frozen=True, slots=True)
class StockCodeChange:
    company_id: int
    old_value: str | None
    new_value: str | None
    reason: str


def preview_stock_code_cleanup(
    store: MySQLStore,
) -> tuple[list[StockCodeChange], list[StockCodeChange]]:
    changes: list[StockCodeChange] = []
    invalid: list[StockCodeChange] = []
    for row in store.list_company_stock_codes():
        company_id = int(row["id"])
        old_value = row.get("stock_code")
        if old_value is None or not str(old_value).strip():
            invalid.append(
                StockCodeChange(company_id, old_value, None, "empty stock code")
            )
            continue
        new_value = clean_cninfo_stock_code(old_value)
        if new_value is None:
            invalid.append(
                StockCodeChange(company_id, str(old_value), None, "not a unique six-digit code")
            )
            continue
        old_text = str(old_value)
        if new_value != old_text:
            changes.append(
                StockCodeChange(company_id, old_text, new_value, "remove code markers")
            )
    return changes, invalid


def execute_stock_code_cleanup(
    store: MySQLStore,
    changes: Sequence[StockCodeChange],
) -> int:
    if not changes:
        return 0
    return store.update_company_stock_codes(changes)


def cleanup_summary(
    store: MySQLStore,
) -> tuple[list[StockCodeChange], list[StockCodeChange], int]:
    rows = store.list_company_stock_codes()
    changes, invalid = preview_stock_code_cleanup(store)
    return changes, invalid, len(rows)
