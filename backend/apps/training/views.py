from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.response import Response
from rest_framework import mixins
from rest_framework.viewsets import GenericViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import TrainingRecord
from .serializers import TrainingRecordCreateSerializer, TrainingRecordSerializer
from .services import create_training_record


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
