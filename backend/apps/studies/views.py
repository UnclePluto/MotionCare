from django.db import transaction
from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.services.grouping import assign_groups
from apps.studies.services.unbind_project_patient import unbind_project_patient
from apps.visits.services import ensure_default_visits

from .models import ProjectPatient, StudyGroup, StudyProject
from .serializers import (
    ProjectPatientSerializer,
    StudyGroupSerializer,
    StudyProjectSerializer,
)


class StudyProjectViewSet(ModelViewSet):
    queryset = StudyProject.objects.all()
    serializer_class = StudyProjectSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        return StudyProject.objects.annotate(patient_count=Count("project_patients", distinct=True)).order_by(
            "-id"
        )

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        project = self.get_object()
        if ProjectPatient.objects.filter(project=project).exists():
            raise ValidationError({"detail": "项目中仍有患者，无法删除。"})
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"], url_path="reset-pending")
    @transaction.atomic
    def reset_pending(self, request, pk=None):
        project = self.get_object()
        affected = ProjectPatient.objects.filter(
            project=project,
            grouping_status=ProjectPatient.GroupingStatus.PENDING,
        ).update(group=None)
        return Response({"affected": affected})

    @action(detail=True, methods=["post"], url_path="randomize")
    @transaction.atomic
    def randomize(self, request, pk=None):
        from apps.patients.models import Patient

        project = self.get_object()
        raw_pool = request.data.get("pool_patient_ids", [])
        if not isinstance(raw_pool, list):
            return Response({"detail": "pool_patient_ids 必须是列表"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            pool_ids = [int(x) for x in raw_pool]
        except (TypeError, ValueError):
            return Response({"detail": "pool_patient_ids 含非法 id"}, status=status.HTTP_400_BAD_REQUEST)

        groups_qs = StudyGroup.objects.filter(project=project, is_active=True).order_by("sort_order", "id")
        if not groups_qs.exists():
            return Response(
                {"detail": "项目没有启用分组，不能随机分组"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if pool_ids:
            existing_ids = set(Patient.objects.filter(pk__in=pool_ids).values_list("pk", flat=True))
            missing = [pid for pid in pool_ids if pid not in existing_ids]
            if missing:
                return Response(
                    {"detail": f"以下患者不存在: {sorted(missing)}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        confirmed_patient_ids = set(
            ProjectPatient.objects.filter(
                project=project,
                grouping_status=ProjectPatient.GroupingStatus.CONFIRMED,
            ).values_list("patient_id", flat=True)
        )
        eligible_pool_ids = [pid for pid in pool_ids if pid not in confirmed_patient_ids]
        for pid in eligible_pool_ids:
            ProjectPatient.objects.get_or_create(
                project=project,
                patient_id=pid,
                defaults={
                    "created_by": request.user,
                    "grouping_status": ProjectPatient.GroupingStatus.PENDING,
                },
            )

        pending_pps = list(
            ProjectPatient.objects.filter(
                project=project,
                grouping_status=ProjectPatient.GroupingStatus.PENDING,
            ).select_for_update(of=("self",))
        )
        if not pending_pps:
            return Response(
                {"detail": "没有可参与随机的患者；请勾选患者池中的患者或保留至少一名未确认患者。"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        groups = [{"id": g.id, "ratio": g.target_ratio} for g in groups_qs]
        patient_ids_for_random = [pp.patient_id for pp in pending_pps]
        assignments_by_patient = assign_groups(
            patient_ids=patient_ids_for_random,
            groups=groups,
            seed=request.data.get("seed"),
        )

        result_assignments: list[dict[str, int]] = []
        for pp in pending_pps:
            pp.group_id = assignments_by_patient.get(pp.patient_id)
            pp.grouping_status = ProjectPatient.GroupingStatus.PENDING
            pp.save(update_fields=["group", "grouping_status", "updated_at"])
            ensure_default_visits(pp)
            result_assignments.append({"project_patient_id": pp.id, "group_id": pp.group_id})

        return Response({"assignments": result_assignments})

    @action(detail=True, methods=["post"], url_path="confirm-grouping")
    @transaction.atomic
    def confirm_grouping(self, request, pk=None):
        project = self.get_object()
        pending_qs = ProjectPatient.objects.filter(
            project=project,
            grouping_status=ProjectPatient.GroupingStatus.PENDING,
        )
        if not pending_qs.exists():
            return Response(
                {"detail": "项目内没有可确认的患者。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if pending_qs.filter(group__isnull=True).exists():
            return Response(
                {"detail": "存在未分配分组的待确认患者，请先随机分组。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        confirmed = pending_qs.update(grouping_status=ProjectPatient.GroupingStatus.CONFIRMED)
        return Response({"confirmed": confirmed})


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
    queryset = ProjectPatient.objects.select_related("project", "patient", "group").order_by("-id")
    serializer_class = ProjectPatientSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = super().get_queryset()
        project_id = self.request.query_params.get("project")
        if project_id:
            qs = qs.filter(project_id=project_id)
        patient_id = self.request.query_params.get("patient")
        if patient_id:
            qs = qs.filter(patient_id=patient_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        instance: ProjectPatient = self.get_object()
        if instance.grouping_status == ProjectPatient.GroupingStatus.CONFIRMED:
            serializer.validated_data.pop("group", None)
        return super().perform_update(serializer)

    @action(detail=True, methods=["post"], url_path="unbind")
    @transaction.atomic
    def unbind(self, request, pk=None):
        pp = self.get_object()
        unbind_project_patient(project_patient=pp)
        return Response(
            {
                "detail": "已从本项目移除；关联处方已终止，CRF 导出记录已清理；访视等业务数据已随入组关系解除。"
            }
        )

