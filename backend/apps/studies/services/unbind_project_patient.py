from django.db import transaction
from django.utils import timezone
from apps.crf.models import CrfExport
from apps.prescriptions.models import Prescription
from apps.studies.models import ProjectPatient


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

    pp.delete()
