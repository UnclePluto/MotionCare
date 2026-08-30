import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.utils import timezone


MIGRATION_FROM = ("patient_app", "0002_alter_patientappbindingcode_code_hash")
MIGRATION_TO = ("patient_app", "0003_add_wechat_binding")


@pytest.mark.django_db(transaction=True)
def test_add_wechat_binding_migration_clears_legacy_temporary_login_codes():
    executor = MigrationExecutor(connection)
    executor.migrate([MIGRATION_FROM])
    old_apps = executor.loader.project_state([MIGRATION_FROM]).apps

    User = old_apps.get_model("accounts", "User")
    Patient = old_apps.get_model("patients", "Patient")
    StudyProject = old_apps.get_model("studies", "StudyProject")
    StudyGroup = old_apps.get_model("studies", "StudyGroup")
    ProjectPatient = old_apps.get_model("studies", "ProjectPatient")
    PatientAppSession = old_apps.get_model("patient_app", "PatientAppSession")

    doctor = User.objects.create(
        username="13800001111",
        phone="13800001111",
        name="测试医生",
        role="doctor",
    )
    patient = Patient.objects.create(
        name="患者甲",
        gender="male",
        age=70,
        phone="13900001111",
        primary_doctor=doctor,
    )
    project = StudyProject.objects.create(name="微信绑定迁移测试项目")
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    project_patient = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=group,
    )
    legacy_session = PatientAppSession.objects.create(
        project_patient=project_patient,
        patient=patient,
        wx_openid="temporary-login-code",
        token_hash="legacy-token-hash",
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
