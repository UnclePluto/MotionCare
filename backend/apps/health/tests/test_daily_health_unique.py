import importlib
from types import SimpleNamespace

import pytest
from django.db import migrations
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_manual_health_api_is_removed(doctor, patient):
    client = APIClient()
    client.force_authenticate(doctor)

    response = client.post(
        "/api/health/",
        {
            "patient": patient.id,
            "record_date": "2026-07-22",
            "steps": 1000,
        },
        format="json",
    )

    assert response.status_code == 404


def _delete_migration():
    try:
        return importlib.import_module("apps.health.migrations.0002_delete_dailyhealthrecord")
    except ModuleNotFoundError:
        return None


def test_delete_migration_allows_empty_manual_health_table():
    migration = _delete_migration()
    assert migration is not None, "缺少删除手工健康数据的 migration"

    records = SimpleNamespace(objects=SimpleNamespace(exists=lambda: False))
    apps = SimpleNamespace(get_model=lambda app_label, model_name: records)

    migration.assert_no_manual_health_records(apps, schema_editor=None)


def test_delete_migration_blocks_when_manual_health_data_exists():
    migration = _delete_migration()
    assert migration is not None, "缺少删除手工健康数据的 migration"

    records = SimpleNamespace(objects=SimpleNamespace(exists=lambda: True))
    apps = SimpleNamespace(get_model=lambda app_label, model_name: records)

    with pytest.raises(
        RuntimeError,
        match="检测到手工健康数据，停止删除；请先确认归档策略",
    ):
        migration.assert_no_manual_health_records(apps, schema_editor=None)


def test_delete_migration_checks_data_before_deleting_model():
    migration = _delete_migration()
    assert migration is not None, "缺少删除手工健康数据的 migration"

    operations = migration.Migration.operations

    assert len(operations) == 2
    assert isinstance(operations[0], migrations.RunPython)
    assert operations[0].code is migration.assert_no_manual_health_records
    assert operations[0].reverse_code is migrations.RunPython.noop
    assert isinstance(operations[1], migrations.DeleteModel)
    assert operations[1].name == "DailyHealthRecord"
