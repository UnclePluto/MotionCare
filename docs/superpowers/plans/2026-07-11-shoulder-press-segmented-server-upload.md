# 肩部推举分段上传与服务端合并实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 状态：implementing
> 日期：2026-07-11
> 范围：替换肩部推举单文件七牛直传，实现 30 秒分段上传业务服务器、FFmpeg 合并、最终文件上传七牛和本地清理；完成医生端视频分析界面。
> 关联 spec：`docs/superpowers/specs/2026-07-11-shoulder-press-segmented-server-upload-design.md`
> 实施基线 commit：d2fe616
>
> 执行记录（2026-07-11, codex）：Task 1 已落地于 commits f933246、4a42ebd，规格与代码复审通过；PostgreSQL 方言验证留待 Task 8。
> 执行记录（2026-07-11, codex）：Task 2 已落地于 commits e459373、ae90f27、5067d08，三轮规格与代码复审通过；PostgreSQL 两连接测试留待 Task 8。
> 执行记录（2026-07-11, codex）：Task 3 已落地于 commits 7ad72e6、42fd576，规格与代码复审通过；真实七牛环境验证留待 Task 8。
> 执行记录（2026-07-11, codex）：Task 4 已落地于 commits a4d4cc1、9810139，规格与代码复审通过；PostgreSQL 行锁及真实 FFmpeg、七牛、Celery 联调留待 Task 8。
> 执行记录（2026-07-11, codex）：Task 5 已落地于 commits 7548a38、f8251db、75ccf78、dc7df2e，四轮规格与代码复审通过。
> 执行记录（2026-07-11, codex）：Task 6 代码已落地于 commits 37b3932、ee5313f、95df8f2，自动测试、双端构建和代码复审通过；Step 8 iOS/Android 微信真机验收未完成，Task 6 保持未完成。
> 执行记录（2026-07-11, codex）：Task 7 已落地于 commits d9b4c4b、a898113，规格与代码复审通过。
> 执行记录（2026-07-11, codex）：Task 8 本地部署配置落地于 commit 94660d5；最终审查修复落地于 commits 7956048、e30f3fe、6f2cae1、46e5a15、bc45777、5184392、f6eeeef，已完成 PostgreSQL、真实 FFmpeg、后端/小程序/医生端全量自动验证与代码复审。
> 剩余验收（2026-07-11）：真实七牛私有空间 E2E、iOS/Android 微信真机连续训练、生产 Linux/Celery 部署演练及真实 PP-TinyPose 推理尚未完成；计划保持 implementing。

**Goal:** 在保留现有医生权限、PP-TinyPose 推理和肩部推举规则层的前提下，把患者端改为可恢复的分段录像上传，并由单台业务服务器合并、上传最终视频、创建训练记录和清理临时文件。

**Architecture:** `TrainingVideo` 从七牛上传意图变为录像会话，新增 `TrainingVideoSegment` 和 `VideoAssemblyJob`。小程序持久化每个约 30 秒片段并顺序上传 Django；Celery 独立队列调用 FFmpeg，优先 `-c copy`，失败时单次 H.264/AAC 转码，随后由后端上传最终 MP4 到七牛并在事务成功后异步清理。

**Tech Stack:** Django 5、DRF、PostgreSQL、Celery/Redis、Python `subprocess`、FFmpeg/FFprobe、七牛 Python SDK 7.x、Taro 4.2、React 18、TypeScript、Vitest、Ant Design 5、TanStack Query v5。

## Global Constraints

- 仅肩部推举 `motion-resistance-shoulder-press` 使用录像链路；普通训练记录 API 必须拒绝该动作。
- 小程序每段约 30 秒，`getVideoInfo.size` 的 kB 值必须乘以 1024 后才作为字节展示；服务端以实际读取字节为准。
- 默认限制：单段 32 MB、单会话 200 MB、600 秒、120 段、临时文件 TTL 86400 秒、磁盘保留 5 GB、合并超时 1800 秒。
- 一期单机部署，Web、Celery Worker 和 Beat 共享 `/var/lib/motioncare/training-video-staging`；FFmpeg 合并独立队列并发固定为 1。
- 小程序不接收七牛 token、bucket 或上传域名；七牛 AK/SK 只存在后端。
- 七牛只保存最终 MP4，不调用 `avconcat` 或其它 DORA 媒体处理接口。
- `finalize` 成功代表分段已安全到达服务器并已排队；患者不等待 FFmpeg 或七牛上传。
- 七牛 stat 校验和训练记录事务成功后立即清理；失败数据 24 小时后过期清理。
- 所有文件路径必须由服务端生成并验证位于会话目录；禁止 shell 命令拼接、路径穿越和符号链接跟随。
- 医生端和 PP-TinyPose 只处理最终完整 MP4，不感知分段边界。
- 所有新行为先写失败测试；每个任务通过聚焦测试、Ruff/TypeScript 检查和双阶段 review 后再提交。
- 所有提交信息使用中文，且不得改写或回退 Task 1-4 已通过复审的无关实现。

---

### Task 1: 把 TrainingVideo 改造成分段录像会话

**Files:**
- Modify: `backend/apps/training/video_models.py`
- Modify: `backend/apps/training/models.py`
- Modify: `backend/config/settings.py`
- Create: `backend/apps/training/migrations/0004_segmented_training_video.py`
- Create: `backend/apps/training/tests/test_video_session_models.py`
- Create: `backend/apps/training/tests/test_video_session_migration.py`
- Modify: `backend/apps/training/tests/test_qiniu.py`

**Interfaces:**
- Consumes: 现有 `TrainingVideo`、`MotionAnalysisJob`、`TrainingRecord` 关系。
- Produces: `TrainingVideoSegment`、`VideoAssemblyJob`，以及 spec 中定义的会话、分段、合并和清理状态。

- [x] **Step 1: 写模型失败测试**

在 `test_video_session_models.py` 中创建会话、两个分段和一个合并任务，验证唯一约束和默认状态：

```python
import uuid

import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.training.models import TrainingVideo, TrainingVideoSegment, VideoAssemblyJob


@pytest.mark.django_db
def test_segmented_training_video_models(project_patient, active_prescription, prescription_action):
    video = TrainingVideo.objects.create(
        client_session_id=uuid.uuid4(),
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=prescription_action,
        training_date=timezone.localdate(),
        expected_duration_seconds=180,
        status=TrainingVideo.Status.RECORDING,
    )
    first = TrainingVideoSegment.objects.create(
        training_video=video,
        index=0,
        duration_ms=30000,
        size_bytes=1024,
        sha256="a" * 64,
        relative_path=f"{video.client_session_id.hex}/segments/000000.mp4",
        status=TrainingVideoSegment.Status.UPLOADED,
    )
    job = VideoAssemblyJob.objects.create(training_video=video)

    assert video.status == TrainingVideo.Status.RECORDING
    assert first.index == 0
    assert job.status == VideoAssemblyJob.Status.PENDING
    assert job.cleanup_status == VideoAssemblyJob.CleanupStatus.PENDING

    with pytest.raises(IntegrityError):
        TrainingVideoSegment.objects.create(
            training_video=video,
            index=0,
            duration_ms=1000,
            size_bytes=1,
            sha256="b" * 64,
            relative_path=f"{video.client_session_id.hex}/segments/duplicate.mp4",
        )
```

同步修改 `test_qiniu.py` 的模型构造，删除不再需要的 `upload_token_expires_at` 参数；新增会话字段已有兼容默认值。

- [x] **Step 2: 运行模型测试并确认失败**

