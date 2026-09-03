# PP-TinyPose 算法服务器冒烟测试实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在独立 Ubuntu CPU 服务器上原生部署 MotionCare 的 PP-TinyPose 肩部推举分析能力，并用同一段 5 分钟视频完成 5 FPS、10 FPS、全帧三组可复现冒烟对照。

**Architecture:** 保留生产侧 `extract_video_keypoint_frames(...) -> list[dict]` 接口，新增可复用模型、全帧采样和提取统计接口；冒烟编排作为不访问数据库的 Django 管理命令运行。服务器只安装代码与 CPU 推理依赖，使用专用无登录用户、4 GiB Swap、持久模型缓存和临时输入目录，最终把脱敏报告取回本地并删除服务器视频。

**Tech Stack:** Python 3.12、Django 5 管理命令、PaddlePaddle CPU 3.3.0、PaddleX 3.7.2、PP-TinyPose_128x96、OpenCV headless 4.10–<5、FFmpeg/FFprobe、pytest、Bash、Ubuntu 24.04

**Spec:** `docs/superpowers/specs/2026-09-03-pp-tinypose-algorithm-server-smoke-test-design.md`

> 状态：implemented
> 执行记录（2026-09-03, Codex）：实现提交范围 `ee59e19`、`0788513`、`65fd8e8`、`d2395b4`、`c8d961c`、`10d19a9`、`03b3d90`；服务器实测 `run_id=20260903T112938Z`；最终归档 `/tmp/motioncare-analysis-03b3d90aac42.tar.gz`，SHA256 `c8170e38500e237fd972cdcf09328eb3934dfb09259f64db659e99b96452a33c`。首轮 `model_load` 权限问题经 TDD 修复后，第二轮通过。
> 日期：2026-09-03
> 范围：本地测试视频、单机 CPU、5 FPS/10 FPS/全帧对照、资源报告与清理；不接七牛和生产服务。
> 实施基线 commit：`acda988`

## Global Constraints

- 服务器固定为 `139.224.3.23`，本地 SSH 别名固定为 `mcare-pp`；只允许 SSH 密钥登录，不在任何文件或命令中记录用户曾提供的密码。
- 目标系统固定为 Ubuntu 24.04 LTS x86-64、Python 3.12、2 vCPU、约 1.6 GiB 可见物理内存、40 GiB 系统盘。
- 本轮先不扩容物理内存；只创建 4 GiB Swap 作为 OOM 保护，Swap 使用量必须进入报告且不得被解释为内存充足。
- 推理设备显式设置为 `cpu`，`use_hpip=False`，任务并发为 1，三个模式必须串行运行并复用同一个模型实例。
- 直接依赖固定为 `paddlepaddle==3.3.0`、`paddlex[cv]==3.7.2`、`opencv-python-headless>=4.10,<5.0`。
- 模型固定为 `PP-TinyPose_128x96`；复用 `apps.training.pose_inference` 和 `apps.training.analysis.analyze_shoulder_press_keypoints`，不得另写计数规则。
- 测试视频固定为 `/Users/nick/my_dev/ai/agents/IMG_0383_SDR_5min.mp4`，预期 SHA-256 固定为 `f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd`。
- 三种模式固定为 5 FPS、10 FPS、原始全部解码帧；全帧必须以每次成功 `capture.read()` 为准，不能用容器 FPS 计算一个近似抽样数。
- 冒烟命令不得查询或写入 PostgreSQL、Redis、七牛或任何生产 API，不启动 Celery，不开放公网端口，不创建常驻 systemd 服务。
- 服务端根目录固定为 `/opt/motioncare-analysis`；输入视频权限为 `0600`，报告不得包含患者信息、SSH 信息、凭据、签名 URL 或本地原始绝对路径。
- 根分区可用空间低于 10 GiB 时拒绝上传和运行；5 FPS 或 10 FPS 出现资源故障时不得继续更高负载模式。
- 当前工作区已有其他会话的未提交改动；实施时只修改本计划列出的文件，不暂存、不覆盖这些既有改动。
- 不把单段视频当作医学有效性证明，不依据一个样例自动调整肩部推举阈值。

---

## File Structure

### 新建

- `backend/apps/training/pose_benchmark_resources.py`：读取 Linux `/proc` 并在后台采样进程 RSS、系统内存和 Swap 峰值。
- `backend/apps/training/pose_benchmark.py`：视频哈希/探测、版本采集、三模式编排、资源保护、脱敏报告和原子写入。
- `backend/apps/training/management/__init__.py`：让 Django 发现 training 管理命令包。
- `backend/apps/training/management/commands/__init__.py`：让 Django 发现具体命令。
- `backend/apps/training/management/commands/run_pose_smoke_benchmark.py`：参数校验、SIGTERM 收口、输入清理和命令退出码。
- `backend/apps/training/tests/test_pose_benchmark_resources.py`：`/proc` 解析与峰值聚合测试。
- `backend/apps/training/tests/test_pose_benchmark.py`：哈希、FFprobe、三模式、模型复用、资源跳过、部分失败和报告脱敏测试。
- `backend/apps/training/tests/test_pose_benchmark_command.py`：管理命令成功、哈希失败、`--delete-input` 清理测试。
- `deploy/motion-analysis-smoke/bootstrap.sh`：幂等安装系统包、创建专用用户/目录/虚拟环境和 4 GiB Swap。
- `deploy/motion-analysis-smoke/run-benchmark.sh`：以前台单进程执行冒烟命令，并用 shell `EXIT` trap 兜底删除输入视频。

### 修改

- `backend/apps/training/pose_inference.py`：显式 CPU 模型工厂、首帧预热、全帧模式和提取统计结果；兼容原调用接口。
- `backend/apps/training/tests/test_pose_inference.py`：覆盖 CPU 参数、预热、5 FPS、10 FPS、全帧和旧接口兼容性。
- `backend/pyproject.toml`：把 motion-analysis 三项直接依赖收紧为本设计固定版本。

### 仅运行时生成，不纳入 Git

- `/opt/motioncare-analysis/reports/pp-tinypose-smoke-${run_id}.json`
- `/opt/motioncare-analysis/reports/pp-tinypose-smoke-${run_id}.txt`
- 本地 `/Users/nick/my_dev/ai/agents/reports/pp-tinypose-smoke-${run_id}.json`
- 本地 `/Users/nick/my_dev/ai/agents/reports/pp-tinypose-smoke-${run_id}.txt`

---

### Task 1: 扩展 PP-TinyPose 推理接口并保持生产兼容

**Files:**
- Modify: `backend/apps/training/pose_inference.py`
- Test: `backend/apps/training/tests/test_pose_inference.py`

**Interfaces:**
- Produces: `create_pose_model(*, device: str = "cpu") -> object`，固定调用 `create_model(model_name=PP_TINYPOSE_MODEL_NAME, device=device, use_hpip=False)`。
- Produces: `warm_up_pose_model(video_path, *, model, capture=None) -> None`，读取第一帧有效视频并执行一次预测，始终释放 capture。
- Produces: `VideoKeypointExtraction(frames: list[dict], decoded_frame_count: int, inferred_frame_count: int, source_fps: float)`。
- Produces: `extract_video_keypoint_frames_with_stats(video_path, *, sample_fps: float | None = DEFAULT_SAMPLE_FPS, model=None, capture=None) -> VideoKeypointExtraction`；`None` 表示每个成功解码帧都推理。
- Preserves: `extract_video_keypoint_frames(...) -> list[dict]` 继续供 `apps.training.tasks` 使用，默认仍为 5 FPS。

- [x] **Step 1: 写 CPU 模型、预热、全帧和兼容性失败测试**

在 `test_pose_inference.py` 增加：

