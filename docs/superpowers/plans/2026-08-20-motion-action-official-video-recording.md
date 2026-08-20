# 五运动动作正式视频与统一录像跟练 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> 状态：approved
> 日期：2026-08-20
> 范围：上传五个正式教学视频，将肩部推举录像链路泛化到全部正式运动动作，并保留审核演示隔离与旧会话兼容。

**Goal:** 五个正式运动动作均使用七牛私有正式教学视频，在微信小程序中完成统一预览、全量录像跟练、分片恢复、训练记录和医生审阅闭环。

**Architecture:** 以固定动作编码到版本化七牛对象 Key 的映射为媒体真相来源，动作库和处方保存 Key 快照，API 动态生成短期 HTTPS 地址。后端录像管线接受五个正式运动动作，小程序抽取通用 `motion-training` 引擎并保留肩部推举旧路由与本地 Key 兼容；AI 分析通过注册表与录像主流程解耦。

**Tech Stack:** Django 5、DRF、PostgreSQL、Celery、FFmpeg/FFprobe、七牛 Kodo、React 18、TypeScript、Taro 4、微信小程序、Vitest、pytest-django。

**Spec:** `docs/superpowers/specs/2026-08-20-motion-action-official-video-recording-design.md`

## Global Constraints

- 正式动作固定为 `motion-aerobic-high-knee`、`motion-balance-sit-stand`、`motion-resistance-row`、`motion-resistance-leg-kickback`、`motion-resistance-shoulder-press`。
- 正式教学视频对象固定使用 `motion-action-videos/v1/<source-key>.mp4`，禁止覆盖内容不同的同版本对象。
- 教学视频存储在现有七牛私有空间；数据库保存对象 Key，API 使用 `https://cdn.whestsun.com` 和 7200 秒 TTL 动态签名。
- 演示视频清单只能签发固定五个 Key，按 IP 每分钟最多 60 次，完整响应缓存 60 秒。
- 所有生效与历史处方动作快照都回填正式 Key，并清除五动作的旧/测试 URL。
- 真实患者五动作统一录像，时长 1–30 分钟、最多 360 个五秒分片、累计与合并结果最多 512 MiB。
- 审核演示五动作统一 10 分钟，可提前结束，但不得录像、生成文件、上传或持久化。
- 本期只有肩部推举注册 AI 分析器；另外四动作只保存录像和训练记录。
- 旧肩部推举页面、`motioncare.pendingShoulderPressSession` 和待上传恢复流程必须保持兼容。
- 示范视频失败不能破坏患者摄像、录像、分片和恢复状态。
- 保留当前工作区中另一会话已完成的未提交改动，实施前先取得用户对检查点提交的明确授权。
- 所有 Git 操作说明和提交信息使用中文；未经用户明确授权不得执行 `git add`、`git commit` 或 `git push`。

---

## File Map

### 后端媒体与处方

| 文件 | 职责 |
| --- | --- |
| `backend/apps/prescriptions/action_library.py` | 五动作集合及正式对象 Key 唯一映射 |
| `backend/apps/prescriptions/models.py` | 动作库对象 Key、处方对象 Key 快照 |
| `backend/apps/prescriptions/migrations/0012_motion_action_video_object_keys.py` | 新字段、五动作和全部历史快照回填、旧 URL 清理 |
| `backend/apps/prescriptions/motion_videos.py` | 白名单校验、教学视频动态签名和清单生成 |
| `backend/apps/prescriptions/motion_video_assets.py` | 本地正式视频 FFprobe、Hash、大小与远端元数据校验 |
| `backend/apps/prescriptions/management/commands/upload_motion_action_videos.py` | 幂等上传五个正式素材 |
| `backend/apps/prescriptions/serializers.py` | 医生端动态 URL、配置状态及正式运动时长上限 |
| `backend/apps/patient_app/views.py` | 患者当前处方动态 URL、演示清单、五动作手工打卡禁用 |
| `backend/apps/patient_app/urls.py` | 注册演示视频清单接口 |

### 后端录像与分析

| 文件 | 职责 |
| --- | --- |
| `backend/apps/training/video_services.py` | 五动作录像资格、累计大小、完成与分析资格 |
| `backend/apps/training/video_tasks.py` | 合并结果 512 MiB 上限 |
| `backend/apps/training/analysis_registry.py` | 动作编码到分析器的唯一注册表 |
| `backend/apps/training/tasks.py` | 根据注册表执行分析器 |
| `backend/apps/training/tracking.py` | 返回 `analysis_available` 与五动作录像状态 |
| `backend/config/settings.py` | 教学视频域名/TTL/限流和 30 分钟录像边界 |

### 管理后台

| 文件 | 职责 |
| --- | --- |
| `frontend/src/pages/prescriptions/types.ts` | 动作视频配置状态类型 |
| `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx` | 根据对象 Key 能力显示已配置视频 |
| `frontend/src/pages/training-tracking/types.ts` | 训练记录 `analysis_available` 类型 |
| `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx` | 仅为已注册动作显示分析入口 |

### 小程序通用引擎

| 文件/目录 | 职责 |
| --- | --- |
| `miniapp/src/features/motion-training/` | 通用会话、录像、上传、缓冲、恢复、计时与画中画 |
| `miniapp/src/pages/motion-training/` | 通用说明、预览、摄像和强制上传页面 |
| `miniapp/src/pages/shoulder-press/` | 旧路由和旧导出兼容包装，不保留业务实现 |
| `miniapp/src/pages/prescription/actionRouting.ts` | 五动作统一路由和“开始跟练”文案 |
| `miniapp/src/demo/data.ts` | 六游戏加五运动动作的本地演示处方 |
| `miniapp/src/demo/motionVideoManifest.ts` | 只读演示清单请求、60 秒内存缓存与 URL 注入 |
| `miniapp/src/demo/patientAppData.ts` | 异步生成带短期正式视频 URL 的演示数据 |
| `miniapp/src/types/patientApp.ts` | `video_unavailable` 类型 |

---

### Task 1: 建立五动作媒体目录与对象 Key 快照

**Files:**
- Modify: `backend/apps/prescriptions/action_library.py`
- Modify: `backend/apps/prescriptions/models.py`
- Create: `backend/apps/prescriptions/migrations/0012_motion_action_video_object_keys.py`
- Modify: `backend/apps/prescriptions/tests/test_motion_action_library.py`

**Interfaces:**
- Produces: `MOTION_ACTION_VIDEO_OBJECT_KEYS: dict[str, str]`、`OFFICIAL_MOTION_ACTION_SOURCE_KEYS: frozenset[str]`、`is_official_motion_action(source_key: str | None) -> bool`。
- Produces: `ActionLibraryItem.video_object_key` 与 `PrescriptionAction.video_object_key_snapshot`。

