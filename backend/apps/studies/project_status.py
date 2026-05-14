from rest_framework.exceptions import ValidationError

from apps.studies.models import StudyProject


PROJECT_COMPLETED_DETAIL = "项目已完结，不能继续新增患者或录入访视。"
PROJECT_COMPLETED_GROUP_DETAIL = "项目已完结，不能修改分组配置。"
PROJECT_COMPLETED_UNBIND_DETAIL = "项目已完结，不能解绑患者。"


def is_project_completed(project: StudyProject) -> bool:
    return project.status == StudyProject.Status.ARCHIVED


def ensure_project_open(project: StudyProject, detail: str = PROJECT_COMPLETED_DETAIL) -> None:
    if is_project_completed(project):
        raise ValidationError({"detail": detail})
