# 训练视频固定健康观察窗口 Implementation Plan

> 状态：implemented
> 日期：2026-08-07
> 范围：以手机端首次录像开始时间和处方时长快照计算固定健康观察窗口，并将实际完成时间降级为可选审计字段
> 关联：`docs/superpowers/specs/2026-08-07-training-video-fixed-health-window-design.md`
> 实施基线 commit：`f9324f8`

执行记录（2026-08-07, codex）：

- Task 1「收敛后端视频开始/结束时间契约」落地于 commit `1f624a1`。
- Task 2「用处方时长快照计算固定健康观察窗口」落地于 commit `12b8e4e`。
- Task 3「让小程序强制上报开始时间并容忍结束时间缺失」落地于 commit `1f75ab0`。
- Task 4「医生端改用固定健康观察窗口」落地于 commit `036cf79`。
- Task 5「全量验证并更新实施记录」落地于 commit `c8ec3a2`。
- 全量验证：Django 无待生成迁移，复杂状态机扫描零匹配；后端 `670 passed`；医生端 `37` 个测试文件、`239 passed`，lint `0 errors / 4 warnings`，生产构建成功；小程序 `23` 个测试文件、`271 passed`，注入正式 HTTPS API 地址后微信生产构建成功。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让训练视频以手机端第一次录像成功时间为起点、以“处方时长快照 + 300 秒”为固定健康观察窗口；正常完成时间可以上传但允许缺失，且不再影响健康图表。

**Architecture:** 小程序只负责在第一次录像成功后持久化开始时间，并在正常点击完成时尽力记录结束时间；视频上传流程继续复用现有简单待上传会话，不新增状态机。后端把开始时间和处方时长快照作为健康窗口的唯一输入，穿戴接口计算并返回明确的窗口字段；医生 Web 端只信任该接口的窗口，不再依赖训练记录中的实际结束时间。

**Tech Stack:** Django 5、Django REST Framework、PostgreSQL、pytest-django、Taro 4、React 18、TypeScript、Vitest、TanStack Query v5、Ant Design 5、`@ant-design/charts` 2.6。

## Global Constraints

- `training_started_at` 必须来自手机端第一次 `recorder.start()` 成功之后；暂停、继续、上传重试不得修改。
- 新建视频会话 API 必须提交 `training_started_at`，并继续校验其手机本地日期等于 `training_date`。
- 数据库字段继续可空，不新增迁移；可空只用于异常/旧 mock 数据的安全读取，不代表新版创建 API 可以省略。
- `training_ended_at` 保持可空，仅作为正常点击完成时的审计字段；医生端不展示，也不参与健康窗口。
- 非空 `training_ended_at` 只校验晚于 `training_started_at`；不得再与实际录像时长或 24 小时上限耦合。
- 健康窗口必须由后端统一计算：`training_started_at` 至 `training_started_at + expected_duration_seconds + 300 秒`。
- `expected_duration_seconds` 使用视频会话创建时保存的处方时长快照；后续处方修改不得改变既有窗口。
- 穿戴测量点继续使用闭区间过滤；患者归属、指标有效性、权限和统计舍入规则保持不变。
- 一期只展示心率、血压、血氧；步数只有自然日总量，不查询、不估算、不展示为训练时段趋势。
- 缺少开始时间、处方时长为空或不大于 0 时，穿戴接口返回 `{"available": false}`。
- 穿戴接口无有效测量点、请求失败或返回不可用时，医生端静默隐藏健康图表，不影响视频和动作分析。
- 不引入 Manifest V2、录像 phase、生命周期恢复、CAS 合并、后台补写或新的前后端依赖。
- 不迁移历史本地清单和 mock 数据；缺少开始时间的本地会话不得创建新的远端视频会话。
- 保留现有分段校验、串行上传、合并、七牛发布、动作分析和权限逻辑。

---

## 文件结构与职责

### 后端视频时间

