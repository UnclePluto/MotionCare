from django.db import transaction
from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ReadOnlyModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.project_status import ensure_project_open

from .models import ActionLibraryItem, Prescription, PrescriptionAction
from .serializers import (
    ActionLibraryItemSerializer,
    PrescriptionActionSerializer,
    PrescriptionSerializer,
)
from .services import PROJECT_COMPLETED_PRESCRIPTION_DETAIL, activate_prescription


class ActionLibraryItemViewSet(ReadOnlyModelViewSet):
    queryset = ActionLibraryItem.objects.order_by("action_type", "id")
    serializer_class = ActionLibraryItemSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = super().get_queryset()
        training_type = self.request.query_params.get("training_type")
        if training_type:
            qs = qs.filter(training_type=training_type)
        internal_type = self.request.query_params.get("internal_type")
        if internal_type:
            qs = qs.filter(internal_type=internal_type)
        return qs


class PrescriptionActionViewSet(ReadOnlyModelViewSet):
    queryset = PrescriptionAction.objects.select_related(
        "prescription", "action_library_item"
    ).order_by("-id")
    serializer_class = PrescriptionActionSerializer
    permission_classes = [IsAdminOrDoctor]


class PrescriptionViewSet(ReadOnlyModelViewSet):
    queryset = (
        Prescription.objects.select_related("project_patient", "opened_by")
        .prefetch_related(
            Prefetch(
                "actions",
                queryset=PrescriptionAction.objects.select_related(
                    "action_library_item"
                ).order_by("sort_order", "id"),
            )
        )
        .order_by("-id")
    )
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        qs = super().get_queryset()
        qs = qs.exclude(status=Prescription.Status.TERMINATED)
        project_patient_id = self.request.query_params.get("project_patient")
        if project_patient_id:
            qs = qs.filter(project_patient_id=project_patient_id)
        return qs

    @action(detail=False, methods=["get"], url_path="current")
    def current(self, request):
        project_patient_id = request.query_params.get("project_patient")
        if not project_patient_id:
            return Response(
                {"detail": "project_patient 为必填参数"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        prescription = (
            self.get_queryset()
            .filter(project_patient_id=project_patient_id, status=Prescription.Status.ACTIVE)
            .order_by("-version", "-id")
            .first()
        )
        if not prescription:
            return Response(None)
        serializer = self.get_serializer(prescription)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def activate(self, request, pk=None):
        prescription: Prescription = self.get_object()
        if prescription.project_patient_id:
            ensure_project_open(
                prescription.project_patient.project,
                PROJECT_COMPLETED_PRESCRIPTION_DETAIL,
            )
        effective_at = request.data.get("effective_at")
        if effective_at:
            try:
                effective_at = timezone.datetime.fromisoformat(effective_at)
            except Exception:
                return Response({"detail": "effective_at 格式错误"}, status=status.HTTP_400_BAD_REQUEST)
            if timezone.is_naive(effective_at):
                effective_at = timezone.make_aware(effective_at)
        activate_prescription(prescription, effective_at=effective_at)
        serializer = self.get_serializer(prescription)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def terminate(self, request, pk=None):
        prescription: Prescription = self.get_object()
        if prescription.project_patient_id:
            ensure_project_open(
                prescription.project_patient.project,
                PROJECT_COMPLETED_PRESCRIPTION_DETAIL,
            )
        if prescription.status != Prescription.Status.ACTIVE:
            return Response({"detail": "只能终止生效中的处方"}, status=status.HTTP_400_BAD_REQUEST)
        prescription.status = Prescription.Status.TERMINATED
        prescription.save(update_fields=["status", "updated_at"])
        serializer = self.get_serializer(prescription)
        return Response(serializer.data)
