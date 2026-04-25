from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://stock:stock@100.97.197.40:54322/stock_quant_v2")

with engine.begin() as conn:
    conn.execute(text("create table if not exists tailscale_test(id int)"))
    conn.execute(text("insert into tailscale_test(id) values (1)"))
    print(conn.execute(text("select * from tailscale_test")).fetchall())