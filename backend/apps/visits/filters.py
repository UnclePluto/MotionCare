import django_filters

from .models import VisitRecord


class VisitRecordFilter(django_filters.FilterSet):
    project_patient = django_filters.NumberFilter()
    visit_type = django_filters.CharFilter()
    status = django_filters.CharFilter()
    project = django_filters.NumberFilter(field_name="project_patient__project_id")
    patient_name = django_filters.CharFilter(
        field_name="project_patient__patient__name",
        lookup_expr="icontains",
    )
    patient_phone = django_filters.CharFilter(
        field_name="project_patient__patient__phone",
        lookup_expr="icontains",
    )

    class Meta:
        model = VisitRecord
        fields = [
            "project_patient",
            "visit_type",
            "status",
            "project",
            "patient_name",
            "patient_phone",
        ]
