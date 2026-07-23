import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient
from apps.wearables.models import WearableDevice


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def wearable_device(db):
    return WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        model="TEST-MODEL",
        short_code="0826",
    )


@pytest.fixture
def other_project_patient(db, doctor, project, group):
    other_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.UNKNOWN,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    return ProjectPatient.objects.create(
        project=project,
        patient=other_patient,
        group=group,
    )
