import json

from django.core.management.base import BaseCommand

from apps.prescriptions.cutover import preview_cutover, cutover_patient
from apps.studies.models import ProjectPatient


class Command(BaseCommand):
    help = "预览计数组处方切换；--apply 自动生成新版本并作废四动作旧训练"

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--project-patient", type=int)

    def handle(self, *args, **options):
        patients = ProjectPatient.objects.select_related("project").order_by("id")
        if options["project_patient"]:
            patients = patients.filter(pk=options["project_patient"])
        for pp in patients.iterator():
            result = cutover_patient(pp.id) if options["apply"] else preview_cutover(pp)
            self.stdout.write(json.dumps(result, ensure_ascii=False))
