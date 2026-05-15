from collections.abc import Mapping

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Prefetch
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAuthenticatedAndPasswordChanged
from apps.health.models import DailyHealthRecord
from apps.prescriptions.models import Prescription, PrescriptionAction
from apps.training.models import TrainingRecord
from apps.training.serializers import TrainingRecordSerializer
from apps.training.services import create_training_record
from apps.training.views import validation_detail

from .authentication import PatientAppTokenAuthentication
from .serializers import (
    PatientAppBindSerializer,
    PatientAppDailyHealthSerializer,
    PatientAppTrainingRecordCreateSerializer,
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
            Prefetch("actions", queryset=PrescriptionAction.objects.order_by("sort_order", "id"))
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

    return {
        "id": prescription.id,
        "version": prescription.version,
        "status": prescription.status,
        "effective_at": prescription.effective_at.isoformat()
        if prescription.effective_at
        else None,
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "actions": [
            {
                "id": action.id,
                "action_library_item": action.action_library_item_id,
                "action_name": action.action_name_snapshot,
                "training_type": action.training_type_snapshot,
                "internal_type": action.internal_type_snapshot,
                "action_type": action.action_type_snapshot,
                "action_instruction": action.action_instruction_snapshot,
                "video_url": action.video_url_snapshot,
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
            for action in actions
        ],
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
        has_daily_health = DailyHealthRecord.objects.filter(
            patient=project_patient.patient,
            record_date=today,
        ).exists()
        prescription = serialize_prescription(project_patient)
        return Response(
            {
                **serialize_me(project_patient),
                "today": today.isoformat(),
                "has_daily_health_today": has_daily_health,
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
        try:
            action = PrescriptionAction.objects.get(pk=data.pop("prescription_action"))
            record = create_training_record(
                project_patient=self.project_patient(),
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


class PatientAppDailyHealthTodayView(PatientAppBaseView):
    def get(self, request):
        project_patient = self.project_patient()
        record = DailyHealthRecord.objects.filter(
            patient=project_patient.patient,
            record_date=timezone.localdate(),
        ).first()
        return Response(PatientAppDailyHealthSerializer(record).data if record else None)

    def put(self, request):
        if not isinstance(request.data, Mapping):
            return Response(
                {"detail": "请求体格式错误"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        project_patient = self.project_patient()
        record, _ = DailyHealthRecord.objects.get_or_create(
            patient=project_patient.patient,
            record_date=timezone.localdate(),
        )
        serializer = PatientAppDailyHealthSerializer(record, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)
