import os
from contextlib import contextmanager
from decimal import Decimal
from importlib import import_module
from typing import Iterator

from sqlalchemy import text
from sqlalchemy.orm import Session


@contextmanager
def _open_session() -> Iterator[Session]:
    db_session_module = import_module("stock_quant_v2.db.session")

    if hasattr(db_session_module, "SessionLocal"):
        session = db_session_module.SessionLocal()
    elif hasattr(db_session_module, "get_session"):
        maybe_session = db_session_module.get_session()
        if hasattr(maybe_session, "__enter__"):
            with maybe_session as session:
                yield session
                return
        session = maybe_session
    else:
        raise RuntimeError(
            "Cannot find SessionLocal or get_session in stock_quant_v2.db.session"
        )

    try:
        yield session
    finally:
        session.close()


def _get_env_int(name: str, default: int | None = None) -> int | None:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return int(value)


def _decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    return Decimal(str(value))


def _resolve_latest_position_snapshot_run_id(session: Session) -> int:
    run_id = session.execute(
        text(
            """
            select run_id
            from trading_paper_portfolio_snapshot
            order by run_id desc
            limit 1
            """
        )
    ).scalar_one_or_none()

    if run_id is None:
        raise ValueError("No trading_paper_portfolio_snapshot found.")

    return int(run_id)


def _get_context_int(session: Session, run_id: int, key: str) -> int | None:
    value = session.execute(
        text(
            """
            select context_json ->> :key
            from ops_run
            where id = :run_id
            """
        ),
        {
            "run_id": run_id,
            "key": key,
        },
    ).scalar_one_or_none()

    if value is None or value == "":
        return None

    return int(value)


def _resolve_run_chain(session: Session) -> dict[str, int]:
    position_snapshot_run_id = _get_env_int("M6_POSITION_SNAPSHOT_RUN_ID")
    if position_snapshot_run_id is None:
        position_snapshot_run_id = _resolve_latest_position_snapshot_run_id(session)

    fill_run_id = _get_env_int("M6_FILL_RUN_ID")
    if fill_run_id is None:
        fill_run_id = _get_context_int(
            session=session,
            run_id=position_snapshot_run_id,
            key="fill_run_id",
        )

    if fill_run_id is None:
        raise ValueError(
            "Cannot resolve fill_run_id. Set M6_FILL_RUN_ID or ensure "
            "ops_run.context_json of position snapshot run contains fill_run_id."
        )

    order_run_id = _get_env_int("M6_ORDER_RUN_ID")
    if order_run_id is None:
        order_run_id = _get_context_int(
            session=session,
            run_id=fill_run_id,
            key="order_run_id",
        )

    if order_run_id is None:
        raise ValueError(
            "Cannot resolve order_run_id. Set M6_ORDER_RUN_ID or ensure "
            "ops_run.context_json of fill run contains order_run_id."
        )

    target_run_id = _get_env_int("M6_TARGET_RUN_ID")
    if target_run_id is None:
        target_run_id = _get_context_int(
            session=session,
            run_id=order_run_id,
            key="target_run_id",
        )

    if target_run_id is None:
        raise ValueError(
            "Cannot resolve target_run_id. Set M6_TARGET_RUN_ID or ensure "
            "ops_run.context_json of order run contains target_run_id."
        )

    portfolio_id = _get_env_int("M6_PAPER_PORTFOLIO_ID")
    if portfolio_id is None:
        portfolio_id = _get_context_int(
            session=session,
            run_id=position_snapshot_run_id,
            key="portfolio_id",
        )

    if portfolio_id is None:
        portfolio_id = session.execute(
            text(
                """
                select portfolio_id
                from trading_paper_portfolio_snapshot
                where run_id = :run_id
                limit 1
                """
            ),
            {"run_id": position_snapshot_run_id},
        ).scalar_one()

    return {
        "target_run_id": int(target_run_id),
        "order_run_id": int(order_run_id),
        "fill_run_id": int(fill_run_id),
        "position_snapshot_run_id": int(position_snapshot_run_id),
        "portfolio_id": int(portfolio_id),
    }


def _single_value(session: Session, sql: str, params: dict) -> int:
    value = session.execute(text(sql), params).scalar_one()
    return int(value or 0)


def _status_counts(session: Session, sql: str, params: dict) -> dict[str, int]:
    rows = session.execute(text(sql), params).all()
    result: dict[str, int] = {}
    for status, cnt in rows:
        result[str(status)] = int(cnt)
    return result


