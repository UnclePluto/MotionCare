from collections import Counter

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.db import transaction
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import MethodNotAllowed, ValidationError
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.patient_app.models import PatientAppBindingCode, PatientAppSession
from apps.patient_app.services import create_binding_code, revoke_project_patient_binding
from apps.prescriptions.serializers import ActivateNowPrescriptionSerializer, PrescriptionSerializer
from apps.prescriptions.services import create_active_prescription_now
from apps.studies.project_status import (
    ensure_project_open,
    PROJECT_COMPLETED_BINDING_DETAIL,
    PROJECT_COMPLETED_GROUP_DETAIL,
    PROJECT_COMPLETED_UNBIND_DETAIL,
)
from apps.studies.services.unbind_project_patient import unbind_project_patient
from apps.visits.models import VisitRecord
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

    @action(detail=True, methods=["post"], url_path="complete")
    @transaction.atomic
    def complete(self, request, pk=None):
        project = self.get_object()
        project = StudyProject.objects.select_for_update(of=("self",)).get(pk=project.pk)
        if project.status != StudyProject.Status.ARCHIVED:
            project.status = StudyProject.Status.ARCHIVED
            project.save(update_fields=["status", "updated_at"])
        return Response(StudyProjectSerializer(project).data)

    @action(detail=True, methods=["post"], url_path="confirm-grouping")
    @transaction.atomic
    def confirm_grouping(self, request, pk=None):
        from apps.patients.models import Patient

        project = self.get_object()
        project = StudyProject.objects.select_for_update(of=("self",)).get(pk=project.pk)
        ensure_project_open(project)
        serializer = ConfirmGroupingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        assignments = serializer.validated_data.get("assignments", [])
        group_ratios = serializer.validated_data.get("group_ratios", [])

        ratios_updated = 0
        if group_ratios:
            ratio_group_ids = [item["group_id"] for item in group_ratios]
            duplicate_ratio_group_ids = sorted(
                group_id for group_id, count in Counter(ratio_group_ids).items() if count > 1
            )
            if duplicate_ratio_group_ids:
                return Response(
                    {"detail": f"重复分组占比: {duplicate_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            ratio_groups = StudyGroup.objects.select_for_update(of=("self",)).filter(
                pk__in=ratio_group_ids
            )
            ratio_groups_by_id = {group.id: group for group in ratio_groups}
            missing_ratio_group_ids = sorted(set(ratio_group_ids) - set(ratio_groups_by_id))
            if missing_ratio_group_ids:
                return Response(
                    {"detail": f"以下分组不存在: {missing_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            other_project_ratio_group_ids = sorted(
                group_id
                for group_id, group in ratio_groups_by_id.items()
                if group.project_id != project.id
            )
            if other_project_ratio_group_ids:
                return Response(
                    {"detail": f"分组不属于当前项目: {other_project_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            inactive_ratio_group_ids = sorted(
                group_id for group_id, group in ratio_groups_by_id.items() if not group.is_active
            )
            if inactive_ratio_group_ids:
                return Response(
                    {"detail": f"分组已停用: {inactive_ratio_group_ids}"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            active_group_ids = set(
                StudyGroup.objects.select_for_update(of=("self",))
                .filter(project=project, is_active=True)
                .values_list("id", flat=True)
            )
            submitted_group_ids = set(ratio_group_ids)
            if submitted_group_ids != active_group_ids:
                return Response(
                    {
                        "detail": (
                            "启用组占比提交不完整，请刷新后重试。"
                            f" expected={sorted(active_group_ids)} submitted={sorted(submitted_group_ids)}"
                        )
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            total_ratio = sum(item["target_ratio"] for item in group_ratios)
            if total_ratio != 100:
                return Response(
                    {"detail": f"启用组占比合计须为 100%，当前为 {total_ratio}%"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            for item in group_ratios:
                group = ratio_groups_by_id[item["group_id"]]
                group.target_ratio = item["target_ratio"]
                group.save(update_fields=["target_ratio", "updated_at"])
                ratios_updated += 1

        def bad_request(detail):
            if ratios_updated:
                transaction.set_rollback(True)
            return Response(detail, status=status.HTTP_400_BAD_REQUEST)

        patient_ids = [assignment["patient_id"] for assignment in assignments]
        duplicate_patient_ids = sorted(
            patient_id for patient_id, count in Counter(patient_ids).items() if count > 1
        )
        if duplicate_patient_ids:
            return bad_request({"detail": f"重复患者: {duplicate_patient_ids}"})

        group_ids = [assignment["group_id"] for assignment in assignments]

        existing_patient_ids = set(
            Patient.objects.filter(pk__in=patient_ids).values_list("pk", flat=True)
        )
        missing_patient_ids = sorted(set(patient_ids) - existing_patient_ids)
        if missing_patient_ids:
            return bad_request({"detail": f"以下患者不存在: {missing_patient_ids}"})

        groups = StudyGroup.objects.select_for_update(of=("self",)).filter(pk__in=group_ids)
        groups_by_id = {group.id: group for group in groups}
        missing_group_ids = sorted(set(group_ids) - set(groups_by_id))
        if missing_group_ids:
            return bad_request({"detail": f"以下分组不存在: {missing_group_ids}"})

        other_project_group_ids = sorted(
            group_id for group_id, group in groups_by_id.items() if group.project_id != project.id
        )
        if other_project_group_ids:
            return bad_request({"detail": f"分组不属于当前项目: {other_project_group_ids}"})

        inactive_group_ids = sorted(
            group_id for group_id, group in groups_by_id.items() if not group.is_active
        )
        if inactive_group_ids:
            return bad_request({"detail": f"分组已停用: {inactive_group_ids}"})

        enrolled_patient_ids = set(
            ProjectPatient.objects.select_for_update(of=("self",))
            .filter(project=project, patient_id__in=patient_ids)
            .values_list("patient_id", flat=True)
        )
        if enrolled_patient_ids:
            return bad_request({"detail": f"已确认入组: {sorted(enrolled_patient_ids)}"})

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
                "ratios_updated": ratios_updated,
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
        ensure_project_open(serializer.validated_data["project"], PROJECT_COMPLETED_GROUP_DETAIL)
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        group = self.get_object()
        ensure_project_open(group.project, PROJECT_COMPLETED_GROUP_DETAIL)
        target_project = serializer.validated_data.get("project", group.project)
        ensure_project_open(target_project, PROJECT_COMPLETED_GROUP_DETAIL)
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        group = self.get_object()
        ensure_project_open(group.project, PROJECT_COMPLETED_GROUP_DETAIL)
        return super().destroy(request, *args, **kwargs)


class ProjectPatientViewSet(ModelViewSet):
    queryset = ProjectPatient.objects.select_related("project", "patient", "group").prefetch_related(
        Prefetch(
            "visits",
            queryset=VisitRecord.objects.only(
                "id", "project_patient_id", "visit_type", "status", "visit_date"
            ),
        )
    ).order_by("-id")
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
        patient_name = self.request.query_params.get("patient_name")
        if patient_name:
            qs = qs.filter(patient__name__icontains=patient_name)
        patient_phone = self.request.query_params.get("patient_phone")
        if patient_phone:
            qs = qs.filter(patient__phone__icontains=patient_phone)
        return qs

    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST", detail="请通过项目确认分组接口创建入组关系。")

    def update(self, request, *args, **kwargs):
        raise MethodNotAllowed("PUT", detail="入组关系不可直接修改，请先解绑后重新确认入组。")

    def partial_update(self, request, *args, **kwargs):
        raise MethodNotAllowed("PATCH", detail="入组关系不可直接修改，请先解绑后重新确认入组。")

    def _binding_status_payload(self, project_patient):
        now = timezone.now()
        active_code = (
            PatientAppBindingCode.objects.filter(
                project_patient=project_patient,
                used_at__isnull=True,
                revoked_at__isnull=True,
                expires_at__gt=now,
            )
            .order_by("-expires_at", "-id")
            .first()
        )
        active_session = (
            PatientAppSession.objects.filter(
                project_patient=project_patient,
                is_active=True,
                expires_at__gt=now,
            )
            .order_by("-created_at", "-id")
            .first()
        )

        return {
            "project_patient_id": project_patient.id,
            "patient_id": project_patient.patient_id,
            "patient_name": project_patient.patient.name,
            "project_id": project_patient.project_id,
            "project_name": project_patient.project.name,
            "has_active_binding_code": active_code is not None,
            "binding_code_expires_at": (
                active_code.expires_at.isoformat() if active_code else None
            ),
            "has_active_session": active_session is not None,
            "last_bound_at": active_session.created_at.isoformat() if active_session else None,
            "active_session_expires_at": (
                active_session.expires_at.isoformat() if active_session else None
            ),
        }

    @action(detail=True, methods=["post"], url_path="binding-code")
    def binding_code(self, request, pk=None):
        project_patient = self.get_object()
        ensure_project_open(project_patient.project, PROJECT_COMPLETED_BINDING_DETAIL)
        try:
            plain_code, binding = create_binding_code(
                project_patient=project_patient,
                created_by=request.user,
            )
        except DjangoValidationError as exc:
            detail = exc.messages[0] if hasattr(exc, "messages") and exc.messages else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "id": binding.id,
                "project_patient_id": project_patient.id,
                "code": plain_code,
                "expires_at": binding.expires_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["get"], url_path="binding-status")
    def binding_status(self, request, pk=None):
        project_patient = self.get_object()
        return Response(self._binding_status_payload(project_patient))

    @action(detail=True, methods=["post"], url_path="revoke-binding")
    def revoke_binding(self, request, pk=None):
        project_patient = self.get_object()
        ensure_project_open(project_patient.project, PROJECT_COMPLETED_BINDING_DETAIL)
        revoke_project_patient_binding(project_patient)
        return Response(
            {
                "detail": "已撤销未使用绑定码，并停用患者端登录。",
                **self._binding_status_payload(project_patient),
            }
        )

    @action(detail=True, methods=["post"], url_path="prescriptions/activate-now")
    def activate_prescription_now(self, request, pk=None):
        project_patient = self.get_object()
        serializer = ActivateNowPrescriptionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            prescription = create_active_prescription_now(
                project_patient=project_patient,
                opened_by=request.user,
                actions=serializer.validated_data["actions"],
                expected_active_version=serializer.validated_data.get("expected_active_version"),
                note=serializer.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            detail = exc.messages[0] if hasattr(exc, "messages") and exc.messages else str(exc)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)
        output = PrescriptionSerializer(prescription)
        return Response(output.data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="unbind")
    @transaction.atomic
    def unbind(self, request, pk=None):
        pp = self.get_object()
        ensure_project_open(pp.project, PROJECT_COMPLETED_UNBIND_DETAIL)
        unbind_project_patient(project_patient=pp)
        return Response(
            {
                "detail": "已从本项目移除；关联处方已终止，CRF 导出记录已清理；访视等业务数据已随入组关系解除。"
            }
        )
