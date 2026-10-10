from collections.abc import Mapping

from django.db import transaction
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.exceptions import ValidationError
from rest_framework.generics import get_object_or_404
from rest_framework.pagination import PageNumberPagination
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.locking import lock_project_patients
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

    def _target_binding(self, current=None):
        data = self.request.data
        if isinstance(data, Mapping) and "project_patient" in data:
            # Use the serializer's relation field (including its access queryset)
            # for the discovery read; all authoritative reads happen under locks.
            return (
                self.get_serializer()
                .fields["project_patient"]
                .run_validation(data["project_patient"])
            )
        return current

    def _lock_bindings(self, *bindings):
        locked = lock_project_patients(*bindings)
        for binding in locked.values():
            ensure_project_open(binding.project)

    def get_object(self):
        instance = super().get_object()
        if self.action not in {"update", "partial_update", "destroy"}:
            return instance
        target = (
            self._target_binding(instance.project_patient)
            if self.action != "destroy"
            else instance.project_patient
        )
        # Across shared entry points the order is P -> PP -> V. Discovery reads
        # above take no row locks. Never chase a new parent after acquiring V.
        self._lock_bindings(instance.project_patient, target)
        locked = get_object_or_404(
            self.filter_queryset(self.get_queryset()).select_for_update(of=("self",)),
            pk=instance.pk,
        )
        if locked.project_patient_id != instance.project_patient_id:
            raise ValidationError({"project_patient": "访视所属入组关系已变化，请刷新后重试。"})
        self.check_object_permissions(self.request, locked)
        self._ensure_current_visit_writable(locked)
        return locked

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        target = self._target_binding()
        if target is not None:
            self._lock_bindings(target)
        return super().create(request, *args, **kwargs)

    @transaction.atomic
    def update(self, request, *args, **kwargs):
        # get_object returns the locked, checked current visit before DRF builds
        # its serializer. Save and validation share the same parent/record locks.
        return super().update(request, *args, **kwargs)

    @transaction.atomic
    def destroy(self, request, *args, **kwargs):
        return super().destroy(request, *args, **kwargs)
