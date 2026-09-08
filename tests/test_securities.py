from __future__ import annotations

import pytest

from cninfo_chain.errors import ReferenceDataError
from cninfo_chain.securities import (
    clean_cninfo_stock_code,
    normalize_akshare_row,
    parse_akshare_rows,
)


def test_normalize_akshare_symbols_to_full_codes():
    assert normalize_akshare_row("sh600519", "贵州茅台").full_code == "600519.SH"
    assert normalize_akshare_row("sz000001", "平安银行").akshare_symbol == "sz000001"
    assert normalize_akshare_row("bj920047", "北交所示例").exchange == "BJ"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("*600519", "600519"),
        (" sh600519 ", "600519"),
        ("600519.SH", "600519"),
        ("000001", "000001"),
        ("*ST", None),
        (None, None),
        ("12345", None),
    ],
)
def test_clean_cninfo_stock_code(value, expected):
    assert clean_cninfo_stock_code(value) == expected


def test_parser_preserves_name_and_rejects_duplicate_codes():
    rows = [{"代码": "sh600519", "名称": "*ST贵州茅台"}]
    assert parse_akshare_rows(rows)[0].security_name == "*ST贵州茅台"
    with pytest.raises(ReferenceDataError, match="duplicate"):
        parse_akshare_rows(rows * 2)


@pytest.mark.parametrize(
    "row",
    [
        {"代码": "xx600519", "名称": "证券"},
        {"代码": "sh12345", "名称": "证券"},
        {"代码": "sh600519", "名称": ""},
        {"名称": "证券"},
    ],
)
def test_parser_rejects_invalid_rows(row):
    with pytest.raises(ReferenceDataError):
        parse_akshare_rows([row])
