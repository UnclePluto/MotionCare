from django.db import models

from apps.common.models import TimeStampedModel


class MotionTrainingSession(TimeStampedModel):
    project_patient = models.ForeignKey(
        "studies.ProjectPatient", on_delete=models.CASCADE, related_name="motion_sessions"
    )
    prescription_action = models.ForeignKey(
        "prescriptions.PrescriptionAction", on_delete=models.PROTECT
    )
    client_session_id = models.UUIDField(unique=True)
    planned_sets = models.PositiveIntegerField()
    repetitions = models.PositiveIntegerField()
    count_unit = models.CharField(max_length=16)
    started_at = models.DateTimeField()
    training_date = models.DateField()
    closed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)


class MotionTrainingSet(TimeStampedModel):
    session = models.ForeignKey(
        MotionTrainingSession, on_delete=models.CASCADE, related_name="groups"
    )
    index = models.PositiveIntegerField()
    attempt_id = models.UUIDField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    video = models.OneToOneField(
        "training.TrainingVideo",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="published_motion_set",
    )

    class Meta:
        ordering = ["index"]
        constraints = [
            models.UniqueConstraint(fields=["session", "index"], name="motion_session_set_unique"),
            models.CheckConstraint(
                condition=models.Q(index__gt=0), name="motion_set_index_positive"
            ),
        ]


class MotionSetAttempt(TimeStampedModel):
    id = models.UUIDField(primary_key=True)
    group = models.ForeignKey(MotionTrainingSet, on_delete=models.CASCADE, related_name="attempts")
    abandoned_at = models.DateTimeField(null=True, blank=True)
