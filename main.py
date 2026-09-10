"""VelaGuard Host entry point."""

from __future__ import annotations

import sys


def main() -> int:
    try:
        from velaguard_host.app_window import run
    except ImportError as exc:
        print("缺少依赖，请先执行: pip install -r requirements.txt", file=sys.stderr)
        print(f"详情: {exc}", file=sys.stderr)
        return 1
    return run()


if __name__ == "__main__":
    sys.exit(main())
