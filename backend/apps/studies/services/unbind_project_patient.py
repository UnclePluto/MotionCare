from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.crf.models import CrfExport
from apps.prescriptions.models import Prescription
from apps.studies.models import ProjectPatient


@transaction.atomic
def unbind_project_patient(*, project_patient: ProjectPatient) -> None:
    """
    解绑：仅允许已确认分组的入组关系；终止关联处方、清理 CRF 导出，再删除 ProjectPatient。
    处方在库中保留为 TERMINATED 以供审计（project_patient 外键可为空）。
    """
    pp = ProjectPatient.objects.select_for_update(of=("self",)).get(pk=project_patient.pk)
    if pp.grouping_status != ProjectPatient.GroupingStatus.CONFIRMED:
        raise ValidationError({"detail": "仅已确认分组的患者可从本项目移除（解绑）。"})

    Prescription.objects.filter(project_patient=pp).exclude(status=Prescription.Status.TERMINATED).update(
        status=Prescription.Status.TERMINATED
    )

    CrfExport.objects.filter(project_patient=pp).delete()

    pp.delete()
