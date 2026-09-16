from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor
from .models import TrainingRecord
from .serializers import TrainingRecordSerializer
from .tracking import accessible_project_patients


class HistoryRecordSerializer(TrainingRecordSerializer):
    action_name = serializers.CharField(source="prescription_action.action_name_snapshot")
    video_id = serializers.SerializerMethodField()

    class Meta(TrainingRecordSerializer.Meta):
        fields = TrainingRecordSerializer.Meta.fields + [
            "action_name",
            "invalidated_at",
            "invalidation_reason",
            "cutover_marker",
            "video_id",
        ]

    def get_video_id(self, record):
        video = getattr(record, "video", None)
        return video.pk if video else None


def history_records(user):
    return (
        TrainingRecord.objects.filter(
            project_patient__in=accessible_project_patients(user),
            invalidated_at__isnull=False,
        )
        .select_related("prescription_action", "video")
        .order_by("-training_date", "-id")
    )


class TrainingHistoryListView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request):
        field = serializers.IntegerField(min_value=1)
        project_patient_id = field.run_validation(request.query_params.get("project_patient"))
        project_patient = get_object_or_404(
            accessible_project_patients(request.user), pk=project_patient_id
        )
        return Response(
            HistoryRecordSerializer(
                history_records(request.user).filter(project_patient=project_patient), many=True
            ).data
        )


class TrainingHistoryDetailView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, record_id):
        record = get_object_or_404(history_records(request.user), pk=record_id)
        return Response(HistoryRecordSerializer(record).data)