Run: `cd backend && pytest apps/training/tests/test_video_session_models.py apps/training/tests/test_qiniu.py -q`

Expected: FAIL，提示 `TrainingVideoSegment` / `VideoAssemblyJob` 不存在或 `TrainingVideo` 缺少新字段。

- [x] **Step 3: 实现模型和配置**

在 `video_models.py` 中把 `TrainingVideo.Status` 替换为：

```python
class Status(models.TextChoices):
    # Task 1 兼容旧 API；Task 2 删除这两个旧状态。
    UPLOADING = "uploading", "上传中"
    UPLOADED = "uploaded", "已上传"
    RECORDING = "recording", "录制中"
    UPLOADING_SEGMENTS = "uploading_segments", "分段上传中"
    QUEUED = "queued", "等待合并"
    ASSEMBLING = "assembling", "合并中"
    UPLOADING_QINIU = "uploading_qiniu", "上传七牛中"
    ATTACHED = "attached", "已绑定"
    FAILED = "failed", "失败"
    EXPIRED = "expired", "已过期"
```

为 `TrainingVideo` 增加下列字段。Task 1 是兼容迁移：暂时保留旧 `UPLOADING` / `UPLOADED` 状态和可空的 `upload_token_expires_at`，让现有直传 API 在 Task 2 替换前仍能运行；原 `bucket`、`object_key`、`content_type`、`size_bytes`、`duration_seconds` 改为允许空值或合理默认值，直到最终视频生成：

```python
client_session_id = models.UUIDField("客户端会话 ID", default=uuid.uuid4)
training_date = models.DateField("训练日期", default=timezone.localdate)
note = models.TextField("备注", blank=True)
expected_duration_seconds = models.PositiveIntegerField("计划时长", null=True, blank=True)
actual_duration_seconds = models.PositiveIntegerField("实际时长", null=True, blank=True)
expected_segment_count = models.PositiveIntegerField("计划分段数", null=True, blank=True)
uploaded_segment_count = models.PositiveIntegerField("已上传分段数", default=0)
finalized_at = models.DateTimeField("提交完成时间", null=True, blank=True)
```

同时把最终对象字段调整为会话创建阶段可为空，并暂时保留旧 token 字段为 nullable：

```python
bucket = models.CharField("空间", max_length=120, blank=True, default="")
object_key = models.CharField("对象 Key", max_length=500, unique=True, null=True, blank=True)
content_type = models.CharField("文件类型", max_length=120, default="video/mp4")
size_bytes = models.PositiveBigIntegerField("文件大小", default=0)
duration_seconds = models.PositiveIntegerField("视频时长", default=0)
upload_token_expires_at = models.DateTimeField("上传凭证过期时间", null=True, blank=True)
```

添加条件与唯一约束：

```python
class Meta:
    constraints = [
        models.UniqueConstraint(
            fields=["project_patient", "client_session_id"],
            name="unique_training_video_client_session_per_patient",
        )
    ]
```

Task 1 保持 `TrainingVideo` 的临时默认状态为旧 `UPLOADING`；Task 2 删除旧端点时再切换到 `RECORDING`。两个新模型的完整契约如下：

```python
class TrainingVideoSegment(UserStampedModel):
    class Status(models.TextChoices):
        UPLOADING = "uploading", "上传中"
        UPLOADED = "uploaded", "已上传"
        DELETED = "deleted", "已删除"
        FAILED = "failed", "失败"

    training_video = models.ForeignKey(
        TrainingVideo,
        on_delete=models.CASCADE,
        related_name="segments",
    )
    index = models.PositiveIntegerField("分段序号")
    duration_ms = models.PositiveIntegerField("分段时长毫秒")
    size_bytes = models.PositiveBigIntegerField("分段大小")
    sha256 = models.CharField("SHA-256", max_length=64, blank=True)
    relative_path = models.CharField("临时相对路径", max_length=500, blank=True)
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.UPLOADING,
    )
    uploaded_at = models.DateTimeField("上传完成时间", null=True, blank=True)
    failure_reason = models.TextField("失败原因", blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["training_video", "index"],
                name="unique_training_video_segment_index",
            )
        ]


class VideoAssemblyJob(UserStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "待处理"
        RUNNING = "running", "处理中"
        SUCCEEDED = "succeeded", "成功"
        FAILED = "failed", "失败"

    class CleanupStatus(models.TextChoices):
        PENDING = "pending", "待清理"
        SUCCEEDED = "succeeded", "清理成功"
        FAILED = "failed", "清理失败"

    training_video = models.OneToOneField(
        TrainingVideo,
        on_delete=models.CASCADE,
        related_name="assembly_job",
    )
    status = models.CharField(
        "状态",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )
    attempt_count = models.PositiveIntegerField("尝试次数", default=0)
    output_relative_path = models.CharField("输出相对路径", max_length=500, blank=True)
    qiniu_object_key = models.CharField("七牛对象 Key", max_length=500, blank=True)
    qiniu_object_hash = models.CharField("七牛对象 Hash", max_length=120, blank=True)
    cleanup_status = models.CharField(
        "清理状态",
        max_length=20,
        choices=CleanupStatus.choices,
        default=CleanupStatus.PENDING,
    )
    cleanup_attempt_count = models.PositiveIntegerField("清理尝试次数", default=0)
    failure_reason = models.TextField("失败原因", blank=True)
    cleanup_error = models.TextField("清理失败原因", blank=True)
    started_at = models.DateTimeField("开始时间", null=True, blank=True)
    finished_at = models.DateTimeField("结束时间", null=True, blank=True)
    heartbeat_at = models.DateTimeField("心跳时间", null=True, blank=True)
```

在 `models.py` 导出：

```python
from .video_models import (  # noqa: E402,F401
    MotionAnalysisJob,
    TrainingVideo,
    TrainingVideoSegment,
    VideoAssemblyJob,
)
```

在 `settings.py` 增加：

```python
TRAINING_VIDEO_STAGING_ROOT = Path(os.getenv(
    "TRAINING_VIDEO_STAGING_ROOT",
    "/var/lib/motioncare/training-video-staging",
))
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES = int(os.getenv(
    "TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES", str(32 * 1024 * 1024)
))
TRAINING_VIDEO_MAX_SEGMENTS = int(os.getenv("TRAINING_VIDEO_MAX_SEGMENTS", "120"))
TRAINING_VIDEO_STAGING_TTL_SECONDS = int(os.getenv(
    "TRAINING_VIDEO_STAGING_TTL_SECONDS", "86400"
))
TRAINING_VIDEO_MIN_FREE_BYTES = int(os.getenv(
    "TRAINING_VIDEO_MIN_FREE_BYTES", str(5 * 1024 * 1024 * 1024)
))
VIDEO_ASSEMBLY_TIMEOUT_SECONDS = int(os.getenv("VIDEO_ASSEMBLY_TIMEOUT_SECONDS", "1800"))
VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS = int(os.getenv(
    "VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS", "3600"
))
FFMPEG_PATH = os.getenv("FFMPEG_PATH", "/usr/bin/ffmpeg")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", "/usr/bin/ffprobe")
```

保留现有 `TRAINING_VIDEO_MAX_SIZE_BYTES=200 MB` 和 `TRAINING_VIDEO_MAX_DURATION_SECONDS=600`。

- [x] **Step 4: 生成并审查迁移**

Run: `cd backend && python manage.py makemigrations training --name segmented_training_video`

Expected: 生成 `0004_segmented_training_video.py`，只添加兼容字段、放宽最终对象字段并创建两个新模型；不得在本迁移删除旧上传字段，也不得修改历史 migration。