- [ ] **Step 1: 写入五动作目录、快照复制和回填失败测试**

在 `test_motion_action_library.py` 增加：

```python
from django.apps import apps as django_apps
import importlib

from apps.prescriptions.action_library import (
    MOTION_ACTION_VIDEO_OBJECT_KEYS,
    OFFICIAL_MOTION_ACTION_SOURCE_KEYS,
)


def test_official_motion_video_catalog_is_complete():
    assert OFFICIAL_MOTION_ACTION_SOURCE_KEYS == frozenset(
        MOTION_ACTION_VIDEO_OBJECT_KEYS
    )
    assert set(MOTION_ACTION_VIDEO_OBJECT_KEYS.values()) == {
        f"motion-action-videos/v1/{source_key}.mp4"
        for source_key in OFFICIAL_MOTION_ACTION_SOURCE_KEYS
    }


@pytest.mark.django_db
def test_prescription_snapshot_copies_motion_video_object_key(project_patient, doctor):
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-row")
    action.video_object_key = MOTION_ACTION_VIDEO_OBJECT_KEYS[action.source_key]
    action.save(update_fields=["video_object_key", "updated_at"])
    prescription = project_patient.prescriptions.create(version=19, opened_by=doctor)

    snapshot = prescription.add_action_snapshot(action, duration_minutes=10)

    assert snapshot.video_object_key_snapshot == action.video_object_key


@pytest.mark.django_db
def test_data_migration_replaces_all_official_motion_urls(project_patient, doctor):
    action = ActionLibraryItem.objects.get(source_key="motion-resistance-shoulder-press")
    action.video_url = "https://old.example.com/shoulder.mp4"
    action.video_object_key = ""
    action.save()
    active = project_patient.prescriptions.create(version=20, opened_by=doctor)
    archived = project_patient.prescriptions.create(version=21, opened_by=doctor)
    active_action = active.add_action_snapshot(action, duration_minutes=10)
    archived_action = archived.add_action_snapshot(action, duration_minutes=10)

    migration = importlib.import_module(
        "apps.prescriptions.migrations.0012_motion_action_video_object_keys"
    )
    migration.backfill_motion_action_video_keys(django_apps, None)

    action.refresh_from_db()
    active_action.refresh_from_db()
    archived_action.refresh_from_db()
    expected = MOTION_ACTION_VIDEO_OBJECT_KEYS[action.source_key]
    assert action.video_object_key == expected
    assert action.video_url == ""
    assert active_action.video_object_key_snapshot == expected
    assert archived_action.video_object_key_snapshot == expected
    assert active_action.video_url_snapshot == ""
    assert archived_action.video_url_snapshot == ""
```

- [ ] **Step 2: 运行目标测试并确认失败**

Run: `cd backend && .venv/bin/pytest apps/prescriptions/tests/test_motion_action_library.py -q`

Expected: FAIL，缺少媒体目录常量、模型字段或 `0012` migration。

- [ ] **Step 3: 实现唯一目录、模型字段和数据迁移**

在 `action_library.py` 定义：

```python
MOTION_ACTION_VIDEO_OBJECT_KEYS = {
    source_key: f"motion-action-videos/v1/{source_key}.mp4"
    for source_key in (
        "motion-aerobic-high-knee",
        "motion-balance-sit-stand",
        "motion-resistance-row",
        "motion-resistance-leg-kickback",
        "motion-resistance-shoulder-press",
    )
}
OFFICIAL_MOTION_ACTION_SOURCE_KEYS = frozenset(MOTION_ACTION_VIDEO_OBJECT_KEYS)


def is_official_motion_action(source_key):
    return source_key in OFFICIAL_MOTION_ACTION_SOURCE_KEYS
```

在模型中新增两个 `CharField(max_length=500, blank=True)`，并让 `add_action_snapshot()` 复制对象 Key。`0012` migration 的 `RunPython` 必须逐动作执行：

```python
ActionLibraryItem.objects.filter(source_key=source_key).update(
    video_object_key=object_key,
    video_url="",
)
PrescriptionAction.objects.filter(
    action_library_item__source_key=source_key
).update(
    video_object_key_snapshot=object_key,
    video_url_snapshot="",
)
```

reverse migration 使用 `RunPython.noop`，避免回退时恢复已废弃的长期 URL。

- [ ] **Step 4: 验证 migration 与目标测试**

Run:

```bash
cd backend
.venv/bin/python manage.py makemigrations --check
.venv/bin/pytest apps/prescriptions/tests/test_motion_action_library.py -q
```

Expected: 无待生成 migration，目标测试 PASS。

- [ ] **Step 5: 检查点提交（仅在用户明确授权后）**

```bash
git add backend/apps/prescriptions/action_library.py backend/apps/prescriptions/models.py backend/apps/prescriptions/migrations/0012_motion_action_video_object_keys.py backend/apps/prescriptions/tests/test_motion_action_library.py
git commit -m "feat(处方): 保存正式动作视频对象键"
```

### Task 2: 实现教学视频动态签名服务

**Files:**
- Create: `backend/apps/prescriptions/motion_videos.py`
- Create: `backend/apps/prescriptions/tests/test_motion_videos.py`
- Modify: `backend/config/settings.py`
- Modify: `backend/tests/test_settings.py`

**Interfaces:**
- Consumes: `MOTION_ACTION_VIDEO_OBJECT_KEYS`。
- Produces: `MotionVideoResolution(url: str, unavailable: bool)`。
- Produces: `resolve_motion_video_url(object_key: str, legacy_url: str = "") -> MotionVideoResolution`。
- Produces: `build_demo_motion_video_manifest() -> list[dict[str, str]]`。

- [ ] **Step 1: 写入白名单、HTTPS、TTL 和失败降级测试**

```python
@override_settings(
    QINIU_ACCESS_KEY="ak",
    QINIU_SECRET_KEY="sk",
    MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN="https://cdn.whestsun.com",
    MOTION_ACTION_VIDEO_TOKEN_TTL_SECONDS=7200,
)
def test_motion_video_key_resolves_to_short_lived_https_url(monkeypatch):
    monkeypatch.setattr(
        "apps.prescriptions.motion_videos.private_download_url",
        lambda base_url, expires_at: f"{base_url}?e={expires_at}&token=signed",
    )
    result = resolve_motion_video_url(
        "motion-action-videos/v1/motion-resistance-row.mp4"
    )
    assert result.unavailable is False
    assert result.url.startswith(
        "https://cdn.whestsun.com/motion-action-videos/v1/motion-resistance-row.mp4?"
    )


def test_motion_video_signer_rejects_arbitrary_key():
    result = resolve_motion_video_url("training-videos/private-patient.mp4")
    assert result == MotionVideoResolution(url="", unavailable=True)


@override_settings(MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN="http://insecure.example.com")
def test_motion_video_signer_rejects_non_https_domain():
    result = resolve_motion_video_url(
        "motion-action-videos/v1/motion-resistance-row.mp4"
    )
    assert result.unavailable is True
    assert result.url == ""
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && .venv/bin/pytest apps/prescriptions/tests/test_motion_videos.py backend/tests/test_settings.py -q`

