from django.db import models

from apps.common.models import UserStampedModel


class PatientAppBindingCode(UserStampedModel):
    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="patient_app_binding_codes",
    )
    code_hash = models.CharField(max_length=128, db_index=True)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["code_hash"],
                condition=models.Q(used_at__isnull=True, revoked_at__isnull=True),
                name="uniq_active_patient_app_binding_code_hash",
            ),
        ]


class PatientAppSession(UserStampedModel):
    project_patient = models.ForeignKey(
        "studies.ProjectPatient",
        on_delete=models.CASCADE,
        related_name="patient_app_sessions",
    )
    patient = models.ForeignKey(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="patient_app_sessions",
    )
    wx_openid = models.CharField(max_length=128)
    token_hash = models.CharField(max_length=128, unique=True)
    expires_at = models.DateTimeField()
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-id"]