手工修正生成迁移中 `client_session_id` 的历史数据处理顺序：先以 `null=True` 且无 default 添加字段；再用 `RunPython` 遍历每条历史 `TrainingVideo` 并分别写入 `uuid.uuid4()`；随后 AlterField 为模型最终的非空 `UUIDField(default=uuid.uuid4)`；最后才添加 `(project_patient, client_session_id)` 唯一约束。禁止通过一次数据库默认值回填所有旧行。

在 `test_video_session_migration.py` 使用 `MigrationExecutor` 迁移到 `0003`，为同一 `ProjectPatient` 建立两条历史视频，再迁移到 `0004`，断言两个 `client_session_id` 均非空且互不相同。该测试是 PostgreSQL/SQLite 都必须通过的数据迁移回归测试。

Run: `cd backend && python manage.py makemigrations --check`

Expected: 输出 `No changes detected`。

- [x] **Step 5: 运行聚焦测试和 Ruff**

Run: `cd backend && pytest apps/training/tests/test_video_session_models.py apps/training/tests/test_video_session_migration.py apps/training/tests/test_qiniu.py -q && ruff check apps/training/video_models.py apps/training/tests/test_video_session_models.py apps/training/tests/test_video_session_migration.py config/settings.py`

Expected: PASS，Ruff 无报错。

- [x] **Step 6: 提交**

```bash
git add backend/apps/training/video_models.py backend/apps/training/models.py backend/apps/training/migrations/0004_segmented_training_video.py backend/apps/training/tests/test_video_session_models.py backend/apps/training/tests/test_video_session_migration.py backend/apps/training/tests/test_qiniu.py backend/config/settings.py
git commit -m "feat(training): 建立分段录像会话模型"
```

---

### Task 2: 实现会话创建、分段落盘和状态 API

**Files:**
- Create: `backend/apps/training/video_staging.py`
- Modify: `backend/apps/training/video_services.py`
- Modify: `backend/apps/patient_app/serializers.py`
- Modify: `backend/apps/patient_app/views.py`
- Modify: `backend/apps/patient_app/urls.py`
- Create: `backend/apps/training/migrations/0005_remove_direct_video_upload.py`
- Replace tests in: `backend/apps/patient_app/tests/test_patient_app_video_api.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `backend/apps/training/tests/test_motion_analysis.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`
- Modify: `backend/apps/training/tests/test_training_video_api.py`

**Interfaces:**
- Consumes: Task 1 模型和 staging 配置。
- Produces:
  - `create_training_video_session(*, project_patient, client_session_id, prescription_action_id, training_date, expected_duration_seconds) -> tuple[TrainingVideo, bool]`
  - `store_training_video_segment(*, project_patient, video_id, index, uploaded_file, duration_ms, declared_size_bytes) -> tuple[TrainingVideoSegment, bool]`
  - `training_video_session_status(*, project_patient, video_id) -> dict`
  - `SessionConflict` / `SegmentConflict`，均由 API 映射为 HTTP 409。

- [x] **Step 1: 写会话与分段 API 失败测试**

把旧 `upload-intent` / `complete` 测试替换为新端点测试：

```python
@pytest.mark.django_db
def test_create_session_is_idempotent(project_patient, doctor, active_prescription):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    payload = {
        "client_session_id": "8cf99c30-9b03-4bda-b4d3-b492f3a2db12",
        "prescription_action": action.id,
        "training_date": "2026-07-11",
        "expected_duration_seconds": 180,
    }
    first = client.post("/api/patient-app/training-video-sessions/", payload, format="json")
    second = client.post("/api/patient-app/training-video-sessions/", payload, format="json")

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.data["video_id"] == second.data["video_id"]
    assert second.data["uploaded_segments"] == []


