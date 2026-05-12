import pytest

from apps.patients.models import Patient
from apps.patients.serializers import PatientSerializer


@pytest.mark.django_db
def test_patient_serializer_includes_primary_doctor_name(doctor, patient):
    data = PatientSerializer(patient).data

    assert data["primary_doctor"] == doctor.id
    assert data["primary_doctor_name"] == "测试医生"


@pytest.mark.django_db
def test_patient_serializer_primary_doctor_name_is_null_without_doctor():
    patient = Patient.objects.create(
        name="无医生患者",
        gender=Patient.Gender.UNKNOWN,
        age=66,
        phone="13900009999",
        primary_doctor=None,
    )

    data = PatientSerializer(patient).data

    assert data["primary_doctor"] is None
    assert data["primary_doctor_name"] is None
