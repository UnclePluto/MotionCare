# pp-mcare 独立动作分析计算服务 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> 状态：implementing
> 日期：2026-09-05
> 执行记录（2026-09-06, codex）：Tasks 1–14 已落地；Task 15 Step 1–4 与算法服务器候选安装/固定视频回归已落地至 `bf7682f`，业务控制面生产部署、token/AUTO 启用和七牛端到端验收待授权。

**Goal:** 把现有 PP-TinyPose 全帧肩部推举能力迁移为部署在独立服务器的 `pp-mcare` 串行服务，实现自动领取、主训练者骨架视频、训练记录回写和医生修正闭环。

**Architecture:** Django 业务端保存任务与当前训练结果，并通过机器鉴权的 HTTPS API 提供 claim、heartbeat、complete、fail；`pp-mcare` 不接触数据库、Redis 或七牛长期密钥，只使用单任务租约和短期存储凭证。两端同仓库、独立依赖、独立部署，以纯 Python 协议包共享请求/响应结构。

**Tech Stack:** Python 3.12、Django 5、DRF、PostgreSQL 16、Celery Beat、Qiniu SDK、HTTPX、PaddlePaddle 3.3.0、PaddleX 3.7.2、OpenCV 4.10、FFmpeg、React 18、TypeScript、Ant Design 5、TanStack Query v5、pytest、Vitest。

**Spec:** `docs/superpowers/specs/2026-09-05-pp-mcare-independent-compute-service-design.md`

## Global Constraints

- `pp-mcare` 与 MotionCare 共用仓库，但分别构建并部署到不同服务器。
- `pp-mcare` 不连接业务 PostgreSQL、Redis/Celery，不保存七牛 AK/SK，不监听业务入站端口。
- 空队列轮询间隔为 900 秒；启动时立即领取，完成或失败后立即领取下一项。
- 单 worker、单任务租约、全链路串行；不实现批量领取和推理并发。
- PP-TinyPose 仅允许全帧流式推理；不得恢复 5 FPS、10 FPS 或任意抽帧生产入口。
- 只分析和绘制主训练者；其他人员不计数、不出现在骨架视频中。
- 骨架视频使用 PP 官方 `visualize_pose` 语义，输出 H.264/yuv420p/faststart 无声 MP4，不叠加计数、阶段、质量或患者信息。
- 算法和医生写 `TrainingRecord` 同一组当前结果字段，始终满足 `total = standard + nonstandard`。
- 当前不提供成功任务重新分析、失败任务重跑或任何重投入口；网络 I/O 与 API 同次执行最多技术重试 3 次。
- 单条视频分析硬上限 60 分钟；超过上限失败，不截断、不抽帧。该值是算法服务的能力上限，本计划不改变现有录制/上传链路的 30 分钟业务上限；未来上游放宽时无需同步改动算法上限。
- 任务本地目录权限 `0700`、文件不宽于 `0600`；成功、失败和异常退出都必须清理。
- 原视频和骨架视频都位于七牛私有空间；医生播放必须经过后端行级权限校验并获取短期 URL。
- 保留既有肩部推举 v2 计数语义与人工真值 90 的回归门槛，不在本计划中重新调参。
- 不触碰与本功能无关的两份用户未跟踪文件。

## File Structure

```text
packages/motion_analysis_contract/
├── pyproject.toml                         # 纯 Python 协议包元数据
├── src/motion_analysis_contract/
│   ├── __init__.py
│   └── contracts.py                      # DTO、协议版本、计数校验
└── tests/test_contracts.py

backend/apps/training/
├── models.py                             # TrainingRecord 当前动作结果
├── video_models.py                       # 租约、原始结果、骨架元数据
├── motion_analysis_support.py            # 业务端动作支持清单
├── motion_analysis_storage.py            # 短期凭证、对象校验、清理墓碑
├── internal_permissions.py               # pp-mcare 机器鉴权
├── internal_serializers.py               # 内部 API 输入输出校验
├── internal_services.py                  # claim/heartbeat/complete/fail 事务
├── internal_views.py                     # 内部 API HTTP 适配
├── internal_urls.py
├── video_services.py / video_tasks.py    # 自动建任务与视频生命周期
├── serializers.py / views.py             # 医生修正当前结果
├── video_serializers.py / video_views.py # 任务状态与骨架私有 URL
└── tracking.py                            # 直接读取 TrainingRecord 当前值

services/pp_mcare/
├── pyproject.toml                         # 独立运行与开发依赖
├── src/pp_mcare/
│   ├── __main__.py
│   ├── config.py                         # 环境配置与启动校验
│   ├── safe_logging.py                   # 敏感信息脱敏
│   ├── api_client.py                     # claim/heartbeat/complete/fail
│   ├── retry.py                          # 仅网络技术重试
│   ├── worker.py                         # 900 秒空轮询和串行循环
│   ├── workspace.py                      # 任务目录与清理
│   ├── storage.py                        # 短期 URL 下载、上传 token 上传
│   ├── media.py                          # ffprobe 与 FFmpeg 编码
│   ├── pose_inference.py                 # 全帧多人 PP-TinyPose
│   ├── subject_tracker.py                # 主训练者跨帧锁定
│   ├── paddle_visualize_pose.py          # PP 官方 visualize_pose 派生代码
│   ├── pipeline.py                       # 单次推理双路输出编排
│   ├── registry.py                       # source_key -> 动作插件
│   └── actions/
│       ├── base.py
│       └── shoulder_press_v2.py
└── tests/                                # worker、算法、追踪、视频与契约测试

frontend/src/pages/training-tracking/
├── MotionAnalysisPanel.tsx               # 状态、当前结果和医生编辑
├── TrainingVideoSwitcher.tsx             # 原视频/骨架视频同步切换
├── TrainingTrackingDetailPage.tsx        # 抽屉组合与查询
├── types.ts
└── *.test.tsx

deploy/pp-mcare/
├── bootstrap.sh                          # 复用并收紧现有安全初始化
├── install-release.sh                    # 原子安装指定提交
├── pp-mcare.service                      # systemd 单 worker
├── env.example                           # 无七牛 AK/SK 的配置模板
└── run-regression.sh                     # 90 次真实视频回归
```

---

### Task 1: 建立共享协议包

**Files:**
- Create: `packages/motion_analysis_contract/pyproject.toml`
- Create: `packages/motion_analysis_contract/src/motion_analysis_contract/__init__.py`
- Create: `packages/motion_analysis_contract/src/motion_analysis_contract/contracts.py`
- Create: `packages/motion_analysis_contract/tests/test_contracts.py`

**Interfaces:**
- Produces: `PROTOCOL_VERSION: str = "1"`
- Produces: `WorkerCapability`, `MotionCounts`, `ClaimedJob`, `CompletionPayload` dataclasses
- Produces: `validate_counts(payload: Mapping[str, object]) -> MotionCounts`
- Produces: `capability_key(capability: WorkerCapability) -> tuple[str, str, str, str]`

- [x] **Step 1: 写协议校验失败测试**

```python
def test_validate_counts_rejects_bool_and_broken_total():
    with pytest.raises(ContractValidationError):
        validate_counts({"total_count": True, "standard_count": 1, "nonstandard_count": 0})
    with pytest.raises(ContractValidationError):
        validate_counts({"total_count": 3, "standard_count": 1, "nonstandard_count": 1})


def test_claimed_job_round_trip_keeps_exact_storage_scope():
    job = ClaimedJob.from_dict(CLAIM_RESPONSE)
    assert job.upload.object_key == "motion-analysis/1/2026/09/job/skeleton.mp4"
    assert job.action_source_key == "motion-resistance-shoulder-press"
    assert job.protocol_version == PROTOCOL_VERSION
```

- [x] **Step 2: 运行测试并确认因包不存在而失败**

Run: `python -m pytest packages/motion_analysis_contract/tests/test_contracts.py -q`

Expected: FAIL，提示无法导入 `motion_analysis_contract`。

- [x] **Step 3: 实现无第三方依赖的协议对象和严格转换**

```python
@dataclass(frozen=True)
class MotionCounts:
    total_count: int
    standard_count: int
    nonstandard_count: int


def validate_counts(payload: Mapping[str, object]) -> MotionCounts:
    values = []
    for name in ("total_count", "standard_count", "nonstandard_count"):
        value = payload.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ContractValidationError(f"{name} 必须是非负整数")
        values.append(value)
    total, standard, nonstandard = values
    if total != standard + nonstandard:
        raise ContractValidationError("total_count 必须等于 standard_count + nonstandard_count")
    return MotionCounts(total, standard, nonstandard)
```

