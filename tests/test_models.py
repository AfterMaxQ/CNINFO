from __future__ import annotations


def test_company_models_preserve_nullable_short_name() -> None:
    from cninfo_chain.models import CompanyCandidate, MergedCompany

    candidate = CompanyCandidate(
        company_name="无锡市万力粘合材料股份有限公司",
        company_short_name=None,
        cninfo_company_id="123",
        stock_code=None,
        listing_signal=0,
        source_order=7,
    )
    merged = MergedCompany(
        company_name=candidate.company_name,
        company_short_name=candidate.company_short_name,
        normalized_name=candidate.company_name,
        cninfo_company_id=candidate.cninfo_company_id,
        stock_code=candidate.stock_code,
        listing_status=0,
        source_order=candidate.source_order,
    )

    assert candidate.company_short_name is None
    assert merged.company_short_name is None


def test_api_business_error_keeps_stable_code() -> None:
    from cninfo_chain.errors import ApiBusinessError, CollectorError

    error = ApiBusinessError("500", "请求失败")

    assert isinstance(error, CollectorError)
    assert error.code == "500"
    assert str(error) == "500: 请求失败"