- `backend/apps/patient_app/serializers.py`：要求创建会话提供带时区的开始时间；完成时间继续可选。
- `backend/apps/patient_app/views.py`：把必填开始时间和可选结束时间传给视频服务。
- `backend/apps/training/video_services.py`：保持创建幂等；把结束时间校验收敛为“非空且晚于开始时间”。
- `backend/apps/patient_app/tests/test_patient_app_video_api.py`：覆盖必填开始时间、可选结束时间、幂等及解耦校验。
- `backend/apps/training/tests/test_video_session_models.py`：为直接调用创建服务的测试补齐开始时间。
- `backend/apps/training/tests/test_video_segment_concurrency.py`：为并发创建服务测试补齐固定开始时间。

### 后端健康窗口

- `backend/apps/wearables/services/training_windows.py`：计算固定窗口、按闭区间查询，并返回新的窗口响应字段。
- `backend/apps/training/tests/test_training_video_wearable_api.py`：覆盖公式、边界、结束时间无关性、不可用条件、统计和权限。

### 微信小程序

- `miniapp/src/pages/shoulder-press/session.ts`：保留简单待上传会话，并提供读取必需开始时间的单一守卫。
- `miniapp/src/pages/shoulder-press/api.ts`：创建会话请求类型要求开始时间；完成请求继续按可选字段发送结束时间。
- `miniapp/src/pages/shoulder-press/workflow.ts`：创建远端会话前拒绝缺少开始时间的本地数据；结束时间缺失不阻断 finalize。
- `miniapp/src/pages/shoulder-press/camera.tsx`：后台创建远端会话前使用同一开始时间守卫；保留首次录像成功后记录时间的现有顺序。
- `miniapp/src/pages/shoulder-press/upload.tsx`：恢复上传创建远端会话时使用同一开始时间守卫。
- `miniapp/src/pages/shoulder-press/session.test.ts`：覆盖开始时间守卫、首次写入和暂停继续不变。
- `miniapp/src/pages/shoulder-press/api.test.ts`：覆盖创建请求必含开始时间、finalize 可省略结束时间。
- `miniapp/src/pages/shoulder-press/workflow.test.ts`：覆盖缺少开始时间停止创建、缺少结束时间仍可完成。
- `miniapp/src/pages/shoulder-press/pages.test.tsx`：回归录像启动失败不写时间、首次成功写入、继续录像不改值。

### 医生 Web

- `frontend/src/pages/training-tracking/types.ts`：把可用穿戴响应改为固定窗口字段。
- `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.ts`：图表横轴改用固定窗口。
- `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts`：锁定横轴起止值。
- `frontend/src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx`：更新可用响应 fixture 并回归趋势、统计。
- `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`：只按抽屉和视频 ID 发起穿戴查询，不再要求实际结束时间；移除实际训练时段展示。
- `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`：覆盖实际结束时间为空仍查询、接口不可用时隐藏、抽屉不展示实际结束时间。

---

### Task 1: 收敛后端视频开始/结束时间契约

**Files:**
- Modify: `backend/apps/patient_app/tests/test_patient_app_video_api.py`
- Modify: `backend/apps/training/tests/test_video_session_models.py`
- Modify: `backend/apps/training/tests/test_video_segment_concurrency.py`
- Modify: `backend/apps/patient_app/serializers.py:PatientAppTrainingVideoSessionSerializer`
- Modify: `backend/apps/patient_app/views.py:PatientAppTrainingVideoSessionView`
- Modify: `backend/apps/training/video_services.py:create_training_video_session`
- Modify: `backend/apps/training/video_services.py:_validate_training_window`

**Interfaces:**
- `POST /api/patient-app/training-video-sessions/`：`training_started_at` 从可选改为必填。
- `POST /api/patient-app/training-video-sessions/{video_id}/finalize/`：`training_ended_at` 继续可选。
- `create_training_video_session` 的 `training_started_at`：移除参数默认值；所有调用者必须明确传入。
- finalize 幂等：第一次成功提交的结束时间（包括 `None`）保持不可变。

