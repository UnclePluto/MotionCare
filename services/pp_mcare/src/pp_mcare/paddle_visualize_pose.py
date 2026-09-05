# Copyright (c) 2021 PaddlePaddle Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""PaddleDetection 2.9 COCO pose rendering, narrowed to one primary person."""

from __future__ import annotations

import importlib
import math
from collections.abc import Mapping

from .pose_inference import PersonPose


COCO_EDGES = (
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
COLORS = (
    (255, 0, 0),
    (255, 85, 0),
    (255, 170, 0),
    (255, 255, 0),
    (170, 255, 0),
    (85, 255, 0),
    (0, 255, 0),
    (0, 255, 85),
    (0, 255, 170),
    (0, 255, 255),
    (0, 170, 255),
    (0, 85, 255),
    (0, 0, 255),
    (85, 0, 255),
    (170, 0, 255),
    (255, 0, 255),
    (255, 0, 170),
    (255, 0, 85),
)


class PoseVisualizationError(RuntimeError):
    """骨架绘制输入或推理图像依赖不可用。"""


def _visual_runtime():
    try:
        cv2 = importlib.import_module("cv2")
        np = importlib.import_module("numpy")
    except ModuleNotFoundError as exc:
        raise PoseVisualizationError("骨架绘制需要 inference extra 中的 OpenCV 和 NumPy") from exc
    return cv2, np


def get_color(idx):
    """Copied from PaddleDetection release/2.9 deploy/python/visualize.py."""
    idx = idx * 3
    color = ((37 * idx) % 255, (17 * idx) % 255, (29 * idx) % 255)
    return color


def _visualize_pose(
    imgfile,
    results: Mapping[str, object],
    visual_thresh=0.6,
    save_name="pose.jpg",
    save_dir="output",
    returnimg=False,
    ids=None,
):
    """PaddleDetection's COCO branch, without unrelated file-output helpers."""
    del save_name, save_dir
    cv2, np = _visual_runtime()
    skeletons, _scores = results["keypoint"]
    skeletons = np.array(skeletons)
    if len(skeletons) > 0 and skeletons.shape[1] != 17:
        raise PoseVisualizationError("骨架绘制只接受 COCO 17 点")

    img = imgfile
    color_set = results.get("colors")
    if "bbox" in results and ids is None:
        for index, rect in enumerate(results["bbox"]):
            xmin, ymin, xmax, ymax = rect
            color = COLORS[0] if color_set is None else COLORS[color_set[index] % len(COLORS)]
            cv2.rectangle(img, (xmin, ymin), (xmax, ymax), color, 1)

    canvas = img.copy()
    for point_index in range(17):
        for person_index in range(len(skeletons)):
            if skeletons[person_index][point_index, 2] < visual_thresh:
                continue
            if ids is None:
                color = (
                    COLORS[point_index]
                    if color_set is None
                    else COLORS[color_set[person_index] % len(COLORS)]
                )
            else:
                color = get_color(ids[person_index])
            cv2.circle(
                canvas,
                tuple(skeletons[person_index][point_index, 0:2].astype("int32")),
                2,
                color,
                thickness=-1,
            )

    for edge_index, edge in enumerate(COCO_EDGES):
        for person_index in range(len(skeletons)):
            if (
                skeletons[person_index][edge[0], 2] < visual_thresh
                or skeletons[person_index][edge[1], 2] < visual_thresh
            ):
                continue
            current = canvas.copy()
            x_values = [
                skeletons[person_index][edge[0], 1],
                skeletons[person_index][edge[1], 1],
            ]
            y_values = [
                skeletons[person_index][edge[0], 0],
                skeletons[person_index][edge[1], 0],
            ]
            mean_x = np.mean(x_values)
            mean_y = np.mean(y_values)
            length = ((x_values[0] - x_values[1]) ** 2 + (y_values[0] - y_values[1]) ** 2) ** 0.5
            angle = math.degrees(math.atan2(x_values[0] - x_values[1], y_values[0] - y_values[1]))
            polygon = cv2.ellipse2Poly(
                (int(mean_y), int(mean_x)),
                (int(length / 2), 2),
                int(angle),
                0,
                360,
                1,
            )
            if ids is None:
                color = (
                    COLORS[edge_index]
                    if color_set is None
                    else COLORS[color_set[person_index] % len(COLORS)]
                )
            else:
                color = get_color(ids[person_index])
            cv2.fillConvexPoly(current, polygon, color)
            canvas = cv2.addWeighted(canvas, 0.4, current, 0.6, 0)
    if returnimg:
        return canvas
    raise PoseVisualizationError("pp-mcare 骨架绘制仅支持返回内存图像")


def render_primary_pose(image, person: PersonPose, threshold=0.6):
    if not isinstance(person, PersonPose):
        raise TypeError("person 必须是 PersonPose")
    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        raise PoseVisualizationError("骨架阈值必须是有限数字")
    threshold = float(threshold)
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise PoseVisualizationError("骨架阈值必须位于 0 到 1")
    copy = getattr(image, "copy", None)
    if not callable(copy):
        raise PoseVisualizationError("骨架帧必须可复制")
    rendered_input = copy()
    try:
        height, width = rendered_input.shape[:2]
    except (AttributeError, TypeError, ValueError) as exc:
        raise PoseVisualizationError("骨架帧尺寸无效") from exc
    bbox = (
        int(round(person.bbox[0] * width)),
        int(round(person.bbox[1] * height)),
        int(round(person.bbox[2] * width)),
        int(round(person.bbox[3] * height)),
    )
    results = {
        "keypoint": ([person.raw_keypoints], [person.mean_score]),
        "bbox": [bbox],
    }
    return _visualize_pose(
        rendered_input,
        results,
        visual_thresh=threshold,
        returnimg=True,
    )
