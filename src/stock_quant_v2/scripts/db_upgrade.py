from __future__ import annotations

import subprocess
import sys


def main() -> int:
    result = subprocess.run(["alembic", "upgrade", "head"], check=False)
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())