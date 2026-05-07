import pytest

from apps.visits.models import VisitRecord
from apps.visits.services import ensure_default_visits


@pytest.mark.django_db
def test_ensure_default_visits_creates_t0_t1_t2(project_patient):
    ensure_default_visits(project_patient)

    assert list(
        VisitRecord.objects.filter(project_patient=project_patient)
        .order_by("visit_type")
        .values_list("visit_type", flat=True)
    ) == ["T0", "T1", "T2"]

