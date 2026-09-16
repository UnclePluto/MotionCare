from .models import MotionTrainingSession, TrainingRecord


def action_lineage(action):
    """系统迁移中原样复制的动作继续累计，医生主动改方不合并。"""
    ids = [action.id]
    previous = action.migrated_from
    while previous and previous.id not in ids:
        ids.append(previous.id)
        previous = previous.migrated_from
    return ids


def ordinary_records(project_patient):
    return TrainingRecord.objects.filter(
        project_patient=project_patient,
        invalidated_at__isnull=True,
        video__motion_attempt__isnull=True,
    )


def completed_count(project_patient, action, start, end):
    ids = action_lineage(action)
    ordinary = (
        ordinary_records(project_patient)
        .filter(
            prescription_action_id__in=ids,
            status="completed",
            training_date__gte=start,
            training_date__lte=end,
        )
        .count()
    )
    counted = MotionTrainingSession.objects.filter(
        project_patient=project_patient,
        prescription_action_id__in=ids,
        completed_at__isnull=False,
        training_date__gte=start,
        training_date__lte=end,
    ).count()
    return ordinary + counted