def _run_checks(session: Session, chain: dict[str, int]) -> dict:
    target_run_id = chain["target_run_id"]
    order_run_id = chain["order_run_id"]
    fill_run_id = chain["fill_run_id"]
    position_snapshot_run_id = chain["position_snapshot_run_id"]
    portfolio_id = chain["portfolio_id"]

    checks: dict[str, bool] = {}

    target_count = _single_value(
        session,
        """
        select count(*)
        from trading_paper_target_position
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        """,
        {"run_id": target_run_id, "portfolio_id": portfolio_id},
    )

    target_status_counts = _status_counts(
        session,
        """
        select status, count(*)
        from trading_paper_target_position
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        group by status
        """,
        {"run_id": target_run_id, "portfolio_id": portfolio_id},
    )

    order_count = _single_value(
        session,
        """
        select count(*)
        from trading_paper_order
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        """,
        {"run_id": order_run_id, "portfolio_id": portfolio_id},
    )

    order_status_counts = _status_counts(
        session,
        """
        select status, count(*)
        from trading_paper_order
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        group by status
        """,
        {"run_id": order_run_id, "portfolio_id": portfolio_id},
    )

    fill_count = _single_value(
        session,
        """
        select count(*)
        from trading_paper_fill
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        """,
        {"run_id": fill_run_id, "portfolio_id": portfolio_id},
    )

    fill_status_counts = _status_counts(
        session,
        """
        select fill_status, count(*)
        from trading_paper_fill
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        group by fill_status
        """,
        {"run_id": fill_run_id, "portfolio_id": portfolio_id},
    )

    position_count = _single_value(
        session,
        """
        select count(*)
        from trading_paper_position
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        """,
        {"run_id": position_snapshot_run_id, "portfolio_id": portfolio_id},
    )

    position_status_counts = _status_counts(
        session,
        """
        select position_status, count(*)
        from trading_paper_position
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        group by position_status
        """,
        {"run_id": position_snapshot_run_id, "portfolio_id": portfolio_id},
    )

    snapshot_count = _single_value(
        session,
        """
        select count(*)
        from trading_paper_portfolio_snapshot
        where run_id = :run_id
          and portfolio_id = :portfolio_id
        """,
        {"run_id": position_snapshot_run_id, "portfolio_id": portfolio_id},
    )

    snapshot = session.execute(
        text(
            """
            select
                cash_balance,
                market_value,
                total_equity,
                holding_count
            from trading_paper_portfolio_snapshot
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            limit 1
            """
        ),
        {
            "run_id": position_snapshot_run_id,
            "portfolio_id": portfolio_id,
        },
    ).mappings().one_or_none()

    if snapshot is None:
        raise ValueError(
            f"No portfolio snapshot found for run_id={position_snapshot_run_id}, "
            f"portfolio_id={portfolio_id}"
        )

    cash_balance = _decimal(snapshot["cash_balance"])
    market_value = _decimal(snapshot["market_value"])
    total_equity = _decimal(snapshot["total_equity"])
    holding_count = int(snapshot["holding_count"])

    initial_cash = _decimal(
        session.execute(
            text(
                """
                select initial_cash
                from trading_paper_portfolio
                where id = :portfolio_id
                """
            ),
            {"portfolio_id": portfolio_id},
        ).scalar_one()
    )

    total_fill_cash_delta = _decimal(
        session.execute(
            text(
                """
                select coalesce(sum(cash_delta), 0)
                from trading_paper_fill
                where run_id = :fill_run_id
                  and portfolio_id = :portfolio_id
                  and fill_status = 'COMPLETED'
                """
            ),
            {
                "fill_run_id": fill_run_id,
                "portfolio_id": portfolio_id,
            },
        ).scalar_one()
    )

    expected_cash_balance = (initial_cash + total_fill_cash_delta).quantize(
        Decimal("0.00000001")
    )
    cash_diff = (cash_balance - expected_cash_balance).quantize(Decimal("0.00000001"))

    expected_total_equity = (cash_balance + market_value).quantize(
        Decimal("0.00000001")
    )
    equity_diff = (total_equity - expected_total_equity).quantize(
        Decimal("0.00000001")
    )

    signal_run_id = _get_context_int(
        session=session,
        run_id=target_run_id,
        key="source_signal_run_id",
    )

    if signal_run_id is None:
        signal_run_id = _single_value(
            session,
            """
            select min(source_signal_run_id)
            from trading_paper_target_position
            where run_id = :run_id
              and portfolio_id = :portfolio_id
            """,
            {"run_id": target_run_id, "portfolio_id": portfolio_id},
        )

    signal_count = _single_value(
        session,
        """
        select count(*)
        from strategy_signal
        where run_id = :signal_run_id
        """,
        {"signal_run_id": signal_run_id},
    )

    linked_signal_count = _single_value(
        session,
        """
        select count(*)
        from trading_paper_target_position t
        join strategy_signal s
          on s.id = t.strategy_signal_id
        where t.run_id = :target_run_id
          and t.portfolio_id = :portfolio_id
          and t.source_signal_run_id = :signal_run_id
          and s.run_id = :signal_run_id
        """,
        {
            "target_run_id": target_run_id,
            "portfolio_id": portfolio_id,
            "signal_run_id": signal_run_id,
        },
    )

    rank_out_of_scope_count = _single_value(
        session,
        """
        select count(*)
        from trading_paper_target_position t
        join strategy_signal s
          on s.id = t.strategy_signal_id
        where t.run_id = :target_run_id
          and t.portfolio_id = :portfolio_id
          and t.source_signal_run_id = :signal_run_id
          and s.run_id = :signal_run_id
          and (s.rank_in_batch is null or s.rank_in_batch > :target_count)
        """,
        {
            "target_run_id": target_run_id,
            "portfolio_id": portfolio_id,
            "signal_run_id": signal_run_id,
            "target_count": target_count,
        },
    )

    max_selected_source_rank = _single_value(
        session,
        """
        select coalesce(max(s.rank_in_batch), 0)
        from trading_paper_target_position t
        join strategy_signal s
          on s.id = t.strategy_signal_id
        where t.run_id = :target_run_id
          and t.portfolio_id = :portfolio_id
          and t.source_signal_run_id = :signal_run_id
          and s.run_id = :signal_run_id
        """,
        {
            "target_run_id": target_run_id,
            "portfolio_id": portfolio_id,
            "signal_run_id": signal_run_id,
        },
    )

    checks["target_count_check"] = target_count == 30
    checks["target_status_check"] = target_status_counts == {"ORDERED": 30}
    checks["order_count_check"] = order_count == 30
    checks["order_status_check"] = order_status_counts == {"FILLED": 30}
    checks["fill_count_check"] = fill_count == 30
    checks["fill_status_check"] = fill_status_counts == {"COMPLETED": 30}
    checks["position_count_check"] = position_count == 30
    checks["position_status_check"] = position_status_counts == {"OPEN": 30}
    checks["snapshot_count_check"] = snapshot_count == 1
    checks["holding_count_check"] = holding_count == position_count
    checks["cash_formula_check"] = cash_diff == Decimal("0.00000000")
    checks["equity_formula_check"] = equity_diff == Decimal("0.00000000")
    checks["cash_non_negative_check"] = cash_balance >= 0
    # New M4 v1.1 strategy signals may publish a larger candidate pool
    # (for example 100 rows) and then use a screen bridge to select 30 rows
    # for paper trading. Therefore the signal source check must verify source
    # existence and target linkage, not require strategy_signal rows == 30.
    checks["signal_source_exists_check"] = signal_count >= target_count
    checks["target_signal_link_check"] = linked_signal_count == target_count
    checks["target_signal_rank_scope_check"] = rank_out_of_scope_count == 0

    overall_status = "PASS" if all(checks.values()) else "FAIL"

    return {
        "overall_status": overall_status,
        "chain": chain,
        "counts": {
            "target_count": target_count,
            "order_count": order_count,
            "fill_count": fill_count,
            "position_count": position_count,
            "snapshot_count": snapshot_count,
            "holding_count": holding_count,
            "source_signal_run_id": signal_run_id,
            "source_signal_count": signal_count,
            "target_signal_link_count": linked_signal_count,
            "target_signal_rank_out_of_scope_count": rank_out_of_scope_count,
            "max_selected_source_rank": max_selected_source_rank,
        },
        "status_counts": {
            "target": target_status_counts,
            "order": order_status_counts,
            "fill": fill_status_counts,
            "position": position_status_counts,
        },
        "cash_equity": {
            "initial_cash": str(initial_cash),
            "cash_balance": str(cash_balance),
            "expected_cash_balance": str(expected_cash_balance),
            "cash_diff": str(cash_diff),
            "market_value": str(market_value),
            "total_equity": str(total_equity),
            "expected_total_equity": str(expected_total_equity),
            "equity_diff": str(equity_diff),
        },
        "checks": checks,
    }


def main() -> None:
    with _open_session() as session:
        chain = _resolve_run_chain(session)
        result = _run_checks(session, chain)

    print(result)


if __name__ == "__main__":
    main()