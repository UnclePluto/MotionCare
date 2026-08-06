# 训练视频时段穿戴趋势 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让肩部推举视频训练保存手机端开始、结束时间，并在医生端视频抽屉展示该时段内已同步的心率、血压、血氧趋势及心率、血压统计。

**Architecture:** `TrainingVideo` 是一期训练时间的唯一持久化位置；小程序把带手机时区偏移的开始时间写入视频会话创建请求，把结束时间写入完成请求，并在本地待上传清单中保持幂等恢复。医生端通过新的按视频查询接口读取已归属患者的原始穿戴点，由独立查询服务生成趋势与统计，React 抽屉使用独立组件展示可用指标。

**Tech Stack:** Django 5、Django REST Framework、PostgreSQL、pytest-django、Taro 4、React 18、TypeScript、Vitest、TanStack Query v5、Ant Design 5、`@ant-design/charts` 2.6。

## Global Constraints

- 一期只覆盖带视频的肩部推举训练，不修改游戏训练和普通 `TrainingRecord` 的时间模型。
- 训练区间包含暂停时间；视频上传、合并、七牛上传和动作分析耗时不进入区间。
- 开始、结束时间必须来自手机端，服务端不得用接收时间或 `timezone.now()` 补写。
- 手机端时间必须包含明确时区偏移或 `Z`；`training_date` 是开始时间对应的手机本地自然日。
- `training_started_at`、`training_ended_at` 保持可空，历史视频不回填。
- 只读取数据库内已经同步并归属该患者的心率、血压、血氧原始点。
- 不查询、不估算、不展示训练时段步数；不调用厂商接口，不触发主动同步。
- 无完整时间、三类指标全部无数据或请求失败时，整个穿戴区域不渲染。
- 心率和血压统计平均值使用十进制定点 `ROUND_HALF_UP` 保留一位小数；最大、最小、次数保持整数。
- 后端权限复用 `get_training_video_for_user`；前端权限控制不能替代后端访问过滤。
- 保持现有视频分段上传、恢复上传、合并、七牛发布和动作分析行为不变。
- 不新增前端或小程序依赖。

---

## 文件结构与职责

### 后端

- `backend/apps/training/video_models.py`：保存视频训练手机端开始、结束时间。
- `backend/apps/training/migrations/0013_trainingvideo_training_window.py`：以可空字段升级数据库，不回填历史记录。
- `backend/apps/patient_app/serializers.py`：校验带偏移的客户端时间和训练日期。
- `backend/apps/patient_app/views.py`：把序列化后的时间传给视频服务。
- `backend/apps/training/video_services.py`：执行会话幂等、时间窗口和实际录像时长校验。
- `backend/apps/wearables/services/training_windows.py`：按单个训练视频查询原始测量点并构造趋势、统计响应。
- `backend/apps/training/video_views.py`：暴露医生端训练时段穿戴查询。
- `backend/apps/training/urls.py`：注册 `wearable-window` 路由。
- `backend/apps/training/tracking.py`：在 `recent_records` 暴露视频训练开始、结束时间。
- `backend/apps/patient_app/tests/test_patient_app_video_api.py`：覆盖患者端时间写入、幂等和非法时间。
- `backend/apps/training/tests/test_training_video_wearable_api.py`：覆盖区间查询、统计、权限和空数据。
- `backend/apps/training/tests/test_tracking_api.py`：覆盖训练跟踪时间序列化。

### 小程序

- `miniapp/src/pages/shoulder-press/session.ts`：定义本地时间字段、带偏移序列化、首次开始和最终结束的幂等状态迁移。
- `miniapp/src/pages/shoulder-press/camera.tsx`：在录像成功开始、训练完成时持久化手机端时间。
- `miniapp/src/pages/shoulder-press/api.ts`：把开始、结束时间发送到患者端视频 API。
- `miniapp/src/pages/shoulder-press/upload.tsx`：恢复上传时继续提交原结束时间。
- `miniapp/src/pages/shoulder-press/workflow.ts`：保持旧上传编排类型与新时间字段一致。
- `miniapp/src/pages/shoulder-press/session.test.ts`：覆盖时间格式、跨午夜、暂停恢复和旧清单兼容。
- `miniapp/src/pages/shoulder-press/api.test.ts`：覆盖 API 请求体。
- `miniapp/src/pages/shoulder-press/pages.test.tsx`：覆盖录像开始、继续和完成时机。
- `miniapp/src/pages/shoulder-press/workflow.test.ts`：覆盖恢复上传继续使用原时间。

### Web

- `frontend/src/pages/training-tracking/types.ts`：定义训练记录时间和穿戴窗口响应类型。
- `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.ts`：把三类原始点转换为精确时间轴折线配置。
- `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts`：验证单线、血压双线、单位和时间轴。
- `frontend/src/pages/training-tracking/TrainingVideoWearablePanel.tsx`：渲染可用指标页签、趋势图和统计表。
- `frontend/src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx`：验证按数据隐藏页签、行和整块区域。
- `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`：并行查询穿戴窗口、展示训练时段并挂载面板。
- `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`：覆盖抽屉查询、重新打开、无数据和失败不阻断。

---

### Task 1: 后端训练视频时间模型与患者端 API

**Files:**
- Modify: `backend/apps/training/video_models.py:TrainingVideo`
- Create: `backend/apps/training/migrations/0013_trainingvideo_training_window.py`
- Modify: `backend/apps/patient_app/serializers.py:PatientAppTrainingVideoSessionSerializer`
- Modify: `backend/apps/patient_app/serializers.py:PatientAppTrainingVideoFinalizeSerializer`
- Modify: `backend/apps/patient_app/views.py:PatientAppTrainingVideoSessionView`
- Modify: `backend/apps/patient_app/views.py:PatientAppTrainingVideoFinalizeView`
- Modify: `backend/apps/training/video_services.py:create_training_video_session`
- Modify: `backend/apps/training/video_services.py:finalize_training_video_session`
- Test: `backend/apps/patient_app/tests/test_patient_app_video_api.py`

**Interfaces:**
- Consumes: 现有 `client_session_id` 幂等约束、`training_date`、分段时长校验和 `SessionConflict`。
- Produces: `TrainingVideo.training_started_at: datetime | None`、`TrainingVideo.training_ended_at: datetime | None`；`create_training_video_session` 新增关键字参数 `training_started_at=None`，`finalize_training_video_session` 新增关键字参数 `training_ended_at=None`。

- [ ] **Step 1: 写创建会话时间字段的失败测试**

在 `_session_payload` 的默认请求中加入带手机偏移的开始时间，并新增日期、幂等冲突和旧客户端兼容断言：

```python
def _session_payload(action, **overrides):
    return {
        "client_session_id": CLIENT_SESSION_ID,
        "prescription_action": action.id,
        "training_date": "2026-07-11",
        "expected_duration_seconds": 180,
        "training_started_at": "2026-07-11T09:32:14+08:00",
        **overrides,
    }


@pytest.mark.django_db
def test_create_session_saves_client_training_started_at(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    response = _create_session(_auth_client(project_patient, doctor), action)
    video = TrainingVideo.objects.get(pk=response.data["video_id"])

    assert video.training_started_at == datetime(2026, 7, 11, 1, 32, 14, tzinfo=UTC)


@pytest.mark.django_db
def test_create_session_rejects_training_started_at_without_offset(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    response = _auth_client(project_patient, doctor).post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, training_started_at="2026-07-11T09:32:14"),
        format="json",
    )

    assert response.status_code == 400
    assert "时区" in str(response.data)


@pytest.mark.django_db
def test_create_session_rejects_start_date_mismatch(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    response = _auth_client(project_patient, doctor).post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, training_date="2026-07-12"),
        format="json",
    )

    assert response.status_code == 400
    assert "训练日期" in str(response.data)
```

继续加入幂等与旧客户端测试：

```python
@pytest.mark.django_db
def test_create_session_start_time_is_idempotent_and_immutable(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    payload = _session_payload(action)

    first = client.post("/api/patient-app/training-video-sessions/", payload, format="json")
    same = client.post("/api/patient-app/training-video-sessions/", payload, format="json")
    changed = client.post(
        "/api/patient-app/training-video-sessions/",
        _session_payload(action, training_started_at="2026-07-11T09:32:15+08:00"),
        format="json",
    )

    assert first.status_code == 201
    assert same.status_code == 200
    assert changed.status_code == 409
    video = TrainingVideo.objects.get(pk=first.data["video_id"])
    assert video.training_started_at == datetime(2026, 7, 11, 1, 32, 14, tzinfo=UTC)


@pytest.mark.django_db
def test_legacy_client_can_create_session_without_start_time(
    project_patient, doctor, active_prescription
):
    action = _shoulder_press_action(active_prescription)
    payload = _session_payload(action)
    payload.pop("training_started_at")

    response = _auth_client(project_patient, doctor).post(
        "/api/patient-app/training-video-sessions/",
        payload,
        format="json",
    )

    assert response.status_code == 201
    assert TrainingVideo.objects.get(pk=response.data["video_id"]).training_started_at is None
```

- [ ] **Step 2: 运行创建会话测试并确认失败**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_video_api.py \
  -k "training_started_at or start_date_mismatch or create_session_is_idempotent" -v