- [x] **Step 1: 把旧客户端无开始时间测试改成失败测试**

在 `test_patient_app_video_api.py` 将
`test_legacy_client_can_create_session_without_start_time` 改为
`test_create_session_requires_training_started_at`：

```python
payload = _session_payload(action)
payload.pop("training_started_at")

response = client.post(
    "/api/patient-app/training-video-sessions/",
    payload,
    format="json",
)

assert response.status_code == 400
assert "training_started_at" in response.data
assert not TrainingVideo.objects.filter(
    project_patient=project_patient,
    client_session_id=payload["client_session_id"],
).exists()
```

- [x] **Step 2: 写 finalize 可缺少结束时间和解耦墙钟跨度的失败测试**

删除“无开始、无结束的旧会话仍可 finalize”测试，新增三个场景：

```python
def test_finalize_accepts_missing_training_ended_at(
    project_patient, doctor, active_prescription, tmp_path
):
    payload = _finalize_payload()
    payload.pop("training_ended_at")
    response = client.post(_finalize_url(video), payload, format="json")
    assert response.status_code == 202
    video.refresh_from_db()
    assert video.training_ended_at is None

def test_finalize_accepts_video_duration_longer_than_training_wall_time(
    project_patient, doctor, active_prescription, tmp_path
):
    response = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at="2026-07-11T09:32:44+08:00"),
        format="json",
    )
    assert response.status_code == 202

def test_finalize_accepts_end_more_than_24_hours_after_start(
    project_patient, doctor, active_prescription, tmp_path
):
    response = client.post(
        _finalize_url(video),
        _finalize_payload(training_ended_at="2026-07-12T09:32:15+08:00"),
        format="json",
    )
    assert response.status_code == 202
```

保留无偏移格式和“结束时间不晚于开始时间”的 400 测试；从非法窗口参数表中移除 24 小时场景。

- [x] **Step 3: 写空结束时间的幂等不可补写测试**

第一次 finalize 不带 `training_ended_at`，相同 payload 重试应返回 200；第三次用同一视频补交非空结束时间应返回 409。该测试锁定“第一次成功值包括空值”的规则。

- [x] **Step 4: 运行后端时间契约测试并确认 RED**

Run:

```bash
cd backend
pytest apps/patient_app/tests/test_patient_app_video_api.py -q
```

Expected: 必填开始时间、超 24 小时允许、录像时长与墙钟解耦测试失败；现有格式与幂等测试继续通过。

- [x] **Step 5: 实现必填开始时间**

在 serializer 使用默认必填行为：

```python
training_started_at = ClientOffsetDateTimeField()
```

`validate()` 直接读取 `attrs["training_started_at"]` 对应的原始输入日期。视图改用：

```python
training_started_at=serializer.validated_data["training_started_at"]
```

服务函数签名改为必需关键字参数：

```python
def create_training_video_session(
    *,
    project_patient,
    client_session_id,
    prescription_action_id,
    training_date,
    expected_duration_seconds,
    training_started_at,
):
```

保持 `_ensure_session_payload_matches` 对开始时间和处方时长快照的现有冲突检查。

- [x] **Step 6: 简化结束时间校验**

把 `_validate_training_window` 收敛为：

```python
def _validate_training_end(video, *, training_ended_at):
    if training_ended_at is None:
        return
    if video.training_started_at is None:
        raise ValidationError("训练开始时间缺失，不能提交训练结束时间")
    if training_ended_at <= video.training_started_at:
        raise ValidationError("训练结束时间必须晚于开始时间")
```

调用处不再传 `actual_duration_seconds`。删除
`MAX_TRAINING_WALL_TIME`、`TRAINING_DURATION_TOLERANCE_SECONDS` 和
`datetime.timedelta` 导入；不要改变 `_validate_uploaded_segments_for_finalize`。

