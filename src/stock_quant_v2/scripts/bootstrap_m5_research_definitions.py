from __future__ import annotations

from stock_quant_v2.db.session import SessionLocal
from stock_quant_v2.research_domain.tasks.seed_research_definitions import (
    seed_research_definitions,
)


def main() -> None:
    with SessionLocal() as session:
        result = seed_research_definitions(session, commit=True)

    print(result)


if __name__ == "__main__":
    main()