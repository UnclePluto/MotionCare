from rest_framework.exceptions import ValidationError
from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor
from apps.studies.models import ProjectPatient

from .models import Patient
from .serializers import PatientSerializer


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.select_related("primary_doctor").order_by("-id")
    serializer_class = PatientSerializer
    permission_classes = [IsAdminOrDoctor]
    search_fields = ["name", "phone"]

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    def destroy(self, request, *args, **kwargs):
        patient = self.get_object()
        if ProjectPatient.objects.filter(patient=patient).exists():
            raise ValidationError(
                {
                    "detail": "该患者已关联研究项目，无法删除。请先移除项目关联或停用档案。"
                }
            )
        return super().destroy(request, *args, **kwargs)

