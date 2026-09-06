import importlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from pp_mcare.pose_inference import InferenceFrame, PersonPose


def test_extract_preserves_every_frame_and_missing_observation(tmp_path, monkeypatch):
    module = importlib.import_module("pp_mcare.offline_reference")
    video = tmp_path / "source.mp4"
    video.write_bytes(b"reference")
    image = np.zeros((200, 100, 3), dtype=np.uint8)
    person = PersonPose.from_coco_keypoints(
        [(50, 80, 0.9)] * 17,
        frame_width=100,
        frame_height=200,
    )
    frames = [
        InferenceFrame(t, 60, image, people)
        for t, people in [(0, (person,)), (17, ()), (33, (person,))]
    ]

    class Stream:
        decoded_frame_count = inferred_frame_count = 3
        source_fps = 60

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def __iter__(self):
            return iter(frames)

    monkeypatch.setattr(module, "open_full_frame_pose_stream", lambda _: Stream())
    monkeypatch.setattr(
        module,
        "probe_source_video",
        lambda _: SimpleNamespace(
            frame_count=3,
            width=100,
            height=200,
            fps=60,
            duration_seconds=0.05,
        ),
    )
    output = tmp_path / "poses.jsonl"
    summary = module.extract_poses(video, output)
    records = [json.loads(line) for line in output.read_text().splitlines()]
    assert summary["decoded_frame_count"] == summary["inferred_frame_count"] == 3
    assert [r["timestamp_ms"] for r in records if r["kind"] == "frame"] == [0, 17, 33]
    assert records[2]["named_keypoints"] == {}
    assert "left_ankle" in records[1]["named_keypoints"]
    assert records[1]["coordinate_aspect_ratio"] == 0.5
    replay = list(module.read_pose_cache(output))
    assert len(replay) == 3
    assert replay[1].named_keypoints == {}


def test_extraction_does_not_overwrite_an_existing_cache(tmp_path):
    module = importlib.import_module("pp_mcare.offline_reference")
    output = tmp_path / "poses.jsonl"
    output.write_text("keep")
    with pytest.raises(FileExistsError):
        module.extract_poses(tmp_path / "missing.mp4", output)
    assert output.read_text() == "keep"


def test_replay_rejects_truncated_cache(tmp_path):
    module = importlib.import_module("pp_mcare.offline_reference")
    output = tmp_path / "poses.jsonl"
    output.write_text(json.dumps({"kind": "metadata", "frame_count": 2}) + "\n")
    with pytest.raises(ValueError):
        list(module.read_pose_cache(output))


def test_manual_count_is_only_a_comparison_and_never_changes_algorithm_output(tmp_path):
    module = importlib.import_module("pp_mcare.offline_reference")
    from pp_mcare.actions.seated_row_v1 import SeatedRowV1Plugin
    from test_additional_action_plugins import sequence

    frames = list(sequence("seated-row", 2))
    cache = tmp_path / "poses.jsonl"
    rows = [
        {
            "kind": "metadata",
            "frame_count": len(frames),
            "video_sha256": "a" * 64,
            "pose_preprocessing_version": "full-image-v1",
        }
    ]
    rows += [
        {
            "kind": "frame",
            "timestamp_ms": f.timestamp_ms,
            "named_keypoints": dict(f.named_keypoints),
            "coordinate_aspect_ratio": 1.0,
        }
        for f in frames
    ]
    rows += [
        {"kind": "summary", "decoded_frame_count": len(frames), "inferred_frame_count": len(frames)}
    ]
    cache.write_text("".join(json.dumps(row) + "\n" for row in rows))
    actual = []
    for expected in (2, 99):
        report = module.evaluate_reference(
            cache, SeatedRowV1Plugin(), tmp_path / f"{expected}.json", manual_total=expected
        )
        actual.append(report["analysis"]["total_count"])
        assert report["comparison"]["total_error"] == 2 - expected
        assert report["comparison"]["matches_manual_total"] is (expected == 2)
    assert actual == [2, 2]


def test_evaluation_rejects_incompatible_pose_preprocessing(tmp_path):
    module = importlib.import_module("pp_mcare.offline_reference")
    from pp_mcare.actions.leg_kickback_v1 import LegKickbackV1Plugin

    cache = tmp_path / "poses.jsonl"
    cache.write_text(
        json.dumps({"kind": "metadata", "pose_preprocessing_version": "full-image-v1"}) + "\n"
    )
    with pytest.raises(ValueError, match="预处理"):
        module.evaluate_reference(
            cache, LegKickbackV1Plugin(), tmp_path / "report.json", manual_total=20
        )
