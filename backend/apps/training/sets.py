from datetime import timedelta

from django.db import transaction
from django.http import Http404
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.prescriptions.models import Prescription, PrescriptionAction
from apps.studies.models import ProjectPatient
from apps.studies.project_status import ensure_project_open
from .set_models import MotionTrainingSession, MotionTrainingSet, MotionSetAttempt


def current_action(pp, action_id):
    ensure_project_open(pp.project, "项目已结束，不能开始新运动")
    action = (
        PrescriptionAction.objects.select_related("prescription")
        .filter(
            pk=action_id,
            prescription__project_patient=pp,
            prescription__status=Prescription.Status.ACTIVE,
            dose_mode="sets",
        )
        .first()
    )
    if action is None:
        raise ValidationError("运动计划已更新，请返回当前运动计划重新进入")
    return action


def group_duration_seconds(group):
    if group.video_id and group.video.actual_duration_seconds is not None:
        return group.video.actual_duration_seconds
    return (group.ended_at - group.started_at).total_seconds() if group.completed else 0


def serialize_session(session):
    groups = list(session.groups.select_related("video"))
    done = sum(g.completed for g in groups)
    uploaded = sum(bool(g.video_id and g.video.status == "attached") for g in groups)
    status = (
        "completed"
        if uploaded == session.planned_sets
        else ("awaiting_upload" if done == session.planned_sets else "partial")
    )
    return {
        "id": session.id,
        "client_session_id": str(session.client_session_id),
        "prescription_action": session.prescription_action_id,
        "training_date": str(session.training_date),
        "started_at": session.started_at.isoformat(),
        "planned_sets": session.planned_sets,
        "repetitions": session.repetitions,
        "count_unit": session.count_unit,
        "actual_duration_seconds": sum(group_duration_seconds(g) for g in groups if g.completed),
        "completed_sets": done,
        "uploaded_sets": uploaded,
        "status": status,
        "closed": session.closed_at is not None,
        "sets": [
            {
                "index": g.index,
                "attempt_id": str(g.attempt_id) if g.attempt_id else None,
                "completed": g.completed,
                "started_at": g.started_at.isoformat() if g.started_at else None,
                "ended_at": g.ended_at.isoformat() if g.ended_at else None,
                "rest_until": (g.ended_at + timedelta(seconds=180)).isoformat()
                if g.completed
                else None,
                "video_id": g.video_id,
                "uploaded": bool(g.video_id and g.video.status == "attached"),
            }
            for g in groups
        ],
    }


@transaction.atomic
def open_session(pp, *, client_session_id, prescription_action, started_at):
    pp = ProjectPatient.objects.select_for_update().select_related("project").get(pk=pp.pk)
    existing = MotionTrainingSession.objects.filter(client_session_id=client_session_id).first()
    if existing:
        if existing.project_patient_id != pp.pk:
            raise Http404
        if (
            existing.prescription_action_id != prescription_action
            or existing.started_at != started_at
        ):
            raise ValidationError("运动会话标识与原始参数冲突")
        return existing, False
    action = current_action(pp, prescription_action)
    if started_at > timezone.now() + timedelta(seconds=30):
        raise ValidationError("运动开始时间无效")
    date = timezone.localdate(started_at)
    MotionTrainingSession.objects.filter(
        project_patient=pp, completed_at__isnull=True, closed_at__isnull=True
    ).exclude(
        prescription_action=action,
        training_date=date,
    ).update(closed_at=timezone.now())
    session = MotionTrainingSession.objects.create(
        project_patient=pp,
        prescription_action=action,
        client_session_id=client_session_id,
        planned_sets=action.sets,
        repetitions=action.repetitions,
        count_unit=action.count_unit,
        started_at=started_at,
        training_date=date,
    )
    return session, True


def owned_session(pp, session_id, *, lock=False):
    qs = MotionTrainingSession.objects.select_related("prescription_action__prescription")
    if lock:
        qs = qs.select_for_update(of=("self",))
    session = qs.filter(pk=session_id, project_patient=pp).first()
    if session is None:
        raise Http404
    return session


@transaction.atomic
def update_set(pp, session_id, index, *, operation, attempt_id, started_at=None, ended_at=None):
    pp = ProjectPatient.objects.select_for_update().select_related("project").get(pk=pp.pk)
    session = owned_session(pp, session_id, lock=True)
    if not 1 <= index <= session.planned_sets:
        raise ValidationError("组序号无效")
    group, _ = MotionTrainingSet.objects.get_or_create(session=session, index=index)
    attempt = MotionSetAttempt.objects.filter(pk=attempt_id).first()
    if attempt and (attempt.group_id != group.id or attempt.abandoned_at):
        raise ValidationError("录像尝试已放弃或归属不符，请重做本组")
    if operation == "start":
        if group.attempt_id == attempt_id:
            if group.started_at != started_at:
                raise ValidationError("重复开始时间冲突")
            return session
        current_action(pp, session.prescription_action_id)
        if session.closed_at or group.completed:
            raise ValidationError("该运动或组已结束")
        if (
            not started_at
            or started_at < session.started_at
            or started_at > timezone.now() + timedelta(seconds=30)
        ):
            raise ValidationError("本组开始时间无效")
        if index > 1:
            previous = session.groups.filter(index=index - 1, completed=True).first()
            if not previous or started_at < previous.ended_at + timedelta(seconds=180):
                raise ValidationError("请完成上一组并休息三分钟")
        if group.attempt_id:
            raise ValidationError("请先放弃被中断的录像尝试")
        MotionSetAttempt.objects.create(id=attempt_id, group=group)
        group.attempt_id, group.started_at = attempt_id, started_at
    else:
        if not attempt or group.attempt_id != attempt_id:
            raise ValidationError("录像尝试不存在或已失效")
        if operation == "complete":
            if group.completed:
                if group.ended_at != ended_at:
                    raise ValidationError("重复完成时间冲突")
                return session
            if not ended_at or not group.started_at < ended_at <= group.started_at + timedelta(
                minutes=30
            ):
                raise ValidationError("本组结束时间无效")
            if ended_at > timezone.now() + timedelta(seconds=30):
                raise ValidationError("本组结束时间超出当前时间")
            group.ended_at, group.completed = ended_at, True
        elif operation == "abandon":
            if group.completed:
                raise ValidationError("已完成组无需重做，请补传视频")
            attempt.abandoned_at = timezone.now()
            attempt.save(update_fields=["abandoned_at"])
            group.attempt_id, group.started_at = None, None
            from .video_tasks import cleanup_unbound_training_video

            for video in attempt.videos.filter(training_record__isnull=True):
                video.cleanup_requested_at = timezone.now()
                # 未完成尝试不属于正式研究记录，移交既有解绑清理流程。
                video.project_patient = None
                video.save(update_fields=["cleanup_requested_at", "project_patient"])
                transaction.on_commit(
                    lambda vid=video.id: cleanup_unbound_training_video.delay(vid)
                )
        else:
            raise ValidationError("操作无效")
    group.save()
    return session


