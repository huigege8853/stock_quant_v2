from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from stock_quant_v2.db.models.ops import OpsRunMetricSnapshot
from stock_quant_v2.research_domain.enums import DimensionType, MetricNamespace


class RunResultRepository:
    def __init__(self, session: Session):
        self.session = session

    def replace_screen_metrics(
        self,
        *,
        run_id: int,
        metrics: dict[str, Any],
    ) -> None:
        self.replace_metrics(
            run_id=run_id,
            metric_namespace=MetricNamespace.SCREEN.value,
            metrics=metrics,
        )

    def replace_backtest_metrics(
        self,
        *,
        run_id: int,
        metrics: dict[str, Any],
    ) -> None:
        self.replace_metrics(
            run_id=run_id,
            metric_namespace=MetricNamespace.BACKTEST.value,
            metrics=metrics,
        )

    def replace_metrics(
        self,
        *,
        run_id: int,
        metric_namespace: str,
        metrics: dict[str, Any],
    ) -> None:
        self.session.query(OpsRunMetricSnapshot).filter(
            OpsRunMetricSnapshot.run_id == run_id,
            OpsRunMetricSnapshot.metric_namespace == metric_namespace,
        ).delete(synchronize_session=False)

        rows = []
        sequence_no = 0

        for metric_code, value in metrics.items():
            if value is None:
                continue

            rows.append(
                OpsRunMetricSnapshot(
                    run_id=run_id,
                    metric_namespace=metric_namespace,
                    metric_code=metric_code,
                    metric_name=metric_code,
                    metric_value_numeric=self._to_decimal_or_none(value),
                    metric_value_text=None if self._is_numeric(value) else str(value),
                    metric_value_json=None,
                    unit=None,
                    dimension_type=DimensionType.PORTFOLIO.value,
                    dimension_key="ALL",
                    sequence_no=sequence_no,
                )
            )
            sequence_no += 1

        self.session.add_all(rows)
        self.session.flush()

    @staticmethod
    def _is_numeric(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return False
        return isinstance(value, (int, float, Decimal))

    @classmethod
    def _to_decimal_or_none(cls, value: Any) -> Decimal | None:
        if not cls._is_numeric(value):
            return None
        return Decimal(str(value))