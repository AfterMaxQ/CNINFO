from cninfo_chain.normalization import normalize_company_name, normalize_short_name


def test_company_normalization_is_exact_and_conservative():
    assert normalize_company_name("  天洋新材（上海）  科技股份有限公司  ") == (
        "天洋新材(上海) 科技股份有限公司"
    )
    assert normalize_company_name("ＡＢＣ（中国）") == "ABC(中国)"


def test_short_name_normalization_does_not_guess_or_remove_suffixes():
    assert normalize_short_name(None) is None
    assert normalize_short_name("  福斯特（中国） ") == "福斯特(中国)"
    assert normalize_short_name("示例股份有限公司") == "示例股份有限公司"

