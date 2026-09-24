from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework.response import Response

from apps.training.direct_video import grant_direct_upload, verify_direct_video
from .views import PatientAppBaseView, validation_detail


class GrantSerializer(serializers.Serializer):
    client_session_id = serializers.UUIDField()
    motion_attempt_id = serializers.UUIDField()
    size_bytes = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
    duration_ms = serializers.IntegerField(min_value=1, max_value=300000)


class DirectUploadGrantView(PatientAppBaseView):
    def post(self, request):
        serializer = GrantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            data, created = grant_direct_upload(project_patient=self.project_patient(), **serializer.validated_data)
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=400)
        return Response(data, status=201 if created else 200)


class DirectUploadCompleteView(PatientAppBaseView):
    def post(self, request, video_id):
        try:
            data = verify_direct_video(project_patient=self.project_patient(), video_id=video_id)
        except DjangoValidationError as exc:
            return Response({"detail": validation_detail(exc)}, status=400)
        return Response(data)
