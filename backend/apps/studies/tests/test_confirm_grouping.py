import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _patient(doctor, name="患者乙", phone="13900000222"):
    return Patient.objects.create(name=name, phone=phone, primary_doctor=doctor)


def _missing_id(model):
    current_max_id = model.objects.order_by("-id").values_list("id", flat=True).first() or 0
    return current_max_id + 1000


@pytest.mark.django_db
@pytest.mark.parametrize(
    "payload_factory",
    [
        pytest.param(lambda patient, group: {}, id="missing_assignments"),
        pytest.param(lambda patient, group: {"assignments": "bad"}, id="assignments_not_list"),
        pytest.param(lambda patient, group: {"assignments": []}, id="empty_assignments"),
        pytest.param(
            lambda patient, group: {
                "assignments": [
                    {"patient_id": patient.id},
                ]
            },
            id="missing_group_id",
        ),
        pytest.param(
            lambda patient, group: {
                "assignments": [
                    {"group_id": group.id},
                ]
            },
            id="missing_patient_id",
        ),
        pytest.param(
            lambda patient, group: {
                "assignments": [
                    {"patient_id": "bad", "group_id": group.id},
                ]
            },
            id="patient_id_not_integer",
        ),
        pytest.param(
            lambda patient, group: {
                "assignments": [
                    {"patient_id": patient.id, "group_id": "bad"},
                ]
            },
            id="group_id_not_integer",
        ),
    ],
)
def test_confirm_grouping_rejects_invalid_assignment_payload_structure(
    doctor,
    project,
    patient,
    payload_factory,
):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        payload_factory(patient, group),
        format="json",
    )

    assert r.status_code == 400
    assert "assignments" in r.data
    assert not ProjectPatient.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_confirm_grouping_creates_project_patients_from_assignments(doctor, project):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=1)
    p1 = _patient(doctor, "甲", "13900000001")
    p2 = _patient(doctor, "乙", "13900000002")

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": p1.id, "group_id": g1.id},
                {"patient_id": p2.id, "group_id": g2.id},
            ]
        },
        format="json",
    )

    assert r.status_code == 200, r.data
    assert r.data["confirmed"] == 2
    assert ProjectPatient.objects.filter(project=project).count() == 2
    assert ProjectPatient.objects.get(project=project, patient=p1).group_id == g1.id
    assert ProjectPatient.objects.get(project=project, patient=p2).group_id == g2.id


@pytest.mark.django_db
def test_confirm_grouping_rejects_patient_already_in_project(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    ProjectPatient.objects.create(project=project, patient=patient, group=group)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": patient.id, "group_id": group.id},
            ]
        },
        format="json",
    )

    assert r.status_code == 400
    assert "已确认入组" in str(r.data)
    assert ProjectPatient.objects.filter(project=project, patient=patient).count() == 1


@pytest.mark.django_db
def test_confirm_grouping_rejects_group_from_other_project(doctor, project, patient):
    other = StudyProject.objects.create(name="其他项目", created_by=doctor)
    other_group = StudyGroup.objects.create(project=other, name="其他组", target_ratio=1)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": patient.id, "group_id": other_group.id},
            ]
        },
        format="json",
    )

    assert r.status_code == 400
    assert "分组不属于当前项目" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_confirm_grouping_rejects_inactive_group(doctor, project, patient):
    group = StudyGroup.objects.create(project=project, name="停用组", target_ratio=1, is_active=False)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": patient.id, "group_id": group.id},
            ]
        },
        format="json",
    )

    assert r.status_code == 400
    assert "分组已停用" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_confirm_grouping_rejects_unknown_patient(doctor, project):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    missing_patient_id = _missing_id(Patient)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": missing_patient_id, "group_id": group.id},
            ]
        },
        format="json",
    )

    assert r.status_code == 400
    assert "以下患者不存在" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_confirm_grouping_rejects_unknown_group(doctor, project, patient):
    missing_group_id = _missing_id(StudyGroup)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": patient.id, "group_id": missing_group_id},
            ]
        },
        format="json",
    )

    assert r.status_code == 400
    assert "以下分组不存在" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()


@pytest.mark.django_db
def test_confirm_grouping_rejects_payload_atomically_when_one_assignment_invalid(doctor, project):
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    p1 = _patient(doctor, "甲", "13900000001")
    p2 = _patient(doctor, "乙", "13900000002")
    missing_group_id = _missing_id(StudyGroup)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": p1.id, "group_id": group.id},
                {"patient_id": p2.id, "group_id": missing_group_id},
            ]
        },
        format="json",
    )

    assert r.status_code == 400
    assert "以下分组不存在" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project).exists()


@pytest.mark.django_db
def test_confirm_grouping_rejects_duplicate_patient_in_payload(doctor, project, patient):
    g1 = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    g2 = StudyGroup.objects.create(project=project, name="对照组", target_ratio=1)

    r = _client(doctor).post(
        f"/api/studies/projects/{project.id}/confirm-grouping/",
        {
            "assignments": [
                {"patient_id": patient.id, "group_id": g1.id},
                {"patient_id": patient.id, "group_id": g2.id},
            ]
        },
        format="json",
    )

    assert r.status_code == 400
    assert "重复患者" in str(r.data)
    assert not ProjectPatient.objects.filter(project=project, patient=patient).exists()
