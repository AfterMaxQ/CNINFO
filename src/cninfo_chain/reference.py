from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from cninfo_chain.errors import ReferenceDataError
from cninfo_chain.securities import AShareSecurity, clean_cninfo_stock_code
from cninfo_chain.storage import MySQLStore


@dataclass(frozen=True, slots=True)
class ReferencePreview:
    total: int
    sh_count: int
    sz_count: int
    bj_count: int
    invalid_count: int
    duplicate_count: int
    sample_rows: tuple[AShareSecurity, ...]


@dataclass(frozen=True, slots=True)
class SecurityMatch:
    status: str
    full_code: str | None = None
    akshare_symbol: str | None = None
    security_name: str | None = None
    reason: str | None = None


def build_reference_preview(rows: Sequence[AShareSecurity]) -> ReferencePreview:
    seen: set[str] = set()
    duplicate_count = 0
    sh_count = sz_count = bj_count = 0
    for row in rows:
        if row.full_code in seen:
            duplicate_count += 1
        seen.add(row.full_code)
        if row.exchange == "SH":
            sh_count += 1
        elif row.exchange == "SZ":
            sz_count += 1
        elif row.exchange == "BJ":
            bj_count += 1
    return ReferencePreview(
        total=len(rows),
        sh_count=sh_count,
        sz_count=sz_count,
        bj_count=bj_count,
        invalid_count=0,
        duplicate_count=duplicate_count,
        sample_rows=tuple(rows[:5]),
    )


def replace_reference_table(
    store: MySQLStore, rows: Sequence[AShareSecurity]
) -> int:
    preview = build_reference_preview(rows)
    if preview.total == 0:
        raise ReferenceDataError("reference table cannot be replaced with no rows")
    if preview.invalid_count or preview.duplicate_count:
        raise ReferenceDataError("reference rows failed validation")
    return store.replace_a_share_security(rows)


def _match_row(row: dict[str, Any]) -> SecurityMatch:
    return SecurityMatch(
        status="matched",
        full_code=row["full_code"],
        akshare_symbol=row["akshare_symbol"],
        security_name=row["security_name"],
    )


def match_security(
    store: MySQLStore,
    *,
    stock_code: object = None,
    security_name: object = None,
) -> SecurityMatch:
    cleaned_code = clean_cninfo_stock_code(stock_code)
    name = str(security_name).strip() if security_name is not None else ""
    code_rows = store.find_a_share_security(stock_code=cleaned_code) if cleaned_code else []
    name_rows = store.find_a_share_security(security_name=name) if name else []

    if code_rows and name_rows:
        code_keys = {row["full_code"] for row in code_rows}
        intersection = [row for row in name_rows if row["full_code"] in code_keys]
        if len(intersection) == 1:
            return _match_row(intersection[0])
        if not intersection:
            return SecurityMatch(status="conflict", reason="code and name resolve to different securities")
        return SecurityMatch(status="ambiguous", reason="code and name resolve to multiple securities")
    if len(code_rows) == 1:
        return _match_row(code_rows[0])
    if len(code_rows) > 1:
        return SecurityMatch(status="ambiguous", reason="stock code exists on multiple exchanges")
    if len(name_rows) == 1:
        return _match_row(name_rows[0])
    if len(name_rows) > 1:
        return SecurityMatch(status="ambiguous", reason="security name matches multiple securities")
    return SecurityMatch(status="unmatched", reason="no local security reference matched")
