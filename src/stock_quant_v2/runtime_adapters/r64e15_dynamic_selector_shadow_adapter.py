# Auto-generated dry-run preview only. Do not treat this file as applied source.

"""
R64E15 dynamic selector shadow adapter, no-op preview.

Boundary:
- Shadow diagnostics only.
- Production output is returned unchanged.
- No DB writes.
- No bridge / force-trade.
- No formal signal publishing.
- No static E15P repair rule solidification.
"""

CONTRACT_ID = "R64E15_DYNAMIC_SELECTOR_SAFETY_GATED_V0"
CONTRACT_VERSION = "v0.preview"
CONTRACT_SHA256 = "9ceaf3ed3386d1e53ceb7e41a21cf3b405d45cd05feb429a250dddf1f9522d81"
ADAPTER_MODE = "shadow_noop"


def evaluate_shadow_selector(signal_context, selector_contract=None):
    """Return shadow diagnostics without changing production signal_context.

    This function is deliberately side-effect free. It may be wired later behind
    an explicit shadow flag, but the production route must consume the original
    signal_context unchanged.
    """
    diagnostics = {
        "adapter_mode": ADAPTER_MODE,
        "contract_id": CONTRACT_ID,
        "contract_version": CONTRACT_VERSION,
        "contract_sha256": CONTRACT_SHA256,
        "production_effect": "NO_ROUTE_NO_SIGNAL_PUBLISH",
        "db_write": False,
        "bridge_force_trade": False,
        "formal_signal_publish": False,
        "trading_logic_changed": False,
        "fallback_policy": "BASELINE_ON_ANY_GATE_FAILURE_OR_MISSING_CONTRACT",
    }
    return signal_context, diagnostics
