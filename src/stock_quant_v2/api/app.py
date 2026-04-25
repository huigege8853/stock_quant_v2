from __future__ import annotations

from fastapi import FastAPI

from stock_quant_v2.api.routers.m8_ops import router as m8_ops_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="stock_quant_v2 Ops API",
        description=(
            "M8 API for Run Monitor, Ops Query, Report Export, "
            "Scheduler Health and Human Review Pack."
        ),
        version="0.1.0",
    )

    @app.get("/health", tags=["health"])
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "stock_quant_v2_ops_api",
        }

    app.include_router(m8_ops_router)

    return app


app = create_app()