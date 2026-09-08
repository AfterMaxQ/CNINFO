from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from cninfo_chain.normalization import normalize_short_name
from cninfo_chain.securities import clean_cninfo_stock_code
from cninfo_chain.storage import MySQLStore


@dataclass(frozen=True, slots=True)
class StockCodeChange:
    company_id: int
    old_value: str | None
    new_value: str | None
    reason: str


@dataclass(frozen=True, slots=True)
class ShortNameChange:
    company_id: int
    old_value: str
    new_value: str
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


def preview_short_name_cleanup(store: MySQLStore) -> list[ShortNameChange]:
    changes: list[ShortNameChange] = []
    for row in store.list_company_stock_codes():
        old_value = row.get("company_short_name")
        if old_value is None or "*" not in str(old_value):
            continue
        old_text = str(old_value)
        new_value = normalize_short_name(old_text)
        if new_value and new_value != old_text:
            changes.append(
                ShortNameChange(int(row["id"]), old_text, new_value, "remove name marker")
            )
    return changes


def execute_stock_code_cleanup(
    store: MySQLStore,
    changes: Sequence[StockCodeChange],
) -> int:
    if not changes:
        return 0
    return store.update_company_stock_codes(changes)


def execute_company_cleanup(
    store: MySQLStore,
    stock_code_changes: Sequence[StockCodeChange],
    short_name_changes: Sequence[ShortNameChange],
) -> int:
    return store.update_company_cleanup(stock_code_changes, short_name_changes)


def cleanup_summary(
    store: MySQLStore,
) -> tuple[list[StockCodeChange], list[StockCodeChange], list[ShortNameChange], int]:
    rows = store.list_company_stock_codes()
    code_changes: list[StockCodeChange] = []
    invalid: list[StockCodeChange] = []
    short_name_changes: list[ShortNameChange] = []
    for row in rows:
        company_id = int(row["id"])
        old_code = row.get("stock_code")
        if old_code is None or not str(old_code).strip():
            invalid.append(StockCodeChange(company_id, old_code, None, "empty stock code"))
        else:
            new_code = clean_cninfo_stock_code(old_code)
            if new_code is None:
                invalid.append(
                    StockCodeChange(
                        company_id,
                        str(old_code),
                        None,
                        "not a unique six-digit code",
                    )
                )
            elif new_code != str(old_code):
                code_changes.append(
                    StockCodeChange(company_id, str(old_code), new_code, "remove code markers")
                )
        old_name = row.get("company_short_name")
        if old_name is not None and "*" in str(old_name):
            old_name_text = str(old_name)
            new_name = normalize_short_name(old_name_text)
            if new_name and new_name != old_name_text:
                short_name_changes.append(
                    ShortNameChange(company_id, old_name_text, new_name, "remove name marker")
                )
    return code_changes, invalid, short_name_changes, len(rows)
