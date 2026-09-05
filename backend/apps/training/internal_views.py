from django.conf import settings
from django.utils import timezone
from motion_analysis_contract import PROTOCOL_VERSION, ClaimedJob
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .internal_permissions import IsPpMcareWorker
from .internal_serializers import ClaimRequestSerializer, HeartbeatRequestSerializer
from .internal_services import (
    LeaseUnavailable,
    StorageGrantUnavailable,
    claim_next_job,
    heartbeat_job,
)


class InternalWorkerAPIView(APIView):
    authentication_classes = ()
    permission_classes = (IsPpMcareWorker,)


class MotionAnalysisClaimView(InternalWorkerAPIView):
    def post(self, request):
        serializer = ClaimRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            claimed = claim_next_job(
                worker_id=serializer.validated_data["worker_id"],
                capabilities=serializer.validated_data["capabilities"],
                now=timezone.now(),
            )
        except StorageGrantUnavailable:
            return Response(
                {"detail": "存储授权暂不可用"},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        if claimed is None:
            return Response(status=status.HTTP_204_NO_CONTENT)

        job = claimed.job
        payload = ClaimedJob(
            protocol_version=PROTOCOL_VERSION,
            job_id=job.id,
            action_source_key=job.action_source_key,
            algorithm_version=job.algorithm_version,
            rule_version=job.rule_version,
            parameter_version=job.parameter_version,
            subject_tracker_version=job.subject_tracker_version,
            lease_token=claimed.lease_token,
            lease_expires_at=job.lease_expires_at.isoformat(),
            heartbeat_interval_seconds=settings.PP_MCARE_HEARTBEAT_INTERVAL_SECONDS,
            download=claimed.storage_grant.download,
            upload=claimed.storage_grant.upload,
        )
        return Response(payload.to_dict(), status=status.HTTP_200_OK)


class MotionAnalysisHeartbeatView(InternalWorkerAPIView):
    def post(self, request, job_id):
        serializer = HeartbeatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            job = heartbeat_job(
                job_id=job_id,
                lease_token=serializer.validated_data["lease_token"],
                stage=serializer.validated_data["stage"],
                now=timezone.now(),
            )
        except LeaseUnavailable:
            return Response(
                {"detail": "租约不可用"},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "protocol_version": PROTOCOL_VERSION,
                "job_id": job.id,
                "lease_expires_at": job.lease_expires_at.isoformat(),
                "heartbeat_interval_seconds": settings.PP_MCARE_HEARTBEAT_INTERVAL_SECONDS,
                "current_stage": job.current_stage,
            },
            status=status.HTTP_200_OK,
        )