```python
from apps.training.pose_inference import (
    PP_TINYPOSE_MODEL_NAME,
    VideoKeypointExtraction,
    create_pose_model,
    extract_video_keypoint_frames_with_stats,
    warm_up_pose_model,
)


def test_create_pose_model_forces_cpu_and_disables_hpip(monkeypatch):
    create_model = Mock(return_value=object())
    monkeypatch.setattr(
        "apps.training.pose_inference.load_motion_analysis_runtime",
        lambda: (Mock(), create_model),
    )

    model = create_pose_model()

    assert model is create_model.return_value
    create_model.assert_called_once_with(
        model_name=PP_TINYPOSE_MODEL_NAME,
        device="cpu",
        use_hpip=False,
    )


def test_warm_up_uses_first_decoded_frame_and_releases_capture():
    capture = FakeCapture([0, 100])
    model = FakeModel()

    warm_up_pose_model("ignored.mp4", model=model, capture=capture)

    assert model.seen_frames == [0]
    assert capture.released is True


def test_full_frame_mode_infers_every_decoded_frame():
    capture = FakeCapture([0, 100, 200, 300, 400])
    model = FakeModel()

    result = extract_video_keypoint_frames_with_stats(
        "ignored.mp4",
        sample_fps=None,
        model=model,
        capture=capture,
    )

    assert isinstance(result, VideoKeypointExtraction)
    assert result.decoded_frame_count == 5
    assert result.inferred_frame_count == 5
    assert model.seen_frames == [0, 1, 2, 3, 4]
    assert [frame["timestamp_ms"] for frame in result.frames] == [0, 100, 200, 300, 400]


def test_ten_fps_mode_reports_decoded_and_inferred_counts():
    capture = FakeCapture([0, 50, 100, 150, 200])
    model = FakeModel()

    result = extract_video_keypoint_frames_with_stats(
        "ignored.mp4",
        sample_fps=10,
        model=model,
        capture=capture,
    )

    assert result.decoded_frame_count == 5
    assert result.inferred_frame_count == 3
    assert model.seen_frames == [0, 2, 4]


def test_existing_extractor_still_returns_only_frame_list():
    capture = FakeCapture([0, 100, 200])
    frames = extract_video_keypoint_frames(
        "ignored.mp4",
        sample_fps=5,
        model=FakeModel(),
        capture=capture,
    )

    assert isinstance(frames, list)
    assert [frame["timestamp_ms"] for frame in frames] == [0, 200]


@pytest.mark.parametrize("sample_fps", [0, -1])
def test_stats_extractor_rejects_non_positive_fixed_fps(sample_fps):
    with pytest.raises(ValueError, match="sample_fps"):
        extract_video_keypoint_frames_with_stats(
            "ignored.mp4",
            sample_fps=sample_fps,
            model=FakeModel(),
            capture=FakeCapture([]),
        )
```

- [x] **Step 2: 运行测试并确认新接口尚不存在**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_inference.py -q
```

Expected: FAIL，导入错误包含 `VideoKeypointExtraction` 或 `create_pose_model`。

- [x] **Step 3: 实现固定 CPU 模型工厂与预热**

在 `pose_inference.py` 顶部增加 `dataclass`，并在运行时加载函数后加入：

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class VideoKeypointExtraction:
    frames: list[dict]
    decoded_frame_count: int
    inferred_frame_count: int
    source_fps: float


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
```

将 `_first_prediction` 保持为唯一调用 `model.predict(frame)` 的低层适配器；不要在预热函数复制 PaddleX 结果迭代逻辑。

- [x] **Step 4: 实现带统计的固定 FPS/全帧提取，并让旧函数做代理**

用下列两个函数替换现有 `extract_video_keypoint_frames`：

```python
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
```

- [x] **Step 5: 运行推理适配器和生产任务回归测试**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_inference.py apps/training/tests/test_motion_analysis.py -q
```

Expected: PASS；原有任务测试继续断言默认采样率传入旧接口。

- [x] **Step 6: 提交 Task 1**

```bash
git add backend/apps/training/pose_inference.py backend/apps/training/tests/test_pose_inference.py
git commit -m "feat(动作分析): 支持全帧推理与模型复用"
```

Expected: 提交中只包含上述两个文件。

---

### Task 2: 增加 Linux 资源峰值采样器

**Files:**
- Create: `backend/apps/training/pose_benchmark_resources.py`
- Create: `backend/apps/training/tests/test_pose_benchmark_resources.py`

**Interfaces:**
- Produces: `ResourceSnapshot(process_rss_bytes: int, system_memory_used_bytes: int, memory_available_bytes: int, swap_used_bytes: int, swap_free_bytes: int)`。
- Produces: `read_linux_resource_snapshot(*, meminfo_path=Path("/proc/meminfo"), statm_path=Path("/proc/self/statm"), page_size=None) -> ResourceSnapshot`。
- Produces: `ResourceSampler(reader=read_linux_resource_snapshot, interval_seconds=0.5)` 上下文管理器，退出后通过 `.peak` 读取逐字段峰值/最低余量。

- [x] **Step 1: 写 `/proc` 解析与峰值测试**

创建 `test_pose_benchmark_resources.py`：

```python
from apps.training.pose_benchmark_resources import (
    ResourceSampler,
    ResourceSnapshot,
    read_linux_resource_snapshot,
)


def test_reads_linux_process_memory_and_swap(tmp_path):
    meminfo = tmp_path / "meminfo"
    statm = tmp_path / "statm"
    meminfo.write_text(
        "MemTotal:       2048000 kB\n"
        "MemAvailable:    512000 kB\n"
        "SwapTotal:      4194304 kB\n"
        "SwapFree:       3145728 kB\n",
        encoding="utf-8",
    )
    statm.write_text("1000 250 0 0 0 0 0\n", encoding="utf-8")

    snapshot = read_linux_resource_snapshot(
        meminfo_path=meminfo,
        statm_path=statm,
        page_size=4096,
    )

    assert snapshot.process_rss_bytes == 250 * 4096
    assert snapshot.system_memory_used_bytes == (2048000 - 512000) * 1024
    assert snapshot.memory_available_bytes == 512000 * 1024
    assert snapshot.swap_used_bytes == (4194304 - 3145728) * 1024
    assert snapshot.swap_free_bytes == 3145728 * 1024


def test_sampler_keeps_peaks_and_lowest_available_values():
    snapshots = iter(
        [
            ResourceSnapshot(100, 500, 900, 10, 990),
            ResourceSnapshot(300, 700, 600, 40, 960),
            ResourceSnapshot(200, 650, 750, 20, 980),
        ]
    )
    sampler = ResourceSampler(reader=lambda: next(snapshots), interval_seconds=60)

    sampler.sample_once()
    sampler.sample_once()
    sampler.sample_once()

    assert sampler.peak == ResourceSnapshot(300, 700, 600, 40, 960)
```

- [x] **Step 2: 运行测试并确认模块尚不存在**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark_resources.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.training.pose_benchmark_resources'`。

- [x] **Step 3: 实现 Linux 资源读取与后台采样**

创建 `pose_benchmark_resources.py`：

```python
import os
import threading
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResourceSnapshot:
    process_rss_bytes: int
    system_memory_used_bytes: int
    memory_available_bytes: int
    swap_used_bytes: int
    swap_free_bytes: int


def _read_meminfo(path):
    values = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        key, raw_value = line.split(":", 1)
        values[key] = int(raw_value.strip().split()[0]) * 1024
    required = ("MemTotal", "MemAvailable", "SwapTotal", "SwapFree")
    if any(key not in values for key in required):
        raise RuntimeError("/proc/meminfo 缺少必要字段")
    return values


def read_linux_resource_snapshot(
    *,
    meminfo_path=Path("/proc/meminfo"),
    statm_path=Path("/proc/self/statm"),
    page_size=None,
):
    memory = _read_meminfo(meminfo_path)
    fields = Path(statm_path).read_text(encoding="utf-8").split()
    if len(fields) < 2:
        raise RuntimeError("/proc/self/statm 格式无效")
    resident_pages = int(fields[1])
    resolved_page_size = page_size or os.sysconf("SC_PAGE_SIZE")
    return ResourceSnapshot(
        process_rss_bytes=resident_pages * resolved_page_size,
        system_memory_used_bytes=memory["MemTotal"] - memory["MemAvailable"],
        memory_available_bytes=memory["MemAvailable"],
        swap_used_bytes=memory["SwapTotal"] - memory["SwapFree"],
        swap_free_bytes=memory["SwapFree"],
    )


class ResourceSampler:
    def __init__(self, *, reader=read_linux_resource_snapshot, interval_seconds=0.5):
        self._reader = reader
        self._interval_seconds = interval_seconds
        self._stop = threading.Event()
        self._thread = None
        self.peak = None

    def sample_once(self):
        current = self._reader()
        if self.peak is None:
            self.peak = current
        else:
            self.peak = ResourceSnapshot(
                process_rss_bytes=max(self.peak.process_rss_bytes, current.process_rss_bytes),
                system_memory_used_bytes=max(
                    self.peak.system_memory_used_bytes,
                    current.system_memory_used_bytes,
                ),
                memory_available_bytes=min(
                    self.peak.memory_available_bytes,
                    current.memory_available_bytes,
                ),
                swap_used_bytes=max(self.peak.swap_used_bytes, current.swap_used_bytes),
                swap_free_bytes=min(self.peak.swap_free_bytes, current.swap_free_bytes),
            )
        return current

    def _run(self):
        while not self._stop.wait(self._interval_seconds):
            self.sample_once()

    def __enter__(self):
        self.sample_once()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(1.0, self._interval_seconds * 2))
        self.sample_once()
```

