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


def test_official_visualizer_observably_preserves_edges_threshold_stick_alpha_and_colors(
    monkeypatch,
):
    from pp_mcare import paddle_visualize_pose

    calls = {"rectangle": [], "circle": [], "ellipse": [], "fill": [], "blend": []}

    class FakeCv2:
        def rectangle(self, image, start, end, color, width):
            calls["rectangle"].append((start, end, color, width))

        def circle(self, image, center, radius, color, thickness):
            calls["circle"].append((center, radius, color, thickness))

        def ellipse2Poly(self, center, axes, angle, start, end, delta):
            calls["ellipse"].append((center, axes, angle, start, end, delta))
            return np.array([[0, 0], [1, 0], [1, 1]], dtype=np.int32)

        def fillConvexPoly(self, image, polygon, color):
            calls["fill"].append(color)

        def addWeighted(self, first, alpha, second, beta, gamma):
            calls["blend"].append((alpha, beta, gamma))
            return first

    monkeypatch.setattr(
        paddle_visualize_pose,
        "_visual_runtime",
        lambda: (FakeCv2(), np),
    )
    points = [[float(index), float(index + 1), 0.6] for index in range(17)]
    expected_edges = (
        (0, 1),
        (0, 2),
        (1, 3),
        (2, 4),
        (3, 5),
        (4, 6),
        (5, 7),
        (6, 8),
        (7, 9),
        (8, 10),
        (5, 11),
        (6, 12),
        (11, 13),
        (12, 14),
        (13, 15),
        (14, 16),
        (11, 12),
    )

    paddle_visualize_pose._visualize_pose(
        np.zeros((30, 30, 3), dtype=np.uint8),
        {"keypoint": ([points], [0.9]), "bbox": [(1, 2, 20, 25)]},
        visual_thresh=0.6,
        returnimg=True,
    )

    assert calls["rectangle"] == [((1, 2), (20, 25), (255, 0, 0), 1)]
    assert len(calls["circle"]) == 17
    assert calls["circle"][0][1:] == (2, (255, 0, 0), -1)
    assert len(calls["ellipse"]) == 17
    assert [arguments[0] for arguments in calls["ellipse"]] == [
        (int((start + end) / 2), int((start + end + 2) / 2)) for start, end in expected_edges
    ]
    assert all(arguments[1][1] == 2 for arguments in calls["ellipse"])
    assert calls["fill"] == list(paddle_visualize_pose.COLORS[:17])
    assert calls["blend"] == [(0.4, 0.6, 0)] * 17

    for values in calls.values():
        values.clear()
    points[0][2] = 0.599
    paddle_visualize_pose._visualize_pose(
        np.zeros((30, 30, 3), dtype=np.uint8),
        {"keypoint": ([points], [0.9])},
        visual_thresh=0.6,
        returnimg=True,
    )

    assert len(calls["circle"]) == 16
    assert len(calls["ellipse"]) == 15
    # Edges 0 and 1 touch the below-threshold nose; the first drawn edge is index 2.
    assert calls["fill"][0] == (255, 170, 0)
