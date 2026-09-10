from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Barrier
from uuid import UUID

import pytest
from django.db import close_old_connections, connection
from django.utils import timezone
from rest_framework.test import APIClient

from apps.patient_app.services import bind_project_patient_with_code, create_binding_code
from apps.patients.models import Patient
from apps.prescriptions.models import ActionLibraryItem, Prescription
from apps.studies.models import ProjectPatient, StudyProject
from apps.training.game_record_service import create_game_training_record
from apps.training.models import GameQuestionResult, TrainingRecord

URL = "/api/patient-app/training-records/"
SESSION = UUID("b0e8bf6b-e9aa-4641-b9f5-d614142f30c1")


@pytest.fixture
def game_action(active_prescription):
    item, _ = ActionLibraryItem.objects.get_or_create(
        source_key="game-executive-inhibition",
        defaults={"name": "反应抑制", "internal_type": "game", "training_type": "认知训练"},
    )
    return active_prescription.add_action_snapshot(item, difficulty="简单")


def auth_client(pp, doctor):
    code, _ = create_binding_code(project_patient=pp, created_by=doctor)
    token, _ = bind_project_patient_with_code(code, wx_openid=f"question-patient-{pp.pk}")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def patient_client(project_patient, doctor):
    return auth_client(project_patient, doctor)


@pytest.fixture
def payload(game_action):
    return {
        "prescription_action": game_action.pk,
        "training_date": "2026-09-09",
        "status": "completed",
        "actual_duration_minutes": 1,
        "score": "90.00",
        "note": "完成",
        "client_session_id": str(SESSION),
        "form_data": {
            "difficulty": "困难",
            "accuracy_rate": 7,
            "error_count": 88,
            "raw_detail": {"session_duration_seconds": 10, "upload_mode": "direct"},
        },
        "question_results": [
            {
                "question_index": 1,
                "game_code": "game-executive-inhibition",
                "difficulty": "困难",
                "response_duration_ms": 2300,
                "is_correct": True,
                "result_type": "answered",
                "swap_count": None,
            }
        ],
    }


@pytest.mark.django_db
def test_same_uuid_retries_return_existing_record_with_authoritative_summary(
    patient_client, payload
):
    first = patient_client.post(URL, payload, format="json")
    assert first.status_code == 201, first.data
    payload["form_data"]["raw_detail"].update(
        upload_mode="retry", retry_count=3, total_retry_count=20
    )
    payload["form_data"]["accuracy_rate"] = 55
    second = patient_client.post(URL, payload, format="json")
    assert second.status_code == 200, second.data
    assert second.data["id"] == first.data["id"]
    assert TrainingRecord.objects.count() == GameQuestionResult.objects.count() == 1
    record = TrainingRecord.objects.get()
    assert record.form_data["accuracy_rate"] == 100
    assert record.form_data["error_count"] == 0
    assert record.question_results.get().capture_version == "active_response_v1"


@pytest.mark.django_db
def test_same_uuid_changed_semantics_conflict(patient_client, payload):
    first = patient_client.post(URL, payload, format="json")
    payload["question_results"][0]["response_duration_ms"] += 1
    second = patient_client.post(URL, payload, format="json")
    assert first.status_code == 201
    assert second.status_code == 409, second.data
    assert second.data == {"detail": "游戏会话内容与已保存记录不一致"}
    assert GameQuestionResult.objects.get().response_duration_ms == 2300


