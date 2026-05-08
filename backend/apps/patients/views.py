from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import Patient, PatientBaseline
from .serializers import PatientBaselineSerializer, PatientSerializer


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.select_related("primary_doctor").order_by("-id")
    serializer_class = PatientSerializer
    permission_classes = [IsAdminOrDoctor]
    search_fields = ["name", "phone"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=["get", "put", "patch"], url_path="baseline")
    def baseline(self, request, pk=None):
        patient = self.get_object()
        baseline, _created = PatientBaseline.objects.get_or_create(
            patient=patient,
            defaults={"created_by": request.user, "updated_by": request.user},
        )

        if request.method == "GET":
            return Response(PatientBaselineSerializer(baseline).data)

        serializer = PatientBaselineSerializer(
            baseline,
            data=request.data,
            partial=(request.method == "PATCH"),
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)

