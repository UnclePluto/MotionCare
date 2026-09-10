"""游戏场次与规范题目的原子写入及患者范围内的 UUID 幂等。"""

from dataclasses import dataclass
from datetime import date
from uuid import UUID

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException

from apps.prescriptions.models import PrescriptionAction
from apps.studies.models import ProjectPatient

from .game_questions import normalize_new_question_results, semantic_game_payload_fingerprint
from .models import GameQuestionResult, GameQuestionSelectionStep, TrainingRecord
from .services import create_training_record


@dataclass(frozen=True)
class GameRecordWriteResult:
    record: TrainingRecord
    created: bool


class GameSessionConflict(APIException):
    status_code = 409
    default_detail = "游戏会话内容与已保存记录不一致"


def _existing_result(*, authorized_records, client_session_id, fingerprint):
    record = authorized_records.filter(client_session_id=client_session_id).first()
    if record is None:
        if not TrainingRecord.objects.filter(client_session_id=client_session_id).exists():
            return None
        # 两次查询之间可能有同一患者的请求提交，须重新核对归属与内容。
        record = authorized_records.filter(client_session_id=client_session_id).first()
    if record is None or record.client_payload_fingerprint != fingerprint:
        raise GameSessionConflict()
    return GameRecordWriteResult(record=record, created=False)


def _is_session_unique_conflict(exc):
    constraint_name = getattr(getattr(exc.__cause__, "diag", None), "constraint_name", None)
    if constraint_name is not None:
        return constraint_name == "training_trainingrecord_client_session_id_key"
    return str(exc) == "UNIQUE constraint failed: training_trainingrecord.client_session_id"


@transaction.atomic
def create_game_training_record(
    *,
    project_patient: ProjectPatient,
    prescription_action: PrescriptionAction,
    training_date: date,
    client_session_id: UUID,
    question_results: list[dict],
    **fields,
) -> GameRecordWriteResult:
    if prescription_action.prescription.project_patient_id != project_patient.pk:
        raise ValidationError("动作不属于当前患者")
    try:
        client_session_id = UUID(str(client_session_id))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValidationError("游戏会话 ID 必须为 UUID") from exc
    questions = normalize_new_question_results(
        prescription_action=prescription_action,
        raw_results=question_results,
        form_data=fields.get("form_data"),
    )
    fingerprint = semantic_game_payload_fingerprint(
        project_patient_id=project_patient.pk,
        prescription_action_id=prescription_action.pk,
        training_date=training_date,
        fields=fields,
        questions=questions,
    )
    authorized_records = TrainingRecord.objects.filter(
        project_patient=project_patient,
        prescription_action=prescription_action,
    )
    existing = _existing_result(
        authorized_records=authorized_records,
        client_session_id=client_session_id,
        fingerprint=fingerprint,
    )
    if existing is not None:
        return existing
    try:
        # 唯一约束竞争只回滚本次创建；在保存点外查询胜出的已提交记录。
        with transaction.atomic():
            record = create_training_record(
                project_patient=project_patient,
                prescription_action=prescription_action,
                training_date=training_date,
                **{**fields, "form_data": questions.form_data},
            )
            parents = GameQuestionResult.objects.bulk_create([
                GameQuestionResult(training_record=record, **{key: value for key, value in row.items() if key != "selection_steps"})
                for row in questions.rows
            ])
            GameQuestionSelectionStep.objects.bulk_create([
                GameQuestionSelectionStep(question=parent, **step)
                for parent, row in zip(parents, questions.rows)
                for step in row.get("selection_steps", [])
            ])
            record.client_session_id = client_session_id
            record.client_payload_fingerprint = fingerprint
            record.save(update_fields=["client_session_id", "client_payload_fingerprint"])
    except IntegrityError as exc:
        if not _is_session_unique_conflict(exc):
            raise
        existing = _existing_result(
            authorized_records=authorized_records,
            client_session_id=client_session_id,
            fingerprint=fingerprint,
        )
        if existing is None:
            raise
        return existing
    return GameRecordWriteResult(record=record, created=True)
