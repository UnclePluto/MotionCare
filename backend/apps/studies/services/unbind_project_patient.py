from django.db import transaction
from django.utils import timezone
from apps.crf.models import CrfExport
from apps.prescriptions.models import Prescription
from apps.studies.models import ProjectPatient
from apps.training.models import TrainingVideo


@transaction.atomic
def unbind_project_patient(*, project_patient: ProjectPatient) -> None:
    """
    解绑：终止关联处方、清理 CRF 导出，再删除 ProjectPatient。
    处方在库中保留为 TERMINATED 以供审计（project_patient 外键可为空）。
    """
    pp = ProjectPatient.objects.select_for_update(of=("self",)).get(pk=project_patient.pk)

    now = timezone.now()
    Prescription.objects.filter(project_patient=pp).exclude(status=Prescription.Status.TERMINATED).update(
        status=Prescription.Status.TERMINATED,
        archived_at=now,
        updated_at=now,
    )

    CrfExport.objects.filter(project_patient=pp).delete()

    video_ids = list(
        TrainingVideo.objects.select_for_update()
        .filter(project_patient=pp)
        .values_list("id", flat=True)
    )
    if video_ids:
        TrainingVideo.objects.filter(id__in=video_ids).update(
            cleanup_status=TrainingVideo.CleanupStatus.PENDING,
            cleanup_requested_at=now,
            cleanup_heartbeat_at=now,
            cleanup_error="",
            updated_at=now,
        )

    pp.delete()
    if video_ids:
        from apps.training.video_tasks import cleanup_unbound_training_video

        for video_id in video_ids:
            transaction.on_commit(
                lambda durable_video_id=video_id: cleanup_unbound_training_video.delay(
                    durable_video_id
                )
            )