所有 `from_dict()` 必须拒绝缺字段、未知协议版本、布尔伪装整数和非字符串凭证；`to_dict()` 只输出 JSON 基础类型。

- [x] **Step 4: 安装协议包并运行测试**

Run: `python -m pip install -e ./packages/motion_analysis_contract`

Run: `python -m pytest packages/motion_analysis_contract/tests/test_contracts.py -q`

Expected: PASS。

- [x] **Step 5: 提交协议包**

```bash
git add packages/motion_analysis_contract
git commit -m "feat(动作分析): 建立独立服务协议包"
```

### Task 2: 扩展训练记录与分析任务模型

**Files:**
- Modify: `backend/apps/training/models.py`
- Modify: `backend/apps/training/video_models.py`
- Create: `backend/apps/training/migrations/0014_pp_mcare_control_plane.py`
- Create: `backend/apps/training/tests/test_motion_analysis_models.py`

**Interfaces:**
- Produces: `TrainingRecord.set_motion_result(counts, quality_data, source, updated_by, now)`
- Produces: `MotionAnalysisJob` 租约、版本、幂等和骨架元数据字段
- Consumes: `motion_analysis_contract.MotionCounts`

- [x] **Step 1: 写当前结果约束和旧任务收口测试**

```python
def test_training_record_rejects_inconsistent_motion_counts(training_record):
    training_record.motion_total_count = 5
    training_record.motion_standard_count = 2
    training_record.motion_nonstandard_count = 2
    with pytest.raises(ValidationError):
        training_record.full_clean()


def test_set_motion_result_records_doctor_provenance(training_record, doctor):
    training_record.set_motion_result(
        MotionCounts(5, 4, 1), {"doctor_note": "已复核"}, "doctor", doctor, timezone.now()
    )
    assert training_record.motion_result_source == "doctor"
    assert training_record.motion_result_updated_by == doctor
```

迁移测试还要断言升级时既有 `pending/running` 任务被标记为 `failed`，失败代码为 `service_migration`，防止旧 Celery 任务与新 worker 并行执行。

- [x] **Step 2: 运行模型测试并确认失败**

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_models.py -q`

Expected: FAIL，字段和 `set_motion_result` 尚不存在。

- [x] **Step 3: 增加字段、模型方法和数据库约束**

```python
class MotionResultSource(models.TextChoices):
    ALGORITHM = "algorithm", "算法"
    DOCTOR = "doctor", "医生"


def set_motion_result(self, counts, quality_data, source, updated_by, now):
    self.motion_total_count = counts.total_count
    self.motion_standard_count = counts.standard_count
    self.motion_nonstandard_count = counts.nonstandard_count
    self.motion_quality_data = dict(quality_data)
    self.motion_result_source = source
    self.motion_result_updated_by = updated_by
    self.motion_result_updated_at = now
```

`MotionAnalysisJob` 新增 `worker_id`、`lease_token_hash`、`lease_expires_at`、`last_heartbeat_at`、`action_source_key`、`parameter_version`、`subject_tracker_version`、`completion_idempotency_key`、`failure_code` 和全部 `skeleton_*` 字段。骨架 key 使用 nullable + unique，避免空字符串唯一冲突。

- [x] **Step 4: 生成并验证 migration**

Run: `cd backend && python manage.py makemigrations training --name pp_mcare_control_plane`

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_models.py -q && python manage.py makemigrations --check`

Expected: PASS，且没有额外 migration。

- [x] **Step 5: 提交模型变更**

```bash
git add backend/apps/training/models.py backend/apps/training/video_models.py backend/apps/training/migrations/0014_pp_mcare_control_plane.py backend/apps/training/tests/test_motion_analysis_models.py
git commit -m "feat(动作分析): 增加独立任务与训练结果字段"
```

### Task 3: 自动创建任务并退役医生手动触发与业务端推理

**Files:**
- Create: `backend/apps/training/motion_analysis_support.py`
- Create: `backend/apps/training/motion_analysis_storage.py`
- Modify: `backend/apps/training/video_tasks.py`
- Modify: `backend/apps/training/video_services.py`
- Modify: `backend/apps/training/tasks.py`
- Modify: `backend/apps/training/video_views.py`
- Modify: `backend/apps/training/urls.py`
- Modify: `backend/apps/training/tracking.py`
- Modify: `backend/apps/training/tests/test_motion_analysis.py`
- Modify: `backend/apps/training/tests/test_video_tasks.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`
- Modify: `backend/config/settings.py`

**Interfaces:**
- Produces: `get_analysis_profile(source_key: str | None) -> AnalysisProfile | None`
- Produces: `build_skeleton_object_key(video: TrainingVideo) -> str`
- Produces: `ensure_motion_analysis_job(video: TrainingVideo) -> MotionAnalysisJob | None`
- Removes: `POST /api/training/videos/{video_id}/analysis-jobs/`
- Removes: `run_motion_analysis_job.delay(job_id)` 和业务端 PP 推理入口

- [x] **Step 1: 把旧测试改为自动建任务和无手动入口的失败测试**

```python
def test_attaching_supported_video_creates_one_pending_analysis_job(video_job):
    first = attach_training_video(
        video_job.id,
        video_job.assembly_result,
        video_job.remote_metadata,
        lease_attempt=video_job.attempt_count,
        object_key=video_job.qiniu_object_key,
    )
    second = attach_training_video(
        video_job.id,
        video_job.assembly_result,
        video_job.remote_metadata,
        lease_attempt=video_job.attempt_count,
        object_key=video_job.qiniu_object_key,
    )
    assert second.pk == first.pk
    jobs = MotionAnalysisJob.objects.filter(training_video=video_job.training_video)
    assert jobs.count() == 1
    assert jobs.get().status == MotionAnalysisJob.Status.PENDING


def test_doctor_cannot_create_or_recreate_analysis_job(api_client, doctor, attached_video):
    api_client.force_authenticate(doctor)
    response = api_client.post(f"/api/training/videos/{attached_video.id}/analysis-jobs/")
    assert response.status_code == 404
```

另加不支持动作不建任务、重复 attach 在失败任务后也不新建、自动开关关闭时不建任务的测试。

- [x] **Step 2: 运行相关测试并确认旧行为导致失败**

Run: `cd backend && pytest apps/training/tests/test_motion_analysis.py apps/training/tests/test_video_tasks.py apps/training/tests/test_tracking_api.py -q`

Expected: FAIL，当前仍由医生 POST 并投递 Celery。

- [x] **Step 3: 实现纯业务支持表和幂等自动创建**

```python
ANALYSIS_PROFILES = {
    "motion-resistance-shoulder-press": AnalysisProfile(
        algorithm_name="pp-tiny-pose",
        algorithm_version="PP-TinyPose_128x96",
        rule_version="shoulder-press-v2",
        parameter_version="shoulder-press-v2-defaults",
        subject_tracker_version="primary-subject-v1",
    )
}


def ensure_motion_analysis_job(video):
    if not settings.PP_MCARE_AUTO_ENQUEUE_ENABLED:
        return None
    if MotionAnalysisJob.objects.filter(training_video=video).exists():
        return MotionAnalysisJob.objects.filter(training_video=video).order_by("id").first()
    source_key = video.prescription_action.action_library_item.source_key
    profile = get_analysis_profile(source_key)
    if profile is None:
        return None
    return MotionAnalysisJob.objects.create(
        training_video=video,
        training_record=video.training_record,
        project_patient=video.project_patient,
        prescription_action=video.prescription_action,
        action_source_key=source_key,
        algorithm_name=profile.algorithm_name,
        algorithm_version=profile.algorithm_version,
        rule_version=profile.rule_version,
        parameter_version=profile.parameter_version,
        subject_tracker_version=profile.subject_tracker_version,
        skeleton_bucket=settings.QINIU_BUCKET,
        skeleton_object_key=build_skeleton_object_key(video),
    )
```

在 `motion_analysis_storage.py` 先实现只依赖 video/job 标识的 `build_skeleton_object_key()`；Task 4 再在同一模块增加七牛授权。`backend/config/settings.py` 新增默认关闭的 `PP_MCARE_AUTO_ENQUEUE_ENABLED`。从 `attach_training_video()` 的现有事务中调用自动建任务；删除手动 view/URL、`create_analysis_job()` 和 `run_motion_analysis_job()`。保留租约超时恢复任务，后续 Task 6 改写。

- [x] **Step 4: 更新 tracking 的支持标志并运行回归**

`tracking.py` 只能导入 `motion_analysis_support.py`，不得再从含 Paddle 逻辑的 registry 推导支持能力。

