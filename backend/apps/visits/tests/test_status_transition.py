import pytest
from rest_framework.test import APIClient

from apps.studies.models import ProjectPatient, StudyGroup, StudyProject
from apps.visits.models import VisitRecord


@pytest.fixture
def auth_client(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)
    return client


@pytest.mark.django_db
def test_patch_status_only(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.form_data = {"assessments": {"sppb": {"total": 7}}, "computed_assessments": {}}
    visit.save(update_fields=["form_data"])

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"status": VisitRecord.Status.COMPLETED},
        format="json",
    )
    assert r.status_code == 200, r.content
    visit.refresh_from_db()
    assert visit.status == VisitRecord.Status.COMPLETED
    # Status PATCH should not accidentally clear/overwrite form_data
    assert visit.form_data["assessments"]["sppb"]["total"] == 7


@pytest.mark.django_db
def test_completed_visit_rejects_form_data_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.form_data = {"assessments": {"sppb": {"total": 8}}, "computed_assessments": {}}
    visit.save()

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)
    visit.refresh_from_db()
    assert visit.form_data["assessments"]["sppb"]["total"] == 8
    assert visit.status == VisitRecord.Status.COMPLETED


@pytest.mark.django_db
def test_completed_visit_rejects_repeated_completed_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.save(update_fields=["status"])

    r = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"status": VisitRecord.Status.COMPLETED},
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)


