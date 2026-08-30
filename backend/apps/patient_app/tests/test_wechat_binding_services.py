import pytest
from django.db import IntegrityError, transaction

from apps.patient_app.models import PatientAppWechatBinding
from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


def create_second_project_patient(doctor):
    patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.FEMALE,
        age=68,
        phone="13900009999",
        primary_doctor=doctor,
    )
    project = StudyProject.objects.create(name="微信绑定测试项目", created_by=doctor)
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    return ProjectPatient.objects.create(project=project, patient=patient, group=group)


@pytest.mark.django_db
def test_wechat_binding_is_unique_on_both_openid_and_project_patient(
    project_patient,
    doctor,
):
    second_project_patient = create_second_project_patient(doctor)
    PatientAppWechatBinding.objects.create(
        project_patient=project_patient,
        wx_openid="openid-001",
    )

    with pytest.raises(IntegrityError), transaction.atomic():
        PatientAppWechatBinding.objects.create(
            project_patient=second_project_patient,
            wx_openid="openid-001",
        )

    with pytest.raises(IntegrityError), transaction.atomic():
        PatientAppWechatBinding.objects.create(
            project_patient=project_patient,
            wx_openid="openid-002",
        )
