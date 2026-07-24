from django.db import IntegrityError
from django.db.models import CharField, Exists, Max, OuterRef, Q, Subquery
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateAPIView
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor
from apps.training.tracking import accessible_project_patients
from apps.wearables.models import WearableBinding, WearableDevice, WearableSyncRun
from apps.wearables.tasks import METRIC_TYPES, sync_device_metric

from .serializers import (
    BindDeviceSerializer,
    UnbindDeviceSerializer,
    WearableBindingSerializer,
    WearableDailySummariesQuerySerializer,
    WearableDeviceSerializer,
    WearableMeasurementsQuerySerializer,
    WearableProjectSummaryQuerySerializer,
)
from .services.bindings import (
    BindingAlreadyUnbound,
    BindingConflict,
    DeviceNotFound,
    InvalidUnbindTime,
    bind_device,
    mask_patient_name,
    unbind_device,
)
from .services.short_codes import ShortCodeExhausted
from .services.commands import (
    ActiveBindingRequired,
    DisabledDevice,
    UnsupportedCapability,
    check_device_status,
    send_device_command,
)
from .services.queries import daily_summaries, measurements, project_summary, sync_status


def _active_patient_binding(request, patient_id):
    if not accessible_project_patients(request.user).filter(patient_id=patient_id).exists():
        raise Http404
    return get_object_or_404(
        WearableBinding.objects.select_related("device").filter(
            patient_id=patient_id,
            unbound_at__isnull=True,
        )
    )


def _device_queryset_for_user(user):
    accessible_patient_ids = (
        accessible_project_patients(user).order_by().values("patient_id")
    )
    active_bindings = WearableBinding.objects.filter(
        device_id=OuterRef("pk"),
        unbound_at__isnull=True,
    )
    accessible_binding_names = (
        active_bindings.filter(
            patient_id__in=Subquery(accessible_patient_ids),
        )
        .order_by()
        .values("patient__name")
    )
    return (
        WearableDevice.objects.annotate(
            _is_bound=Exists(active_bindings),
            _current_patient_name=Subquery(
                accessible_binding_names[:1],
                output_field=CharField(),
            ),
            _last_sync_at=Max(
                "sync_runs__updated_at",
                filter=Q(sync_runs__status=WearableSyncRun.Status.SUCCEEDED),
            ),
        )
        .order_by("-id")
    )


def _device_for_management(request, pk):
    device = get_object_or_404(WearableDevice.objects.order_by("-id"), pk=pk)
    binding = (
        WearableBinding.objects.filter(device=device, unbound_at__isnull=True)
        .values("patient_id")
        .first()
    )
    if binding:
        if not accessible_project_patients(request.user).filter(
            patient_id=binding["patient_id"]
        ).exists():
            raise Http404
    return device


def _command_response(command):
    return {
        "id": command.id,
        "command_type": command.command_type,
        "status": command.status,
        "provider_code": command.provider_code,
        "completed_at": command.completed_at.isoformat() if command.completed_at else None,
    }


def _command_error(exc):
    if isinstance(exc, DisabledDevice):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, ActiveBindingRequired):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class WearableDeviceListCreateView(ListCreateAPIView):
    serializer_class = WearableDeviceSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        return _device_queryset_for_user(self.request.user)

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
    serializer_class = WearableDeviceSerializer
    permission_classes = [IsAdminOrDoctor]

    def get_queryset(self):
        return _device_queryset_for_user(self.request.user)


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
            detail = str(exc)
            if exc.conflicting_patient_id is not None:
                patient_name = (
                    accessible_project_patients(request.user)
                    .filter(patient_id=exc.conflicting_patient_id)
                    .order_by()
                    .values_list("patient__name", flat=True)
                    .first()
                )
                if patient_name:
                    detail = f"设备已绑定患者{mask_patient_name(patient_name)}。"
            return Response({"detail": detail}, status=status.HTTP_409_CONFLICT)
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
        except InvalidUnbindTime as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "binding": WearableBindingSerializer(binding).data,
                "historical_data_preserved": True,
            }
        )


class WearableDeviceStatusView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, pk):
        device = _device_for_management(request, pk)
        try:
            return Response(check_device_status(device))
        except DisabledDevice as exc:
            return _command_error(exc)
        except Exception:
            return Response({"detail": "设备通信测试失败。"}, status=status.HTTP_502_BAD_GATEWAY)


