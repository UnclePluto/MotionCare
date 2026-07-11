from unittest.mock import Mock

import pytest
from django.core.exceptions import ValidationError


def test_worker_startup_health_checks_binaries_and_staging(monkeypatch):
    from config import celery as celery_config

    check = Mock()
    monkeypatch.setattr(
        "apps.training.video_staging.validate_video_runtime_environment",
        check,
    )

    celery_config.TrainingVideoWorkerHealthCheck(None).start(None)

    check.assert_called_once_with(check_disk_space=False)


def test_worker_startup_health_failure_is_not_swallowed(monkeypatch):
    from config import celery as celery_config

    monkeypatch.setattr(
        "apps.training.video_staging.validate_video_runtime_environment",
        Mock(side_effect=ValidationError("FFprobe 不可用")),
    )

    with pytest.raises(ValidationError, match="FFprobe"):
        celery_config.TrainingVideoWorkerHealthCheck(None).start(None)


def test_worker_health_check_is_registered_as_worker_bootstep():
    from config import celery as celery_config

    assert celery_config.TrainingVideoWorkerHealthCheck in celery_config.app.steps["worker"]
