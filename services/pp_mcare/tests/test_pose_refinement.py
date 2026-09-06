import importlib
from types import SimpleNamespace

import numpy as np
import pytest

from pp_mcare.pose_inference import convert_paddlex_people


def test_crop_refinement_maps_padded_coordinates_back_to_original_frame():
    module = importlib.import_module("pp_mcare.pose_refinement")

    class Model:
        def __init__(self):
            self.calls = 0

        def predict(self, image):
            self.calls += 1
            if self.calls == 1:
                points = [(40 + i * 1.25, 40 + i * 7.5, 0.9) for i in range(17)]
            else:
                height, width = image.shape[:2]
                points = [(width / 2, height / 2, 1.02)] * 17
            return [SimpleNamespace(json={"res": {"kpts": [{"keypoints": points}]}})]

    model = Model()
    refined = module.BodyCropPoseModel(model)
    people = convert_paddlex_people(
        next(iter(refined.predict(np.zeros((200, 100, 3), dtype=np.uint8)))),
        frame_width=100,
        frame_height=200,
    )
    assert model.calls == 2
    assert people[0].named_keypoints["left_shoulder"] == pytest.approx((0.5, 0.5, 1.0))


def test_empty_coarse_result_stays_empty_without_inventing_a_person():
    module = importlib.import_module("pp_mcare.pose_refinement")

    class Model:
        def predict(self, image):
            return [SimpleNamespace(json={"res": {"kpts": []}})]

    result = next(
        iter(module.BodyCropPoseModel(Model()).predict(np.zeros((20, 20, 3), dtype=np.uint8)))
    )
    assert convert_paddlex_people(result, frame_width=20, frame_height=20) == ()


def test_preprocessing_is_selected_by_plugin_without_changing_legacy_default(monkeypatch):
    module = importlib.import_module("pp_mcare.pose_refinement")
    inference = importlib.import_module("pp_mcare.pose_inference")
    model = object()
    monkeypatch.setattr(inference, "create_pose_model", lambda: model)
    assert module.pose_stream_options(SimpleNamespace()) == {}
    options = module.pose_stream_options(SimpleNamespace(pose_preprocessing_version="body-crop-v1"))
    assert isinstance(options["model"], module.BodyCropPoseModel)
    assert options["model"].model is model
    with pytest.raises(ValueError, match="预处理"):
        module.pose_stream_options(SimpleNamespace(pose_preprocessing_version="unknown"))
