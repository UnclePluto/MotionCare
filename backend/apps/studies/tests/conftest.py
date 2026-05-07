import pytest

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


@pytest.fixture
def doctor(db):
    return User.objects.create_user(
        phone="13800001111",
        password="pass123456",
        name="测试医生",
        role=User.Role.DOCTOR,
    )


@pytest.fixture
def patient(db, doctor):
    return Patient.objects.create(
        name="患者甲",
        gender=Patient.Gender.MALE,
        age=70,
        phone="13900001111",
        primary_doctor=doctor,
    )


@pytest.fixture
def project(db, doctor):
    return StudyProject.objects.create(name="认知衰弱研究", created_by=doctor)


@pytest.fixture
def group(db, project):
    return StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)


@pytest.fixture
def project_patient(db, project, patient, group):
    return ProjectPatient.objects.create(project=project, patient=patient, group=group)

