from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pp_mcare")
    subcommands = parser.add_subparsers(dest="command", required=True)
    regression = subcommands.add_parser("regression")
    regression.add_argument("--video", required=True)
    regression.add_argument("--manual-total-count", required=True, type=int)
    regression.add_argument("--report", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
        if arguments.manual_total_count != 90:
            parser.error("--manual-total-count 必须为 90")
    except SystemExit as exc:
        return int(exc.code)

    from .regression import RegressionFailure, run_regression

    try:
        run_regression(
            video_path=arguments.video,
            manual_total_count=arguments.manual_total_count,
            report_path=arguments.report,
        )
    except RegressionFailure:
        sys.stderr.write("pp-mcare 回归失败，详情见脱敏报告\n")
        return 1
    return 0
