from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

from cninfo_chain.errors import (
    ApiBusinessError,
    NodeSetMismatch,
    PaginationMismatch,
    SchemaChanged,
    UnknownZone,
)
from cninfo_chain.models import ChainNode, ChainSeed, PageResult


CHAIN_PAGE_BASE = "https://pis.cninfo.com.cn/ics/index.html#/industryChain"
ZONE_GROUPS = (
    ("tier1", "上游", "上游"),
    ("tier2", "中游", "中游"),
    ("tier3", "下游", "下游"),
    ("tier0", "其他", "未分配节点"),
)


def _envelope(payload: Any, endpoint: str) -> Any:
    if not isinstance(payload, Mapping):
        raise SchemaChanged(f"{endpoint}: response must be an object")
    code = payload.get("code")
    if str(code) != "200":
        raise ApiBusinessError(str(code), str(payload.get("msg", "request failed")))
    if payload.get("ok") is False:
        raise ApiBusinessError(str(code), str(payload.get("msg", "ok=false")))
    if "data" not in payload:
        raise SchemaChanged(f"{endpoint}: missing data")
    return payload["data"]


def _mapping(value: Any, location: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise SchemaChanged(f"{location} must be an object")
    return value


def _list(value: Any, location: str) -> list[Any]:
    if not isinstance(value, list):
        raise SchemaChanged(f"{location} must be an array")
    return value


def _nonempty(value: Any, location: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SchemaChanged(f"{location} must be a non-empty string")
    return value


def _integer(value: Any, location: str) -> int:
    if isinstance(value, bool):
        raise SchemaChanged(f"{location} must be an integer")
    try:
        result = int(value)
    except (TypeError, ValueError) as error:
        raise SchemaChanged(f"{location} must be an integer") from error
    return result


def parse_chain_list(payload: Any) -> list[ChainSeed]:
    groups = _list(_envelope(payload, "chain_list"), "chain_list.data")
    result: list[ChainSeed] = []
    seen: set[str] = set()
    for group_index, raw_group in enumerate(groups):
        group = _mapping(raw_group, f"chain_list.data[{group_index}]")
        menu_name = _nonempty(group.get("chain_menu"), "chain_menu")
        chains = _list(group.get("chains"), "chains")
        for raw_chain in chains:
            chain = _mapping(raw_chain, "chain")
            chain_id = _nonempty(chain.get("chain_id"), "chain.chain_id")
            if chain_id in seen:
                raise SchemaChanged(f"duplicate chain_id: {chain_id}")
            seen.add(chain_id)
            result.append(
                ChainSeed(
                    chain_id=chain_id,
                    chain_name=_nonempty(chain.get("chain_name"), "chain.chain_name"),
                    menu_name=str(chain.get("chain_menu") or menu_name),
                    sort_no=len(result),
                )
            )
    if not result:
        raise SchemaChanged("chain_list returned no themes")
    return result


def parse_industry_metadata(payload: Any) -> dict[str, dict[str, Any]]:
    data = _mapping(_envelope(payload, "industry_info"), "industry_info.data")
    items = _list(data.get("list"), "industry_info.data.list")
    total = _integer(data.get("total"), "industry_info.data.total")
    if total != len(items):
        raise SchemaChanged(f"industry_info total mismatch: {total} != {len(items)}")
    result: dict[str, dict[str, Any]] = {}
    for raw_item in items:
        item = dict(_mapping(raw_item, "industry_info item"))
        node_id = _nonempty(item.get("cnode_id"), "industry_info.cnode_id")
        if node_id in result:
            raise SchemaChanged(f"duplicate industry metadata node: {node_id}")
        result[node_id] = item
    return result


def parse_dynamic_nodes(
    chain_id: str,
    payload: Any,
    metadata: Mapping[str, Mapping[str, Any]],
) -> list[ChainNode]:
    data = _mapping(_envelope(payload, "dynamic_map"), "dynamic_map.data")
    result: list[ChainNode] = []
    seen: set[str] = set()

    def visit(
        raw_node: Any,
        *,
        parent_node_id: str | None,
        path: tuple[str, ...],
        zone: str,
        raw_zone: str,
    ) -> None:
        node = _mapping(raw_node, "dynamic node")
        node_id = _nonempty(node.get("node_id"), "dynamic node_id")
        node_name = _nonempty(node.get("node_name"), "dynamic node_name")
        if node_id in seen:
            raise NodeSetMismatch(f"duplicate dynamic node: {node_id}")
        observed_zone = _nonempty(node.get("chain_up_down"), "dynamic chain_up_down")
        if observed_zone != raw_zone:
            raise UnknownZone(
                f"{node_id}: expected {raw_zone} in source group, got {observed_zone}"
            )
        if parent_node_id and node.get("node_pid") not in (None, "", parent_node_id):
            raise NodeSetMismatch(f"{node_id}: node_pid conflicts with children relationship")
        seen.add(node_id)
        meta = metadata.get(node_id)
        if meta is None:
            raise NodeSetMismatch(f"dynamic node missing metadata: {node_id}")
        current_path = (*path, node_name)
        industry_code = _optional_string(meta.get("industry_code"))
        result.append(
            ChainNode(
                chain_id=chain_id,
                node_id=node_id,
                parent_node_id=parent_node_id,
                node_name=node_name,
                node_definition=_optional_string(meta.get("chain_introduction")),
                business_zone=zone,
                sort_no=len(result),
                path=current_path,
                industry_code=industry_code,
                industry_name=_optional_string(meta.get("industry_name")),
                source_url=(
                    f"{CHAIN_PAGE_BASE}/{node_id}/{chain_id}/{node_id}/"
                    f"{quote(node_name, safe='')}"
                ),
            )
        )
        children = _list(node.get("children"), f"{node_id}.children")
        for child in children:
            visit(
                child,
                parent_node_id=node_id,
                path=current_path,
                zone=zone,
                raw_zone=raw_zone,
            )

    for group_key, zone, raw_zone in ZONE_GROUPS:
        roots = _list(data.get(group_key), f"dynamic_map.data.{group_key}")
        for root in roots:
            visit(
                root,
                parent_node_id=None,
                path=(),
                zone=zone,
                raw_zone=raw_zone,
            )
    metadata_ids = set(metadata)
    if seen != metadata_ids:
        missing_dynamic = sorted(metadata_ids - seen)
        missing_metadata = sorted(seen - metadata_ids)
        raise NodeSetMismatch(
            f"node sets differ: dynamic_missing={missing_dynamic}, metadata_missing={missing_metadata}"
        )
    return result


def parse_company_income_page(payload: Any) -> PageResult:
    data = _mapping(_envelope(payload, "company_income"), "company_income.data")
    page_data = _mapping(data.get("list"), "company_income.data.list")
    return PageResult(
        endpoint="company_income",
        items=tuple(
            dict(_mapping(item, "company_income item"))
            for item in _list(page_data.get("list"), "company_income.data.list.list")
        ),
        total=_integer(page_data.get("total"), "company_income.total"),
        pages=_integer(page_data.get("pages"), "company_income.pages"),
        page=_integer(page_data.get("page_num"), "company_income.page_num"),
        page_size=_integer(page_data.get("page_size"), "company_income.page_size"),
    )


def parse_search_page(payload: Any, endpoint: str, page_size: int) -> PageResult:
    if endpoint not in {"listed_search", "non_listed_search"}:
        raise ValueError(f"unsupported search endpoint: {endpoint}")
    data = _mapping(_envelope(payload, endpoint), f"{endpoint}.data")
    return PageResult(
        endpoint=endpoint,
        items=tuple(
            dict(_mapping(item, f"{endpoint} item"))
            for item in _list(data.get("companys"), f"{endpoint}.data.companys")
        ),
        total=_integer(data.get("total"), f"{endpoint}.total"),
        pages=_integer(data.get("total_page"), f"{endpoint}.total_page"),
        page=_integer(data.get("page"), f"{endpoint}.page"),
        page_size=page_size,
    )


def validate_pages(pages: Sequence[PageResult]) -> list[dict[str, Any]]:
    if not pages:
        raise PaginationMismatch("no pages captured")
    first = pages[0]
    if len(pages) != first.pages:
        raise PaginationMismatch(f"expected {first.pages} pages, captured {len(pages)}")
    items: list[dict[str, Any]] = []
    for expected_page, page in enumerate(pages, start=1):
        if (
            page.endpoint != first.endpoint
            or page.total != first.total
            or page.pages != first.pages
            or page.page != expected_page
            or page.page_size != first.page_size
        ):
            raise PaginationMismatch(f"inconsistent pagination at page {expected_page}")
        if len(page.items) > page.page_size:
            raise PaginationMismatch(f"page {expected_page} exceeds page_size")
        items.extend(page.items)
    if len(items) != first.total:
        raise PaginationMismatch(f"expected {first.total} rows, captured {len(items)}")
    return items


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