Expected: FAIL，签名服务和配置尚不存在。

- [ ] **Step 3: 实现安全解析结果和清单生成**

```python
@dataclass(frozen=True)
class MotionVideoResolution:
    url: str
    unavailable: bool


def resolve_motion_video_url(object_key: str, legacy_url: str = "") -> MotionVideoResolution:
    if not object_key:
        return MotionVideoResolution(url=legacy_url, unavailable=False)
    if object_key not in MOTION_ACTION_VIDEO_OBJECT_KEYS.values():
        return MotionVideoResolution(url="", unavailable=True)
    domain = settings.MOTION_ACTION_VIDEO_DOWNLOAD_DOMAIN.rstrip("/")
    if urlparse(domain).scheme != "https":
        return MotionVideoResolution(url="", unavailable=True)
    if not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY:
        return MotionVideoResolution(url="", unavailable=True)
    expires_at = int((timezone.now() + timedelta(
        seconds=settings.MOTION_ACTION_VIDEO_TOKEN_TTL_SECONDS
    )).timestamp())
    return MotionVideoResolution(
        url=private_download_url(f"{domain}/{object_key}", expires_at=expires_at),
        unavailable=False,
    )
```

`build_demo_motion_video_manifest()` 遍历固定映射；任一项 `unavailable=True` 时抛出统一 `ValidationError("演示视频暂时不可用")`，不得包含对象 Key 或签名错误原文。

- [ ] **Step 4: 加入精确配置并验证**

在 settings 中加入 7200 秒 TTL、HTTPS 域名、演示限流 `60/min`，并将录像上限配置留给 Task 5。运行：

Run: `cd backend && .venv/bin/pytest apps/prescriptions/tests/test_motion_videos.py backend/tests/test_settings.py -q`

Expected: PASS。

- [ ] **Step 5: 检查点提交（仅在用户明确授权后）**

```bash
git add backend/apps/prescriptions/motion_videos.py backend/apps/prescriptions/tests/test_motion_videos.py backend/config/settings.py backend/tests/test_settings.py
git commit -m "feat(视频): 动态签发正式教学视频地址"
```

### Task 3: 接入医生序列化、患者处方与审核演示清单

**Files:**
- Modify: `backend/apps/prescriptions/serializers.py`
- Modify: `backend/apps/prescriptions/tests/test_motion_action_library.py`
- Modify: `backend/apps/patient_app/views.py`
- Modify: `backend/apps/patient_app/urls.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`

**Interfaces:**
- Consumes: `resolve_motion_video_url()`、`build_demo_motion_video_manifest()`。
- Produces: 兼容字段 `video_url` / `video_url_snapshot`、新字段 `video_configured` / `video_unavailable`。
- Produces: `GET /api/patient-app/demo-motion-videos/`。

- [ ] **Step 1: 写入序列化和清单失败测试**

```python
@pytest.mark.django_db
def test_current_prescription_keeps_business_data_when_video_signing_fails(
    project_patient, doctor, prescription_action, monkeypatch
):
    client = _auth_client(project_patient, doctor)
    monkeypatch.setattr(
        "apps.patient_app.views.resolve_motion_video_url",
        lambda *args, **kwargs: MotionVideoResolution(url="", unavailable=True),
    )
    response = client.get("/api/patient-app/current-prescription/")
    assert response.status_code == 200
    action = response.json()["actions"][0]
    assert action["video_url"] == ""
    assert action["video_unavailable"] is True


@pytest.mark.django_db
def test_demo_motion_manifest_has_no_patient_queries(client, django_assert_num_queries, monkeypatch):
    monkeypatch.setattr(
        "apps.patient_app.views.build_demo_motion_video_manifest",
        lambda: [{"source_key": "motion-resistance-row", "video_url": "https://signed"}],
    )
    with django_assert_num_queries(0):
        response = client.get("/api/patient-app/demo-motion-videos/")
    assert response.status_code == 200
    assert response.json() == {
        "videos": [{"source_key": "motion-resistance-row", "video_url": "https://signed"}]
    }
```

另加测试确认接口不接受 `?object_key=...` 改变结果、签名失败返回不含 token/Key 的 503、缓存 60 秒内只调用一次清单生成器。

- [ ] **Step 2: 运行目标测试并确认失败**

Run: `cd backend && .venv/bin/pytest apps/prescriptions/tests/test_motion_action_library.py apps/patient_app/tests/test_patient_app_api.py -q`

Expected: FAIL，响应字段和演示接口尚不存在。

- [ ] **Step 3: 实现兼容序列化**

将动作库和处方动作的 URL 字段改为 `SerializerMethodField`，调用签名服务；模型原字段仍保留。患者端动作响应使用：

```python
resolution = resolve_motion_video_url(
    action.video_object_key_snapshot,
    action.video_url_snapshot,
)
return {
    # 既有动作字段保持不变
    "video_url": resolution.url,
    "video_unavailable": resolution.unavailable,
}
```

医生端额外返回 `video_configured = bool(video_object_key or legacy_url)`，使动作库徽标不依赖数据库中的旧 URL。

- [ ] **Step 4: 实现只读演示清单**

`DemoMotionVideoManifestView` 使用 `AllowAny`、`ScopedRateThrottle` 和 scope `demo_motion_videos`。以固定 cache key `patient-app:demo-motion-videos:v1` 缓存完整响应 60 秒；异常统一返回：

```python
return Response(
    {"detail": "演示视频暂时不可用，请稍后重试"},
    status=status.HTTP_503_SERVICE_UNAVAILABLE,
)
```

- [ ] **Step 5: 运行目标测试**

Run: `cd backend && .venv/bin/pytest apps/prescriptions/tests/test_motion_action_library.py apps/patient_app/tests/test_patient_app_api.py -q`

Expected: PASS。

- [ ] **Step 6: 检查点提交（仅在用户明确授权后）**

