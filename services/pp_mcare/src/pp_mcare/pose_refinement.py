"""Optional single-frame body crop for the top-down TinyPose model."""

import math
from types import SimpleNamespace

from .pose_inference import _first_prediction, _result_payload


BODY_CROP_VERSION = "body-crop-v1"


def pose_stream_options(plugin):
    version = getattr(plugin, "pose_preprocessing_version", "full-image-v1")
    if version == "full-image-v1":
        return {}
    if version != BODY_CROP_VERSION:
        raise ValueError("不支持的姿态预处理版本")
    from .pose_inference import create_pose_model

    return {"model": BodyCropPoseModel(create_pose_model())}


class BodyCropPoseModel:
    def __init__(self, model):
        self.model = model

    def predict(self, image):
        import cv2

        coarse = _result_payload(_first_prediction(self.model, image))["res"]["kpts"]
        height, width = image.shape[:2]
        people = []
        for person in coarse:
            raw = person.get("keypoints", ())
            if len(raw) != 17 or any(
                len(p) != 3 or not all(math.isfinite(v) for v in p) for p in raw
            ):
                continue
            xs = [max(0, min(width, p[0])) for p in raw]
            ys = [max(0, min(height, p[1])) for p in raw]
            cx, cy = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
            crop_height = (max(ys) - min(ys)) * 1.25
            crop_width = max((max(xs) - min(xs)) * 1.25, crop_height * 0.85)
            if min(crop_width, crop_height) < 8:
                continue
            x1, x2 = math.floor(cx - crop_width / 2), math.ceil(cx + crop_width / 2)
            y1, y2 = math.floor(cy - crop_height / 2), math.ceil(cy + crop_height / 2)
            padded = cv2.copyMakeBorder(
                image,
                max(0, -y1),
                max(0, y2 - height),
                max(0, -x1),
                max(0, x2 - width),
                cv2.BORDER_CONSTANT,
                value=0,
            )
            crop = padded[max(0, y1) : max(0, y1) + y2 - y1, max(0, x1) : max(0, x1) + x2 - x1]
            result = _result_payload(_first_prediction(self.model, crop))["res"]["kpts"]
            for refined in result:
                points = refined.get("keypoints", ())
                if len(points) != 17 or any(
                    len(p) != 3 or not all(math.isfinite(v) for v in p) for p in points
                ):
                    continue
                # Model heatmaps are not probabilities and can slightly exceed 1.
                # Normalize at this adapter boundary; DTO validation remains strict.
                people.append(
                    {
                        "keypoints": [
                            (x + x1, y + y1, max(0, min(1, score))) for x, y, score in points
                        ]
                    }
                )
        return [SimpleNamespace(json={"res": {"kpts": people}})]
