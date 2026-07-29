import json
import shlex
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from django.conf import settings


def _point(frame, name):
    return frame.get("keypoints", {}).get(name, {})


def _frame_state(frame):
    shoulder = _point(frame, "left_shoulder")
    wrist = _point(frame, "left_wrist")
    score = min(float(shoulder.get("score", 0)), float(wrist.get("score", 0)))
    shoulder_y = float(shoulder.get("y", 0.5))
    wrist_y = float(wrist.get("y", 0.5))
    if wrist_y <= shoulder_y - 0.16:
        return "up", score
    if wrist_y >= shoulder_y - 0.02:
        return "down", score
    return "transition", score


def analyze_shoulder_press_keypoints(frames):
    compressed = []
    for frame in frames:
        state, score = _frame_state(frame)
        if state == "transition":
            continue
        if not compressed or compressed[-1]["state"] != state:
            compressed.append(
                {
                    "state": state,
                    "timestamp_ms": int(frame.get("timestamp_ms", 0)),
                    "min_score": score,
                }
            )
        else:
            compressed[-1]["min_score"] = min(compressed[-1]["min_score"], score)

    rep_details = []
    index = 0
    while index + 2 < len(compressed):
        first, second, third = compressed[index : index + 3]
        if first["state"] == "down" and second["state"] == "up" and third["state"] == "down":
            duration = third["timestamp_ms"] - first["timestamp_ms"]
            flags = []
            if min(first["min_score"], second["min_score"], third["min_score"]) < 0.4:
                flags.append("low_confidence")
            if duration < 800 or duration > 8000:
                flags.append("tempo_abnormal")
            rep_details.append(
                {
                    "index": len(rep_details) + 1,
                    "start_ms": first["timestamp_ms"],
                    "end_ms": third["timestamp_ms"],
                    "is_standard": not flags,
                    "flags": flags,
                }
            )
            index += 2
        else:
            index += 1

    standard_count = sum(item["is_standard"] for item in rep_details)
    total_count = len(rep_details)
    return {
        "total_count": total_count,
        "standard_count": standard_count,
        "nonstandard_count": total_count - standard_count,
        "rep_details": rep_details,
        "quality_flags": ["camera_angle_unverified"],
    }


def extract_keypoint_frames(video_url: str) -> tuple[list[dict], str]:
    """Run an external PP-TinyPose adapter.

    The command receives ``--input <video> --output <json>``. The JSON must be
    either a frame list or ``{"frames": [...], "algorithm_version": "..."}``.
    """
    command = shlex.split(settings.PP_TINYPOSE_COMMAND)
    if not command:
        raise RuntimeError("PP-TinyPose 推理命令未配置")

    with tempfile.TemporaryDirectory(prefix="motioncare-pose-") as temp_dir:
        video_path = Path(temp_dir) / "input.mp4"
        output_path = Path(temp_dir) / "keypoints.json"
        source_path = Path(video_url)
        if source_path.is_file():
            shutil.copyfile(source_path, video_path)
        else:
            urllib.request.urlretrieve(video_url, video_path)
        completed = subprocess.run(
            [*command, "--input", str(video_path), "--output", str(output_path)],
            capture_output=True,
            text=True,
            timeout=settings.PP_TINYPOSE_TIMEOUT_SECONDS,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"PP-TinyPose 推理失败：{detail[-500:]}")
        if not output_path.exists():
            raise RuntimeError("PP-TinyPose 未生成关键点结果")
        payload = json.loads(output_path.read_text(encoding="utf-8"))

    if isinstance(payload, list):
        return payload, ""
    frames = payload.get("frames") if isinstance(payload, dict) else None
    if not isinstance(frames, list):
        raise RuntimeError("PP-TinyPose 关键点结果格式错误")
    return frames, str(payload.get("algorithm_version", ""))
