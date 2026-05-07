from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import DailyHealthRecord
from .serializers import DailyHealthRecordSerializer


class DailyHealthRecordViewSet(ModelViewSet):
    queryset = DailyHealthRecord.objects.select_related("patient").order_by("-id")
    serializer_class = DailyHealthRecordSerializer
    permission_classes = [IsAdminOrDoctor]