Run: `cd backend && pytest apps/training/tests/test_motion_analysis.py apps/training/tests/test_video_tasks.py apps/training/tests/test_tracking_api.py -q`

Expected: PASS，且测试中没有 `.delay()` 动作分析调用。

- [x] **Step 5: 提交自动任务切换**

```bash
git add backend/apps/training backend/config/settings.py
git commit -m "feat(动作分析): 视频绑定后自动创建分析任务"
```

### Task 4: 签发单任务七牛权限并管理骨架对象生命周期

**Files:**
- Modify: `backend/apps/training/motion_analysis_storage.py`
- Modify: `backend/apps/training/qiniu.py`
- Modify: `backend/config/settings.py`
- Modify: `deploy/env.production.example`
- Modify: `deploy/docker-compose.prod.yml`
- Create: `backend/apps/training/tests/test_motion_analysis_storage.py`

**Interfaces:**
- Produces: `issue_storage_grant(job: MotionAnalysisJob, now) -> AnalysisStorageGrant`
- Produces: `verify_skeleton_upload(job: MotionAnalysisJob, metadata: Mapping) -> dict`
- Produces: `queue_skeleton_cleanup(job: MotionAnalysisJob) -> QiniuCleanupTombstone`

- [x] **Step 1: 写凭证 scope、TTL 和对象校验测试**

```python
@override_settings(PP_MCARE_DOWNLOAD_TOKEN_TTL_SECONDS=3600, PP_MCARE_UPLOAD_TOKEN_TTL_SECONDS=10800)
def test_issue_grant_limits_upload_to_preallocated_key(job, mocker):
    upload_token = mocker.patch("apps.training.motion_analysis_storage.Auth.upload_token")
    grant = issue_storage_grant(job, timezone.now())
    upload_token.assert_called_once_with(job.skeleton_bucket, job.skeleton_object_key, 10800, policy={"insertOnly": 1})
    assert grant.upload.object_key == job.skeleton_object_key
    assert "token=" not in repr(grant)
```

再写 hash、大小、MIME 不一致拒绝和骨架 tombstone `retain_canonical=False` 测试。

- [x] **Step 2: 运行存储测试并确认失败**

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_storage.py -q`

Expected: FAIL，存储授权模块尚不存在。

- [x] **Step 3: 实现任务对象键、私有下载和限定上传 token**

```python
def issue_storage_grant(job, now):
    return AnalysisStorageGrant(
        download_url=create_private_object_download_url(
            job.training_video.object_key,
            expires_at=now + timedelta(seconds=settings.PP_MCARE_DOWNLOAD_TOKEN_TTL_SECONDS),
        ),
        upload=UploadGrant(
            token=Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY).upload_token(
                job.skeleton_bucket,
                job.skeleton_object_key,
                settings.PP_MCARE_UPLOAD_TOKEN_TTL_SECONDS,
                policy={"insertOnly": 1},
            ),
            bucket=job.skeleton_bucket,
            object_key=job.skeleton_object_key,
        ),
    )
```

日志对象的 `repr` 必须隐藏 token 和签名 URL；验证函数复用 `stat_object_metadata()` 和 `validate_object_metadata()`。

- [x] **Step 4: 接入骨架清理墓碑并运行测试**

训练视频删除/解绑清理创建骨架墓碑，`attempt_key_prefix` 使用任务目录前缀，`canonical_key` 为骨架 key，`retain_canonical=False`。

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_storage.py apps/training/tests/test_qiniu.py apps/training/tests/test_video_tasks.py -q`

Expected: PASS。

- [x] **Step 5: 提交存储边界**

```bash
git add backend/apps/training/motion_analysis_storage.py backend/apps/training/qiniu.py backend/config/settings.py deploy/env.production.example deploy/docker-compose.prod.yml backend/apps/training/tests/test_motion_analysis_storage.py
git commit -m "feat(动作分析): 签发单任务七牛存储权限"
```

### Task 5: 实现机器鉴权、领取和心跳 API

**Files:**
- Create: `backend/apps/training/internal_permissions.py`
- Create: `backend/apps/training/internal_serializers.py`
- Create: `backend/apps/training/internal_services.py`
- Create: `backend/apps/training/internal_views.py`
- Create: `backend/apps/training/internal_urls.py`
- Modify: `backend/config/urls.py`
- Modify: `backend/config/settings.py`
- Create: `backend/apps/training/tests/test_motion_analysis_internal_claim_api.py`

**Interfaces:**
- Produces: `claim_next_job(*, worker_id, capabilities, now) -> ClaimedMotionJob | None`
- Produces: `heartbeat_job(*, job_id, lease_token, stage, now) -> MotionAnalysisJob`
- Produces endpoints: `POST /api/internal/motion-analysis/jobs/claim/`、`POST /api/internal/motion-analysis/jobs/{id}/heartbeat/`

- [x] **Step 1: 写鉴权、能力匹配和租约测试**

```python
def test_claim_requires_exact_bearer_token(api_client, settings):
    settings.PP_MCARE_SERVICE_TOKEN_SHA256 = hashlib.sha256(b"machine-secret").hexdigest()
    response = api_client.post(CLAIM_URL, CLAIM_BODY, format="json")
    assert response.status_code == 403


def test_claim_locks_oldest_compatible_job(api_client, machine_auth, compatible_jobs):
    response = api_client.post(CLAIM_URL, CLAIM_BODY, format="json", **machine_auth)
    assert response.status_code == 200
    assert response.data["job_id"] == compatible_jobs[0].id
    assert MotionAnalysisJob.objects.get(pk=compatible_jobs[0].id).status == "running"
```

还要覆盖空队列 204、不匹配能力不领取、并发 claim 只能一个获胜、令牌只存 SHA-256、错误/过期租约拒绝心跳。

- [x] **Step 2: 运行内部 API 测试并确认失败**

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_internal_claim_api.py -q`

Expected: FAIL，URL 和服务尚不存在。

- [x] **Step 3: 实现常量时间机器鉴权和原子 claim**

```python
class IsPpMcareWorker(BasePermission):
    def has_permission(self, request, view):
        scheme, _, supplied = request.headers.get("Authorization", "").partition(" ")
        expected_hash = settings.PP_MCARE_SERVICE_TOKEN_SHA256
        supplied_hash = hashlib.sha256(supplied.encode()).hexdigest()
        return bool(expected_hash and scheme == "Bearer" and compare_digest(supplied_hash, expected_hash))


@transaction.atomic
def claim_next_job(*, worker_id, capabilities, now):
    capability_keys = {capability_key(item) for item in capabilities}
    candidates = (
        MotionAnalysisJob.objects.select_for_update(skip_locked=True)
        .filter(status=MotionAnalysisJob.Status.PENDING)
        .order_by("created_at", "id")
    )
    for job in candidates:
        job_key = (
            job.action_source_key,
            job.algorithm_version,
            job.rule_version,
            job.parameter_version,
        )
        if job_key not in capability_keys:
            continue
        lease_token = secrets.token_urlsafe(32)
        job.status = MotionAnalysisJob.Status.RUNNING
        job.worker_id = worker_id
        job.lease_token_hash = hashlib.sha256(lease_token.encode()).hexdigest()
        job.lease_expires_at = now + timedelta(seconds=300)
        job.last_heartbeat_at = now
        job.started_at = now
        job.save(update_fields=[
            "status", "worker_id", "lease_token_hash", "lease_expires_at",
            "last_heartbeat_at", "started_at", "updated_at",
        ])
        return ClaimedMotionJob(job=job, lease_token=lease_token)
    return None
```

不能把机器 token、租约原文或存储凭证写日志。

- [x] **Step 4: 返回存储 grant 并实现心跳续租**

claim 成功调用 Task 4 的 `issue_storage_grant()`，初始租约 300 秒；heartbeat 每次续回 300 秒并保存 `last_heartbeat_at` 与脱敏阶段名。

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_internal_claim_api.py -q`

Expected: PASS。

- [x] **Step 5: 提交领取 API**

```bash
git add backend/apps/training/internal_* backend/config/urls.py backend/config/settings.py backend/apps/training/tests/test_motion_analysis_internal_claim_api.py
git commit -m "feat(动作分析): 提供任务领取与心跳接口"
```

### Task 6: 实现完成、失败、租约过期和幂等事务

