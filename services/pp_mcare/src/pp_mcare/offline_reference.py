"""Offline reference tooling. No service token, business API, database or cloud writes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path

from .actions.base import PoseFrame
from .media import probe_source_video
from .pose_inference import open_full_frame_pose_stream
from .subject_tracker import PrimarySubjectTracker


def extract_poses(video_path, output_path, *, refine_pose=False):
    output = Path(output_path)
    fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    started = time.monotonic()
    try:
        with os.fdopen(fd, "w") as sink:
            source = probe_source_video(video_path)
            with Path(video_path).open("rb") as video:
                digest = hashlib.file_digest(video, "sha256").hexdigest()
            sink.write(
                json.dumps(
                    {
                        "kind": "metadata",
                        "schema_version": 1,
                        "pose_preprocessing_version": "body-crop-v1"
                        if refine_pose
                        else "full-image-v1",
                        "video_sha256": digest,
                        "frame_count": source.frame_count,
                        "width": source.width,
                        "height": source.height,
                        "fps": source.fps,
                        "duration_seconds": source.duration_seconds,
                    }
                )
                + "\n"
            )
            tracker = PrimarySubjectTracker()
            stream_options = {}
            if refine_pose:
                from .pose_inference import create_pose_model
                from .pose_refinement import BodyCropPoseModel

                stream_options["model"] = BodyCropPoseModel(create_pose_model())
            with open_full_frame_pose_stream(video_path, **stream_options) as stream:
                count = 0
                for frame in stream:
                    tracked = tracker.observe(frame)
                    action = tracked.to_action_frame()
                    record = {
                        "kind": "frame",
                        "timestamp_ms": frame.timestamp_ms,
                        "coordinate_aspect_ratio": source.width / source.height,
                        "named_keypoints": dict(action.named_keypoints) if action else {},
                    }
                    sink.write(json.dumps(record, allow_nan=False) + "\n")
                    count += 1
                    if count % 500 == 0:
                        sink.flush()
                        print(f"frames={count}/{source.frame_count}", flush=True)
                if (
                    not count
                    == stream.decoded_frame_count
                    == stream.inferred_frame_count
                    == source.frame_count
                ):
                    raise ValueError("离线提取帧数不一致")
                summary = {
                    "kind": "summary",
                    "decoded_frame_count": stream.decoded_frame_count,
                    "inferred_frame_count": stream.inferred_frame_count,
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "tracking": dict(tracker.finish()),
                }
            sink.write(json.dumps(summary, allow_nan=False) + "\n")
        return summary
    except BaseException:
        output.unlink(missing_ok=True)
        raise


def read_pose_cache(path):
    with Path(path).open() as source:
        metadata = json.loads(next(source))
        if metadata.get("kind") != "metadata":
            raise ValueError("缺少离线样本元数据")
        count = 0
        previous = -1
        finished = False
        for line in source:
            record = json.loads(line)
            if finished:
                raise ValueError("离线样本包含多余记录")
            if record.get("kind") == "summary":
                if (
                    not count
                    == metadata["frame_count"]
                    == record["decoded_frame_count"]
                    == record["inferred_frame_count"]
                ):
                    raise ValueError("离线样本帧数不完整")
                finished = True
                continue
            if record.get("kind") != "frame" or record["timestamp_ms"] <= previous:
                raise ValueError("离线样本时间轴无效")
            previous = record["timestamp_ms"]
            count += 1
            yield PoseFrame(
                timestamp_ms=previous,
                named_keypoints=record["named_keypoints"],
                coordinate_aspect_ratio=record["coordinate_aspect_ratio"],
            )
        if not finished:
            raise ValueError("离线样本缺少完整结束记录")


def evaluate_reference(
    cache_path, plugin, report_path, *, manual_total, manual_left=None, manual_right=None
):
    for value in (manual_total, manual_left, manual_right):
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, int) or value < 0
        ):
            raise ValueError("人工计数必须是非负整数")
    if manual_total is None:
        raise ValueError("缺少人工总次数")
    with Path(cache_path).open() as source:
        metadata = json.loads(next(source))
    expected_preprocessing = getattr(plugin, "pose_preprocessing_version", "full-image-v1")
    if metadata.get("pose_preprocessing_version") != expected_preprocessing:
        raise ValueError("离线样本预处理版本与动作插件不一致")
    analysis = plugin.analyze(read_pose_cache(cache_path)).to_json_dict()
    with Path(cache_path).open("rb") as source:
        cache_hash = hashlib.file_digest(source, "sha256").hexdigest()
    comparison = {
        "manual_total": manual_total,
        "total_error": analysis["total_count"] - manual_total,
        "matches_manual_total": analysis["total_count"] == manual_total,
    }
    for side, expected in [("left", manual_left), ("right", manual_right)]:
        if expected is not None:
            comparison[f"manual_{side}"] = expected
            comparison[f"{side}_error"] = analysis[f"{side}_event_count"] - expected
    report = {
        "scope": "offline_reference_only",
        "pose_cache_sha256": cache_hash,
        "source": metadata,
        "analysis": analysis,
        "comparison": comparison,
        "limitations": [
            "single_reference_per_action",
            "not_independent_holdout",
            "quality_not_manually_labeled",
        ],
    }
    fd = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as sink:
        json.dump(report, sink, ensure_ascii=False, indent=2, allow_nan=False)
        sink.write("\n")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--refine-pose", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            extract_poses(args.video, args.output, refine_pose=args.refine_pose), ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
