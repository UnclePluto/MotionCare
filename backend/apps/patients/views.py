from django.db import transaction
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.visits.services import ensure_default_visits

from .models import Patient, PatientBaseline
from .serializers import (
    EnrollProjectsSerializer,
    PatientBaselineSerializer,
    PatientSerializer,
)


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
        enrollments = serializer.validated_data["enrollments"]

        project_ids = {item["project_id"] for item in enrollments}
        group_ids = {item["group_id"] for item in enrollments}

        existing_project_ids = set(
            StudyProject.objects.filter(pk__in=project_ids).values_list("pk", flat=True)
        )
        missing_projects = sorted(project_ids - existing_project_ids)
        if missing_projects:
            raise ValidationError({"detail": f"以下项目不存在: {missing_projects}"})

        existing_groups = {
            group.id: group
            for group in StudyGroup.objects.filter(pk__in=group_ids)
        }
        missing_groups = sorted(group_ids - existing_groups.keys())
        if missing_groups:
            raise ValidationError({"detail": f"以下分组不存在: {missing_groups}"})

        for item in enrollments:
            group = existing_groups[item["group_id"]]
            if group.project_id != item["project_id"]:
                raise ValidationError(
                    {"detail": f"分组 {item['group_id']} 不属于项目 {item['project_id']}"}
                )
            if not group.is_active:
                raise ValidationError({"detail": f"分组已停用: {item['group_id']}"})

        already_linked = list(
            ProjectPatient.objects.filter(
                patient=patient, project_id__in=project_ids
            ).values_list("project_id", flat=True)
        )
        if already_linked:
            raise ValidationError(
                {"detail": f"该患者已在以下项目中: {sorted(already_linked)}"}
            )

        created = []
        for item in enrollments:
            pp = ProjectPatient.objects.create(
                project_id=item["project_id"],
                patient=patient,
                group_id=item["group_id"],
                created_by=request.user,
            )
            ensure_default_visits(pp)
            created.append(
                {
                    "project_id": item["project_id"],
                    "group_id": item["group_id"],
                    "project_patient_id": pp.id,
                }
            )

        return Response(
            {
                "detail": "已确认入组到所选分组。",
                "created": created,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["get", "put", "patch"], url_path="baseline")
    def baseline(self, request, pk=None):
        patient = self.get_object()
        baseline, _created = PatientBaseline.objects.get_or_create(
            patient=patient,
            defaults={"created_by": request.user, "updated_by": request.user},
        )

        if request.method == "GET":
            return Response(PatientBaselineSerializer(baseline).data)

        # PUT 与 PATCH 一律按部分更新处理：CRF 录入是逐节累积的，
        # 避免 PUT 全量覆盖把已录入的 JSON 节段（demographics 等）误清空。
        serializer = PatientBaselineSerializer(
            baseline,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)