```

Expected: FAIL，原因是模型和序列化器尚无 `training_started_at`。

- [ ] **Step 3: 添加模型字段和 migration**

在 `TrainingVideo` 的 `training_date` 后加入：

```python
training_started_at = models.DateTimeField("训练开始时间", null=True, blank=True)
training_ended_at = models.DateTimeField("训练结束时间", null=True, blank=True)
```

新增 migration：

```python
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("training", "0012_repair_unbound_qiniu_canonical_keys"),
    ]

    operations = [
        migrations.AddField(
            model_name="trainingvideo",
            name="training_started_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="训练开始时间"),
        ),
        migrations.AddField(
            model_name="trainingvideo",
            name="training_ended_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="训练结束时间"),
        ),
    ]
```

- [ ] **Step 4: 实现带时区字段和开始日期校验**

在 `backend/apps/patient_app/serializers.py` 增加一个只接受显式偏移的字段：

```python
import re
from datetime import datetime

CLIENT_TIMEZONE_SUFFIX = re.compile(r"(?:Z|[+-]\d{2}:\d{2})$")


class ClientOffsetDateTimeField(serializers.DateTimeField):
    default_error_messages = {
        **serializers.DateTimeField.default_error_messages,
        "timezone_required": "训练时间必须包含手机时区。",
    }

    def to_internal_value(self, value):
        if not isinstance(value, str) or not CLIENT_TIMEZONE_SUFFIX.search(value):
            self.fail("timezone_required")
        return super().to_internal_value(value)


def client_local_date(value: str):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
```

扩展创建序列化器：

```python
training_started_at = ClientOffsetDateTimeField(required=False)

def validate(self, attrs):
    raw_started_at = self.initial_data.get("training_started_at")
    if raw_started_at is not None and client_local_date(raw_started_at) != attrs["training_date"]:
        raise serializers.ValidationError(
            {"training_date": "训练日期必须与手机端开始时间一致。"}
        )
    return attrs
```

扩展完成序列化器：

```python
training_ended_at = ClientOffsetDateTimeField(required=False)
```

- [ ] **Step 5: 把开始时间接入创建服务的幂等判断**

扩展 `_ensure_session_payload_matches` 和 `create_training_video_session`：

```python
def _ensure_session_payload_matches(
    video,
    *,
    prescription_action_id,
    training_date,
    expected_duration_seconds,
    training_started_at,
):
    # 保留现有三个字段判断
    if video.training_started_at != training_started_at:
        raise SessionConflict("客户端会话训练开始时间与已创建会话冲突")


def create_training_video_session(
    *,
    project_patient,
    client_session_id,
    prescription_action_id,
    training_date,
    expected_duration_seconds,
    training_started_at=None,
):
    lookup = {
        "project_patient": project_patient,
        "client_session_id": client_session_id,
    }
    active, action = _get_current_shoulder_action(
        project_patient, prescription_action_id
    )
    video = TrainingVideo.objects.create(
        **lookup,
        prescription=active,
        prescription_action=action,
        training_date=training_date,
        expected_duration_seconds=expected_duration_seconds,
        training_started_at=training_started_at,
        status=TrainingVideo.Status.RECORDING,
    )
```

保留现有的“先查已存在会话、运行环境校验、时长上限、`IntegrityError` 竞争赢家恢复”顺序；在两个调用 `_ensure_session_payload_matches` 的分支都传入 `training_started_at`。`PatientAppTrainingVideoSessionView` 使用 `.get("training_started_at")` 传参，避免旧客户端缺字段时抛 `KeyError`。

- [ ] **Step 6: 写完成时间和窗口校验的失败测试**

为 finalize 请求加入结束时间，并覆盖正常、顺序、24 小时、录像时长和幂等冲突：

```python
def _finalize_payload(**overrides):
    return {
        "segment_count": 1,
        "actual_duration_seconds": 60,
        "note": "",
        "training_ended_at": "2026-07-11T09:41:27+08:00",
        **overrides,
    }


@pytest.mark.django_db
def test_finalize_saves_client_training_ended_at(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    response = client.post(_finalize_url(video), _finalize_payload(), format="json")
    video.refresh_from_db()
    assert response.status_code == 202
    assert video.training_ended_at == datetime(2026, 7, 11, 1, 41, 27, tzinfo=UTC)
```

参数化非法请求：

```python
@pytest.mark.parametrize(
    ("ended_at", "expected_fragment"),
    [
        ("2026-07-11T09:32:14+08:00", "晚于"),
        ("2026-07-12T09:32:15+08:00", "24 小时"),
        ("2026-07-11T09:32:30", "时区"),
    ],
)
def test_finalize_rejects_invalid_training_window(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    ended_at,
    expected_fragment,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    response = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at=ended_at),
        format="json",
    )

    assert response.status_code == 400
    assert expected_fragment in str(response.data)
```

用以下测试固定剩余边界：

```python
@pytest.mark.django_db
def test_finalize_rejects_video_duration_longer_than_wall_time(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    response = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at="2026-07-11T09:32:44+08:00"),
        format="json",
    )

    assert response.status_code == 400
    assert "录像时长" in str(response.data)


@pytest.mark.django_db
def test_finalize_end_time_is_idempotent_and_immutable(
    project_patient,
    doctor,
    active_prescription,
    tmp_path,
    django_capture_on_commit_callbacks,
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    session = _create_session(client, action)
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])

    with django_capture_on_commit_callbacks(execute=False):
        first = client.post(_finalize_url(video), _finalize_payload(), format="json")
    same = client.post(_finalize_url(video), _finalize_payload(), format="json")
    changed = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at="2026-07-11T09:41:28+08:00"),
        format="json",
    )

    assert first.status_code == 202
    assert same.status_code == 200
    assert changed.status_code == 409


@pytest.mark.django_db
def test_legacy_session_without_training_window_still_finalizes(
    project_patient, doctor, active_prescription, tmp_path
):
    action = _shoulder_press_action(active_prescription)
    client = _auth_client(project_patient, doctor)
    create_payload = _session_payload(action)
    create_payload.pop("training_started_at")
    session = client.post(
        "/api/patient-app/training-video-sessions/",
        create_payload,
        format="json",
    )
    video = TrainingVideo.objects.get(pk=session.data["video_id"])
    _create_uploaded_segments(video, tmp_path, [60_000])
    finalize_payload = _finalize_payload()
    finalize_payload.pop("training_ended_at")

    response = client.post(_finalize_url(video), finalize_payload, format="json")

    assert response.status_code == 202
    video.refresh_from_db()
    assert video.training_started_at is None
    assert video.training_ended_at is None
```

- [ ] **Step 7: 运行完成时间测试并确认失败**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_video_api.py \
  -k "training_ended_at or training_window or finalize" -v
```

Expected: FAIL，原因是 finalize 尚未接收和校验结束时间。

- [ ] **Step 8: 实现结束时间校验与幂等保存**

在 `video_services.py` 增加：

```python
MAX_TRAINING_WALL_TIME = timedelta(hours=24)
TRAINING_DURATION_TOLERANCE_SECONDS = 5


def _validate_training_window(video, *, training_ended_at, actual_duration_seconds):
    if training_ended_at is None:
        return
    if video.training_started_at is None:
        raise ValidationError("训练开始时间缺失，不能提交训练结束时间")
    wall_time = training_ended_at - video.training_started_at
    if wall_time <= timedelta(0):
        raise ValidationError("训练结束时间必须晚于开始时间")
    if wall_time > MAX_TRAINING_WALL_TIME:
        raise ValidationError("训练时间跨度不能超过 24 小时")
    if actual_duration_seconds > wall_time.total_seconds() + TRAINING_DURATION_TOLERANCE_SECONDS:
        raise ValidationError("实际录像时长不能超过训练时间跨度")
```

把 `training_ended_at` 纳入 `_finalize_payload_matches`，在创建任务前调用校验，并在同一个事务中保存：

```python
video.training_ended_at = training_ended_at
video.save(update_fields=[
    "expected_segment_count",
    "actual_duration_seconds",
    "note",
    "finalized_at",
    "status",
    "failure_reason",
    "training_ended_at",
    "updated_at",
])
```

视图使用 `serializer.validated_data.get("training_ended_at")` 传参。

- [ ] **Step 9: 运行后端时间相关测试与 migration 检查**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_video_api.py -v
python manage.py makemigrations --check
python manage.py migrate --plan
```

Expected: 全部 PASS；`makemigrations --check` 输出 `No changes detected`；迁移计划包含 `training.0013_trainingvideo_training_window`。

- [ ] **Step 10: 提交后端时间模型**

```bash
git add \
  backend/apps/training/video_models.py \
  backend/apps/training/migrations/0013_trainingvideo_training_window.py \
  backend/apps/patient_app/serializers.py \
  backend/apps/patient_app/views.py \
  backend/apps/training/video_services.py \
  backend/apps/patient_app/tests/test_patient_app_video_api.py
git commit -m "feat(training): 记录视频训练手机端时间"
```

---

### Task 2: 小程序本地训练时间状态

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/session.ts`
- Modify: `miniapp/src/pages/shoulder-press/session.test.ts`

