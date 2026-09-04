# PP-TinyPose 全帧流式肩部推举计数 v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将肩部推举分析从整段关键点列表和姿态门槛计数升级为全帧流式推理、左右单侧运动峰值检测、锚点计数和双侧质量匹配，并在人工标注视频上稳定得到 90 次。

**Architecture:** `pose_inference` 暴露可显式关闭的惰性关键点流；新的 `shoulder_press_v2` 规则器逐帧维护左右侧 200 ms 平滑窗口和有限状态，以确定性锚点侧产生计数明细，并对另一侧紧凑事件做单调质量匹配。Celery 任务保持现有 HTTP/数据库契约，默认全帧单并发，冒烟命令负责三档回归、资源门槛和远端验收。

**Tech Stack:** Python 3.12、Django 5、Celery 5、PaddlePaddle CPU 3.3.0、PaddleX 3.7.2、PP-TinyPose_128x96、OpenCV contrib 4.10.0.84、pytest、Ruff、Bash、Ubuntu 24.04

**Spec:** `docs/superpowers/specs/2026-09-03-pp-tinypose-full-frame-streaming-counter-v2-design.md`

> 状态：implemented
> 日期：2026-09-04
> 范围：肩部推举 v2 规则、全帧流式推理、任务接入、三档算法验收与独立服务器部署
> 实施基线 commit：`6c08451`
> 最终实现 commit：`de56352ce93a987d0d8e0972d64fab6045567963`
> 最终验收：run_id `20260904T045247Z`，三档均为 90 次且 `acceptance.passed=true`；服务器物理内存约 1.58 GiB，尚未达到生产内存规格

## 实施与验收记录

- Task 1：`e7e5ebc` 实现惰性关键点流，`b82d0d0` 收紧非有限采样、资源释放和时间戳语义。
- Task 2：`55d8d6a` 实现流式计数 v2；`129fe47`、`684047a`、`49aff06` 分别修复状态机边界、浮点阈值和非有限派生测量。
- Task 3：`b4690f7` 接入默认全帧 v2；`d0d8399`、`3e21bb5` 修复版本固化解析与审计字段语义。
- Task 4：`14b4d81` 增加人工真值和资源验收；`7868e6c` 将验收输入和报告 schema 改为 fail-closed。
- Task 5 首次部署：commit `7868e6c`，归档 SHA-256 `9cfee638e315b4dfad989bbefee5d811b722b1c6543d22edd352a6b59807845c`，run_id `20260904T031108Z`。5 FPS / 10 FPS / 全帧为 113 / 108 / 118，失败代码为 `all_frame_count_mismatch`、`sampled_count_error_over_one`；全帧耗时 412.136 秒、RSS 665,055,232 B、Swap 0。已恢复 v1 `77b0166`，失败 v2 与脱敏报告隔离保留。
- 首次失败根因：三档左右事件数均为 90 / 90，旧的 400 ms 并集合并只匹配 67 / 72 / 62 对，把同一双侧动作拆成额外计数；不是单侧周期检测或资源性能问题。
- Task 6：用户批准 `total_count=max(left_event_count,right_event_count)`；`3b88626` 实现确定性锚点与扩展质量匹配，`de56352` 修复非正时长扩展匹配并通过复审。
- Task 5 第二次部署：最终 commit `de56352ce93a987d0d8e0972d64fab6045567963`，归档 SHA-256 `0b6fc49b2ea685511b36e1b82b6777a4662844c97dfb914e2613173908733a4e`，run_id `20260904T045247Z`。5 FPS / 10 FPS / 全帧均为 90 次；耗时 185.103 / 224.840 / 415.576 秒；峰值 RSS 654,696,448 / 660,058,112 / 660,041,728 B；Swap 均为 0；报告 `acceptance.passed=true`。
- 第二次脱敏报告已下载到 `/Users/nick/my_dev/ai/agents/reports/pp-tinypose-v2-20260904T045247Z.json` 和同名前缀 `.txt`；JSON / TXT SHA-256 分别为 `8bce128c527f992b15fd1c64f5a376a592552b0bd75ce51aff0d2061a57913de` / `130cc8f2c678e8ae2f78e6e731ac5d8bfb9987835e3a9849140a2e4c55821017`，敏感路径与凭据模式扫描无命中。
- 第二次本地门禁：后端 1075 passed，Ruff 通过；前端 37 个文件、265 个测试通过，Lint 0 error、5 个既有 warning，构建和 `git diff --check` 通过。
- 远端最终状态：正式 app 为最终 v2，v1 保留为 `app.previous-77b0166`，首次失败 v2 和历史报告未删除；输入和 tmp 无文件，无遗留 benchmark 进程。服务器为 2 vCPU、4 GiB Swap，但 `MemTotal=1,691,308,032 B`（约 1.58 GiB），明确不达 4 GiB 生产内存规格。

## Global Constraints

- 当前 2 vCPU 保持不变；生产目标为 4 GiB 物理内存、4 GiB Swap、CPU 推理、动作分析并发 1。
- 算法输入按最长 60 分钟设计；既有业务上传上限 `TRAINING_VIDEO_MAX_DURATION_SECONDS=1800` 不在本计划内修改，端到端上传 60 分钟需另行设计。
- 正式默认分析全部成功解码帧；`MOTION_ANALYSIS_SAMPLE_FPS=all` 映射为内部 `None`，正浮点数只保留为诊断和紧急降级能力。
- 模型固定为 `PP-TinyPose_128x96`，`device="cpu"`，`use_hpip=False`；不得更换模型或新增推理依赖来规避验收。
- 新规则版本固定为 `shoulder-press-v2`，v1 文件保留用于历史理解和代码级回退，但注册表默认只启用 v2。
- v2 初始参数固定为：平滑 200 ms、峰值突出度 0.15 torso、上升/回落迟滞各 0.08 torso、同侧最小间隔 800 ms、缺口 300 ms；双侧质量匹配使用 400 ms 直接峰值窗口，或 800 ms 峰值上限加至少 50% 的正时长区间重叠。
- 计数与质量分离；肘角不阻断计数。标准性阈值固定为抬升峰值 0.55 torso、突出度 0.20 torso、肘角 150 度、动作时长 800–8,000 ms、动作关键点覆盖率 80%。
- 不新增数据库字段或 migration；扩展指标写入现有 `result_payload`，`total_count = standard_count + nonstandard_count` 必须继续成立。
- 不改变 HTTP API、医生端页面、视频存储供应商、上传/分段协议、数据库网络或 Redis 网络。
- 独立服务器本期继续以无数据库、无 Redis 的前台 benchmark 方式验收，不启动常驻 Celery Worker；生产队列接入需要单独取得网络与凭据授权。
- 测试视频固定为 `/Users/nick/my_dev/ai/agents/IMG_0383_SDR_5min.mp4`，SHA-256 固定为 `f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd`，人工真值固定为 90。
- 真实视频硬验收：全帧 90 次；5 FPS、10 FPS 与全帧相差不超过 1 次；全帧耗时不超过 600 秒；峰值 RSS 低于 1.5 GiB；Swap 使用为零。
- 所有服务器报告必须脱敏，测试输入和中间文件在成功、失败或中断后删除；不把单视频结果描述为医学或临床有效性证明。
- 主检出目录存在另一会话的未提交改动；只在 `.worktrees/pp-tinypose-smoke` 工作树修改本计划列出的文件，不暂存或覆盖主目录改动。

---

## File Structure

### 新建

- `backend/apps/training/shoulder_press_v2.py`：纯 Python 的单侧测量、滚动中位数、峰谷事件检测、锚点计数、双侧质量匹配、质量与置信度汇总。
- `backend/apps/training/tests/test_shoulder_press_v2.py`：跨 FPS、缺口、锚点选择、双侧质量匹配、质量规则、生成器消费和 60 分钟内存边界测试。

