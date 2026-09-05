from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence


_SAFE_PARSE_ERROR = (
    "用法: pp_mcare regression --video <路径> "
    "--manual-total-count 90 --report <路径>\n"
    "pp_mcare: 参数无效\n"
)


class _SafeArgumentParser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        self.exit(2, _SAFE_PARSE_ERROR)


def _parser() -> argparse.ArgumentParser:
    parser = _SafeArgumentParser(prog="pp_mcare")
    subcommands = parser.add_subparsers(dest="command", required=True)
    regression = subcommands.add_parser("regression")
    regression.add_argument("--video", required=True)
    regression.add_argument("--manual-total-count", required=True, type=int)
    regression.add_argument("--report", required=True, help="报告目标必须不存在（create-once）")
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