- [x] **Step 7: 补齐服务级测试调用者的固定开始时间**

在 `test_video_session_models.py` 和 `test_video_segment_concurrency.py`
所有直接调用 `create_training_video_session` 的位置传入同一个 aware datetime。
并发幂等测试的多个线程必须使用完全相同的值，避免把新的时间冲突误判成并发问题。

- [x] **Step 8: 运行后端相关测试并确认 GREEN**

Run:

```bash
cd backend
pytest \
  apps/patient_app/tests/test_patient_app_video_api.py \
  apps/training/tests/test_video_session_models.py \
  apps/training/tests/test_video_segment_concurrency.py -q
```

Expected: 全部通过，无 migration 变更。

- [x] **Step 9: 提交后端时间契约**

```bash
git add \
  backend/apps/patient_app/serializers.py \
  backend/apps/patient_app/views.py \
  backend/apps/training/video_services.py \
  backend/apps/patient_app/tests/test_patient_app_video_api.py \
  backend/apps/training/tests/test_video_session_models.py \
  backend/apps/training/tests/test_video_segment_concurrency.py
git commit -m "refactor(training): 简化训练视频时间契约"
```

---

### Task 2: 用处方时长快照计算固定健康观察窗口

**Files:**
- Modify: `backend/apps/training/tests/test_training_video_wearable_api.py`
- Modify: `backend/apps/wearables/services/training_windows.py:training_video_wearable_window`

**Interfaces:**
- 可用响应：

```json
{
  "available": true,
  "window_started_at": "2026-08-06T01:32:14+00:00",
  "window_ended_at": "2026-08-06T01:40:14+00:00",
  "expected_duration_seconds": 180,
  "buffer_seconds": 300,
  "metrics": {}
}
```

- 查询区间：`[training_started_at, training_started_at + expected_duration_seconds + 300 秒]`。
- `training_ended_at` 不参与可用性、上界或响应。

- [x] **Step 1: 调整测试工厂以明确处方时长快照**

把 `_video` 改为接受：

```python
def _video(
    project_patient,
    active_prescription,
    *,
    started_at,
    ended_at=None,
    expected_duration_seconds=180,
):
```

创建 `TrainingVideo` 时写入 `expected_duration_seconds`。允许
`ended_at=None`，以便测试意外退出。

- [x] **Step 2: 把主成功测试改成固定公式和闭区间测试**

使用：

```python
started_at = datetime(2026, 8, 6, 1, 32, 14, tzinfo=UTC)
expected_duration_seconds = 180
window_ended_at = started_at + timedelta(seconds=480)
```

在开始边界、窗口结束边界各放入有效点，并在两端外侧一微秒放入无效点。
断言响应为：

```python
assert response.data["window_started_at"] == started_at.isoformat()
assert response.data["window_ended_at"] == window_ended_at.isoformat()
assert response.data["expected_duration_seconds"] == 180
assert response.data["buffer_seconds"] == 300
assert "training_started_at" not in response.data
assert "training_ended_at" not in response.data
```

保留心率、血压 `ROUND_HALF_UP` 统计、血氧无统计和不返回 `steps` 的现有断言。

- [x] **Step 3: 写实际结束时间不影响窗口的失败测试**

为同一患者创建两个具有相同开始时间和处方时长的视频，一个
`training_ended_at=None`，另一个结束时间明显早于固定窗口上界。
分别调用接口，断言两者的 `window_started_at`、`window_ended_at`、
`expected_duration_seconds`、`buffer_seconds` 和 `metrics` 相同。

- [x] **Step 4: 写不可用条件失败测试**

参数化以下状态并断言精确返回 `{"available": False}`：

- `training_started_at=None`
- `expected_duration_seconds=None`
- `expected_duration_seconds=0`

从旧参数表移除 `training_ended_at`；另加 `training_ended_at=None` 且窗口内有数据时 `available: true` 的断言。