```bash
git add backend/apps/prescriptions/serializers.py backend/apps/prescriptions/tests/test_motion_action_library.py backend/apps/patient_app/views.py backend/apps/patient_app/urls.py backend/apps/patient_app/tests/test_patient_app_api.py
git commit -m "feat(患者端): 返回正式动作视频动态地址"
```

### Task 4: 实现正式素材幂等上传命令

**Files:**
- Create: `backend/apps/prescriptions/motion_video_assets.py`
- Create: `backend/apps/prescriptions/management/__init__.py`
- Create: `backend/apps/prescriptions/management/commands/__init__.py`
- Create: `backend/apps/prescriptions/management/commands/upload_motion_action_videos.py`
- Create: `backend/apps/prescriptions/tests/test_motion_video_upload.py`

**Interfaces:**
- Produces: `MotionAssetProbe(codec, audio_codec, width, height, duration_seconds, size_bytes)`。
- Produces: `UploadedMotionAsset(source_key, object_key, size_bytes, status)`，其中 `status` 仅为 `existing` 或 `uploaded`。
- Produces: `probe_motion_asset(path: Path, ffprobe_path: str) -> MotionAssetProbe`。
- Produces: `upload_motion_action_assets(source_root: Path) -> list[UploadedMotionAsset]`。

- [ ] **Step 1: 写入固定路径、FFprobe 与远端冲突测试**

测试必须覆盖：缺一个文件即在任何上传前失败；非 H.264、非 AAC、非 1080×1920、时长不在 5–120 秒均失败；远端相同 Hash/大小/MIME 幂等成功；远端内容不同失败且不调用上传覆盖。

核心断言：

```python
assert [asset.object_key for asset in uploaded] == list(
    MOTION_ACTION_VIDEO_OBJECT_KEYS.values()
)
upload.assert_not_called()  # 远端五项全部完全一致时
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd backend && .venv/bin/pytest apps/prescriptions/tests/test_motion_video_upload.py -q`

Expected: FAIL，上传模块和命令不存在。

- [ ] **Step 3: 实现 FFprobe 解析与固定文件映射**

使用 `subprocess.run([...], capture_output=True, text=True, timeout=30, check=True)` 获取 JSON。校验逻辑必须精确为：

```python
@dataclass(frozen=True)
class MotionAssetProbe:
    codec: str
    audio_codec: str
    width: int
    height: int
    duration_seconds: float
    size_bytes: int


@dataclass(frozen=True)
class UploadedMotionAsset:
    source_key: str
    object_key: str
    size_bytes: int
    status: Literal["existing", "uploaded"]


if video_codec != "h264" or audio_codec != "aac":
    raise CommandError("正式动作视频编码必须为 H.264 + AAC")
if (width, height) != (1080, 1920):
    raise CommandError("正式动作视频尺寸必须为 1080×1920")
if not 5 <= duration_seconds <= 120:
    raise CommandError("正式动作视频时长必须为 5–120 秒")
```

- [ ] **Step 4: 实现远端幂等校验和命令输出**

先通过 `stat_object_metadata_or_none()` 读取远端；存在时使用 `validate_object_metadata()` 校验本地七牛 ETag、大小和 `video/mp4`。不存在时调用 `upload_local_video()` 上传固定 canonical Key，再次 stat 校验。输出只包含动作编码、Key、字节数和“已存在/已上传”。

命令必须注册 `--check-only` 布尔参数；启用时只执行本地文件与 FFprobe 校验，既不调用七牛 stat，也不调用上传。

- [ ] **Step 5: 运行单元测试与本地只读预检**

Run:

```bash
cd backend
.venv/bin/pytest apps/prescriptions/tests/test_motion_video_upload.py -q
.venv/bin/python manage.py upload_motion_action_videos --source-root ../docs/other/运动处方 --check-only
```

Expected: 测试 PASS；五个本地素材全部通过，`--check-only` 不访问写接口。

- [ ] **Step 6: 检查点提交（仅在用户明确授权后）**

```bash
git add backend/apps/prescriptions/motion_video_assets.py backend/apps/prescriptions/management backend/apps/prescriptions/tests/test_motion_video_upload.py
git commit -m "feat(视频): 增加正式动作素材幂等上传命令"
```

### Task 5: 将后端录像资格扩展到五动作并收紧 30 分钟边界

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/apps/training/video_services.py`
- Modify: `backend/apps/training/video_tasks.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_video_api.py`
- Modify: `backend/apps/training/tests/test_video_tasks.py`

**Interfaces:**
- Consumes: `OFFICIAL_MOTION_ACTION_SOURCE_KEYS`、`is_official_motion_action()`。
- Produces: `_get_current_recordable_motion_action(project_patient, prescription_action_id)`。
- Enforces: 1800 秒、360 分片、536870912 字节。

- [ ] **Step 1: 写入五动作参数化会话与容量失败测试**

```python
@pytest.mark.parametrize("source_key", sorted(OFFICIAL_MOTION_ACTION_SOURCE_KEYS))
@pytest.mark.django_db
def test_every_official_motion_action_can_create_video_session(
    source_key, project_patient, active_prescription
):
    action = ActionLibraryItem.objects.get(source_key=source_key)
    prescription_action = active_prescription.add_action_snapshot(
        action, duration_minutes=10
    )
    video, created = create_training_video_session(
        project_patient=project_patient,
        client_session_id=uuid.uuid4(),
        prescription_action_id=prescription_action.id,
        training_date=timezone.localdate(),
        expected_duration_seconds=600,
        training_started_at=timezone.now(),
    )
    assert created is True
    assert video.prescription_action_id == prescription_action.id
```

另加：1801 秒失败、index 360 失败、累计分片刚好 512 MiB 允许而多 1 字节失败、合并输出多 1 字节失败、非正式 motion 动作失败。

- [ ] **Step 2: 运行目标测试并确认旧肩部推举限制导致失败**

Run: `cd backend && .venv/bin/pytest apps/patient_app/tests/test_patient_app_video_api.py apps/training/tests/test_video_tasks.py -q`

Expected: 另外四动作创建会话失败，容量配置不符合新边界。

- [ ] **Step 3: 泛化录像动作校验**

把 `_get_current_shoulder_action()` 替换为：

```python
def _get_current_recordable_motion_action(project_patient, prescription_action_id):
    active = _active_prescription(project_patient)
    if active is None:
        raise ValidationError("当前无生效处方")
    action = PrescriptionAction.objects.select_related("action_library_item").filter(
        pk=prescription_action_id,
        prescription=active,
    ).first()
    if action is None:
        raise ValidationError("运动计划已更新，请返回当前运动计划重新进入")
    if (
        action.internal_type_snapshot != ActionLibraryItem.InternalType.MOTION
        or not is_official_motion_action(action.action_library_item.source_key)
    ):
        raise ValidationError("当前动作不支持录像上传")
    return active, action
