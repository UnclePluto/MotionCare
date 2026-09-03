import importlib
import json
from dataclasses import dataclass
from statistics import mean


PP_TINYPOSE_MODEL_NAME = "PP-TinyPose_128x96"
DEFAULT_SAMPLE_FPS = 5.0
CAP_PROP_POS_MSEC = 0
CAP_PROP_FPS = 5
COCO_JOINT_INDEXES = {
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow": 7,
    "right_elbow": 8,
    "left_wrist": 9,
    "right_wrist": 10,
    "left_hip": 11,
    "right_hip": 12,
}


class MotionAnalysisDependencyError(RuntimeError):
    pass


class MotionAnalysisInferenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class VideoKeypointExtraction:
    frames: list[dict]
    decoded_frame_count: int
    inferred_frame_count: int
    source_fps: float


def load_motion_analysis_runtime():
    try:
        cv2 = importlib.import_module("cv2")
        paddlex = importlib.import_module("paddlex")
    except ModuleNotFoundError as exc:
        raise MotionAnalysisDependencyError(
            "动作分析依赖缺失，请安装 motion-analysis 可选依赖"
        ) from exc
    create_model = getattr(paddlex, "create_model", None)
    if create_model is None:
        raise MotionAnalysisDependencyError("PaddleX 未提供 create_model")
    return cv2, create_model


def _result_payload(result):
    payload = getattr(result, "json", None)
    if callable(payload):
        payload = payload()
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError as exc:
            raise MotionAnalysisInferenceError("PP-TinyPose 返回了无效 JSON") from exc
    if not isinstance(payload, dict):
        raise MotionAnalysisInferenceError("PP-TinyPose 结果缺少 JSON 数据")
    return payload


def _score_person(person):
    try:
        keypoints = person["keypoints"]
        scores = [float(keypoints[index][2]) for index in COCO_JOINT_INDEXES.values()]
    except (KeyError, IndexError, TypeError, ValueError):
        return None
    return mean(scores)


def convert_paddlex_result(result, *, frame_width, frame_height):
    if frame_width <= 0 or frame_height <= 0:
        raise MotionAnalysisInferenceError("视频帧尺寸无效")
    payload = _result_payload(result)
    try:
        people = payload["res"]["kpts"]
    except (KeyError, TypeError) as exc:
        raise MotionAnalysisInferenceError("PP-TinyPose 结果结构无效") from exc
    if not isinstance(people, list):
        raise MotionAnalysisInferenceError("PP-TinyPose 人体关键点结构无效")

    scored_people = [
        (score, person)
        for person in people
        if (score := _score_person(person)) is not None
    ]
    if not scored_people:
        return {}
    _, selected = max(scored_people, key=lambda item: item[0])
    return {
        name: {
            "x": max(0.0, min(1.0, float(selected["keypoints"][index][0]) / frame_width)),
            "y": max(0.0, min(1.0, float(selected["keypoints"][index][1]) / frame_height)),
            "score": float(selected["keypoints"][index][2]),
        }
        for name, index in COCO_JOINT_INDEXES.items()
    }


def _first_prediction(model, frame):
    predictions = model.predict(frame)
    try:
        return next(iter(predictions))
    except StopIteration as exc:
        raise MotionAnalysisInferenceError("PP-TinyPose 未返回推理结果") from exc


def create_pose_model(*, device="cpu"):
    _, create_model = load_motion_analysis_runtime()
    return create_model(
        model_name=PP_TINYPOSE_MODEL_NAME,
        device=device,
        use_hpip=False,
    )


def warm_up_pose_model(video_path, *, model, capture=None):
    cv2 = None
    if capture is None:
        cv2, _ = load_motion_analysis_runtime()
        capture = cv2.VideoCapture(str(video_path))
    try:
        if not capture.isOpened():
            raise MotionAnalysisInferenceError("训练视频无法解码")
        ok, frame = capture.read()
        if not ok:
            raise MotionAnalysisInferenceError("训练视频没有可分析帧")
        _first_prediction(model, frame)
    finally:
        capture.release()


def extract_video_keypoint_frames_with_stats(
    video_path,
    *,
    sample_fps=DEFAULT_SAMPLE_FPS,
    model=None,
    capture=None,
):
    if sample_fps is not None and sample_fps <= 0:
        raise ValueError("sample_fps 必须大于 0 或为 None")

    cv2 = None
    if model is None or capture is None:
        cv2, _ = load_motion_analysis_runtime()
    if model is None:
        model = create_pose_model()
    if capture is None:
        capture = cv2.VideoCapture(str(video_path))

    try:
        if not capture.isOpened():
            raise MotionAnalysisInferenceError("训练视频无法解码")
        fallback_fps = sample_fps or DEFAULT_SAMPLE_FPS
        source_fps = float(capture.get(CAP_PROP_FPS) or fallback_fps)
        sample_interval_ms = None if sample_fps is None else 1000.0 / sample_fps
        next_sample_ms = 0.0
        decoded_frame_count = 0
        frames = []

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            frame_index = decoded_frame_count
            decoded_frame_count += 1
            timestamp_ms = float(capture.get(CAP_PROP_POS_MSEC) or 0.0)
            if timestamp_ms <= 0 and frame_index:
                timestamp_ms = frame_index * 1000.0 / source_fps
            if sample_interval_ms is not None and timestamp_ms + 0.5 < next_sample_ms:
                continue

            try:
                frame_height, frame_width = frame.shape[:2]
            except (AttributeError, TypeError, ValueError) as exc:
                raise MotionAnalysisInferenceError("视频帧尺寸无效") from exc
            frames.append(
                {
                    "timestamp_ms": int(round(timestamp_ms)),
                    "keypoints": convert_paddlex_result(
                        _first_prediction(model, frame),
                        frame_width=frame_width,
                        frame_height=frame_height,
                    ),
                }
            )
            if sample_interval_ms is not None:
                while next_sample_ms <= timestamp_ms + 0.5:
                    next_sample_ms += sample_interval_ms

        if not frames:
            raise MotionAnalysisInferenceError("训练视频没有可分析帧")
        return VideoKeypointExtraction(
            frames=frames,
            decoded_frame_count=decoded_frame_count,
            inferred_frame_count=len(frames),
            source_fps=source_fps,
        )
    finally:
        capture.release()


def extract_video_keypoint_frames(
    video_path,
    *,
    sample_fps=DEFAULT_SAMPLE_FPS,
    model=None,
    capture=None,
):
    return extract_video_keypoint_frames_with_stats(
        video_path,
        sample_fps=sample_fps,
        model=model,
        capture=capture,
    ).frames
