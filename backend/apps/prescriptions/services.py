from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.studies.models import ProjectPatient, StudyProject
from apps.studies.project_status import ensure_project_open

from .models import Prescription

STALE_ACTIVE_VERSION_DETAIL = "当前处方已变化，请刷新后重试。"
PROJECT_COMPLETED_PRESCRIPTION_DETAIL = "项目已完结，不能调整处方。"


def lock_open_project_patient_for_prescription(project_patient_id) -> ProjectPatient:
    project_patient = (
        ProjectPatient.objects.select_for_update(of=("self",))
        .select_related("project")
        .get(pk=project_patient_id)
    )
    project = StudyProject.objects.select_for_update(of=("self",)).get(
        pk=project_patient.project_id
    )
    ensure_project_open(project, PROJECT_COMPLETED_PRESCRIPTION_DETAIL)
    project_patient.project = project
    return project_patient


@transaction.atomic
def activate_prescription(prescription: Prescription, effective_at=None) -> Prescription:
    locked_project_patient = None
    if prescription.project_patient_id:
        locked_project_patient = lock_open_project_patient_for_prescription(
            prescription.project_patient_id
        )
        prescription = Prescription.objects.select_for_update(of=("self",)).get(
            pk=prescription.pk
        )
    else:
        prescription = Prescription.objects.select_for_update(of=("self",)).get(
            pk=prescription.pk
        )

    now = timezone.now()
    effective_at = effective_at or now
    Prescription.objects.filter(
        project_patient=locked_project_patient or prescription.project_patient,
        status=Prescription.Status.ACTIVE,
    ).exclude(id=prescription.id).update(status=Prescription.Status.ARCHIVED)

    prescription.effective_at = effective_at
    prescription.status = (
        Prescription.Status.ACTIVE if effective_at <= now else Prescription.Status.PENDING
    )
    prescription.save(update_fields=["effective_at", "status", "updated_at"])
    return prescription


@transaction.atomic
def create_active_prescription_now(
    project_patient: ProjectPatient,
    opened_by,
    actions,
    expected_active_version=None,
    note="",
) -> Prescription:
    note = note or ""
    locked_project_patient = lock_open_project_patient_for_prescription(
        project_patient.pk
    )
    prescriptions = Prescription.objects.select_for_update(of=("self",)).filter(
        project_patient=locked_project_patient
    )
    active_prescription = (
        prescriptions.filter(status=Prescription.Status.ACTIVE).order_by("-version", "-id").first()
    )
    active_version = active_prescription.version if active_prescription else None
    if active_version != expected_active_version:
        raise ValidationError(STALE_ACTIVE_VERSION_DETAIL)

    next_version = (prescriptions.aggregate(max_version=Max("version"))["max_version"] or 0) + 1
    now = timezone.now()
    prescriptions.filter(status=Prescription.Status.ACTIVE).update(
        status=Prescription.Status.ARCHIVED,
        updated_at=now,
    )

    prescription = Prescription.objects.create(
        project_patient=locked_project_patient,
        version=next_version,
        opened_by=opened_by,
        effective_at=now,
        status=Prescription.Status.ACTIVE,
        note=note,
    )
    for action_data in actions:
        action = action_data["action_library_item"]
        prescription.add_action_snapshot(
            action,
            weekly_frequency=action_data.get("weekly_frequency", ""),
            duration_minutes=action_data.get("duration_minutes"),
            sets=action_data.get("sets"),
            repetitions=action_data.get("repetitions"),
            difficulty=action_data.get("difficulty", ""),
            notes=action_data.get("notes", ""),
            sort_order=action_data.get("sort_order", 0),
        )
    return prescription
