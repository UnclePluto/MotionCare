from uuid import uuid4

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


MIGRATION_FROM = [
    ("accounts", "0002_user_gender_must_change_password"),
    ("patient_app", "0002_alter_patientappbindingcode_code_hash"),
]
MIGRATION_TO = ("patient_app", "0003_add_wechat_binding")


@pytest.fixture(name="db")
def _create_test_database_without_transaction(django_db_setup):
    """创建测试数据库，但让迁移测试自行管理 schema 与清理。"""
    yield


@pytest.mark.usefixtures("db")
def test_add_wechat_binding_migration_clears_legacy_temporary_login_codes(
    django_db_blocker,
):
    assert connection.settings_dict["NAME"].startswith("test_")

    with django_db_blocker.unblock():
        executor = MigrationExecutor(connection)
        original_leaf_nodes = executor.loader.graph.leaf_nodes()
        token_hash = f"migration-test-{uuid4().hex}"
        doctor_id = patient_id = project_id = project_patient_id = None

        try:
            executor.migrate(MIGRATION_FROM)
            old_apps = executor.loader.project_state(MIGRATION_FROM).apps

            User = old_apps.get_model("accounts", "User")
            Patient = old_apps.get_model("patients", "Patient")
            StudyProject = old_apps.get_model("studies", "StudyProject")
            StudyGroup = old_apps.get_model("studies", "StudyGroup")
            ProjectPatient = old_apps.get_model("studies", "ProjectPatient")
            PatientAppSession = old_apps.get_model("patient_app", "PatientAppSession")

            phone_suffix = f"{uuid4().int % 1_000_000_000:09d}"
            doctor = User.objects.create(
                username=f"13{phone_suffix}",
                phone=f"13{phone_suffix}",
                name="测试医生",
                role="doctor",
                gender="unknown",
            )
            doctor_id = doctor.pk
            patient = Patient.objects.create(
                name="患者甲",
                gender="male",
                age=70,
                phone=f"15{phone_suffix}",
                primary_doctor=doctor,
            )
            patient_id = patient.pk
            project = StudyProject.objects.create(name="微信绑定迁移测试项目")
            project_id = project.pk
            group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
            project_patient = ProjectPatient.objects.create(
                project=project,
                patient=patient,
                group=group,
            )
            project_patient_id = project_patient.pk
            legacy_session = PatientAppSession.objects.create(
                project_patient=project_patient,
                patient=patient,
                wx_openid="temporary-login-code",
                token_hash=token_hash,
                expires_at=timezone.now(),
            )

            executor = MigrationExecutor(connection)
            executor.migrate([MIGRATION_TO])
            new_apps = executor.loader.project_state([MIGRATION_TO]).apps
            PatientAppSession = new_apps.get_model("patient_app", "PatientAppSession")
            PatientAppWechatBinding = new_apps.get_model("patient_app", "PatientAppWechatBinding")

            migrated_session = PatientAppSession.objects.get(pk=legacy_session.pk)
            assert migrated_session.wx_openid is None
            assert PatientAppWechatBinding.objects.count() == 0

            executor = MigrationExecutor(connection)
            executor.migrate(MIGRATION_FROM)
            rolled_back_apps = executor.loader.project_state(MIGRATION_FROM).apps
            PatientAppSession = rolled_back_apps.get_model("patient_app", "PatientAppSession")

            rolled_back_session = PatientAppSession.objects.get(pk=legacy_session.pk)
            assert rolled_back_session.wx_openid == ""
        finally:
            try:
                MigrationExecutor(connection).migrate(original_leaf_nodes)
            finally:
                from apps.accounts.models import User as CurrentUser
                from apps.patient_app.models import PatientAppSession as CurrentPatientAppSession
                from apps.patients.models import Patient as CurrentPatient
                from apps.studies.models import ProjectPatient as CurrentProjectPatient
                from apps.studies.models import StudyProject as CurrentStudyProject

                CurrentPatientAppSession.objects.filter(token_hash=token_hash).delete()
                if project_patient_id is not None:
                    CurrentProjectPatient.objects.filter(pk=project_patient_id).delete()
                if project_id is not None:
                    CurrentStudyProject.objects.filter(pk=project_id).delete()
                if patient_id is not None:
                    CurrentPatient.objects.filter(pk=patient_id).delete()
                if doctor_id is not None:
                    CurrentUser.objects.filter(pk=doctor_id).delete()