**Files:**
- Modify: `backend/apps/training/internal_serializers.py`
- Modify: `backend/apps/training/internal_services.py`
- Modify: `backend/apps/training/internal_views.py`
- Modify: `backend/apps/training/internal_urls.py`
- Modify: `backend/apps/training/tasks.py`
- Modify: `backend/config/settings.py`
- Create: `backend/apps/training/tests/test_motion_analysis_internal_completion_api.py`
- Create: `backend/apps/training/motion_analysis_monitoring.py`
- Create: `backend/apps/training/tests/test_motion_analysis_monitoring.py`

**Interfaces:**
- Produces: `complete_job(*, job_id, lease_token, idempotency_key, payload, now) -> MotionAnalysisJob`
- Produces: `fail_job(*, job_id, lease_token, idempotency_key, failure, now) -> MotionAnalysisJob`
- Produces: `expire_stale_motion_analysis_jobs(now=None) -> int`
- Produces: `motion_analysis_health_snapshot(now=None) -> MotionAnalysisHealthSnapshot`

- [x] **Step 1: 写完成原子性和幂等测试**

```python
def test_complete_verifies_object_and_updates_job_and_record_atomically(running_job, api_client, machine_auth, mocker):
    mocker.patch("apps.training.internal_services.verify_skeleton_upload", return_value=REMOTE_METADATA)
    response = api_client.post(complete_url(running_job), COMPLETE_BODY, format="json", **machine_auth)
    running_job.refresh_from_db()
    running_job.training_record.refresh_from_db()
    assert response.status_code == 200
    assert running_job.status == "succeeded"
    assert running_job.training_record.motion_total_count == 90
    assert running_job.training_record.motion_result_source == "algorithm"


def test_duplicate_completion_does_not_overwrite_later_doctor_edit(succeeded_job, doctor_edit):
    response = post_same_completion(succeeded_job)
    succeeded_job.training_record.refresh_from_db()
    assert response.status_code == 200
    assert succeeded_job.training_record.motion_result_source == "doctor"
```

另测对象不存在时整个事务回滚、不同幂等键返回 409、失败不清空训练结果、租约过期置失败且不回队列。

- [x] **Step 2: 运行完成 API 测试并确认失败**

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_internal_completion_api.py -q`

Expected: FAIL，complete/fail 服务尚不存在。

- [x] **Step 3: 实现 complete/fail 的锁与终态规则**

```python
@transaction.atomic
def complete_job(*, job_id, lease_token, idempotency_key, payload, now):
    job = MotionAnalysisJob.objects.select_for_update().select_related("training_record", "training_video").get(pk=job_id)
    if job.status == MotionAnalysisJob.Status.SUCCEEDED:
        if job.completion_idempotency_key == idempotency_key:
            return job
        raise AnalysisConflict("任务已由不同请求完成")
    require_live_lease(job, lease_token, now)
    counts = validate_counts(payload)
    verify_skeleton_upload(job, payload["skeleton"])
    job.training_record.set_motion_result(counts, payload["quality_summary"], "algorithm", None, now)
    job.training_record.save(update_fields=[
        "motion_total_count",
        "motion_standard_count",
        "motion_nonstandard_count",
        "motion_quality_data",
        "motion_result_source",
        "motion_result_updated_by",
        "motion_result_updated_at",
        "updated_at",
    ])
    job.status = MotionAnalysisJob.Status.SUCCEEDED
    job.completion_idempotency_key = idempotency_key
    job.total_count = counts.total_count
    job.standard_count = counts.standard_count
    job.nonstandard_count = counts.nonstandard_count
    job.result_payload = payload["result_payload"]
    job.skeleton_object_hash = payload["skeleton"]["object_hash"]
    job.skeleton_size_bytes = payload["skeleton"]["size_bytes"]
    job.skeleton_duration_seconds = payload["skeleton"]["duration_seconds"]
    job.skeleton_width = payload["skeleton"]["width"]
    job.skeleton_height = payload["skeleton"]["height"]
    job.skeleton_fps = payload["skeleton"]["fps"]
    job.finished_at = now
    job.save(update_fields=[
        "status",
        "completion_idempotency_key",
        "total_count",
        "standard_count",
        "nonstandard_count",
        "result_payload",
        "skeleton_object_hash",
        "skeleton_size_bytes",
        "skeleton_duration_seconds",
        "skeleton_width",
        "skeleton_height",
        "skeleton_fps",
        "finished_at",
        "updated_at",
    ])
    return job
```

`fail_job()` 使用同样的租约和幂等边界，只保存稳定 `failure_code` 与最长 2000 字的脱敏摘要。

- [x] **Step 4: 把 stale recovery 改为租约过期并运行测试**

Celery Beat 每 300 秒执行 `recover_stale_motion_analysis_jobs`，条件改为 `status=running AND lease_expires_at < now`；结果只到 `failed`，不重新投递。

新增 `motion_analysis_health_snapshot()` 统计 pending 数量、最老等待秒数、running 任务及租约年龄。Celery Beat 每 300 秒记录快照，最老 pending 超过 1200 秒时输出结构化 warning，供现有日志采集告警。

Run: `cd backend && pytest apps/training/tests/test_motion_analysis_internal_completion_api.py apps/training/tests/test_motion_analysis_monitoring.py apps/training/tests/test_motion_analysis.py -q`

Expected: PASS。

- [x] **Step 5: 提交完成和失败控制面**

```bash
git add backend/apps/training/internal_* backend/apps/training/motion_analysis_monitoring.py backend/apps/training/tasks.py backend/config/settings.py backend/apps/training/tests/test_motion_analysis_internal_completion_api.py backend/apps/training/tests/test_motion_analysis_monitoring.py
git commit -m "feat(动作分析): 原子完成独立分析任务"
```

### Task 7: 建立 pp-mcare 配置、HTTP 客户端和串行 worker

**Files:**
- Create: `services/pp_mcare/pyproject.toml`
- Create: `services/pp_mcare/src/pp_mcare/__init__.py`
- Create: `services/pp_mcare/src/pp_mcare/__main__.py`
- Create: `services/pp_mcare/src/pp_mcare/config.py`
- Create: `services/pp_mcare/src/pp_mcare/retry.py`
- Create: `services/pp_mcare/src/pp_mcare/safe_logging.py`
- Create: `services/pp_mcare/src/pp_mcare/api_client.py`
- Create: `services/pp_mcare/src/pp_mcare/worker.py`
- Create: `services/pp_mcare/tests/test_config.py`
- Create: `services/pp_mcare/tests/test_api_client.py`
- Create: `services/pp_mcare/tests/test_worker.py`

**Interfaces:**
- Produces: `Settings.from_env(environ: Mapping[str, str]) -> Settings`
- Produces: `MotionCareClient.claim/heartbeat/complete/fail`
- Produces: `run_worker(*, client, processor, sleeper, settings, max_claims: int | None = None) -> None`

- [x] **Step 1: 写 900 秒空轮询和积压连续处理测试**

```python
def test_worker_sleeps_only_after_empty_claim():
    client = FakeClient(claims=[JOB_1, JOB_2, None])
    sleeps = []
    run_worker(client=client, processor=SuccessfulProcessor(), sleeper=sleeps.append, settings=TEST_SETTINGS, max_claims=3)
    assert client.claim_count == 3
    assert sleeps == [900]


def test_settings_rejects_qiniu_long_term_secrets():
    env = VALID_ENV | {"QINIU_ACCESS_KEY": "forbidden"}
    with pytest.raises(ConfigurationError):
        Settings.from_env(env)
```

另测启动立即 claim、成功/失败后不 sleep、机器 token 不出现在日志、可重试状态码只限超时/连接错误/5xx。

- [x] **Step 2: 运行 service 测试并确认失败**

Run: `python -m pytest services/pp_mcare/tests/test_config.py services/pp_mcare/tests/test_api_client.py services/pp_mcare/tests/test_worker.py -q`

Expected: FAIL，service 尚不存在。

- [x] **Step 3: 建立独立包和配置边界**

```python
@dataclass(frozen=True)
class Settings:
    api_base_url: str
    service_token: str = field(repr=False)
    worker_id: str
    poll_interval_seconds: int = 900
    work_root: Path = Path("/opt/motioncare-analysis/tmp/jobs")
    model_cache: Path = Path("/opt/motioncare-analysis/model-cache")
    network_attempts: int = 3
