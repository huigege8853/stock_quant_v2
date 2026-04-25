from __future__ import annotations

from stock_quant_v2.risk_domain.dto.risk import (
    ApplyRiskToTargetRequestDTO,
    ApplyRiskToTargetResultDTO,
)
from stock_quant_v2.risk_domain.services.risk_target_service import RiskTargetService


def apply_risk_to_target(session, request: ApplyRiskToTargetRequestDTO) -> ApplyRiskToTargetResultDTO:
    service = RiskTargetService(session)
    result = service.apply_risk_to_target(request)
    session.flush()
    return result
