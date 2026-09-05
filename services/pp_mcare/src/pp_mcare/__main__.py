from __future__ import annotations

import logging
import signal
import sys
from functools import partial

from .api_client import MotionCareClient
from .config import ConfigurationError, Settings
from .safe_logging import configure_safe_logging
from .storage import configure_storage_logging
from .worker import process_claimed_job, run_worker
from .workspace import CleanupSummary, cleanup_stale_workspaces


_logger = logging.getLogger(__name__)


class GracefulShutdown(SystemExit):
    pass


def _handle_shutdown_signal(_signum, _frame) -> None:
    raise GracefulShutdown(0)


def main() -> int:
    try:
        settings = Settings.from_env()
    except ConfigurationError:
        sys.stderr.write("pp-mcare 配置无效，拒绝启动\n")
        return 2

    configure_safe_logging(secrets=(settings.service_token,))
    configure_storage_logging((settings.service_token,))
    previous_handlers = {
        signum: signal.getsignal(signum) for signum in (signal.SIGTERM, signal.SIGINT)
    }
    for signum in previous_handlers:
        signal.signal(signum, _handle_shutdown_signal)
    try:
        cleanup = cleanup_stale_workspaces(
            settings.work_root,
            max_age_seconds=14_400,
            limit=100,
        )
        if isinstance(cleanup, CleanupSummary):
            _logger.info(
                "motion_analysis_stale_cleanup",
                extra={
                    "outcome": "removed" if cleanup.removed else "retained",
                    "cleanup_scanned": cleanup.scanned,
                    "cleanup_removed": cleanup.removed,
                    "cleanup_failed": cleanup.failed,
                },
            )
        with MotionCareClient(settings) as client:
            run_worker(
                client=client,
                processor=partial(process_claimed_job, client=client, settings=settings),
                settings=settings,
            )
    except GracefulShutdown:
        return 0
    finally:
        for signum, handler in previous_handlers.items():
            signal.signal(signum, handler)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
