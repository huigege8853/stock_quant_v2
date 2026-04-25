from __future__ import annotations

from pathlib import Path


TARGET = Path("src/stock_quant_v2/scripts/bootstrap_m7_apply_risk_to_target.py")

OLD = 'run_type="PAPER_TARGET_POSITION_RISK_ADJUSTED",'
NEW = 'run_type="RISK_ADJ_TARGET",'

OLD_ALT = 'run_type = "PAPER_TARGET_POSITION_RISK_ADJUSTED"'
NEW_ALT = 'run_type = "RISK_ADJ_TARGET"'


def main() -> None:
    if not TARGET.exists():
        raise FileNotFoundError(f"not found: {TARGET}")

    text = TARGET.read_text(encoding="utf-8")

    changed = False
    if OLD in text:
        text = text.replace(OLD, NEW)
        changed = True
    if OLD_ALT in text:
        text = text.replace(OLD_ALT, NEW_ALT)
        changed = True

    # Defensive normalization: if a previous manual edit used this long literal
    # inside single quotes, shorten it too.
    text2 = text.replace(
        "'PAPER_TARGET_POSITION_RISK_ADJUSTED'",
        "'RISK_ADJ_TARGET'",
    ).replace(
        '"PAPER_TARGET_POSITION_RISK_ADJUSTED"',
        '"RISK_ADJ_TARGET"',
    )
    if text2 != text:
        text = text2
        changed = True

    if changed:
        TARGET.write_text(text, encoding="utf-8")
        print(f"[OK] patched run_type length in {TARGET}")
    else:
        print(f"[OK] no change needed; long run_type not found in {TARGET}")


if __name__ == "__main__":
    main()
