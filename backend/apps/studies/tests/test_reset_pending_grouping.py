import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient, StudyGroup


@pytest.mark.django_db
def test_reset_pending_clears_pending_group_keeps_confirmed(doctor, project, patient):
    group_a = StudyGroup.objects.create(project=project, name="A", target_ratio=1)
    group_b = StudyGroup.objects.create(project=project, name="B", target_ratio=1)
    p_pending = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=group_a,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )
    other = Patient.objects.create(name="患者乙", phone="13900000222", primary_doctor=doctor)
    p_confirmed = ProjectPatient.objects.create(
        project=project,
        patient=other,
        group=group_b,
        grouping_status=ProjectPatient.GroupingStatus.CONFIRMED,
    )

    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/projects/{project.id}/reset-pending/", {}, format="json")

    assert r.status_code == 200
    p_pending.refresh_from_db()
    p_confirmed.refresh_from_db()
    assert p_pending.group_id is None
    assert p_pending.grouping_status == ProjectPatient.GroupingStatus.PENDING
    assert p_confirmed.group_id == group_b.id
    assert p_confirmed.grouping_status == ProjectPatient.GroupingStatus.CONFIRMED


@pytest.mark.django_db
def test_reset_pending_returns_200_when_no_pending(doctor, project):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/projects/{project.id}/reset-pending/", {}, format="json")

    assert r.status_code == 200
    assert r.data.get("affected") == 0