- [x] **Step 5: 运行穿戴窗口测试并确认 RED**

Run:

```bash
cd backend
pytest apps/training/tests/test_training_video_wearable_api.py -q
```

Expected: 新响应字段、固定上界、缺少结束时间仍可用的测试失败。

- [x] **Step 6: 实现统一窗口计算**

在 `training_windows.py` 增加：

```python
from datetime import timedelta

TRAINING_VIDEO_WEARABLE_BUFFER_SECONDS = 300


def _health_window(video):
    duration = video.expected_duration_seconds
    if video.training_started_at is None or duration is None or duration <= 0:
        return None
    started_at = video.training_started_at
    ended_at = started_at + timedelta(
        seconds=duration + TRAINING_VIDEO_WEARABLE_BUFFER_SECONDS
    )
    return started_at, ended_at
```

`training_video_wearable_window` 只使用 `_health_window` 的结果过滤
`measured_at__gte` / `measured_at__lte`，并返回：

```python
{
    "available": True,
    "window_started_at": window_started_at.isoformat(),
    "window_ended_at": window_ended_at.isoformat(),
    "expected_duration_seconds": video.expected_duration_seconds,
    "buffer_seconds": TRAINING_VIDEO_WEARABLE_BUFFER_SECONDS,
    "metrics": metrics,
}
```

无有效指标时继续返回 `{"available": False}`；不要查询
`WearableDailySource` 或触发穿戴同步。

- [x] **Step 7: 运行后端穿戴和跟踪回归测试**

Run:

```bash
cd backend
pytest \
  apps/training/tests/test_training_video_wearable_api.py \
  apps/training/tests/test_tracking_api.py -q
```

Expected: 全部通过；训练跟踪 API 仍可保留审计用的实际开始/结束字段。

- [x] **Step 8: 提交固定窗口后端实现**

```bash
git add \
  backend/apps/wearables/services/training_windows.py \
  backend/apps/training/tests/test_training_video_wearable_api.py
git commit -m "feat(wearables): 使用处方时长计算健康窗口"
```

---

### Task 3: 让小程序强制上报开始时间并容忍结束时间缺失

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/session.ts`
- Modify: `miniapp/src/pages/shoulder-press/session.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/api.ts`
- Modify: `miniapp/src/pages/shoulder-press/api.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/workflow.ts`
- Modify: `miniapp/src/pages/shoulder-press/workflow.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Test: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- `PendingShoulderPressSession.trainingStartedAt` 保持可选，因为会话在录像开始前创建。
- `requireShoulderPressTrainingStartedAt(session): string` 是所有远端创建调用的唯一运行时守卫。
- `createVideoSession({ trainingStartedAt: string })` 必填并始终发送。
- `finalizeVideoSession({ trainingEndedAt?: string })` 保持可选并在缺失时省略请求字段。

- [x] **Step 1: 写开始时间守卫失败测试**

在 `session.test.ts` 新增：

```ts
expect(() => requireShoulderPressTrainingStartedAt(
  createPendingShoulderPressSession(validInput),
)).toThrow('训练开始时间缺失，请重新训练')
```

并断言带有效偏移时间时原样返回。保留现有“首次开始后继续录像不修改”的测试。

- [x] **Step 2: 写上传流程缺少开始时间立即停止的失败测试**

在 `workflow.test.ts` 复制 `baseSession()`，删除 `trainingStartedAt`，
调用 `runPendingSegmentUploads`，断言：

```ts
await expect(runPendingSegmentUploads(session, deps, vi.fn()))
  .rejects.toThrow('训练开始时间缺失，请重新训练')
expect(deps.createVideoSession).not.toHaveBeenCalled()
expect(deps.uploadVideoSegment).not.toHaveBeenCalled()
expect(deps.finalizeVideoSession).not.toHaveBeenCalled()
```

- [x] **Step 3: 写缺少结束时间仍 finalize 的失败测试**

