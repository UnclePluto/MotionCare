import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup


def _make_patient(doctor, name, phone):
    return Patient.objects.create(name=name, phone=phone, primary_doctor=doctor)


@pytest.mark.django_db
def test_randomize_creates_pending_for_pool_patients(doctor, project):
    StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    StudyGroup.objects.create(project=project, name="B", target_ratio=1)
    p1 = _make_patient(doctor, "甲", "13900000001")
    p2 = _make_patient(doctor, "乙", "13900000002")

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/studies/projects/{project.id}/randomize/",
        {"pool_patient_ids": [p1.id, p2.id], "seed": 1},
        format="json",
    )

    assert r.status_code == 200, r.data
    assignments = r.data["assignments"]
    assert len(assignments) == 2
    pps = ProjectPatient.objects.filter(project=project)
    assert pps.count() == 2
    for pp in pps:
        assert pp.grouping_status == ProjectPatient.GroupingStatus.PENDING
        assert pp.group_id is not None


@pytest.mark.django_db
def test_randomize_includes_existing_pending_and_keeps_confirmed_intact(doctor, project):
    g_a = StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    g_b = StudyGroup.objects.create(project=project, name="B", target_ratio=1)
    p_pending = _make_patient(doctor, "已 pending", "13900000010")
    pp_pending = ProjectPatient.objects.create(
        project=project,
        patient=p_pending,
        group=g_a,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )
    p_conf = _make_patient(doctor, "已确认", "13900000011")
    pp_confirmed = ProjectPatient.objects.create(
        project=project,
        patient=p_conf,
        group=g_b,
        grouping_status=ProjectPatient.GroupingStatus.CONFIRMED,
    )
    p_new1 = _make_patient(doctor, "新 1", "13900000012")
    p_new2 = _make_patient(doctor, "新 2", "13900000013")
    p_new3 = _make_patient(doctor, "新 3", "13900000014")

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/studies/projects/{project.id}/randomize/",
        {"pool_patient_ids": [p_new1.id, p_new2.id, p_new3.id], "seed": 42},
        format="json",
    )

    assert r.status_code == 200, r.data
    pp_confirmed.refresh_from_db()
    assert pp_confirmed.group_id == g_b.id
    assert pp_confirmed.grouping_status == ProjectPatient.GroupingStatus.CONFIRMED

    pending_after = ProjectPatient.objects.filter(
        project=project, grouping_status=ProjectPatient.GroupingStatus.PENDING
    )
    assert pending_after.count() == 4
    for pp in pending_after:
        assert pp.group_id in {g_a.id, g_b.id}

    assert {a["project_patient_id"] for a in r.data["assignments"]} == set(
        pending_after.values_list("id", flat=True)
    )


@pytest.mark.django_db
def test_randomize_empty_pool_reshuffles_existing_pending(doctor, project):
    StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    StudyGroup.objects.create(project=project, name="B", target_ratio=1)
    p1 = _make_patient(doctor, "甲", "13900000020")
    p2 = _make_patient(doctor, "乙", "13900000021")
    ProjectPatient.objects.create(
        project=project,
        patient=p1,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )
    ProjectPatient.objects.create(
        project=project,
        patient=p2,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/studies/projects/{project.id}/randomize/",
        {"pool_patient_ids": [], "seed": 7},
        format="json",
    )

    assert r.status_code == 200, r.data
    pps = ProjectPatient.objects.filter(project=project)
    assert all(pp.group_id is not None for pp in pps)
    assert len(r.data["assignments"]) == 2


@pytest.mark.django_db
def test_randomize_rejects_when_no_groups(doctor, project):
    p = _make_patient(doctor, "甲", "13900000030")
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/studies/projects/{project.id}/randomize/",
        {"pool_patient_ids": [p.id]},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_randomize_rejects_when_no_one_to_randomize(doctor, project):
    StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/studies/projects/{project.id}/randomize/",
        {"pool_patient_ids": []},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_randomize_rejects_unknown_patient_id(doctor, project):
    StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/studies/projects/{project.id}/randomize/",
        {"pool_patient_ids": [999999]},
        format="json",
    )
    assert r.status_code == 400


@pytest.mark.django_db
def test_randomize_skips_pool_patient_already_confirmed(doctor, project):
    g = StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    p_conf = _make_patient(doctor, "已确认", "13900000040")
    pp = ProjectPatient.objects.create(
        project=project,
        patient=p_conf,
        group=g,
        grouping_status=ProjectPatient.GroupingStatus.CONFIRMED,
    )
    p_new = _make_patient(doctor, "新", "13900000041")

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(
        f"/api/studies/projects/{project.id}/randomize/",
        {"pool_patient_ids": [p_conf.id, p_new.id]},
        format="json",
    )

    assert r.status_code == 200, r.data
    pp.refresh_from_db()
    assert pp.grouping_status == ProjectPatient.GroupingStatus.CONFIRMED
    pending = ProjectPatient.objects.filter(
        project=project, grouping_status=ProjectPatient.GroupingStatus.PENDING
    )
    assert pending.count() == 1
    assert pending.first().patient_id == p_new.id
