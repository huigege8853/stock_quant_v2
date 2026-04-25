from __future__ import annotations

from sqlalchemy.orm import Session

from stock_quant_v2.research_domain.dto.screen import ScreenRequestDTO, ScreenResultDTO
from stock_quant_v2.research_domain.services.screen_service import ScreenService


def run_screen_first_chain(
    session: Session,
    dto: ScreenRequestDTO,
) -> ScreenResultDTO:
    return ScreenService(session).run_screen(dto)