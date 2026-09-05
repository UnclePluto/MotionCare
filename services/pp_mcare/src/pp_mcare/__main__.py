from __future__ import annotations

import logging

from motion_analysis_contract import ClaimedJob

from .api_client import MotionCareClient
from .config import Settings
from .worker import run_worker


def _processor_pending_task_11(_job: ClaimedJob) -> None:
    """Task 11 会用完整单任务执行器替换此 fail-safe 边界。"""
    raise RuntimeError("任务执行器尚未接入")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = Settings.from_env()
    with MotionCareClient(settings) as client:
        run_worker(
            client=client,
            processor=_processor_pending_task_11,
            settings=settings,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
