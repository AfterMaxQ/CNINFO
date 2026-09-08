from __future__ import annotations

import pytest

from cninfo_chain.cleanup import (
    StockCodeChange,
    ShortNameChange,
    execute_company_cleanup,
    execute_stock_code_cleanup,
    preview_short_name_cleanup,
    preview_stock_code_cleanup,
)


class FakeStore:
    def __init__(self):
        self.rows = [
            {"id": 1, "stock_code": "*600519"},
            {"id": 2, "stock_code": " sh600519 "},
            {"id": 3, "stock_code": "*ST"},
            {"id": 4, "stock_code": None},
            {"id": 5, "stock_code": "000001"},
        ]
        self.updated = None

    def list_company_stock_codes(self):
        return self.rows

    def update_company_stock_codes(self, changes):
        self.updated = list(changes)
        return len(self.updated)

    def update_company_cleanup(self, code_changes, short_name_changes):
        self.updated = list(code_changes) + list(short_name_changes)
        return len(self.updated)


def test_preview_only_returns_safe_changes_and_invalid_rows():
    store = FakeStore()
    changes, invalid = preview_stock_code_cleanup(store)
    assert [(change.company_id, change.new_value) for change in changes] == [
        (1, "600519"),
        (2, "600519"),
    ]
    assert {change.company_id for change in invalid} == {3, 4}
    assert store.updated is None


def test_execute_delegates_only_changes():
    store = FakeStore()
    changes, _ = preview_stock_code_cleanup(store)
    assert execute_stock_code_cleanup(store, changes) == 2
    assert store.updated == changes


def test_execute_empty_changes_is_noop():
    store = FakeStore()
    assert execute_stock_code_cleanup(store, []) == 0
    assert store.updated is None


def test_preview_short_name_cleanup_removes_marker_but_keeps_st():
    store = FakeStore()
    store.rows[0]["company_short_name"] = "*ST示例"
    changes = preview_short_name_cleanup(store)
    assert changes == [ShortNameChange(1, "*ST示例", "ST示例", "remove name marker")]


def test_execute_company_cleanup_updates_codes_and_short_names_atomically():
    store = FakeStore()
    code_changes, _ = preview_stock_code_cleanup(store)
    store.rows[0]["company_short_name"] = "*ST示例"
    short_changes = preview_short_name_cleanup(store)
    assert execute_company_cleanup(store, code_changes, short_changes) == 3
    assert store.updated == code_changes + short_changes