**Interfaces:**
- Consumes: `PendingShoulderPressSession` 的本地持久化、冷恢复规范化和旧清单兼容。
- Produces:
  - `clientTrainingMoment(nowMs: number, offsetMinutes?: number): { trainingDate: string; timestamp: string }`
  - `markShoulderPressTrainingStarted(session, nowMs, offsetMinutes?): PendingShoulderPressSession`
  - `markShoulderPressTrainingEnded(session, nowMs, offsetMinutes?): PendingShoulderPressSession`
  - `PendingShoulderPressSession.trainingStartedAt?: string`
  - `PendingShoulderPressSession.trainingEndedAt?: string`

- [ ] **Step 1: 写本地时间格式和状态迁移失败测试**

新增确定性测试，显式传入 UTC+8 的 480 分钟偏移：

```typescript
it('formats the phone instant with an explicit local offset', () => {
  expect(clientTrainingMoment(Date.UTC(2026, 7, 5, 16, 1, 2), 480)).toEqual({
    trainingDate: '2026-08-06',
    timestamp: '2026-08-06T00:01:02+08:00'
  })
})

it('sets the first start once and refreshes a stale pre-midnight training date', () => {
  const session = createPendingShoulderPressSession({
    actionId: 42,
    expectedDurationSeconds: 180,
    trainingDate: '2026-08-05',
    clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
    createdAt: Date.UTC(2026, 7, 5, 15, 59, 0)
  })

  const started = markShoulderPressTrainingStarted(
    session,
    Date.UTC(2026, 7, 5, 16, 1, 2),
    480
  )
  const resumed = markShoulderPressTrainingStarted(
    started,
    Date.UTC(2026, 7, 5, 16, 5, 0),
    480
  )

  expect(started.trainingDate).toBe('2026-08-06')
  expect(started.trainingStartedAt).toBe('2026-08-06T00:01:02+08:00')
  expect(resumed.trainingStartedAt).toBe(started.trainingStartedAt)
})

it('sets the final end once and keeps it through storage recovery', () => {
  const ended = markShoulderPressTrainingEnded(started, endMs, 480)
  savePendingShoulderPressSession(storage, ended)
  expect(loadPendingShoulderPressSession(storage)).toMatchObject({
    trainingStartedAt: '2026-08-06T00:01:02+08:00',
    trainingEndedAt: '2026-08-06T00:09:27+08:00'
  })
})
```

继续加入以下恢复边界：

```typescript
it('rejects ending without a start and rejects a non-increasing end', () => {
  const session = createPendingShoulderPressSession({
    actionId: 42,
    expectedDurationSeconds: 180,
    trainingDate: '2026-08-06',
    clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
    createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
  })
  expect(() => markShoulderPressTrainingEnded(
    session,
    Date.UTC(2026, 7, 5, 16, 9, 27),
    480
  ))
    .toThrow('训练开始时间缺失')
  expect(() => markShoulderPressTrainingEnded({
    ...session,
    trainingStartedAt: '2026-08-06T00:09:27+08:00'
  }, Date.UTC(2026, 7, 5, 16, 1, 2), 480)).toThrow('训练结束时间必须晚于开始时间')
})

it('keeps legacy manifests valid but rejects malformed offset timestamps', () => {
  const legacyManifest = {
    clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
    actionId: 42,
    trainingDate: '2026-08-06',
    expectedDurationSeconds: 180,
    actualDurationMs: 0,
    segments: [],
    finalized: false,
    createdAt: Date.UTC(2026, 7, 5, 16, 0, 0)
  }
  expect(loadPendingShoulderPressSession(memoryStorage(legacyManifest))).not.toBeNull()
  expect(loadPendingShoulderPressSession(memoryStorage({
    ...legacyManifest,
    trainingStartedAt: '2026-08-06T00:01:02'
  }))).toBeNull()
})
```

- [ ] **Step 2: 运行 session 测试并确认失败**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/session.test.ts
```

Expected: FAIL，原因是三个时间辅助函数和本地字段尚不存在。

- [ ] **Step 3: 实现带偏移手机时间格式**

在 `session.ts` 增加：

```typescript
const OFFSET_ISO_PATTERN = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})$/

function twoDigits(value: number): string {
  return String(value).padStart(2, '0')
}

export function clientTrainingMoment(
  nowMs: number,
  offsetMinutes = -new Date(nowMs).getTimezoneOffset()
): { trainingDate: string; timestamp: string } {
  const shifted = new Date(nowMs + offsetMinutes * 60_000)
  const trainingDate = [
    shifted.getUTCFullYear(),
    twoDigits(shifted.getUTCMonth() + 1),
    twoDigits(shifted.getUTCDate())
  ].join('-')
  const localTime = [
    twoDigits(shifted.getUTCHours()),
    twoDigits(shifted.getUTCMinutes()),
    twoDigits(shifted.getUTCSeconds())
  ].join(':')
  const sign = offsetMinutes >= 0 ? '+' : '-'
  const absoluteOffset = Math.abs(offsetMinutes)
  const offset = `${sign}${twoDigits(Math.floor(absoluteOffset / 60))}:${twoDigits(absoluteOffset % 60)}`
  return { trainingDate, timestamp: `${trainingDate}T${localTime}${offset}` }
}
```

- [ ] **Step 4: 实现开始和结束的幂等状态迁移**

扩展会话类型并增加：

```typescript
在现有 `PendingShoulderPressSession` 的 `trainingDate` 后插入：

```typescript
trainingStartedAt?: string
trainingEndedAt?: string
```

export function markShoulderPressTrainingStarted(
  session: PendingShoulderPressSession,
  nowMs: number,
  offsetMinutes?: number
): PendingShoulderPressSession {
  if (session.trainingStartedAt) return session
  const moment = clientTrainingMoment(nowMs, offsetMinutes)
  return {
    ...session,
    trainingDate: moment.trainingDate,
    trainingStartedAt: moment.timestamp
  }
}

export function markShoulderPressTrainingEnded(
  session: PendingShoulderPressSession,
  nowMs: number,
  offsetMinutes?: number
): PendingShoulderPressSession {
  if (!session.trainingStartedAt) throw new Error('训练开始时间缺失，请重新训练')
  if (session.trainingEndedAt) return session
  const moment = clientTrainingMoment(nowMs, offsetMinutes)
  if (Date.parse(moment.timestamp) <= Date.parse(session.trainingStartedAt)) {
    throw new Error('训练结束时间必须晚于开始时间')
  }
  return { ...session, trainingEndedAt: moment.timestamp }
}
```

- [ ] **Step 5: 扩展冷恢复校验并保留旧清单兼容**

`normalizeSession` 使用 `OFFSET_ISO_PATTERN` 校验可选字段：

```typescript
if (
  session.trainingStartedAt !== undefined &&
  (!isNonEmptyString(session.trainingStartedAt) || !OFFSET_ISO_PATTERN.test(session.trainingStartedAt))
) return null
if (
  session.trainingEndedAt !== undefined &&
  (!isNonEmptyString(session.trainingEndedAt) || !OFFSET_ISO_PATTERN.test(session.trainingEndedAt))
) return null
if (session.trainingEndedAt && !session.trainingStartedAt) return null
if (
  session.trainingStartedAt &&
  session.trainingEndedAt &&
  Date.parse(session.trainingEndedAt) <= Date.parse(session.trainingStartedAt)
) return null
```

在规范化返回值中只在字段存在时复制字段。不要把旧清单缺失字段判为损坏。

- [ ] **Step 6: 运行本地会话测试**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/session.test.ts
```

Expected: PASS。

- [ ] **Step 7: 提交小程序时间状态**

```bash
git add \
  miniapp/src/pages/shoulder-press/session.ts \
  miniapp/src/pages/shoulder-press/session.test.ts
git commit -m "feat(miniapp): 持久化肩部训练手机时间"
```

---

### Task 3: 小程序录像与上传链路接入时间字段

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/api.ts`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Modify: `miniapp/src/pages/shoulder-press/workflow.ts`
- Modify: `miniapp/src/pages/shoulder-press/api.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`
- Modify: `miniapp/src/pages/shoulder-press/workflow.test.ts`

**Interfaces:**
- Consumes: Task 2 的 `markShoulderPressTrainingStarted`、`markShoulderPressTrainingEnded` 和两个本地时间字段。
- Produces:
  - `createVideoSession` 输入新增 `trainingStartedAt?: string`
  - `finalizeVideoSession` 输入新增 `trainingEndedAt?: string`
  - 新版录像流程在首次成功开始和最终完成时写入时间，恢复上传原样发送。

- [ ] **Step 1: 写 API 请求体失败测试**

修改 `api.test.ts` 的创建和完成调用：

```typescript
await createVideoSession({
  actionId: 42,
  clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
  trainingDate: '2026-07-11',
  expectedDurationSeconds: 180,
  trainingStartedAt: '2026-07-11T09:32:14+08:00'
})

await finalizeVideoSession({
  videoId: 9,
  segmentCount: 2,
  actualDurationSeconds: 60,
  note: '',
  trainingEndedAt: '2026-07-11T09:41:27+08:00'
})
```

断言请求体增加：

```typescript
training_started_at: '2026-07-11T09:32:14+08:00'
training_ended_at: '2026-07-11T09:41:27+08:00'
```

加入旧调用兼容断言：

```typescript
await createVideoSession({
  actionId: 42,
  clientSessionId: '8cf99c30-9b03-4bda-b4d3-b492f3a2db12',
  trainingDate: '2026-07-11',
  expectedDurationSeconds: 180
})
await finalizeVideoSession({
  videoId: 9,
  segmentCount: 2,
  actualDurationSeconds: 60,
  note: ''
})

