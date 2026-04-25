from stock_quant_v2.data_domain.services.instrument_classification_service import classify_cn_instrument


def test_classify_index():
    assert classify_cn_instrument("SSE", "000001", "上证综合指数") == "INDEX"


def test_classify_bond_index():
    assert classify_cn_instrument("SSE", "000012", "国债指数") == "BOND_INDEX"


def test_classify_fund_index():
    assert classify_cn_instrument("SSE", "000100", "基金指数") == "FUND_INDEX"


def test_classify_equity():
    assert classify_cn_instrument("SSE", "600000", "浦发银行") == "EQUITY"
    assert classify_cn_instrument("SZSE", "000001", "平安银行") == "EQUITY"