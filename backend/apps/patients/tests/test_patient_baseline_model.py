import pytest


@pytest.mark.django_db
def test_patient_baseline_can_be_created_and_linked_one_to_one(patient):
    from apps.patients.models import PatientBaseline

    baseline = PatientBaseline.objects.create(
        patient=patient,
        subject_id="SUBJ-001",
        name_initials="AA",
        demographics={"gender": "male", "age": 70},
        surgery_allergy={"history": "none"},
        comorbidities={"hypertension": True},
        lifestyle={"smoking": False},
        baseline_medications={"aspirin": True},
    )

    patient.refresh_from_db()
    assert patient.baseline == baseline
    assert baseline.patient == patient
    assert baseline.demographics["gender"] == "male"


@pytest.mark.django_db
def test_patient_baseline_one_to_one_unique_constraint(patient):
    from django.db.utils import IntegrityError

    from apps.patients.models import PatientBaseline

    PatientBaseline.objects.create(patient=patient)

    with pytest.raises(IntegrityError):
        PatientBaseline.objects.create(patient=patient)


@pytest.mark.django_db
def test_patient_baseline_json_defaults_are_empty_dict(patient):
    from apps.patients.models import PatientBaseline

    baseline = PatientBaseline.objects.create(patient=patient)

    assert baseline.demographics == {}
    assert baseline.surgery_allergy == {}
    assert baseline.comorbidities == {}
    assert baseline.lifestyle == {}
    assert baseline.baseline_medications == {}
