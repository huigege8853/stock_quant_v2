from __future__ import annotations

from datetime import date

from stock_quant_v2.data_domain.providers.akshare.client import AkshareClient


def main() -> None:
    client = AkshareClient()

    samples = [
        ("SSE", "600000", date(2024, 1, 2)),
        ("SZSE", "000001", date(2024, 1, 2)),
        ("SSE", "600015", date(2024, 1, 2)),
    ]

    for exchange_code, ticker, trade_date in samples:
        print("=" * 80)
        print(f"probe: {exchange_code} {ticker} {trade_date.isoformat()}")
        try:
            rows = client.fetch_fundamental_snapshot_by_symbol(
                exchange_code=exchange_code,
                ticker=ticker,
                trade_date=trade_date,
            )
            print(f"row_count={len(rows)}")
            for row in rows[:3]:
                print(row)
        except Exception as exc:  # noqa: BLE001
            print(f"error={exc}")


if __name__ == "__main__":
    main()