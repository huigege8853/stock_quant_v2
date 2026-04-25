from stock_quant_v2.data_domain.services.universe_service import is_valid_cn_stock


def test_is_valid_cn_stock_sse():
    assert is_valid_cn_stock("SSE", "600000") is True
    assert is_valid_cn_stock("SSE", "688001") is True
    assert is_valid_cn_stock("SSE", "000001") is False


def test_is_valid_cn_stock_szse():
    assert is_valid_cn_stock("SZSE", "000001") is True
    assert is_valid_cn_stock("SZSE", "300001") is True
    assert is_valid_cn_stock("SZSE", "600000") is False