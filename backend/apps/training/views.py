from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import TrainingRecord
from .serializers import TrainingRecordSerializer


class TrainingRecordViewSet(ModelViewSet):
    queryset = TrainingRecord.objects.select_related(
        "project_patient", "prescription", "prescription_action"
    ).order_by("-id")
    serializer_class = TrainingRecordSerializer
    permission_classes = [IsAdminOrDoctor]

