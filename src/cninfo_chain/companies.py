from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from cninfo_chain.errors import IdentityConflict
from cninfo_chain.models import CompanyCandidate, MergedCompany
from cninfo_chain.normalization import normalize_company_name, normalize_short_name
from cninfo_chain.storage import aggregate_listing_status


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _first(*values: Any) -> str | None:
    for value in values:
        text = _text(value)
        if text:
            return text
    return None


def candidates_from_income(
    items: Sequence[dict[str, Any]], *, start_order: int
) -> list[CompanyCandidate]:
    result: list[CompanyCandidate] = []
    for index, item in enumerate(items):
        name = _first(item.get("company_name_one"), item.get("company_name_two"))
        if not name:
            continue
        result.append(
            CompanyCandidate(
                company_name=name,
                company_short_name=normalize_short_name(
                    _first(item.get("secname_one"), item.get("secname_two"))
                ),
                cninfo_company_id=_first(
                    item.get("company_num_id_one"), item.get("company_num_id_two")
                ),
                stock_code=_first(item.get("seccode_one"), item.get("seccode_two")),
                listing_signal=1,
                source_order=start_order + index,
            )
        )
    return result


def candidates_from_listed(
    items: Sequence[dict[str, Any]], *, start_order: int
) -> list[CompanyCandidate]:
    result: list[CompanyCandidate] = []
    for index, item in enumerate(items):
        name = _first(item.get("fullname"), item.get("companyShortName"))
        if not name:
            continue
        result.append(
            CompanyCandidate(
                company_name=name,
                company_short_name=normalize_short_name(_text(item.get("companyShortName"))),
                cninfo_company_id=_text(item.get("company_id")),
                stock_code=_text(item.get("stockCode")),
                listing_signal=1,
                source_order=start_order + index,
            )
        )
    return result


def candidates_from_non_listed(
    items: Sequence[dict[str, Any]], *, start_order: int
) -> list[CompanyCandidate]:
    result: list[CompanyCandidate] = []
    for index, item in enumerate(items):
        name = _first(item.get("fullname"), item.get("companyShortName"))
        if not name:
            continue
        stock_code = None
        stocks = item.get("stock")
        if isinstance(stocks, list):
            for stock in stocks:
                if isinstance(stock, dict):
                    stock_code = _text(stock.get("stock_id"))
                    if stock_code:
                        break
        result.append(
            CompanyCandidate(
                company_name=name,
                company_short_name=None,
                cninfo_company_id=_text(item.get("company_id")),
                stock_code=stock_code or _text(item.get("stockCode")),
                listing_signal=0,
                source_order=start_order + index,
            )
        )
    return result


@dataclass(slots=True)
class _Entity:
    company_name: str
    company_short_name: str | None
    normalized_name: str
    cninfo_company_id: str | None
    stock_code: str | None
    source_order: int
    signals: list[int] = field(default_factory=list)


def merge_companies(candidates: Sequence[CompanyCandidate]) -> list[MergedCompany]:
    entities: list[_Entity] = []
    by_company_id: dict[str, int] = {}
    by_stock_code: dict[str, int] = {}
    by_name: dict[str, int] = {}

    for candidate in candidates:
        normalized_name = normalize_company_name(candidate.company_name)
        if not normalized_name:
            continue
        matches: set[int] = set()
        if candidate.cninfo_company_id in by_company_id:
            matches.add(by_company_id[candidate.cninfo_company_id])
        if candidate.stock_code in by_stock_code:
            matches.add(by_stock_code[candidate.stock_code])
        if normalized_name in by_name:
            matches.add(by_name[normalized_name])
        if len(matches) > 1:
            raise IdentityConflict(
                f"candidate identifiers point to different companies: {candidate.company_name}"
            )

        if matches:
            entity_index = matches.pop()
            entity = entities[entity_index]
            if (
                entity.cninfo_company_id
                and candidate.cninfo_company_id
                and entity.cninfo_company_id != candidate.cninfo_company_id
            ):
                raise IdentityConflict(
                    f"conflicting CNINFO company IDs: {candidate.company_name}"
                )
            if (
                entity.stock_code
                and candidate.stock_code
                and entity.stock_code != candidate.stock_code
            ):
                raise IdentityConflict(f"conflicting stock codes: {candidate.company_name}")
            entity.cninfo_company_id = entity.cninfo_company_id or candidate.cninfo_company_id
            entity.stock_code = entity.stock_code or candidate.stock_code
            entity.company_short_name = (
                entity.company_short_name
                or normalize_short_name(candidate.company_short_name)
            )
            entity.signals.append(candidate.listing_signal)
        else:
            entity_index = len(entities)
            entity = _Entity(
                company_name=candidate.company_name,
                company_short_name=normalize_short_name(candidate.company_short_name),
                normalized_name=normalized_name,
                cninfo_company_id=candidate.cninfo_company_id,
                stock_code=candidate.stock_code,
                source_order=candidate.source_order,
                signals=[candidate.listing_signal],
            )
            entities.append(entity)

        for key, mapping in (
            (entity.cninfo_company_id, by_company_id),
            (entity.stock_code, by_stock_code),
            (entity.normalized_name, by_name),
        ):
            if key is None:
                continue
            existing = mapping.get(key)
            if existing is not None and existing != entity_index:
                raise IdentityConflict(f"identifier is already assigned: {key}")
            mapping[key] = entity_index

    return [
        MergedCompany(
            company_name=entity.company_name,
            company_short_name=entity.company_short_name,
            normalized_name=entity.normalized_name,
            cninfo_company_id=entity.cninfo_company_id,
            stock_code=entity.stock_code,
            listing_status=aggregate_listing_status(entity.signals),
            source_order=entity.source_order,
        )
        for entity in entities
    ]
