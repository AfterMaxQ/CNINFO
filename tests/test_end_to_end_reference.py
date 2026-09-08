from __future__ import annotations

from cninfo_chain.reference import match_security, replace_reference_table
from cninfo_chain.securities import AShareSecurity


class LocalReferenceStore:
    def __init__(self):
        self.rows = []

    def replace_a_share_security(self, rows):
        self.rows = [
            {
                "full_code": row.full_code,
                "stock_code": row.stock_code,
                "security_name": row.security_name,
                "akshare_symbol": row.akshare_symbol,
            }
            for row in rows
        ]
        return len(self.rows)

    def find_a_share_security(self, *, stock_code=None, security_name=None):
        return [
            row
            for row in self.rows
            if (stock_code is None or row["stock_code"] == stock_code)
            and (security_name is None or row["security_name"] == security_name)
        ]


def test_local_reference_lookup_does_not_need_akshare(monkeypatch):
    from cninfo_chain import securities

    monkeypatch.setattr(
        securities,
        "load_akshare_rows",
        lambda: (_ for _ in ()).throw(AssertionError("AkShare must not be called")),
    )
    store = LocalReferenceStore()
    replace_reference_table(
        store,
        [AShareSecurity("600519.SH", "600519", "SH", "贵州茅台", "sh600519")],
    )
    result = match_security(store, stock_code="600519")
    assert result.status == "matched"
    assert result.full_code == "600519.SH"