@pytest.mark.django_db
def test_upload_segment_streams_to_server_and_is_idempotent(
    project_patient, doctor, active_prescription, settings, tmp_path
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = client.post(
        "/api/patient-app/training-video-sessions/",
        {
            "client_session_id": "8cf99c30-9b03-4bda-b4d3-b492f3a2db12",
            "prescription_action": action.id,
            "training_date": "2026-07-11",
            "expected_duration_seconds": 180,
        },
        format="json",
    )
    file = SimpleUploadedFile("segment.mp4", b"video-bytes", content_type="video/mp4")
    url = f"/api/patient-app/training-video-sessions/{session.data['video_id']}/segments/0/"

    first = client.post(url, {"file": file, "duration_ms": 30000, "size_bytes": 11})
    second = client.post(
        url,
        {"file": SimpleUploadedFile("again.mp4", b"video-bytes", content_type="video/mp4"), "duration_ms": 30000, "size_bytes": 11},
    )

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.data["sha256"] == second.data["sha256"]
    assert (tmp_path / "8cf99c309b034bdab4d3b492f3a2db12" / "segments" / "000000.mp4").read_bytes() == b"video-bytes"
```

再增加：相同会话 UUID 不同 action/date/duration 返回 409；恢复既有会话不受后来磁盘低水位、FFmpeg 不可用或处方更新影响；分段元数据冲突返回 409、跨患者返回 404、单段/总量超限不残留 `.part`、状态接口返回真实已上传索引、旧直传端点返回 404。

增加文件锁并发回归：两个线程竞争同一 session/index 时，失败请求必须在持有安装锁期间清理自己的最终文件，成功请求随后安装的文件不能被删除。另写仅 PostgreSQL 执行的 `TransactionTestCase`，使用两个数据库连接验证 `select_for_update` 串行化；SQLite 环境明确 skip，并在 Task 8 的 PostgreSQL 验证中强制运行。

在 `test_patient_app_api.py` 增加普通训练记录绕过测试：肩部推举提交 `/training-records/` 返回 400，其它动作行为不变。

- [x] **Step 2: 运行 API 测试并确认失败**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_video_api.py apps/patient_app/tests/test_patient_app_api.py -q`

Expected: FAIL，新端点 404，旧普通训练记录接口仍允许肩部推举。

- [x] **Step 3: 实现安全落盘模块**

在 `video_staging.py` 定义：

```python
class SegmentConflict(Exception):
    pass


class SessionConflict(Exception):
    pass


def session_root(video: TrainingVideo) -> Path:
    root = Path(settings.TRAINING_VIDEO_STAGING_ROOT).resolve()
    candidate = (root / f"{video.pk}-{video.client_session_id.hex}").resolve()
    if not candidate.is_relative_to(root):
        raise ValidationError("训练视频临时目录无效")
    return candidate


def segment_path(video: TrainingVideo, index: int) -> Path:
    return session_root(video) / "segments" / f"{index:06d}.mp4"


def write_uploaded_segment(video, index, uploaded_file) -> tuple[Path, int, str]:
    destination = segment_path(video, index)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(f".mp4.{uuid.uuid4().hex}.part")
    digest = hashlib.sha256()
    written = 0
    try:
        with temporary.open("xb") as output:
            for chunk in uploaded_file.chunks():
                written += len(chunk)
                if written > settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES:
                    raise ValidationError("训练视频分段过大")
                digest.update(chunk)
                output.write(chunk)
        return temporary, written, digest.hexdigest()
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
```

新增 `segment_install_lock(video, index)` context manager：在包含后端全局 `video.pk` 的会话目录 `locks/{index:06d}.lock` 上使用 `fcntl.flock(LOCK_EX)`。锁必须从进入数据库 `transaction.atomic()` 前一直持有到事务成功返回，或事务失败后的 `destination.unlink()` 完成；禁止释放锁后再按公共目标路径清理。

SQLite 可运行测试分成两个短用例：第一项用两个线程直接调用真实 `segment_install_lock` 证明第二线程在第一线程释放前无法进入；第二项调用真实 `store_training_video_segment`，只注入数据库 create 失败和一个可观察锁 wrapper，断言 `destination.unlink()` 执行时 wrapper 仍处于 active。不要在测试中手工复制生产安装/清理算法。PostgreSQL-only 测试继续调用真实服务覆盖完整两连接竞态。

最终 `os.replace` 必须在锁定会话、完成总量和重复检查后执行；数据库保存失败时删除刚生成的最终分段文件。

- [x] **Step 4: 实现服务、序列化器、视图和路由**

在 `video_services.py` 删除 `create_upload_intent`、`complete_training_video` 及七牛直传 token 依赖，实现 Task 接口。创建会话先按 `(project_patient, client_session_id)` 查找既有记录：action、training_date、expected_duration 完全一致时直接恢复，不再检查当前处方、FFmpeg 或磁盘；任一不可变参数冲突时抛 `SessionConflict`。只有确实新建时才调用 `_get_current_shoulder_action` 和环境检查；并发创建落败方捕获唯一约束后必须读取胜出记录并执行同一等价性检查。

存片段时先写独立 `.part`，再获取 `segment_install_lock`，随后锁定 `TrainingVideo`，只允许 `recording` / `uploading_segments`，按数据库真实分段汇总总大小和总时长。`os.replace`、数据库事务退出和失败后的最终文件清理全部位于文件锁作用域内。

创建 `0005_remove_direct_video_upload.py`：先用 `RunPython` 把历史 `uploading` / `uploaded` 视频标为 `failed` 并写入“旧直传会话已停止，请重新训练”，保留 `attached` 视频；随后删除 `upload_token_expires_at`，移除旧状态选项并把默认状态改为 `recording`。同步删除 `QINIU_UPLOAD_HOST` 和 `QINIU_UPLOAD_TOKEN_TTL_SECONDS` 设置。

机械更新 `test_motion_analysis.py`、`test_tracking_api.py`、`test_training_video_api.py`：删除所有 `upload_token_expires_at` 构造参数；原“非 attached 视频禁止下载”用例把旧 `UPLOADING` 改为 `RECORDING`。不得改动 attached 视频、分析结果或权限断言。

序列化器字段：

```python
class PatientAppTrainingVideoSessionSerializer(serializers.Serializer):
    client_session_id = serializers.UUIDField()
    prescription_action = serializers.IntegerField(min_value=1)
    training_date = serializers.DateField()
    expected_duration_seconds = serializers.IntegerField(min_value=1)


class PatientAppTrainingVideoSegmentSerializer(serializers.Serializer):
    file = serializers.FileField()
    duration_ms = serializers.IntegerField(min_value=1)
    size_bytes = serializers.IntegerField(min_value=1)
```

路由必须精确为：

```python
path("training-video-sessions/", PatientAppTrainingVideoSessionView.as_view()),
path("training-video-sessions/<int:video_id>/segments/<int:index>/", PatientAppTrainingVideoSegmentView.as_view()),
path("training-video-sessions/<int:video_id>/status/", PatientAppTrainingVideoStatusView.as_view()),
```

删除旧 `training-videos/upload-intent/` 和 `training-videos/<id>/complete/` 路由。`PatientAppTrainingRecordView` 在创建记录前检查 `source_key`，肩部推举返回“肩部推举必须完成录像上传”。

- [x] **Step 5: 运行聚焦测试和 Ruff**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_video_api.py apps/patient_app/tests/test_patient_app_api.py apps/training/tests/test_motion_analysis.py apps/training/tests/test_tracking_api.py apps/training/tests/test_training_video_api.py -q && ruff check apps/training/video_staging.py apps/training/video_services.py apps/patient_app apps/training/tests`

Expected: PASS，Ruff 无报错。

- [x] **Step 6: 提交**

```bash
git add backend/apps/training/video_staging.py backend/apps/training/video_services.py backend/apps/training/migrations/0005_remove_direct_video_upload.py backend/apps/patient_app/serializers.py backend/apps/patient_app/views.py backend/apps/patient_app/urls.py backend/apps/patient_app/tests/test_patient_app_video_api.py backend/apps/patient_app/tests/test_patient_app_api.py backend/apps/training/tests/test_motion_analysis.py backend/apps/training/tests/test_tracking_api.py backend/apps/training/tests/test_training_video_api.py backend/config/settings.py
git commit -m "feat(patient-app): 支持训练视频分段上传"
```

---

### Task 3: 实现 FFmpeg 合并和服务端七牛上传

**Files:**
- Create: `backend/apps/training/video_assembly.py`
- Modify: `backend/apps/training/qiniu.py`
- Create: `backend/apps/training/tests/test_video_assembly.py`
- Modify: `backend/apps/training/tests/test_qiniu.py`

**Interfaces:**
- Consumes: Task 1/2 的分段文件和七牛配置。
- Produces:
  - `probe_video(path: Path, *, ffprobe_path: str, timeout: int) -> VideoProbe`
  - `assemble_video(segment_paths: list[Path], output_path: Path, *, ffmpeg_path: str, ffprobe_path: str, timeout: int) -> AssemblyResult`
  - `upload_local_video(*, path: Path, bucket: str, key: str) -> dict`

- [x] **Step 1: 写 FFmpeg 命令和真实集成失败测试**

在 `test_video_assembly.py` 使用注入 runner 验证先 copy、后单次转码：

```python
def test_assemble_video_falls_back_to_one_transcode(tmp_path, monkeypatch):
    calls = []

    def runner(command, **kwargs):
        calls.append(command)
        if "copy" in command:
            raise subprocess.CalledProcessError(1, command, stderr="bad timestamps")
        Path(command[-1]).write_bytes(b"merged")
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(video_assembly, "probe_video", lambda *args, **kwargs: VideoProbe(
        duration_seconds=1.0,
        width=640,
        height=480,
        video_codec="h264",
        audio_codec="aac",
    ))
    result = assemble_video(
        [tmp_path / "000000.mp4", tmp_path / "000001.mp4"],
        tmp_path / "final.mp4",
        ffmpeg_path="ffmpeg",
        ffprobe_path="ffprobe",
        timeout=30,
        runner=runner,
    )

    assert result.transcoded is True
    assert sum("libx264" in call for call in calls) == 1
```

增加 `@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg required")` 集成测试：生成 23 个 0.1 秒 H.264/AAC 小片段，调用真实 `assemble_video`，再用 `ffprobe` 断言输出可读、包含视频流且时长大于 2 秒。

- [x] **Step 2: 写服务端七牛上传失败测试**

Mock `qiniu.put_file` 和 `BucketManager.stat`：上传返回 200 后必须再 stat；目标对象已存在且匹配时不重复 `put_file`；已存在但 hash/大小冲突时抛 `ValidationError`。

- [x] **Step 3: 运行测试并确认失败**

Run: `cd backend && pytest apps/training/tests/test_video_assembly.py apps/training/tests/test_qiniu.py -q`

Expected: FAIL，模块和 `upload_local_video` 尚不存在。

- [x] **Step 4: 实现视频预检与两阶段合并**

`video_assembly.py` 使用 dataclass 固定返回类型：

```python
@dataclass(frozen=True)
class VideoProbe:
    duration_seconds: float
    width: int
    height: int
    video_codec: str
    audio_codec: str | None


@dataclass(frozen=True)
class AssemblyResult:
    output_path: Path
    probe: VideoProbe
    size_bytes: int
    transcoded: bool
```

`probe_video` 运行 `ffprobe -v error -show_streams -show_format -of json` 并结构化解析 JSON。`assemble_video` 必须：

1. 验证输入非空、路径存在且均为普通文件。
2. 在 output 同目录生成只含服务端路径的 `concat.txt`。
3. 首次运行 `-f concat -safe 0 -c copy -movflags +faststart`。
4. copy 命令失败或输出探测失败时删除临时输出，只运行一次 `libx264/yuv420p/aac` 转码命令。
5. 校验输出时长与输入总时长误差不超过 `max(2.0, total * 0.02)`。
6. 将 `final.tmp.mp4` 原子替换为调用方指定的 `final.mp4`。

所有 `subprocess.run` 使用 `check=True`、`capture_output=True`、`text=True`、`timeout=timeout`，错误信息通过统一截断函数处理。

- [x] **Step 5: 实现七牛最终文件上传**

在 `qiniu.py` 删除已无调用方的 `generate_upload_token`，保留下载签名和 stat。实现：

```python
def upload_local_video(*, path: Path, bucket: str, key: str) -> dict:
    local_size = path.stat().st_size
    local_etag = qiniu.etag(str(path))
    existing = stat_object_metadata_or_none(bucket=bucket, key=key)
    if existing is not None:
        if existing.get("fsize") != local_size or existing.get("hash") != local_etag:
            raise ValidationError("七牛目标对象与本地视频冲突")
        return existing

    auth = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY)
    token = auth.upload_token(bucket, key, 3600)
    result, response = put_file(
        token,
        key,
        str(path),
        check_crc=True,
        mime_type="video/mp4",
    )
    if getattr(response, "status_code", None) != 200 or not isinstance(result, dict):
        raise ValidationError("训练视频上传七牛失败")
    if result.get("key") != key or result.get("hash") != local_etag:
        raise ValidationError("七牛训练视频上传结果不匹配")
    metadata = stat_object_metadata(bucket=bucket, key=key)
    validate_object_metadata(
        metadata,
        expected_hash=local_etag,
        expected_size_bytes=local_size,
        expected_content_type="video/mp4",
    )
    return metadata
```

`stat_object_metadata_or_none` 只把七牛明确的“对象不存在”返回为 `None`；网络、鉴权和服务错误仍抛异常，不能误判为可覆盖。

- [x] **Step 6: 运行聚焦测试和 Ruff**

Run: `cd backend && pytest apps/training/tests/test_video_assembly.py apps/training/tests/test_qiniu.py -q && ruff check apps/training/video_assembly.py apps/training/qiniu.py`

Expected: PASS；安装了 FFmpeg 时真实 23 段测试也 PASS。

- [x] **Step 7: 提交**

```bash
git add backend/apps/training/video_assembly.py backend/apps/training/qiniu.py backend/apps/training/tests/test_video_assembly.py backend/apps/training/tests/test_qiniu.py
git commit -m "feat(training): 支持服务端合并并上传最终视频"
```

---

### Task 4: 编排 finalize、训练记录、重试与清理

**Files:**
- Create: `backend/apps/training/video_tasks.py`
- Modify: `backend/apps/training/tasks.py`
- Modify: `backend/apps/training/video_services.py`
- Modify: `backend/apps/patient_app/serializers.py`
- Modify: `backend/apps/patient_app/views.py`
- Modify: `backend/apps/patient_app/urls.py`
- Modify: `backend/config/settings.py`
- Create: `backend/apps/training/tests/test_video_tasks.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_video_api.py`

**Interfaces:**
- Consumes: `assemble_video`、`upload_local_video`、Task 1 模型和 Task 2 staging 路径。
- Produces:
  - `finalize_training_video_session(*, project_patient, video_id: int, segment_count: int, actual_duration_seconds: int, note: str) -> tuple[TrainingVideo, VideoAssemblyJob, bool]`
  - `run_video_assembly_job(job_id: int)` Celery task
  - `cleanup_training_video_files(job_id: int)` Celery task
  - `recover_stale_video_assembly_jobs()` Celery Beat task
  - `expire_stale_training_video_sessions()` Celery Beat task

- [x] **Step 1: 写 finalize 与幂等失败测试**

```python
@pytest.mark.django_db
def test_finalize_requires_contiguous_segments_and_enqueues_once(
    project_patient, doctor, active_prescription, tmp_path, settings, monkeypatch
):
    settings.TRAINING_VIDEO_STAGING_ROOT = tmp_path
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    video = TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=timezone.localdate(),
        expected_duration_seconds=60,
        status=TrainingVideo.Status.UPLOADING_SEGMENTS,
    )
    for index in range(2):
        relative = f"{video.client_session_id.hex}/segments/{index:06d}.mp4"
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"segment")
        TrainingVideoSegment.objects.create(
            training_video=video,
            index=index,
            duration_ms=30000,
            size_bytes=7,
            sha256="a" * 64,
            relative_path=relative,
            status=TrainingVideoSegment.Status.UPLOADED,
        )
    delay = Mock()
    monkeypatch.setattr("apps.training.video_tasks.run_video_assembly_job.delay", delay)
    url = f"/api/patient-app/training-video-sessions/{video.id}/finalize/"
    payload = {"segment_count": 2, "actual_duration_seconds": 60, "note": ""}

    first = client.post(url, payload, format="json")
    second = client.post(url, payload, format="json")

    assert first.status_code == 202
    assert second.status_code == 200
    assert first.data["assembly_job_id"] == second.data["assembly_job_id"]
    assert delay.call_count == 1
```

增加缺少索引、总时长不一致、超过 120 段、解绑患者和重复 payload 冲突测试。

- [x] **Step 2: 写任务成功、失败恢复和清理失败测试**

Mock `assemble_video` / `upload_local_video`，验证：

- 成功只创建一个 `TrainingRecord`，`TrainingVideo` 进入 `attached`，`cleanup_training_video_files.delay` 在 commit 后调用。
- 七牛已经存在相同对象时不重复合并或创建记录。
- 七牛失败保留 `final.mp4`，任务有限重试；最终失败保留分段。
- 清理失败只更新 `cleanup_status=failed`，不回滚记录。
- 24 小时扫描删除失败/未 finalize 文件并置 `expired`。
- 有新心跳的任务不被陈旧恢复抢占；陈旧任务回到 `pending` 并只重新入队一次。

- [x] **Step 3: 运行测试并确认失败**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_video_api.py apps/training/tests/test_video_tasks.py -q`

Expected: FAIL，finalize 路由和任务不存在。

- [x] **Step 4: 实现 finalize API**

新增序列化器：

```python
class PatientAppTrainingVideoFinalizeSerializer(serializers.Serializer):
    segment_count = serializers.IntegerField(min_value=1)
    actual_duration_seconds = serializers.IntegerField(min_value=1)
    note = serializers.CharField(required=False, allow_blank=True)
```

`finalize_training_video_session` 在事务中锁定 `ProjectPatient` 和 `TrainingVideo`，查询 `index` 有序的 uploaded 分段并断言等于 `list(range(segment_count))`。校验总时长误差 `<= max(2, actual_duration_seconds * 0.02)`，保存原始训练日期/处方，创建唯一 job，把 video 置 `queued`，只在首次创建时 `transaction.on_commit(lambda: run_video_assembly_job.delay(job.id))`。

路由：

```python
path("training-video-sessions/<int:video_id>/finalize/", PatientAppTrainingVideoFinalizeView.as_view()),
```

- [x] **Step 5: 实现任务状态机和训练记录事务**

在 `video_tasks.py` 把 IO 编排与数据库状态更新分离。核心处理函数流程固定为：

```python
def process_video_assembly_job(job_id: int) -> VideoAssemblyJob:
    job, claimed = claim_video_assembly_job(job_id)
    if not claimed:
        return job
    segments = list(job.training_video.segments.order_by("index"))
    result = load_verified_assembly_output(job)
    if result is None:
        result = assemble_video(
            [absolute_staging_path(segment.relative_path) for segment in segments],
            assembly_output_path(job.training_video),
            ffmpeg_path=settings.FFMPEG_PATH,
            ffprobe_path=settings.FFPROBE_PATH,
            timeout=settings.VIDEO_ASSEMBLY_TIMEOUT_SECONDS,
        )
    mark_uploading_qiniu(job.id, result)
    metadata = upload_local_video(
        path=result.output_path,
        bucket=settings.QINIU_BUCKET,
        key=job.qiniu_object_key,
    )
    attached = attach_training_video(job.id, result, metadata)
    cleanup_training_video_files.delay(attached.id)
    return attached
```

`attach_training_video` 必须锁 `ProjectPatient`、`TrainingVideo`、`VideoAssemblyJob`，使用会话开始时保存的 `prescription_action` 创建 `TrainingRecord(status=completed)`，时长分钟为 `max(1, ceil(actual_duration_seconds / 60))`，`form_data` 写入 `video_id` 和 `video_object_key`。重复调用返回原记录。

`load_verified_assembly_output` 仅在 job 已保存 `output_relative_path`、文件仍位于会话目录且 FFprobe 的时长/大小与 job 元数据一致时返回 `AssemblyResult`；否则返回 `None`。因此七牛上传失败后的重试直接复用最终文件，只有文件缺失或校验失败才从原始分段重新合并。

任务重试最多 3 次并指数退避；失败原因使用现有 `_safe_failure_reason` 的脱敏规则。不要把视频路径、七牛签名或完整 stderr 写入数据库。

- [x] **Step 6: 实现成功清理、过期清理和陈旧恢复**

`cleanup_training_video_files` 只清理 `attached` 会话，递归删除前逐个验证路径位于 session root 且不是符号链接。删除幂等，成功更新所有 segment 为 `deleted`。

陈旧恢复使用 `VIDEO_ASSEMBLY_STALE_TIMEOUT_SECONDS=3600`，每个 FFprobe、FFmpeg、七牛上传和数据库阶段前后更新 `heartbeat_at`。Beat 只回收 heartbeat 超过 3600 秒未更新的 running job，避免 1800 秒合法转码被重复执行。

Beat 配置增加：

```python
"recover-stale-video-assembly-jobs": {
    "task": "apps.training.video_tasks.recover_stale_video_assembly_jobs",
    "schedule": 300,
},
"expire-stale-training-video-sessions": {
    "task": "apps.training.video_tasks.expire_stale_training_video_sessions",
    "schedule": 900,
},
```

在 `tasks.py` 显式导入视频任务，确保 Celery autodiscovery 注册：

```python
from .video_tasks import (  # noqa: F401,E402
    cleanup_training_video_files,
    expire_stale_training_video_sessions,
    recover_stale_video_assembly_jobs,
    run_video_assembly_job,
)
```

- [x] **Step 7: 运行聚焦测试和 Ruff**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_video_api.py apps/training/tests/test_video_tasks.py apps/training/tests/test_training_video_api.py apps/training/tests/test_motion_analysis.py -q && ruff check apps/training/video_tasks.py apps/training/tasks.py apps/training/video_services.py apps/patient_app config/settings.py`

Expected: PASS，现有医生下载与动作分析测试不回归。

- [x] **Step 8: 提交**

```bash
git add backend/apps/training/video_tasks.py backend/apps/training/tasks.py backend/apps/training/video_services.py backend/apps/patient_app/serializers.py backend/apps/patient_app/views.py backend/apps/patient_app/urls.py backend/config/settings.py backend/apps/training/tests/test_video_tasks.py backend/apps/patient_app/tests/test_patient_app_video_api.py
git commit -m "feat(training): 编排视频合并上传与临时文件清理"
```

---

### Task 5: 重写小程序分段会话、API 和上传队列

**Files:**
- Modify: `miniapp/src/api/client.ts`
- Replace: `miniapp/src/pages/shoulder-press/api.ts`
- Replace: `miniapp/src/pages/shoulder-press/session.ts`
- Replace: `miniapp/src/pages/shoulder-press/workflow.ts`
- Create: `miniapp/src/pages/shoulder-press/recorder.ts`
- Replace tests: `miniapp/src/pages/shoulder-press/api.test.ts`
- Replace tests: `miniapp/src/pages/shoulder-press/session.test.ts`
- Replace tests: `miniapp/src/pages/shoulder-press/workflow.test.ts`
- Create: `miniapp/src/pages/shoulder-press/recorder.test.ts`

**Interfaces:**
- Consumes: Task 2/4 患者 session API。
- Produces:
  - `PendingShoulderPressSession` / `PendingShoulderPressSegment`
  - `createVideoSession`、`uploadVideoSegment`、`finalizeVideoSession`、`getVideoSessionStatus`
  - `runPendingSegmentUploads(session, deps, onProgress) -> Promise<PendingShoulderPressSession>`
  - `ShoulderPressRecorder`，负责 30 秒 timeout、手动完成和页面隐藏暂停且每个文件只交付一次。

- [x] **Step 1: 写持久化会话和 kB 换算失败测试**

```typescript
it('persists multiple saved segments and converts getVideoInfo kB to bytes', () => {
  const session = createPendingShoulderPressSession({
    actionId: 42,
    expectedDurationSeconds: 180,
    trainingDate: '2026-07-11',
    clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
    createdAt: 1783692000000
  })
  const updated = appendPendingSegment(session, {
    savedFilePath: 'wxfile://store/segment-0.mp4',
    durationSeconds: 29.8,
    sizeKb: 2048
  })

  expect(updated.segments[0]).toMatchObject({
    index: 0,
    durationMs: 29800,
    sizeBytes: 2097152,
    uploadState: 'pending'
  })
  expect(updated.trainingDate).toBe('2026-07-11')
})
```

增加损坏 segment、索引不连续、次日恢复保持 trainingDate、服务端已确认 segment 标记和本地文件删除前置条件测试。

- [x] **Step 2: 写业务服务器 API 和顺序上传失败测试**

验证 `Taro.uploadFile` 地址是 `/api/patient-app/training-video-sessions/{id}/segments/{index}/`，携带 Bearer token、`duration_ms`、字节大小；不包含七牛 token/key/bucket。工作流测试断言同一时刻只有一个 upload Promise，已上传索引跳过，失败只保留当前及后续片段。

- [x] **Step 3: 写录像控制器失败测试**

使用 fake CameraContext 验证：

- timeout 交付第 0 段后立即调用下一次 `startRecord`。
- `pause()` 保存超过 2 秒片段，低于 2 秒丢弃。
- timeout 与 `stopRecord.success` 竞争时同一路径只交付一次。
- `finish()` 停止自动续录并返回所有已交付片段。

- [x] **Step 4: 运行测试并确认失败**

Run: `cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/recorder.test.ts`

Expected: FAIL，旧类型仍为单文件七牛上传。

- [x] **Step 5: 实现授权 multipart 上传客户端**

在 `miniapp/src/api/client.ts` 导出：

```typescript
export function apiUrl(path: string): string {
  return `${API_BASE_URL}${path}`
}

export function patientAuthorizationHeader(): Record<string, string> {
  const token = getPatientAppToken()
  return token ? { Authorization: `Bearer ${token}` } : {}
}
```

`api.ts` 使用现有 JSON `request` 创建/查询/finalize，会话分段使用 `Taro.uploadFile`。统一解析非 2xx 响应，401/403 清 token 并跳绑定页，错误文本不得暴露 Authorization header。

- [x] **Step 6: 实现本地会话模型和顺序上传工作流**

本地类型固定为：

```typescript
export type PendingShoulderPressSegment = {
  index: number
  savedFilePath: string
  durationMs: number
  sizeBytes: number
  uploadState: 'pending' | 'uploading' | 'uploaded'
  sha256?: string
}

export type PendingShoulderPressSession = {
  clientSessionId: string
  videoId?: number
  actionId: number
  trainingDate: string
  expectedDurationSeconds: number
  actualDurationMs: number
  segments: PendingShoulderPressSegment[]
  finalized: boolean
  createdAt: number
  lastError?: string
}
```

生成 RFC 4122 v4 形状的 `clientSessionId` 仅用于幂等，不作为安全凭证。每次状态变化都先 `savePendingShoulderPressSession` 再继续下一步。上传成功后先持久化 `uploaded/sha256`，再调用文件删除依赖；删除失败不把 segment 改回 pending。

- [x] **Step 7: 实现录像控制器**

`recorder.ts` 不依赖 React，构造参数注入 `CameraContext`、`now()`、`onSegment(path, durationMs)` 和 `onPause()`。用递增 generation 令牌消除 timeout/stop 双回调；正常 timeout 先启动下一段，再异步交付上一段；`pause/finish` 设置模式后调用 `stopRecord`，禁止自动续录。

- [x] **Step 8: 运行聚焦测试和 TypeScript 构建**

Run: `cd miniapp && npm run test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/workflow.test.ts src/pages/shoulder-press/recorder.test.ts && npm run build:weapp`

Expected: PASS，TypeScript 无错误，构建产物不包含七牛上传 token 字段。

- [x] **Step 9: 提交**

```bash
git add miniapp/src/api/client.ts miniapp/src/pages/shoulder-press/api.ts miniapp/src/pages/shoulder-press/session.ts miniapp/src/pages/shoulder-press/workflow.ts miniapp/src/pages/shoulder-press/recorder.ts miniapp/src/pages/shoulder-press/api.test.ts miniapp/src/pages/shoulder-press/session.test.ts miniapp/src/pages/shoulder-press/workflow.test.ts miniapp/src/pages/shoulder-press/recorder.test.ts
git commit -m "feat(miniapp): 建立肩部推举分段上传队列"
```

---

### Task 6: 接入分段录像页、强制上传页和冷启动恢复

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pageState.ts`
- Modify: `miniapp/src/pages/shoulder-press/pageState.test.ts`
- Create: `miniapp/src/pages/shoulder-press/pages.test.tsx`
- Modify: `miniapp/src/app.ts`
- Modify: `miniapp/src/pages/home/index.tsx`
- Modify: `miniapp/src/pages/prescription/index.tsx`
- Modify: `miniapp/src/app.scss`

**Interfaces:**
- Consumes: Task 5 会话、Recorder 和上传工作流。
- Produces: 可真机运行的连续分段录像、训练中后台上传、强制补传/finalize 和全局待上传恢复。

- [x] **Step 1: 写页面行为失败测试**

使用 Vitest mock Taro，至少断言：

```typescript
it('keeps the forced page until all segments and finalize succeed', async () => {
  render(<ShoulderPressUploadPage />)
  await waitFor(() => expect(mockUploadSegment).toHaveBeenCalledTimes(2))
  expect(mockReLaunch).not.toHaveBeenCalled()
  mockFinalize.resolve({ status: 'queued', assembly_job_id: 9 })
  await waitFor(() => expect(mockReLaunch).toHaveBeenCalledWith({ url: '/pages/prescription/index' }))
})
```

再覆盖：页面隐藏调用 pause；返回后要求点击继续；`Taro.saveFile` 成功后才写 manifest；训练期间触发单并发后台上传；app `useDidShow` 发现未 finalize 会话时优先 `reLaunch` 强制页；首页“继续训练”对肩部推举也走专用路由。

- [x] **Step 2: 运行页面测试并确认失败**

Run: `cd miniapp && npm run test -- src/pages/shoulder-press/pageState.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: FAIL，旧页面在第一次 30 秒 timeout 后直接结束并进入单文件上传。

- [x] **Step 3: 重写跟练页**

页面加载时若存在未 finalize 会话则强制进入 upload；否则固定 action、trainingDate、clientSessionId。`onSegment` 处理顺序必须为：

```typescript
const saved = await Taro.saveFile({ tempFilePath })
const info = await Taro.getVideoInfo({ src: saved.savedFilePath })
const nextSession = appendPendingSegment(currentSession, {
  savedFilePath: saved.savedFilePath,
  durationSeconds: info.duration,
  sizeKb: info.size
})
savePendingShoulderPressSession(Taro, nextSession)
void uploadPendingSegmentsInBackground()
```

训练完成按钮调用 recorder `finish()`，等待最后片段持久化后 `reLaunch` 强制页。`useDidHide` 调用 `pause()`，恢复后不自动开相机录像，只显示“继续训练”。有效时长达到处方目标可完成，600 秒硬上限自动完成。

- [x] **Step 4: 重写强制上传页**

页面阶段改为“上传分段 / 提交处理”。加载 manifest 后：创建或恢复远端会话、读取 status 合并服务端已上传索引、顺序补传 pending、调用 finalize。finalize 返回 `queued/assembling/uploading_qiniu/attached` 都表示患者数据已安全接收，可清理本地 manifest 并返回处方；`failed/expired` 留在页面展示重试或重新训练。

不得在服务端确认前删除本地 segment。finalize 成功后逐个 best-effort 调用文件系统 unlink，并在 `finally` 中清除 pending manifest；unlink 失败不重新上传已确认片段，也不能让患者再次被强制页拦截。

- [x] **Step 5: 实现冷启动和入口封堵**

在 `app.ts` 的 `useDidShow` 中先检查肩部推举 pending session；存在且未 finalized 时 `Taro.reLaunch({ url: buildShoulderPressUploadUrl() })` 并跳过普通页面流程。首页 `continueFirstAction()` 使用现有 `actionEntryUrl(firstAction)`，不再把所有非游戏动作硬编码到普通训练页。处方页保持相同恢复检查。

- [x] **Step 6: 更新状态展示和样式**

保留前置摄像头与示例视频并排布局。增加固定尺寸的录像计时、分段上传计数、暂停/继续状态和强制页总进度；按钮和文本必须在 320px 宽度不溢出，不添加嵌套卡片或解释性营销文案。

- [x] **Step 7: 运行小程序测试与双端构建**

Run: `cd miniapp && npm run test && npm run build:weapp && npm run build:h5`

Expected: 全部 PASS；微信和 H5 构建无 TypeScript 错误。

- [ ] **Step 8: 真机检查清单**

在至少一台 iOS 和一台 Android 验证：连续 10 分钟、超过 20 段、弱网/断网恢复、切后台暂停、返回继续、关闭后重开、完成后不能返回录像页。把机型、微信版本、分段数、最终时长和异常写入 plan 执行记录；未完成真机检查不得把本任务标记完成。

- [x] **Step 9: 提交**

```bash
git add miniapp/src/pages/shoulder-press/index.tsx miniapp/src/pages/shoulder-press/upload.tsx miniapp/src/pages/shoulder-press/pageState.ts miniapp/src/pages/shoulder-press/pageState.test.ts miniapp/src/pages/shoulder-press/pages.test.tsx miniapp/src/app.ts miniapp/src/pages/home/index.tsx miniapp/src/pages/prescription/index.tsx miniapp/src/app.scss
git commit -m "feat(miniapp): 完成肩部推举连续分段录像"
```

---

### Task 7: 完成医生端视频播放与动作分析界面

**Files:**
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`
- Modify: `backend/apps/training/tracking.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`

**Interfaces:**
- Consumes: 已有 `/api/training/videos/{id}/download-url/`、分析任务 API 和 tracking 视频摘要。
- Produces: 最近训练记录中的视频状态、单视频抽屉、手动分析、轮询和计数结果展示。

- [x] **Step 1: 写医生端失败测试**

在 fixture 增加 `video_id`、`video_status`、`latest_analysis_status` 和计数字段，测试：

- `attached` 行显示视频图标按钮和“动作分析”。
- `pending_training_videos` 中 queued/assembling/uploading_qiniu 显示“视频处理中”，failed 显示安全失败摘要；这些条目不提供播放和分析按钮。
- 点击视频后请求下载 URL 并在 Drawer 内渲染 `<video controls>`。
- 点击分析 POST 创建任务，pending/running 时禁用重复触发并轮询 latest。
- succeeded 展示“总数 8 / 标准 6 / 不标准 2”；failed 展示失败摘要和重试。
- 非肩部推举或无视频记录不显示动作按钮。

- [x] **Step 2: 运行前端测试并确认失败**

Run: `cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

Expected: FAIL，类型和操作列尚不存在。

- [x] **Step 3: 扩展类型与 API 调用**

为 `TrackingRecentRecord` 增加：

```typescript
video_id: number | null;
video_status: string | null;
latest_analysis_status: "pending" | "running" | "succeeded" | "failed" | null;
analysis_total_count: number | null;
analysis_standard_count: number | null;
analysis_nonstandard_count: number | null;
```

新增待处理类型并加入 `TrackingDetail`：

```typescript
export type TrackingPendingVideo = {
  id: number;
  training_date: string;
  action_name: string;
  status: "queued" | "assembling" | "uploading_qiniu" | "failed";
  failure_reason: string;
  created_at: string;
};

pending_training_videos: TrackingPendingVideo[];
```

后端 `tracking.py` 查询 selected `ProjectPatient` 下 `training_record__isnull=True` 且状态属于上述四种值的 `TrainingVideo`，按 `-created_at, -id` 返回最多 30 条。`failure_reason` 只能使用数据库中已经脱敏、截断的摘要。测试必须覆盖其它项目患者的视频不会泄露。

在页面附近定义 `MotionAnalysisJob` 返回类型。所有请求继续使用 `apiClient`，让现有 Session/CSRF 拦截器处理鉴权。

- [x] **Step 4: 实现视频 Drawer 和分析状态**

使用 AntD `Drawer`、`Button`、`Tag`、`Descriptions`、`Spin`，按钮使用现有 `@ant-design/icons` 的 `PlayCircleOutlined` / `ExperimentOutlined` 并提供 tooltip。视频元素设置 `controls`、`preload="metadata"`、稳定宽高和 `maxWidth: 100%`；关闭 Drawer 时清空短效 URL。

创建分析成功后使 tracking query 和 latest job query 失效；pending/running 每 2 秒轮询，终态停止。错误通过现有安全 `errorMessage` 显示，不渲染签名 URL。

- [x] **Step 5: 运行前端测试、lint 和构建**

Run: `cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx && npm run lint && npm run build`

Expected: PASS，ESLint 与 TypeScript 无报错。

- [x] **Step 6: 提交**

```bash
git add frontend/src/pages/training-tracking/types.ts frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx backend/apps/training/tracking.py backend/apps/training/tests/test_tracking_api.py
git commit -m "feat(frontend): 支持训练视频播放与动作分析"
```

---

### Task 8: 部署配置、全量验证和计划收口

**Files:**
- Modify: `docs/development.md`
- Modify: `docs/superpowers/README.md`
- Modify: `docs/superpowers/plans/2026-07-11-shoulder-press-segmented-server-upload.md`

**Interfaces:**
- Consumes: Task 1-7 的完整链路。
- Produces: 可复现的单机 FFmpeg/Celery 部署说明、完整验证证据和 implemented 状态。

- [x] **Step 1: 增加部署检查说明**

在 `docs/development.md` 的后端启动章节增加以下可执行检查，不创建独立泛化运维文档：

```bash
ffmpeg -version
ffprobe -version
mkdir -p /var/lib/motioncare/training-video-staging
test -w /var/lib/motioncare/training-video-staging
celery -A config worker -Q video-assembly --concurrency=1
celery -A config beat
```

列出 plan 全局约束中的环境变量，并明确 Nginx `client_max_body_size` 只需覆盖 32 MB 单段加 multipart 开销；临时目录不得配置静态访问或备份。

- [x] **Step 2: 运行后端聚焦和全量验证**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_video_api.py apps/training/tests/test_video_session_models.py apps/training/tests/test_video_assembly.py apps/training/tests/test_video_tasks.py apps/training/tests/test_training_video_api.py apps/training/tests/test_motion_analysis.py apps/training/tests/test_tracking_api.py -q
pytest
ruff check .
python manage.py makemigrations --check
```

Expected: 全部 PASS，migration 无漂移。若真实 FFmpeg 集成测试被 skip，必须安装 FFmpeg 后重跑，不接受以 skip 作为完成证据。

- [x] **Step 3: 运行小程序全量验证**

Run:

```bash
cd miniapp
npm run test
npm run build:weapp
npm run build:h5
```

Expected: 全部 PASS。

- [x] **Step 4: 运行医生端全量验证**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: 全部 PASS。

- [ ] **Step 5: 做本地端到端清理验证**

使用 23 个短片段调用患者 API，等待 Celery 完成后验证：

```text
TrainingVideo.status = attached
VideoAssemblyJob.status = succeeded
VideoAssemblyJob.cleanup_status = succeeded
TrainingRecord 恰好 1 条
七牛目标 key 恰好 1 个最终 MP4
业务服务器会话目录不存在
医生下载 URL 可播放
```

再构造失败任务并把时间推进 24 小时，运行过期任务，验证本地文件删除且会话 `expired`。

- [x] **Step 6: 请求最终代码审查**

按 `superpowers:requesting-code-review` 检查：患者越权、文件路径安全、任务幂等、数据库/文件系统不一致、磁盘耗尽、Celery 崩溃恢复、七牛重复对象、FFmpeg 超时、上传页绕过和测试缺口。所有 Blocker/Important 修复后重跑受影响测试。

- [x] **Step 7: 更新执行记录和状态**

在本计划顶部逐任务追加：

```text
每完成一个任务，使用该任务的实际编号和真实 commit short SHA 追加一行执行记录，并注明聚焦测试与复审结果。
```

只有自动化、真实 FFmpeg、七牛集成和 iOS/Android 真机验收全部完成后，才把本计划与 spec 状态改为 `implemented`；否则保持 `implementing` 并明确剩余验收项。

- [x] **Step 8: 提交收口文档**

```bash
git add docs/development.md docs/superpowers/README.md docs/superpowers/specs/2026-07-11-shoulder-press-segmented-server-upload-design.md docs/superpowers/plans/2026-07-11-shoulder-press-segmented-server-upload.md
git commit -m "docs: 收口肩部推举分段视频实施记录"
```
