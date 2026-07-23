from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor
from apps.training.tracking import accessible_project_patients
from apps.wearables.models import WearableBinding, WearableDevice

from .serializers import (
    BindDeviceSerializer,
    UnbindDeviceSerializer,
    WearableBindingSerializer,
    WearableDeviceSerializer,
)
from .services.bindings import (
    BindingAlreadyUnbound,
    BindingConflict,
    DeviceNotFound,
    bind_device,
    unbind_device,
)
from .services.short_codes import ShortCodeExhausted


class WearableDeviceListCreateView(ListCreateAPIView):
    queryset = WearableDevice.objects.order_by("-id")
    serializer_class = WearableDeviceSerializer
    permission_classes = [IsAdminOrDoctor]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            self.perform_create(serializer)
        except ShortCodeExhausted as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        except IntegrityError:
            return Response({"detail": "设备厂商标识已存在。"}, status=status.HTTP_409_CONFLICT)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class WearableDeviceDetailView(RetrieveUpdateAPIView):
    queryset = WearableDevice.objects.order_by("-id")
    serializer_class = WearableDeviceSerializer
    permission_classes = [IsAdminOrDoctor]


class ProjectPatientBindingStatusView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, project_patient_id):
        project_patient = get_object_or_404(
            accessible_project_patients(request.user),
            pk=project_patient_id,
        )
        binding = (
            WearableBinding.objects.select_related("device")
            .filter(patient_id=project_patient.patient_id, unbound_at__isnull=True)
            .first()
        )
        return Response(
            {
                "project_patient_id": project_patient.id,
                "patient_id": project_patient.patient_id,
                "binding": WearableBindingSerializer(binding).data if binding else None,
            }
        )


class ProjectPatientBindView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, project_patient_id):
        project_patient = get_object_or_404(
            accessible_project_patients(request.user),
            pk=project_patient_id,
        )
        serializer = BindDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            binding, created = bind_device(
                project_patient=project_patient,
                short_code=serializer.validated_data["short_code"],
                actor=request.user,
            )
        except DeviceNotFound:
            return Response({"detail": "未找到启用的设备。"}, status=status.HTTP_404_NOT_FOUND)
        except BindingConflict as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            WearableBindingSerializer(binding).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class WearableBindingUnbindView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, binding_id):
        accessible_patient_ids = accessible_project_patients(request.user).values("patient_id")
        binding = get_object_or_404(
            WearableBinding.objects.select_related("device").filter(patient_id__in=accessible_patient_ids),
            pk=binding_id,
        )
        serializer = UnbindDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            binding = unbind_device(
                binding=binding,
                actor=request.user,
                reason=serializer.validated_data.get("reason", ""),
            )
        except BindingAlreadyUnbound as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(
            {
                "binding": WearableBindingSerializer(binding).data,
                "historical_data_preserved": True,
            }
        )