### 修改

- `backend/apps/training/pose_inference.py`：增加 `VideoKeypointStream` 和 `open_video_keypoint_stream(...)`，保留旧列表接口作为兼容代理。
- `backend/apps/training/tests/test_pose_inference.py`：覆盖惰性读取、全帧/固定 FPS、统计和所有退出路径释放。
- `backend/config/environment.py`：增加 `env_sample_fps(...)`，只接受 `all` 或正有限浮点数。
- `backend/config/settings.py`：动作分析采样默认值改为全帧。
- `backend/tests/test_settings.py`：覆盖采样配置解析和默认值。
- `.env.example`、`deploy/env.production.example`：显式记录 `MOTION_ANALYSIS_SAMPLE_FPS=all`。
- `backend/apps/training/analysis_registry.py`：注册 `shoulder-press-v2`、规则版本和 Iterable 输入契约。
- `backend/apps/training/video_services.py`：任务创建时固化模型版本和规则版本。
- `backend/apps/training/tasks.py`：在上下文管理器内流式消费关键点，补充耗时与流统计并持久化 v2。
- `backend/apps/training/tests/test_motion_analysis.py`：覆盖注册、任务版本、流消费、指标保存和资源释放。
- `backend/apps/training/pose_benchmark.py`：三档模式改用流式推理，记录人工真值、误差和 v2 硬验收。
- `backend/apps/training/management/commands/run_pose_smoke_benchmark.py`：接收正整数 `--manual-total-count`。
- `backend/apps/training/tests/test_pose_benchmark.py`：覆盖三档流式统计和算法/资源验收。
- `backend/apps/training/tests/test_pose_benchmark_command.py`：覆盖人工真值参数传递与校验。
- `deploy/motion-analysis-smoke/run-benchmark.sh`：固定传入人工真值 90。
- `backend/apps/training/tests/test_pose_benchmark_scripts.py`：验证脚本携带人工真值且继续安全清理输入。
- `docs/superpowers/plans/2026-09-04-pp-tinypose-full-frame-streaming-counter-v2.md`：执行时勾选步骤并追加提交、报告和服务器验收记录。
- `docs/superpowers/specs/2026-09-03-pp-tinypose-full-frame-streaming-counter-v2-design.md`：同步最终锚点计数和质量匹配语义。
- `specs/patient-rehab-system/changelog.md`：按协作协议只追加动作分析决策变更记录。

### 明确保留不改

- `backend/apps/training/analysis.py`：保留 `shoulder-press-v1` 实现，不继续在旧状态机上叠加阈值修补。
- `backend/apps/training/video_models.py`：现有字段足以保存 v2，无 migration。
- 前端和小程序目录：接口向后兼容，无 UI 改动。

---

### Task 1: 增加可关闭的惰性关键点流

**Files:**
- Modify: `backend/apps/training/pose_inference.py`
- Test: `backend/apps/training/tests/test_pose_inference.py`

**Interfaces:**
- Produces: `VideoKeypointStream`，实现 `Iterator[dict]` 和上下文管理器；公开只读统计 `source_fps`、`decoded_frame_count`、`inferred_frame_count`、`inference_seconds`。
- Produces: `open_video_keypoint_stream(video_path, *, sample_fps: float | None, model=None, capture=None) -> VideoKeypointStream`；`None` 表示全帧。
- Preserves: `extract_video_keypoint_frames_with_stats(...) -> VideoKeypointExtraction` 和 `extract_video_keypoint_frames(...) -> list[dict]`，内部改为消费新流，避免维护两套解码逻辑。

- [x] **Step 1: 写惰性、采样统计和释放失败测试**

在 `test_pose_inference.py` 增加导入和测试：

```python
from apps.training.pose_inference import open_video_keypoint_stream


def test_keypoint_stream_is_lazy_and_infers_every_frame_in_all_mode():
    capture = FakeCapture([0, 100, 200])
    model = FakeModel()

    stream = open_video_keypoint_stream(
        "ignored.mp4",
        sample_fps=None,
        model=model,
        capture=capture,
    )
    assert model.seen_frames == []

    with stream:
        frames = list(stream)

    assert model.seen_frames == [0, 1, 2]
    assert [item["timestamp_ms"] for item in frames] == [0, 100, 200]
    assert all(item["source_fps"] == 10.0 for item in frames)
    assert stream.decoded_frame_count == 3
    assert stream.inferred_frame_count == 3
    assert capture.released is True


def test_keypoint_stream_context_releases_capture_when_consumer_fails():
    capture = FakeCapture([0, 100])
    stream = open_video_keypoint_stream(
        "ignored.mp4",
        sample_fps=None,
        model=FakeModel(),
        capture=capture,
    )

    with pytest.raises(RuntimeError, match="consumer failed"):
        with stream:
            next(stream)
            raise RuntimeError("consumer failed")

    assert capture.released is True


def test_keypoint_stream_keeps_fixed_fps_sampling_and_stats():
    capture = FakeCapture([0, 50, 100, 150, 200])
    model = FakeModel()

    with open_video_keypoint_stream(
        "ignored.mp4",
        sample_fps=10.0,
        model=model,
        capture=capture,
    ) as stream:
        frames = list(stream)

    assert model.seen_frames == [0, 2, 4]
    assert stream.decoded_frame_count == 5
    assert stream.inferred_frame_count == 3
    assert stream.inference_seconds >= 0
    assert [item["timestamp_ms"] for item in frames] == [0, 100, 200]
```

- [x] **Step 2: 运行测试并确认因新接口不存在而失败**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_inference.py -q
```

Expected: FAIL，导入错误包含 `open_video_keypoint_stream`。

- [x] **Step 3: 实现流对象的生命周期和单帧推理**

在 `pose_inference.py` 增加 `VideoKeypointStream`。`__next__` 每次循环读取到下一个应推理帧，累计模型调用耗时并产出一项；所有资源由 `close()` 和 `__exit__()` 收口：

```python
class VideoKeypointStream:
    def __init__(self, *, capture, model, sample_fps, source_fps):
        self.capture = capture
        self.model = model
        self.sample_fps = sample_fps
        self.source_fps = source_fps
        self.decoded_frame_count = 0
        self.inferred_frame_count = 0
        self.inference_seconds = 0.0
        self._next_sample_ms = 0.0
        self._last_timestamp_ms = -1.0
        self._closed = False

    def __iter__(self):
        return self

    def __next__(self):
        if self._closed:
            raise StopIteration
        while True:
            ok, frame = self.capture.read()
            if not ok:
                self.close()
                if self.inferred_frame_count == 0:
                    raise MotionAnalysisInferenceError("训练视频没有可分析帧")
                raise StopIteration
            frame_index = self.decoded_frame_count
            self.decoded_frame_count += 1
            timestamp_ms = float(self.capture.get(CAP_PROP_POS_MSEC) or 0.0)
            if timestamp_ms <= 0 and frame_index:
                timestamp_ms = frame_index * 1000.0 / self.source_fps
            if timestamp_ms <= self._last_timestamp_ms:
                timestamp_ms = max(
                    frame_index * 1000.0 / self.source_fps,
                    self._last_timestamp_ms + 1000.0 / self.source_fps,
                )
            self._last_timestamp_ms = timestamp_ms
            if (
                self.sample_fps is not None
                and timestamp_ms + 0.5 < self._next_sample_ms
            ):
                continue
            try:
                frame_height, frame_width = frame.shape[:2]
            except (AttributeError, TypeError, ValueError) as exc:
                raise MotionAnalysisInferenceError("视频帧尺寸无效") from exc
            inference_started = time.monotonic()
            prediction = _first_prediction(self.model, frame)
            self.inference_seconds += time.monotonic() - inference_started
            self.inferred_frame_count += 1
            if self.sample_fps is not None:
                interval_ms = 1000.0 / self.sample_fps
                while self._next_sample_ms <= timestamp_ms + 0.5:
                    self._next_sample_ms += interval_ms
            return {
                "timestamp_ms": int(round(timestamp_ms)),
                "source_fps": self.source_fps,
                "keypoints": convert_paddlex_result(
                    prediction,
                    frame_width=frame_width,
                    frame_height=frame_height,
                ),
            }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False

    def close(self):
        if not self._closed:
            self.capture.release()
            self._closed = True