def attach_set_video(video):
    if not video.motion_attempt_id:
        return
    attempt = MotionSetAttempt.objects.select_related("group").get(pk=video.motion_attempt_id)
    group = MotionTrainingSet.objects.select_for_update().get(pk=attempt.group_id)
    if attempt.abandoned_at or not group.completed or group.attempt_id != attempt.id:
        raise ValidationError("未完成或已放弃的组不能发布")
    if group.video_id and group.video_id != video.id:
        raise ValidationError("本组已有正式视频")
    group.video = video
    group.save(update_fields=["video"])
    session = MotionTrainingSession.objects.select_for_update().get(pk=group.session_id)
    if (
        session.groups.filter(completed=True, video__status="attached").count()
        == session.planned_sets
    ):
        if not session.completed_at:
            session.completed_at = timezone.now()
            session.save(update_fields=["completed_at"])


@transaction.atomic
def recover_session(pp, *, client_session_id, prescription_action, started_at, completed_sets):
    """接收用户已安全保存的完成声明；可补传旧方，不能用来开始新组。"""
    pp = ProjectPatient.objects.select_for_update().select_related("project").get(pk=pp.pk)
    action = (
        PrescriptionAction.objects.select_related("prescription")
        .filter(
            pk=prescription_action,
            prescription__project_patient=pp,
            dose_mode="sets",
        )
        .first()
    )
    if not action or action.prescription.status not in {"active", "archived", "terminated"}:
        raise ValidationError("原运动计划不可恢复")
    session = MotionTrainingSession.objects.filter(client_session_id=client_session_id).first()
    if session and session.project_patient_id != pp.pk:
        raise Http404
    if session and (
        session.prescription_action_id != action.pk or session.started_at != started_at
    ):
        raise ValidationError("原运动会话参数不符")
    if started_at > timezone.now() + timedelta(seconds=30) or (
        action.prescription.effective_at and started_at < action.prescription.effective_at
    ):
        raise ValidationError("运动开始时间不在原计划有效范围内")
    if not session:
        session = MotionTrainingSession.objects.create(
            project_patient=pp,
            prescription_action=action,
            client_session_id=client_session_id,
            planned_sets=action.sets,
            repetitions=action.repetitions,
            count_unit=action.count_unit,
            started_at=started_at,
            training_date=timezone.localdate(started_at),
        )
    for item in completed_sets:
        index, attempt_id = item["index"], item["attempt_id"]
        start, end = item["started_at"], item["ended_at"]
        if (
            not 1 <= index <= session.planned_sets
            or not started_at <= start < end <= start + timedelta(minutes=30)
        ):
            raise ValidationError("已完成组序号或起止时间无效")
        if end > timezone.now() + timedelta(seconds=30):
            raise ValidationError("已完成组时间超出当前时间")
        if action.prescription.archived_at and start > action.prescription.archived_at:
            raise ValidationError("不能按已失效计划开始新组")
        if index > 1:
            previous = session.groups.filter(index=index - 1, completed=True).first()
            if not previous or start < previous.ended_at + timedelta(seconds=180):
                raise ValidationError("已完成组缺少上一组或三分钟休息")
        group, _ = MotionTrainingSet.objects.get_or_create(session=session, index=index)
        if group.completed:
            if (group.attempt_id, group.started_at, group.ended_at) != (attempt_id, start, end):
                raise ValidationError("已完成组声明冲突")
            continue
        attempt = MotionSetAttempt.objects.filter(pk=attempt_id).first()
        if attempt and (attempt.group_id != group.id or attempt.abandoned_at):
            raise ValidationError("录像尝试已放弃或归属不符")
        if group.started_at and group.attempt_id == attempt_id and group.started_at != start:
            raise ValidationError("录像尝试开始时间与原始快照冲突")
        if group.attempt_id and group.attempt_id != attempt_id:
            raise ValidationError("请先放弃旧录像尝试")
        if not attempt:
            MotionSetAttempt.objects.create(id=attempt_id, group=group)
        group.attempt_id, group.started_at, group.ended_at, group.completed = (
            attempt_id,
            start,
            end,
            True,
        )
        group.save()
    return session
