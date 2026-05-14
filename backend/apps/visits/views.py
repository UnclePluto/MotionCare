from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.project_status import ensure_project_open

from .filters import VisitRecordFilter
from .models import VisitRecord
from .serializers import VisitRecordListSerializer, VisitRecordSerializer


class VisitRecordPagination(PageNumberPagination):
    """仅访视列表使用分页，避免全局 DRF 分页破坏其它列表接口。"""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class VisitRecordViewSet(ModelViewSet):
    permission_classes = [IsAdminOrDoctor]
    filter_backends = [DjangoFilterBackend]
    filterset_class = VisitRecordFilter
    pagination_class = VisitRecordPagination

    queryset = VisitRecord.objects.select_related(
        "project_patient__patient",
        "project_patient__project",
        "project_patient__group",
    ).order_by("-id")

    serializer_class = VisitRecordSerializer

    def get_serializer_class(self):
        if self.action == "list":
            return VisitRecordListSerializer
        return VisitRecordSerializer

    def _ensure_current_visit_writable(self, visit: VisitRecord) -> None:
        if visit.status == VisitRecord.Status.COMPLETED:
            raise ValidationError({"detail": "已完成访视只读，不能继续编辑。"})

    def perform_update(self, serializer):
        visit = self.get_object()
        self._ensure_current_visit_writable(visit)
        ensure_project_open(visit.project_patient.project)
        target_project_patient = serializer.validated_data.get("project_patient", visit.project_patient)
        ensure_project_open(target_project_patient.project)
        serializer.save()
