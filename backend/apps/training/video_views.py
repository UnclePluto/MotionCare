import datetime

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor
from apps.wearables.services.training_windows import training_video_wearable_window

from .motion_analysis_storage import validate_published_skeleton_metadata
from .models import MotionAnalysisJob
from .qiniu import create_private_object_download_url
from .video_serializers import (
    MotionAnalysisJobSerializer,
)
from .video_services import (
    create_private_download_url,
    get_training_video_for_user,
)
from .views import validation_detail


class TrainingVideoWearableWindowView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        return Response(training_video_wearable_window(video))


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


class TrainingVideoLatestAnalysisJobView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        job = (
            MotionAnalysisJob.objects.select_related("training_video")
            .filter(training_video=video)
            .order_by("-created_at", "-id")
            .first()
        )
        return Response(MotionAnalysisJobSerializer(job).data if job else None)


class TrainingVideoLatestAnalysisSkeletonUrlView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        job = (
            MotionAnalysisJob.objects.select_related("training_video")
            .filter(training_video=video)
            .order_by("-created_at", "-id")
            .first()
        )
        try:
            validate_published_skeleton_metadata(job)
        except DjangoValidationError:
            raise Http404
        expires_at = timezone.now() + datetime.timedelta(
            seconds=settings.QINIU_DOWNLOAD_TOKEN_TTL_SECONDS
        )
        try:
            url = create_private_object_download_url(
                object_key=job.skeleton_object_key,
                expires_at=expires_at,
            )
        except DjangoValidationError as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({"url": url})