在 `workflow.test.ts` 删除 `trainingEndedAt` 后完成一次上传，断言 finalize
被调用且 `trainingEndedAt` 为 `undefined`。在 `api.test.ts` 单独调用
`finalizeVideoSession` 不传结束时间，并断言 HTTP 请求体没有
`training_ended_at`。

删除旧的“创建与完成时间都可省略”API 测试，改成只验证完成时间可省略；
所有 `createVideoSession` 测试调用必须显式传入 `trainingStartedAt`。

- [x] **Step 4: 运行小程序定向测试并确认 RED**

Run:

```bash
cd miniapp
npm test -- --run \
  src/pages/shoulder-press/session.test.ts \
  src/pages/shoulder-press/api.test.ts \
  src/pages/shoulder-press/workflow.test.ts
```

Expected: 守卫尚不存在、创建请求类型仍可选、缺少开始时间仍调用 API 的测试失败。

- [x] **Step 5: 实现单一开始时间守卫**

在 `session.ts` 增加：

```ts
export function requireShoulderPressTrainingStartedAt(
  session: PendingShoulderPressSession
): string {
  if (!session.trainingStartedAt) {
    throw new Error('训练开始时间缺失，请重新训练')
  }
  return session.trainingStartedAt
}
```

不要改变 `markShoulderPressTrainingStarted`、
`markShoulderPressTrainingEnded` 或清单 schema，不新增 phase 字段。

- [x] **Step 6: 收紧创建 API 类型并始终发送开始时间**

将 `api.ts`、`workflow.ts` 及旧适配器中的创建输入统一为：

```ts
trainingStartedAt: string
```

请求体直接写：

```ts
training_started_at: input.trainingStartedAt
```

保留 finalize 中条件展开 `training_ended_at` 的现有实现。

- [x] **Step 7: 在三个远端创建入口复用守卫**

在以下位置先读取一次：

```ts
const trainingStartedAt = requireShoulderPressTrainingStartedAt(session)
```

再传给 `createVideoSession`：

- `workflow.ts:runPendingSegmentUploads`
- `camera.tsx:ensureRemoteSession`
- `upload.tsx` 的远端会话创建路径

守卫必须位于任何网络调用之前。已有 `videoId` 的恢复上传不需要重新创建，
仍允许 `trainingEndedAt` 缺失并继续 finalize。

- [x] **Step 8: 回归录像时间采集顺序**

不重构 `camera.tsx:startTraining`。确认代码顺序保持：

```ts
await recorder.start()
const startedSession = markShoulderPressTrainingStarted(currentSession, Date.now())
saveCurrentSession(startedSession)
```

在 `pages.test.tsx` 保留并补强以下断言：

- `recorder.start()` reject 时本地会话没有 `trainingStartedAt`。
- 第一次成功后写入手机偏移时间。
- 暂停再继续后值完全不变。
- 正常完成写入 `trainingEndedAt`；意外退出不需要补写。

- [x] **Step 9: 运行小程序回归测试和构建**

Run:

```bash
cd miniapp
npm test -- --run \
  src/pages/shoulder-press/session.test.ts \
  src/pages/shoulder-press/api.test.ts \
  src/pages/shoulder-press/workflow.test.ts \
  src/pages/shoulder-press/pages.test.tsx
npm run build:weapp
```

Expected: 测试和微信小程序开发构建全部通过。

- [x] **Step 10: 提交小程序简化实现**

```bash
git add \
  miniapp/src/pages/shoulder-press/session.ts \
  miniapp/src/pages/shoulder-press/session.test.ts \
  miniapp/src/pages/shoulder-press/api.ts \
  miniapp/src/pages/shoulder-press/api.test.ts \
  miniapp/src/pages/shoulder-press/workflow.ts \
  miniapp/src/pages/shoulder-press/workflow.test.ts \
  miniapp/src/pages/shoulder-press/camera.tsx \
  miniapp/src/pages/shoulder-press/upload.tsx \
  miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "refactor(miniapp): 简化训练视频时间上报"
```

