from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://stock:stock@100.97.197.40:54322/stock_quant_v2")

with engine.connect() as conn:
    rows = conn.execute(text("select table_name from information_schema.tables where table_schema='public' limit 10"))
    for row in rows:
        print(row)