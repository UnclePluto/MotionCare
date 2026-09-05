from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from motion_analysis_contract import MotionCounts
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.response import Response
from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import MotionAnalysisJob, MotionResultSource, TrainingRecord
from .serializers import (
    MotionResultUpdateSerializer,
    TrainingRecordCreateSerializer,
    TrainingRecordSerializer,
)
from .services import create_training_record
from .tracking import accessible_project_patients


def validation_detail(exc):
    if isinstance(exc, DrfValidationError):
        detail = exc.detail
        if isinstance(detail, dict) and "detail" in detail:
            return detail["detail"]
        return detail
    if hasattr(exc, "messages") and exc.messages:
        return exc.messages[0]
    return str(exc)


class TrainingRecordViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    GenericViewSet,
):
    queryset = TrainingRecord.objects.select_related(
        "project_patient", "prescription", "prescription_action"
    ).order_by("-id")
    serializer_class = TrainingRecordSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(project_patient__in=accessible_project_patients(self.request.user))
        )

    def create(self, request, *args, **kwargs):
        serializer = TrainingRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_training_record(**serializer.validated_data)
        except (DjangoValidationError, DrfValidationError) as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            TrainingRecordSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["patch"], url_path="motion-result")
    @transaction.atomic
    def motion_result(self, request, pk=None):
        record = get_object_or_404(
            self.get_queryset().select_for_update(),
            pk=pk,
        )
        has_active_analysis = record.motion_analysis_jobs.filter(
            status__in=[
                MotionAnalysisJob.Status.PENDING,
                MotionAnalysisJob.Status.RUNNING,
            ]
        ).exists()
        if has_active_analysis:
            return Response(
                {"detail": "动作分析完成前暂不可修改"},
                status=status.HTTP_409_CONFLICT,
            )

        serializer = MotionResultUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        record.set_motion_result(
            MotionCounts(
                total_count=data["total_count"],
                standard_count=data["standard_count"],
                nonstandard_count=data["nonstandard_count"],
            ),
            {"doctor_note": data["quality_note"]} if data.get("quality_note") else {},
            MotionResultSource.DOCTOR,
            request.user,
            timezone.now(),
        )
        record.save(
            update_fields=[
                "motion_total_count",
                "motion_standard_count",
                "motion_nonstandard_count",
                "motion_quality_data",
                "motion_result_source",
                "motion_result_updated_by",
                "motion_result_updated_at",
                "updated_at",
            ]
        )
        return Response(TrainingRecordSerializer(record).data)
