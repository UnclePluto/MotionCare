import pytest
from rest_framework.test import APIClient

from apps.studies.models import GroupingBatch, ProjectPatient


@pytest.mark.django_db
def test_discard_grouping_draft_clears_batch_and_fields(doctor, project, patient, group):
    batch = GroupingBatch.objects.create(project=project, status=GroupingBatch.Status.PENDING)
    pp = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=group,
        grouping_batch=batch,
        grouping_status=ProjectPatient.GroupingStatus.PENDING,
    )
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/projects/{project.id}/discard-grouping-draft/", {}, format="json")
    assert r.status_code == 200
    assert not GroupingBatch.objects.filter(pk=batch.pk).exists()
    pp.refresh_from_db()
    assert pp.grouping_batch_id is None
    assert pp.group_id is None


@pytest.mark.django_db
def test_discard_grouping_draft_400_when_none(doctor, project):
    client = APIClient()
    client.force_authenticate(user=doctor)
    r = client.post(f"/api/studies/projects/{project.id}/discard-grouping-draft/", {}, format="json")
    assert r.status_code == 400
