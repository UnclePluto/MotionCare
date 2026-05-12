import datetime

import pytest
from apps.patients.models import Patient
from apps.patients.serializers import PatientSerializer


@pytest.mark.django_db
def test_serializer_exposes_primary_doctor_name(doctor):
    p = Patient.objects.create(
        name="甲",
        gender=Patient.Gender.MALE,
        age=40,
        phone="13900000001",
        primary_doctor=doctor,
    )
    data = PatientSerializer(instance=p).data
    assert data["primary_doctor_name"] == doctor.name


@pytest.mark.django_db
def test_validate_clears_age_when_birth_date_nulled(patient):
    patient.birth_date = datetime.date(1950, 6, 1)
    patient.age = 75
    patient.save()
    ser = PatientSerializer(instance=patient, data={"birth_date": None}, partial=True)
    assert ser.is_valid(), ser.errors
    inst = ser.save()
    assert inst.birth_date is None
    assert inst.age is None


@pytest.mark.django_db
def test_validate_recomputes_age_when_birth_date_set(patient):
    patient.birth_date = None
    patient.age = 99
    patient.save()
    ser = PatientSerializer(
        instance=patient,
        data={"birth_date": datetime.date(2000, 1, 1)},
        partial=True,
    )
    assert ser.is_valid(), ser.errors
    inst = ser.save()
    assert inst.birth_date == datetime.date(2000, 1, 1)
    expected = datetime.date.today().year - 2000
    if (datetime.date.today().month, datetime.date.today().day) < (1, 1):
        expected -= 1
    assert inst.age == expected
