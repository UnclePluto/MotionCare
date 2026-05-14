from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Prefetch
from rest_framework import status
from rest_framework.exceptions import ValidationError as DrfValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import IsAdminOrDoctor
from apps.prescriptions.models import Prescription, PrescriptionAction
from apps.prescriptions.serializers import PrescriptionSerializer
from apps.studies.models import ProjectPatient

from .serializers import TrainingRecordCreateSerializer, TrainingRecordSerializer
from .services import create_training_record
from .views import validation_detail


def get_current_active_prescription(project_patient):
    return (
        Prescription.objects.filter(
            project_patient=project_patient,
            status=Prescription.Status.ACTIVE,
        )
        .prefetch_related(
            Prefetch("actions", queryset=PrescriptionAction.objects.order_by("sort_order", "id"))
        )
        .order_by("-effective_at", "-id")
        .first()
    )


class PatientSimCurrentPrescriptionView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, project_patient_id):
        project_patient = get_object_or_404(ProjectPatient, pk=project_patient_id)
        prescription = get_current_active_prescription(project_patient)
        if not prescription:
            return HttpResponse("null", content_type="application/json")
        return Response(PrescriptionSerializer(prescription).data)


class PatientSimTrainingRecordView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def post(self, request, project_patient_id):
        project_patient = get_object_or_404(ProjectPatient, pk=project_patient_id)
        if not get_current_active_prescription(project_patient):
            return Response(
                {"detail": "当前无生效处方，不能录入训练"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = {**request.data, "project_patient": project_patient_id}
        serializer = TrainingRecordCreateSerializer(data=data)
        serializer.is_valid(raise_exception=True)
        try:
            record = create_training_record(**serializer.validated_data)
        except (DjangoValidationError, DrfValidationError) as exc:
            return Response(
                {"detail": validation_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(
            TrainingRecordSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )
