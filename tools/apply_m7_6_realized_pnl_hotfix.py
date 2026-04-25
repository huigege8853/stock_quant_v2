from __future__ import annotations

from pathlib import Path

TARGET = Path("src/stock_quant_v2/trading_domain/services/paper_portfolio_snapshot_m7_service.py")


def main() -> None:
    if not TARGET.exists():
        raise SystemExit(f"target file not found: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")

    if "def _resolve_previous_realized_pnl" in text:
        print("[SKIP] realized_pnl hotfix already applied")
        return

    old_1 = """        previous_snapshot = self._load_previous_snapshot(\n            previous_snapshot_run_id=previous_snapshot_run_id,\n            portfolio_id=portfolio_id,\n        )\n        previous_cash_balance = self._resolve_previous_cash(previous_snapshot)\n\n        cash_delta = self._calculate_fill_cash_delta(\n"""
    new_1 = """        previous_snapshot = self._load_previous_snapshot(\n            previous_snapshot_run_id=previous_snapshot_run_id,\n            portfolio_id=portfolio_id,\n        )\n        previous_cash_balance = self._resolve_previous_cash(previous_snapshot)\n        previous_realized_pnl = self._resolve_previous_realized_pnl(previous_snapshot)\n\n        cash_delta = self._calculate_fill_cash_delta(\n"""

    if old_1 not in text:
        raise SystemExit("[FAIL] cannot find previous_snapshot / previous_cash_balance block")
    text = text.replace(old_1, new_1, 1)

    old_2 = """        market_value = valuation["market_value"]\n        total_cost = valuation["total_cost"]\n        unrealized_pnl = valuation["unrealized_pnl"]\n        realized_pnl = valuation["realized_pnl"]\n        open_position_count = valuation["open_position_count"]\n        closed_position_count = valuation["closed_position_count"]\n\n        total_equity = self._money(cash_balance + market_value)\n"""
    new_2 = """        market_value = valuation["market_value"]\n        total_cost = valuation["total_cost"]\n        unrealized_pnl = valuation["unrealized_pnl"]\n        current_position_realized_pnl = valuation["realized_pnl"]\n        open_position_count = valuation["open_position_count"]\n        closed_position_count = valuation["closed_position_count"]\n        realized_pnl = self._resolve_snapshot_realized_pnl(\n            previous_realized_pnl=previous_realized_pnl,\n            current_position_realized_pnl=current_position_realized_pnl,\n            open_position_count=open_position_count,\n            closed_position_count=closed_position_count,\n        )\n\n        total_equity = self._money(cash_balance + market_value)\n"""

    if old_2 not in text:
        raise SystemExit("[FAIL] cannot find valuation realized_pnl block")
    text = text.replace(old_2, new_2, 1)

    old_3 = """    def _calculate_fill_cash_delta(\n        self,\n"""
    helper = """    def _resolve_previous_realized_pnl(self, previous_snapshot: dict[str, Any]) -> Decimal:\n        if "realized_pnl" not in previous_snapshot:\n            return Decimal("0")\n        return self._money(self._to_decimal(previous_snapshot.get("realized_pnl")))\n\n    def _resolve_snapshot_realized_pnl(\n        self,\n        *,\n        previous_realized_pnl: Decimal,\n        current_position_realized_pnl: Decimal,\n        open_position_count: int,\n        closed_position_count: int,\n    ) -> Decimal:\n        \"\"\"\n        M7.6 hotfix: keep portfolio_snapshot.realized_pnl continuous across days.\n\n        Current M7 carry-forward only rolls open positions. After a full exit day, the\n        next day may have an empty position run, so summing realized_pnl from current\n        positions returns 0 and incorrectly resets the portfolio-level realized_pnl.\n\n        Minimal accounting rule for M7.6:\n        - If current position run has no open/closed positions and no position-level\n          realized_pnl source, inherit previous snapshot realized_pnl.\n        - Otherwise keep existing M7 behavior: use realized_pnl resolved from the\n          current position run, including closed positions when present.\n\n        A later M7.7/M8 accounting enhancement can introduce explicit\n        realized_pnl_delta at snapshot level to avoid relying on position-row sums.\n        \"\"\"\n        current_value = self._money(current_position_realized_pnl)\n        if open_position_count == 0 and closed_position_count == 0 and current_value == 0:\n            return self._money(previous_realized_pnl)\n        return current_value\n\n"""
    if old_3 not in text:
        raise SystemExit("[FAIL] cannot find _calculate_fill_cash_delta insertion point")
    text = text.replace(old_3, helper + old_3, 1)

    TARGET.write_text(text, encoding="utf-8")
    print(f"[OK] applied M7.6 realized_pnl hotfix: {TARGET}")


if __name__ == "__main__":
    main()