```

生产依赖固定 `httpx>=0.27,<1`、`qiniu>=7.17,<8`、`psutil>=6,<8`；`inference` extra 固定已验收的 Paddle/OpenCV 版本；dev extra 固定 pytest/ruff。

- [x] **Step 4: 实现客户端重试和 worker 循环**

`MotionCareClient` 每次请求设置 Bearer 机器 token；日志只写 method、path、status、job ID，不写 headers/body 中的 URL/token。`run_worker()` 每次只把一个 `ClaimedJob` 交给 processor。

Run: `python -m pip install -e ./packages/motion_analysis_contract -e './services/pp_mcare[dev]'`

Run: `python -m pytest services/pp_mcare/tests/test_config.py services/pp_mcare/tests/test_api_client.py services/pp_mcare/tests/test_worker.py -q`

Expected: PASS。

- [x] **Step 5: 提交 worker 基础**

```bash
git add services/pp_mcare
git commit -m "feat(pp-mcare): 建立串行轮询服务"
```

### Task 8: 迁移肩部推举 v2 为动作插件

**Files:**
- Create: `services/pp_mcare/src/pp_mcare/actions/base.py`
- Create: `services/pp_mcare/src/pp_mcare/actions/shoulder_press_v2.py`
- Create: `services/pp_mcare/src/pp_mcare/registry.py`
- Create: `services/pp_mcare/tests/test_shoulder_press_v2.py`
- Create: `services/pp_mcare/tests/test_registry.py`
- Reference: `backend/apps/training/shoulder_press_v2.py`
- Reference: `backend/apps/training/tests/test_shoulder_press_v2.py`

**Interfaces:**
- Produces: `ActionPlugin` Protocol
- Produces: `PoseFrame(timestamp_ms, named_keypoints)` immutable dataclass
- Produces: `AnalysisResult(counts: MotionCounts, payload: dict)` immutable dataclass
- Produces: `get_action_plugin(source_key, algorithm_version, rule_version, parameter_version) -> ActionPlugin | None`
- Produces: `ShoulderPressV2Plugin.analyze(frames: Iterable[PoseFrame]) -> AnalysisResult`

- [x] **Step 1: 复制现有回归测试到 service 并增加插件契约测试**

```python
def test_registry_resolves_only_exact_shoulder_press_v2_versions():
    plugin = get_action_plugin(
        "motion-resistance-shoulder-press",
        "PP-TinyPose_128x96",
        "shoulder-press-v2",
        "shoulder-press-v2-defaults",
    )
    assert plugin is not None
    assert plugin.rule_version == "shoulder-press-v2"
    assert get_action_plugin(
        "motion-resistance-row",
        "PP-TinyPose_128x96",
        "shoulder-press-v2",
        "shoulder-press-v2-defaults",
    ) is None
```

原 `test_shoulder_press_v2.py` 的完整周期、左右最大值、锚点、质量、边界和 90 次语义全部保留，不精简为少量冒烟。

- [x] **Step 2: 运行迁移后的测试并确认失败**

Run: `python -m pytest services/pp_mcare/tests/test_shoulder_press_v2.py services/pp_mcare/tests/test_registry.py -q`

Expected: FAIL，插件文件尚不存在。

- [x] **Step 3: 无行为变化迁移计数实现并加插件包装**

```python
@dataclass(frozen=True)
class PoseFrame:
    timestamp_ms: int
    named_keypoints: Mapping[str, tuple[float, float, float]]


@dataclass(frozen=True)
class AnalysisResult:
    counts: MotionCounts
    payload: dict[str, object]


class ShoulderPressV2Plugin:
    source_key = "motion-resistance-shoulder-press"
    algorithm_version = "PP-TinyPose_128x96"
    rule_version = "shoulder-press-v2"
    parameter_version = "shoulder-press-v2-defaults"

    def analyze(self, frames):
        payload = analyze_shoulder_press_keypoints_v2(frames)
        counts = validate_counts(payload)
        return AnalysisResult(counts=counts, payload=payload)
```

迁移时只调整 import 和类型，不调整阈值、左右计数或质量规则。

- [x] **Step 4: 运行插件与协议测试**

Run: `python -m pytest services/pp_mcare/tests/test_shoulder_press_v2.py services/pp_mcare/tests/test_registry.py packages/motion_analysis_contract/tests/test_contracts.py -q`

Expected: PASS，测试数量不低于原 shoulder v2 测试数量。

- [x] **Step 5: 提交动作插件**

```bash
git add services/pp_mcare/src/pp_mcare/actions services/pp_mcare/src/pp_mcare/registry.py services/pp_mcare/tests/test_shoulder_press_v2.py services/pp_mcare/tests/test_registry.py
git commit -m "feat(pp-mcare): 迁移肩部推举全帧算法插件"
```

### Task 9: 实现全帧多人推理和主训练者追踪

**Files:**
- Create: `services/pp_mcare/src/pp_mcare/pose_inference.py`
- Create: `services/pp_mcare/src/pp_mcare/subject_tracker.py`
- Create: `services/pp_mcare/tests/test_pose_inference.py`
- Create: `services/pp_mcare/tests/test_subject_tracker.py`
- Reference: `backend/apps/training/pose_inference.py`

**Interfaces:**
- Produces: `PersonPose(raw_keypoints, named_keypoints, bbox, mean_score, fingerprint)`
- Produces: `InferenceFrame(timestamp_ms, source_fps, image, people)`
- Produces: `open_full_frame_pose_stream(video_path, model=None, capture=None) -> VideoPoseStream`
- Produces: `PrimarySubjectTracker.observe(frame: InferenceFrame) -> TrackedPoseFrame`
- Produces: `TrackedPoseFrame.to_action_frame() -> PoseFrame`

- [x] **Step 1: 写“每帧所有人”和跨帧不换人的失败测试**

```python
def test_pose_stream_infers_every_decoded_frame_and_keeps_all_people(fake_capture, fake_model):
    with open_full_frame_pose_stream("video.mp4", model=fake_model, capture=fake_capture) as stream:
        frames = list(stream)
    assert stream.decoded_frame_count == 3
    assert stream.inferred_frame_count == 3
    assert len(frames[0].people) == 2


def test_tracker_keeps_original_subject_when_larger_bystander_enters():
    tracker = PrimarySubjectTracker()
    first = tracker.observe(frame(0, [trainee(center=.50, area=.40)]))
    second = tracker.observe(frame(33, [trainee(center=.51, area=.39), bystander(center=.25, area=.55)]))
    assert second.primary.fingerprint == first.primary.fingerprint
```

还要覆盖中心最大主体初始化、短缺失保持、连续失锁 3000ms 抛 `SubjectUnstable`、歧义帧不输出旁人、异常时间戳单调回退。

- [x] **Step 2: 运行推理与追踪测试并确认失败**

Run: `python -m pytest services/pp_mcare/tests/test_pose_inference.py services/pp_mcare/tests/test_subject_tracker.py -q`

Expected: FAIL，模块尚不存在。

- [x] **Step 3: 把 PaddleX 结果转换为完整多人结构**

```python
def convert_paddlex_people(result, *, frame_width, frame_height):
    people = _result_payload(result)["res"]["kpts"]
    return tuple(
        PersonPose.from_coco_keypoints(person["keypoints"], frame_width, frame_height)
        for person in people
        if valid_coco_person(person)
    )
```

必须保留全部 17 个原始像素关键点供 PP 绘制，同时提供肩、肘、腕、髋归一化命名关键点供动作插件；不得像旧实现一样逐帧选择最高平均分的人。

`TrackedPoseFrame.to_action_frame()` 只把已锁定主训练者的 `named_keypoints` 交给动作插件；原始多人集合不得进入计数算法。

- [x] **Step 4: 实现 `primary-subject-v1` 追踪器**

初始主体优先画面中心 70% 区域内面积最大者；后续用共同可靠关键点的归一化中位距离为主、bbox IoU 为辅匹配既有主体。默认最大归一化跳变 0.35、连续失锁上限 3000ms、歧义帧占比上限 10%，常量集中在模块顶部并写入结果摘要。

Run: `python -m pytest services/pp_mcare/tests/test_pose_inference.py services/pp_mcare/tests/test_subject_tracker.py -q`

Expected: PASS。

- [x] **Step 5: 提交推理与主体追踪**

```bash
git add services/pp_mcare/src/pp_mcare/pose_inference.py services/pp_mcare/src/pp_mcare/subject_tracker.py services/pp_mcare/tests/test_pose_inference.py services/pp_mcare/tests/test_subject_tracker.py
git commit -m "feat(pp-mcare): 锁定全帧主训练者"
```

### Task 10: 复用 PP 可视化并建立无声骨架视频流水线

**Files:**
- Create: `services/pp_mcare/src/pp_mcare/paddle_visualize_pose.py`
- Create: `services/pp_mcare/src/pp_mcare/media.py`
- Create: `services/pp_mcare/src/pp_mcare/pipeline.py`
- Create: `services/pp_mcare/NOTICE`
- Create: `services/pp_mcare/tests/test_paddle_visualize_pose.py`
- Create: `services/pp_mcare/tests/test_media.py`
- Create: `services/pp_mcare/tests/test_pipeline.py`

**Interfaces:**
- Produces: `render_primary_pose(image, person: PersonPose, threshold=0.6) -> np.ndarray`
- Produces: `SkeletonVideoEncoder(path, width, height, fps)` with `write(frame)` and `close()`
- Produces: `run_local_pipeline(job, input_path, output_path, heartbeat) -> LocalAnalysisResult`

- [x] **Step 1: 写单人绘制、单次推理双路消费和无音轨测试**

```python
def test_renderer_passes_exactly_one_skeleton_to_pp_visualizer(mocker, person, frame):
    visualize_pose = mocker.patch("pp_mcare.paddle_visualize_pose._visualize_pose")
    render_primary_pose(frame, person)
    results = visualize_pose.call_args.args[1]
    assert len(results["keypoint"][0]) == 1