```

- [ ] **Step 4: 实现时长、分片和累计字节三层校验**

settings 设为 1800、360、536870912。接收新分片前聚合已上传 `Sum("size_bytes")`，若加本分片后超过上限则拒绝；finalize 再校验总和；合并完成后在写入 `video.size_bytes` 前拒绝超限结果并进入现有失败/清理流程。

- [ ] **Step 5: 运行录像后端目标测试**

Run: `cd backend && .venv/bin/pytest apps/patient_app/tests/test_patient_app_video_api.py apps/training/tests/test_video_tasks.py -q`

Expected: PASS。

- [ ] **Step 6: 检查点提交（仅在用户明确授权后）**

```bash
git add backend/config/settings.py backend/apps/training/video_services.py backend/apps/training/video_tasks.py backend/apps/patient_app/tests/test_patient_app_video_api.py backend/apps/training/tests/test_video_tasks.py
git commit -m "feat(训练): 支持五动作三十分钟录像"
```

### Task 6: 禁止五动作绕过录像并建立 AI 分析注册表

**Files:**
- Modify: `backend/apps/patient_app/views.py`
- Modify: `backend/apps/prescriptions/serializers.py`
- Create: `backend/apps/training/analysis_registry.py`
- Modify: `backend/apps/training/video_services.py`
- Modify: `backend/apps/training/tasks.py`
- Modify: `backend/apps/training/tracking.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `backend/apps/training/tests/test_motion_analysis.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`

**Interfaces:**
- Produces: `MotionAnalyzer(source_key, algorithm_version, analyze_keypoints)`。
- Produces: `get_motion_analyzer(source_key: str | None) -> MotionAnalyzer | None`、`analysis_available(source_key) -> bool`。
- Produces: 训练追踪记录 `analysis_available: bool`。

- [ ] **Step 1: 写入绕过限制、时长和分析注册失败测试**

测试必须参数化五动作，断言 `POST /api/patient-app/training-records/` 全部返回 400 和“运动动作必须完成录像上传”；处方运动动作 31 分钟返回 400，30 分钟通过；分析注册表只为肩部推举返回 analyzer；其它四动作 `create_analysis_job()` 返回“不支持当前动作分析”；tracking 五动作都有录像字段，但仅肩部推举 `analysis_available=true`。

- [ ] **Step 2: 运行目标测试并确认失败**

Run:

```bash
cd backend
.venv/bin/pytest apps/patient_app/tests/test_patient_app_api.py apps/training/tests/test_motion_analysis.py apps/training/tests/test_tracking_api.py -q
```

Expected: 旧逻辑只拦肩部推举且 tasks 硬编码分析函数。

- [ ] **Step 3: 实现手工提交和处方时长限制**

患者端使用 `is_official_motion_action()` 拦截五动作。`ActivateNowActionSerializer.validate()` 读取 `attrs["action_library_item"]`；正式运动动作 `duration_minutes > 30` 时返回“运动动作时长不能超过 30 分钟”，游戏不受本次新上限影响。

- [ ] **Step 4: 实现单分析器注册表并改造任务**

```python
@dataclass(frozen=True)
class MotionAnalyzer:
    source_key: str
    algorithm_version: str
    analyze_keypoints: Callable[[list], dict]


MOTION_ANALYZERS = {
    "motion-resistance-shoulder-press": MotionAnalyzer(
        source_key="motion-resistance-shoulder-press",
        algorithm_version=PP_TINYPOSE_MODEL_NAME,
        analyze_keypoints=analyze_shoulder_press_keypoints,
    )
}
```

`create_analysis_job()` 根据 source key 获取注册项；`run_motion_analysis_job()` 从 job 的处方动作 source key 获取同一 analyzer，调用 `analyze_keypoints(frames)`，并把 `algorithm_version` 传给 `_persist_success()`。不得改变肩部推举既有结果结构。

- [ ] **Step 5: 在 tracking 返回计算能力并运行测试**

每条 recent record 增加：

```python
"analysis_available": analysis_available(
    record.prescription_action.action_library_item.source_key
),
```

Run: `cd backend && .venv/bin/pytest apps/patient_app/tests/test_patient_app_api.py apps/training/tests/test_motion_analysis.py apps/training/tests/test_tracking_api.py -q`

Expected: PASS。

- [ ] **Step 6: 检查点提交（仅在用户明确授权后）**

```bash
git add backend/apps/patient_app/views.py backend/apps/prescriptions/serializers.py backend/apps/training/analysis_registry.py backend/apps/training/video_services.py backend/apps/training/tasks.py backend/apps/training/tracking.py backend/apps/patient_app/tests/test_patient_app_api.py backend/apps/training/tests/test_motion_analysis.py backend/apps/training/tests/test_tracking_api.py
git commit -m "refactor(分析): 按动作注册录像分析器"
```

### Task 7: 更新管理后台视频配置与分析入口

