from __future__ import annotations

from datetime import date
from typing import Any

import backtrader as bt


class MinimalSignalSelectionStrategy(bt.Strategy):
    """M5.11 strict NEXT_OPEN 最小真实回测策略。

    语义：
    - 消费 M4 strategy_signal 转换后的 target_weights_by_date。
    - 默认只在 open hook 中触发下单，严格服务 NEXT_OPEN。
    - next_fallback 默认关闭，仅作为 debug / emergency 选项保留。
    - 回测内部 target_weight 不等于 M6 target_position。
    """

    params = (
        ("target_weights_by_date", None),
        ("daily_records", None),
        ("order_records", None),
        ("rebalance_records", None),
        ("record_start_date", None),
        ("record_end_date", None),
        ("allow_next_fallback", False),
    )

    def __init__(self) -> None:
        self._executed_rebalance_dates: set[date] = set()

        self.target_weights_by_date = self.p.target_weights_by_date or {}
        self.daily_records = (
            self.p.daily_records if self.p.daily_records is not None else []
        )
        self.order_records = (
            self.p.order_records if self.p.order_records is not None else []
        )
        self.rebalance_records = (
            self.p.rebalance_records if self.p.rebalance_records is not None else []
        )

        self.record_start_date = self.p.record_start_date
        self.record_end_date = self.p.record_end_date
        self.allow_next_fallback = bool(self.p.allow_next_fallback)

    def prenext_open(self) -> None:
        self._rebalance_if_needed(source="prenext_open")

    def nextstart_open(self) -> None:
        self._rebalance_if_needed(source="nextstart_open")

    def next_open(self) -> None:
        self._rebalance_if_needed(source="next_open")

    def next(self) -> None:
        if self.allow_next_fallback:
            self._rebalance_if_needed(source="next_fallback")

        current_date = self.datas[0].datetime.date(0)

        if self.record_start_date is not None and current_date < self.record_start_date:
            return

        if self.record_end_date is not None and current_date > self.record_end_date:
            return

        holding_count = 0
        gross_exposure_value = 0.0

        for data in self.datas:
            position = self.getposition(data)
            if position.size != 0:
                holding_count += 1
                gross_exposure_value += abs(position.size * data.close[0])

        portfolio_value = float(self.broker.getvalue())
        cash = float(self.broker.getcash())

        self.daily_records.append(
            {
                "trade_date": current_date.isoformat(),
                "portfolio_equity": portfolio_value,
                "cash": cash,
                "holding_count": holding_count,
                "gross_exposure": gross_exposure_value,
            }
        )

    def _rebalance_if_needed(self, *, source: str) -> None:
        if not self.datas:
            return

        current_date = self.datas[0].datetime.date(0)

        if current_date in self._executed_rebalance_dates:
            return

        if current_date not in self.target_weights_by_date:
            return

        target_weights = self.target_weights_by_date[current_date]
        submitted_count = 0

        for data in self.datas:
            instrument_id = int(data._name)
            target_weight = float(target_weights.get(instrument_id, 0.0))

            if target_weight <= 0:
                continue

            self.order_target_percent(data=data, target=target_weight)
            submitted_count += 1

        self._executed_rebalance_dates.add(current_date)

        self.rebalance_records.append(
            {
                "trade_date": current_date.isoformat(),
                "source": source,
                "submitted_count": submitted_count,
                "target_count": len(target_weights),
                "allow_next_fallback": self.allow_next_fallback,
            }
        )

    def notify_order(self, order: bt.Order) -> None:
        if order.status not in [
            order.Submitted,
            order.Accepted,
            order.Completed,
            order.Canceled,
            order.Margin,
            order.Rejected,
        ]:
            return

        status_name = order.getstatusname()
        data_name = getattr(order.data, "_name", None)

        record: dict[str, Any] = {
            "trade_date": self.datas[0].datetime.date(0).isoformat(),
            "instrument_id": int(data_name) if data_name is not None else None,
            "status": status_name,
            "is_buy": bool(order.isbuy()),
            "created_size": float(order.created.size)
            if order.created is not None
            else None,
            "executed_size": float(order.executed.size)
            if order.executed is not None
            else None,
            "executed_price": float(order.executed.price)
            if order.executed is not None
            else None,
            "executed_value": float(order.executed.value)
            if order.executed is not None
            else None,
            "executed_commission": float(order.executed.comm)
            if order.executed is not None
            else None,
        }

        self.order_records.append(record)