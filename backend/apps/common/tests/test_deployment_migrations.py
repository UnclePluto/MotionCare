import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder


@pytest.mark.django_db
def test_deployment_rejects_database_migration_missing_from_candidate():
    MigrationRecorder(connection).record_applied("training", "9999_future_video_format")
    with pytest.raises(CommandError, match="training.9999_future_video_format"):
        call_command("check_deployment_migrations")


@pytest.mark.django_db
def test_deployment_accepts_current_schema():
    call_command("check_deployment_migrations")
