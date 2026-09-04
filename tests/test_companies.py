from __future__ import annotations

import pytest

from cninfo_chain.companies import (
    candidates_from_income,
    candidates_from_listed,
    candidates_from_non_listed,
    merge_companies,
)
from cninfo_chain.errors import IdentityConflict
from cninfo_chain.models import CompanyCandidate
from cninfo_chain.parsers import (
    parse_company_income_page,
    parse_search_page,
    validate_pages,
)


def _real_candidates(load_json):
    income_items = parse_company_income_page(
        load_json("node_A02n019_companyIncome.json")
    ).items
    listed_items = parse_search_page(
        load_json("node_A02n019_searchOtherListed.json"), "listed_search", 15
    ).items
    non_listed_pages = [
        parse_search_page(
            load_json(f"node_A02n019_searchglobalNew{suffix}.json"),
            "non_listed_search",
            15,
        )
        for suffix in ("", "_page2", "_page3", "_page4", "_page5")
    ]
    non_listed_items = validate_pages(non_listed_pages)
    income = candidates_from_income(income_items, start_order=0)
    listed = candidates_from_listed(listed_items, start_order=len(income))
    non_listed = candidates_from_non_listed(
        non_listed_items, start_order=len(income) + len(listed)
    )
    return income + listed + non_listed


def test_real_eva_candidates_merge_from_87_rows_to_85_companies(load_json):
    candidates = _real_candidates(load_json)
    merged = merge_companies(candidates)
    assert len(candidates) == 87
    assert len(merged) == 85
    assert len({company.source_order for company in merged}) == 85

    tianyang = next(company for company in merged if company.stock_code == "603330")
    assert tianyang.company_short_name == "天洋新材"
    assert tianyang.listing_status == 1

    youlesai = next(company for company in merged if company.cninfo_company_id == "6830078")
    assert youlesai.listing_status == 2


def test_non_listed_mapping_keeps_company_but_leaves_short_name_empty(load_json):
    page = parse_search_page(
        load_json("node_A02n019_searchglobalNew.json"), "non_listed_search", 15
    )
    candidate = candidates_from_non_listed(page.items, start_order=0)[0]
    assert candidate.company_name == "无锡市万力粘合材料股份有限公司"
    assert candidate.company_short_name is None
    assert candidate.cninfo_company_id == "141143"
    assert candidate.stock_code == "834763"
    assert candidate.listing_signal == 0


def test_conflicting_stable_identifiers_fail_the_whole_merge():
    candidates = [
        CompanyCandidate("甲公司", "甲", "1", "A", 1, 0),
        CompanyCandidate("乙公司", "乙", "2", "B", 1, 1),
        CompanyCandidate("甲公司", None, "1", "B", 0, 2),
    ]
    with pytest.raises(IdentityConflict):
        merge_companies(candidates)