expect(taroMock.request.mock.calls.at(-2)?.[0].data)
  .not.toHaveProperty('training_started_at')
expect(taroMock.request.mock.calls.at(-1)?.[0].data)
  .not.toHaveProperty('training_ended_at')
```

- [ ] **Step 2: 运行 API 测试并确认失败**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/api.test.ts
```

Expected: FAIL，请求体尚未包含两个字段。

- [ ] **Step 3: 扩展 API 输入并条件发送时间**

在 `api.ts` 修改输入类型与请求体：

```typescript
export async function createVideoSession(input: {
  actionId: number
  clientSessionId: string
  trainingDate: string
  expectedDurationSeconds: number
  trainingStartedAt?: string
}): Promise<VideoSessionStatus> {
  const response = await request<unknown>('/patient-app/training-video-sessions/', {
    method: 'POST',
    data: {
      prescription_action: input.actionId,
      client_session_id: input.clientSessionId,
      training_date: input.trainingDate,
      expected_duration_seconds: normalizeShoulderPressExpectedDurationSeconds(
        input.expectedDurationSeconds
      ),
      ...(input.trainingStartedAt
        ? { training_started_at: input.trainingStartedAt }
        : {})
    }
  })
  return parseVideoSessionStatus(response, { requireUploadedSegments: true })
}

export async function finalizeVideoSession(input: {
  videoId: number
  segmentCount: number
  actualDurationSeconds: number
  note: string
  trainingEndedAt?: string
}): Promise<VideoSessionStatus> {
  const response = await request<unknown>(
    `/patient-app/training-video-sessions/${input.videoId}/finalize/`,
    {
      method: 'POST',
      data: {
        segment_count: input.segmentCount,
        actual_duration_seconds: input.actualDurationSeconds,
        note: input.note,
        ...(input.trainingEndedAt
          ? { training_ended_at: input.trainingEndedAt }
          : {})
      }
    }
  )
  return parseVideoSessionStatus(response, {
    requireAssemblyJobId: true,
    expectedVideoId: input.videoId
  })
}
```

同步更新文件底部兼容包装函数的参数透传。

- [ ] **Step 4: 写摄像页时间时机失败测试**

在 `pages.test.tsx` 使用 fake timers 固定手机时间，覆盖：

```typescript
it('persists start only after recorder start succeeds and keeps it on resume', async () => {
  vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
  vi.useFakeTimers()
  vi.setSystemTime(new Date('2026-08-06T01:32:14Z'))
  const page = renderPage(ShoulderPressCameraPage)
  await flushPromises()
  page.rerender()
  findFirstByType(page.element, 'Camera').props.onInitDone?.()
  page.rerender()

  findButtonByText(page.element, '开始训练').props.onClick?.()
  await flushPromises()
  const started = taroHarness.storage.get(
    PENDING_SHOULDER_PRESS_SESSION_KEY
  ) as PendingShoulderPressSession
  expect(started.trainingStartedAt).toBe('2026-08-06T09:32:14+08:00')

  await taroHarness.hideCallbacks[0]()
  await flushPromises()
  page.rerender()
  vi.setSystemTime(new Date('2026-08-06T01:35:00Z'))
  findButtonByText(page.element, '继续训练').props.onClick?.()
  await flushPromises()
  const resumed = taroHarness.storage.get(
    PENDING_SHOULDER_PRESS_SESSION_KEY
  ) as PendingShoulderPressSession
  expect(resumed.trainingStartedAt).toBe(started.trainingStartedAt)
})

it('persists end before recorder finalization and upload work', async () => {
  vi.spyOn(Date.prototype, 'getTimezoneOffset').mockReturnValue(-480)
  vi.useFakeTimers()
  const startAt = new Date('2026-08-06T01:32:14Z').valueOf()
  vi.setSystemTime(startAt)
  const page = renderPage(ShoulderPressCameraPage)
  await flushPromises()
  page.rerender()
  findFirstByType(page.element, 'Camera').props.onInitDone?.()
  page.rerender()
  findButtonByText(page.element, '开始训练').props.onClick?.()
  await flushPromises()

  vi.setSystemTime(new Date('2026-08-06T01:41:27Z'))
  page.rerender()
  findButtonByText(page.element, '完成训练').props.onClick?.()
  await flushPromises()

  const ended = taroHarness.storage.get(
    PENDING_SHOULDER_PRESS_SESSION_KEY
  ) as PendingShoulderPressSession
  expect(ended.trainingEndedAt).toBe('2026-08-06T09:41:27+08:00')
})
```

再用两个完整断言固定失败与自动完成入口：

```typescript
recorderHarness.instances[0].start.mockRejectedValueOnce(new Error('camera failed'))
findButtonByText(page.element, '开始训练').props.onClick?.()
await flushPromises()
expect(
  (taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as PendingShoulderPressSession)
    .trainingStartedAt
).toBeUndefined()

vi.setSystemTime(new Date('2026-08-06T02:12:11Z'))
recorderHarness.instances[0].options.onMaxDuration()
await flushPromises()
expect(
  (taroHarness.storage.get(PENDING_SHOULDER_PRESS_SESSION_KEY) as PendingShoulderPressSession)
    .trainingEndedAt
).toBe('2026-08-06T10:12:11+08:00')
```

把这两段分别放入独立 `it`，每个测试按前一个示例完成页面初始化、摄像头 ready 和 fake timer 清理，避免共享状态。

- [ ] **Step 5: 运行摄像页测试并确认失败**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pages.test.tsx
```

Expected: FAIL，摄像页尚未调用 Task 2 的状态迁移。

- [ ] **Step 6: 在首次成功启动和完成入口持久化时间**

`camera.tsx` 导入两个 helper。在 `await recorder.start()` 成功后、设置 recording 状态前：

```typescript
const currentSession = sessionRef.current
if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')
const startedSession = markShoulderPressTrainingStarted(currentSession, Date.now())
saveCurrentSession(startedSession)
```

在 `finishTraining` 通过时长检查后、调用 `recorder.finish()` 前：

```typescript
const currentSession = sessionRef.current
if (!currentSession) throw new Error('训练会话未准备好，请返回处方重新进入')
const endedSession = markShoulderPressTrainingEnded(currentSession, Date.now())
saveCurrentSession(endedSession)
```

继续训练会命中 helper 幂等分支，不覆盖开始时间。自动完成继续调用同一 `finishTraining(true)`，因此使用同一路径。

- [ ] **Step 7: 把本地时间透传到所有上传路径**

在 `camera.tsx` 和 `upload.tsx` 的 `createVideoSession` 调用增加：

```typescript
trainingStartedAt: session.trainingStartedAt
```

在 `upload.tsx` 的 `finalizeVideoSession` 调用增加：

```typescript
trainingEndedAt: session.trainingEndedAt
```

同步扩展 `workflow.ts` 的依赖签名及调用：

```typescript
createVideoSession({
  actionId: session.actionId,
  clientSessionId: session.clientSessionId,
  trainingDate: session.trainingDate,
  expectedDurationSeconds: session.expectedDurationSeconds,
  trainingStartedAt: session.trainingStartedAt
})

finalizeVideoSession({
  videoId: session.videoId,
  segmentCount: session.segments.length,
  actualDurationSeconds: Math.ceil(session.actualDurationMs / 1000),
  note: '',
  trainingEndedAt: session.trainingEndedAt
})
```

- [ ] **Step 8: 更新恢复上传断言并运行小程序目标测试**

在 `workflow.test.ts` 的 `baseSession()` 增加固定开始、结束时间，并断言创建、完成依赖收到同一值；在上传页测试中断言重试不重新生成时间。

Run:

```bash
cd miniapp
npm test -- \
  src/pages/shoulder-press/api.test.ts \
  src/pages/shoulder-press/pages.test.tsx \
  src/pages/shoulder-press/workflow.test.ts
```

Expected: PASS。

- [ ] **Step 9: 构建微信小程序**

Run:

```bash
cd miniapp
npm run build:weapp
```

Expected: 构建成功，无 TypeScript 或 Taro 编译错误。

- [ ] **Step 10: 提交小程序链路**

```bash
git add \
  miniapp/src/pages/shoulder-press/camera.tsx \
  miniapp/src/pages/shoulder-press/api.ts \
  miniapp/src/pages/shoulder-press/upload.tsx \
  miniapp/src/pages/shoulder-press/workflow.ts \
  miniapp/src/pages/shoulder-press/api.test.ts \
  miniapp/src/pages/shoulder-press/pages.test.tsx \
  miniapp/src/pages/shoulder-press/workflow.test.ts
