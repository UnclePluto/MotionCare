import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from apps.studies.models import ProjectPatient
from apps.training.history import preview_legacy_training, invalidate_legacy_training


class Command(BaseCommand):
    help = "预览四动作旧模式训练作废影响（默认只读）"

    def add_arguments(self, parser):
        parser.add_argument("--project-patient", type=int, required=True)
        parser.add_argument(
            "--execute", action="store_true", help="执行作废，要求患者已有处方切换标记"
        )

    def handle(self, *args, **options):
        try:
            project_patient = ProjectPatient.objects.get(pk=options["project_patient"])
        except ProjectPatient.DoesNotExist as exc:
            raise CommandError("患者项目绑定不存在") from exc
        try:
            result = (
                invalidate_legacy_training(project_patient)
                if options["execute"]
                else preview_legacy_training(project_patient)
            )
        except ValidationError as exc:
            raise CommandError("；".join(exc.messages)) from exc
        self.stdout.write(json.dumps(result, ensure_ascii=False))