**Files:**
- Modify: `frontend/src/pages/prescriptions/types.ts`
- Modify: `frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx`
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`
- Modify: `frontend/src/pages/prescriptions/PrescriptionPanel.test.tsx`

**Interfaces:**
- Consumes: `video_configured: boolean`、`analysis_available: boolean`。

- [ ] **Step 1: 写入徽标与分析入口失败测试**

在 tracking 测试构造一条非肩部推举但 `analysis_available=true` 的记录，断言显示分析入口；构造肩部推举但 `analysis_available=false` 的记录，断言不显示。动作库测试数据 `video_url=""`、`video_configured=true` 时仍断言“已配置视频”。

- [ ] **Step 2: 运行目标测试并确认失败**

Run: `cd frontend && npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx src/pages/prescriptions/PrescriptionPanel.test.tsx`

Expected: FAIL，页面仍以肩部推举编码和 `video_url` 判断能力。

- [ ] **Step 3: 改用后端能力字段**

删除 `isShoulderPressRecord()` 对分析按钮的控制，改为：

```ts
const selectedVideoSupportsAnalysis = videoDrawerRecord?.analysis_available === true;
```

动作库徽标使用 `action.video_configured`；保留动态 `video_url` 给需要播放的界面。

- [ ] **Step 4: 运行目标测试、lint 和类型构建**

Run:

```bash
cd frontend
npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx src/pages/prescriptions/PrescriptionPanel.test.tsx
npm run lint
npm run build
```

Expected: 全部 PASS。

- [ ] **Step 5: 检查点提交（仅在用户明确授权后）**

```bash
git add frontend/src/pages/prescriptions/types.ts frontend/src/pages/prescriptions/FixedActionLibraryTab.tsx frontend/src/pages/training-tracking/types.ts frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(管理端): 按能力展示动作视频分析"
```

### Task 8: 建立小程序通用动作目录、路由和旧会话兼容

**Files:**
- Create: `miniapp/src/features/motion-training/catalog.ts`
- Create: `miniapp/src/features/motion-training/action.ts`
- Create: `miniapp/src/features/motion-training/session.ts`
- Modify: `miniapp/src/pages/prescription/actionRouting.ts`
- Modify: `miniapp/src/pages/prescription/actionRouting.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/session.ts`
- Modify: `miniapp/src/types/patientApp.ts`
- Modify: `miniapp/src/pages/shoulder-press/session.test.ts`

**Interfaces:**
- Produces: `OFFICIAL_MOTION_SOURCE_KEYS`、`MotionSourceKey`、`isOfficialMotionSourceKey()`。
- Produces: `resolveMotionTrainingAction(prescription, actionId)`。
- Produces: `buildMotionTrainingGuideUrl()`、`buildMotionTrainingPreviewUrl()`、`buildMotionTrainingCameraUrl()`、`buildMotionTrainingUploadUrl()`。
- Produces: `PENDING_MOTION_TRAINING_SESSION_KEY = "motioncare.pendingMotionTrainingSession"`，兼容读取 `motioncare.pendingShoulderPressSession`。

- [ ] **Step 1: 写入五动作路由和旧 Key 恢复失败测试**

```ts
it.each(OFFICIAL_MOTION_SOURCE_KEYS)('routes %s to motion training', (sourceKey) => {
  expect(actionEntryUrl({ id: 42, source_key: sourceKey, internal_type: 'motion' }))
    .toBe('/pages/motion-training/index?actionId=42')
})

it('migrates the old shoulder session without deleting it early', () => {
  storage.setStorageSync(LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY, pendingSession())
  expect(loadPendingMotionTrainingSession(storage)).toMatchObject({ actionId: 42 })
  expect(storage.getStorageSync(PENDING_MOTION_TRAINING_SESSION_KEY)).toBeTruthy()
  expect(storage.getStorageSync(LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY)).toBeTruthy()
})
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/session.test.ts src/pages/prescription/actionRouting.test.ts`

Expected: FAIL，通用目录、路由和 Key 不存在。

- [ ] **Step 3: 实现通用目录、动作解析与路由**

`catalog.ts` 必须与后端五编码一致，并以 `export type MotionSourceKey = typeof OFFICIAL_MOTION_SOURCE_KEYS[number]` 导出联合类型。`actionEntryUrl()` 对五动作统一返回通用说明页，按钮统一为“开始跟练”；游戏与其它训练保持原路由。

`resolveMotionTrainingAction()` 必须同时校验 actionId、source key 和 `internal_type === 'motion'`。

`CurrentPrescription.actions[].video_unavailable` 定义为可选布尔值 `video_unavailable?: boolean`，兼容升级前写入本地缓存的旧处方响应。

- [ ] **Step 4: 实现旧会话双 Key 兼容**

加载顺序为新 Key 优先、旧 Key 次之。旧 Key 命中时把规范化载荷写入新 Key但不删除旧 Key；成功完成或用户明确放弃时同时清除两个 Key。旧导出通过别名继续可用：

```ts
export const PENDING_SHOULDER_PRESS_SESSION_KEY = LEGACY_PENDING_SHOULDER_PRESS_SESSION_KEY
export const loadPendingShoulderPressSession = loadPendingMotionTrainingSession
```

- [ ] **Step 5: 运行目标测试**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/session.test.ts src/pages/prescription/actionRouting.test.ts`

Expected: PASS。

- [ ] **Step 6: 检查点提交（仅在用户明确授权后）**

```bash
git add miniapp/src/features/motion-training miniapp/src/pages/prescription/actionRouting.ts miniapp/src/types/patientApp.ts miniapp/src/pages/shoulder-press/session.test.ts miniapp/src/pages/prescription/actionRouting.test.ts
git commit -m "refactor(小程序): 建立通用运动跟练会话"
```

### Task 9: 抽取录像、上传、缓冲和画中画通用核心

**Files:**
- Create: `miniapp/src/features/motion-training/api.ts`
- Create: `miniapp/src/features/motion-training/recorder.ts`
- Create: `miniapp/src/features/motion-training/bufferGuard.ts`
- Create: `miniapp/src/features/motion-training/storageGuard.ts`
- Create: `miniapp/src/features/motion-training/localFile.ts`
- Create: `miniapp/src/features/motion-training/workflow.ts`
- Create: `miniapp/src/features/motion-training/pageState.ts`
- Create: `miniapp/src/features/motion-training/alertAudio.ts`
- Create: `miniapp/src/features/motion-training/TrainingOverlay.tsx`
- Create: `miniapp/src/features/motion-training/api.test.ts`
- Create: `miniapp/src/features/motion-training/recorder.test.ts`
- Create: `miniapp/src/features/motion-training/bufferGuard.test.ts`
- Create: `miniapp/src/features/motion-training/storageGuard.test.ts`
- Create: `miniapp/src/features/motion-training/localFile.test.ts`
- Create: `miniapp/src/features/motion-training/workflow.test.ts`
- Create: `miniapp/src/features/motion-training/pageState.test.ts`
- Create: `miniapp/src/features/motion-training/alertAudio.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/api.ts`
- Modify: `miniapp/src/pages/shoulder-press/recorder.ts`
- Modify: `miniapp/src/pages/shoulder-press/bufferGuard.ts`
- Modify: `miniapp/src/pages/shoulder-press/storageGuard.ts`
- Modify: `miniapp/src/pages/shoulder-press/localFile.ts`
- Modify: `miniapp/src/pages/shoulder-press/workflow.ts`
- Modify: `miniapp/src/pages/shoulder-press/pageState.ts`
- Modify: `miniapp/src/pages/shoulder-press/alertAudio.ts`
- Modify: `miniapp/src/pages/shoulder-press/trainingOverlay.tsx`

**Interfaces:**
- Produces generic `MotionTraining*` types/functions matching the existing shoulder pipeline behavior。
- Preserves legacy `ShoulderPress*` aliases only in thin files under `pages/shoulder-press/`。

- [ ] **Step 1: 复制现有纯逻辑测试到通用目录并执行精确符号映射**

使用以下无遗漏映射更新测试和实现：

