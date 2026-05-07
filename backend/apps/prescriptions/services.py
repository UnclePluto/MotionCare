from django.db import transaction
from django.utils import timezone

from .models import Prescription


@transaction.atomic
def activate_prescription(prescription: Prescription, effective_at=None) -> Prescription:
    now = timezone.now()
    effective_at = effective_at or now
    Prescription.objects.filter(
        project_patient=prescription.project_patient,
        status=Prescription.Status.ACTIVE,
    ).exclude(id=prescription.id).update(status=Prescription.Status.ARCHIVED)

    prescription.effective_at = effective_at
    prescription.status = (
        Prescription.Status.ACTIVE if effective_at <= now else Prescription.Status.PENDING
    )
    prescription.save(update_fields=["effective_at", "status", "updated_at"])
    return prescription