def test_pipeline_infers_each_frame_once_for_analysis_and_video(fake_pose_stream, fake_plugin, fake_encoder):
    result = run_local_pipeline(JOB, INPUT, OUTPUT, heartbeat=lambda _: None)
    assert fake_pose_stream.inferred_frame_count == fake_pose_stream.decoded_frame_count
    assert fake_plugin.seen_timestamps == fake_encoder.seen_timestamps
```

媒体集成测试用 2 秒夹具运行 `ffprobe`，断言只有一个 H.264 视频流、无音频流、像素格式 yuv420p、时长误差符合 `max(1 秒, 1%)`。

- [x] **Step 2: 运行流水线测试并确认失败**

Run: `python -m pytest services/pp_mcare/tests/test_paddle_visualize_pose.py services/pp_mcare/tests/test_media.py services/pp_mcare/tests/test_pipeline.py -q`

Expected: FAIL，可视化和流水线尚不存在。

- [x] **Step 3: 引入 PP 官方可视化语义并保留许可证**

从 PaddleDetection `release/2.9` 的 `deploy/python/visualize.py::visualize_pose` 提取 `visualize_pose`/`get_color` 到独立模块，保留 Apache-2.0 文件头，并在 `NOTICE` 记录来源 URL 和版本。包装器只传一个主训练者：

```python
def render_primary_pose(image, person, threshold=0.6):
    results = {
        "keypoint": ([person.raw_keypoints], [person.mean_score]),
        "bbox": [person.bbox],
    }
    return _visualize_pose(image.copy(), results, visual_thresh=threshold, returnimg=True)
```

- [x] **Step 4: 用 FFmpeg stdin 流式编码并编排生成器**

编码命令固定包含：

```text
ffmpeg -f rawvideo -pix_fmt bgr24 -s WIDTHxHEIGHT -r SOURCE_FPS -i pipe:0 -an -c:v libx264 -pix_fmt yuv420p -movflags +faststart OUTPUT.mp4
```

`pipeline.py` 用一个生成器完成：读取 `InferenceFrame` → tracker 选择主主体 → 绘制并写 encoder → yield 动作插件帧。插件消费结束后校验推理帧数、主体覆盖、结果计数和输出媒体。

Run: `python -m pytest services/pp_mcare/tests/test_paddle_visualize_pose.py services/pp_mcare/tests/test_media.py services/pp_mcare/tests/test_pipeline.py -q`

Expected: PASS。

- [x] **Step 5: 提交骨架视频流水线**

```bash
git add services/pp_mcare/src/pp_mcare/paddle_visualize_pose.py services/pp_mcare/src/pp_mcare/media.py services/pp_mcare/src/pp_mcare/pipeline.py services/pp_mcare/NOTICE services/pp_mcare/tests
git commit -m "feat(pp-mcare): 生成单主体无声骨架视频"
```

### Task 11: 接通下载、上传、心跳与任务目录清理

**Files:**
- Create: `services/pp_mcare/src/pp_mcare/workspace.py`
- Create: `services/pp_mcare/src/pp_mcare/storage.py`
- Modify: `services/pp_mcare/src/pp_mcare/worker.py`
- Modify: `services/pp_mcare/src/pp_mcare/api_client.py`
- Create: `services/pp_mcare/tests/test_workspace.py`
- Create: `services/pp_mcare/tests/test_storage.py`
- Create: `services/pp_mcare/tests/test_task_execution.py`

**Interfaces:**
- Produces: `TaskWorkspace.create(root, job_id) -> TaskWorkspace`
- Produces: `download_original(grant, destination, expected_size, expected_hash) -> DownloadedObject`
- Produces: `upload_skeleton(grant, path) -> UploadedObject`
- Produces: `process_claimed_job(job, client, settings) -> None`

- [x] **Step 1: 写安全目录、网络重试和完整执行测试**

```python
def test_task_workspace_cleans_files_on_exception(tmp_path):
    with pytest.raises(RuntimeError):
        with TaskWorkspace.create(tmp_path, 42) as workspace:
            workspace.input_path.write_bytes(b"private")
            raise RuntimeError("boom")
    assert list(tmp_path.iterdir()) == []


def test_process_uploads_then_completes_then_cleans(fake_qiniu, fake_motioncare, tmp_path, caplog):
    process_claimed_job(JOB, fake_motioncare, settings(tmp_path))
    assert fake_qiniu.calls == [("upload", JOB.upload.object_key)]
    assert fake_motioncare.complete_calls[0].counts.total_count == 90
    assert list(tmp_path.iterdir()) == []
    assert "peak_rss_bytes" in caplog.text
    assert "disk_free_bytes" in caplog.text
```

另测下载 hash/大小不符、上传 4xx 不重试、5xx 最多 3 次、complete 响应丢失使用同一幂等键、失败只调用 fail 不重跑 pipeline、启动清理超龄目录。

- [x] **Step 2: 运行执行测试并确认失败**

Run: `python -m pytest services/pp_mcare/tests/test_workspace.py services/pp_mcare/tests/test_storage.py services/pp_mcare/tests/test_task_execution.py -q`

Expected: FAIL，任务工作目录和存储客户端尚不存在。

- [x] **Step 3: 实现精确目录边界和无长期凭证上传**

```python
with TaskWorkspace.create(settings.work_root, job.job_id) as workspace:
    completion_idempotency_key = uuid.uuid4().hex
    with HeartbeatLease(client, job, interval_seconds=60) as lease:
        download_original(job.download, workspace.input_path, job.video.size_bytes, job.video.object_hash)
        local = run_local_pipeline(job, workspace.input_path, workspace.output_path, lease.raise_if_lost)
        uploaded = upload_skeleton(job.upload, workspace.output_path)
        client.complete(job.job_id, job.lease_token, completion_idempotency_key, local, uploaded)
```

`upload_skeleton()` 只把后端给出的 token 和 key 传给 Qiniu SDK；模块不得读取 `QINIU_ACCESS_KEY/QINIU_SECRET_KEY`。

- [x] **Step 4: 加入独立心跳泵和 fail-safe 收口**

心跳泵每 60 秒调用 heartbeat，在下载、推理、编码和上传期间持续续租，但不启动第二个推理任务。任务异常先构造稳定 failure code 并调用 `fail`；无论 fail 是否成功都清理本地目录。上传成功而 complete 失败时仍清理，本地记录对象 key，业务端租约回收负责创建孤儿清理墓碑。

每个阶段记录开始/结束时间；任务结束记录下载、推理、编码、上传、回传耗时，以及 decoded/inferred/output 帧数、峰值 RSS、系统内存、Swap、磁盘余量和清理结果。结构化日志只使用 job ID 关联，不含患者信息。

Run: `python -m pytest services/pp_mcare/tests -q`

Expected: PASS。

- [x] **Step 5: 提交端到端 worker 执行**

```bash
git add services/pp_mcare
git commit -m "feat(pp-mcare): 接通任务下载上传与清理"
```

### Task 12: 提供医生结果修正、骨架 URL 和安全状态 API

**Files:**
- Modify: `backend/apps/training/serializers.py`
- Modify: `backend/apps/training/views.py`
- Modify: `backend/apps/training/video_serializers.py`
- Modify: `backend/apps/training/video_views.py`
- Modify: `backend/apps/training/urls.py`
- Modify: `backend/apps/training/tracking.py`
- Create: `backend/apps/training/tests/test_motion_result_edit_api.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`
- Modify: `backend/apps/training/tests/test_motion_analysis.py`

**Interfaces:**
- Produces: `PATCH /api/training/{record_id}/motion-result/`
- Produces: `GET /api/training/videos/{video_id}/analysis-jobs/latest/skeleton-url/`
- Produces: tracking fields `motion_*`, `analysis_status`, `analysis_failure_message`, `skeleton_available`

- [x] **Step 1: 写医生编辑和骨架私有 URL 测试**

```python
def test_doctor_overwrites_algorithm_fields_on_same_training_record(api_client, doctor, analyzed_record):
    api_client.force_authenticate(doctor)
    response = api_client.patch(
        f"/api/training/{analyzed_record.id}/motion-result/",
        {"total_count": 90, "standard_count": 85, "nonstandard_count": 5, "quality_note": "人工复核"},
        format="json",
    )
    analyzed_record.refresh_from_db()
    assert response.status_code == 200
    assert analyzed_record.motion_result_source == "doctor"
    assert analyzed_record.motion_result_updated_by == doctor


