from rest_framework import serializers

from .models import VisitRecord


class VisitRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitRecord
        fields = [
            "id",
            "project_patient",
            "visit_type",
            "status",
            "visit_date",
            "form_data",
        ]
        read_only_fields = ["id"]