```text
ShoulderPress -> MotionTraining
shoulderPress -> motionTraining
SHOULDER_PRESS -> MOTION_TRAINING
肩部推举录像 -> 运动录像
/pages/shoulder-press/upload -> /pages/motion-training/upload（新会话）
```

保留动作名称等由 API 返回的真实文案，不做字符串替换。所有既有 API、recorder、buffer、storage、local file、workflow、page state 和 alert audio 测试必须在通用目录运行。

- [ ] **Step 2: 运行迁移后的测试并确认导入失败**

Run: `cd miniapp && npm test -- src/features/motion-training`

Expected: FAIL，通用实现尚未完成或仍存在肩部推举导入。

- [ ] **Step 3: 抽取通用实现并保持行为不变**

以现有已通过测试的肩部推举实现为唯一来源，移动逻辑后只做上述符号和路由泛化。关键常量必须为：

```ts
export const MOTION_TRAINING_SEGMENT_DURATION_MS = 5_000
export const MOTION_TRAINING_HARD_LIMIT_MS = 1_800_000
export const MOTION_TRAINING_RECORDING_STOP_MS = 1_797_000
export const MOTION_TRAINING_BUFFER_HIGH_BYTES = 65 * 1024 * 1024
export const MOTION_TRAINING_BUFFER_LOW_BYTES = 10 * 1024 * 1024
```

`shouldAutoFinishMotionTraining()` 以处方时长或 1,797,000ms 安全截止先到者为准。API 函数使用 `MotionTraining` 命名，但请求路径保持现有后端 `training-video-sessions` 不变。

- [ ] **Step 4: 在旧目录保留薄别名并验证无循环依赖**

旧纯逻辑文件只允许从 `../../features/motion-training/...` 重导出；不得反向让通用模块导入 `pages/shoulder-press`。运行：

```bash
cd miniapp
rg "pages/shoulder-press|../shoulder-press" src/features/motion-training
```

Expected: 无匹配。

- [ ] **Step 5: 运行通用核心与旧测试回归**

Run: `cd miniapp && npm test -- src/features/motion-training src/pages/shoulder-press`

Expected: PASS。

- [ ] **Step 6: 检查点提交（仅在用户明确授权后）**

提交时只 stage 通用目录和本任务改成薄别名的旧纯逻辑文件，提交信息：

```bash
git commit -m "refactor(小程序): 抽取通用运动录像核心"
```

### Task 10: 建立通用说明、预览、摄像与上传页面

**Files:**
- Create: `miniapp/src/pages/motion-training/index.tsx`
- Create: `miniapp/src/pages/motion-training/preview.tsx`
- Create: `miniapp/src/pages/motion-training/camera.tsx`
- Create: `miniapp/src/pages/motion-training/upload.tsx`
- Create: `miniapp/src/pages/motion-training/index.config.ts`
- Create: `miniapp/src/pages/motion-training/preview.config.ts`
- Create: `miniapp/src/pages/motion-training/camera.config.ts`
- Create: `miniapp/src/pages/motion-training/upload.config.ts`
- Modify: `miniapp/src/app.config.ts`
- Modify: `miniapp/src/app.scss`
- Modify: `miniapp/src/pages/shoulder-press/index.tsx`
- Modify: `miniapp/src/pages/shoulder-press/preview.tsx`
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: Task 8/9 的通用动作、路由、会话和录像核心。
- Produces: 四个 `/pages/motion-training/*` 页面；旧肩部推举页面为兼容包装。

- [ ] **Step 1: 将页面测试参数化为五动作**

构造五个 `CurrentPrescription.actions`，逐个断言：处方按钮为“开始跟练”；说明页有“动作预览/开始训练”；预览使用对应 `video_url`；camera 创建对应 actionId 的会话；upload 恢复同一 actionId。视频继续断言 `autoplay/loop/muted/controls=false`。

- [ ] **Step 2: 运行页面测试并确认失败**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/pages.test.tsx`

Expected: 另外四动作仍进入手工训练或被肩部推举 resolver 拒绝。

- [ ] **Step 3: 实现通用说明和预览页**

说明与预览页调用 `fetchCurrentPrescriptionData()` 后使用 `resolveMotionTrainingAction()`。`video_unavailable=true` 或 URL 为空时隐藏预览播放器但保留“开始训练”；视频 onError 触发一次处方刷新，第二次失败显示非阻塞提示。

- [ ] **Step 4: 泛化 camera 与 upload 协调页面**

以现有 shoulder camera/upload 为行为基线，替换为通用 imports 和类型。camera 必须把实际 action 的 `video_url` 传入 `MotionTrainingOverlay`；所有 session、segment、finalize 请求使用当前 actionId。页面不得按 source key 分支，AI 不在小程序录像页执行。

- [ ] **Step 5: 保留旧路由包装并注册新页面**

旧页面默认导出通用页面组件；旧路由参数原样透传。`app.config.ts` 注册四个新页面，同时保留原四个 shoulder 路由。旧 upload 恢复页仍能清理两个本地 Key。

- [ ] **Step 6: 运行页面测试与微信构建**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pages.test.tsx src/features/motion-training
npm run build:weapp
```

Expected: PASS；`dist/app.json` 同时包含新旧路由。

- [ ] **Step 7: 检查点提交（仅在用户明确授权后）**

```bash
git commit -m "feat(小程序): 五动作统一录像跟练页面"
```

### Task 11: 接入五动作审核演示清单与 10 分钟本地体验

**Files:**
- Modify: `miniapp/src/api/client.ts`
- Create: `miniapp/src/demo/motionVideoManifest.ts`
- Modify: `miniapp/src/demo/data.ts`
- Modify: `miniapp/src/demo/patientAppData.ts`
- Create: `miniapp/src/features/motion-training/DemoCamera.tsx`
- Modify: `miniapp/src/pages/motion-training/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/demoCamera.tsx`
- Modify: `miniapp/src/demo/data.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Produces: `publicRequest<T>(path: string) -> Promise<T>`，不附带患者 token且 401 不清理患者会话。
- Produces: `fetchDemoMotionVideoManifest() -> Promise<Record<MotionSourceKey, string>>`，60 秒内存缓存。
- Produces: 五个 duration 10 的演示 motion actions。

- [ ] **Step 1: 写入五动作清单、10 分钟与零副作用测试**

测试固定演示 ID：肩部推举保留 `888807`；高抬腿、坐站、划船、后踢依次使用 `888808`–`888811`。断言五动作 `duration_minutes=10`、每个 URL 来自 manifest、camera `expectedDurationSeconds=600`。

对五动作参数化断言演示 camera 不调用：`createCameraContext`、`createVideoSession`、`uploadVideoSegment`、`finalizeVideoSession`、`setStorageSync(PENDING_MOTION_TRAINING_SESSION_KEY, ...)`。提前结束只显示本地“体验完成”。

- [ ] **Step 2: 运行演示测试并确认失败**

Run: `cd miniapp && npm test -- src/demo/data.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: 当前只有肩部推举、时长 1 分钟且使用长期硬编码 URL。