```

补充 `import time`。`__next__` 复用现有 `_first_prediction()` 和 `convert_paddlex_result()`；帧字典固定为：

```python
{
    "timestamp_ms": int(round(timestamp_ms)),
    "source_fps": self.source_fps,
    "keypoints": converted_keypoints,
}
```

EOF 且 `inferred_frame_count == 0` 时抛出 `MotionAnalysisInferenceError("训练视频没有可分析帧")`；正常 EOF 抛出 `StopIteration`。关闭后的再次迭代直接停止，不访问 capture。

- [x] **Step 4: 增加流工厂并让旧接口做代理**

新增：

```python
def open_video_keypoint_stream(
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
    if not capture.isOpened():
        capture.release()
        raise MotionAnalysisInferenceError("训练视频无法解码")
    fallback_fps = sample_fps or DEFAULT_SAMPLE_FPS
    source_fps = float(capture.get(CAP_PROP_FPS) or fallback_fps)
    if not math.isfinite(source_fps) or source_fps <= 0:
        source_fps = fallback_fps
    return VideoKeypointStream(
        capture=capture,
        model=model,
        sample_fps=sample_fps,
        source_fps=source_fps,
    )
```

补充 `import math`；迭代器必须保证输出时间戳严格递增，即使 OpenCV 返回重复或倒退的 `CAP_PROP_POS_MSEC`。

把旧统计函数改为：

```python
with open_video_keypoint_stream(
    video_path,
    sample_fps=sample_fps,
    model=model,
    capture=capture,
) as stream:
    frames = list(stream)
return VideoKeypointExtraction(
    frames=frames,
    decoded_frame_count=stream.decoded_frame_count,
    inferred_frame_count=stream.inferred_frame_count,
    source_fps=stream.source_fps,
)
```

- [x] **Step 5: 运行推理适配器测试和 Ruff**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_inference.py -q
ruff check apps/training/pose_inference.py apps/training/tests/test_pose_inference.py
```

Expected: 全部 PASS，Ruff 无输出且退出码为 0。

- [x] **Step 6: 提交 Task 1**

```bash
git add backend/apps/training/pose_inference.py backend/apps/training/tests/test_pose_inference.py
git commit -m "feat(动作分析): 增加流式关键点推理接口"
```

Expected: 提交只包含上述两个文件。

---

### Task 2: 实现肩部推举 v2 流式计数器

**Files:**
- Create: `backend/apps/training/shoulder_press_v2.py`
- Create: `backend/apps/training/tests/test_shoulder_press_v2.py`

**Interfaces:**
- Produces: `SHOULDER_PRESS_RULE_VERSION = "shoulder-press-v2"`。
- Produces: `analyze_shoulder_press_keypoints_v2(frames: Iterable[dict]) -> dict`，只单次遍历输入。
- Internal: `SideMeasurement`、`SideEvent`、`SideEventDetector`，分别承载单帧标量、紧凑事件和有限状态。
- Output: 设计规格第 8 节的计数、左右事件数、双侧一致率、覆盖率、置信度、动作明细和质量标记。

- [x] **Step 1: 写跨帧率计数和半次动作失败测试**

创建 `test_shoulder_press_v2.py`。测试数据直接构造归一化关键点，肩髋距离固定为 0.3：

```python
import math
import tracemalloc

import pytest

from apps.training.shoulder_press_v2 import analyze_shoulder_press_keypoints_v2


def _frame(
    timestamp_ms,
    left_lift,
    right_lift,
    *,
    left_score=0.95,
    right_score=0.95,
    source_fps=30.0,
):
    keypoints = {}
    for side, shoulder_x, wrist_x, lift, score in (
        ("left", 0.4, 0.3, left_lift, left_score),
        ("right", 0.6, 0.7, right_lift, right_score),
    ):
        shoulder_y = 0.5
        wrist_y = shoulder_y - lift * 0.3
        keypoints[f"{side}_shoulder"] = {"x": shoulder_x, "y": shoulder_y, "score": score}
        keypoints[f"{side}_hip"] = {"x": shoulder_x, "y": 0.8, "score": score}
        keypoints[f"{side}_wrist"] = {"x": wrist_x, "y": wrist_y, "score": score}
        keypoints[f"{side}_elbow"] = {
            "x": (shoulder_x + wrist_x) / 2,
            "y": (shoulder_y + wrist_y) / 2,
            "score": score,
        }
    return {"timestamp_ms": timestamp_ms, "source_fps": source_fps, "keypoints": keypoints}


def _triangle_sequence(*, fps, repetitions, period_seconds=3.0):
    frame_count = math.floor(fps * repetitions * period_seconds) + 1
    for index in range(frame_count):
        timestamp_ms = round(index * 1000 / fps)
        phase = (timestamp_ms / 1000 % period_seconds) / period_seconds
        lift = 1.6 * phase if phase <= 0.5 else 1.6 * (1 - phase)
        yield _frame(timestamp_ms, lift, lift, source_fps=fps)


@pytest.mark.parametrize("fps", [5.0, 10.0, 30.0])
def test_counts_same_complete_cycles_at_different_frame_rates(fps):
    result = analyze_shoulder_press_keypoints_v2(
        _triangle_sequence(fps=fps, repetitions=3)
    )

    assert result["total_count"] == 3
    assert result["left_event_count"] == 3
    assert result["right_event_count"] == 3
    assert result["bilateral_event_count"] == 3


def test_does_not_count_leading_or_trailing_half_cycle():
    frames = (
        _frame(timestamp_ms, lift, lift)
        for timestamp_ms, lift in [(0, 0.8), (300, 0.4), (600, 0.0), (900, 0.4), (1200, 0.8)]
    )

    result = analyze_shoulder_press_keypoints_v2(frames)

    assert result["total_count"] == 0
```

- [x] **Step 2: 写突出度、缺口、双侧匹配和质量测试**

继续增加以下独立断言：

```python
def test_low_amplitude_complete_cycle_counts_as_nonstandard():
    frames = (
        _frame(timestamp_ms, lift, lift)
        for timestamp_ms, lift in [(0, 0.0), (400, 0.18), (800, 0.0)]
    )
    result = analyze_shoulder_press_keypoints_v2(frames)
    assert result["total_count"] == 1
    assert result["nonstandard_count"] == 1
    assert "range_too_small" in result["rep_details"][0]["flags"]


def test_short_missing_gap_keeps_candidate_but_long_gap_resets_it():
    short_gap = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.8),
        {"timestamp_ms": 500, "source_fps": 10.0, "keypoints": {}},
        _frame(650, 0.6, 0.6),
        _frame(900, 0.0, 0.0),
    ]
    long_gap = [*short_gap[:3], {"timestamp_ms": 850, "source_fps": 10.0, "keypoints": {}}, _frame(1000, 0.0, 0.0)]

    assert analyze_shoulder_press_keypoints_v2(iter(short_gap))["total_count"] == 1
    assert analyze_shoulder_press_keypoints_v2(iter(long_gap))["total_count"] == 0


def test_merges_synchronized_sides_and_marks_visible_unmatched_side():
    matched = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.7),
        _frame(800, 0.0, 0.0),
    ]
    unmatched = [
        _frame(0, 0.0, 0.0),
        _frame(400, 0.8, 0.0),
        _frame(800, 0.0, 0.0),
    ]

    matched_result = analyze_shoulder_press_keypoints_v2(iter(matched))
    unmatched_result = analyze_shoulder_press_keypoints_v2(iter(unmatched))

    assert matched_result["total_count"] == 1
    assert matched_result["rep_details"][0]["source_sides"] == ["left", "right"]
    assert unmatched_result["total_count"] == 1
    assert "bilateral_mismatch" in unmatched_result["rep_details"][0]["flags"]
```

质量测试使用完整周期，并分别改变峰值肘坐标、动作时长和可靠分数：

```python
def test_quality_failures_do_not_remove_completed_repetition():
    bent_peak = _frame(400, 0.8, 0.8)
    bent_peak["keypoints"]["left_elbow"].update(x=0.25, y=0.4)
    bent_peak["keypoints"]["right_elbow"].update(x=0.75, y=0.4)
    bent = [_frame(0, 0.0, 0.0), bent_peak, _frame(800, 0.0, 0.0)]
    fast = [_frame(0, 0.0, 0.0), _frame(200, 0.8, 0.8), _frame(400, 0.0, 0.0)]
    unreliable = [
        _frame(0, 0.0, 0.0),
        _frame(200, 0.4, 0.4, left_score=0.3, right_score=0.3),
        _frame(400, 0.8, 0.8),
        _frame(600, 0.4, 0.4, left_score=0.3, right_score=0.3),
        _frame(800, 0.0, 0.0),
    ]

    cases = [
        (bent, "elbow_not_extended"),
        (fast, "tempo_abnormal"),
        (unreliable, "low_confidence"),
    ]
    for frames, expected_flag in cases:
        result = analyze_shoulder_press_keypoints_v2(iter(frames))
        assert result["total_count"] == 1
        assert result["nonstandard_count"] == 1
        assert expected_flag in result["rep_details"][0]["flags"]
```

- [x] **Step 3: 写置信度、单次迭代和 60 分钟内存边界测试**

```python
class OneShotFrames:
    def __init__(self, frames):
        self.frames = frames
        self.iterated = False

    def __iter__(self):
        if self.iterated:
            raise AssertionError("关键点流被重复迭代")
        self.iterated = True
        return iter(self.frames)


def test_consumes_input_once_and_reports_confidence_metrics():
    source = OneShotFrames(list(_triangle_sequence(fps=10.0, repetitions=2)))
    result = analyze_shoulder_press_keypoints_v2(source)
    assert source.iterated is True
    assert result["total_count"] == 2
    assert result["keypoint_coverage_ratio"] == 1.0
    assert result["bilateral_agreement_ratio"] == 1.0
    assert result["confidence_level"] == "high"


def test_stationary_sixty_minute_stream_has_bounded_python_memory():
    def frames():
        for index in range(108_000):
            yield _frame(round(index * 1000 / 30), 0.0, 0.0)

    tracemalloc.start()
    result = analyze_shoulder_press_keypoints_v2(frames())
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    assert result["processed_frames"] == 108_000
    assert result["total_count"] == 0
    assert peak_bytes < 8 * 1024 * 1024


def test_rejects_stream_without_any_measurable_person():
    frames = ({"timestamp_ms": index * 100, "keypoints": {}} for index in range(5))
    with pytest.raises(MotionAnalysisInferenceError, match="没有可用的人体关键点"):
        analyze_shoulder_press_keypoints_v2(frames)


def test_rejects_decreasing_timestamps():
    frames = [_frame(100, 0.0, 0.0), _frame(50, 0.4, 0.4)]
    with pytest.raises(ValueError, match="时间戳"):
        analyze_shoulder_press_keypoints_v2(iter(frames))
```

为最后两个测试从 `apps.training.pose_inference` 导入 `MotionAnalysisInferenceError`。空输入由关键点流抛出“没有可分析帧”；有帧但全程不可测量由 v2 抛出“全程没有可用的人体关键点”。流式规则器不排序输入，发现时间戳倒退立即失败。

- [x] **Step 4: 运行测试并确认 v2 模块尚不存在**

Run:

```bash
cd backend
pytest apps/training/tests/test_shoulder_press_v2.py -q
```

Expected: FAIL，导入错误包含 `apps.training.shoulder_press_v2`。

- [x] **Step 5: 实现单侧测量和按时间滚动中位数**

在 `shoulder_press_v2.py` 定义设计中的常量，并使用不可变数据类：

```python
@dataclass(frozen=True)
class SideMeasurement:
    side: str
    timestamp_ms: int
    wrist_lift: float
    elbow_angle: float
    score: float


@dataclass(frozen=True)
class SideEvent:
    side: str
    start_ms: int
    peak_ms: int
    end_ms: int
    prominence: float
    peak_wrist_lift: float
    peak_elbow_angle: float
    coverage_ratio: float
    opposite_coverage_ratio: float
```

`_measurement(frame, side)` 先校验四个点坐标和非零躯干长度；不可测量时返回 `None`。可测量结果携带四点最低 `score`，其中 `score >= 0.4` 记为可靠。`SideEventDetector` 用 `deque` 删除 `timestamp_ms < current_ms - 200` 的测量，再以 `statistics.median` 计算平滑抬升值。不得保存窗口外测量。

- [x] **Step 6: 实现峰谷状态机和缺口重置**

状态机只保留当前谷值、候选峰值、候选总帧/有效帧、最后有效时间和最后确认峰值时间：

```python
if phase == "seeking" and smoothed_lift - trough_lift >= 0.08:
    phase = "rising"
if phase == "rising" and smoothed_lift >= peak_lift:
    peak = measurement
if phase == "rising" and peak_lift - smoothed_lift >= 0.08:
    prominence = peak_lift - trough_lift
    if prominence >= 0.15 and peak_ms - last_event_peak_ms >= 800:
        emit_side_event()
    reset_from_current_measurement()
```

`observe_missing(timestamp_ms, opposite_valid)` 累计候选覆盖率；`timestamp_ms - last_valid_ms > 300` 时清空未完成候选。事件 `end_ms` 是首次满足回落迟滞的时间，不要求返回固定 `down` 阈值。

- [x] **Step 7: 实现锚点计数、双侧质量匹配、质量标记和整体置信度**

消费帧流时分别调用左右检测器，只保存 `SideEvent` 列表。最终以事件数更多的一侧为锚点；数量相同时使用平均 `coverage_ratio` 更高的一侧，再平局固定选择左侧。每个锚点事件产生一条 `rep_details`，因此 `total_count=max(left_event_count,right_event_count)`；另一侧事件按时间单调、一对一匹配，未匹配的非锚点事件不得增加总数。

双侧匹配在峰值差不超过 400 ms 时直接成立；峰值差为 401–800 ms 时，仅当两个事件时长均为正且区间重叠长度至少占较短区间 50% 才成立。匹配只影响双侧计数、一致率、flags 和标准/不标准分类。匹配明细时间固定为：

```python
start_ms = min(event.start_ms for event in matched)
peak_ms = round(sum(event.peak_ms for event in matched) / len(matched))
end_ms = max(event.end_ms for event in matched)
```

质量标记按固定顺序生成：`range_too_small`、`elbow_not_extended`、`tempo_abnormal`、`low_confidence`、`bilateral_mismatch`。峰值抬升小于 0.55 或突出度小于 0.20 时标记幅度不足；峰值肘角小于 150 度时标记伸展不足；动作时长不在 800–8,000 ms 时标记节奏异常；周期内可靠测量比例低于 80% 时标记低置信度；对侧可靠覆盖率不低于 80% 但没有按直接或扩展规则匹配时标记双侧不一致。

单侧覆盖率等于该侧可靠帧数除以已处理帧数，整体覆盖率等于至少一侧可靠的帧数除以已处理帧数；双侧一致率等于匹配事件数除以 `max(left_event_count, right_event_count, 1)`。整体覆盖率不低于 90% 且一致率不低于 80% 为 `high`；覆盖率不低于 70% 且一致率不低于 50% 为 `medium`；其余可计数结果为 `low`。`rep_details` 按 `peak_ms` 排序并从 1 编号。

- [x] **Step 8: 运行 v2 测试、旧规则回归和 Ruff**

Run:

```bash
cd backend
pytest apps/training/tests/test_shoulder_press_v2.py apps/training/tests/test_motion_analysis.py -q
ruff check apps/training/shoulder_press_v2.py apps/training/tests/test_shoulder_press_v2.py
```

Expected: 全部 PASS；旧 v1 测试继续通过且旧文件未修改。

- [x] **Step 9: 提交 Task 2**

```bash
git add backend/apps/training/shoulder_press_v2.py backend/apps/training/tests/test_shoulder_press_v2.py
git commit -m "feat(动作分析): 增加肩部推举流式计数v2"
```

Expected: 提交只包含 v2 模块和对应测试。

---

### Task 3: 将 v2 接入配置、注册表和 Celery 任务

**Files:**
- Modify: `backend/config/environment.py`
- Modify: `backend/config/settings.py`
- Modify: `backend/tests/test_settings.py`
- Modify: `.env.example`
- Modify: `deploy/env.production.example`
- Modify: `backend/apps/training/analysis_registry.py`
- Modify: `backend/apps/training/video_services.py`
- Modify: `backend/apps/training/tasks.py`
- Modify: `backend/apps/training/tests/test_motion_analysis.py`

**Interfaces:**
- Produces: `env_sample_fps(name: str, *, default: str = "all") -> float | None`。
- Changes: `MotionAnalyzer(source_key, algorithm_version, rule_version, analyze_keypoints)`；分析函数接受 `Iterable[dict]`。
- Changes: 新任务创建时固化 `algorithm_version` 和 `rule_version`；成功任务补充流统计和分析耗时。
- Consumes: Task 1 的 `open_video_keypoint_stream(...)` 和 Task 2 的 `analyze_shoulder_press_keypoints_v2(...)`。

- [x] **Step 1: 写采样配置解析失败测试**

在 `backend/tests/test_settings.py` 导入 `env_sample_fps` 并增加：

```python
@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [("all", None), (" ALL ", None), ("5", 5.0), ("10.5", 10.5)],
)
def test_env_sample_fps_accepts_all_or_positive_number(monkeypatch, raw_value, expected):
    monkeypatch.setenv("TEST_SAMPLE_FPS", raw_value)
    assert env_sample_fps("TEST_SAMPLE_FPS") == expected


@pytest.mark.parametrize("raw_value", ["", "0", "-1", "nan", "inf", "full"])
def test_env_sample_fps_rejects_invalid_value(monkeypatch, raw_value):
    monkeypatch.setenv("TEST_SAMPLE_FPS", raw_value)
    with pytest.raises(ImproperlyConfigured, match="TEST_SAMPLE_FPS"):
        env_sample_fps("TEST_SAMPLE_FPS")


def test_motion_analysis_defaults_to_all_frames():
    assert settings.MOTION_ANALYSIS_SAMPLE_FPS is None
```

- [x] **Step 2: 写注册版本、创建任务和流式持久化失败测试**

调整注册表测试，断言：

```python
assert analyzer.algorithm_version == PP_TINYPOSE_MODEL_NAME
assert analyzer.rule_version == "shoulder-press-v2"
assert analyzer.analyze_keypoints is analyze_shoulder_press_keypoints_v2
```

在创建任务测试中断言初始 `job.algorithm_version` 和 `job.rule_version` 已固化。把任务成功测试的假流定义为：

```python
class FakeKeypointStream:
    source_fps = 29.763
    decoded_frame_count = 2
    inferred_frame_count = 2

    def __init__(self):
        self.closed = False

    def __iter__(self):
        yield {"timestamp_ms": 0, "keypoints": {}}
        yield {"timestamp_ms": 34, "keypoints": {}}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.closed = True
        return False
```

模拟分析器必须实际执行 `list(frames)`，并断言保存结果含：

```python
assert job.rule_version == "shoulder-press-v2"
assert job.result_payload["processed_frames"] == 2
assert job.result_payload["source_fps"] == pytest.approx(29.763)
assert job.result_payload["analysis_elapsed_ms"] >= 0
assert fake_stream.closed is True
```

另加分析器抛错测试，断言 `FakeKeypointStream.__exit__` 仍执行、临时视频仍删除、任务为 `failed`。

- [x] **Step 3: 运行测试并确认配置仍为 5 FPS、注册仍指向 v1**

Run:

```bash
cd backend
pytest tests/test_settings.py apps/training/tests/test_motion_analysis.py -q
```

Expected: FAIL，失败点包含默认采样值、缺少 `rule_version` 或注册函数仍为 v1。

- [x] **Step 4: 实现严格采样配置并更新环境模板**

在 `config/environment.py` 增加：

```python
def env_sample_fps(name, *, default="all"):
    raw_value = os.getenv(name, default).strip().lower()
    if raw_value == "all":
        return None
    try:
        value = float(raw_value)
    except ValueError as exc:
        raise ImproperlyConfigured(f"{name} 只允许设置为 all 或正数。") from exc
    if not math.isfinite(value) or value <= 0:
        raise ImproperlyConfigured(f"{name} 只允许设置为 all 或正数。")
    return value
```

补充 `import math`，并把 settings 改为：

```python
MOTION_ANALYSIS_SAMPLE_FPS = env_sample_fps("MOTION_ANALYSIS_SAMPLE_FPS")
```

`.env.example` 和 `deploy/env.production.example` 均显式增加：

```dotenv
MOTION_ANALYSIS_SAMPLE_FPS=all
```

- [x] **Step 5: 注册 v2 并在任务创建时固化版本**

把 `MotionAnalyzer` 改为：

```python
@dataclass(frozen=True)
class MotionAnalyzer:
    source_key: str
    algorithm_version: str
    rule_version: str
    analyze_keypoints: Callable[[Iterable[dict]], dict]
```

注册肩部推举时使用 `SHOULDER_PRESS_RULE_VERSION` 和 `analyze_shoulder_press_keypoints_v2`。`create_analysis_job()` 只调用一次 `get_motion_analyzer(source_key)`，并在 `MotionAnalysisJob.objects.create(...)` 传入：

```python
algorithm_version=analyzer.algorithm_version,
rule_version=analyzer.rule_version,
```

- [x] **Step 6: Celery 任务在上下文中消费流并补充指标**

将任务中的列表提取替换为：

```python
analysis_started = time.monotonic()
with open_video_keypoint_stream(
    temporary_path,
    sample_fps=settings.MOTION_ANALYSIS_SAMPLE_FPS,
) as stream:
    result = analyzer.analyze_keypoints(stream)
result = {
    **result,
    "rule_version": analyzer.rule_version,
    "processed_frames": stream.inferred_frame_count,
    "source_fps": stream.source_fps,
    "analysis_elapsed_ms": round((time.monotonic() - analysis_started) * 1000),
}
```

调用 `_persist_success(job.id, result, analyzer.algorithm_version, analyzer.rule_version)`；该函数同时更新模型版本和规则版本。阶段名称改为“关键点推理与规则分析”，使惰性推理异常的失败原因准确。

- [x] **Step 7: 运行配置、任务、接口和模型测试**

Run:

```bash
cd backend
pytest tests/test_settings.py apps/training/tests/test_motion_analysis.py apps/training/tests/test_training_video_api.py apps/training/tests/test_video_session_models.py -q
ruff check config/environment.py config/settings.py apps/training/analysis_registry.py apps/training/video_services.py apps/training/tasks.py
```

Expected: 全部 PASS，Ruff 退出码为 0；无需生成 migration。

- [x] **Step 8: 提交 Task 3**

```bash
git add .env.example deploy/env.production.example backend/config/environment.py backend/config/settings.py backend/tests/test_settings.py backend/apps/training/analysis_registry.py backend/apps/training/video_services.py backend/apps/training/tasks.py backend/apps/training/tests/test_motion_analysis.py
git commit -m "feat(动作分析): 默认全帧接入计数v2"
```

Expected: 提交不包含模型、视频、报告或数据库 migration。

---

### Task 4: 将三档冒烟升级为带人工真值的 v2 验收

**Files:**
- Modify: `backend/apps/training/pose_benchmark.py`
- Modify: `backend/apps/training/management/commands/run_pose_smoke_benchmark.py`
- Modify: `backend/apps/training/tests/test_pose_benchmark.py`
- Modify: `backend/apps/training/tests/test_pose_benchmark_command.py`
- Modify: `deploy/motion-analysis-smoke/run-benchmark.sh`
- Modify: `backend/apps/training/tests/test_pose_benchmark_scripts.py`

**Interfaces:**
- Changes: `run_pose_smoke_benchmark(..., manual_total_count: int, stream_factory=open_video_keypoint_stream, analyzer=analyze_shoulder_press_keypoints_v2) -> dict`。
- Produces: 报告格式 `2.0`，每档包含 `count_error`，顶层包含 `acceptance`。
- Internal: `_v2_acceptance_failures(report: dict) -> list[str]`，纯函数返回固定失败代码，便于逐门槛测试。
- Changes: 管理命令新增必填正整数 `--manual-total-count`；固定脚本传入 `90`。
- Changes: 固定脚本和报告文件名前缀从 `pp-tinypose-smoke-` 更新为 `pp-tinypose-v2-`，避免覆盖 v1 报告。

- [x] **Step 1: 写流式三档、人工误差和通过验收测试**

把 benchmark 测试的假提取器替换为上下文流，并传入 `manual_total_count=3`：

```python
class FakeStream:
    def __init__(self, frames, *, source_fps=30.0):
        self.frames = frames
        self.source_fps = source_fps
        self.decoded_frame_count = len(frames)
        self.inferred_frame_count = len(frames)
        self.inference_seconds = 0.1

    def __iter__(self):
        return iter(self.frames)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False


def _benchmark_result(total_count):
    return {
        "total_count": total_count,
        "standard_count": total_count,
        "nonstandard_count": 0,
        "rep_details": [],
        "quality_flags": ["camera_angle_unverified"],
    }


def test_v2_benchmark_records_manual_count_and_passes_all_gates(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    summary = tmp_path / "report.txt"

    def fake_stream_factory(path, *, sample_fps, model):
        frames = [{"timestamp_ms": index * 100, "keypoints": {}} for index in range(3)]
        return FakeStream(frames)

    result = run_pose_smoke_benchmark(
        video,
        report_path=report,
        summary_path=summary,
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        manual_total_count=3,
        ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
        model_factory=lambda: object(),
        warm_up=lambda path, *, model: None,
        stream_factory=fake_stream_factory,
        analyzer=lambda frames: (list(frames), _benchmark_result(3))[1],
        sampler_factory=lambda: FakeSampler(_peak(swap_used=0)),
        version_reader=lambda: {},
        hardware_reader=lambda: {},
    )
    assert result["report_format_version"] == "2.0"
    assert result["manual_total_count"] == 3
    assert [mode["count_error"] for mode in result["modes"]] == [0, 0, 0]
    assert result["acceptance"]["passed"] is True
```

更新 `_peak()` 测试帮助函数，使 `swap_used` 可显式传入。

- [x] **Step 2: 写每个硬门槛的独立失败测试**

直接测试纯验收函数，避免通过计时 mock 间接覆盖规则：

```python
@pytest.mark.parametrize(
    "case",
    [
        "full_frame_count_not_90",
        "sampled_count_diff_over_one",
        "all_frame_over_two_times_duration",
        "rss_at_or_over_1_5_gib",
        "swap_used_nonzero",
        "all_frame_not_completed",
    ],
)
def test_v2_acceptance_rejects_each_failed_gate(tmp_path, case):
    report = {
        "manual_total_count": 90,
        "video": {"duration_seconds": 300.0},
        "modes": [
            {"name": "5fps", "status": "completed", "count_error": 0},
            {"name": "10fps", "status": "completed", "count_error": 0},
            {
                "name": "all_frames",
                "status": "completed",
                "count_error": 0,
                "total_seconds": 445.0,
                "result": {"total_count": 90},
                "resource_peak": {
                    "process_rss_bytes": 700 * 1024**2,
                    "swap_used_bytes": 0,
                },
            },
        ],
    }
    if case == "full_frame_count_not_90":
        report["modes"][2]["result"]["total_count"] = 89
    elif case == "sampled_count_diff_over_one":
        report["modes"][0]["count_error"] = -2
    elif case == "all_frame_over_two_times_duration":
        report["modes"][2]["total_seconds"] = 601.0
    elif case == "rss_at_or_over_1_5_gib":
        report["modes"][2]["resource_peak"]["process_rss_bytes"] = int(1.5 * 1024**3)
    elif case == "swap_used_nonzero":
        report["modes"][2]["resource_peak"]["swap_used_bytes"] = 4096
    else:
        report["modes"][2]["status"] = "failed"

    assert _v2_acceptance_failures(report)
```

增加 benchmark 集成测试，按三档依次返回 90、90、89：

```python
def test_benchmark_persists_sanitized_report_before_v2_acceptance_failure(tmp_path):
    video = tmp_path / "private-patient-video.mp4"
    video.write_bytes(b"video")
    report_path = tmp_path / "report.json"
    totals = iter([90, 90, 89])

    def stream_factory(path, *, sample_fps, model):
        return FakeStream([{"timestamp_ms": 0, "keypoints": {}}])

    def analyzer(frames):
        list(frames)
        return _benchmark_result(next(totals))

    with pytest.raises(BenchmarkFailure, match="v2 算法验收失败"):
        run_pose_smoke_benchmark(
            video,
            report_path=report_path,
            summary_path=tmp_path / "report.txt",
            expected_sha256=sha256_file(video),
            git_commit="abc1234",
            manual_total_count=90,
            ffprobe_runner=lambda *args, **kwargs: _probe_payload(),
            model_factory=lambda: object(),
            warm_up=lambda path, *, model: None,
            stream_factory=stream_factory,
            analyzer=analyzer,
            sampler_factory=lambda: FakeSampler(_peak(swap_used=0)),
            version_reader=lambda: {},
            hardware_reader=lambda: {},
        )

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["acceptance"]["failures"] == ["all_frame_count_mismatch"]
    assert str(video) not in json.dumps(payload, ensure_ascii=False)
```

- [x] **Step 3: 写命令和 Shell 参数失败测试**

命令测试增加：

```python
call_command(
    "run_pose_smoke_benchmark",
    video=str(video),
    report=str(report),
    summary=str(summary),
    expected_sha256="f" * 64,
    git_commit="abc1234",
    manual_total_count=90,
)
runner.assert_called_once_with(
    Path(video),
    report_path=Path(report),
    summary_path=Path(summary),
    expected_sha256="f" * 64,
    git_commit="abc1234",
    manual_total_count=90,
)
```

再参数化 `0`、`-1` 和非整数输入，断言命令拒绝。Shell 测试从伪 `runuser` 参数中断言存在连续参数 `--manual-total-count 90`，且所有退出路径仍删除输入。

- [x] **Step 4: 运行测试并确认旧 benchmark 尚不支持人工真值**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark.py apps/training/tests/test_pose_benchmark_command.py apps/training/tests/test_pose_benchmark_scripts.py -q
```

Expected: FAIL，错误包含未知 `manual_total_count` 或缺少 `--manual-total-count`。

- [x] **Step 5: 改为逐档消费关键点流并记录统计**

在每个模式中使用：

```python
with sampler_factory() as sampler:
    with stream_factory(
        video_path,
        sample_fps=mode.sample_fps,
        model=model,
    ) as stream:
        mode_started = monotonic()
        result = analyzer(stream)
        total_seconds = monotonic() - mode_started
mode_report.update(
    decoded_frame_count=stream.decoded_frame_count,
    inferred_frame_count=stream.inferred_frame_count,
    source_fps=stream.source_fps,
    inference_seconds=stream.inference_seconds,
    total_seconds=total_seconds,
    average_inference_ms_per_frame=(
        stream.inference_seconds * 1000 / stream.inferred_frame_count
    ),
    count_error=result["total_count"] - manual_total_count,
    result=result,
)
```

流、资源采样器和输入文件的现有异常清理逻辑必须保留。

- [x] **Step 6: 实现明确的 v2 硬验收**

报告顶层写入：

```python
"manual_total_count": manual_total_count,
"acceptance": {"passed": False, "failures": []},
```

先检查三档是否均为 `completed`；任一档未完成时直接返回 `required_mode_not_completed`，不得继续读取该档缺失的结果字段。三档均完成后按以下固定条件追加失败代码：

```python
if all_frames["result"]["total_count"] != manual_total_count:
    failures.append("all_frame_count_mismatch")
if any(abs(mode["count_error"]) > 1 for mode in sampled_modes):
    failures.append("sampled_count_error_over_one")
if all_frames["total_seconds"] > report["video"]["duration_seconds"] * 2:
    failures.append("all_frame_slower_than_two_times_duration")
if all_frames["resource_peak"]["process_rss_bytes"] >= int(1.5 * 1024**3):
    failures.append("all_frame_rss_limit_exceeded")
if all_frames["resource_peak"]["swap_used_bytes"] != 0:
    failures.append("swap_used")
```

任何模式未完成时追加 `required_mode_not_completed`。`failures` 为空才把 `acceptance.passed` 和顶层 `status` 置为成功。

- [x] **Step 7: 接入命令参数和固定人工真值**

管理命令增加：

```python
parser.add_argument("--manual-total-count", required=True, type=int)
```

在调用 runner 前校验大于 0。`run-benchmark.sh` 的管理命令参数增加：

```bash
--manual-total-count 90
```

摘要逐档输出“总次数、人工误差”，结尾输出“v2验收：通过/失败”。脚本的 `report_path` 和 `summary_path` 同步改用 `pp-tinypose-v2-${run_id}`。

- [x] **Step 8: 运行 benchmark 全部测试、Shell 语法和 Ruff**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark.py apps/training/tests/test_pose_benchmark_command.py apps/training/tests/test_pose_benchmark_resources.py apps/training/tests/test_pose_benchmark_scripts.py -q
ruff check apps/training/pose_benchmark.py apps/training/management/commands/run_pose_smoke_benchmark.py apps/training/tests/test_pose_benchmark.py apps/training/tests/test_pose_benchmark_command.py apps/training/tests/test_pose_benchmark_scripts.py
bash -n ../deploy/motion-analysis-smoke/run-benchmark.sh
```

Expected: 全部 PASS，Ruff 和 `bash -n` 退出码均为 0。

- [x] **Step 9: 提交 Task 4**

```bash
git add backend/apps/training/pose_benchmark.py backend/apps/training/management/commands/run_pose_smoke_benchmark.py backend/apps/training/tests/test_pose_benchmark.py backend/apps/training/tests/test_pose_benchmark_command.py backend/apps/training/tests/test_pose_benchmark_scripts.py deploy/motion-analysis-smoke/run-benchmark.sh
git commit -m "test(动作分析): 增加人工真值与资源验收"
```

Expected: 提交只包含 benchmark、命令、脚本和对应测试。

---

### Task 5: 完成本地回归并部署独立算法服务器

**Files:**
- Modify after successful rollout: `docs/superpowers/plans/2026-09-04-pp-tinypose-full-frame-streaming-counter-v2.md`
- Modify for consistency correction: `docs/superpowers/specs/2026-09-03-pp-tinypose-full-frame-streaming-counter-v2-design.md`
- Append after successful rollout: `specs/patient-rehab-system/changelog.md`
- Runtime only: `/opt/motioncare-analysis/app`、`/opt/motioncare-analysis/input`、`/opt/motioncare-analysis/reports`
- Local report only: `/Users/nick/my_dev/ai/agents/reports/pp-tinypose-v2-${run_id}.json`
- Local report only: `/Users/nick/my_dev/ai/agents/reports/pp-tinypose-v2-${run_id}.txt`

**Interfaces:**
- Consumes: Tasks 1–4 的完整实现。
- Produces: 可回退的远端应用版本、脱敏三档验收报告、服务器资源结论和计划执行记录。

- [x] **Step 1: 运行完整本地验证**

Run:

```bash
cd backend
pytest
ruff check .
cd ../frontend
npm run test
npm run lint
npm run build
cd ..
git diff --check
```

Expected: 后端测试和 Ruff 全部通过；前端测试、Lint、构建通过；仅允许已记录的既有前端 warning，不允许新增 error。

- [x] **Step 2: 验证服务器硬件、安全和剩余空间**

Run:

```bash
ssh mcare-pp 'set -e; uname -m; nproc; free -b; swapon --show; df -B1 /opt/motioncare-analysis; stat -c "%U:%G:%a:%n" /opt/motioncare-analysis /opt/motioncare-analysis/app /opt/motioncare-analysis/input'
```

Expected:

- 架构为 `x86_64`，CPU 为 2 vCPU；
- Swap 为 4 GiB 且文件权限仍为 root:root 0600；
- 根分区可用空间不低于 10 GiB；
- 物理内存若已升级，`MemTotal` 不低于 3.5 GiB；若仍低于该值，可以继续功能和算法验收，但最终结论必须标记“尚未达到生产内存规格”。

- [x] **Step 3: 从已提交代码生成可追溯归档**

确保 `git status --short` 只有本计划允许收口的 design/plan 文档改动，然后执行；归档必须取 committed HEAD，不能包含未提交文档：

```bash
analysis_commit="$(git rev-parse HEAD)"
analysis_archive="/tmp/motioncare-analysis-${analysis_commit}.tar.gz"
git archive --format=tar.gz --output="${analysis_archive}" "${analysis_commit}"
shasum -a 256 "${analysis_archive}"
```

Expected: 记录完整 commit、归档路径和 SHA-256；归档中不含 `.env`、私钥、测试视频或本地报告。

- [x] **Step 4: 上传并在新目录验证候选版本**

先上传归档，再创建全新候选目录并设置权限：

```bash
analysis_commit="$(git rev-parse HEAD)"
analysis_archive="/tmp/motioncare-analysis-${analysis_commit}.tar.gz"
scp "${analysis_archive}" "mcare-pp:/tmp/motioncare-analysis-${analysis_commit}.tar.gz"
ssh mcare-pp "set -e
candidate='/opt/motioncare-analysis/app.candidate-${analysis_commit}'
test ! -e \"\${candidate}\"
install -d -m 0750 -o root -g motioncare-analysis \"\${candidate}\"
tar -xzf '/tmp/motioncare-analysis-${analysis_commit}.tar.gz' -C \"\${candidate}\"
chown -R root:motioncare-analysis \"\${candidate}\"
find \"\${candidate}\" -type d -exec chmod 0750 {} +
find \"\${candidate}\" -type f -exec chmod 0640 {} +
chmod 0750 \"\${candidate}/deploy/motion-analysis-smoke/bootstrap.sh\" \"\${candidate}/deploy/motion-analysis-smoke/run-benchmark.sh\"
cd \"\${candidate}/backend\"
runuser -u motioncare-analysis -- env PYTHONDONTWRITEBYTECODE=1 /opt/motioncare-analysis/venv/bin/python manage.py check --no-color
runuser -u motioncare-analysis -- env PYTHONDONTWRITEBYTECODE=1 /opt/motioncare-analysis/venv/bin/python -c 'from apps.training.analysis_registry import MOTION_ANALYZERS; a=MOTION_ANALYZERS[\"motion-resistance-shoulder-press\"]; assert a.rule_version == \"shoulder-press-v2\"'
"
```

Expected: Django 检查和 v2 注册导入通过。失败时当前 `/opt/motioncare-analysis/app` 完全不动，并执行 `mv "/opt/motioncare-analysis/app.candidate-${analysis_commit}" "/opt/motioncare-analysis/app.candidate-${analysis_commit}.failed"` 后停止部署；失败目标已存在时保持候选原位并报告冲突，不覆盖任何目录。

- [x] **Step 5: 原子切换并保留上一版本**

使用失败自动复原的目录移动切换，并保留上一版本：

```bash
analysis_commit="$(git rev-parse HEAD)"
ssh mcare-pp "set -e
current='/opt/motioncare-analysis/app'
candidate='/opt/motioncare-analysis/app.candidate-${analysis_commit}'
previous='/opt/motioncare-analysis/app.previous-77b0166'
failed='/opt/motioncare-analysis/app.failed-${analysis_commit}'
test -d \"\${current}\" && test ! -L \"\${current}\"
test -d \"\${candidate}\" && test ! -L \"\${candidate}\"
test ! -e \"\${previous}\"
test ! -e \"\${failed}\"
mv \"\${current}\" \"\${previous}\"
if ! mv \"\${candidate}\" \"\${current}\"; then
  mv \"\${previous}\" \"\${current}\"
  exit 1
fi
if ! (
  cd \"\${current}/backend\"
  runuser -u motioncare-analysis -- env PYTHONDONTWRITEBYTECODE=1 /opt/motioncare-analysis/venv/bin/python -c 'from apps.training.shoulder_press_v2 import SHOULDER_PRESS_RULE_VERSION; assert SHOULDER_PRESS_RULE_VERSION == \"shoulder-press-v2\"'
); then
  mv \"\${current}\" \"\${failed}\"
  mv \"\${previous}\" \"\${current}\"
  exit 1
fi
"
```

Expected: 新版本从正式工作目录导入成功，旧版本完整保留且可通过目录换回；若切换后的导入检查失败，新版本移入全新失败隔离目录并立即恢复旧版，任何目标冲突都停止且不覆盖。

- [x] **Step 6: 安全上传固定测试视频并执行三档验收**

上传后用 `install -m 0600 -o motioncare-analysis -g motioncare-analysis` 放入固定输入路径，并在服务器重新计算 SHA-256。生成 UTC `run_id`，执行：

```bash
analysis_commit="$(git rev-parse HEAD)"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
scp /Users/nick/my_dev/ai/agents/IMG_0383_SDR_5min.mp4 mcare-pp:/tmp/IMG_0383_SDR_5min.mp4.upload
ssh mcare-pp "set -e
test \"\$(sha256sum /tmp/IMG_0383_SDR_5min.mp4.upload | cut -d' ' -f1)\" = 'f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd'
install -m 0600 -o motioncare-analysis -g motioncare-analysis /tmp/IMG_0383_SDR_5min.mp4.upload /opt/motioncare-analysis/input/IMG_0383_SDR_5min.mp4
unlink /tmp/IMG_0383_SDR_5min.mp4.upload
/opt/motioncare-analysis/app/deploy/motion-analysis-smoke/run-benchmark.sh '${analysis_commit}' '${run_id}'
"
```

Expected: 进程前台串行执行 5 FPS、10 FPS、全帧；无并发第二任务；脚本退出码为 0。

- [x] **Step 7: 下载并核验脱敏报告**

将 JSON/TXT 下载到本地固定报告目录，然后核验：

```bash
install -d -m 0700 /Users/nick/my_dev/ai/agents/reports
scp "mcare-pp:/opt/motioncare-analysis/reports/pp-tinypose-v2-${run_id}.json" /Users/nick/my_dev/ai/agents/reports/
scp "mcare-pp:/opt/motioncare-analysis/reports/pp-tinypose-v2-${run_id}.txt" /Users/nick/my_dev/ai/agents/reports/
jq '{status, manual_total_count, acceptance, modes: [.modes[] | {name, status, count_error, total_count: .result.total_count, total_seconds, resource_peak}]}' "/Users/nick/my_dev/ai/agents/reports/pp-tinypose-v2-${run_id}.json"
```

Expected:

- `status == "completed"`；
- `manual_total_count == 90`；
- `acceptance.passed == true`；
- 全帧 `total_count == 90`；
- 5 FPS、10 FPS 的 `abs(count_error) <= 1`；
- 全帧耗时小于等于 600 秒；
- 全帧峰值 RSS 小于 1.5 GiB，Swap 使用为 0。

- [x] **Step 8: 验证输入清理和运行环境未泄漏**

Run:

```bash
ssh mcare-pp 'set -e; test -z "$(find /opt/motioncare-analysis/input /opt/motioncare-analysis/tmp -mindepth 1 -type f -print -quit)"; if pgrep -af "[r]un_pose_smoke_benchmark"; then exit 1; fi; find /opt/motioncare-analysis/reports -maxdepth 1 -type f -printf "%f\n"'
```

Expected: 输入和临时目录无视频/中间文件，不存在遗留 benchmark 进程；只保留脱敏报告、模型缓存、虚拟环境、新 app 和 previous app。

- [x] **Step 9: 更新本计划执行记录并提交收口**

把本计划所有完成步骤勾选为 `[x]`，状态改为 `implemented`，在头部追加实现 commits、归档 SHA-256、`run_id`、报告路径、90 次结果、耗时、RSS、Swap 和物理内存是否达到 4 GiB；同步 design，并按协作协议只追加一条 changelog 记录。

Run:

```bash
git add docs/superpowers/specs/2026-09-03-pp-tinypose-full-frame-streaming-counter-v2-design.md docs/superpowers/plans/2026-09-04-pp-tinypose-full-frame-streaming-counter-v2.md specs/patient-rehab-system/changelog.md
git commit -m "docs(动作分析): 记录全帧计数v2验收结果"
git status --short
```

Expected: 三份文档记录提交成功；动作分析工作树为空。主检出目录的其它会话改动保持原样。

---

### Task 6: 首次验收失败后修正左右计数语义

- [x] **Step 1: 用脱敏报告定位 400 ms 并集合并导致过计数**
- [x] **Step 2: 经用户批准，将最终次数改为左右独立事件数的较大值**
- [x] **Step 3: 实现锚点侧、单调一对一质量匹配和 401–800 ms 区间重叠扩展规则**
- [x] **Step 4: 拒绝非正时长扩展匹配并通过实现复审**
- [x] **Step 5: 使用最终 HEAD 从头重跑 Task 5 完整本地与远端验收**

---

## 回退步骤

只有在新版本导入失败、真实视频验收失败或上线后任务异常时执行：

1. 停止新的动作分析任务进入该 Worker；当前设计并发为 1，不中断正在写报告的进程。
2. 确认 `/opt/motioncare-analysis/app.previous-77b0166` 是普通目录且权限正确。
3. 把当前 app 移到带失败 commit 的隔离目录，把 previous 目录移动回 `/opt/motioncare-analysis/app`。
4. 从正式工作目录运行 v1 导入检查和 5 FPS 短冒烟。
5. 不修改或删除历史 `MotionAnalysisJob`；通过 `rule_version` 区分已经产生的 v1/v2 结果。
6. 保留失败版本、脱敏报告和资源数据供诊断，不保留输入视频。
