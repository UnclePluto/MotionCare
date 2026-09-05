from __future__ import annotations

import sys

from .config import Settings


def main() -> int:
    Settings.from_env()
    sys.stderr.write("pp-mcare 执行器尚未接入，拒绝启动\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