- [ ] **Step 3: 实现不带患者身份的 publicRequest 与 manifest 缓存**

`publicRequest` 只发送 JSON header，不调用 `patientAuthorizationHeader()`，失败使用安全中性错误。manifest 模块验证响应恰好包含五个唯一 source key 和非空 HTTPS URL；60 秒内复用同一 Promise，失败立即清空缓存以允许重试。

- [ ] **Step 4: 构造五动作演示处方并移除长期 URL**

删除 `DEMO_SHOULDER_PRESS_VIDEO_URL`。`createDemoCurrentPrescription(videoUrls)` 与 `createDemoHomeData(videoUrls)` 接收清单映射；五个 motion action 统一 `duration_minutes: 10`、`weekly_target_count: 1`，视频不可用时设置 `video_url: ''`、`video_unavailable: true`。

- [ ] **Step 5: 将演示 camera 泛化为当前动作**

`DemoCamera.tsx` 从演示处方解析 actionId，把 `action.video_url` 和 600 秒传给通用 overlay。通用 camera 在演示会话下渲染该组件；旧 `shoulder-press/demoCamera.tsx` 只重导出它。保持只渲染 `Camera`、本地计时、后台暂停、权限设置和提前结束，不创建 CameraContext。

- [ ] **Step 6: 运行演示测试和小程序完整测试**

Run:

```bash
cd miniapp
npm test
npm run build:weapp
```

Expected: 全部 PASS，无长期 token 字符串残留：

```bash
rg "token=.*210|IMG_0383_SDR|DEMO_SHOULDER_PRESS_VIDEO_URL" src
```

Expected: 无匹配。

- [ ] **Step 7: 检查点提交（仅在用户明确授权后）**

```bash
git commit -m "feat(小程序): 演示五动作十分钟跟练"
```

### Task 12: 更新决策记录、真实上传与完整验证

**Files:**
- Modify: `docs/superpowers/specs/2026-08-20-motion-action-official-video-recording-design.md`
- Modify: `docs/superpowers/plans/2026-08-20-motion-action-official-video-recording.md`
- Modify: `docs/superpowers/README.md`
- Modify: `specs/patient-rehab-system/open-questions.md`
- Modify: `specs/patient-rehab-system/changelog.md`

**Interfaces:**
- Consumes: Tasks 1–11 的代码、migration、上传命令和构建产物。
- Produces: 五个真实七牛 `v1` 对象、已迁移本地数据和完整验证记录。

- [ ] **Step 1: 更新追加式决策记录**

在 `open-questions.md` 已确认决策表追加 D039：五个正式运动动作统一使用私有正式教学视频和全量录像跟练，真实患者上限 30 分钟，演示为 10 分钟无录像体验，AI 按动作逐步注册。

在 changelog 顶部追加 `0.20 - 2026-08-20`，只追加本次决策，不修改 0.19 及更早条目。README 索引加入本 spec/plan。spec/plan 状态改为 `implementing`，执行记录只在实际 checkpoint commit 存在后填写 short SHA。

- [ ] **Step 2: 运行完整自动化门禁**

Run:

```bash
cd backend && .venv/bin/pytest
cd frontend && npm run test
cd frontend && npm run lint
cd frontend && npm run build
cd miniapp && npm test
cd miniapp && npm run build:weapp
```

Expected: 全部 PASS。

- [ ] **Step 3: 执行真实七牛上传**

此步骤是用户已授权目标内的外部写操作，但执行前再次打印目标 bucket `motioncare` 和五个 canonical Key；不得打印密钥或 token。

Run:

```bash
cd backend
.venv/bin/python manage.py upload_motion_action_videos --source-root ../docs/other/运动处方
```

Expected: 五项均显示“已上传”或“已存在且校验一致”，无冲突。

- [ ] **Step 4: 迁移本地数据库并核对五动作及全部快照**

Run:

```bash
cd backend
.venv/bin/python manage.py migrate
.venv/bin/python manage.py shell -c "from apps.prescriptions.action_library import OFFICIAL_MOTION_ACTION_SOURCE_KEYS as K; from apps.prescriptions.models import ActionLibraryItem, PrescriptionAction; print(ActionLibraryItem.objects.filter(source_key__in=K).exclude(video_object_key='').count()); print(PrescriptionAction.objects.filter(action_library_item__source_key__in=K).exclude(video_object_key_snapshot='').count()); print(ActionLibraryItem.objects.filter(source_key__in=K).exclude(video_url='').count()); print(PrescriptionAction.objects.filter(action_library_item__source_key__in=K).exclude(video_url_snapshot='').count())"
```

Expected: 第一行 `5`；第二行等于全部正式运动处方动作快照数量；第三、四行均为 `0`。

- [ ] **Step 5: 验证五个动态 HTTPS 地址和远端媒体**

通过 Django shell 调用 `build_demo_motion_video_manifest()`，逐 URL 执行 HEAD/GET，断言状态 200、`Content-Type: video/mp4`，再用 FFprobe 验证下载首个对象。日志仅输出 source key、状态、MIME、Content-Length，不输出完整 query/token。

- [ ] **Step 6: 执行静态安全扫描**

Run:

```bash
rg "cdn\.whestsun\.com/.+token=|QINIU_SECRET_KEY\s*=\s*['\"]|IMG_0383_SDR" backend frontend miniapp --glob '!**/node_modules/**'
git diff --check
git status --short
```

Expected: 无硬编码长期签名、密钥或旧肩推源；diff 无空白错误；status 只包含已知保留改动和本计划产物。

- [ ] **Step 7: 记录人工门禁状态**

微信开发者工具、iOS、Android 分别记录五动作首帧、循环预览、Camera+Video 同层、前后台切换、弱网和提前结束结果。未完成的人工项明确列为“待真机验收”，不得报告生产真机已完成。

- [ ] **Step 8: 最终检查点提交（仅在用户明确授权后）**

```bash
git add docs/superpowers/specs/2026-08-20-motion-action-official-video-recording-design.md docs/superpowers/plans/2026-08-20-motion-action-official-video-recording.md docs/superpowers/README.md specs/patient-rehab-system/open-questions.md specs/patient-rehab-system/changelog.md
git commit -m "docs(运动处方): 记录五动作正式视频落地"
```
