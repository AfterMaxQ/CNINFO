from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


API_BASE = "https://pis.cninfo.com.cn/ics/aasKnowledgeBase"


@dataclass(frozen=True, slots=True)
class Endpoint:
    key: str
    path: str
    encoding: Literal["form", "json"]


ENDPOINTS = {
    "chain_list": Endpoint("chain_list", "/chaincenter/chainlist/list", "form"),
    "dynamic_map": Endpoint(
        "dynamic_map", "/chaincenter/chainlist/dynamicChainMapNew", "form"
    ),
    "chain_info": Endpoint("chain_info", "/industry/industry-info", "form"),
    "node_info": Endpoint("node_info", "/industry/industry-info", "form"),
    "company_income": Endpoint(
        "company_income", "/industryDetail/companyIncome", "json"
    ),
    "listed_search": Endpoint(
        "listed_search", "/chaincenter/searchOtherListed", "json"
    ),
    "non_listed_search": Endpoint(
        "non_listed_search", "/chaincenter/searchglobalNew", "form"
    ),
}


def request_parameters(
    endpoint_key: str,
    *,
    chain_id: str | None = None,
    node_id: str | None = None,
    industry_code: str | None = None,
    page: int = 1,
    page_size: int = 15,
) -> dict[str, Any]:
    if endpoint_key == "chain_list":
        return {"chainId": "ROOT"}
    if endpoint_key == "dynamic_map":
        return {"chainId": _required(chain_id, "chain_id")}
    if endpoint_key == "chain_info":
        return {"chainid": _required(chain_id, "chain_id")}
    if endpoint_key == "node_info":
        return {"cnodeid": _required(node_id, "node_id")}
    if endpoint_key == "company_income":
        return {
            "industryCode": _required(industry_code, "industry_code"),
            "pageNum": page,
            "pageSize": page_size,
            "industry_flag": True,
        }
    if endpoint_key == "listed_search":
        return {
            "industry": _required(industry_code, "industry_code"),
            "type": "company",
            "page_num": page,
            "page_size": page_size,
            "industry_flag": True,
        }
    if endpoint_key == "non_listed_search":
        return {
            "industry": _required(industry_code, "industry_code"),
            "type": "company",
            "pageNumber": page,
            "pageSize": page_size,
            "flag": "noListed",
            "industryFlag": True,
        }
    raise KeyError(f"unknown endpoint: {endpoint_key}")


def endpoint_url(endpoint_key: str) -> str:
    return API_BASE + ENDPOINTS[endpoint_key].path


def _required(value: str | None, name: str) -> str:
    if not value:
        raise ValueError(f"{name} is required")
    return value
