from sqlalchemy import create_engine, text

engine = create_engine("postgresql+psycopg://stock:stock@100.97.197.40:54322/stock_quant_v2")

with engine.connect() as conn:
    print(conn.execute(text("select current_database(), inet_server_addr(), inet_server_port()")).fetchone())