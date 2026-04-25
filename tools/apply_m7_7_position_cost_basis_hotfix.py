from __future__ import annotations

from pathlib import Path


TARGET = Path("src/stock_quant_v2/trading_domain/services/paper_position_apply_fill_service.py")


OLD_BLOCK = """        position["quantity"] = new_quantity

        # T+1：当日买入不增加 available_quantity。
        if "available_quantity" not in position or position.get("available_quantity") is None:
            position["available_quantity"] = Decimal("0")

        self._set_if_exists(position, "avg_cost", new_avg_cost)
        self._set_if_exists(position, "cost_price", new_avg_cost)
        self._set_if_exists(position, "cost_amount", new_cost_amount)
        self._set_if_exists(position, "last_buy_date", effective_date)
        self._set_if_exists(position, "position_status", "OPEN")
        self._set_if_exists(position, "status", "OPEN")
"""


NEW_BLOCK = """        position["quantity"] = new_quantity

        # T+1：当日买入不增加 available_quantity。
        if "available_quantity" not in position or position.get("available_quantity") is None:
            position["available_quantity"] = Decimal("0")

        # M7.7-Fix-2:
        # New BUY positions are created from fill rows, so the working row may not
        # contain position-table cost / valuation keys yet.  The final insert payload
        # is built from this working row, therefore these values must be materialized
        # here instead of using _set_if_exists only.
        position["avg_cost"] = new_avg_cost
        position["cost_price"] = new_avg_cost
        position["average_cost"] = new_avg_cost
        position["cost_amount"] = new_cost_amount
        position["total_cost"] = new_cost_amount

        position["market_price"] = fill_price
        position["last_price"] = fill_price
        position["close_price"] = fill_price
        position["price"] = fill_price

        market_value = self._money(new_quantity * fill_price)
        unrealized_pnl = self._money(market_value - new_cost_amount)
        realized_pnl = self._to_decimal(position.get("realized_pnl"))

        position["market_value"] = market_value
        position["unrealized_pnl"] = unrealized_pnl
        position["total_pnl"] = self._money(realized_pnl + unrealized_pnl)

        self._set_if_exists(position, "last_buy_date", effective_date)
        self._set_if_exists(position, "position_status", "OPEN")
        self._set_if_exists(position, "status", "OPEN")
"""


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(f"Cannot find {TARGET}")

    text = TARGET.read_text(encoding="utf-8")

    if "M7.7-Fix-2" in text:
        print(f"[OK] M7.7 position cost basis hotfix already applied: {TARGET}")
        return

    if OLD_BLOCK not in text:
        raise RuntimeError(
            "Could not find expected _apply_buy block. "
            "Open paper_position_apply_fill_service.py and patch _apply_buy manually."
        )

    TARGET.write_text(text.replace(OLD_BLOCK, NEW_BLOCK), encoding="utf-8")
    print(f"[OK] applied M7.7 position cost basis hotfix: {TARGET}")


if __name__ == "__main__":
    main()
