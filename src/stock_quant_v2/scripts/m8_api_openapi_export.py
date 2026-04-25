from __future__ import annotations

import json
import os
from pathlib import Path

from stock_quant_v2.api.app import create_app


def main() -> None:
    output_dir = Path(os.getenv("M8_API_DOC_OUTPUT_DIR", "artifacts/m8/api"))
    output_dir.mkdir(parents=True, exist_ok=True)

    app = create_app()
    schema = app.openapi()

    json_path = output_dir / "m8_openapi.json"
    md_path = output_dir / "m8_api_endpoints.md"

    json_path.write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )

    paths = schema.get("paths", {})
    lines = [
        "# M8 API Endpoints",
        "",
        "Generated from FastAPI OpenAPI schema.",
        "",
        "## Endpoints",
        "",
    ]

    for path, methods in sorted(paths.items()):
        for method, spec in sorted(methods.items()):
            lines.append(
                f"- `{method.upper():<6}` `{path}` - {spec.get('summary') or spec.get('operationId')}"
            )

    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "module": "M8.8",
                "query": "m8_api_openapi_export",
                "files": {
                    "openapi_json": str(json_path),
                    "endpoints_markdown": str(md_path),
                },
                "path_count": len(paths),
                "overall_status": "PASS",
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()