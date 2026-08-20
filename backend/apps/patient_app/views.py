from collections.abc import Mapping

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.cache import cache
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.common.permissions import IsAuthenticatedAndPasswordChanged
from apps.prescriptions.models import Prescription, PrescriptionAction
from apps.prescriptions.motion_videos import (
    build_demo_motion_video_manifest,
    resolve_motion_video_url,
)
from apps.training.models import TrainingRecord
from apps.training.serializers import TrainingRecordSerializer
from apps.training.services import create_training_record
from apps.training.video_services import (
    SegmentConflict,
    SessionConflict,
    SHOULDER_PRESS_SOURCE_KEY,
    create_training_video_session,
    finalize_training_video_session,
    store_training_video_segment,
    training_video_session_status,
)
from apps.training.views import validation_detail

from .authentication import PatientAppTokenAuthentication
from .serializers import (
    PatientAppBindSerializer,
    PatientAppTrainingRecordCreateSerializer,
    PatientAppTrainingVideoFinalizeSerializer,
    PatientAppTrainingVideoSegmentSerializer,
    PatientAppTrainingVideoSessionSerializer,
)
from .services import bind_project_patient_with_code


def current_week_bounds(today=None):
    today = today or timezone.localdate()
    start = today - timezone.timedelta(days=today.weekday())
    end = start + timezone.timedelta(days=6)
    return start, end


def serialize_me(project_patient):
    return {
        "project_patient_id": project_patient.id,
        "patient": {
            "id": project_patient.patient_id,
            "name": project_patient.patient.name,
        },
        "project": {
            "id": project_patient.project_id,
            "name": project_patient.project.name,
        },
    }


def current_prescription_for(project_patient):
    return (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
        )
        .prefetch_related(
            Prefetch(
                "actions",
                queryset=PrescriptionAction.objects.select_related("action_library_item").order_by(
                    "sort_order", "id"
                ),
            )
        )
        .order_by("-effective_at", "-id")
        .first()
    )


def serialize_training_record(record):
    if record is None:
        return None
    return {
        "id": record.id,
        "prescription": record.prescription_id,
        "prescription_action": record.prescription_action_id,
        "training_date": record.training_date.isoformat(),
        "status": record.status,
        "actual_duration_minutes": record.actual_duration_minutes,
        "score": str(record.score) if record.score is not None else None,
        "form_data": record.form_data,
        "note": record.note,
    }


def serialize_prescription(project_patient):
    prescription = current_prescription_for(project_patient)
    if prescription is None:
        return None

    actions = list(prescription.actions.all())
    action_ids = [action.id for action in actions]
    week_start, week_end = current_week_bounds()

    completed_counts = {
        row["prescription_action_id"]: row["count"]
        for row in TrainingRecord.objects.filter(
            project_patient=project_patient,
            prescription_action_id__in=action_ids,
            training_date__gte=week_start,
            training_date__lte=week_end,
            status=TrainingRecord.Status.COMPLETED,
        )
        .values("prescription_action_id")
        .annotate(count=Count("id"))
    }

    recent_records = {}
    for record in TrainingRecord.objects.filter(
        project_patient=project_patient,
        prescription_action_id__in=action_ids,
    ).order_by("prescription_action_id", "-training_date", "-id"):
        recent_records.setdefault(record.prescription_action_id, record)

    serialized_actions = []
    for action in actions:
        resolution = resolve_motion_video_url(
            action.video_object_key_snapshot,
            action.video_url_snapshot,
        )
        serialized_actions.append(
            {
                "id": action.id,
                "action_library_item": action.action_library_item_id,
                "source_key": action.action_library_item.source_key or None,
                "action_name": action.action_name_snapshot,
                "training_type": action.training_type_snapshot,
                "internal_type": action.internal_type_snapshot,
                "action_type": action.action_type_snapshot,
                "action_instruction": action.action_instruction_snapshot,
                "video_url": resolution.url,
                "video_unavailable": resolution.unavailable,
                "has_ai_supervision": action.has_ai_supervision_snapshot,
                "weekly_frequency": action.weekly_frequency,
                "duration_minutes": action.duration_minutes,
                "weekly_target_count": action.weekly_target_count,
                "weekly_completed_count": completed_counts.get(action.id, 0),
                "difficulty": action.difficulty,
                "notes": action.notes,
                "sort_order": action.sort_order,
                "recent_record": serialize_training_record(recent_records.get(action.id)),
            }
        )

    return {
        "id": prescription.id,
        "version": prescription.version,
        "status": prescription.status,
        "effective_at": prescription.effective_at.isoformat()
        if prescription.effective_at
        else None,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "actions": serialized_actions,
    }


class PatientAppBindView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PatientAppBindSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token, session = bind_project_patient_with_code(**serializer.validated_data)
        except DjangoValidationError as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"token": token, **serialize_me(session.project_patient)})


