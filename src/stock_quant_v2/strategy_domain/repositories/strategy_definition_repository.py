from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from stock_quant_v2.db.models.strategy.strategy_definition import StrategyDefinition


class StrategyDefinitionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_code(self, strategy_code: str) -> StrategyDefinition | None:
        return self._session.execute(
            select(StrategyDefinition).where(StrategyDefinition.strategy_code == strategy_code)
        ).scalar_one_or_none()

    def create(
        self,
        *,
        strategy_code: str,
        strategy_name: str,
        strategy_type: str,
        engine_type: str,
        market_scope: str,
        bar_frequency: str,
        description: str | None,
        lifecycle_status: str,
        owner: str,
        tags_json: list,
    ) -> StrategyDefinition:
        row = StrategyDefinition(
            strategy_code=strategy_code,
            strategy_name=strategy_name,
            strategy_type=strategy_type,
            engine_type=engine_type,
            market_scope=market_scope,
            bar_frequency=bar_frequency,
            description=description,
            lifecycle_status=lifecycle_status,
            owner=owner,
            tags_json=tags_json,
        )
        self._session.add(row)
        self._session.flush()
        return row