from apps.visits.models import VisitRecord


DEFAULT_VISIT_TYPES = ["T0", "T1", "T2"]


def ensure_default_visits(project_patient) -> None:
    for visit_type in DEFAULT_VISIT_TYPES:
        VisitRecord.objects.get_or_create(
            project_patient=project_patient,
            visit_type=visit_type,
            defaults={"form_data": {}},
        )

