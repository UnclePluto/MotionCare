from collections import Counter

from django.db import IntegrityError
from django.db import transaction
from django.db.models import Count
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.services.unbind_project_patient import unbind_project_patient
from apps.visits.services import ensure_default_visits

from .models import ProjectPatient, StudyGroup, StudyProject
from .serializers import (
    ConfirmGroupingSerializer,
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

    @action(detail=True, methods=["post"], url_path="confirm-grouping")
    @transaction.atomic
    def confirm_grouping(self, request, pk=None):
        from apps.patients.models import Patient

        project = self.get_object()
        project = StudyProject.objects.select_for_update(of=("self",)).get(pk=project.pk)
        serializer = ConfirmGroupingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assignments = serializer.validated_data["assignments"]
        patient_ids = [assignment["patient_id"] for assignment in assignments]
        duplicate_patient_ids = sorted(
            patient_id for patient_id, count in Counter(patient_ids).items() if count > 1
        )
        if duplicate_patient_ids:
            return Response(
                {"detail": f"重复患者: {duplicate_patient_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        group_ids = [assignment["group_id"] for assignment in assignments]

        existing_patient_ids = set(
            Patient.objects.filter(pk__in=patient_ids).values_list("pk", flat=True)
        )
        missing_patient_ids = sorted(set(patient_ids) - existing_patient_ids)
        if missing_patient_ids:
            return Response(
                {"detail": f"以下患者不存在: {missing_patient_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        groups = StudyGroup.objects.select_for_update(of=("self",)).filter(pk__in=group_ids)
        groups_by_id = {group.id: group for group in groups}
        missing_group_ids = sorted(set(group_ids) - set(groups_by_id))
        if missing_group_ids:
            return Response(
                {"detail": f"以下分组不存在: {missing_group_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        other_project_group_ids = sorted(
            group_id for group_id, group in groups_by_id.items() if group.project_id != project.id
        )
        if other_project_group_ids:
            return Response(
                {"detail": f"分组不属于当前项目: {other_project_group_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        inactive_group_ids = sorted(
            group_id for group_id, group in groups_by_id.items() if not group.is_active
        )
        if inactive_group_ids:
            return Response(
                {"detail": f"分组已停用: {inactive_group_ids}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enrolled_patient_ids = set(
            ProjectPatient.objects.select_for_update(of=("self",))
            .filter(project=project, patient_id__in=patient_ids)
            .values_list("patient_id", flat=True)
        )
        if enrolled_patient_ids:
            return Response(
                {"detail": f"已确认入组: {sorted(enrolled_patient_ids)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        created = []
        try:
            for assignment in assignments:
                project_patient = ProjectPatient.objects.create(
                    project=project,
                    patient_id=assignment["patient_id"],
                    group_id=assignment["group_id"],
                    created_by=request.user,
                )
                ensure_default_visits(project_patient)
                created.append(project_patient)
        except IntegrityError as exc:
            raise ValidationError({"detail": "已确认入组，请刷新后重试。"}) from exc

        return Response(
            {
                "confirmed": len(created),
                "created": [
                    {
                        "project_patient_id": project_patient.id,
                        "patient_id": project_patient.patient_id,
                        "group_id": project_patient.group_id,
                    }
                    for project_patient in created
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
