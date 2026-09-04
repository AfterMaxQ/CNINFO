from __future__ import annotations

import pytest

from cninfo_chain.endpoints import ENDPOINTS, request_parameters
from cninfo_chain.errors import ApiBusinessError, PaginationMismatch, SchemaChanged, UnknownZone
from cninfo_chain.parsers import (
    parse_chain_list,
    parse_company_income_page,
    parse_dynamic_nodes,
    parse_industry_metadata,
    parse_search_page,
    validate_pages,
)


def test_real_chain_list_contains_134_unique_topics(load_json):
    chains = parse_chain_list(load_json("chainlist_ROOT.json"))
    assert len(chains) == 134
    assert len({chain.chain_id for chain in chains}) == 134
    assert (chains[0].chain_id, chains[0].chain_name, chains[0].menu_name) == (
        "lsx019",
        "新能源",
        "能源",
    )
    assert chains[-1].sort_no == 133


def test_endpoint_registry_keeps_the_three_observed_request_formats():
    assert ENDPOINTS["company_income"].encoding == "json"
    assert ENDPOINTS["listed_search"].encoding == "json"
    assert ENDPOINTS["non_listed_search"].encoding == "form"
    assert request_parameters(
        "non_listed_search", industry_code="A02010201", page=5, page_size=15
    ) == {
        "key": "",
        "industry": "A02010201",
        "type": "company",
        "pageNumber": 5,
        "pageSize": 15,
        "paixu": "default",
        "companytype": "",
        "province": "",
        "city": "",
        "district": "",
        "clrq": "",
        "flag": "noListed",
        "industryFlag": True,
    }


def test_real_dynamic_tree_matches_metadata_and_keeps_source_order(load_json):
    metadata = parse_industry_metadata(load_json("chain_lsx019_industry_info.json"))
    nodes = parse_dynamic_nodes(
        "lsx019",
        load_json("chain_lsx019_dynamicChainMapNew.json"),
        metadata,
    )
    assert len(nodes) == len(metadata) == 124
    assert [node.business_zone for node in nodes[:2]] == ["上游", "上游"]
    assert nodes[-1].business_zone == "其他"

    parent = next(node for node in nodes if node.node_id == "A02n027")
    eva = next(node for node in nodes if node.node_id == "A02n019")
    assert parent.path == ("太阳能电池零部件",)
    assert eva.parent_node_id == "A02n027"
    assert eva.path == ("太阳能电池零部件", "太阳能EVA胶膜")
    assert eva.industry_code == "A02010201"
    assert eva.node_definition.startswith("太阳能EVA胶膜")
    assert eva.source_url.endswith("/lsx019/A02n019/%E5%A4%AA%E9%98%B3%E8%83%BDEVA%E8%83%B6%E8%86%9C")


def test_unknown_dynamic_zone_is_rejected(load_json):
    dynamic = load_json("chain_lsx019_dynamicChainMapNew.json")
    metadata = parse_industry_metadata(load_json("chain_lsx019_industry_info.json"))
    dynamic["data"]["tier1"][0]["chain_up_down"] = "待确认"
    with pytest.raises(UnknownZone):
        parse_dynamic_nodes("lsx019", dynamic, metadata)


def test_envelope_and_required_shape_fail_closed(load_json):
    payload = load_json("chainlist_ROOT.json")
    payload["code"] = 500
    with pytest.raises(ApiBusinessError) as error:
        parse_chain_list(payload)
    assert error.value.code == "500"

    payload = load_json("chainlist_ROOT.json")
    payload["data"][0]["chains"] = "changed"
    with pytest.raises(SchemaChanged):
        parse_chain_list(payload)


def test_real_company_pages_validate_all_pagination(load_json):
    income = parse_company_income_page(load_json("node_A02n019_companyIncome.json"))
    listed = parse_search_page(
        load_json("node_A02n019_searchOtherListed.json"), "listed_search", page_size=15
    )
    non_listed = [
        parse_search_page(
            load_json(f"node_A02n019_searchglobalNew{suffix}.json"),
            "non_listed_search",
            page_size=15,
        )
        for suffix in ("", "_page2", "_page3", "_page4", "_page5")
    ]

    assert (income.total, income.pages, len(income.items)) == (9, 1, 9)
    assert (listed.total, listed.pages, len(listed.items)) == (7, 1, 7)
    assert len(validate_pages(non_listed)) == 71

    with pytest.raises(PaginationMismatch):
        validate_pages(non_listed[:-1])


def test_empty_search_result_accepts_zero_total_pages_as_one_captured_page():
    page = parse_search_page(
        {
            "code": 200,
            "ok": True,
            "data": {"total": 0, "total_page": 0, "page": 1, "companys": []},
        },
        "non_listed_search",
        15,
    )
    assert page.pages == 1
    assert validate_pages([page]) == []
