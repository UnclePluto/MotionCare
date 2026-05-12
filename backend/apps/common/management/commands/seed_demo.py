from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.prescriptions.services import activate_prescription
from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.visits.services import ensure_default_visits


class Command(BaseCommand):
    help = "Create demo data for local development"

    def handle(self, *args, **options):
        doctor, _ = User.objects.get_or_create(
            phone="13800000000",
            defaults={"name": "演示医生", "role": User.Role.DOCTOR, "username": "13800000000"},
        )
        doctor.set_password("pass123456")
        doctor.save()

        patient, _ = Patient.objects.get_or_create(
            phone="13900000000",
            defaults={"name": "演示患者", "gender": Patient.Gender.MALE, "age": 72},
        )
        project, _ = StudyProject.objects.get_or_create(
            name="认知衰弱数字疗法研究",
            defaults={"created_by": doctor, "status": StudyProject.Status.ACTIVE},
        )
        group, _ = StudyGroup.objects.get_or_create(project=project, name="干预组")
        project_patient, _ = ProjectPatient.objects.get_or_create(
            project=project,
            patient=patient,
            defaults={"group": group},
        )
        ensure_default_visits(project_patient)

        action, _ = ActionLibraryItem.objects.get_or_create(
            name="坐立训练",
            defaults={
                "training_type": "运动训练",
                "internal_type": ActionLibraryItem.InternalType.MOTION,
                "action_type": "平衡训练",
            },
        )
        prescription, _ = Prescription.objects.get_or_create(
            project_patient=project_patient,
            version=1,
            defaults={"opened_by": doctor, "effective_at": timezone.now()},
        )
        if not prescription.actions.exists():
            prescription.add_action_snapshot(action, duration_minutes=10, sets=2)
        activate_prescription(prescription)

        self.stdout.write(self.style.SUCCESS("Demo data created. Doctor: 13800000000 / pass123456"))
