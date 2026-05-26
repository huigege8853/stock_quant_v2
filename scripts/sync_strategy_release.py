#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path


CACHE_DIR = Path("/app/strategy_release_cache")
ACTIVE_DIR = CACHE_DIR / "active"
ARCHIVE_DIR = CACHE_DIR / "archive"
ACTIVE_FILE = ACTIVE_DIR / "strategy_release.json"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))



def _release_identity(payload: dict) -> dict:
    params = payload.get("params") if isinstance(payload.get("params"), dict) else {}
    contract = payload.get("r63_fast_deploy_contract") if isinstance(payload.get("r63_fast_deploy_contract"), dict) else {}
    return {
        "strategy_code": payload.get("strategy_code"),
        "version_code": payload.get("version_code") or payload.get("strategy_version_code"),
        "parameter_version_id": (
            payload.get("parameter_version_id")
            or params.get("parameter_version_id")
            or contract.get("parameter_version_id")
        ),
        "policy_effective_hash": (
            payload.get("policy_effective_hash")
            or params.get("policy_effective_hash")
            or contract.get("policy_effective_hash")
        ),
        "release_profile": payload.get("release_profile") or params.get("release_profile"),
        "checksum": payload.get("checksum"),
    }


def main() -> int:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ACTIVE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    source_path = os.getenv("STRATEGY_RELEASE_LOCAL_FILE", "").strip()
    if not source_path:
        raise RuntimeError("STRATEGY_RELEASE_LOCAL_FILE is empty")

    src = Path(source_path)
    if not src.exists():
        if ACTIVE_FILE.exists():
            print(json.dumps({"status": "NO_SOURCE_USE_ACTIVE"}))
            return 0
        raise FileNotFoundError(f"strategy release source not found: {src}")

    payload = _load_json(src)

    required = ["strategy_code", "version_code", "release_date", "effective_from"]
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise RuntimeError(f"strategy release missing keys: {missing}")

    current = {}
    if ACTIVE_FILE.exists():
        try:
            current = _load_json(ACTIVE_FILE)
        except Exception:
            current = {}

    current_identity = _release_identity(current)
    payload_identity = _release_identity(payload)

    if current_identity == payload_identity:
        print(json.dumps({
            "status": "NO_CHANGE",
            "strategy_code": payload["strategy_code"],
            "version_code": payload["version_code"],
            "release_identity": payload_identity,
        }, ensure_ascii=False))
        return 0

    if ACTIVE_FILE.exists():
        archive_name = f"{current.get('strategy_code','unknown')}__{current.get('version_code','unknown')}.json"
        shutil.copy2(ACTIVE_FILE, ARCHIVE_DIR / archive_name)

    ACTIVE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "status": "UPDATED",
        "strategy_code": payload["strategy_code"],
        "version_code": payload["version_code"],
        "active_file": str(ACTIVE_FILE),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())