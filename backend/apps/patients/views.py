from rest_framework.viewsets import ModelViewSet

from apps.common.permissions import IsAdminOrDoctor

from .models import Patient
from .serializers import PatientSerializer


class PatientViewSet(ModelViewSet):
    queryset = Patient.objects.select_related("primary_doctor").order_by("-id")
    serializer_class = PatientSerializer
    permission_classes = [IsAdminOrDoctor]
    search_fields = ["name", "phone"]

