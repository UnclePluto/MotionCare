from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor

from .tracking import get_patient_tracking_detail, list_patient_tracking_summaries


class TrackingPatientListView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request):
        return Response(
            list_patient_tracking_summaries(
                request.user,
                q=request.query_params.get("q", "").strip(),
            )
        )


class TrackingPatientDetailView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, patient_id):
        project_patient_id = request.query_params.get("project_patient")
        if project_patient_id:
            try:
                project_patient_id = int(project_patient_id)
            except (TypeError, ValueError):
                return Response(
                    {"detail": "project_patient 必须是数字"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            project_patient_id = None

        try:
            data = get_patient_tracking_detail(
                request.user,
                patient_id=patient_id,
                project_patient_id=project_patient_id,
                range_value=request.query_params.get("range", "30d"),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)