@pytest.mark.django_db
def test_completed_visit_rejects_put(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    visit.status = VisitRecord.Status.COMPLETED
    visit.visit_date = "2026-05-01"
    visit.form_data = {"assessments": {"sppb": {"total": 8}}, "computed_assessments": {}}
    visit.save()

    r = auth_client.put(
        f"/api/visits/{visit.id}/",
        {
            "project_patient": project_patient.id,
            "visit_type": visit.visit_type,
            "status": VisitRecord.Status.DRAFT,
            "visit_date": "2026-05-02",
            "form_data": {"assessments": {"sppb": {"total": 9}}},
        },
        format="json",
    )

    assert r.status_code == 400, r.content
    assert "已完成访视只读" in str(r.data)
    visit.refresh_from_db()
    assert visit.status == VisitRecord.Status.COMPLETED
    assert visit.visit_date.isoformat() == "2026-05-01"
    assert visit.form_data["assessments"]["sppb"]["total"] == 8


@pytest.mark.django_db
def test_visit_detail_includes_project_status(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    response = auth_client.get(f"/api/visits/{visit.id}/")

    assert response.status_code == 200, response.content
    assert response.data["project_id"] == project_patient.project_id
    assert response.data["project_name"] == project_patient.project.name
    assert response.data["project_status"] == project_patient.project.status


@pytest.mark.django_db
def test_completed_project_rejects_visit_patch(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    project = project_patient.project
    project.status = "archived"
    project.save(update_fields=["status"])

    response = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    visit.refresh_from_db()
    assert visit.form_data == {}


@pytest.mark.django_db
def test_completed_project_rejects_visit_put(auth_client, project_patient):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    project = project_patient.project
    project.status = "archived"
    project.save(update_fields=["status"])

    response = auth_client.put(
        f"/api/visits/{visit.id}/",
        {
            "project_patient": project_patient.id,
            "visit_type": visit.visit_type,
            "status": VisitRecord.Status.COMPLETED,
            "visit_date": "2026-05-13",
            "form_data": {"assessments": {"sppb": {"total": 9}}},
        },
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    visit.refresh_from_db()
    assert visit.status == VisitRecord.Status.DRAFT
    assert visit.visit_date is None
    assert visit.form_data == {}


@pytest.mark.django_db
def test_completed_project_rejects_moving_visit_to_completed_project_patient(
    auth_client,
    doctor,
    project_patient,
    patient,
):
    completed_project = StudyProject.objects.create(
        name="已完结研究",
        status=StudyProject.Status.ARCHIVED,
        created_by=doctor,
    )
    completed_group = StudyGroup.objects.create(
        project=completed_project, name="历史组", target_ratio=100
    )
    completed_project_patient = ProjectPatient.objects.create(
        project=completed_project,
        patient=patient,
        group=completed_group,
    )
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")

    response = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"project_patient": completed_project_patient.id},
        format="json",
    )

    assert response.status_code == 400
    assert "项目已完结" in str(response.data)
    visit.refresh_from_db()
    assert visit.project_patient_id == project_patient.id


@pytest.mark.django_db
@pytest.mark.parametrize("operation", ["create", "move"])
def test_cannot_move_or_create_visit_into_archived_project(auth_client, project_patient, operation):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    project_patient.project.status = "archived"
    project_patient.project.save()
    if operation == "create":
        visit.delete()
        response = auth_client.post(
            "/api/visits/",
            {"project_patient": project_patient.id, "visit_type": "T0"},
            format="json",
        )
        assert response.status_code == 400, response.data
        assert not VisitRecord.objects.filter(
            project_patient=project_patient, visit_type="T0"
        ).exists()
    else:
        response = auth_client.patch(
            f"/api/visits/{visit.id}/", {"project_patient": project_patient.id}, format="json"
        )
        assert response.status_code == 400


@pytest.mark.django_db
@pytest.mark.parametrize("include_form", [False, True])
def test_visit_type_change_cannot_escape_validation(auth_client, project_patient, include_form):
    VisitRecord.objects.filter(project_patient=project_patient, visit_type="T1").delete()
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    original = {"crf": {"adherence": {"accept_continue": "旧自由文本"}}}
    visit.form_data = original
    visit.save()
    payload = {"visit_type": "T1"}
    if include_form:
        payload["form_data"] = original
    response = auth_client.patch(f"/api/visits/{visit.id}/", payload, format="json")
    assert response.status_code == 400, response.data
    visit.refresh_from_db()
    assert visit.visit_type == "T0"
    assert visit.form_data == original


@pytest.mark.django_db
@pytest.mark.parametrize(
    "status,bonus,expected", [("completed", 1, 200), ("completed", 0, 400), ("bad", 1, 400)]
)
def test_completion_saves_date_scores_feedback_and_state_atomically(
    auth_client, project_patient, status, bonus, expected
):
    from apps.patients.models import PatientBaseline

    PatientBaseline.objects.create(
        patient=project_patient.patient, demographics={"education_years": 9}
    )
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    key = "visit.form_data.assessments.sppb.total"
    form_data = {
        "assessments": {"sppb": {"total": None}, "moca": {"subscores": {"education_bonus": bonus}}},
        "crf": {
            "adherence": {"investigator_action": "其他", "investigator_other_remark": "下次复核"},
            "_field_meta": {key: {"state": "unknown"}},
        },
    }
    response = auth_client.patch(
        f"/api/visits/{visit.id}/",
        {"status": status, "visit_date": "2026-10-08", "form_data": form_data},
        format="json",
    )
    assert response.status_code == expected, response.data
    visit.refresh_from_db()
    if expected == 200:
        assert visit.status == "completed"
        assert visit.visit_date.isoformat() == "2026-10-08"
        assert visit.form_data["assessments"] == form_data["assessments"]
        assert visit.form_data["crf"]["_field_meta"] == form_data["crf"]["_field_meta"]
        assert visit.form_data["crf"]["adherence"] == form_data["crf"]["adherence"]
    else:
        assert visit.status == "draft"
        assert visit.visit_date is None
        assert visit.form_data == {}


@pytest.mark.django_db
def test_changed_project_patient_uses_target_baseline(auth_client, doctor, project_patient):
    from apps.patients.models import Patient, PatientBaseline

    patient = Patient.objects.create(name="患者乙", gender="male", phone="13900009998")
    PatientBaseline.objects.create(patient=patient, demographics={"education_years": 16})
    target = ProjectPatient.objects.create(
        patient=patient, project=project_patient.project, group=project_patient.group
    )
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    original = {"assessments": {"moca": {"subscores": {"education_bonus": 1}}}}
    visit.form_data = original
    visit.save()
    response = auth_client.patch(
        f"/api/visits/{visit.id}/", {"project_patient": target.id}, format="json"
    )
    assert response.status_code == 400, response.data
    visit.refresh_from_db()
    assert visit.project_patient_id == project_patient.id
    assert visit.form_data == original


@pytest.mark.django_db
@pytest.mark.parametrize("protected", ["completed", "archived"])
def test_readonly_visit_cannot_be_deleted(auth_client, project_patient, protected):
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    if protected == "completed":
        visit.status = "completed"
        visit.save()
    else:
        project_patient.project.status = "archived"
        project_patient.project.save()
    response = auth_client.delete(f"/api/visits/{visit.id}/")
    assert response.status_code == 400, response.data
    assert VisitRecord.objects.filter(pk=visit.pk).exists()


@pytest.mark.django_db(transaction=True)
def test_visit_save_unbind_and_confirm_grouping_have_no_lock_cycle(
    doctor, project_patient, monkeypatch
):
    """旧交错：保存持V，解绑持PP等V，确认持P等PP，保存再等P。"""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event

    from django.db import close_old_connections, connection
    from apps.visits.serializers import VisitRecordSerializer

    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    save_validating, release_save = Event(), Event()
    unbind_attempt, unbind_acquired, unbind_deleting = Event(), Event(), Event()
    confirm_attempt, confirm_waiting_pp = Event(), Event()
    real_validate = VisitRecordSerializer.validate

    def pause_save(self, attrs):
        save_validating.set()
        assert release_save.wait(10)
        return real_validate(self, attrs)

    monkeypatch.setattr(VisitRecordSerializer, "validate", pause_save)

    def request(kind):
        close_old_connections()
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(doctor)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '8s'")

        def observe(execute, sql, params, many, context):
            locking = sql.lstrip().upper().startswith("SELECT") and "FOR UPDATE" in sql.upper()
            pp_lock = locking and 'FROM "studies_projectpatient"' in sql
            project_lock = locking and 'FROM "studies_studyproject"' in sql
            if kind == "unbind" and pp_lock:
                unbind_attempt.set()
            if kind == "unbind" and sql.startswith('DELETE FROM "visits_visitrecord"'):
                unbind_deleting.set()
            if kind == "confirm" and project_lock:
                confirm_attempt.set()
            if kind == "confirm" and pp_lock:
                confirm_waiting_pp.set()
            result = execute(sql, params, many, context)
            if kind == "unbind" and pp_lock:
                unbind_acquired.set()
            return result

        try:
            with connection.execute_wrapper(observe):
                if kind == "save":
                    response = client.patch(
                        f"/api/visits/{visit.pk}/",
                        {"form_data": {"assessments": {"sppb": {"balance": 3}}}},
                        format="json",
                    )
                elif kind == "unbind":
                    response = client.post(
                        f"/api/studies/project-patients/{project_patient.pk}/unbind/"
                    )
                else:
                    response = client.post(
                        f"/api/studies/projects/{project_patient.project_id}/confirm-grouping/",
                        {
                            "assignments": [
                                {
                                    "patient_id": project_patient.patient_id,
                                    "group_id": project_patient.group_id,
                                }
                            ]
                        },
                        format="json",
                    )
            return response.status_code, getattr(response, "data", None)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=3) as executor:
        save = executor.submit(request, "save")
        try:
            assert save_validating.wait(10)
            unbind = executor.submit(request, "unbind")
            assert unbind_attempt.wait(10)
            # Old code acquires PP/deletes V; fixed order blocks before PP.
            if unbind_acquired.wait(0.3):
                assert unbind_deleting.wait(10)
            confirm = executor.submit(request, "confirm")
            assert confirm_attempt.wait(10)
            # Old code holds P and waits PP; fixed code waits P at this point.
            confirm_waiting_pp.wait(0.3)
        finally:
            release_save.set()
        results = [future.result(timeout=12) for future in (save, unbind, confirm)]
    assert all(status < 500 for status, _ in results), results
    assert results[0][0] == results[1][0] == 200, results
    assert results[0][1]["form_data"]["assessments"]["sppb"]["balance"] == 3
    assert results[2][0] in (200, 400), results
    assert not VisitRecord.objects.filter(pk=visit.pk).exists()
    assert not ProjectPatient.objects.filter(pk=project_patient.pk).exists()
    remaining = ProjectPatient.objects.filter(
        project=project_patient.project, patient=project_patient.patient
    )
    if results[2][0] == 200:
        recreated = remaining.get()
        assert recreated.visits.count() == 3
        assert set(recreated.visits.values_list("status", flat=True)) == {"draft"}
    else:
        assert not remaining.exists()


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "interleave",
    [
        "move",
        "delete_after_move",
        "unbind_current",
        "unbind_target",
        "create_after_unbind",
        "archive_target",
    ],
)
def test_visit_write_rechecks_discovered_binding_after_parent_locks(
    doctor, project_patient, interleave
):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from django.db import close_old_connections, connection

    target_project = StudyProject.objects.create(name="目标研究", created_by=doctor)
    target_group = StudyGroup.objects.create(
        project=target_project, name="目标分组", target_ratio=100
    )
    target = ProjectPatient.objects.create(
        project=target_project, patient=project_patient.patient, group=target_group
    )
    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    visit.form_data = {"assessments": {"sppb": {"balance": 2}}}
    visit.save()
    parent_query_started, release_first = Event(), Event()

    def request(first):
        close_old_connections()
        client = APIClient(raise_request_exception=False)
        client.force_authenticate(doctor)
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '5s'")

        def pause_before_parent_lock(execute, sql, params, many, context):
            if first and 'FROM "studies_studyproject"' in sql and "FOR UPDATE" in sql.upper():
                parent_query_started.set()
                assert release_first.wait(10)
            return execute(sql, params, many, context)

        try:
            with connection.execute_wrapper(pause_before_parent_lock):
                if first:
                    payload = {"form_data": {"assessments": {"sppb": {"balance": 3}}}}
                    if interleave in ("unbind_target", "archive_target", "create_after_unbind"):
                        payload["project_patient"] = target.pk
                    if interleave == "create_after_unbind":
                        payload["visit_type"] = "T1"
                        response = client.post("/api/visits/", payload, format="json")
                    elif interleave == "delete_after_move":
                        response = client.delete(f"/api/visits/{visit.pk}/")
                    else:
                        response = client.patch(f"/api/visits/{visit.pk}/", payload, format="json")
                elif interleave in ("move", "delete_after_move"):
                    response = client.patch(
                        f"/api/visits/{visit.pk}/", {"project_patient": target.pk}, format="json"
                    )
                elif interleave == "archive_target":
                    response = client.post(f"/api/studies/projects/{target_project.pk}/complete/")
                else:
                    binding = project_patient if interleave == "unbind_current" else target
                    response = client.post(f"/api/studies/project-patients/{binding.pk}/unbind/")
            return response.status_code, getattr(response, "data", None)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        stale_request = executor.submit(request, True)
        try:
            assert parent_query_started.wait(10)
            concurrent_result = executor.submit(request, False).result(timeout=10)
            assert concurrent_result[0] == 200, concurrent_result
        finally:
            release_first.set()
        stale_result = stale_request.result(timeout=12)
    assert stale_result[0] in (400, 404), stale_result
    if interleave == "unbind_current":
        assert not VisitRecord.objects.filter(pk=visit.pk).exists()
        assert not ProjectPatient.objects.filter(pk=project_patient.pk).exists()
    else:
        visit.refresh_from_db()
        assert visit.project_patient_id == (
            target.pk if interleave in ("move", "delete_after_move") else project_patient.pk
        )
        assert visit.form_data == {"assessments": {"sppb": {"balance": 2}}}
        if interleave in ("unbind_target", "create_after_unbind"):
            assert not ProjectPatient.objects.filter(pk=target.pk).exists()
            assert not VisitRecord.objects.filter(project_patient_id=target.pk).exists()
