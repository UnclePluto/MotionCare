import importlib
import json
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


def extract_video_keypoint_frames(
    video_path,
    *,
    sample_fps=DEFAULT_SAMPLE_FPS,
    model=None,
    capture=None,
):
    if sample_fps <= 0:
        raise ValueError("sample_fps 必须大于 0")

    cv2 = None
    create_model = None
    if model is None or capture is None:
        cv2, create_model = load_motion_analysis_runtime()
    if model is None:
        model = create_model(PP_TINYPOSE_MODEL_NAME)
    if capture is None:
        capture = cv2.VideoCapture(str(video_path))

    try:
        if not capture.isOpened():
            raise MotionAnalysisInferenceError("训练视频无法解码")
        source_fps = float(capture.get(CAP_PROP_FPS) or sample_fps)
        sample_interval_ms = 1000.0 / sample_fps
        next_sample_ms = 0.0
        frame_index = 0
        frames = []

        while True:
            ok, frame = capture.read()
            if not ok:
                break
            timestamp_ms = float(capture.get(CAP_PROP_POS_MSEC) or 0.0)
            if timestamp_ms <= 0 and frame_index:
                timestamp_ms = frame_index * 1000.0 / source_fps
            frame_index += 1
            if timestamp_ms + 0.5 < next_sample_ms:
                continue

            try:
                frame_height, frame_width = frame.shape[:2]
            except (AttributeError, TypeError, ValueError) as exc:
                raise MotionAnalysisInferenceError("视频帧尺寸无效") from exc
            result = _first_prediction(model, frame)
            frames.append(
                {
                    "timestamp_ms": int(round(timestamp_ms)),
                    "keypoints": convert_paddlex_result(
                        result,
                        frame_width=frame_width,
                        frame_height=frame_height,
                    ),
                }
            )
            while next_sample_ms <= timestamp_ms + 0.5:
                next_sample_ms += sample_interval_ms

        if not frames:
            raise MotionAnalysisInferenceError("训练视频没有可分析帧")
        return frames
    finally:
        capture.release()
