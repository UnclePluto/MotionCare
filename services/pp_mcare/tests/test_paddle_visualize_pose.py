from __future__ import annotations

import numpy as np
import pytest

from pp_mcare.pose_inference import PersonPose


def _person() -> PersonPose:
    points = [[10.0 + index * 2, 12.0 + index, 0.95] for index in range(17)]
    return PersonPose.from_coco_keypoints(points, frame_width=80, frame_height=60)


def test_renderer_passes_one_pixel_space_person_and_does_not_mutate_input(monkeypatch):
    from pp_mcare import paddle_visualize_pose

    frame = np.zeros((60, 80, 3), dtype=np.uint8)
    original = frame.copy()
    captured = {}

    def visualizer(image, results, *, visual_thresh, returnimg):
        captured["image"] = image
        captured["results"] = results
        captured["threshold"] = visual_thresh
        captured["returnimg"] = returnimg
        image[0, 0] = 255
        return image

    monkeypatch.setattr(paddle_visualize_pose, "_visualize_pose", visualizer)

    rendered = paddle_visualize_pose.render_primary_pose(frame, _person(), threshold=0.7)

    assert np.array_equal(frame, original)
    assert rendered[0, 0].tolist() == [255, 255, 255]
    assert captured["image"] is not frame
    assert captured["threshold"] == 0.7
    assert captured["returnimg"] is True
    assert captured["results"]["keypoint"] == ([_person().raw_keypoints], [0.95])
    assert captured["results"]["bbox"] == [(10, 12, 42, 28)]


def test_renderer_never_invokes_visualizer_without_a_primary_person(monkeypatch):
    from pp_mcare import paddle_visualize_pose

    called = False

    def visualizer(*args, **kwargs):
        nonlocal called
        called = True

    monkeypatch.setattr(paddle_visualize_pose, "_visualize_pose", visualizer)

    with pytest.raises(TypeError, match="PersonPose"):
        paddle_visualize_pose.render_primary_pose(np.zeros((20, 20, 3), dtype=np.uint8), None)

    assert called is False


def test_official_visualizer_keeps_coco_threshold_edge_and_color_semantics():
    from pp_mcare.paddle_visualize_pose import _visualize_pose, get_color

    image = np.zeros((64, 64, 3), dtype=np.uint8)
    points = [[8.0 + index * 2, 8.0 + index * 2, 0.59] for index in range(17)]
    points[5][2] = 0.95
    points[7][2] = 0.95

    rendered = _visualize_pose(
        image,
        {"keypoint": ([points], [0.95])},
        visual_thresh=0.6,
        returnimg=True,
    )

    assert get_color(2) == (222, 102, 174)
    assert rendered.shape == image.shape
    assert rendered.dtype == np.uint8
    assert rendered.sum() > 0
    assert np.count_nonzero(rendered) < rendered.size
