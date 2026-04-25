# M7 Schema

## 复用 M6 表

M7 继续复用：

- trading_paper_target_position
- trading_paper_order
- trading_paper_fill
- trading_paper_position
- trading_paper_portfolio_snapshot
- ops_run

## M7 新增迁移

alembic/versions/m7_0001_snap_ext.py

## trading_paper_portfolio_snapshot 扩展字段

- previous_snapshot_run_id bigint
- position_run_id bigint
- fill_run_id bigint
- previous_cash_balance numeric(28, 8)
- cash_delta numeric(28, 8)
- total_cost numeric(28, 8)
- unrealized_pnl numeric(28, 8)
- realized_pnl numeric(28, 8)
- open_position_count integer
- closed_position_count integer

## 关键 run

- carry source position run: 114
- carry target position run: 116
- order run: 141
- fill run: 142
- position after fill run: 143
- snapshot run: 144