def test_skeleton_url_requires_row_level_access(api_client, unrelated_doctor, succeeded_job):
    api_client.force_authenticate(unrelated_doctor)
    response = api_client.get(skeleton_url(succeeded_job.training_video_id))
    assert response.status_code == 404
```

还要覆盖 pending/running 时 409、failed/unsupported 可填写、计数不守恒 400、公开响应不含内部 `failure_reason`/对象 key/令牌。

- [x] **Step 2: 运行公开 API 测试并确认失败**

Run: `cd backend && pytest apps/training/tests/test_motion_result_edit_api.py apps/training/tests/test_tracking_api.py apps/training/tests/test_motion_analysis.py -q`

Expected: FAIL，编辑 action 与骨架 URL 尚不存在。

- [x] **Step 3: 实现受控编辑 action**

```python
@action(detail=True, methods=["patch"], url_path="motion-result")
def motion_result(self, request, pk=None):
    record = get_object_or_404(
        TrainingRecord.objects.filter(project_patient__in=accessible_project_patients(request.user)),
        pk=pk,
    )
    if record.motion_analysis_jobs.filter(status__in=["pending", "running"]).exists():
        return Response({"detail": "动作分析完成前暂不可修改"}, status=409)
    serializer = MotionResultUpdateSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    update_motion_result_from_doctor(record, request.user, serializer.validated_data)
    return Response(TrainingRecordSerializer(record).data)
```

- [x] **Step 4: 实现骨架下载和 tracking 当前值**

骨架 URL 只在最新任务 `succeeded` 且对象元数据完整时签发；tracking 直接读 `TrainingRecord.motion_*`，任务仅提供状态。失败对医生固定为“自动分析未完成，请填写训练结果”，不返回内部摘要。

Run: `cd backend && pytest apps/training/tests/test_motion_result_edit_api.py apps/training/tests/test_tracking_api.py apps/training/tests/test_motion_analysis.py -q`

Expected: PASS。

- [x] **Step 5: 提交医生端业务 API**

```bash
git add backend/apps/training/serializers.py backend/apps/training/views.py backend/apps/training/video_serializers.py backend/apps/training/video_views.py backend/apps/training/urls.py backend/apps/training/tracking.py backend/apps/training/tests
git commit -m "feat(动作分析): 支持医生修正结果与查看骨架视频"
```

### Task 13: 改造医生端视频与动作结果界面

**Files:**
- Create: `frontend/src/pages/training-tracking/MotionAnalysisPanel.tsx`
- Create: `frontend/src/pages/training-tracking/MotionAnalysisPanel.test.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingVideoSwitcher.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingVideoSwitcher.test.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.css`

**Interfaces:**
- Produces: `<MotionAnalysisPanel record onSaved />`
- Produces: `<TrainingVideoSwitcher originalUrl skeletonUrl activeSource onChange />`
- Consumes: Task 12 tracking、编辑与短期 URL API

- [x] **Step 1: 用 UI 测试固定五种状态和无触发按钮**

```tsx
it.each(["pending", "running"])("%s 时只展示状态且禁止编辑", async (status) => {
  render(<MotionAnalysisPanel record={record({ analysis_status: status })} />);
  expect(screen.queryByRole("button", { name: /开始|重新分析|重试分析/ })).not.toBeInTheDocument();
  expect(screen.getByRole("spinbutton", { name: "总次数" })).toBeDisabled();
});

it("失败时允许医生填写同一结果字段", async () => {
  render(<MotionAnalysisPanel record={record({ analysis_status: "failed" })} />);
  await userEvent.type(screen.getByRole("spinbutton", { name: "总次数" }), "90");
  expect(screen.getByRole("button", { name: "保存训练结果" })).toBeEnabled();
});
```

再测 succeeded 可修改、unsupported 可填写、守恒错误、保存后“医生已修正”、不显示内部错误。

- [x] **Step 2: 写视频切换保持时间点测试并确认全部失败**

```tsx
it("切换骨架视频时复制 currentTime 和暂停状态", async () => {
  render(<TrainingVideoSwitcher originalUrl="original" skeletonUrl="skeleton" />);
  setMediaState("训练视频播放器", { currentTime: 42.5, paused: true });
  await userEvent.click(screen.getByRole("radio", { name: "骨架视频" }));
  fireEvent.loadedMetadata(screen.getByLabelText("骨架视频播放器"));
  expect(screen.getByLabelText("骨架视频播放器").currentTime).toBeCloseTo(42.5);
});
```

Run: `cd frontend && npm run test -- MotionAnalysisPanel.test.tsx TrainingVideoSwitcher.test.tsx TrainingTrackingDetailPage.test.tsx`

Expected: FAIL，新组件尚不存在且旧页面仍有手动分析按钮。

- [x] **Step 3: 实现结果表单和状态文案**

使用 AntD `Form` + `InputNumber`，只提交 Task 12 的四个允许字段。pending/running 禁用；succeeded/failed/unsupported 可编辑。保存成功失效 `training-tracking` 与 `latest-analysis` query。

- [x] **Step 4: 实现原视频/骨架视频切换并移除旧 mutation**

删除 `createAnalysisMutation`、开始/重新分析按钮和 POST 调用。骨架选项只有成功且 URL 可取时启用；切换前保存 `currentTime` 与 `paused`，新视频 `loadedMetadata` 后恢复，播放失败只保持暂停并展示提示。

Run: `cd frontend && npm run test -- MotionAnalysisPanel.test.tsx TrainingVideoSwitcher.test.tsx TrainingTrackingDetailPage.test.tsx`

Expected: PASS。

- [x] **Step 5: 运行前端门禁并提交**

Run: `cd frontend && npm run lint && npm run build`

Expected: lint 无 error，build 成功。

```bash
git add frontend/src/pages/training-tracking
git commit -m "feat(训练追踪): 展示骨架视频并支持医生修正"
```

### Task 14: 切断业务端算法依赖并迁移回归工具

**Files:**
- Delete: `backend/apps/training/analysis.py`
- Delete: `backend/apps/training/analysis_registry.py`
- Delete: `backend/apps/training/pose_inference.py`
- Delete: `backend/apps/training/shoulder_press_v2.py`
- Delete: `backend/apps/training/pose_benchmark.py`
- Delete: `backend/apps/training/pose_benchmark_resources.py`
- Delete: `backend/apps/training/management/commands/run_pose_smoke_benchmark.py`
- Delete or migrate: corresponding backend pose/benchmark/shoulder tests
- Modify: `backend/pyproject.toml`
- Create: `services/pp_mcare/src/pp_mcare/regression.py`
- Create: `services/pp_mcare/src/pp_mcare/cli.py`
- Create: `services/pp_mcare/tests/test_regression.py`
- Modify: `deploy/motion-analysis-smoke/run-benchmark.sh`
- Modify: `backend/apps/training/tests/test_pose_benchmark_scripts.py`

**Interfaces:**
- Produces: `python -m pp_mcare regression --video /Users/nick/my_dev/ai/agents/IMG_0383_SDR_5min.mp4 --manual-total-count 90 --report /private/tmp/pp-mcare-regression.json`
- Removes: Django/Celery 进程对 Paddle、PaddleX 和 OpenCV 的任何运行时 import

- [x] **Step 1: 写独立回归 CLI 和业务包无 Paddle import 测试**

```python
def test_regression_cli_rejects_manual_count_other_than_90(runner, video):
    completed = runner(["regression", "--video", str(video), "--manual-total-count", "89"])
    assert completed.returncode == 2


def test_backend_training_package_has_no_paddle_imports():
    offenders = scan_imports(PROJECT_ROOT / "backend/apps/training", {"paddle", "paddlex", "cv2"})
    assert offenders == []