class DemoMotionVideoManifestView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "demo_motion_videos"
    cache_key = "patient-app:demo-motion-videos:v1"
    cache_timeout_seconds = 60

    def get(self, request):
        response_data = cache.get(self.cache_key)
        if response_data is None:
            try:
                response_data = {"videos": build_demo_motion_video_manifest()}
            except Exception:
                return Response(
                    {"detail": "演示视频暂时不可用，请稍后重试"},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            cache.set(self.cache_key, response_data, self.cache_timeout_seconds)
        return Response(response_data)


class PatientAppBaseView(APIView):
    authentication_classes = [PatientAppTokenAuthentication]
    permission_classes = [IsAuthenticatedAndPasswordChanged]

    def project_patient(self):
        return self.request.user.project_patient


class PatientAppMeView(PatientAppBaseView):
    def get(self, request):
        return Response(serialize_me(self.project_patient()))


class PatientAppHomeView(PatientAppBaseView):
    def get(self, request):
        project_patient = self.project_patient()
        today = timezone.localdate()
        prescription = serialize_prescription(project_patient)
        return Response(
            {
                **serialize_me(project_patient),
                "today": today.isoformat(),
                "current_prescription": prescription,
            }
        )


class PatientAppCurrentPrescriptionView(PatientAppBaseView):
    def get(self, request):
        return Response(serialize_prescription(self.project_patient()))


class PatientAppTrainingRecordView(PatientAppBaseView):
    def post(self, request):
        if not isinstance(request.data, Mapping):
            return Response(
                {"detail": "请求体格式错误"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = PatientAppTrainingRecordCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        project_patient = self.project_patient()
        try:
            action = PrescriptionAction.objects.get(pk=data.pop("prescription_action"))
            active_prescription = current_prescription_for(project_patient)
            if active_prescription is None or action.prescription_id != active_prescription.id:
                return Response(
                    {"detail": "处方已更新，请返回当前处方重新进入"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            if action.action_library_item.source_key == SHOULDER_PRESS_SOURCE_KEY:
                return Response(
                    {"detail": "肩部推举必须完成录像上传"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            record = create_training_record(
                project_patient=project_patient,
                prescription_action=action,
                **data,
            )
        except PrescriptionAction.DoesNotExist:
            return Response(
                {"detail": "动作不存在或不属于当前处方"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except (DjangoValidationError, DrfValidationError) as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(TrainingRecordSerializer(record).data, status=status.HTTP_201_CREATED)


class PatientAppTrainingVideoSessionView(PatientAppBaseView):
    def post(self, request):
        serializer = PatientAppTrainingVideoSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            video, created = create_training_video_session(
                project_patient=self.project_patient(),
                client_session_id=serializer.validated_data["client_session_id"],
                prescription_action_id=serializer.validated_data["prescription_action"],
                training_date=serializer.validated_data["training_date"],
                expected_duration_seconds=serializer.validated_data["expected_duration_seconds"],
                training_started_at=serializer.validated_data["training_started_at"],
            )
        except SessionConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        data = training_video_session_status(
            project_patient=self.project_patient(),
            video_id=video.id,
        )
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(data, status=response_status)


class PatientAppTrainingVideoSegmentView(PatientAppBaseView):
    def post(self, request, video_id, index):
        serializer = PatientAppTrainingVideoSegmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            segment, created = store_training_video_segment(
                project_patient=self.project_patient(),
                video_id=video_id,
                index=index,
                uploaded_file=serializer.validated_data["file"],
                duration_ms=serializer.validated_data["duration_ms"],
                declared_size_bytes=serializer.validated_data["size_bytes"],
            )
        except SegmentConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=status.HTTP_400_BAD_REQUEST)
        response_status = status.HTTP_201_CREATED if created else status.HTTP_200_OK
        return Response(
            {
                "index": segment.index,
                "duration_ms": segment.duration_ms,
                "size_bytes": segment.size_bytes,
                "sha256": segment.sha256,
                "uploaded_segment_count": segment.training_video.uploaded_segment_count,
            },
            status=response_status,
        )


class PatientAppTrainingVideoFinalizeView(PatientAppBaseView):
    def post(self, request, video_id):
        serializer = PatientAppTrainingVideoFinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            video, job, created = finalize_training_video_session(
                project_patient=self.project_patient(),
                video_id=video_id,
                segment_count=serializer.validated_data["segment_count"],
                actual_duration_seconds=serializer.validated_data[
                    "actual_duration_seconds"
                ],
                note=serializer.validated_data["note"],
                training_ended_at=serializer.validated_data.get("training_ended_at"),
            )
        except SessionConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            {
                "video_id": video.id,
                "status": video.status,
                "assembly_job_id": job.id,
                "processing_stage": job.status,
            },
            status=status.HTTP_202_ACCEPTED if created else status.HTTP_200_OK,
        )


class PatientAppTrainingVideoStatusView(PatientAppBaseView):
    def get(self, request, video_id):
        data = training_video_session_status(
            project_patient=self.project_patient(),
            video_id=video_id,
        )
        return Response(data)


class PatientAppActionHistoryView(PatientAppBaseView):
    def get(self, request, prescription_action_id):
        project_patient = self.project_patient()
        active_prescription = current_prescription_for(project_patient)
        if (
            active_prescription is None
            or not active_prescription.actions.filter(pk=prescription_action_id).exists()
        ):
            return Response(
                {"detail": "动作不存在或不属于当前处方"},
                status=status.HTTP_404_NOT_FOUND,
            )

        today = timezone.localdate()
        last_7_start = today - timezone.timedelta(days=6)
        last_30_start = today - timezone.timedelta(days=29)
        records = TrainingRecord.objects.filter(
            project_patient=project_patient,
            prescription=active_prescription,
            prescription_action_id=prescription_action_id,
        ).order_by("-training_date", "-id")
        return Response(
            {
                "prescription_action": prescription_action_id,
                "last_7_days_completed_count": records.filter(
                    training_date__gte=last_7_start,
                    status=TrainingRecord.Status.COMPLETED,
                ).count(),
                "last_30_days_completed_count": records.filter(
                    training_date__gte=last_30_start,
                    status=TrainingRecord.Status.COMPLETED,
                ).count(),
                "records": [serialize_training_record(record) for record in records[:30]],
            }
        )
