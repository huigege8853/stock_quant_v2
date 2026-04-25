from __future__ import annotations


def _contains_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword in text for keyword in keywords)


def classify_cn_instrument(
    exchange_code: str,
    ticker: str,
    display_name: str,
    provider_instrument_type: str | None = None,
) -> str:
    """
    Canonical instrument types used in phase 1:
    - EQUITY
    - INDEX
    - BOND_INDEX
    - FUND_INDEX
    - UNKNOWN
    """
    name = (display_name or "").strip()
    symbol = str(ticker or "").strip()
    exchange = (exchange_code or "").strip().upper()
    provider_type = (provider_instrument_type or "").strip().upper()

    if provider_type in {"INDEX", "BOND_INDEX", "FUND_INDEX"}:
        return provider_type

    if _contains_any(name, ("基金",)):
        return "FUND_INDEX"

    if _contains_any(name, ("债", "国债", "企债", "信用债", "可转换债券")):
        return "BOND_INDEX"

    if _contains_any(
        name,
        (
            "指数",
            "综指",
            "沪深300",
            "中证",
            "上证50",
            "上证180",
            "上证380",
            "等权",
            "成长",
            "价值",
            "红利",
            "主题",
            "波动",
            "行业",
            "消费",
            "资源",
            "龙头",
            "中盘",
            "小盘",
            "全指",
            "周期",
            "海外",
            "国企",
            "民企",
            "高新",
            "分层",
            "持续产业",
            "高端装备",
            "技术领先",
            "智能资产",
            "领先行业",
            "两岸三地",
            "银河99",
        ),
    ):
        return "INDEX"

    if exchange == "SSE" and symbol.startswith(("600", "601", "603", "605", "688", "689")):
        return "EQUITY"

    if exchange == "SZSE" and symbol.startswith(("000", "001", "002", "003", "300", "301")):
        return "EQUITY"

    if exchange == "BSE" and symbol.startswith(("430", "830", "831", "832", "833", "835", "836", "837", "838", "839")):
        return "EQUITY"

    return "UNKNOWN"