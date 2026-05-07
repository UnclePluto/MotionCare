from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import VisitRecord
from .serializers import VisitRecordSerializer


class VisitRecordViewSet(ModelViewSet):
    queryset = VisitRecord.objects.select_related("project_patient").order_by("-id")
    serializer_class = VisitRecordSerializer
    permission_classes = [IsAdminOrDoctor]

