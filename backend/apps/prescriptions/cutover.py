from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.studies.models import ProjectPatient, StudyProject
from apps.training.history import preview_legacy_training, invalidate_legacy_training
from .doses import COUNTED_MOTION_KEYS, count_unit_for
from .models import Prescription, PrescriptionAction, MotionPrescriptionCutover


def preview_cutover(pp):
    active = Prescription.objects.filter(project_patient=pp, status="active").first()
    affected = bool(
        active
        and pp.project.status != StudyProject.Status.ARCHIVED
        and active.actions.filter(
            action_library_item__source_key__in=COUNTED_MOTION_KEYS,
            dose_mode="duration",
        ).exists()
    )
    return {**preview_legacy_training(pp), "new_prescription_version": affected}


@transaction.atomic
def cutover_patient(project_patient_id):
    pp = (
        ProjectPatient.objects.select_for_update()
        .select_related("project")
        .get(pk=project_patient_id)
    )
    project = StudyProject.objects.select_for_update().get(pk=pp.project_id)
    prescriptions = Prescription.objects.select_for_update().filter(project_patient=pp)
    active = prescriptions.filter(status="active").order_by("-version").first()
    marker, _ = MotionPrescriptionCutover.objects.get_or_create(project_patient=pp)
    result = {"project_patient": pp.id, "new_prescription_version": False}
    if (
        active
        and project.status != StudyProject.Status.ARCHIVED
        and active.actions.filter(
            dose_mode="duration",
            action_library_item__source_key__in=COUNTED_MOTION_KEYS,
        ).exists()
    ):
        now = timezone.now()
        active.status, active.archived_at = Prescription.Status.ARCHIVED, now
        active.save(update_fields=["status", "archived_at", "updated_at"])
        updated = Prescription.objects.create(
            project_patient=pp,
            version=(prescriptions.aggregate(v=Max("version"))["v"] or 0) + 1,
            opened_by=active.opened_by,
            effective_at=now,
            status="active",
            note=active.note,
            migration_source="counted_motion_v1",
        )
        for old in active.actions.select_related("action_library_item").order_by(
            "sort_order", "id"
        ):
            values = {
                field.attname: getattr(old, field.attname)
                for field in PrescriptionAction._meta.concrete_fields
                if not field.primary_key
                and field.name
                not in {
                    "prescription",
                    "created_at",
                    "updated_at",
                    "created_by",
                    "updated_by",
                    "migrated_from",
                }
            }
            key = old.action_library_item.source_key
            if key in COUNTED_MOTION_KEYS:
                values.update(
                    dose_mode="sets",
                    repetitions=10,
                    sets=3,
                    count_unit=count_unit_for(key),
                    duration_minutes=None,
                )
            else:
                values["migrated_from_id"] = old.id
            PrescriptionAction.objects.create(prescription=updated, **values)
        result["new_prescription_version"] = updated.version
    result.update(invalidate_legacy_training(pp))
    return result
