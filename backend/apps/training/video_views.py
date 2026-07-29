from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor

from .models import MotionAnalysisJob
from .video_serializers import MotionAnalysisJobSerializer
from .video_services import (
    create_analysis_job,
    create_private_download_url,
    get_training_video_for_user,
)
from .views import validation_detail


class TrainingVideoDownloadUrlView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        try:
            url = create_private_download_url(video)
        except DjangoValidationError as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"url": url})


class TrainingVideoAnalysisJobView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        try:
            job = create_analysis_job(video=video, requested_by=request.user)
        except DjangoValidationError as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            MotionAnalysisJobSerializer(job).data,
            status=status.HTTP_201_CREATED,
        )


class TrainingVideoLatestAnalysisJobView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        job = (
            MotionAnalysisJob.objects.filter(training_video=video)
            .order_by("-created_at", "-id")
            .first()
        )
        return Response(MotionAnalysisJobSerializer(job).data if job else None)
