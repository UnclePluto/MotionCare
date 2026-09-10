from dataclasses import dataclass
from datetime import date, timedelta

from django.shortcuts import get_object_or_404
from rest_framework import serializers

from .tracking import accessible_project_patients


@dataclass(frozen=True)
class ExportFilter:
    project_patient_id: int
    range_value: str
    start_date: date | None
    end_date: date | None


class TrainingDetailExportSerializer(serializers.Serializer):
    project_patient = serializers.IntegerField(min_value=1)
    range = serializers.ChoiceField(choices=("7d", "30d", "custom", "all"), default="30d")
    start_date = serializers.DateField(required=False)
    end_date = serializers.DateField(required=False)

    def to_internal_value(self, data):
        if isinstance(data, dict) and set(data) - set(self.fields):
            raise serializers.ValidationError({"non_field_errors": ["存在不支持的导出参数"]})
        return super().to_internal_value(data)

    def validate(self, attrs):
        has_dates = "start_date" in attrs or "end_date" in attrs
        if attrs["range"] != "custom":
            if has_dates:
                raise serializers.ValidationError("只有自定义范围可传入日期")
            return attrs
        if "start_date" not in attrs or "end_date" not in attrs:
            raise serializers.ValidationError("自定义范围必须提供开始和结束日期")
        if attrs["start_date"] > attrs["end_date"]:
            raise serializers.ValidationError("开始日期不能晚于结束日期")
        today = self.context.get("today")
        if today is not None and attrs["end_date"] > today:
            raise serializers.ValidationError("结束日期不能晚于今天")
        return attrs


def resolve_export_filter(data: dict, *, today: date) -> ExportFilter:
    serializer = TrainingDetailExportSerializer(data=data, context={"today": today})
    serializer.is_valid(raise_exception=True)
    attrs = serializer.validated_data
    value = attrs["range"]
    start = end = None
    if value in ("7d", "30d"):
        start, end = today - timedelta(days=6 if value == "7d" else 29), today
    elif value == "custom":
        start, end = attrs["start_date"], attrs["end_date"]
    return ExportFilter(attrs["project_patient"], value, start, end)


def authorize_export(user, *, patient_id: int, project_patient_id: int):
    return get_object_or_404(
        accessible_project_patients(user), pk=project_patient_id, patient_id=patient_id
    )
