# Auto-generated dry-run preview only. Do not treat this file as applied source.

"""R64E15 selector contract loader preview."""

EXPECTED_CONTRACT_ID = "R64E15_DYNAMIC_SELECTOR_SAFETY_GATED_V0"
EXPECTED_CONTRACT_VERSION = "v0.preview"
EXPECTED_CONTRACT_SHA256 = "9ceaf3ed3386d1e53ceb7e41a21cf3b405d45cd05feb429a250dddf1f9522d81"


def validate_contract_metadata(contract):
    """Validate contract metadata. Returns (ok, reason)."""
    if not isinstance(contract, dict):
        return False, "CONTRACT_NOT_DICT"
    if contract.get("contract_id") != EXPECTED_CONTRACT_ID:
        return False, "CONTRACT_ID_MISMATCH"
    if contract.get("contract_version") != EXPECTED_CONTRACT_VERSION:
        return False, "CONTRACT_VERSION_MISMATCH"
    if contract.get("contract_sha256") not in (None, EXPECTED_CONTRACT_SHA256):
        return False, "CONTRACT_SHA256_MISMATCH"
    return True, "CONTRACT_METADATA_OK"
