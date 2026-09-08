from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from cninfo_chain.errors import ReferenceDataError


_AKSHARE_SYMBOL = re.compile(r"^(sh|sz|bj)([0-9]{6})$", re.IGNORECASE)
_FULL_CODE = re.compile(r"^([0-9]{6})\.(SH|SZ|BJ)$", re.IGNORECASE)
_PREFIXED_CODE = re.compile(r"^(sh|sz|bj)\.?([0-9]{6})$", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class AShareSecurity:
    full_code: str
    stock_code: str
    exchange: str
    security_name: str
    akshare_symbol: str


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def normalize_akshare_row(symbol: object, name: object) -> AShareSecurity:
    symbol_text = _text(symbol).lower()
    match = _AKSHARE_SYMBOL.fullmatch(symbol_text)
    security_name = _text(name)
    if not match:
        raise ReferenceDataError(f"invalid AkShare symbol: {symbol!r}")
    if not security_name:
        raise ReferenceDataError(f"missing security name for: {symbol_text}")
    exchange = match.group(1).upper()
    stock_code = match.group(2)
    return AShareSecurity(
        full_code=f"{stock_code}.{exchange}",
        stock_code=stock_code,
        exchange=exchange,
        security_name=security_name,
        akshare_symbol=symbol_text,
    )


def parse_akshare_rows(rows: Sequence[Mapping[str, object]]) -> list[AShareSecurity]:
    result: list[AShareSecurity] = []
    seen_codes: set[str] = set()
    seen_symbols: set[str] = set()
    for index, row in enumerate(rows):
        if "代码" not in row or "名称" not in row:
            raise ReferenceDataError(f"AkShare row {index} lacks 代码 or 名称")
        try:
            security = normalize_akshare_row(row["代码"], row["名称"])
        except ReferenceDataError as error:
            raise ReferenceDataError(f"AkShare row {index}: {error}") from error
        if security.full_code in seen_codes or security.akshare_symbol in seen_symbols:
            raise ReferenceDataError(f"duplicate security code: {security.full_code}")
        seen_codes.add(security.full_code)
        seen_symbols.add(security.akshare_symbol)
        result.append(security)
    if not result:
        raise ReferenceDataError("AkShare returned no A-share securities")
    return result


def clean_cninfo_stock_code(value: object) -> str | None:
    text = _text(value)
    if not text:
        return None
    text = text.replace("*", "")
    text = re.sub(r"\s+", "", text)
    match = _FULL_CODE.fullmatch(text.upper())
    if match:
        return match.group(1)
    match = _PREFIXED_CODE.fullmatch(text)
    if match:
        return match.group(2)
    if re.fullmatch(r"[0-9]{6}", text):
        return text
    return None


def load_akshare_rows() -> Sequence[Mapping[str, object]]:
    try:
        import akshare as ak
    except ImportError as error:
        raise ReferenceDataError(
            "AkShare is required for reference init/refresh; install the reference extra"
        ) from error
    frame = ak.stock_zh_a_spot()
    if not hasattr(frame, "to_dict"):
        raise ReferenceDataError("AkShare stock_zh_a_spot returned an invalid result")
    return frame.to_dict("records")
