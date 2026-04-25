from __future__ import annotations

from pathlib import Path

TARGET = Path('src/stock_quant_v2/trading_domain/services/paper_rebalance_service.py')


def main() -> None:
    path = TARGET
    if not path.exists():
        raise SystemExit(f'[FAIL] not found: {path}')

    text = path.read_text(encoding='utf-8')

    # 1) Replace call site to pass security/date context into price resolver.
    old_call = '''        estimated_price = self._resolve_estimated_price(
            current_row=current_row,
            target_row=target_row,
            template_row=template_row,
            fallback_template_row=fallback_template_row,
        )'''
    new_call = '''        estimated_price = self._resolve_estimated_price(
            current_row=current_row,
            target_row=target_row,
            template_row=template_row,
            fallback_template_row=fallback_template_row,
            security_key=security_key,
            security_value=security_value,
            as_of_date=as_of_date,
            effective_date=effective_date,
        )'''
    if old_call in text:
        text = text.replace(old_call, new_call)

    # 2) Replace resolver with DB-backed fallback. The implementation intentionally
    # keeps the original row-candidate logic first, then falls back to core_daily_bar.
    start = text.find('    def _resolve_estimated_price(\n')
    if start == -1:
        raise SystemExit('[FAIL] cannot find _resolve_estimated_price')
    end = text.find('    @staticmethod\n    def _pick_value', start)
    if end == -1:
        raise SystemExit('[FAIL] cannot find end marker after _resolve_estimated_price')

    replacement = r'''    def _resolve_estimated_price(
        self,
        *,
        current_row: dict[str, Any] | None,
        target_row: dict[str, Any] | None,
        template_row: dict[str, Any] | None,
        fallback_template_row: dict[str, Any] | None,
        security_key: str | None = None,
        security_value: Any | None = None,
        as_of_date: date | None = None,
        effective_date: date | None = None,
    ) -> Decimal:
        """
        M7.7-Fix-1: order 阶段必须尽量给出 estimated_price。

        价格优先级：
        1. 订单/持仓/目标行中已有价格字段；
        2. core_daily_bar 在 as_of_date 或 effective_date 之前最近一个交易日的 close/open；
        3. 返回 0，让 fill 阶段在没有价格时继续显式报错。

        注意：真正成交仍优先使用 effective_date NEXT_OPEN；这里的 estimated_price
        只是给缺失 NEXT_OPEN 的 paper-trading 测试链路提供保守 fallback。
        """

        candidate_keys = [
            "estimated_price",
            "fill_price",
            "avg_fill_price",
            "open_price",
            "close_price",
            "last_price",
            "market_price",
            "price",
            "open",
            "close",
            "avg_cost",
            "cost_price",
        ]

        for row in (template_row, current_row, target_row, fallback_template_row):
            if row is None:
                continue

            for key in candidate_keys:
                if key not in row:
                    continue

                value = self._to_decimal(row.get(key))
                if value > 0:
                    return value

        db_price = self._resolve_estimated_price_from_daily_bar(
            security_key=security_key,
            security_value=security_value,
            as_of_date=as_of_date,
            effective_date=effective_date,
        )
        if db_price > 0:
            return db_price

        return Decimal("0")

    def _resolve_estimated_price_from_daily_bar(
        self,
        *,
        security_key: str | None,
        security_value: Any | None,
        as_of_date: date | None,
        effective_date: date | None,
    ) -> Decimal:
        if not security_key or security_value is None:
            return Decimal("0")

        daily_bar_table = "core_daily_bar"
        columns = self._get_table_columns(daily_bar_table)
        if not columns:
            return Decimal("0")

        if security_key in columns:
            id_col = security_key
        elif security_key == "instrument_id" and "instrument_id" in columns:
            id_col = "instrument_id"
        else:
            return Decimal("0")

        date_col = None
        for col in ["trade_date", "bar_date", "date"]:
            if col in columns:
                date_col = col
                break
        if date_col is None:
            return Decimal("0")

        close_col = None
        for col in ["close", "close_price", "adj_close", "close_adj"]:
            if col in columns:
                close_col = col
                break

        open_col = None
        for col in ["open", "open_price", "adj_open", "open_adj"]:
            if col in columns:
                open_col = col
                break

        if close_col is None and open_col is None:
            return Decimal("0")

        price_expr_parts = []
        if close_col:
            price_expr_parts.append(close_col)
        if open_col:
            price_expr_parts.append(open_col)
        price_expr = "coalesce(" + ", ".join(price_expr_parts) + ")"

        anchor_date = as_of_date or effective_date
        if anchor_date is None:
            return Decimal("0")

        extra_filter = ""
        if "price_adjust_type" in columns:
            extra_filter = " and coalesce(price_adjust_type, 'RAW') = 'RAW'"

        row = self.session.execute(
            text(
                f"""
                select {price_expr} as estimated_price
                from {daily_bar_table}
                where {id_col} = :security_value
                  and {date_col} <= :anchor_date
                  {extra_filter}
                order by {date_col} desc
                limit 1
                """
            ),
            {
                "security_value": security_value,
                "anchor_date": anchor_date,
            },
        ).mappings().first()

        if row is None:
            return Decimal("0")

        value = self._to_decimal(row.get("estimated_price"))
        return value if value > 0 else Decimal("0")

'''
    text = text[:start] + replacement + text[end:]

    path.write_text(text, encoding='utf-8')
    print(f'[OK] applied M7.7 price fallback hotfix: {path}')


if __name__ == '__main__':
    main()