git commit -m "feat(miniapp): 上报视频训练起止时间"
```

---

### Task 4: 后端训练时段穿戴查询与训练跟踪字段

**Files:**
- Create: `backend/apps/wearables/services/training_windows.py`
- Modify: `backend/apps/training/video_views.py`
- Modify: `backend/apps/training/urls.py`
- Modify: `backend/apps/training/tracking.py:recent_records`
- Create: `backend/apps/training/tests/test_training_video_wearable_api.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`

**Interfaces:**
- Consumes: Task 1 的 `TrainingVideo.training_started_at`、`training_ended_at`；现有 `WearableMeasurement` 患者归属；`get_training_video_for_user` 权限边界。
- Produces:
  - `training_video_wearable_window(video: TrainingVideo) -> dict`
  - `GET /api/training/videos/{video_id}/wearable-window/`
  - `TrackingRecentRecord.training_started_at`、`training_ended_at`

- [ ] **Step 1: 写穿戴窗口 API 的失败测试骨架**

新建 `test_training_video_wearable_api.py`，复用现有 `doctor`、`project_patient`、`active_prescription` fixtures，创建带时间的已绑定视频和设备测量点：

```python
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.patients.models import Patient
from apps.training.models import TrainingRecord, TrainingVideo
from apps.training.video_services import SHOULDER_PRESS_SOURCE_KEY
from apps.prescriptions.models import ActionLibraryItem
from apps.wearables.models import (
    WearableBinding,
    WearableDevice,
    WearableMeasurement,
    WearableSyncRun,
)


def _client(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _video(project_patient, active_prescription, *, started_at, ended_at):
    item = ActionLibraryItem.objects.get(source_key=SHOULDER_PRESS_SOURCE_KEY)
    action = active_prescription.actions.filter(action_library_item=item).first()
    if action is None:
        action = active_prescription.add_action_snapshot(
            item,
            weekly_frequency="2 次/周",
            weekly_target_count=2,
            duration_minutes=10,
        )
    record = TrainingRecord.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_date=started_at.astimezone(timezone.get_fixed_timezone(480)).date(),
        status=TrainingRecord.Status.COMPLETED,
        actual_duration_minutes=10,
    )
    return TrainingVideo.objects.create(
        project_patient=project_patient,
        prescription=active_prescription,
        prescription_action=action,
        training_record=record,
        training_date=record.training_date,
        training_started_at=started_at,
        training_ended_at=ended_at,
        object_key=f"training-videos/{project_patient.id}/{uuid.uuid4().hex}.mp4",
        status=TrainingVideo.Status.ATTACHED,
    )


def _bound_device(project_patient, doctor):
    device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="training-window-device",
        identifier_type="device_id",
        model="TEST",
        short_code="2608",
    )
    binding = WearableBinding.objects.create(
        patient=project_patient.patient,
        device=device,
        bound_at=datetime(2026, 8, 1, tzinfo=UTC),
        bound_by=doctor,
    )
    return device, binding


def _other_patient_binding(doctor):
    patient = Patient.objects.create(
        name="穿戴窗口其他患者",
        gender=Patient.Gender.UNKNOWN,
        age=68,
        phone="13900007777",
        primary_doctor=doctor,
    )
    device = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="training-window-other-device",
        identifier_type="device_id",
        model="TEST",
        short_code="2609",
    )
    binding = WearableBinding.objects.create(
        patient=patient,
        device=device,
        bound_at=datetime(2026, 8, 1, tzinfo=UTC),
        bound_by=doctor,
    )
    return patient, device, binding


def _other_doctor():
    return User.objects.create_user(
        phone="13800007777",
        password="pass123456",
        name="无权限医生",
        role=User.Role.DOCTOR,
    )


def _measurement(*, patient, device, binding, metric_type, measured_at, **values):
    return WearableMeasurement.objects.create(
        provider="miwitracker",
        patient=patient,
        device=device,
        binding=binding,
        metric_type=metric_type,
        measured_at=measured_at,
        source_fingerprint=f"{metric_type}-{measured_at.isoformat()}-{values}",
        attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
        raw_payload={},
        **values,
    )
```

核心成功测试创建区间内外测量点并断言：

```python
started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
ended_at = datetime(2026, 8, 6, 1, 41, 27, tzinfo=UTC)
video = _video(
    project_patient,
    active_prescription,
    started_at=started_at,
    ended_at=ended_at,
)
device, binding = _bound_device(project_patient, doctor)
for second, value in [(0, 67), (60, 89), (120, 90), (180, 112)]:
    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at + timedelta(seconds=second),
        heart_rate=value,
    )
for second, systolic, diastolic in [
    (30, 121, 74),
    (90, 126, 78),
    (150, 132, 82),
]:
    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.BLOOD_PRESSURE,
        measured_at=started_at + timedelta(seconds=second),
        systolic=systolic,
        diastolic=diastolic,
    )

response = _client(doctor).get(
    f"/api/training/videos/{video.id}/wearable-window/"
)

assert response.status_code == 200
assert response.data["available"] is True
assert response.data["metrics"]["heart_rate"]["statistics"] == {
    "average": 89.5,
    "maximum": 112,
    "minimum": 67,
    "count": 4,
}
assert response.data["metrics"]["blood_pressure"]["statistics"] == {
    "systolic": {"average": 126.3, "maximum": 132, "minimum": 121},
    "diastolic": {"average": 78.0, "maximum": 82, "minimum": 74},
    "count": 3,
}
assert "statistics" not in response.data["metrics"]["blood_oxygen"]
assert "steps" not in response.data["metrics"]
```

把上方第一个心率点放在开始边界；再创建一个血氧点在结束边界和两个区间外点，断言响应只包含边界内数据：

```python
_measurement(
    patient=project_patient.patient,
    device=device,
    binding=binding,
    metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
    measured_at=ended_at,
    blood_oxygen=97,
)
for measured_at in (started_at - timedelta(microseconds=1), ended_at + timedelta(microseconds=1)):
    _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
        measured_at=measured_at,
        blood_oxygen=95,
    )
