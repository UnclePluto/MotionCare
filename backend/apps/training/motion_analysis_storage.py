import uuid

from .video_models import TrainingVideo


def build_skeleton_object_key(video: TrainingVideo) -> str:
    return (
        f"motion-analysis/{video.project_patient_id}/"
        f"{video.training_date:%Y/%m}/{uuid.uuid4()}/skeleton.mp4"
    )
