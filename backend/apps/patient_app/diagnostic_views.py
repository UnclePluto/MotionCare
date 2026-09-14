from collections.abc import Mapping

from django.conf import settings
from rest_framework import serializers
from rest_framework.exceptions import APIException, ParseError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.training.models import TrainingUploadDiagnostic, TrainingVideo
from apps.training.upload_diagnostics import sanitize_diagnostic_message
from .authentication import PatientAppTokenAuthentication
from .throttles import RedisFixedWindowRateThrottle


class DiagnosticRequestTooLarge(APIException):
    status_code = 413
    default_detail = "诊断请求过大"


class DiagnosticRateLimitUnavailable(APIException):
    status_code = 503
    default_detail = "诊断服务繁忙，请稍后重试"


class TrainingUploadDiagnosticThrottle(RedisFixedWindowRateThrottle):
    key_namespace = "training-upload-diagnostics"
    redis_url_setting = "TRAINING_UPLOAD_DIAGNOSTIC_RATE_LIMIT_REDIS_URL"
    requests_setting = "TRAINING_UPLOAD_DIAGNOSTIC_RATE_LIMIT_REQUESTS"
    window_setting = "TRAINING_UPLOAD_DIAGNOSTIC_RATE_LIMIT_WINDOW_SECONDS"
    unavailable_exception_class = DiagnosticRateLimitUnavailable


class DiagnosticJSONParser(JSONParser):
    def parse(self, stream, media_type=None, parser_context=None):
        from io import BytesIO

        limit = settings.TRAINING_UPLOAD_DIAGNOSTIC_MAX_BODY_BYTES
        body = stream.read(limit + 1)
        if len(body) > limit:
            raise DiagnosticRequestTooLarge()
        return super().parse(BytesIO(body), media_type, parser_context)


class DiagnosticSerializer(serializers.Serializer):
    event_id = serializers.UUIDField()
    occurred_at = serializers.DateTimeField()
    client_session_id = serializers.UUIDField(required=False, allow_null=True)
    video_id = serializers.IntegerField(
        required=False, allow_null=True, min_value=1, max_value=2**63 - 1
    )
    segment_index = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=2**31 - 1
    )
    http_status = serializers.IntegerField(
        required=False, allow_null=True, min_value=100, max_value=599
    )
    stage = serializers.ChoiceField(choices=TrainingUploadDiagnostic.Stage.choices)
    error_code = serializers.RegexField(r"\A(?!.*[0-9]{9})[a-z][a-z0-9_]{0,63}\Z", max_length=64)
    message = serializers.CharField(max_length=500, allow_blank=True)
    network_type = serializers.ChoiceField(
        choices=["wifi", "2g", "3g", "4g", "5g", "none", "unknown", "ethernet"]
    )
    platform = serializers.ChoiceField(
        choices=["ios", "android", "devtools", "windows", "mac", "ohos", "unknown"]
    )
    sdk_version = serializers.RegexField(
        r"\A(?:unknown|[0-9]{1,4}(?:\.[0-9]{1,4}){0,3})\Z", max_length=32
    )
    app_version = serializers.RegexField(
        r"\A(?:unknown|[0-9]{1,4}(?:\.[0-9]{1,4}){0,3})\Z", max_length=32
    )

    def to_internal_value(self, data):
        if not isinstance(data, Mapping) or set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["诊断字段无效"]})
        return super().to_internal_value(data)

    def validate_message(self, value):
        return sanitize_diagnostic_message(value)

    def validate(self, attrs):
        video_id = attrs.get("video_id")
        if video_id is not None:
            video = (
                TrainingVideo.objects.filter(
                    pk=video_id,
                    project_patient=self.context["project_patient"],
                )
                .only("client_session_id")
                .first()
            )
            if video is None or (
                attrs.get("client_session_id") is not None
                and attrs["client_session_id"] != video.client_session_id
            ):
                raise serializers.ValidationError("训练会话无效")
        return attrs


class TrainingUploadDiagnosticView(APIView):
    authentication_classes = [PatientAppTokenAuthentication]
    permission_classes = [IsAuthenticated]
    throttle_classes = [TrainingUploadDiagnosticThrottle]
    parser_classes = [DiagnosticJSONParser]
    http_method_names = ["post"]

    def post(self, request):
        # Check advertised size before DRF loads its request stream; the parser
        # independently bounds the actual bytes, including absent length cases.
        try:
            size = int(request.META.get("CONTENT_LENGTH") or 0)
        except (TypeError, ValueError):
            raise ParseError("诊断请求无效")
        if size > settings.TRAINING_UPLOAD_DIAGNOSTIC_MAX_BODY_BYTES:
            raise DiagnosticRequestTooLarge()
        serializer = DiagnosticSerializer(
            data=request.data,
            context={
                "project_patient": request.user.project_patient,
            },
        )
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        event_id = data.pop("event_id")
        TrainingUploadDiagnostic.objects.get_or_create(
            project_patient=request.user.project_patient,
            event_id=event_id,
            defaults=data,
        )
        return Response({"event_id": str(event_id)})