---

### Task 4: 医生端改用固定健康观察窗口

**Files:**
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Modify: `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.ts`
- Modify: `frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts`
- Modify: `frontend/src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`

**Interfaces:**
- `TrainingVideoWearableWindowResponse` 可用分支改为：

```ts
{
  available: true
  window_started_at: string
  window_ended_at: string
  expected_duration_seconds: number
  buffer_seconds: number
  metrics: { /* 既有三类指标 */ }
}
```

- 穿戴查询是否启用只依赖 `drawerOpen && selectedVideoId != null`。
- `TrackingRecentRecord.training_ended_at` 继续保留为后端审计兼容字段，但不参与展示和查询。

- [x] **Step 1: 更新响应 fixture 并写固定横轴失败测试**

在图表配置测试和面板测试中把旧字段改为：

```ts
window_started_at: "2026-08-06T01:32:14Z",
window_ended_at: "2026-08-06T01:40:14Z",
expected_duration_seconds: 180,
buffer_seconds: 300,
```

图表测试断言 `domainMin` / `domainMax` 精确来自这两个窗口字段，
而不是任何实际结束时间。

- [x] **Step 2: 写实际结束时间缺失仍查询的页面失败测试**

复制训练跟踪详情 fixture，将所选视频的 `training_ended_at` 设为 `null`，
让穿戴接口返回可用固定窗口。打开抽屉后断言：

```ts
expect(mockGet).toHaveBeenCalledWith(
  "/training/videos/8101/wearable-window/",
)
expect(await screen.findByText("训练时段穿戴趋势")).toBeInTheDocument()
expect(screen.queryByText("训练时段")).not.toBeInTheDocument()
```

- [x] **Step 3: 改写缺失本地时间的页面测试**

旧测试“缺开始或结束时不查询”不再成立。改为后端接口为唯一判定：

- 跟踪记录缺少实际结束时间：仍请求，后端可用则展示。
- 跟踪记录缺少开始时间：仍请求，后端返回 `available: false` 则隐藏。
- 请求失败：保留视频与动作分析，且不泄露错误文本。

- [x] **Step 4: 运行医生端定向测试并确认 RED**

Run:

```bash
cd frontend
npm test -- --run \
  src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts \
  src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx \
  src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
```

Expected: 类型字段、图表范围、结束时间为空仍查询的断言失败。

- [x] **Step 5: 更新响应类型和图表横轴**

在 `types.ts` 替换可用响应字段；在
`trainingVideoWearableChartConfig.ts` 改为：

```ts
domainMin: new Date(response.window_started_at).valueOf(),
domainMax: new Date(response.window_ended_at).valueOf(),
```

三类指标、单位、tooltip、统计表和空数据行为保持不变。

- [x] **Step 6: 删除对实际训练结束时间的 UI 依赖**

在 `TrainingTrackingDetailPage.tsx`：

- 删除 `selectedVideoHasTrainingWindow`。
- 删除从 `TrackingRecentRecord` 计算的 `trainingWindowLabel`。
- 删除抽屉 `Descriptions` 中“训练时段”项，避免展示实际完成时间。
- 将 query `enabled` 改为：

```ts
enabled: drawerOpen && selectedVideoId != null
```

继续使用视频 ID 作为 query key，并保留每次打开重新请求、失败静默隐藏的行为。

- [x] **Step 7: 运行前端定向测试、lint 和构建**

Run:

```bash
cd frontend
npm test -- --run \
  src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts \
  src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx \
  src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
npm run lint
npm run build
```

Expected: 全部通过，无 TypeScript 错误。

- [x] **Step 8: 提交医生端适配**

