from __future__ import annotations

from cninfo_chain.reference import build_reference_preview, match_security, replace_reference_table
from cninfo_chain.securities import AShareSecurity


ROWS = [
    AShareSecurity("600519.SH", "600519", "SH", "贵州茅台", "sh600519"),
    AShareSecurity("000001.SZ", "000001", "SZ", "平安银行", "sz000001"),
]


class FakeStore:
    def __init__(self, rows=ROWS):
        self.rows = [
            {
                "full_code": row.full_code,
                "stock_code": row.stock_code,
                "exchange": row.exchange,
                "security_name": row.security_name,
                "akshare_symbol": row.akshare_symbol,
            }
            for row in rows
        ]
        self.replaced = None

    def find_a_share_security(self, *, stock_code=None, security_name=None):
        return [
            row
            for row in self.rows
            if (stock_code is None or row["stock_code"] == stock_code)
            and (security_name is None or row["security_name"] == security_name)
        ]

    def replace_a_share_security(self, rows):
        self.replaced = list(rows)
        return len(self.replaced)


def test_reference_preview_counts_exchanges():
    preview = build_reference_preview(ROWS)
    assert (preview.total, preview.sh_count, preview.sz_count, preview.bj_count) == (2, 1, 1, 0)


def test_match_by_code_and_name():
    store = FakeStore()
    assert match_security(store, stock_code="600519").full_code == "600519.SH"
    assert match_security(store, security_name="贵州茅台").status == "matched"
    assert match_security(store, security_name="不存在").status == "unmatched"


def test_match_reports_ambiguity_and_conflict():
    same_name = ROWS + [AShareSecurity("000519.SZ", "000519", "SZ", "同名证券", "sz000519")]
    store = FakeStore(same_name)
    assert match_security(store, security_name="同名证券").status == "matched"
    store.rows.extend(
        [{
            "full_code": "300001.SZ",
            "stock_code": "300001",
            "exchange": "SZ",
            "security_name": "同名证券",
            "akshare_symbol": "sz300001",
        }]
    )
    assert match_security(store, security_name="同名证券").status == "ambiguous"
    assert match_security(store, stock_code="600519", security_name="平安银行").status == "conflict"


def test_replace_reference_table_delegates_after_validation():
    store = FakeStore()
    assert replace_reference_table(store, ROWS) == 2
    assert store.replaced == ROWS
