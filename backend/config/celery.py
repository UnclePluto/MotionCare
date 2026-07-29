import os

from celery import Celery, bootsteps

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
app = Celery("motioncare")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


def validate_training_video_worker_environment():
    from apps.training.video_staging import validate_video_runtime_environment

    validate_video_runtime_environment(check_disk_space=False)


class TrainingVideoWorkerHealthCheck(bootsteps.StartStopStep):
    label = "training video runtime health check"

    def start(self, worker):
        validate_training_video_worker_environment()


app.steps["worker"].add(TrainingVideoWorkerHealthCheck)