- [x] **Step 4: 运行资源采样测试**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark_resources.py -q
```

Expected: PASS。

- [x] **Step 5: 提交 Task 2**

```bash
git add backend/apps/training/pose_benchmark_resources.py backend/apps/training/tests/test_pose_benchmark_resources.py
git commit -m "feat(动作分析): 采集冒烟测试资源峰值"
```

---

### Task 3: 实现视频探测、三模式编排与原子报告

**Files:**
- Create: `backend/apps/training/pose_benchmark.py`
- Create: `backend/apps/training/tests/test_pose_benchmark.py`

**Interfaces:**
- Consumes: `create_pose_model`、`warm_up_pose_model`、`extract_video_keypoint_frames_with_stats`、`analyze_shoulder_press_keypoints`、`ResourceSampler`。
- Produces: `BenchmarkMode(name: str, sample_fps: float | None)` 与固定 `BENCHMARK_MODES = (5fps, 10fps, all_frames)`。
- Produces: `sha256_file(path: Path) -> str`。
- Produces: `probe_video(path: Path, *, ffprobe_path: str = "/usr/bin/ffprobe", runner=subprocess.run) -> dict`，同时保留 `r_frame_rate` 和 `avg_frame_rate`。
- Produces: `run_pose_smoke_benchmark(video_path: Path, *, report_path: Path, summary_path: Path, expected_sha256: str, git_commit: str, ...) -> dict`。
- Produces: `BenchmarkFailure(RuntimeError)`；任何失败都先原子写入当前报告，再抛出该异常。

- [x] **Step 1: 写探测、成功编排、资源跳过和脱敏失败测试**

创建 `test_pose_benchmark.py`，使用小型假对象而不导入 PaddleX：

```python
import json
import subprocess
from types import SimpleNamespace

import pytest

from apps.training.pose_benchmark import (
    BenchmarkFailure,
    probe_video,
    run_pose_smoke_benchmark,
    sha256_file,
)
from apps.training.pose_benchmark_resources import ResourceSnapshot
from apps.training.pose_inference import VideoKeypointExtraction


class FakeSampler:
    def __init__(self, peak):
        self.peak = peak

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _peak(*, available=800 * 1024**2, swap_free=3 * 1024**3):
    return ResourceSnapshot(
        process_rss_bytes=400 * 1024**2,
        system_memory_used_bytes=900 * 1024**2,
        memory_available_bytes=available,
        swap_used_bytes=100 * 1024**2,
        swap_free_bytes=swap_free,
    )


def _probe_payload():
    return subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout=json.dumps(
            {
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30/1",
                        "avg_frame_rate": "8929/300",
                        "nb_frames": "8929",
                    },
                    {"codec_type": "audio", "codec_name": "aac"},
                ],
                "format": {"duration": "300", "size": "384318737"},
            }
        ),
        stderr="",
    )


