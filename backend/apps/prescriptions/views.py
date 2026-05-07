from django.db import transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import ActionLibraryItem, Prescription, PrescriptionAction
from .serializers import (
    ActionLibraryItemSerializer,
    PrescriptionActionSerializer,
    PrescriptionSerializer,
)
from .services import activate_prescription


class ActionLibraryItemViewSet(ModelViewSet):
    queryset = ActionLibraryItem.objects.order_by("-id")
    serializer_class = ActionLibraryItemSerializer
    permission_classes = [IsAdminOrDoctor]


class PrescriptionActionViewSet(ModelViewSet):
    queryset = PrescriptionAction.objects.select_related("prescription", "action_library_item").order_by("-id")
    serializer_class = PrescriptionActionSerializer
    permission_classes = [IsAdminOrDoctor]


class PrescriptionViewSet(ModelViewSet):
    queryset = Prescription.objects.select_related("project_patient", "opened_by").order_by("-id")
    serializer_class = PrescriptionSerializer
    permission_classes = [IsAdminOrDoctor]

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def activate(self, request, pk=None):
        prescription: Prescription = self.get_object()
        effective_at = request.data.get("effective_at")
        if effective_at:
            try:
                effective_at = timezone.datetime.fromisoformat(effective_at)
            except Exception:
                return Response({"detail": "effective_at 格式错误"}, status=status.HTTP_400_BAD_REQUEST)
            if timezone.is_naive(effective_at):
                effective_at = timezone.make_aware(effective_at)
        activate_prescription(prescription, effective_at=effective_at)
        serializer = self.get_serializer(prescription)
        return Response(serializer.data)

    @action(detail=True, methods=["post"])
    @transaction.atomic
    def terminate(self, request, pk=None):
        prescription: Prescription = self.get_object()
        if prescription.status != Prescription.Status.ACTIVE:
            return Response({"detail": "只能终止生效中的处方"}, status=status.HTTP_400_BAD_REQUEST)
        prescription.status = Prescription.Status.TERMINATED
        prescription.save(update_fields=["status", "updated_at"])
        serializer = self.get_serializer(prescription)
        return Response(serializer.data)

