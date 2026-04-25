from stock_quant_v2.data_domain.providers.tushare.builder import build_tushare_api_client


def main():
    client = build_tushare_api_client()
    df = client.trade_cal(exchange="SSE", start_date="20240101", end_date="20240110")
    records = df.to_dict("records") if hasattr(df, "to_dict") else list(df)
    print("records:", len(records))
    print(records[:3])


if __name__ == "__main__":
    main()