@pytest.mark.django_db
def test_idempotency_precedes_current_prescription_and_project_write_gate(
    patient_client,
    payload,
    active_prescription,
    doctor,
    project,
):
    first = patient_client.post(URL, payload, format="json")
    active_prescription.status = Prescription.Status.ARCHIVED
    active_prescription.save(update_fields=["status"])
    Prescription.objects.create(
        project_patient=active_prescription.project_patient,
        version=2,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    second = patient_client.post(URL, payload, format="json")
    assert second.status_code == 200, second.data
    assert second.data["id"] == first.data["id"]
    changed = deepcopy(payload)
    changed["client_session_id"] = "66538d50-7a43-4c4a-bc80-b299a275f959"
    assert patient_client.post(URL, changed, format="json").status_code == 400
    project.status = StudyProject.Status.ARCHIVED
    project.save(update_fields=["status"])
    assert patient_client.post(URL, payload, format="json").status_code == 200
    assert patient_client.post(URL, changed, format="json").status_code == 400


@pytest.mark.django_db
def test_other_patient_cannot_read_uuid_or_use_foreign_action(
    patient_client,
    payload,
    project,
    group,
    doctor,
    game_action,
):
    first = patient_client.post(URL, payload, format="json")
    patient = Patient.objects.create(name="患者乙", phone="13900002222", primary_doctor=doctor)
    pp = ProjectPatient.objects.create(project=project, group=group, patient=patient)
    client = auth_client(pp, doctor)
    foreign = client.post(URL, payload, format="json")
    assert foreign.status_code == 400
    prescription = Prescription.objects.create(
        project_patient=pp,
        version=1,
        opened_by=doctor,
        status=Prescription.Status.ACTIVE,
        effective_at=timezone.now(),
    )
    own_action = prescription.add_action_snapshot(
        game_action.action_library_item, difficulty="简单"
    )
    payload["prescription_action"] = own_action.pk
    collision = client.post(URL, payload, format="json")
    assert first.status_code == 201
    assert collision.status_code == 409, collision.data
    assert collision.data == {"detail": "游戏会话内容与已保存记录不一致"}
    assert TrainingRecord.objects.count() == 1


@pytest.mark.django_db
def test_same_patient_different_action_uuid_conflicts(
    patient_client, payload, game_action, active_prescription
):
    assert patient_client.post(URL, payload, format="json").status_code == 201
    action = active_prescription.add_action_snapshot(
        game_action.action_library_item, difficulty="简单"
    )
    payload["prescription_action"] = action.pk
    response = patient_client.post(URL, payload, format="json")
    assert response.status_code == 409, response.data
    assert TrainingRecord.objects.count() == 1


@pytest.mark.django_db
@pytest.mark.parametrize("remove", ["question_results", "client_session_id"])
def test_new_fields_required_as_pair(patient_client, payload, remove):
    payload.pop(remove)
    response = patient_client.post(URL, payload, format="json")
    assert response.status_code == 400, response.data
    assert TrainingRecord.objects.count() == 0


@pytest.mark.django_db
def test_empty_question_array_is_valid_and_anonymous_request_is_rejected(patient_client, payload):
    assert APIClient().post(URL, payload, format="json").status_code == 403
    payload["question_results"] = []
    response = patient_client.post(URL, payload, format="json")
    assert response.status_code == 201, response.data
    assert TrainingRecord.objects.count() == 1
    assert GameQuestionResult.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("invalid", [None, True, {}, [{"question_index": True}]])
def test_invalid_question_array_writes_nothing(patient_client, payload, invalid):
    payload["question_results"] = invalid
    response = patient_client.post(URL, payload, format="json")
    assert response.status_code == 400, response.data
    assert TrainingRecord.objects.count() == GameQuestionResult.objects.count() == 0


@pytest.mark.django_db
def test_invalid_later_question_rolls_back_entire_session(patient_client, payload):
    payload["question_results"].append(
        dict(payload["question_results"][0], question_index=2, is_correct="false")
    )
    response = patient_client.post(URL, payload, format="json")
    assert response.status_code == 400, response.data
    assert TrainingRecord.objects.count() == GameQuestionResult.objects.count() == 0


@pytest.mark.django_db
def test_new_fields_rejected_for_motion(patient_client, payload, prescription_action):
    payload["prescription_action"] = prescription_action.pk
    payload["question_results"] = []
    assert patient_client.post(URL, payload, format="json").status_code == 400
    assert TrainingRecord.objects.count() == 0


@pytest.mark.django_db
def test_new_rows_override_redundant_legacy_rounds(patient_client, payload):
    payload["form_data"]["raw_detail"]["rounds"] = [
        {"round_index": 7, "response_ms": 77, "correct": False}
    ]
    assert patient_client.post(URL, payload, format="json").status_code == 201
    record = TrainingRecord.objects.get()
    assert "rounds" not in record.form_data["raw_detail"]
    assert list(record.question_results.values_list("question_index", flat=True)) == [1]


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("changed", [False, True])
def test_concurrent_uuid_unique_race_is_atomic(game_action, payload, monkeypatch, changed):
    import apps.training.game_record_service as service

    barrier = Barrier(2, timeout=10)
    original_create = service.create_training_record

    def synchronized_create(**kwargs):
        barrier.wait()
        return original_create(**kwargs)

    monkeypatch.setattr(service, "create_training_record", synchronized_create)
    action_id = game_action.pk
    pp_id = game_action.prescription.project_patient_id

    def write(note):
        close_old_connections()
        try:
            from apps.prescriptions.models import PrescriptionAction
            from apps.training.game_record_service import GameSessionConflict

            data = deepcopy(payload)
            data.pop("prescription_action")
            data["note"] = note
            data["client_session_id"] = SESSION
            action = PrescriptionAction.objects.get(pk=action_id)
            pp = ProjectPatient.objects.get(pk=pp_id)
            try:
                result = create_game_training_record(
                    project_patient=pp, prescription_action=action, **data
                )
                return (result.record.pk, result.created)
            except GameSessionConflict:
                return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as executor:
        a = executor.submit(write, "完成")
        b = executor.submit(write, "变化" if changed else "完成")
        results = [a.result(timeout=20), b.result(timeout=20)]
    assert TrainingRecord.objects.count() == GameQuestionResult.objects.count() == 1
    if changed:
        assert results.count("conflict") == 1
    else:
        assert {result[1] for result in results} == {True, False}
        assert results[0][0] == results[1][0]


@pytest.mark.django_db
def test_official_motion_with_game_fields_keeps_video_required_response(
    patient_client,
    payload,
    active_prescription,
):
    item = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    action = active_prescription.add_action_snapshot(item)
    payload["prescription_action"] = action.pk
    payload["question_results"] = []
    response = patient_client.post(URL, payload, format="json")
    assert response.status_code == 400
    assert response.data == {"detail": "运动动作必须完成录像上传"}
    assert TrainingRecord.objects.count() == 0


@pytest.mark.django_db
def test_question_insert_failure_rolls_back_record_and_children(game_action, payload, monkeypatch):
    from django.db import IntegrityError

    original_bulk_create = GameQuestionResult.objects.bulk_create

    def fail_after_insert(rows, **kwargs):
        result = original_bulk_create(rows, **kwargs)
        if rows:
            raise IntegrityError("模拟题目存储故障")
        return result

    monkeypatch.setattr(GameQuestionResult.objects, "bulk_create", fail_after_insert)
    data = deepcopy(payload)
    data.pop("prescription_action")
    with pytest.raises(IntegrityError, match="模拟题目存储故障"):
        create_game_training_record(
            project_patient=game_action.prescription.project_patient,
            prescription_action=game_action,
            **data,
        )
    assert TrainingRecord.objects.count() == GameQuestionResult.objects.count() == 0


@pytest.mark.django_db
def test_legacy_game_requests_remain_non_idempotent(patient_client, payload):
    payload.pop("client_session_id")
    payload.pop("question_results")
    payload["form_data"]["raw_detail"]["rounds"] = [
        {"round_index": 4, "response_ms": 0, "correct": False},
    ]
    first = patient_client.post(URL, payload, format="json")
    second = patient_client.post(URL, payload, format="json")
    assert first.status_code == second.status_code == 201
    assert first.data["id"] != second.data["id"]
    assert TrainingRecord.objects.count() == GameQuestionResult.objects.count() == 2
    assert set(GameQuestionResult.objects.values_list("capture_version", flat=True)) == {
        "legacy_wall_clock_v0"
    }


@pytest.mark.django_db(transaction=True)
@pytest.mark.parametrize("changed", [False, True])
def test_uuid_committed_between_lookup_queries_is_rechecked(
    game_action, payload, monkeypatch, changed
):
    from threading import Event, local

    from django.db.models.query import QuerySet

    from apps.prescriptions.models import PrescriptionAction
    from apps.training.game_record_service import GameSessionConflict

    lookup_finished = Event()
    winner_committed = Event()
    thread_state = local()
    original_first = QuerySet.first

    def first_then_wait_for_commit(queryset):
        record = original_first(queryset)
        if (
            queryset.model is TrainingRecord
            and record is None
            and getattr(thread_state, "pause_after_lookup", False)
        ):
            thread_state.pause_after_lookup = False
            lookup_finished.set()
            assert winner_committed.wait(timeout=10), "首次提交未在期限内完成"
        return record

    monkeypatch.setattr(QuerySet, "first", first_then_wait_for_commit)
    action_id = game_action.pk
    pp_id = game_action.prescription.project_patient_id

    def delayed_retry():
        close_old_connections()
        thread_state.pause_after_lookup = True
        try:
            action = PrescriptionAction.objects.get(pk=action_id)
            pp = ProjectPatient.objects.get(pk=pp_id)
            data = deepcopy(payload)
            data.pop("prescription_action")
            if changed:
                data["note"] = "不同内容"
            try:
                result = create_game_training_record(
                    project_patient=pp,
                    prescription_action=action,
                    **data,
                )
                return result.record.pk, result.created
            except GameSessionConflict:
                return "conflict"
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as executor:
        retry = executor.submit(delayed_retry)
        try:
            assert lookup_finished.wait(timeout=10), "重传未完成首次不存在查询"
            data = deepcopy(payload)
            data.pop("prescription_action")
            first = create_game_training_record(
                project_patient=game_action.prescription.project_patient,
                prescription_action=game_action,
                **data,
            )
        finally:
            winner_committed.set()
        result = retry.result(timeout=15)

    assert first.created is True
    assert TrainingRecord.objects.count() == GameQuestionResult.objects.count() == 1
    assert result == ("conflict" if changed else (first.record.pk, False))
