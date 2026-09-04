from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChainSeed:
    chain_id: str
    chain_name: str
    menu_name: str
    sort_no: int


@dataclass(frozen=True, slots=True)
class ChainNode:
    chain_id: str
    node_id: str
    parent_node_id: str | None
    node_name: str
    node_definition: str | None
    business_zone: str
    sort_no: int
    path: tuple[str, ...]
    industry_code: str | None
    industry_name: str | None
    source_url: str


@dataclass(frozen=True, slots=True)
class CompanyCandidate:
    company_name: str
    company_short_name: str | None
    cninfo_company_id: str | None
    stock_code: str | None
    listing_signal: int
    source_order: int


@dataclass(frozen=True, slots=True)
class MergedCompany:
    company_name: str
    company_short_name: str | None
    normalized_name: str
    cninfo_company_id: str | None
    stock_code: str | None
    listing_status: int
    source_order: int
