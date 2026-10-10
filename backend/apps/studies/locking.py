"""Shared parent locks; callers own the transaction and business validation."""

from rest_framework.exceptions import ValidationError

from .models import ProjectPatient, StudyProject


def lock_project_patients(*bindings):
    """Lock P -> PP in primary-key order, then verify the discovery snapshots.

    Do not acquire child locks before calling this function, or chase a changed
    parent while holding PP. Authorization and project-status policy stay with
    the caller; recovery operations can legitimately use an archived project.
    """
    snapshots = {binding.pk: (binding.project_id, binding.patient_id) for binding in bindings}
    project_ids = {project_id for project_id, _patient_id in snapshots.values()}
    projects = {
        project.pk: project
        for project in StudyProject.objects.select_for_update(of=("self",))
        .filter(pk__in=project_ids)
        .order_by("pk")
    }
    if set(projects) != project_ids:
        raise ValidationError({"project_patient": "所属项目已变化，请刷新后重试。"})
    locked = {
        binding.pk: binding
        for binding in ProjectPatient.objects.select_for_update(of=("self",))
        .filter(pk__in=snapshots)
        .order_by("pk")
    }
    if set(locked) != set(snapshots) or any(
        (locked[pk].project_id, locked[pk].patient_id) != snapshot
        for pk, snapshot in snapshots.items()
    ):
        raise ValidationError({"project_patient": "入组关系已变化，请刷新后重试。"})
    for binding in locked.values():
        binding.project = projects[binding.project_id]
    return locked


def lock_project_patient(project_patient_id):
    """Discover without locks; obtain the authoritative binding under P -> PP."""
    snapshot = ProjectPatient.objects.get(pk=project_patient_id)
    return lock_project_patients(snapshot)[snapshot.pk]