boundary_response = _client(doctor).get(
    f"/api/training/videos/{video.id}/wearable-window/"
)
assert boundary_response.data["metrics"]["blood_oxygen"]["points"] == [
    {"measured_at": ended_at.isoformat(), "value": 97}
]
```

最终成功测试可以保留第一次 GET 的统计断言，再用 `boundary_response` 验证新增的血氧边界点。

- [ ] **Step 2: 增加权限、空数据和归属过滤失败测试**

增加以下独立测试和明确断言：

```python
@pytest.mark.parametrize("missing_field", ["training_started_at", "training_ended_at"])
def test_wearable_window_is_unavailable_when_video_time_is_incomplete(
    project_patient, doctor, active_prescription, missing_field
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    setattr(video, missing_field, None)
    video.save(update_fields=[missing_field, "updated_at"])
    response = _client(doctor).get(
        f"/api/training/videos/{video.id}/wearable-window/"
    )
    assert response.status_code == 200
    assert response.data == {"available": False}


def test_wearable_window_filters_invalid_attribution_and_other_patient(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    device, binding = _bound_device(project_patient, doctor)
    outside = _measurement(
        patient=project_patient.patient,
        device=device,
        binding=binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at,
        heart_rate=88,
    )
    outside.attribution_status = WearableMeasurement.AttributionStatus.OUTSIDE_BINDING
    outside.save(update_fields=["attribution_status", "updated_at"])
    other_patient, other_device, other_binding = _other_patient_binding(doctor)
    _measurement(
        patient=other_patient,
        device=other_device,
        binding=other_binding,
        metric_type=WearableMeasurement.MetricType.HEART_RATE,
        measured_at=started_at,
        heart_rate=99,
    )
    response = _client(doctor).get(
        f"/api/training/videos/{video.id}/wearable-window/"
    )
    assert response.data == {"available": False}


def test_wearable_window_is_hidden_from_inaccessible_doctor(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    response = _client(_other_doctor()).get(
        f"/api/training/videos/{video.id}/wearable-window/"
    )
    assert response.status_code == 404


def test_wearable_window_does_not_enqueue_sync(
    project_patient, doctor, active_prescription
):
    started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
    video = _video(
        project_patient,
        active_prescription,
        started_at=started_at,
        ended_at=started_at + timedelta(minutes=10),
    )
    before = WearableSyncRun.objects.count()
    response = _client(doctor).get(
        f"/api/training/videos/{video.id}/wearable-window/"
    )
    assert response.status_code == 200
    assert WearableSyncRun.objects.count() == before
```

另建“只有血氧”“无任何点”“同一 measured_at 的两个心率点”三个测试，核心断言如下：

```python
_measurement(
    patient=project_patient.patient,
    device=device,
    binding=binding,
    metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
    measured_at=started_at,
    blood_oxygen=97,
)
oxygen_response = _client(doctor).get(
    f"/api/training/videos/{video.id}/wearable-window/"
)
assert set(oxygen_response.data["metrics"]) == {"blood_oxygen"}

empty_video = _video(
    project_patient,
    active_prescription,
    started_at=started_at + timedelta(days=1),
    ended_at=started_at + timedelta(days=1, minutes=10),
)
empty_response = _client(doctor).get(
    f"/api/training/videos/{empty_video.id}/wearable-window/"
)
assert empty_response.data == {"available": False}

first = _measurement(
    patient=project_patient.patient,
    device=device,
    binding=binding,
    metric_type=WearableMeasurement.MetricType.HEART_RATE,
    measured_at=started_at + timedelta(seconds=1),
    heart_rate=80,
)
second = _measurement(
    patient=project_patient.patient,
    device=device,
    binding=binding,
    metric_type=WearableMeasurement.MetricType.HEART_RATE,
    measured_at=started_at + timedelta(seconds=1),
    heart_rate=81,
)
ordered_response = _client(doctor).get(
    f"/api/training/videos/{video.id}/wearable-window/"
)
assert first.id < second.id
assert [
    point["value"]
    for point in ordered_response.data["metrics"]["heart_rate"]["points"]
] == [80, 81]
```

三个断言分别放入独立测试；每个测试重新创建自己的视频和绑定。只有血氧测试不要再创建心率点，稳定排序测试不要创建血氧点。

- [ ] **Step 3: 运行新 API 测试并确认失败**

Run:

```bash
cd backend
pytest apps/training/tests/test_training_video_wearable_api.py -v
```

Expected: FAIL，路由和查询服务尚不存在。

- [ ] **Step 4: 实现查询、分组和十进制统计**

新建 `training_windows.py`：

```python
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q

from apps.wearables.models import WearableMeasurement

ONE_DECIMAL = Decimal("0.1")


def _average(values):
    if not values:
        return None
    result = (sum(Decimal(value) for value in values) / Decimal(len(values))).quantize(
        ONE_DECIMAL,
        rounding=ROUND_HALF_UP,
    )
    return float(result)


def _scalar_statistics(values):
    return {
        "average": _average(values),
        "maximum": max(values),
        "minimum": min(values),
        "count": len(values),
    }


def training_video_wearable_window(video):
    if video.training_started_at is None or video.training_ended_at is None:
        return {"available": False}

    points = WearableMeasurement.objects.filter(
        patient_id=video.project_patient.patient_id,
        attribution_status=WearableMeasurement.AttributionStatus.ATTRIBUTED,
        measured_at__gte=video.training_started_at,
        measured_at__lte=video.training_ended_at,
    ).filter(
        Q(metric_type=WearableMeasurement.MetricType.HEART_RATE, heart_rate__isnull=False)
        | Q(
            metric_type=WearableMeasurement.MetricType.BLOOD_PRESSURE,
            systolic__isnull=False,
            diastolic__isnull=False,
        )
        | Q(
            metric_type=WearableMeasurement.MetricType.BLOOD_OXYGEN,
            blood_oxygen__isnull=False,
        )
    ).order_by("measured_at", "id")
```

单次遍历把点分到三个列表；只为非空列表创建指标键。心率使用 `_scalar_statistics`。血压分别收集收缩压、舒张压，复用 `_average`，次数取成对点数量。血氧只返回点。

所有 `measured_at`、开始和结束时间使用 `.isoformat()`；不要返回 `raw_payload`、设备 ID 或 binding ID。

- [ ] **Step 5: 注册权限受控 API**

在 `video_views.py` 增加：

```python
from apps.wearables.services.training_windows import training_video_wearable_window


class TrainingVideoWearableWindowView(APIView):
    permission_classes = [IsAdminOrDoctor]

    def get(self, request, video_id):
        video = get_training_video_for_user(request.user, video_id)
        return Response(training_video_wearable_window(video))
```

在 `training/urls.py` 注册：

```python
path(
    "videos/<int:video_id>/wearable-window/",
    TrainingVideoWearableWindowView.as_view(),
),
```

- [ ] **Step 6: 暴露训练跟踪时间并写失败测试**

在 `test_tracking_api.py` 对有视频的 recent record 断言：

```python
assert row["training_started_at"] == video.training_started_at.isoformat()
assert row["training_ended_at"] == video.training_ended_at.isoformat()
```

对无视频或旧视频断言两个字段为 `None`。

Run:

```bash
cd backend
pytest apps/training/tests/test_tracking_api.py -k "recent_records and training" -v
```

Expected: FAIL，序列化结果尚无字段。

- [ ] **Step 7: 实现训练跟踪时间序列化**

在 `recent_records` 的每一行加入：

```python
"training_started_at": (
    video.training_started_at.isoformat()
    if video and video.training_started_at
    else None
),
"training_ended_at": (
    video.training_ended_at.isoformat()
    if video and video.training_ended_at
    else None
),
```

- [ ] **Step 8: 运行后端穿戴与跟踪测试**

Run:

```bash
cd backend
pytest \
  apps/training/tests/test_training_video_wearable_api.py \
  apps/training/tests/test_tracking_api.py \
  apps/wearables/tests/test_queries_api.py -v
```

Expected: PASS，现有穿戴查询回归不受影响。

- [ ] **Step 9: 提交穿戴窗口后端**

```bash
git add \
  backend/apps/wearables/services/training_windows.py \
  backend/apps/training/video_views.py \
  backend/apps/training/urls.py \
  backend/apps/training/tracking.py \
  backend/apps/training/tests/test_training_video_wearable_api.py \
  backend/apps/training/tests/test_tracking_api.py
git commit -m "feat(wearables): 提供训练视频时段趋势统计"
```

---

### Task 5: Web 穿戴趋势图和统计面板

**Files:**
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Create: `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.ts`
- Create: `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts`
- Create: `frontend/src/pages/training-tracking/TrainingVideoWearablePanel.tsx`
- Create: `frontend/src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx`

**Interfaces:**
- Consumes: Task 4 的 `TrainingVideoWearableWindowResponse` JSON 结构；项目现有上海时间格式化工具和 `@ant-design/charts`。
- Produces:
  - `buildTrainingVideoWearableChartConfig(metric, data)`
  - `<TrainingVideoWearablePanel data={response} />`
  - `TrainingVideoWearableWindowResponse` TypeScript 判别联合。

- [ ] **Step 1: 定义精确响应类型**

在 `types.ts` 增加：

```typescript
export type TrainingVideoHeartRatePoint = {
  measured_at: string;
  value: number;
};

export type TrainingVideoBloodPressurePoint = {
  measured_at: string;
  systolic: number;
  diastolic: number;
};

export type TrainingVideoBloodOxygenPoint = {
  measured_at: string;
  value: number;
};

export type TrainingVideoScalarStatistics = {
  average: number;
  maximum: number;
  minimum: number;
  count: number;
};

export type TrainingVideoWearableWindowResponse =
  | { available: false }
  | {
      available: true;
      training_started_at: string;
      training_ended_at: string;
      metrics: {
        heart_rate?: {
          points: TrainingVideoHeartRatePoint[];
          statistics: TrainingVideoScalarStatistics;
        };
        blood_pressure?: {
          points: TrainingVideoBloodPressurePoint[];
          statistics: {
            systolic: Omit<TrainingVideoScalarStatistics, "count">;
            diastolic: Omit<TrainingVideoScalarStatistics, "count">;
            count: number;
          };
        };
        blood_oxygen?: {
          points: TrainingVideoBloodOxygenPoint[];
        };
      };
    };
```

同时为 `TrackingRecentRecord` 增加两个 `string | null` 时间字段。

在图表配置文件中定义窄化后的可用响应类型，后续函数统一使用它：

```typescript
export type AvailableTrainingVideoWearableWindow = Extract<
  TrainingVideoWearableWindowResponse,
  { available: true }
>;

export type TrainingVideoWearableMetric = keyof
  AvailableTrainingVideoWearableWindow["metrics"];
```

- [ ] **Step 2: 写图表配置失败测试**

新建 `trainingVideoWearableChartConfig.test.ts`：

```typescript
const wearableResponse: AvailableTrainingVideoWearableWindow = {
  available: true,
  training_started_at: "2026-08-06T01:32:14Z",
  training_ended_at: "2026-08-06T01:41:27Z",
  metrics: {
    heart_rate: {
      points: [{ measured_at: "2026-08-06T01:33:00Z", value: 86 }],
      statistics: { average: 86, maximum: 86, minimum: 86, count: 1 },
    },
    blood_pressure: {
      points: [
        {
          measured_at: "2026-08-06T01:34:00Z",
          systolic: 126,
          diastolic: 78,
        },
      ],
      statistics: {
        systolic: { average: 126, maximum: 126, minimum: 126 },
        diastolic: { average: 78, maximum: 78, minimum: 78 },
        count: 1,
      },
    },
    blood_oxygen: {
      points: [{ measured_at: "2026-08-06T01:35:00Z", value: 97 }],
    },
  },
};

it("builds one heart-rate series on the exact training time domain", () => {
  const config = buildTrainingVideoWearableChartConfig(
    "heart_rate",
    wearableResponse,
  );
  expect(config.data).toEqual([
    expect.objectContaining({ series: "心率", value: 86 }),
  ]);
  expect(config.scale?.x?.domainMin).toBe(
    new Date(wearableResponse.training_started_at).valueOf(),
  );
  expect(config.scale?.x?.domainMax).toBe(
    new Date(wearableResponse.training_ended_at).valueOf(),
  );
  expect(config.axis?.y?.title).toBe("次/分");
});

it("builds paired systolic and diastolic series", () => {
  const config = buildTrainingVideoWearableChartConfig(
    "blood_pressure",
    wearableResponse,
  );
  expect(config.data.map((point) => point.series)).toEqual([
    "收缩压",
    "舒张压",
  ]);
  expect(config.legend).toEqual({ color: { title: false } });
  expect(config.axis?.y?.title).toBe("mmHg");
});
```

再覆盖血氧单位 `%` 和上海本地 tooltip 时间。

- [ ] **Step 3: 运行图表配置测试并确认失败**

Run:

```bash
cd frontend
npm run test -- src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts
```

Expected: FAIL，配置模块尚不存在。

- [ ] **Step 4: 实现训练窗口专用图表配置**

创建 `trainingVideoWearableChartConfig.ts`。返回配置包含：

```typescript
function buildMetricPoints(
  metric: TrainingVideoWearableMetric,
  response: AvailableTrainingVideoWearableWindow,
) {
  if (metric === "heart_rate") {
    return (response.metrics.heart_rate?.points ?? []).map((point) => ({
      timestamp: new Date(point.measured_at).valueOf(),
      label: formatShanghaiChartTime(point.measured_at),
      series: "心率",
      value: point.value,
    }));
  }
  if (metric === "blood_pressure") {
    return (response.metrics.blood_pressure?.points ?? []).flatMap((point) => [
      {
        timestamp: new Date(point.measured_at).valueOf(),
        label: formatShanghaiChartTime(point.measured_at),
        series: "收缩压",
        value: point.systolic,
      },
      {
        timestamp: new Date(point.measured_at).valueOf(),
        label: formatShanghaiChartTime(point.measured_at),
        series: "舒张压",
        value: point.diastolic,
      },
    ]);
  }
  return (response.metrics.blood_oxygen?.points ?? []).map((point) => ({
    timestamp: new Date(point.measured_at).valueOf(),
    label: formatShanghaiChartTime(point.measured_at),
    series: "血氧",
    value: point.value,
  }));
}

export function buildTrainingVideoWearableChartConfig(
  metric: TrainingVideoWearableMetric,
  response: AvailableTrainingVideoWearableWindow,
) {
  const unitByMetric = {
    heart_rate: "次/分",
    blood_pressure: "mmHg",
    blood_oxygen: "%",
  } satisfies Record<TrainingVideoWearableMetric, string>;
  const data = buildMetricPoints(metric, response);
  return {
    height: 280,
    data,
    xField: "timestamp",
    yField: "value",
    colorField: metric === "blood_pressure" ? "series" : undefined,
    scale: {
      x: {
        type: "time",
        domainMin: new Date(response.training_started_at).valueOf(),
        domainMax: new Date(response.training_ended_at).valueOf(),
      },
    },
    axis: {
      x: { labelFormatter: (value) => formatShanghaiChartTime(value) },
      y: { title: unitByMetric[metric] },
    },
    legend: metric === "blood_pressure" ? { color: { title: false } } : undefined,
    tooltip: { title: { field: "label" } },
    smooth: true,
  };
}
```

心率、血氧每个点生成单条 series；血压每个原始点展开为“收缩压”和“舒张压”两个同时间点。不要补点、聚合或插值原始数组。

- [ ] **Step 5: 写面板显示规则失败测试**

Mock `@ant-design/charts` 的 `Line` 并新增：

```typescript
const responseWithoutOxygen: TrainingVideoWearableWindowResponse = {
  available: true,
  training_started_at: "2026-08-06T01:32:14Z",
  training_ended_at: "2026-08-06T01:41:27Z",
  metrics: {
    heart_rate: {
      points: [{ measured_at: "2026-08-06T01:33:00Z", value: 86 }],
      statistics: { average: 89.5, maximum: 112, minimum: 67, count: 4 },
    },
    blood_pressure: {
      points: [
        {
          measured_at: "2026-08-06T01:34:00Z",
          systolic: 126,
          diastolic: 78,
        },
      ],
      statistics: {
        systolic: { average: 126.3, maximum: 132, minimum: 121 },
        diastolic: { average: 78, maximum: 82, minimum: 74 },
        count: 3,
      },
    },
  },
};

const oxygenOnlyResponse: TrainingVideoWearableWindowResponse = {
  available: true,
  training_started_at: "2026-08-06T01:32:14Z",
  training_ended_at: "2026-08-06T01:41:27Z",
  metrics: {
    blood_oxygen: {
      points: [{ measured_at: "2026-08-06T01:35:00Z", value: 97 }],
    },
  },
};

it("renders only available metric tabs and heart/blood-pressure statistics", () => {
  render(<TrainingVideoWearablePanel data={responseWithoutOxygen} />);
  expect(screen.getByRole("tab", { name: "心率" })).toBeInTheDocument();
  expect(screen.getByRole("tab", { name: "血压" })).toBeInTheDocument();
  expect(screen.queryByRole("tab", { name: "血氧" })).not.toBeInTheDocument();
  expect(screen.getByText("89.5")).toBeInTheDocument();
  expect(screen.getByText("收缩压")).toBeInTheDocument();
  expect(screen.getByText("舒张压")).toBeInTheDocument();
});

it("renders oxygen trend without a statistics table", () => {
  render(<TrainingVideoWearablePanel data={oxygenOnlyResponse} />);
  expect(screen.getByRole("tab", { name: "血氧" })).toBeInTheDocument();
  expect(screen.queryByText("训练时段统计")).not.toBeInTheDocument();
});

it("renders nothing when the response is unavailable", () => {
  const { container } = render(
    <TrainingVideoWearablePanel data={{ available: false }} />,
  );
  expect(container).toBeEmptyDOMElement();
});
```

- [ ] **Step 6: 运行面板测试并确认失败**

Run:

```bash
cd frontend
npm run test -- src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx
```

Expected: FAIL，面板组件尚不存在。

- [ ] **Step 7: 实现指标页签与统计表**

组件从 `antd` 导入 `Space`、`Table`、`TableColumnsType`、`Tabs`、`Typography`，从 `@ant-design/charts` 导入 `Line`。组件规则：

```typescript
const METRIC_ORDER: TrainingVideoWearableMetric[] = [
  "heart_rate",
  "blood_pressure",
  "blood_oxygen",
];

const METRIC_LABEL: Record<TrainingVideoWearableMetric, string> = {
  heart_rate: "心率",
  blood_pressure: "血压",
  blood_oxygen: "血氧",
};

type StatisticRow = {
  metric: "heart_rate" | "systolic" | "diastolic";
  label: string;
  average: number;
  maximum: number;
  minimum: number;
  count: number;
};

function buildStatisticRows(
  metrics: AvailableTrainingVideoWearableWindow["metrics"],
): StatisticRow[] {
  const rows: StatisticRow[] = [];
  if (metrics.heart_rate) {
    rows.push({
      metric: "heart_rate",
      label: "心率（次/分）",
      ...metrics.heart_rate.statistics,
    });
  }
  if (metrics.blood_pressure) {
    rows.push({
      metric: "systolic",
      label: "收缩压（mmHg）",
      ...metrics.blood_pressure.statistics.systolic,
      count: metrics.blood_pressure.statistics.count,
    });
    rows.push({
      metric: "diastolic",
      label: "舒张压（mmHg）",
      ...metrics.blood_pressure.statistics.diastolic,
      count: metrics.blood_pressure.statistics.count,
    });
  }
  return rows;
}

const STATISTIC_COLUMNS: TableColumnsType<StatisticRow> = [
  { title: "指标", dataIndex: "label" },
  { title: "平均", dataIndex: "average" },
  { title: "最高", dataIndex: "maximum" },
  { title: "最低", dataIndex: "minimum" },
  { title: "测量次数", dataIndex: "count" },
];

export function TrainingVideoWearablePanel({ data }: Props) {
  if (!data?.available) return null;

  const metricTabs = METRIC_ORDER.flatMap((metric) =>
    data.metrics[metric]
      ? [{
          key: metric,
          label: METRIC_LABEL[metric],
          children: (
            <Line
              {...buildTrainingVideoWearableChartConfig(metric, data)}
            />
          ),
        }]
      : [],
  );
  if (metricTabs.length === 0) return null;

  const rows = buildStatisticRows(data.metrics);
  return (
    <Space direction="vertical" size={12} style={{ width: "100%" }}>
      <Typography.Title level={5}>训练时段穿戴趋势</Typography.Title>
      <Tabs items={metricTabs} />
      {rows.length > 0 ? (
        <>
          <Typography.Title level={5}>训练时段统计</Typography.Title>
          <Table rowKey="metric" columns={STATISTIC_COLUMNS} dataSource={rows} pagination={false} size="small" />
        </>
      ) : null}
    </Space>
  );
}
```

统计行顺序固定为心率、收缩压、舒张压。平均值使用后端一位小数结果；最大、最小、次数直接显示整数；血压两行复用相同 count。

- [ ] **Step 8: 运行前端组件测试**

Run:

```bash
cd frontend
npm run test -- \
  src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts \
  src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx
```

Expected: PASS。

- [ ] **Step 9: 提交趋势组件**

```bash
git add \
  frontend/src/pages/training-tracking/types.ts \
  frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.ts \
  frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts \
  frontend/src/pages/training-tracking/TrainingVideoWearablePanel.tsx \
  frontend/src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx
git commit -m "feat(frontend): 新增训练时段穿戴趋势面板"
```

---

### Task 6: 视频抽屉查询与展示集成

**Files:**
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

**Interfaces:**
- Consumes: Task 4 的 API 和 tracking 时间字段；Task 5 的 `TrainingVideoWearablePanel`。
- Produces: 每次打开视频抽屉并行查询穿戴数据；训练时段描述；无数据和失败静默隐藏。

- [ ] **Step 1: 写成功查询和训练时段显示失败测试**

在页面 API mock 中增加：

```typescript
const wearableWindowResponse: TrainingVideoWearableWindowResponse = {
  available: true,
  training_started_at: "2026-08-06T01:32:14Z",
  training_ended_at: "2026-08-06T01:41:27Z",
  metrics: {
    heart_rate: {
      points: [{ measured_at: "2026-08-06T01:33:00Z", value: 86 }],
      statistics: { average: 86, maximum: 86, minimum: 86, count: 1 },
    },
  },
};

if (url === "/training/videos/8101/wearable-window/") {
  return Promise.resolve({ data: wearableWindowResponse });
}
```

打开视频抽屉后断言：

```typescript
await waitFor(() => {
  expect(mockGet).toHaveBeenCalledWith(
    "/training/videos/8101/wearable-window/",
  );
});
expect(screen.getByText("训练时段")).toBeInTheDocument();
expect(screen.getByText("09:32:14–09:41:27")).toBeInTheDocument();
expect(screen.getByText("训练时段穿戴趋势")).toBeInTheDocument();
```

使用 `Asia/Shanghai` 时间格式断言，不直接截取 ISO 字符串。

再把同一记录改为跨午夜窗口并断言两端日期：

```typescript
const overnightDetail = structuredClone(trackingDetail);
overnightDetail.recent_records[0].training_started_at =
  "2026-08-06T15:58:00Z";
overnightDetail.recent_records[0].training_ended_at =
  "2026-08-06T16:05:00Z";
expect(screen.getByText("08-06 23:58:00–08-07 00:05:00"))
  .toBeInTheDocument();
```

该断言放入独立测试，并让 tracking detail mock 返回 `overnightDetail` 后再打开视频抽屉。

- [ ] **Step 2: 写无数据、失败和重新打开失败测试**

增加：

```typescript
function videoDrawerGet(
  url: string,
  wearableResult: TrainingVideoWearableWindowResponse | Error =
    wearableWindowResponse,
) {
  if (url === "/training/tracking/patients/201/") {
    return Promise.resolve({ data: trackingDetail });
  }
  if (url === "/training/videos/8101/download-url/") {
    return Promise.resolve({ data: { url: "https://cdn.example.com/video.mp4" } });
  }
  if (url === "/training/videos/8101/analysis-jobs/latest/") {
    return Promise.resolve({ data: null });
  }
  if (url === "/training/videos/8101/wearable-window/") {
    return wearableResult instanceof Error
      ? Promise.reject(wearableResult)
      : Promise.resolve({ data: wearableResult });
  }
  return Promise.reject(new Error(`unexpected GET ${url}`));
}

it("hides the wearable section when the endpoint is unavailable", async () => {
  mockGet.mockImplementation((url: string) =>
    videoDrawerGet(url, { available: false }),
  );
  renderAt("/training-tracking/patients/201");
  fireEvent.click(await screen.findByRole("button", { name: "播放训练视频" }));
  expect(screen.queryByText("训练时段穿戴趋势")).not.toBeInTheDocument();
});

it("keeps video and analysis visible when wearable loading fails", async () => {
  mockGet.mockImplementation((url: string) =>
    videoDrawerGet(url, new Error("wearable failed")),
  );
  renderAt("/training-tracking/patients/201");
  fireEvent.click(await screen.findByRole("button", { name: "播放训练视频" }));
  expect(screen.getByLabelText("训练视频播放器")).toBeInTheDocument();
  expect(screen.getByText("动作分析")).toBeInTheDocument();
  expect(screen.queryByText("wearable failed")).not.toBeInTheDocument();
});

it("refetches wearable data when the same video drawer is reopened", async () => {
  mockGet.mockImplementation((url: string) => videoDrawerGet(url));
  renderAt("/training-tracking/patients/201");
  fireEvent.click(await screen.findByRole("button", { name: "播放训练视频" }));
  fireEvent.click(await screen.findByRole("button", { name: /Close|关闭/ }));
  fireEvent.click(await screen.findByRole("button", { name: "播放训练视频" }));
  await waitFor(() => {
    expect(
      mockGet.mock.calls.filter(
        ([url]) => url === "/training/videos/8101/wearable-window/",
      ),
    ).toHaveLength(2);
  });
});
```

另加旧视频两个时间为 `null` 的测试：复制 `trackingDetail`，把第一条记录的 `training_started_at`、`training_ended_at` 设为 `null`，让 `videoDrawerGet` 返回该副本；打开抽屉后断言 `screen.queryByText("训练时段")` 为 `null`。

- [ ] **Step 3: 运行抽屉测试并确认失败**

Run:

```bash
cd frontend
npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

Expected: FAIL，页面尚未查询或挂载穿戴面板。

- [ ] **Step 4: 增加训练时间格式化**

在页面局部增加纯函数：

```typescript
function formatTrainingWindow(
  startedAt: string | null,
  endedAt: string | null,
): string | null {
  if (!startedAt || !endedAt) return null;
  const start = inShanghai(startedAt);
  const end = inShanghai(endedAt);
  if (start.isSame(end, "day")) {
    return `${start.format("HH:mm:ss")}–${end.format("HH:mm:ss")}`;
  }
  return `${start.format("MM-DD HH:mm:ss")}–${end.format("MM-DD HH:mm:ss")}`;
}
```

构造 `Descriptions.items` 时只在结果非空时加入训练时段项。

- [ ] **Step 5: 增加按抽屉启用的 TanStack Query**

```typescript
const wearableWindowQuery = useQuery({
  queryKey: ["training-video-wearable-window", selectedVideoId],
  queryFn: async () => {
    const response = await apiClient.get<TrainingVideoWearableWindowResponse>(
      `/training/videos/${selectedVideoId}/wearable-window/`,
    );
    return response.data;
  },
  enabled: drawerOpen && selectedVideoId != null,
  staleTime: 0,
  refetchOnMount: "always",
});
```

关闭抽屉时不显示、不中断现有视频卸载逻辑；重新打开相同视频时必须重新请求。查询错误不渲染 `Alert`。

- [ ] **Step 6: 在动作分析下方挂载面板**

在现有动作分析块之后加入：

```tsx
{wearableWindowQuery.data?.available ? (
  <TrainingVideoWearablePanel data={wearableWindowQuery.data} />
) : null}
```

同时给现有 `<video>` 增加 `aria-label="训练视频播放器"`，与页面测试和键盘辅助技术保持一致。

加载期间不显示 skeleton 或固定高度占位；失败时保持 `null`。

- [ ] **Step 7: 运行页面测试、lint 和构建**

Run:

```bash
cd frontend
npm run test -- src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
npm run lint
npm run build
```

Expected: 全部 PASS。

- [ ] **Step 8: 提交视频抽屉集成**

```bash
git add \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(frontend): 在视频抽屉展示穿戴趋势"
```

---

### Task 7: 全量回归、实施记录与交付收口

**Files:**
- Modify: `docs/superpowers/plans/2026-08-06-training-video-wearable-window.md`
- Modify: `docs/superpowers/specs/2026-08-06-training-video-wearable-window-design.md`
- Modify: `specs/patient-rehab-system/changelog.md`

**Interfaces:**
- Consumes: Tasks 1–6 的完整端到端实现。
- Produces: 全量测试证据、已完成计划勾选、设计状态和追加式变更日志。

- [ ] **Step 1: 运行完整后端测试**

Run:

```bash
cd backend
pytest
```

Expected: 全部 PASS，无新增 warning 或失败。

- [ ] **Step 2: 运行完整前端验证**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: 全部 PASS。

- [ ] **Step 3: 运行完整小程序验证**

Run:

```bash
cd miniapp
npm test
npm run build:weapp
```

Expected: 全部 PASS，微信小程序构建成功。

- [ ] **Step 4: 验证数据库迁移和工作区差异**

Run:

```bash
cd backend
python manage.py makemigrations --check
python manage.py migrate --plan
cd ..
git diff --check
git status --short
```

Expected: 无遗漏 migration、无空白错误；工作区只包含本任务计划的文档收口改动。

- [ ] **Step 5: 更新实施记录**

在 plan 顶部状态区之后追加逐任务记录，格式固定：

```text
执行记录（2026-08-06, codex）：Task 1–6 已落地，提交哈希按下方 `git log` 输出顺序记录；全量验证通过。
```

先运行：

```bash
git log --reverse --format="%h %s" fa56cf3..HEAD
```

把输出中 Task 1–6 的六个实际短哈希和提交标题逐项复制到执行记录下一行。把所有已完成复选框改为 `- [x]`。把设计文档头部状态从 `approved` 更新为 `implemented`，并把 `实施基线 commit` 更新为 Task 6 的实际短哈希。

在 `specs/patient-rehab-system/changelog.md` 末尾追加一条，不修改历史条目：

```markdown
- 2026-08-06：肩部推举视频训练记录手机端开始/结束时间；医生端视频抽屉按训练时段展示已同步的心率、血压、血氧趋势及心率、血压统计；步数和主动同步不在一期范围。
```

- [ ] **Step 6: 提交文档收口**

```bash
git add \
  docs/superpowers/plans/2026-08-06-training-video-wearable-window.md \
  docs/superpowers/specs/2026-08-06-training-video-wearable-window-design.md \
  specs/patient-rehab-system/changelog.md
git commit -m "docs(training): 记录训练时段穿戴趋势实施结果"
```

- [ ] **Step 7: 最终确认提交历史与工作区**

Run:

```bash
git log --oneline --decorate -8
git status --short --branch
```

Expected: 最近提交依次包含后端时间、小程序时间状态、小程序上传、穿戴查询、前端面板、抽屉集成和文档收口；工作区干净。