```

- [x] **Step 2: 运行测试并确认旧代码边界失败**

Run: `python -m pytest services/pp_mcare/tests/test_regression.py -q`

Run: `cd backend && pytest apps/training/tests/test_pose_benchmark_scripts.py -q`

Expected: FAIL，回归 CLI 不存在且 backend 仍包含推理模块。

- [x] **Step 3: 迁移 benchmark 资源采样、报告和命令**

保留现有报告的人工真值、帧数一致、耗时、RSS、Swap 与 SHA-256 校验；入口改为 service CLI，唯一模式仍为 `all_frames`。`deploy/motion-analysis-smoke/run-benchmark.sh` 改为调用 `/opt/motioncare-analysis/venv/bin/python -m pp_mcare regression`。

- [x] **Step 4: 删除业务端算法实现和可选依赖**

确认 Task 8–10 已承接全部测试后删除旧模块与重复测试，从 `backend/pyproject.toml` 删除 `motion-analysis` extra。保留与任务控制面、Qiniu 和视频组装相关模块。

Run: `cd backend && pytest apps/training -q && ruff check .`

Run: `python -m pytest services/pp_mcare/tests -q`

Expected: 全部 PASS，backend 安装不需要 Paddle/OpenCV。

- [x] **Step 5: 提交依赖隔离**

```bash
git add backend services/pp_mcare deploy/motion-analysis-smoke
git commit -m "refactor(动作分析): 将推理能力完全迁出业务服务"
```

### Task 15: 部署脚本、CI、全链路验收与文档收口

**Files:**
- Create: `deploy/pp-mcare/bootstrap.sh`
- Create: `deploy/pp-mcare/install-release.sh`
- Create: `deploy/pp-mcare/pp-mcare.service`
- Create: `deploy/pp-mcare/env.example`
- Create: `deploy/pp-mcare/run-regression.sh`
- Create: `services/pp_mcare/tests/test_deploy_scripts.py`
- Modify: `.github/workflows/deploy-production.yml`
- Modify: `backend/Dockerfile`
- Modify: `backend/tests/test_deploy_workflow.py`
- Modify: `docs/superpowers/plans/2026-09-05-pp-mcare-independent-compute-service.md`
- Modify: `docs/superpowers/specs/2026-09-05-pp-mcare-independent-compute-service-design.md`
- Modify: `docs/superpowers/README.md`
- Modify: `specs/patient-rehab-system/changelog.md`

**Interfaces:**
- Produces: `systemctl start|stop|status pp-mcare`
- Produces: `/opt/motioncare-analysis/current` 原子发布目录
- Produces: CI 对协议包、backend、frontend、pp-mcare 非推理测试的完整门禁

- [x] **Step 1: 写脚本安全和 CI 构建失败测试**

```python
def test_install_release_rejects_non_commit_release_name(tmp_path):
    completed = source_and_call(INSTALL_SCRIPT, "_install_release", tmp_path, "latest")
    assert completed.returncode == 2


def test_systemd_unit_runs_unprivileged_without_inbound_port():
    unit = SERVICE_UNIT.read_text()
    assert "User=motioncare-analysis" in unit
    assert "ExecStart=/opt/motioncare-analysis/current/.venv/bin/python -m pp_mcare" in unit
    assert "--host" not in unit and "--port" not in unit
```

CI 测试断言 backend Dockerfile 先安装 `motion_analysis_contract`，工作流运行 contract 和 pp-mcare 测试，但不在通用 CI 下载重量级推理模型。

- [x] **Step 2: 运行部署测试并确认失败**

Run: `python -m pytest services/pp_mcare/tests/test_deploy_scripts.py backend/tests/test_deploy_workflow.py -q`

Expected: FAIL，正式部署脚本和 CI 步骤尚不存在。

- [x] **Step 3: 实现安全安装、systemd 和 CI**

`bootstrap.sh` 复用现有目录/用户/Swap 安全检查；`install-release.sh` 只接收 7–40 位提交 SHA，把归档解压到 `/opt/motioncare-analysis/releases/` 下以该 SHA 命名的目录，在该 release 的 `.venv` 完成安装和自检后原子切换 `current`。systemd 始终执行 `/opt/motioncare-analysis/current/.venv/bin/python -m pp_mcare`。`env.example` 只允许：

```text
PP_MCARE_API_BASE_URL=https://mcare-api.whestsun.com
PP_MCARE_SERVICE_TOKEN=
PP_MCARE_WORKER_ID=pp-mcare-01
PP_MCARE_POLL_INTERVAL_SECONDS=900
PADDLE_PDX_CACHE_HOME=/opt/motioncare-analysis/model-cache
```

明确禁止 Qiniu AK/SK、DATABASE_URL 和 REDIS_URL。

- [x] **Step 4: 运行全部本地门禁**

Run: `python -m pytest packages/motion_analysis_contract/tests services/pp_mcare/tests -q`

Run: `cd backend && pytest -q && ruff check . && python manage.py makemigrations --check`

Run: `cd frontend && npm run test && npm run lint && npm run build`

Run: `cd miniapp && npm run test && npm run build:weapp && npm run build:h5`

Expected: 所有测试和构建通过；lint 无 error；没有未生成 migration。

- [ ] **Step 5: 先部署业务控制面但保持自动建任务关闭**

生成高熵机器 token；明文只配置到算法服务器的受限环境文件，业务服务器只配置 `PP_MCARE_SERVICE_TOKEN_SHA256`。先部署 migration、内部 API、医生端 API 和前端，设置 `PP_MCARE_AUTO_ENQUEUE_ENABLED=false`，验证无 token 为 403、正确 token 的空队列 claim 为 204，并确认既有训练记录没有被批量补任务。

- [ ] **Step 6: 在独立算法服务器安装候选版本**

先保存当前 `/opt/motioncare-analysis/app` 版本信息，不删除历史 app、模型缓存和脱敏报告。使用明确提交 SHA 生成归档并调用 `install-release.sh`，配置机器 token 后：

```bash
ssh mcare-pp 'sudo systemctl daemon-reload && sudo systemctl enable --now pp-mcare && sudo systemctl status --no-pager pp-mcare'
```

Expected: 服务以 `motioncare-analysis` 用户运行；没有监听业务端口；日志显示启动后立即 claim，空队列后等待 900 秒；此时尚未自动产生新任务。

- [ ] **Step 7: 启用自动建任务并执行真实 90 次视频端到端验收**

在业务服务器设置 `PP_MCARE_AUTO_ENQUEUE_ENABLED=true` 并滚动重启业务进程；只对启用后的新视频创建分析任务，不扫描或重投历史记录。

使用既有 SHA-256 `f4c7b1a4e1a7cdc192b32b73f6cb60600b02446d65f9aa471d34ee71458a78dd` 视频创建非生产训练记录，验证：

```text
decoded_frame_count = inferred_frame_count = 8929
motion_total_count = 90
motion_total_count = motion_standard_count + motion_nonstandard_count
skeleton audio_stream_count = 0
job.status = succeeded
TrainingRecord.motion_result_source = algorithm
/opt/motioncare-analysis/tmp/jobs 为空
Swap 正常任务使用量 = 0
```

再由医生把三项计数修改为合法值，确认同一 `TrainingRecord` 字段被覆盖、来源变成 `doctor`，`MotionAnalysisJob.result_payload` 仍保持原始 90 次结果。

- [ ] **Step 8: 标记 plan/spec 状态并提交最终收口**

把本 plan 完成项全部改为 `[x]`，在顶部增加执行记录和最终 commit；把 spec 状态改为 `implemented`，更新 `docs/superpowers/README.md`，在 changelog 追加实现与远端验收事实。

```bash
git add .github backend frontend miniapp packages services deploy docs/superpowers specs/patient-rehab-system/changelog.md
git commit -m "feat(动作分析): 完成pp-mcare独立计算闭环"
```

## Execution Order and Review Gates

1. Task 1–6 形成可独立测试的业务控制面，审查重点是权限、事务、幂等和不重跑语义。
2. Task 7–11 形成不依赖 Django 的算法 worker，审查重点是全帧、单主体、单次推理、无声骨架和清理。
3. Task 12–13 形成医生端闭环，审查重点是同字段覆盖、状态限制和无手动触发。
4. Task 14 切断旧业务端算法依赖；只有 service 回归测试完整迁移后才能删除旧实现。
5. Task 15 完成发布与真实视频验收；远端部署失败时保持旧 `/opt/motioncare-analysis/app` 可回退，不删除历史报告。
