-- M7.6 rerun cleanup SQL
-- psql usage:
-- \set portfolio_id 1
-- \i sql/m7_6_cleanup_rerun_artifacts.sql
--
-- Important: delete child tables before parent tables.

begin;

delete from trading_paper_portfolio_snapshot
where portfolio_id = :portfolio_id
  and run_id in (149, 154);

delete from trading_paper_trade_ledger
where portfolio_id = :portfolio_id
  and run_id in (145, 146, 147, 148, 149, 150, 151, 152, 153, 154);

delete from trading_paper_position
where portfolio_id = :portfolio_id
  and run_id in (145, 148, 150, 153);

-- Must delete fills before orders because fill.order_id references order.id.
delete from trading_paper_fill
where portfolio_id = :portfolio_id
  and run_id in (147, 152);

delete from trading_paper_order
where portfolio_id = :portfolio_id
  and run_id in (146, 151);

commit;
