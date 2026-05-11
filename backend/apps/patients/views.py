from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.models import ProjectPatient, StudyProject
from apps.visits.services import ensure_default_visits

from .models import Patient
from .serializers import EnrollProjectsSerializer, PatientSerializer


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.select_related("primary_doctor").order_by("-id")
    serializer_class = PatientSerializer
    permission_classes = [IsAdminOrDoctor]
    search_fields = ["name", "phone"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        patient = self.get_object()
        if ProjectPatient.objects.filter(patient=patient).exists():
            raise ValidationError(
                {
                    "detail": "该患者已关联研究项目，无法删除。请先移除项目关联或停用档案。"
                }
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="enroll-projects")
    @transaction.atomic
    def enroll_projects(self, request, pk=None):
        patient = self.get_object()
        serializer = EnrollProjectsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        raw_ids = serializer.validated_data["project_ids"]
        project_ids = list(dict.fromkeys(raw_ids))

        missing = [pid for pid in project_ids if not StudyProject.objects.filter(pk=pid).exists()]
        if missing:
            raise ValidationError({"project_ids": f"以下项目不存在: {sorted(missing)}"})

        created = []
        skipped_project_ids = []
        for pid in project_ids:
            project = StudyProject.objects.get(pk=pid)
            pp, was_created = ProjectPatient.objects.get_or_create(
                project=project,
                patient=patient,
                defaults={"created_by": request.user},
            )
            if was_created:
                ensure_default_visits(pp)
                created.append({"project_id": project.id, "project_patient_id": pp.id})
            else:
                skipped_project_ids.append(pid)

        detail = "请到各项目的「项目详情」看板勾选患者后使用「随机分组」完成按比例入组。"
        return Response(
            {
                "detail": detail,
                "created": created,
                "skipped_project_ids": skipped_project_ids,
            },
            status=status.HTTP_200_OK,
        )

