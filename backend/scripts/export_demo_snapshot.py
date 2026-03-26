#!/usr/bin/env python3
"""
Export a sanitized demo snapshot from a real analysis run.

Usage:
  python3 scripts/export_demo_snapshot.py --conflict "Yemen"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from services.demo_snapshot_export import OUTPUT_PATH, export_demo_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Export sanitized demo snapshot from latest analysis.")
    parser.add_argument("--conflict", default="Yemen", help="Conflict key used in /api/analyze/latest")
    parser.add_argument("--timeout", type=int, default=45, help="HTTP timeout in seconds")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Backend base URL")
    parser.add_argument("--output", default=str(OUTPUT_PATH), help="Output JSON path")
    args = parser.parse_args()

    res = export_demo_snapshot(
        conflict=args.conflict,
        timeout=args.timeout,
        output_path=Path(args.output),
        base_url=args.base_url,
    )
    print(f"Exported sanitized snapshot to {res['output_path']}")
    print(f"Agent rows: {res['agent_rows']}")


if __name__ == "__main__":
    main()
