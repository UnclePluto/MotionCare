from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.services.grouping import assign_groups
from apps.visits.services import ensure_default_visits

from .models import GroupingBatch, ProjectPatient, StudyGroup, StudyProject
from .serializers import (
    GroupingBatchSerializer,
    ProjectPatientSerializer,
    StudyGroupSerializer,
    StudyProjectSerializer,
)


class StudyProjectViewSet(ModelViewSet):
    queryset = StudyProject.objects.order_by("-id")
    serializer_class = StudyProjectSerializer
    permission_classes = [IsAdminOrDoctor]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        if ProjectPatient.objects.filter(project=project).exists():
            raise ValidationError({"detail": "项目中仍有患者，无法删除。"})
        if GroupingBatch.objects.filter(project=project, status=GroupingBatch.Status.PENDING).exists():
            raise ValidationError({"detail": "存在待确认的分组批次，无法删除。"})
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def create_grouping_batch(self, request, pk=None):
        project = self.get_object()
        patient_ids = request.data.get("patient_ids") or []
        if not isinstance(patient_ids, list) or not patient_ids:
            return Response({"detail": "patient_ids 不能为空"}, status=status.HTTP_400_BAD_REQUEST)

        groups_qs = StudyGroup.objects.filter(project=project, is_active=True).order_by("sort_order", "id")
        if not groups_qs.exists():
            return Response({"detail": "项目没有启用分组，不能随机分组"}, status=status.HTTP_400_BAD_REQUEST)

        groups = [{"id": g.id, "ratio": g.target_ratio} for g in groups_qs]
        draft_assignments = assign_groups(patient_ids=patient_ids, groups=groups, seed=request.data.get("seed"))

        batch = GroupingBatch.objects.create(project=project)

        created_project_patients: list[ProjectPatient] = []
        for patient_id in patient_ids:
            pp, _created = ProjectPatient.objects.get_or_create(
                project=project,
                patient_id=patient_id,
                defaults={"grouping_batch": batch, "grouping_status": ProjectPatient.GroupingStatus.PENDING},
            )
            pp.grouping_batch = batch
            pp.grouping_status = ProjectPatient.GroupingStatus.PENDING
            pp.group_id = draft_assignments.get(patient_id)
            pp.save(update_fields=["grouping_batch", "grouping_status", "group", "updated_at"])
            ensure_default_visits(pp)
            created_project_patients.append(pp)

        return Response(
            {
                "batch_id": batch.id,
                "status": batch.status,
                "assignments": [
                    {"project_patient_id": pp.id, "group_id": pp.group_id} for pp in created_project_patients
                ],
            }
        )


class StudyGroupViewSet(ModelViewSet):
    queryset = StudyGroup.objects.select_related("project").order_by("-id")
    serializer_class = StudyGroupSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ProjectPatientViewSet(ModelViewSet):
    queryset = ProjectPatient.objects.select_related("project", "patient", "group", "grouping_batch").order_by("-id")
    serializer_class = ProjectPatientSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        batch_id = self.request.query_params.get("grouping_batch")
        if batch_id:
            qs = qs.filter(grouping_batch_id=batch_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance: ProjectPatient = self.get_object()
        if instance.grouping_status == ProjectPatient.GroupingStatus.CONFIRMED:
            serializer.validated_data.pop("group", None)
        return super().perform_update(serializer)


class GroupingBatchViewSet(ModelViewSet):
    queryset = GroupingBatch.objects.select_related("project", "confirmed_by").order_by("-id")
    serializer_class = GroupingBatchSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        return qs

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def confirm(self, request, pk=None):
        batch: GroupingBatch = self.get_object()
        if batch.status != GroupingBatch.Status.PENDING:
            return Response({"detail": "该批次不是待确认状态"}, status=status.HTTP_400_BAD_REQUEST)

        assignments = request.data.get("assignments") or []
        if not isinstance(assignments, list):
            return Response({"detail": "assignments 格式错误"}, status=status.HTTP_400_BAD_REQUEST)

        pp_by_id = {
            pp.id: pp
            for pp in ProjectPatient.objects.select_for_update().filter(grouping_batch=batch).select_related("group")
        }

        for item in assignments:
            try:
                project_patient_id = int(item["project_patient_id"])
                group_id = int(item["group_id"])
            except Exception:
                return Response({"detail": "assignments 字段缺失或格式错误"}, status=status.HTTP_400_BAD_REQUEST)
            pp = pp_by_id.get(project_patient_id)
            if not pp:
                return Response({"detail": f"project_patient_id={project_patient_id} 不属于该批次"}, status=status.HTTP_400_BAD_REQUEST)
            pp.group_id = group_id
            pp.grouping_status = ProjectPatient.GroupingStatus.CONFIRMED
            pp.save(update_fields=["group", "grouping_status", "updated_at"])

        ProjectPatient.objects.filter(grouping_batch=batch).exclude(
            grouping_status=ProjectPatient.GroupingStatus.CONFIRMED
        ).update(grouping_status=ProjectPatient.GroupingStatus.CONFIRMED)

        batch.status = GroupingBatch.Status.CONFIRMED
        batch.confirmed_by = request.user
        batch.confirmed_at = timezone.now()
        batch.save(update_fields=["status", "confirmed_by", "confirmed_at", "updated_at"])

        return Response({"batch_id": batch.id, "status": batch.status})