def test_probe_video_preserves_nominal_and_average_rates(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    result = probe_video(video, ffprobe_path="ffprobe", runner=lambda *a, **k: _probe_payload())

    assert result["nominal_frame_rate"] == "30/1"
    assert result["average_frame_rate"] == "8929/300"
    assert result["reported_frame_count"] == 8929


def test_runs_all_modes_with_one_model_and_writes_sanitized_reports(tmp_path):
    video = tmp_path / "patient-name-must-not-leak.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    summary = tmp_path / "report.txt"
    model = object()
    model_factory_calls = []
    sample_modes = []

    def model_factory():
        model_factory_calls.append(True)
        return model

    def extractor(path, *, sample_fps, model):
        assert path == video
        assert model is not None
        sample_modes.append(sample_fps)
        count = {5.0: 2, 10.0: 3, None: 5}[sample_fps]
        frames = [{"timestamp_ms": index * 100, "keypoints": {}} for index in range(count)]
        return VideoKeypointExtraction(frames, 5, count, 30.0)

    result = run_pose_smoke_benchmark(
        video,
        report_path=report,
        summary_path=summary,
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        ffprobe_runner=lambda *a, **k: _probe_payload(),
        model_factory=model_factory,
        warm_up=lambda path, *, model: None,
        extractor=extractor,
        analyzer=lambda frames: {
            "total_count": len(frames),
            "standard_count": len(frames),
            "nonstandard_count": 0,
            "rep_details": [],
            "quality_flags": ["camera_angle_unverified"],
        },
        sampler_factory=lambda: FakeSampler(_peak()),
        version_reader=lambda: {"python": "3.12.3", "paddlepaddle": "3.3.0"},
        hardware_reader=lambda: {"cpu_model": "Fake CPU", "vcpu_count": 2},
    )

    assert len(model_factory_calls) == 1
    assert sample_modes == [5.0, 10.0, None]
    assert [item["status"] for item in result["modes"]] == ["completed"] * 3
    assert [item["inferred_frame_count"] for item in result["modes"]] == [2, 3, 5]
    serialized = report.read_text(encoding="utf-8")
    assert str(video) not in serialized
    assert video.name not in serialized
    assert "abc1234" in serialized
    assert result["manual_total_count"] == "not_provided"
    assert "5 FPS" in summary.read_text(encoding="utf-8")


def test_skips_all_frames_when_ten_fps_exhausts_safety_reserve(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    peaks = iter([_peak(), _peak(available=200 * 1024**2)])
    modes = []

    result = run_pose_smoke_benchmark(
        video,
        report_path=tmp_path / "report.json",
        summary_path=tmp_path / "report.txt",
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        ffprobe_runner=lambda *a, **k: _probe_payload(),
        model_factory=lambda: object(),
        warm_up=lambda path, *, model: None,
        extractor=lambda path, *, sample_fps, model: (
            modes.append(sample_fps)
            or VideoKeypointExtraction(
                [{"timestamp_ms": 0, "keypoints": {}}], 1, 1, 30.0
            )
        ),
        analyzer=lambda frames: {
            "total_count": 0,
            "standard_count": 0,
            "nonstandard_count": 0,
            "rep_details": [],
            "quality_flags": [],
        },
        sampler_factory=lambda: FakeSampler(next(peaks)),
        version_reader=lambda: {},
        hardware_reader=lambda: {},
    )

    assert modes == [5.0, 10.0]
    assert result["modes"][2]["status"] == "skipped_for_resource_safety"
    assert result["modes"][2]["reason"] == "memory_available_below_256_mib"


def test_hash_mismatch_writes_failed_report_before_model_load(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"

    with pytest.raises(BenchmarkFailure, match="SHA-256"):
        run_pose_smoke_benchmark(
            video,
            report_path=report,
            summary_path=tmp_path / "report.txt",
            expected_sha256="0" * 64,
            git_commit="abc1234",
            model_factory=lambda: pytest.fail("哈希失败后不得加载模型"),
        )

    payload = json.loads(report.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert str(video) not in json.dumps(payload, ensure_ascii=False)
    assert "private-video" not in json.dumps(payload, ensure_ascii=False)
```

再增加资源失败脱敏用例：

```python
def test_resource_failure_is_sanitized_and_stops_higher_modes(tmp_path):
    video = tmp_path / "private-video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "report.json"
    calls = []

    def extractor(path, *, sample_fps, model):
        calls.append(sample_fps)
        raise MemoryError("private /path/video.mp4")

    result = run_pose_smoke_benchmark(
        video,
        report_path=report,
        summary_path=tmp_path / "report.txt",
        expected_sha256=sha256_file(video),
        git_commit="abc1234",
        ffprobe_runner=lambda *a, **k: _probe_payload(),
        model_factory=lambda: object(),
        warm_up=lambda path, *, model: None,
        extractor=extractor,
        analyzer=lambda frames: {},
        sampler_factory=lambda: FakeSampler(_peak()),
        version_reader=lambda: {},
        hardware_reader=lambda: {},
    )

    assert calls == [5.0]
    assert result["modes"][0]["status"] == "failed"
    assert result["modes"][0]["error_type"] == "MemoryError"
    assert result["modes"][1]["status"] == "skipped_for_resource_safety"
    assert result["modes"][2]["status"] == "skipped_for_resource_safety"
    serialized = report.read_text(encoding="utf-8")
    assert "private /path" not in serialized
    assert str(video) not in serialized
```

- [x] **Step 2: 运行测试并确认冒烟模块尚不存在**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark.py -q
```

Expected: FAIL with `ModuleNotFoundError: No module named 'apps.training.pose_benchmark'`。

- [x] **Step 3: 实现探测、版本、硬件和原子报告基础函数**

创建 `pose_benchmark.py`，先实现下列固定结构：

```python
import errno
import gc
import hashlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

from .analysis import analyze_shoulder_press_keypoints
from .pose_benchmark_resources import ResourceSampler, read_linux_resource_snapshot
from .pose_inference import (
    PP_TINYPOSE_MODEL_NAME,
    create_pose_model,
    extract_video_keypoint_frames_with_stats,
    warm_up_pose_model,
)

MIB = 1024**2
MIN_MEMORY_AVAILABLE_BYTES = 256 * MIB
MIN_SWAP_FREE_BYTES = 512 * MIB
REPORT_FORMAT_VERSION = "1.0"


class BenchmarkFailure(RuntimeError):
    pass


@dataclass(frozen=True)
class BenchmarkMode:
    name: str
    sample_fps: float | None


BENCHMARK_MODES = (
    BenchmarkMode("5fps", 5.0),
    BenchmarkMode("10fps", 10.0),
    BenchmarkMode("all_frames", None),
)


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _probe_video_unchecked(path, *, ffprobe_path, runner):
    completed = runner(
        [
            ffprobe_path,
            "-v", "error",
            "-show_streams",
            "-show_format",
            "-of", "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    payload = json.loads(completed.stdout)
    streams = payload["streams"]
    video = next(item for item in streams if item.get("codec_type") == "video")
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    return {
        "sha256": sha256_file(path),
        "size_bytes": int(payload["format"]["size"]),
        "duration_seconds": float(payload["format"]["duration"]),
        "video_codec": str(video["codec_name"]),
        "audio_codec": None if audio is None else str(audio["codec_name"]),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "nominal_frame_rate": str(video.get("r_frame_rate") or ""),
        "average_frame_rate": str(video.get("avg_frame_rate") or ""),
        "reported_frame_count": (
            None if not video.get("nb_frames") else int(video["nb_frames"])
        ),
    }


def probe_video(path, *, ffprobe_path="/usr/bin/ffprobe", runner=subprocess.run):
    try:
        return _probe_video_unchecked(path, ffprobe_path=ffprobe_path, runner=runner)
    except (
        OSError,
        subprocess.CalledProcessError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
        KeyError,
        StopIteration,
        TypeError,
        ValueError,
    ) as exc:
        raise BenchmarkFailure("视频探测失败") from exc


def read_versions():
    versions = {"python": platform.python_version()}
    for distribution in ("paddlepaddle", "paddlex", "opencv-python-headless"):
        try:
            versions[distribution] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[distribution] = "not_installed"
    completed = subprocess.run(
        ["/usr/bin/ffmpeg", "-version"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    versions["ffmpeg"] = completed.stdout.splitlines()[0]
    return versions


def read_hardware():
    cpu_model = "unknown"
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name"):
                cpu_model = line.split(":", 1)[1].strip()
                break
    snapshot = read_linux_resource_snapshot()
    return {
        "cpu_model": cpu_model,
        "vcpu_count": os.cpu_count(),
        "physical_memory_bytes": (
            snapshot.system_memory_used_bytes + snapshot.memory_available_bytes
        ),
        "swap_total_bytes": snapshot.swap_used_bytes + snapshot.swap_free_bytes,
    }


def _atomic_write_text(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def _write_report(report_path, summary_path, report):
    _atomic_write_text(
        report_path,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    lines = [
        f"状态: {report['status']}",
        f"模型: {report['model']['name']} ({report['model']['device']})",
    ]
    for mode in report.get("modes", []):
        lines.append(
            f"{mode['label']}: {mode['status']}; "
            f"推理帧={mode.get('inferred_frame_count', '-')}; "
            f"总次数={mode.get('result', {}).get('total_count', '-')}"
        )
    _atomic_write_text(summary_path, "\n".join(lines) + "\n")
```

`probe_video` 只公开固定中文错误，不得把 subprocess stderr 原文写入报告。

- [x] **Step 4: 实现三模式编排、资源门禁和失败收口**

在同一文件实现 `run_pose_smoke_benchmark`，固定执行顺序与报告字段：

```python
def run_pose_smoke_benchmark(
    video_path,
    *,
    report_path,
    summary_path,
    expected_sha256,
    git_commit,
    ffprobe_path="/usr/bin/ffprobe",
    ffprobe_runner=subprocess.run,
    model_factory=create_pose_model,
    warm_up=warm_up_pose_model,
    extractor=extract_video_keypoint_frames_with_stats,
    analyzer=analyze_shoulder_press_keypoints,
    sampler_factory=ResourceSampler,
    version_reader=read_versions,
    hardware_reader=read_hardware,
    monotonic=time.monotonic,
):
    video_path = Path(video_path)
    started_at = datetime.now(timezone.utc)
    report = {
        "report_format_version": REPORT_FORMAT_VERSION,
        "status": "running",
        "started_at": started_at.isoformat(),
        "finished_at": None,
        "git_commit": git_commit,
        "versions": {},
        "hardware": {},
        "video": {},
        "model": {"name": PP_TINYPOSE_MODEL_NAME, "device": "cpu"},
        "manual_total_count": "not_provided",
        "modes": [],
    }
    stage = "hash_validation"

    def persist():
        _write_report(report_path, summary_path, report)

    try:
        actual_sha256 = sha256_file(video_path)
        if actual_sha256 != expected_sha256.lower():
            raise BenchmarkFailure("视频 SHA-256 与预期不一致")
        stage = "video_probe"
        report["video"] = probe_video(
            video_path,
            ffprobe_path=ffprobe_path,
            runner=ffprobe_runner,
        )
        report["versions"] = version_reader()
        report["hardware"] = hardware_reader()
        persist()

        stage = "model_load"
        model_started = monotonic()
        model = model_factory()
        report["model"]["load_seconds"] = monotonic() - model_started
        stage = "model_warm_up"
        warm_started = monotonic()
        warm_up(video_path, model=model)
        report["model"]["warm_up_seconds"] = monotonic() - warm_started
        persist()

        resource_abort = False
        for mode in BENCHMARK_MODES:
            label = "全帧" if mode.sample_fps is None else f"{int(mode.sample_fps)} FPS"
            if resource_abort:
                report["modes"].append(
                    {
                        "name": mode.name,
                        "label": label,
                        "sample_fps": mode.sample_fps,
                        "status": "skipped_for_resource_safety",
                        "reason": "prior_resource_failure",
                    }
                )
                persist()
                continue
            if mode.sample_fps is None and report["modes"]:
                previous_peak = report["modes"][-1].get("resource_peak", {})
                if previous_peak.get("memory_available_bytes", 0) < MIN_MEMORY_AVAILABLE_BYTES:
                    report["modes"].append(
                        {
                            "name": mode.name,
                            "label": label,
                            "sample_fps": None,
                            "status": "skipped_for_resource_safety",
                            "reason": "memory_available_below_256_mib",
                        }
                    )
                    persist()
                    continue
                if previous_peak.get("swap_free_bytes", 0) < MIN_SWAP_FREE_BYTES:
                    report["modes"].append(
                        {
                            "name": mode.name,
                            "label": label,
                            "sample_fps": None,
                            "status": "skipped_for_resource_safety",
                            "reason": "swap_free_below_512_mib",
                        }
                    )
                    persist()
                    continue

            mode_report = {
                "name": mode.name,
                "label": label,
                "sample_fps": mode.sample_fps,
                "status": "running",
            }
            report["modes"].append(mode_report)
            persist()
            stage = f"{mode.name}_inference"
            mode_started = monotonic()
            extraction = None
            sampler = None
            try:
                with sampler_factory() as sampler:
                    inference_started = monotonic()
                    extraction = extractor(
                        video_path,
                        sample_fps=mode.sample_fps,
                        model=model,
                    )
                    inference_seconds = monotonic() - inference_started
                    result = analyzer(extraction.frames)
                mode_report.update(
                    {
                        "status": "completed",
                        "decoded_frame_count": extraction.decoded_frame_count,
                        "inferred_frame_count": extraction.inferred_frame_count,
                        "source_fps": extraction.source_fps,
                        "inference_seconds": inference_seconds,
                        "total_seconds": monotonic() - mode_started,
                        "average_inference_ms_per_frame": (
                            inference_seconds * 1000 / extraction.inferred_frame_count
                        ),
                        "resource_peak": asdict(sampler.peak),
                        "result": result,
                    }
                )
            except (MemoryError, OSError) as exc:
                if isinstance(exc, OSError) and exc.errno != errno.ENOMEM:
                    raise
                mode_report.update(
                    {
                        "status": "failed",
                        "failure_stage": stage,
                        "error_type": type(exc).__name__,
                        "error_summary": "推理阶段发生资源错误",
                        "resource_peak": (
                            None
                            if sampler is None or sampler.peak is None
                            else asdict(sampler.peak)
                        ),
                    }
                )
                resource_abort = True
            finally:
                if extraction is not None:
                    del extraction
                gc.collect()
                persist()

        report["status"] = (
            "completed"
            if all(item["status"] == "completed" for item in report["modes"][:2])
            else "failed"
        )
    except BaseException as exc:
        report["status"] = "failed"
        report["failure"] = {
            "stage": stage,
            "error_type": type(exc).__name__,
            "error_summary": (
                str(exc) if isinstance(exc, BenchmarkFailure) else "冒烟测试执行失败"
            ),
        }
        report["finished_at"] = datetime.now(timezone.utc).isoformat()
        persist()
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        raise BenchmarkFailure(report["failure"]["error_summary"]) from exc

    stage = "complete"
    report["finished_at"] = datetime.now(timezone.utc).isoformat()
    persist()
    return report
```

局部变量每轮先设为 `None`，避免上一轮对象被重复引用。若 5 FPS 或 10 FPS 是资源失败，后续模式均标记 `skipped_for_resource_safety`；非资源异常进入外层失败收口并停止运行。报告 `status=completed` 的含义固定为 5 FPS 和 10 FPS 均完成，全帧允许完成、资源跳过或失败。

- [x] **Step 5: 运行冒烟编排单元测试**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark.py -q
```

Expected: PASS；测试生成的 JSON 中不包含输入文件路径或文件名。

- [x] **Step 6: 提交 Task 3**

```bash
git add backend/apps/training/pose_benchmark.py backend/apps/training/tests/test_pose_benchmark.py
git commit -m "feat(动作分析): 增加三档冒烟测试报告"
```

---

### Task 4: 增加管理命令、固定依赖与服务器初始化脚本

**Files:**
- Create: `backend/apps/training/management/__init__.py`
- Create: `backend/apps/training/management/commands/__init__.py`
- Create: `backend/apps/training/management/commands/run_pose_smoke_benchmark.py`
- Create: `backend/apps/training/tests/test_pose_benchmark_command.py`
- Modify: `backend/pyproject.toml`
- Create: `deploy/motion-analysis-smoke/bootstrap.sh`
- Create: `deploy/motion-analysis-smoke/run-benchmark.sh`

**Interfaces:**
- Produces CLI: `python manage.py run_pose_smoke_benchmark --video PATH --report PATH --summary PATH --expected-sha256 HEX --git-commit SHA [--delete-input]`。
- Produces: `bootstrap.sh` 仅接受环境变量 `MOTIONCARE_ANALYSIS_ROOT`，默认 `/opt/motioncare-analysis`；只允许 root 执行。
- Produces: `run-benchmark.sh COMMIT RUN_ID`，验证参数、以前台单进程运行命令，并在 shell 退出时再次清理固定输入文件。
- Consumes: Task 3 `run_pose_smoke_benchmark(...)`；成功退出码 0，失败抛 `CommandError` 并返回非零。

- [x] **Step 1: 写管理命令失败测试**

创建命令包的两个空 `__init__.py`，再创建 `test_pose_benchmark_command.py`：

```python
from pathlib import Path
from unittest.mock import Mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def test_command_passes_fixed_paths_and_deletes_input_after_success(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    report = tmp_path / "reports" / "report.json"
    summary = tmp_path / "reports" / "report.txt"
    runner = Mock(return_value={"status": "completed"})
    monkeypatch.setattr(
        "apps.training.management.commands.run_pose_smoke_benchmark.run_pose_smoke_benchmark",
        runner,
    )

    call_command(
        "run_pose_smoke_benchmark",
        video=str(video),
        report=str(report),
        summary=str(summary),
        expected_sha256="f" * 64,
        git_commit="abc1234",
        delete_input=True,
    )

    assert not video.exists()
    runner.assert_called_once_with(
        Path(video),
        report_path=Path(report),
        summary_path=Path(summary),
        expected_sha256="f" * 64,
        git_commit="abc1234",
    )


def test_command_deletes_input_even_when_benchmark_fails(tmp_path, monkeypatch):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    monkeypatch.setattr(
        "apps.training.management.commands.run_pose_smoke_benchmark.run_pose_smoke_benchmark",
        Mock(side_effect=RuntimeError("private failure /path/video.mp4")),
    )

    with pytest.raises(CommandError, match="冒烟测试失败"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
            delete_input=True,
        )

    assert not video.exists()
```

增加参数校验用例：

```python
@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"expected_sha256": "bad"}, "expected-sha256"),
        ({"git_commit": "not-a-commit"}, "git-commit"),
    ],
)
def test_command_rejects_invalid_identifiers(tmp_path, overrides, message):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")
    options = {
        "video": str(video),
        "report": str(tmp_path / "reports" / "report.json"),
        "summary": str(tmp_path / "reports" / "report.txt"),
        "expected_sha256": "f" * 64,
        "git_commit": "abc1234",
    }
    options.update(overrides)

    with pytest.raises(CommandError, match=message):
        call_command("run_pose_smoke_benchmark", **options)


def test_command_rejects_symlink_input(tmp_path):
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    video = tmp_path / "link.mp4"
    video.symlink_to(source)

    with pytest.raises(CommandError, match="符号链接"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "reports" / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
        )


def test_command_rejects_reports_in_input_directory(tmp_path):
    video = tmp_path / "video.mp4"
    video.write_bytes(b"video")

    with pytest.raises(CommandError, match="报告不能写入输入目录"):
        call_command(
            "run_pose_smoke_benchmark",
            video=str(video),
            report=str(tmp_path / "report.json"),
            summary=str(tmp_path / "reports" / "report.txt"),
            expected_sha256="f" * 64,
            git_commit="abc1234",
        )
```

- [x] **Step 2: 运行命令测试并确认命令尚不存在**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark_command.py -q
```

Expected: FAIL，错误包含 `Unknown command: 'run_pose_smoke_benchmark'`。

- [x] **Step 3: 实现管理命令与 SIGTERM 收口**

创建 `run_pose_smoke_benchmark.py`：

```python
import re
import signal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.training.pose_benchmark import BenchmarkFailure, run_pose_smoke_benchmark

SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")
COMMIT_PATTERN = re.compile(r"^[a-f0-9]{7,40}$")


class Command(BaseCommand):
    help = "Run isolated PP-TinyPose smoke benchmark without database access"

    def add_arguments(self, parser):
        parser.add_argument("--video", required=True)
        parser.add_argument("--report", required=True)
        parser.add_argument("--summary", required=True)
        parser.add_argument("--expected-sha256", required=True)
        parser.add_argument("--git-commit", required=True)
        parser.add_argument("--delete-input", action="store_true")

    def handle(self, *args, **options):
        video = Path(options["video"])
        report = Path(options["report"])
        summary = Path(options["summary"])
        expected_sha256 = options["expected_sha256"].lower()
        git_commit = options["git_commit"].lower()
        if video.is_symlink() or not video.is_file():
            raise CommandError("视频必须是普通文件且不能是符号链接")
        if not SHA256_PATTERN.fullmatch(expected_sha256):
            raise CommandError("expected-sha256 格式无效")
        if not COMMIT_PATTERN.fullmatch(git_commit):
            raise CommandError("git-commit 格式无效")
        if report.parent.resolve() == video.parent.resolve():
            raise CommandError("报告不能写入输入目录")
        if summary.parent.resolve() == video.parent.resolve():
            raise CommandError("摘要不能写入输入目录")

        previous_sigterm = signal.getsignal(signal.SIGTERM)

        def interrupt_on_sigterm(signum, frame):
            raise KeyboardInterrupt("received SIGTERM")

        signal.signal(signal.SIGTERM, interrupt_on_sigterm)
        try:
            result = run_pose_smoke_benchmark(
                video,
                report_path=report,
                summary_path=summary,
                expected_sha256=expected_sha256,
                git_commit=git_commit,
            )
        except (BenchmarkFailure, RuntimeError) as exc:
            raise CommandError("冒烟测试失败，详情见脱敏报告") from exc
        finally:
            signal.signal(signal.SIGTERM, previous_sigterm)
            if options["delete_input"]:
                video.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f"冒烟测试完成：{result['status']}"))
```

`KeyboardInterrupt` 不要转换为包含原始异常的 `CommandError`，但 `finally` 仍必须删除输入文件并恢复原信号处理器。

- [x] **Step 4: 收紧动作分析依赖版本**

将 `backend/pyproject.toml` 的可选依赖改为：

```toml
motion-analysis = [
  "paddlepaddle==3.3.0",
  "paddlex[cv]==3.7.2",
  "opencv-python-headless>=4.10,<5.0",
]
```

普通 `pip install -e ".[dev]"` 仍不安装重型动作分析依赖；服务器使用非 editable 的 `pip install "/opt/motioncare-analysis/app/backend[motion-analysis]"`，避免专用用户向 root 管理的源码目录写入 egg-info。

- [x] **Step 5: 写幂等服务器初始化脚本**

创建 `deploy/motion-analysis-smoke/bootstrap.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

if [[ "${EUID}" -ne 0 ]]; then
  echo "必须以 root 执行" >&2
  exit 1
fi

analysis_root="${MOTIONCARE_ANALYSIS_ROOT:-/opt/motioncare-analysis}"
service_user="motioncare-analysis"
swap_path="/swapfile"

if [[ "${analysis_root}" != "/opt/motioncare-analysis" ]]; then
  echo "本次冒烟只允许 /opt/motioncare-analysis" >&2
  exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  ca-certificates ffmpeg python3 python3-venv python3-pip

if ! id "${service_user}" >/dev/null 2>&1; then
  useradd --system \
    --home-dir "${analysis_root}" \
    --create-home \
    --shell /usr/sbin/nologin \
    "${service_user}"
fi

install -d -m 0750 -o root -g "${service_user}" "${analysis_root}"
install -d -m 0750 -o root -g "${service_user}" "${analysis_root}/app"
install -d -m 0700 -o "${service_user}" -g "${service_user}" \
  "${analysis_root}/model-cache" \
  "${analysis_root}/input" \
  "${analysis_root}/tmp" \
  "${analysis_root}/reports" \
  "${analysis_root}/logs"

if [[ ! -e "${swap_path}" ]]; then
  fallocate -l 4G "${swap_path}"
  chmod 0600 "${swap_path}"
  mkswap "${swap_path}"
fi
if [[ "$(stat -c '%s' "${swap_path}")" -ne 4294967296 ]]; then
  echo "/swapfile 已存在但不是 4 GiB，停止以避免覆盖" >&2
  exit 1
fi
if ! swapon --show=NAME --noheadings --raw | grep -Fxq "${swap_path}"; then
  swapon "${swap_path}"
fi
if ! grep -Eq '^/swapfile[[:space:]]+none[[:space:]]+swap[[:space:]]+sw' /etc/fstab; then
  printf '%s\n' '/swapfile none swap sw 0 0' >> /etc/fstab
fi

if [[ ! -e "${analysis_root}/venv" ]]; then
  install -d -m 0700 -o "${service_user}" -g "${service_user}" \
    "${analysis_root}/venv"
fi
if [[ ! -x "${analysis_root}/venv/bin/python" ]]; then
  runuser -u "${service_user}" -- python3 -m venv "${analysis_root}/venv"
fi

test "$(stat -c '%a' "${analysis_root}/input")" = "700"
test "$(stat -c '%a' "${swap_path}")" = "600"
swapon --show "${swap_path}"
```

脚本不得关闭或重写 SSH 配置；SSH 已在前序步骤完成加固，本任务只读验证。

- [x] **Step 6: 写带 shell 清理兜底的前台运行脚本**

创建 `deploy/motion-analysis-smoke/run-benchmark.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail
umask 077

if [[ "${EUID}" -ne 0 ]]; then
  echo "必须以 root 执行" >&2
  exit 1
fi
if [[ "$#" -ne 2 ]]; then
  echo "用法: $0 COMMIT RUN_ID" >&2
  exit 2
fi

implementation_commit="$1"
run_id="$2"
analysis_root="/opt/motioncare-analysis"
video_path="${analysis_root}/input/IMG_0383_SDR_5min.mp4"
report_path="${analysis_root}/reports/pp-tinypose-smoke-${run_id}.json"
summary_path="${analysis_root}/reports/pp-tinypose-smoke-${run_id}.txt"

if [[ ! "${implementation_commit}" =~ ^[a-f0-9]{7,40}$ ]]; then
  echo "COMMIT 格式无效" >&2
  exit 2
fi
if [[ ! "${run_id}" =~ ^[0-9]{8}T[0-9]{6}Z$ ]]; then
  echo "RUN_ID 格式无效" >&2
  exit 2
fi
if [[ ! -f "${video_path}" || -L "${video_path}" ]]; then
  echo "输入视频不存在或不是普通文件" >&2
  exit 1
fi

cleanup_input() {
  if [[ -e "${video_path}" && ! -L "${video_path}" ]]; then
    unlink "${video_path}"
  fi
}
trap cleanup_input EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP

runuser -u motioncare-analysis -- env \
  PADDLE_PDX_CACHE_HOME="${analysis_root}/model-cache" \
  TMPDIR="${analysis_root}/tmp" \
  "${analysis_root}/venv/bin/python" \
  "${analysis_root}/app/backend/manage.py" \
  run_pose_smoke_benchmark \
  --video "${video_path}" \
  --report "${report_path}" \
  --summary "${summary_path}" \
  --expected-sha256 f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd \
  --git-commit "${implementation_commit}" \
  --delete-input

printf '%s\n' "${report_path}" "${summary_path}"
```

该脚本本身不进入后台、不使用 `nohup`、不启动第二份推理进程；Python 的 `finally` 与 shell 的 `EXIT` trap 形成两层输入清理。

- [x] **Step 7: 运行命令测试、依赖解析检查与 Shell 语法检查**

Run:

```bash
cd backend
pytest apps/training/tests/test_pose_benchmark_command.py -q
python -m pip install --dry-run ".[motion-analysis]"
cd ..
chmod 0755 \
  deploy/motion-analysis-smoke/bootstrap.sh \
  deploy/motion-analysis-smoke/run-benchmark.sh
bash -n deploy/motion-analysis-smoke/bootstrap.sh
bash -n deploy/motion-analysis-smoke/run-benchmark.sh
```

Expected: pytest PASS；dry-run 显示固定 `paddlepaddle==3.3.0`、`paddlex==3.7.2`；两个 `bash -n` 均退出 0。

- [x] **Step 8: 提交 Task 4**

```bash
git add \
  backend/apps/training/management/__init__.py \
  backend/apps/training/management/commands/__init__.py \
  backend/apps/training/management/commands/run_pose_smoke_benchmark.py \
  backend/apps/training/tests/test_pose_benchmark_command.py \
  backend/pyproject.toml \
  deploy/motion-analysis-smoke/bootstrap.sh \
  deploy/motion-analysis-smoke/run-benchmark.sh
git commit -m "feat(部署): 增加PP-TinyPose冒烟命令与初始化脚本"
```

---

### Task 5: 完成本地全量验证并生成干净部署包

**Files:**
- Verify only: Task 1–4 的全部文件
- Runtime artifact: `/tmp/motioncare-analysis-${implementation_commit}.tar.gz`

**Interfaces:**
- Consumes: 已提交的 Task 1–4 实现。
- Produces: 只由 Git 已提交内容生成的部署包和对应 7–40 位 commit 标识。

- [x] **Step 1: 跑动作分析专项测试**

Run:

```bash
cd backend
pytest \
  apps/training/tests/test_pose_inference.py \
  apps/training/tests/test_pose_benchmark_resources.py \
  apps/training/tests/test_pose_benchmark.py \
  apps/training/tests/test_pose_benchmark_command.py \
  apps/training/tests/test_motion_analysis.py \
  -q
```

Expected: 全部 PASS。

- [x] **Step 2: 跑项目要求的后端与前端全量验证**

Run:

```bash
cd backend
pytest -q
ruff check .
cd ../frontend
npm run test
npm run lint
npm run build
```

Expected: 后端测试、Ruff、前端测试、lint 和构建全部通过。

- [x] **Step 3: 检查提交范围与工作区隔离**

Run:

```bash
git status --short
git diff --check HEAD~4..HEAD
git log --oneline -5
```

Expected: 只保留实施前已经存在的其他会话未提交文件；Task 1–4 文件无未提交漂移，最近四个实施提交分别对应推理、资源、报告编排、命令/部署脚本。

- [x] **Step 4: 从 Git 提交而不是脏工作区生成部署包**

Run:

```bash
implementation_commit="$(git rev-parse --short=12 HEAD)"
archive_path="/tmp/motioncare-analysis-${implementation_commit}.tar.gz"
git archive --format=tar.gz --output="${archive_path}" HEAD backend deploy/motion-analysis-smoke
sha256sum "${archive_path}" 2>/dev/null || shasum -a 256 "${archive_path}"
printf '%s\n' "${implementation_commit}" "${archive_path}"
```

Expected: 压缩包只包含 `backend/` 与 `deploy/motion-analysis-smoke/`；记录输出的 commit 和压缩包 SHA-256，后续命令逐字复用。

---

### Task 6: 初始化算法服务器并验证安全边界

**Files:**
- Deploy: `deploy/motion-analysis-smoke/bootstrap.sh`
- Remote create: `/opt/motioncare-analysis/{app,venv,model-cache,input,tmp,reports,logs}`
- Remote create: `/swapfile`

**Interfaces:**
- Consumes: SSH 别名 `mcare-pp` 和 Task 5 部署包。
- Produces: 可运行 Python 3.12 虚拟环境、4 GiB 已启用 Swap、专用 `motioncare-analysis` 用户和受限目录。

- [x] **Step 1: 再次只读验证主机身份、系统和 SSH 策略**

Run locally:

```bash
ssh -o BatchMode=yes -o PasswordAuthentication=no mcare-pp \
  'hostnamectl; uname -m; python3 --version; free -h; df -h /; sshd -T | grep -E "^(pubkeyauthentication|passwordauthentication|kbdinteractiveauthentication|permitrootlogin) "'
```

Expected: Ubuntu 24.04、`x86_64`、Python 3.12；`pubkeyauthentication yes`、`passwordauthentication no`、`kbdinteractiveauthentication no`、root 仅密钥方式；根分区剩余空间大于 10 GiB。

- [x] **Step 2: 上传并执行初始化脚本**

Run locally:

```bash
scp deploy/motion-analysis-smoke/bootstrap.sh mcare-pp:/tmp/motioncare-analysis-bootstrap.sh
ssh mcare-pp \
  'chmod 0700 /tmp/motioncare-analysis-bootstrap.sh && /tmp/motioncare-analysis-bootstrap.sh && unlink /tmp/motioncare-analysis-bootstrap.sh'
```

Expected: 脚本退出 0，不修改 SSH 配置。

- [x] **Step 3: 验证用户、目录、Swap 和磁盘余量**

Run locally:

```bash
ssh mcare-pp \
  'id motioncare-analysis; swapon --show; free -h; stat -c "%U %G %a %n" /opt/motioncare-analysis /opt/motioncare-analysis/input /opt/motioncare-analysis/reports /swapfile; df -BG --output=avail / | tail -1'
```

Expected: `motioncare-analysis` 是系统用户；`/swapfile` 大小约 4 GiB、权限 600 且已启用；input/reports 为专用用户 700；根分区可用空间仍大于 10 GiB。

---

### Task 7: 部署代码和固定依赖，完成模型冷/热加载检查

**Files:**
- Deploy archive: Task 5 `/tmp/motioncare-analysis-${implementation_commit}.tar.gz`
- Remote code: `/opt/motioncare-analysis/app/backend`
- Remote virtualenv: `/opt/motioncare-analysis/venv`
- Remote model cache: `/opt/motioncare-analysis/model-cache`

**Interfaces:**
- Consumes: Task 5 的 `implementation_commit` 与 `archive_path`。
- Produces: 能以专用用户运行的固定版本 Paddle CPU 环境和已缓存模型。

- [x] **Step 1: 上传部署包并验证本地/远端 SHA-256 一致**

Run locally from the repository root；该值必须直接从当前已验证的提交计算：

```bash
implementation_commit="$(git rev-parse --short=12 HEAD)"
archive_path="/tmp/motioncare-analysis-${implementation_commit}.tar.gz"
test -f "${archive_path}"
scp "${archive_path}" mcare-pp:/tmp/motioncare-analysis.tar.gz
ssh mcare-pp 'sha256sum /tmp/motioncare-analysis.tar.gz'
```

Expected: 远端哈希与 Task 5 完全一致；commit 来自当前 HEAD，不手工填写。

- [x] **Step 2: 仅在远端 app 目录为空时解包并锁定代码权限**

Run locally:

```bash
ssh mcare-pp \
  'test -z "$(find /opt/motioncare-analysis/app -mindepth 1 -maxdepth 1 -print -quit)" && tar -xzf /tmp/motioncare-analysis.tar.gz -C /opt/motioncare-analysis/app && chown -R root:motioncare-analysis /opt/motioncare-analysis/app && chmod -R u=rwX,g=rX,o= /opt/motioncare-analysis/app && unlink /tmp/motioncare-analysis.tar.gz'
```

Expected: `/opt/motioncare-analysis/app/backend/manage.py` 存在，代码不可由服务用户修改。若 app 非空则停止，不覆盖原内容，由用户决定是否保留旧版本。

- [x] **Step 3: 以专用用户安装固定 Python 依赖**

Run locally:

```bash
ssh mcare-pp \
  'runuser -u motioncare-analysis -- env PIP_CACHE_DIR=/opt/motioncare-analysis/tmp/pip-cache TMPDIR=/opt/motioncare-analysis/tmp /opt/motioncare-analysis/venv/bin/python -m pip install --upgrade pip && runuser -u motioncare-analysis -- env PIP_CACHE_DIR=/opt/motioncare-analysis/tmp/pip-cache TMPDIR=/opt/motioncare-analysis/tmp /opt/motioncare-analysis/venv/bin/python -m pip install "/opt/motioncare-analysis/app/backend[motion-analysis]"'
```

Expected: 安装退出 0；不使用系统 Python site-packages。

- [x] **Step 4: 验证版本、Paddle 自检和显式 CPU 模型首次下载**

Run locally:

```bash
ssh mcare-pp \
  'runuser -u motioncare-analysis -- env PADDLE_PDX_CACHE_HOME=/opt/motioncare-analysis/model-cache /opt/motioncare-analysis/venv/bin/python -c "import importlib.metadata as m; import paddle; from apps.training.pose_inference import create_pose_model; print(m.version(\"paddlepaddle\"), m.version(\"paddlex\"), m.version(\"opencv-python-headless\")); paddle.utils.run_check(); create_pose_model(); print(\"MODEL_LOAD_OK\")" && du -sb /opt/motioncare-analysis/model-cache'
```

Expected: 版本分别为 3.3.0、3.7.2、4.10–<5；Paddle 检查成功；输出 `MODEL_LOAD_OK`；模型文件落入 `/opt/motioncare-analysis/model-cache`。`PADDLE_PDX_CACHE_HOME` 必须在 Python 导入 PaddleX 前由进程环境设置。

- [x] **Step 5: 再次加载模型以确认持久缓存可复用**

Run locally:

```bash
ssh mcare-pp \
  'runuser -u motioncare-analysis -- env PADDLE_PDX_CACHE_HOME=/opt/motioncare-analysis/model-cache /opt/motioncare-analysis/venv/bin/python -c "import importlib.metadata as m; import paddle; from apps.training.pose_inference import create_pose_model; print(m.version(\"paddlepaddle\"), m.version(\"paddlex\"), m.version(\"opencv-python-headless\")); paddle.utils.run_check(); create_pose_model(); print(\"MODEL_LOAD_OK\")" && du -sb /opt/motioncare-analysis/model-cache'
```

Expected: 再次输出 `MODEL_LOAD_OK`，两次 `du -sb` 结果不出现一次完整模型的重复增长。

---

### Task 8: 上传固定视频并执行 5 FPS、10 FPS、全帧对照

**Files:**
- Local input: `/Users/nick/my_dev/ai/agents/IMG_0383_SDR_5min.mp4`
- Remote temporary input: `/opt/motioncare-analysis/input/IMG_0383_SDR_5min.mp4`
- Remote output: `/opt/motioncare-analysis/reports/pp-tinypose-smoke-${run_id}.json`
- Remote output: `/opt/motioncare-analysis/reports/pp-tinypose-smoke-${run_id}.txt`

**Interfaces:**
- Consumes: Task 7 固定环境与 Task 5 `implementation_commit`。
- Produces: 三模式脱敏 JSON/文本报告；命令始终尝试删除输入视频。

- [x] **Step 1: 上传前重新核验本地视频**

Run locally:

```bash
video_path="/Users/nick/my_dev/ai/agents/IMG_0383_SDR_5min.mp4"
expected_sha256="f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd"
test "$(shasum -a 256 "${video_path}" | awk '{print $1}')" = "${expected_sha256}"
stat -f '%z bytes' "${video_path}"
```

Expected: 哈希完全匹配，大小为 `384318737 bytes`；不匹配时停止，不上传。

- [x] **Step 2: 检查服务器空间并上传视频**

Run locally:

```bash
ssh mcare-pp 'test "$(df -BG --output=avail / | tail -1 | tr -dc "0-9")" -ge 10'
remote_upload="/opt/motioncare-analysis/input/.IMG_0383_SDR_5min.mp4.upload"
if ! scp "${video_path}" "mcare-pp:${remote_upload}"; then
  ssh mcare-pp "test ! -e ${remote_upload} || unlink ${remote_upload}"
  exit 1
fi
ssh mcare-pp \
  'upload=/opt/motioncare-analysis/input/.IMG_0383_SDR_5min.mp4.upload; final=/opt/motioncare-analysis/input/IMG_0383_SDR_5min.mp4; actual="$(sha256sum "${upload}" | awk '\''{print $1}'\'')"; if [ "${actual}" != "f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd" ]; then unlink "${upload}"; exit 1; fi; chown motioncare-analysis:motioncare-analysis "${upload}"; chmod 0600 "${upload}"; mv "${upload}" "${final}"; stat -c "%U %G %a %s" "${final}"'
```

Expected: 远端哈希完全匹配，所有者为专用用户、权限 600、大小 384318737。

- [x] **Step 3: 通过带清理兜底的脚本串行运行三档冒烟命令**

Run locally from the repository root：

```bash
implementation_commit="$(git rev-parse --short=12 HEAD)"
run_id="$(date -u +%Y%m%dT%H%M%SZ)"
remote_report="/opt/motioncare-analysis/reports/pp-tinypose-smoke-${run_id}.json"
remote_summary="/opt/motioncare-analysis/reports/pp-tinypose-smoke-${run_id}.txt"
ssh mcare-pp \
  "/opt/motioncare-analysis/app/deploy/motion-analysis-smoke/run-benchmark.sh ${implementation_commit} ${run_id}"
```

Expected: 命令保持前台串行运行；5 FPS、10 FPS 先完成，全帧按资源门禁完成或明确跳过/失败；Python `finally` 和 shell `EXIT` trap 都尝试删除输入。若命令耗时较长，使用现有终端会话持续等待，不启动第二个并发任务。

- [x] **Step 4: 即使命令失败也检查报告、OOM 证据和输入清理**

Run locally，沿用同一 shell 中的 `remote_report`、`remote_summary`：

```bash
ssh mcare-pp \
  "test ! -e /opt/motioncare-analysis/input/IMG_0383_SDR_5min.mp4; test -f ${remote_report}; test -f ${remote_summary}; python3 -m json.tool ${remote_report} >/dev/null; journalctl -k --since '-6 hours' --no-pager | grep -Ei 'out of memory|killed process' || true; free -h"
```

Expected: 输入已删除，JSON 可解析；若内核发生 OOM，保留证据并停止，不重复高负载测试。

- [x] **Step 5: 下载脱敏报告到本地并复核不存在敏感字段**

Run locally:

```bash
local_report_dir="/Users/nick/my_dev/ai/agents/reports"
mkdir -p "${local_report_dir}"
scp "mcare-pp:${remote_report}" "${local_report_dir}/"
scp "mcare-pp:${remote_summary}" "${local_report_dir}/"
local_report="${local_report_dir}/$(basename "${remote_report}")"
python3 -m json.tool "${local_report}" >/dev/null
if rg -n '/Users/|/root/|\.pem|QINIU_|ssh|patient-name' "${local_report}"; then
  echo "报告包含不应出现的信息" >&2
  exit 1
fi
```

Expected: 本地 JSON 可解析，敏感信息扫描无匹配。报告与测试视频不加入 Git。

- [x] **Step 6: 验证服务器没有测试视频副本**

Run locally:

```bash
ssh mcare-pp \
  'test -z "$(find /opt/motioncare-analysis/input /opt/motioncare-analysis/tmp -type f -print -quit)"; matches="$(find /opt/motioncare-analysis -type f -size 384318737c -exec sha256sum {} \; | awk '\''$1 == "f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd"'\'')"; test -z "${matches}"'
```

Expected: input/tmp 没有文件，`/opt/motioncare-analysis` 下不存在 SHA-256 相同的测试视频副本；只保留代码、虚拟环境、模型缓存、日志和脱敏报告。

---

### Task 9: 解释对照结果并给出实例规格与采样建议

**Files:**
- Read only: 本地 `pp-tinypose-smoke-${run_id}.json`
- Read only: 本地 `pp-tinypose-smoke-${run_id}.txt`

**Interfaces:**
- Consumes: 三档运行状态、实际推理帧数、耗时、平均单帧耗时、峰值 RSS、内存/Swap、动作次数与质量标记。
- Produces: 一份用户可直接决策的结论；不改规则、不写生产配置。

- [x] **Step 1: 校验报告契约和帧数关系**

Run locally：

```bash
local_report_dir="/Users/nick/my_dev/ai/agents/reports"
local_report="$(find "${local_report_dir}" -maxdepth 1 -type f -name 'pp-tinypose-smoke-*.json' -print | sort | tail -1)"
test -n "${local_report}"
python3 - "${local_report}" <<'PY'
import json
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert report["report_format_version"] == "1.0"
modes = {item["name"]: item for item in report["modes"]}
assert modes["5fps"]["status"] == "completed"
assert modes["10fps"]["status"] == "completed"
assert abs(modes["5fps"]["inferred_frame_count"] - 1500) <= 30
assert abs(modes["10fps"]["inferred_frame_count"] - 3000) <= 60
if modes["all_frames"]["status"] == "completed":
    assert modes["all_frames"]["inferred_frame_count"] == modes["all_frames"]["decoded_frame_count"]
    assert abs(modes["all_frames"]["inferred_frame_count"] - 8929) <= 10
for mode in modes.values():
    if mode["status"] != "completed":
        continue
    result = mode["result"]
    assert result["standard_count"] + result["nonstandard_count"] == result["total_count"]
print("REPORT_CONTRACT_OK")
PY
```

Expected: 输出 `REPORT_CONTRACT_OK`；任一硬断言失败都按技术未通过报告，不用人工解释掩盖。

- [x] **Step 2: 输出三档对照表**

Run locally；若用户提供人工次数，先执行 `export MANUAL_COUNT=实际整数`，否则不设置：

```bash
python3 - "${local_report}" <<'PY'
import json
import os
import sys
from pathlib import Path

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
manual_raw = os.getenv("MANUAL_COUNT")
manual_count = None if manual_raw is None else int(manual_raw)
headers = [
    "模式", "状态", "推理帧", "推理秒", "总秒", "毫秒/帧",
    "峰值RSS MiB", "峰值Swap MiB", "总次数", "标准", "不标准", "质量标记", "人工差异",
]
print("| " + " | ".join(headers) + " |")
print("|" + "|".join(["---"] * len(headers)) + "|")
for mode in report["modes"]:
    result = mode.get("result", {})
    peak = mode.get("resource_peak", {})
    total = result.get("total_count")
    difference = "未提供" if manual_count is None or total is None else str(total - manual_count)
    values = [
        mode["label"],
        mode["status"],
        str(mode.get("inferred_frame_count", "-")),
        f"{mode.get('inference_seconds', 0):.2f}" if "inference_seconds" in mode else "-",
        f"{mode.get('total_seconds', 0):.2f}" if "total_seconds" in mode else "-",
        f"{mode.get('average_inference_ms_per_frame', 0):.2f}" if "average_inference_ms_per_frame" in mode else "-",
        f"{peak.get('process_rss_bytes', 0) / 1024**2:.1f}" if peak else "-",
        f"{peak.get('swap_used_bytes', 0) / 1024**2:.1f}" if peak else "-",
        str(total if total is not None else "-"),
        str(result.get("standard_count", "-")),
        str(result.get("nonstandard_count", "-")),
        ",".join(result.get("quality_flags", [])) or "-",
        difference,
    ]
    print("| " + " | ".join(values) + " |")
PY
```

Expected: 输出固定列的 Markdown 三档对照表；未提供人工标签时最后一列为 `未提供`。

- [x] **Step 3: 按固定规则给出容量结论**

- 5 FPS 失败或发生 OOM：当前实例不可用，建议先升级物理内存后复测。
- 5/10 FPS 完成但峰值 Swap 使用超过 1 GiB：仅证明勉强可运行，不建议正式任务使用当前 2 GiB 规格。
- 5/10 FPS 完成、Swap 峰值低于 512 MiB、系统最低可用内存大于 256 MiB：可继续作为低量单并发测试机。
- 全帧显著更慢且总次数/动作时间无实质改善：正式策略优先 5 FPS；若 10 FPS 明显改善动作边界且成本可接受，则优先 10 FPS。
- 全帧明显改善计数：不直接切换；先另行设计把连续帧去抖改为按时间语义，再用多段人工标注视频复测。

- [x] **Step 4: 报告下一阶段边界**

明确下一阶段仍需单独设计：专用 Celery `motion-analysis` 队列、生产 Redis/PostgreSQL 受保护网络、七牛私有下载、正式 Worker 守护与告警。不得在本轮冒烟通过后自动接入生产。