```bash
git add \
  frontend/src/pages/training-tracking/types.ts \
  frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.ts \
  frontend/src/pages/training-tracking/trainingVideoWearableChartConfig.test.ts \
  frontend/src/pages/training-tracking/TrainingVideoWearablePanel.test.tsx \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx \
  frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx
git commit -m "feat(frontend): 展示固定健康观察窗口"
```

---

### Task 5: 全量验证并更新实施记录

**Files:**
- Modify: `docs/superpowers/specs/2026-08-07-training-video-fixed-health-window-design.md`
- Modify: `docs/superpowers/plans/2026-08-07-training-video-fixed-health-window.md`
- Modify: `docs/superpowers/README.md`
- Modify: `specs/patient-rehab-system/changelog.md`

- [x] **Step 1: 检查数据库迁移和复杂状态机未被重新引入**

Run:

```bash
cd backend
python manage.py makemigrations --check --dry-run
cd ..
rg -n "Manifest V2|manifestVersion|phase.*recording|lifecycle recovery|training_ended_at.*wearable" \
  miniapp/src backend/apps frontend/src
```

Expected:

- Django 输出 `No changes detected`。
- 没有新增 Manifest V2、录像 phase 或生命周期恢复代码。
- `training_ended_at` 不出现在穿戴窗口计算和医生端查询门槛中；允许出现在审计字段、finalize 和相关测试中。

- [x] **Step 2: 运行后端全量测试**

Run:

```bash
cd backend
pytest
```

Expected: 全部通过。

- [x] **Step 3: 运行前端全量测试、lint 和构建**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: 全部通过。

- [x] **Step 4: 运行小程序全量测试和生产构建**

Run:

```bash
cd miniapp
npm run test
npm run build:weapp:prod
```

Expected: 全部通过。

- [x] **Step 5: 更新设计、计划索引和追加式变更日志**

- 将设计状态从 `approved` 改为 `implemented`。
- 将本计划状态从 `approved` 改为 `implemented`。
- 把所有已完成 checkbox 改为 `- [x]`。
- 在计划顶部追加每个任务的中文 commit short SHA 和全量验证结果。
- 在 `docs/superpowers/README.md` 的设计、计划清单新增本主题和最终状态。
- 只在 `specs/patient-rehab-system/changelog.md` 末尾追加一条：

```text
2026-08-07：训练视频健康观察窗口改为手机首次录像时间起、处方时长快照加 5 分钟止；实际完成时间保留为可选审计字段，不再影响穿戴趋势。
```

- [x] **Step 6: 提交文档收口**

```bash
git add \
  docs/superpowers/specs/2026-08-07-training-video-fixed-health-window-design.md \
  docs/superpowers/plans/2026-08-07-training-video-fixed-health-window.md \
  docs/superpowers/README.md \
  specs/patient-rehab-system/changelog.md
git commit -m "docs(training): 记录固定健康观察窗口实施结果"
```

---

## 最终验收清单

- [x] 第一次录像真正启动成功后，手机端只记录一次 `training_started_at`。
- [x] 暂停、继续、上传和重试不改变开始时间或处方时长快照。
- [x] 新建远端视频会话缺少开始时间时，在客户端和后端都被拒绝。
- [x] 正常完成可上传 `training_ended_at`，意外退出导致缺失时不补写、不阻断允许的恢复上传。
- [x] 非空实际结束时间只校验晚于开始时间，不再限制 24 小时或实际录像时长。
- [x] 健康窗口严格等于 `training_started_at + expected_duration_seconds + 300 秒`。
- [x] 实际结束时间为空、提前或延后都不改变健康窗口。
- [x] 心率、血压、血氧按固定闭区间展示；心率和血压统计保持正确。
- [x] 步数不被估算成训练时段趋势。
- [x] 医生端不展示实际完成时间，也不以其是否存在决定是否查询健康窗口。
- [x] 视频、动作分析、穿戴权限和上传链路无回归。
- [x] 后端、前端、小程序全量验证和构建全部通过。