class WearableDeviceRingView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, pk):
        device = _device_for_management(request, pk)
        try:
            command = send_device_command(device, "ring", request.user)
        except (ActiveBindingRequired, DisabledDevice, UnsupportedCapability) as exc:
            return _command_error(exc)
        return Response(
            _command_response(command),
            status=status.HTTP_202_ACCEPTED
            if command.status == "queued"
            else status.HTTP_200_OK,
        )


class PatientMeasureView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, patient_id):
        binding = _active_patient_binding(request, patient_id)
        metric_type = request.data.get("metric_type")
        command_type = {
            "heart_rate": "measure_heart_rate",
            "blood_pressure": "measure_blood_pressure",
            "blood_oxygen": "measure_blood_oxygen",
        }.get(metric_type)
        if command_type is None:
            return Response({"metric_type": "仅支持心率、血压或血氧。"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            command = send_device_command(
                binding.device,
                command_type,
                request.user,
                require_binding=True,
            )
        except (ActiveBindingRequired, DisabledDevice, UnsupportedCapability) as exc:
            return _command_error(exc)
        return Response(
            _command_response(command),
            status=status.HTTP_202_ACCEPTED
            if command.status == "queued"
            else status.HTTP_200_OK,
        )


class PatientConfigureView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, patient_id):
        binding = _active_patient_binding(request, patient_id)
        setting = request.data.get("setting")
        command_type = {
            "heart_rate_interval": "configure_heart_rate_interval",
            "blood_pressure_interval": "configure_blood_pressure_interval",
            "blood_oxygen_interval": "configure_blood_oxygen_interval",
            "step_switch": "configure_step_switch",
        }.get(setting)
        if command_type is None:
            return Response({"setting": "不支持的设备配置项。"}, status=status.HTTP_400_BAD_REQUEST)
        parameter_name = "enabled" if setting == "step_switch" else "interval_minutes"
        if set(request.data.keys()) != {"setting", parameter_name}:
            return Response({"detail": "配置请求字段不合法。"}, status=status.HTTP_400_BAD_REQUEST)
        value = request.data.get(parameter_name)
        if parameter_name == "enabled":
            if not isinstance(value, bool):
                return Response({"enabled": "步数开关必须为布尔值。"}, status=status.HTTP_400_BAD_REQUEST)
        elif isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= 1440:
            return Response(
                {"interval_minutes": "采集间隔必须为 1 至 1440 分钟。"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        parameters = {parameter_name: value}
        try:
            command = send_device_command(
                binding.device,
                command_type,
                request.user,
                parameters=parameters,
                require_binding=True,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except (ActiveBindingRequired, DisabledDevice, UnsupportedCapability) as exc:
            return _command_error(exc)
        return Response(_command_response(command))


class PatientSyncView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, patient_id):
        binding = _active_patient_binding(request, patient_id)
        if not binding.device.enabled:
            return _command_error(DisabledDevice("设备已停用。"))
        metric_type = request.data.get("metric_type")
        if metric_type is None:
            metric_types = list(METRIC_TYPES)
        elif metric_type in METRIC_TYPES:
            metric_types = [metric_type]
        else:
            return Response({"metric_type": "不支持的同步指标。"}, status=status.HTTP_400_BAD_REQUEST)
        for value in metric_types:
            sync_device_metric.delay(binding.device.id, value)
        return Response({"metric_types": metric_types, "status": "queued"}, status=status.HTTP_202_ACCEPTED)


class PatientMeasurementsView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, patient_id):
        serializer = WearableMeasurementsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            data = measurements(
                user=request.user,
                patient_id=patient_id,
                project_patient_id=serializer.validated_data.get("project_patient"),
                metric_type=serializer.validated_data["metric_type"],
                start=serializer.validated_data["start"],
                end=serializer.validated_data["end"],
                bucket=serializer.validated_data["bucket"],
                page=serializer.validated_data["page"],
                page_size=serializer.validated_data["page_size"],
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)


class PatientDailySummariesView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, patient_id):
        serializer = WearableDailySummariesQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(
            daily_summaries(
                user=request.user,
                patient_id=patient_id,
                project_patient_id=serializer.validated_data.get("project_patient"),
                start=serializer.validated_data["start"],
                end=serializer.validated_data["end"],
            )
        )


class PatientSyncStatusView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, patient_id):
        return Response(sync_status(user=request.user, patient_id=patient_id))


class ProjectWearableSummaryView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, project_id):
        serializer = WearableProjectSummaryQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        return Response(
            project_summary(
                user=request.user,
                project_id=project_id,
                metric_type=serializer.validated_data["metric_type"],
                start=serializer.validated_data["start"],
                end=serializer.validated_data["end"],
            )
        )
