"""真实 PostgreSQL：访视与共用 P/PP 的训练、计数组、处方写入串行化。"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event
from time import monotonic, sleep
from uuid import uuid4

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.training.models import TrainingRecord
from apps.visits.models import VisitRecord


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize(
    "operation",
    [
        "training_record",
        "set_open",
        "set_update",
        "set_recover",
        "prescription_create",
        "prescription_activate",
        "prescription_terminate",
        "prescription_cutover",
    ],
)
def test_visit_and_shared_writes_do_not_reverse_project_binding_locks(
    doctor, project_patient, active_prescription, prescription_action, operation
):
    from apps.prescriptions.cutover import cutover_patient
    from apps.prescriptions.services import activate_prescription, create_active_prescription_now
    from apps.training.services import create_training_record
    from apps.training.set_models import MotionTrainingSession
    from apps.training.sets import open_session, recover_session, update_set

    now = timezone.now()
    started_at = now - timezone.timedelta(seconds=40)
    active_prescription.effective_at = now - timezone.timedelta(minutes=5)
    active_prescription.save(update_fields=["effective_at"])
    action = prescription_action
    session_uuid, attempt_uuid = uuid4(), uuid4()
    session = None
    legacy_record = None
    if operation.startswith("set_") or operation == "prescription_cutover":
        item, _ = ActionLibraryItem.objects.get_or_create(
            source_key="motion-resistance-shoulder-press",
            defaults={"name": "肩部推举", "internal_type": "motion", "training_type": "运动训练"},
        )
        options = (
            {"dose_mode": "sets", "sets": 1, "repetitions": 10}
            if operation.startswith("set_")
            else {"duration_minutes": 10}
        )
        action = active_prescription.add_action_snapshot(item, weekly_target_count=4, **options)
    if operation == "set_update":
        session, _ = open_session(
            project_patient,
            client_session_id=session_uuid,
            prescription_action=action.pk,
            started_at=started_at,
        )
    if operation == "prescription_activate":
        next_prescription = Prescription.objects.create(
            project_patient=project_patient, opened_by=doctor, version=2, status="draft"
        )
    if operation == "prescription_cutover":
        legacy_record = TrainingRecord.objects.create(
            project_patient=project_patient,
            prescription=active_prescription,
            prescription_action=action,
            training_date=timezone.localdate(),
            status="completed",
        )

    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T1")
    project_locked, shared_attempted, release_visit = Event(), Event(), Event()
    backend_pids = {}

    def request(kind):
        close_old_connections()
        with connection.cursor() as cursor:
            cursor.execute("SET statement_timeout = '8s'")
            cursor.execute("SELECT pg_backend_pid()")
            backend_pids[kind] = cursor.fetchone()[0]

        def observe(execute, sql, params, many, context):
            locking = "FOR UPDATE" in sql.upper()
            if (
                kind == "shared"
                and locking
                and ('FROM "studies_projectpatient"' in sql or 'FROM "studies_studyproject"' in sql)
            ):
                shared_attempted.set()
            result = execute(sql, params, many, context)
            if kind == "visit" and locking and 'FROM "studies_studyproject"' in sql:
                project_locked.set()
                assert release_visit.wait(10)
            return result

        try:
            with connection.execute_wrapper(observe):
                if kind == "visit":
                    client = APIClient(raise_request_exception=False)
                    client.force_authenticate(doctor)
                    response = client.patch(
                        f"/api/visits/{visit.pk}/", {"visit_date": "2026-10-09"}, format="json"
                    )
                    return response.status_code, getattr(response, "data", None)
                if operation == "training_record":
                    record = create_training_record(
                        project_patient=project_patient,
                        prescription_action=action,
                        training_date=timezone.localdate(),
                        status="completed",
                    )
                    return 200, record.pk
                if operation == "set_open":
                    opened, created = open_session(
                        project_patient,
                        client_session_id=session_uuid,
                        prescription_action=action.pk,
                        started_at=started_at,
                    )
                    return 200, (opened.pk, created)
                if operation == "set_update":
                    updated = update_set(
                        project_patient,
                        session.pk,
                        1,
                        operation="start",
                        attempt_id=attempt_uuid,
                        started_at=started_at,
                    )
                    return 200, updated.pk
                if operation == "set_recover":
                    recovered = recover_session(
                        project_patient,
                        client_session_id=session_uuid,
                        prescription_action=action.pk,
                        started_at=started_at,
                        completed_sets=[
                            {
                                "index": 1,
                                "attempt_id": attempt_uuid,
                                "started_at": started_at,
                                "ended_at": started_at + timezone.timedelta(seconds=20),
                            }
                        ],
                    )
                    return 200, recovered.pk
                if operation == "prescription_create":
                    created = create_active_prescription_now(
                        project_patient,
                        doctor,
                        [
                            {
                                "action_library_item": action.action_library_item,
                                "duration_minutes": 10,
                            }
                        ],
                        expected_active_version=1,
                    )
                    return 200, created.pk
                if operation == "prescription_activate":
                    activated = activate_prescription(next_prescription)
                    return 200, activated.pk
                if operation == "prescription_terminate":
                    client = APIClient(raise_request_exception=False)
                    client.force_authenticate(doctor)
                    response = client.post(
                        f"/api/prescriptions/{active_prescription.pk}/terminate/"
                    )
                    return response.status_code, getattr(response, "data", None)
                return 200, cutover_patient(project_patient.pk)
        except Exception as exc:
            return "error", (type(exc).__name__, str(exc))
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(request, "visit")
        try:
            assert project_locked.wait(10)
            second = pool.submit(request, "shared")
            assert shared_attempted.wait(10)
            deadline = monotonic() + 3
            waiting = False
            while monotonic() < deadline:
                with connection.cursor() as cursor:
                    cursor.execute(
                        "SELECT EXISTS (SELECT 1 FROM pg_stat_activity WHERE pid=%s AND wait_event_type='Lock')",
                        [backend_pids["shared"]],
                    )
                    waiting = cursor.fetchone()[0]
                if waiting:
                    break
                sleep(0.02)
            assert waiting, "第二入口必须实际进入数据库锁等待"
        finally:
            release_visit.set()
        results = [first.result(timeout=12), second.result(timeout=12)]
    assert [status for status, _ in results] == [200, 200], results
    visit.refresh_from_db()
    assert visit.visit_date.isoformat() == "2026-10-09"
    if operation == "training_record":
        stored = TrainingRecord.objects.get(pk=results[1][1])
        assert stored.prescription_id == active_prescription.pk
        assert stored.prescription_action_id == action.pk
    elif operation.startswith("set_"):
        stored = MotionTrainingSession.objects.get(client_session_id=session_uuid)
        assert (stored.planned_sets, stored.repetitions) == (1, 10)
        if operation == "set_open":
            assert results[1][1][1] is True
        else:
            group = stored.groups.get(index=1)
            assert group.attempt_id == attempt_uuid
            assert group.completed == (operation == "set_recover")
    elif operation == "prescription_terminate":
        active_prescription.refresh_from_db()
        assert active_prescription.status == "terminated"
    else:
        active_prescription.refresh_from_db()
        assert active_prescription.status == "archived"
        current = Prescription.objects.get(project_patient=project_patient, status="active")
        assert current.version == 2
        if operation == "prescription_cutover":
            counted = current.actions.get(action_library_item=action.action_library_item)
            assert (
                counted.dose_mode,
                counted.sets,
                counted.repetitions,
                counted.weekly_target_count,
            ) == ("sets", 3, 10, 4)
            legacy_record.refresh_from_db()
            assert legacy_record.invalidated_at is not None
