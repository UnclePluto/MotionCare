# 穿戴设备 OpenAPI 接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 执行记录（2026-07-23, codex）：Task 1 已落地于 commits `6b46942`、`b73bab7`，任务审查通过。
>
> 执行记录（2026-07-23, codex）：Task 2 已落地于 commits `d5f0050`、`e785522`、`1495a04`，任务审查通过。

**Goal:** 在 MotionCare 中完成穿戴设备台账与患者绑定、miwitracker OpenAPI 同步和非破坏性远程操作，并把现有“训练追踪”升级为包含“训练跟踪/穿戴健康”双页签的“训练与健康”，同时移除手工健康录入且保持 CRF 完全不变。

**Architecture:** 在现有 Django 单体中新建 `apps.wearables`，由 provider 适配层隔离厂商协议，由绑定区间决定数据归属，由 Celery 每天 03:00 动态补拉最多七天数据。React 管理端复用现有训练追踪页面并新增穿戴健康页签；微信小程序和旧 `health` 应用只做手工健康能力下线。

**Tech Stack:** Django 5、DRF、PostgreSQL、Celery/Redis、httpx、React 18、TypeScript、TanStack Query v5、Ant Design 5、Vitest、pytest-django、Taro。

## Global Constraints

- 不实现 TCP 直连、Webhook、定位、轨迹、电子围栏、重启、关机、恢复出厂。
- 不修改 `backend/apps/crf/`、CRF registry、CRF Word 模板、CRF 预览或导出响应结构。
- 厂商真实标识统一命名为 `external_device_id`，不得把业务字段写死为 IMEI。
- 设备固定简码必须是允许前导零的四位数字字符串；小程序临时绑定码与设备固定简码必须使用不同文案。
- 设备绑定对象是全局 `Patient`；项目患者页面只是安全解析患者和提供操作入口。
- 绑定区间采用 `[bound_at, unbound_at)`；解绑不删除旧患者研究数据。
- 心率、血压、血氧保留原始点；患者日汇总唯一键为 `patient + record_date`。
- 同日中途绑定、解绑或换绑时，厂商整日步数标记不可归属，不猜测、不分摊。
- Django 保持 `USE_TZ = True`；库存储 UTC，业务自然日固定为 `Asia/Shanghai`。
- Celery Beat 每天 03:00 调度；每个设备、每个指标动态补拉且最多回看七天。
- “训练与健康”详情内只有“训练跟踪”和“穿戴健康”两个页签，页签名旁不显示设备在线标签。
- Web 和微信小程序均移除手工健康录入。
- 后端 API 必须使用 `IsAdminOrDoctor` 并复用现有行级数据范围规则。
- 所有新增或修改 API 行为必须先写失败测试，再写实现。
- 所有提交信息使用中文；执行者不得覆盖任务开始前已有的未提交改动。

---

## 文件结构

新增后端文件：

```text
backend/apps/wearables/
├── __init__.py
├── apps.py
├── models.py
├── urls.py
├── serializers.py
├── views.py
├── tasks.py
├── capabilities.py
├── providers/
│   ├── __init__.py
│   ├── base.py
│   └── miwitracker.py
├── services/
│   ├── __init__.py
│   ├── attribution.py
│   ├── bindings.py
│   ├── commands.py
│   ├── queries.py
│   ├── short_codes.py
│   ├── summaries.py
│   └── sync.py
├── migrations/
│   ├── __init__.py
│   └── 0001_initial.py
└── tests/
    ├── __init__.py
    ├── test_attribution.py
    ├── test_binding_api.py
    ├── test_commands.py
    ├── test_models.py
    ├── test_provider_miwitracker.py
    ├── test_queries_api.py
    ├── test_summaries.py
    └── test_sync.py
```

新增前端文件：

```text
frontend/src/pages/wearables/
├── DeviceInventoryPage.tsx
├── DeviceInventoryPage.test.tsx
├── WearableBindingPanel.tsx
├── WearableBindingPanel.test.tsx
├── WearableHealthTab.tsx
├── WearableHealthTab.test.tsx
├── WearableMetricChart.tsx
└── types.ts
```

现有 `training-tracking` 文件继续负责训练页签，不迁移或重写训练统计算法。

---

### Task 1: 建立 wearables 应用和数据模型

**Files:**
- Create: `backend/apps/wearables/__init__.py`
- Create: `backend/apps/wearables/apps.py`
- Create: `backend/apps/wearables/models.py`
- Create: `backend/apps/wearables/migrations/__init__.py`
- Create: `backend/apps/wearables/migrations/0001_initial.py`
- Create: `backend/apps/wearables/tests/__init__.py`
- Create: `backend/apps/wearables/tests/conftest.py`
- Create: `backend/apps/wearables/tests/test_models.py`
- Modify: `backend/config/settings.py`

**Interfaces:**
- Produces: `WearableDevice`、`WearableBinding`、`WearableMeasurement`、`WearableDailySource`、`WearableDailySummary`、`WearableSyncCursor`、`WearableSyncRun`、`WearableCommandLog`。
- Consumes: `apps.patients.models.Patient`、`apps.accounts.models.User`、`apps.common.models.TimeStampedModel`。

- [x] **Step 1: 建立测试夹具**

```python
# backend/apps/wearables/tests/conftest.py
import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient
from apps.studies.models import ProjectPatient
from apps.wearables.models import WearableDevice


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def wearable_device(db):
    return WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        model="TEST-MODEL",
        short_code="0826",
    )


@pytest.fixture
def other_project_patient(db, doctor, project, group):
    other_patient = Patient.objects.create(
        name="患者乙",
        gender=Patient.Gender.UNKNOWN,
        age=68,
        phone="13900002222",
        primary_doctor=doctor,
    )
    return ProjectPatient.objects.create(
        project=project,
        patient=other_patient,
        group=group,
    )
```

- [x] **Step 2: 写模型约束失败测试**

```python
# backend/apps/wearables/tests/test_models.py
import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.wearables.models import WearableBinding, WearableDevice


@pytest.mark.django_db
def test_device_external_identity_and_short_code_are_unique():
    WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        short_code="0826",
    )
    with pytest.raises(IntegrityError):
        WearableDevice.objects.create(
            provider="miwitracker",
            external_device_id="dev-001",
            identifier_type="device_id",
            short_code="1735",
        )


@pytest.mark.django_db
def test_patient_and_device_each_have_only_one_active_binding(patient, doctor):
    first = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-001",
        identifier_type="device_id",
        short_code="0826",
    )
    second = WearableDevice.objects.create(
        provider="miwitracker",
        external_device_id="dev-002",
        identifier_type="device_id",
        short_code="1735",
    )
    WearableBinding.objects.create(
        patient=patient,
        device=first,
        bound_at=timezone.now(),
        bound_by=doctor,
    )
    with pytest.raises(IntegrityError):
        WearableBinding.objects.create(
            patient=patient,
            device=second,
            bound_at=timezone.now(),
            bound_by=doctor,
        )
```

- [x] **Step 3: 运行模型测试确认失败**

Run: `cd backend && pytest apps/wearables/tests/test_models.py -q`

Expected: FAIL，原因是 `apps.wearables` 尚不存在。

- [x] **Step 4: 创建模型和数据库约束**

`WearableBinding` 的数据库约束必须包含：

```python
models.UniqueConstraint(
    fields=["patient"],
    condition=models.Q(unbound_at__isnull=True),
    name="uniq_active_wearable_binding_per_patient",
)
models.UniqueConstraint(
    fields=["device"],
    condition=models.Q(unbound_at__isnull=True),
    name="uniq_active_wearable_binding_per_device",
)
models.CheckConstraint(
    condition=models.Q(unbound_at__isnull=True) | models.Q(unbound_at__gt=models.F("bound_at")),
    name="wearable_binding_end_after_start",
)
```

`WearableDevice.short_code` 使用 `CharField(max_length=4, unique=True)`；在 `clean()` 中使用正则 `r"\d{4}"` 校验。

`WearableMeasurement` 使用以下指标枚举：

```python
class MetricType(models.TextChoices):
    HEART_RATE = "heart_rate", "心率"
    BLOOD_PRESSURE = "blood_pressure", "血压"
    BLOOD_OXYGEN = "blood_oxygen", "血氧"
```

其唯一约束为：

```python
models.UniqueConstraint(
    fields=["provider", "device", "metric_type", "source_fingerprint"],
    name="uniq_wearable_measurement_source",
)
```

`WearableDailySource` 唯一键为 `provider + device + record_date`；`WearableDailySummary` 唯一键为 `patient + record_date`；`WearableSyncCursor` 唯一键为 `device + metric_type`。

`WearableSyncRun` 保存 `window_start`、`window_end`、`status`、`returned_count`、`error_code`、`error_message`、`retry_count`。`WearableCommandLog` 保存 `command_type`、`command_code`、`request_payload`、`provider_code`、`status`、`requested_by`、`completed_at`。

- [x] **Step 5: 注册应用并生成 migration**

在 `INSTALLED_APPS` 中把 `"apps.wearables"` 放在 `"apps.health"` 之前。

Run: `cd backend && python manage.py makemigrations wearables`

Expected: 生成 `apps/wearables/migrations/0001_initial.py`，包含八个模型和上述约束。

- [x] **Step 6: 验证 migration 和模型测试**

Run: `cd backend && python manage.py makemigrations --check && pytest apps/wearables/tests/test_models.py -q`

Expected: `No changes detected`，测试 PASS。

- [x] **Step 7: 提交**

```bash
git add backend/apps/wearables backend/config/settings.py
git commit -m "feat(wearables): 建立穿戴设备数据模型"
```

---

### Task 2: 实现 miwitracker Provider、Token 和数据解析

**Files:**
- Create: `backend/apps/wearables/providers/__init__.py`
- Create: `backend/apps/wearables/providers/base.py`
- Create: `backend/apps/wearables/providers/miwitracker.py`
- Create: `backend/apps/wearables/tests/test_provider_miwitracker.py`
- Modify: `backend/pyproject.toml`
- Modify: `backend/config/settings.py`
- Modify: `.env.example`
- Modify: `deploy/env.production.example`

**Interfaces:**
- Produces: `ProviderMeasurement`、`ProviderDailySteps`、`ProviderDeviceStatus`、`ProviderCommandResult`、`WearableProvider` protocol、`MiwitrackerClient`。
- Consumes: `MIWITRACKER_BASE_URL`、`MIWITRACKER_APP_ID`、`MIWITRACKER_KEY`。

- [x] **Step 1: 增加 httpx 依赖并写 Provider 合约**

在 `backend/pyproject.toml` dependencies 增加：

```toml
"httpx>=0.27,<1.0",
```

在 `providers/base.py` 定义不可变 dataclass：

```python
@dataclass(frozen=True)
class ProviderMeasurement:
    metric_type: str
    measured_at: datetime
    values: dict[str, int | Decimal]
    raw_payload: dict


@dataclass(frozen=True)
class ProviderDailySteps:
    record_date: date
    steps: int | None
    distance: Decimal | None
    calorie: Decimal | None
    raw_payload: dict
```

`WearableProvider` 必须定义 `get_heart_rates()`、`get_blood_pressures()`、`get_blood_oxygen()`、`get_daily_steps()`、`get_device_status()`、`send_command()`。

- [x] **Step 2: 写 Token 和解析失败测试**

使用 `httpx.MockTransport` 验证：

```python
def test_token_password_is_md5_key_appid_timestamp(settings):
    settings.MIWITRACKER_APP_ID = "188"
    settings.MIWITRACKER_KEY = "abc"
    assert build_token_password("abc", "188", 1619582437) == "d70429870da4c12b70e195638ebe1a07"


def test_heart_rate_parser_treats_begin_and_end_as_utc_zero(client):
    points = client.parse_heart_rates(
        [{"HeartRate": 72, "HrTime": "2026-07-22 01:15:00"}]
    )
    assert points[0].measured_at.isoformat() == "2026-07-22T01:15:00+00:00"
```

测试必须覆盖：

- Token 请求体 `Password = md5(KEY + AppId + Timestamp)`。
- Token 请求地址 `/api/token/get_token`。
- 业务请求 Header `Authorization` 等于 `AccessToken`，且请求体保留文档要求的 `AccessToken`。
- 心率 `HeartRate/HrTime`。
- 血压 `Systolic/Diastolic/BpTime`。
- 血氧 `BloodOxygen/BloodOxygenTime`。
- 步数 `Items[].Date/Steps/Distance/Calorie`。
- 空数组返回空列表。
- 非零厂商 `Code` 抛出带 code 的 `ProviderError`。

- [x] **Step 3: 运行 Provider 测试确认失败**

Run: `cd backend && pytest apps/wearables/tests/test_provider_miwitracker.py -q`

Expected: FAIL，原因是 Provider 类尚未实现。

- [x] **Step 4: 实现 Token 缓存和四类接口**

`MiwitrackerClient` 使用以下 endpoint：

```python
TOKEN_PATH = "/api/token/get_token"
HEART_RATE_PATH = "/api/heartrate/get_heartrate_bytime"
BLOOD_PRESSURE_PATH = "/api/bloodpressure/get_bloodpressure_bytime"
BLOOD_OXYGEN_PATH = "/api/bloodoxygen/get_bloodoxygen_bytime"
DAILY_STEPS_PATH = "/api/steps/get_steps_forday"
DEVICE_STATUS_PATH = "/api/location/get_location_info"
COMMAND_PATH = "/api/command/sendcommand"
```

Token 使用 Django cache 保存 50 分钟；401 或厂商无权限响应时清除缓存、刷新 Token 并且只重试一次。超时必须设置连接 5 秒、读取 20 秒。日志不得输出 KEY、Password 或 AccessToken。

- [x] **Step 5: 增加环境配置**

```python
MIWITRACKER_BASE_URL = os.getenv(
    "MIWITRACKER_BASE_URL", "https://openapi.miwitracker.com"
)
MIWITRACKER_APP_ID = os.getenv("MIWITRACKER_APP_ID", "")
MIWITRACKER_KEY = os.getenv("MIWITRACKER_KEY", "")
```

`.env.example` 和 `deploy/env.production.example` 只写空值和说明，不填写真实凭据。执行时如果这些文件已有其他会话改动，必须在原内容上定向追加。

- [x] **Step 6: 运行测试**

Run: `cd backend && python -m pip install -e '.[dev]' && pytest apps/wearables/tests/test_provider_miwitracker.py -q`

Expected: PASS。

- [x] **Step 7: 提交**

```bash
git add backend/pyproject.toml backend/apps/wearables/providers backend/apps/wearables/tests/test_provider_miwitracker.py backend/config/settings.py .env.example deploy/env.production.example
git commit -m "feat(wearables): 实现厂商OpenAPI客户端"
```

---

### Task 3: 实现设备台账、固定简码与患者绑定 API

**Files:**
- Create: `backend/apps/wearables/services/__init__.py`
- Create: `backend/apps/wearables/services/short_codes.py`
- Create: `backend/apps/wearables/services/bindings.py`
- Create: `backend/apps/wearables/serializers.py`
- Create: `backend/apps/wearables/views.py`
- Create: `backend/apps/wearables/urls.py`
- Create: `backend/apps/wearables/tests/test_binding_api.py`
- Modify: `backend/config/urls.py`

**Interfaces:**
- Produces: `generate_device_short_code()`、`bind_device()`、`unbind_device()`、设备 CRUD、项目患者绑定状态/绑定/解绑 API。
- Consumes: Task 1 模型、现有 `accessible_project_patients(user)` 行级过滤。

- [ ] **Step 1: 写固定简码和绑定 API 失败测试**

核心用例：

```python
@pytest.mark.django_db
def test_bind_project_patient_resolves_global_patient(
    api_client, doctor, project_patient, wearable_device
):
    api_client.force_authenticate(doctor)
    response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    assert response.status_code == 201
    assert response.data["patient_id"] == project_patient.patient_id


@pytest.mark.django_db
def test_rebound_device_does_not_overlap_previous_patient(
    api_client, doctor, project_patient, other_project_patient, wearable_device
):
    api_client.force_authenticate(doctor)
    api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    response = api_client.post(
        f"/api/wearables/project-patients/{other_project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    assert response.status_code == 409
```

同时覆盖：前导零简码、简码碰撞重试、四位空间耗尽、患者已有设备、设备已绑其他患者、无权访问 `ProjectPatient`、解绑二次调用幂等拒绝。

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest apps/wearables/tests/test_binding_api.py -q`

Expected: FAIL，路由不存在。

- [ ] **Step 3: 实现固定简码生成器**

`generate_device_short_code()`：

1. 使用 `secrets.randbelow(10000)` 生成 `f"{value:04d}"`。
2. 随机尝试 32 次。
3. 仍碰撞时从 `0000` 到 `9999` 查找第一个未使用号码。
4. 全部占用时抛出 `ShortCodeExhausted("四位设备简码已用尽")`。

创建设备必须在事务内调用生成器并捕获 `IntegrityError` 重试，避免并发重复。

- [ ] **Step 4: 实现绑定事务**

`bind_device(*, project_patient, short_code, actor, bound_at=None)` 必须：

```python
with transaction.atomic():
    patient = Patient.objects.select_for_update().get(pk=project_patient.patient_id)
    device = WearableDevice.objects.select_for_update().get(short_code=short_code, enabled=True)
    active_for_patient = WearableBinding.objects.select_for_update().filter(
        patient=patient, unbound_at__isnull=True
    ).first()
    active_for_device = WearableBinding.objects.select_for_update().filter(
        device=device, unbound_at__isnull=True
    ).first()
```

同一患者已绑定同一设备时返回现有绑定；患者或设备冲突时返回 409。`unbind_device()` 设置 `[bound_at, unbound_at)` 的结束时间，不删除绑定。

- [ ] **Step 5: 实现 API 和权限**

路由：

```text
GET/POST  /api/wearables/devices/
GET/PATCH /api/wearables/devices/{id}/
GET       /api/wearables/project-patients/{id}/binding/
POST      /api/wearables/project-patients/{id}/bind/
POST      /api/wearables/bindings/{id}/unbind/
```

项目患者解析必须使用 `accessible_project_patients(request.user)`；设备接口使用 `IsAdminOrDoctor`。解绑响应明确返回 `historical_data_preserved: true`。

- [ ] **Step 6: 运行测试**

Run: `cd backend && pytest apps/wearables/tests/test_binding_api.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/apps/wearables backend/config/urls.py
git commit -m "feat(wearables): 完成设备台账与患者绑定"
```

---

### Task 4: 实现原始数据归属和患者日汇总

**Files:**
- Create: `backend/apps/wearables/services/attribution.py`
- Create: `backend/apps/wearables/services/summaries.py`
- Create: `backend/apps/wearables/tests/test_attribution.py`
- Create: `backend/apps/wearables/tests/test_summaries.py`

**Interfaces:**
- Produces: `attribute_measurement()`、`attribute_daily_steps()`、`recalculate_daily_summary(patient_id, record_date)`。
- Consumes: Task 1 模型、Task 2 `ProviderMeasurement` 和 `ProviderDailySteps`。

- [ ] **Step 1: 写绑定边界失败测试**

测试必须固定时间并覆盖半开区间：

```python
@pytest.mark.django_db
def test_measurement_at_unbound_at_is_not_old_patient(
    patient, doctor, wearable_device
):
    start = datetime(2026, 7, 20, tzinfo=UTC)
    end = datetime(2026, 7, 22, tzinfo=UTC)
    WearableBinding.objects.create(
        patient=patient,
        device=wearable_device,
        bound_at=start,
        unbound_at=end,
        bound_by=doctor,
        unbound_by=doctor,
    )
    result = resolve_binding(wearable_device, end)
    assert result is None
```

步数测试必须覆盖：

- 绑定在上海自然日开始前且解绑在次日零点后：可归属。
- 当日 10:00 绑定：`ambiguous`。
- 当日 15:00 从 A 换到 B：A、B 都不能取得该设备整日步数。

- [ ] **Step 2: 写日汇总失败测试**

插入同日心率 `60, 72, 84`、两次血压 `120/80, 118/76`、血氧 `96, 98` 和有效步数 `5821`，断言：

```python
assert summary.heart_rate_avg == Decimal("72.00")
assert (summary.heart_rate_min, summary.heart_rate_max, summary.heart_rate_count) == (60, 84, 3)
assert summary.systolic_avg == Decimal("119.00")
assert summary.diastolic_avg == Decimal("78.00")
assert summary.blood_pressure_count == 2
assert summary.blood_oxygen_avg == Decimal("97.00")
assert summary.steps == 5821
```

- [ ] **Step 3: 运行失败测试**

Run: `cd backend && pytest apps/wearables/tests/test_attribution.py apps/wearables/tests/test_summaries.py -q`

Expected: FAIL，服务函数不存在。

- [ ] **Step 4: 实现时间归属**

`resolve_binding(device, measured_at)` 查询：

```python
WearableBinding.objects.filter(
    device=device,
    bound_at__lte=measured_at,
).filter(
    Q(unbound_at__isnull=True) | Q(unbound_at__gt=measured_at)
)
```

零条为 `outside_binding`，一条为 `attributed`，多条为 `ambiguous`。不得把未归属记录附给当前患者。

步数归属使用 `ZoneInfo("Asia/Shanghai")` 计算 `[day_start, day_end)`，只有唯一绑定满足 `bound_at <= day_start` 且 `unbound_at is null or unbound_at >= day_end` 时才归属。

- [ ] **Step 5: 实现幂等写入和汇总**

指纹使用规范化 JSON 的 SHA-256：

```python
payload = {
    "metric_type": point.metric_type,
    "measured_at": point.measured_at.isoformat(),
    "values": point.values,
}
fingerprint = hashlib.sha256(
    json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
).hexdigest()
```

汇总只查询 `attribution_status="attributed"` 的记录，并以 `WearableDailySummary.objects.update_or_create()` 写入。无有效值时对应字段设为 `None`、count 设为 `0`。

- [ ] **Step 6: 运行测试**

Run: `cd backend && pytest apps/wearables/tests/test_attribution.py apps/wearables/tests/test_summaries.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/apps/wearables/services backend/apps/wearables/tests
git commit -m "feat(wearables): 实现测量归属与日汇总"
```

---

### Task 5: 实现每天 03:00 动态补拉任务

**Files:**
- Create: `backend/apps/wearables/services/sync.py`
- Create: `backend/apps/wearables/tasks.py`
- Create: `backend/apps/wearables/tests/test_sync.py`
- Modify: `backend/config/settings.py`

**Interfaces:**
- Produces: `calculate_sync_window()`、`sync_device_metric()`、`schedule_daily_wearable_sync()`。
- Consumes: Provider、归属、汇总、同步游标和日志模型。

- [ ] **Step 1: 写窗口计算失败测试**

固定 `target_end = 2026-07-23 00:00 Asia/Shanghai`，覆盖：

- 无游标且绑定已持续 20 天：开始时间为七天前。
- 最近成功结束在两天前：开始时间为成功结束前 24 小时。
- 失败窗口在六天前：开始时间回退覆盖失败窗口。
- 失败窗口在十天前：仍只能回退七天。
- 最近七天已解绑设备仍被调度。
- 成功空结果推进游标。
- 某一指标失败不影响其他三个指标成功。

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest apps/wearables/tests/test_sync.py -q`

Expected: FAIL，任务和窗口函数不存在。

- [ ] **Step 3: 实现窗口函数**

函数签名：

```python
def calculate_sync_window(
    *,
    device: WearableDevice,
    metric_type: str,
    target_end: datetime,
) -> tuple[datetime, datetime]:
```

开始时间取：

```text
max(
  target_end - 7 days,
  最近七天相关绑定历史的最早 bound_at,
  last_success_window_end - 24 hours
)
```

若七天范围内存在更早未解决失败窗口，则用该窗口开始时间替换第三项。所有结果转换为 UTC。

- [ ] **Step 4: 实现同步任务**

`schedule_daily_wearable_sync` 查询：

```python
WearableDevice.objects.filter(
    enabled=True,
    bindings__bound_at__lt=target_end,
).filter(
    Q(bindings__unbound_at__isnull=True)
    | Q(bindings__unbound_at__gte=target_end - timedelta(days=7))
).distinct()
```

对每台设备下发四个独立 Celery task：`heart_rate`、`blood_pressure`、`blood_oxygen`、`steps`。每个 task：

1. 创建 `WearableSyncRun(status="running")`。
2. 调用对应 Provider。
3. 幂等写入并归属。
4. 重算受影响日期。
5. 成功时推进 `WearableSyncCursor`，包括空结果。
6. 失败时保存错误且不推进游标，再通过 `self.retry(countdown=60 * 2**retries, max_retries=3)` 重试。

- [ ] **Step 5: 配置每天 03:00**

在 `settings.py` 引入 `from celery.schedules import crontab`，加入：

```python
"schedule-daily-wearable-sync": {
    "task": "apps.wearables.tasks.schedule_daily_wearable_sync",
    "schedule": crontab(hour=3, minute=0),
},
```

同时设置：

```python
CELERY_TIMEZONE = "Asia/Shanghai"
CELERY_ENABLE_UTC = True
```

- [ ] **Step 6: 运行测试**

Run: `cd backend && pytest apps/wearables/tests/test_sync.py -q`

Expected: PASS。

- [ ] **Step 7: 提交**

```bash
git add backend/apps/wearables backend/config/settings.py
git commit -m "feat(wearables): 增加每日动态补拉任务"
```

---

### Task 6: 实现通信测试、型号能力和远程命令

**Files:**
- Create: `backend/apps/wearables/capabilities.py`
- Create: `backend/apps/wearables/services/commands.py`
- Create: `backend/apps/wearables/tests/test_commands.py`
- Modify: `backend/apps/wearables/views.py`
- Modify: `backend/apps/wearables/urls.py`

**Interfaces:**
- Produces: `CapabilityProfile`、`get_capability_profile()`、`check_device_status()`、`send_device_command()`、主动测量轮询任务。
- Consumes: Provider `get_device_status()` 和 `send_command()`。

- [ ] **Step 1: 写安全能力失败测试**

测试：

```python
def test_unknown_model_cannot_send_measurement_command(wearable_device):
    wearable_device.model = "UNKNOWN"
    with pytest.raises(UnsupportedCapability):
        send_device_command(
            device=wearable_device,
            command_type="measure_heart_rate",
            actor=None,
        )
```

并覆盖：

- 状态接口只返回 ID、型号、在线状态、电量、最近通信，不返回经纬度。
- 未验证型号允许状态查询和历史拉取。
- 未验证型号禁用响铃、配置和主动测量。
- 测试能力配置中 `ring=9018`、`heart_rate=9012`、`blood_pressure=9510`、`blood_oxygen=9511` 能生成正确请求。
- `0/1803/1800/1801/1802` 映射为 `succeeded/queued/offline/timeout/failed`。
- 命令日志保存参数摘要但不保存 AccessToken。

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest apps/wearables/tests/test_commands.py -q`

Expected: FAIL。

- [ ] **Step 3: 实现能力配置**

```python
@dataclass(frozen=True)
class CapabilityProfile:
    ring: str | None = None
    measure_heart_rate: str | None = None
    measure_blood_pressure: str | None = None
    measure_blood_oxygen: str | None = None
    configure_heart_rate_interval: str | None = None
    configure_blood_pressure_interval: str | None = None
    configure_blood_oxygen_interval: str | None = None
    configure_step_switch: str | None = None


MODEL_CAPABILITIES: dict[tuple[str, str], CapabilityProfile] = {}
```

生产默认映射保持为空，直到医院实际设备型号完成现场验证；测试通过 monkeypatch 注入明确 profile。空映射是安全关闭，不允许根据文档里的多型号混合命令表猜测型号能力。

- [ ] **Step 4: 实现动作接口**

```text
POST /api/wearables/devices/{id}/check-status/
POST /api/wearables/devices/{id}/ring/
POST /api/wearables/patients/{patient_id}/measure/
POST /api/wearables/patients/{patient_id}/configure/
POST /api/wearables/patients/{patient_id}/sync/
```

主动测量 body：

```json
{"metric_type": "heart_rate"}
```

命令返回 `queued` 后，Celery 每 10 秒查询对应历史接口，最多 6 次；取得 `requested_at` 之后的新点即成功。60 秒内没有新点返回 `timeout`，不创建伪造测量值。

- [ ] **Step 5: 运行测试**

Run: `cd backend && pytest apps/wearables/tests/test_commands.py -q`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add backend/apps/wearables
git commit -m "feat(wearables): 增加设备通信与远程操作"
```

---

### Task 7: 实现穿戴查询和研究汇总 API

**Files:**
- Create: `backend/apps/wearables/services/queries.py`
- Create: `backend/apps/wearables/tests/test_queries_api.py`
- Modify: `backend/apps/wearables/serializers.py`
- Modify: `backend/apps/wearables/views.py`
- Modify: `backend/apps/wearables/urls.py`
- Modify: `backend/apps/training/tracking.py`
- Modify: `backend/apps/training/tests/test_tracking_api.py`

**Interfaces:**
- Produces: 患者原始趋势、日汇总、同步状态、项目/分组汇总 API；训练与健康患者列表的穿戴摘要字段。
- Consumes: `accessible_project_patients(user)`、Wearable 原始数据和日汇总。

- [ ] **Step 1: 写查询失败测试**

覆盖：

- 医生只能查询可访问 `ProjectPatient` 所属患者。
- 同一患者多项目时，切换 `project_patient` 后日期裁剪到对应 `enrolled_at` 与项目研究结束日期。
- 原始、5m、15m、30m、1h 分桶返回正确平均值。
- 血压分桶分别计算收缩压和舒张压。
- 步数查询拒绝 `bucket=15m`，只返回日总量。
- 项目汇总按 group 返回患者数、有效数据日、均值、范围、测量次数和缺失率。
- CRF preview 响应快照没有新增 `health` 或 `wearable` key。

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest apps/wearables/tests/test_queries_api.py apps/training/tests/test_tracking_api.py -q`

Expected: FAIL，新字段和新接口不存在。

- [ ] **Step 3: 实现患者查询**

路由：

```text
GET /api/wearables/patients/{patient_id}/measurements/
GET /api/wearables/patients/{patient_id}/daily-summaries/
GET /api/wearables/patients/{patient_id}/sync-status/
GET /api/wearables/projects/{project_id}/summary/
```

测量查询参数：

```text
project_patient=<id>
metric_type=heart_rate|blood_pressure|blood_oxygen
start=YYYY-MM-DD
end=YYYY-MM-DD
bucket=raw|5m|15m|30m|1h
```

所有患者查询先验证该患者至少存在一条 `accessible_project_patients(user)`。提供 `project_patient` 时，必须验证其属于当前患者并在用户可访问范围内。

- [ ] **Step 4: 扩展训练追踪列表**

`list_patient_tracking_summaries()` 每行新增：

```python
"wearable": {
    "is_bound": bool,
    "device_short_code": str | None,
    "last_sync_at": str | None,
    "last_30_days_data_completeness": float | None,
}
```

不要在列表或页签名旁添加“在线” Tag；在线状态只在穿戴健康内容区按需查询。

- [ ] **Step 5: 运行测试**

Run: `cd backend && pytest apps/wearables/tests/test_queries_api.py apps/training/tests/test_tracking_api.py apps/crf/tests -q`

Expected: PASS，CRF 回归无变化。

- [ ] **Step 6: 提交**

```bash
git add backend/apps/wearables backend/apps/training
git commit -m "feat(wearables): 提供穿戴趋势与研究汇总接口"
```

---

### Task 8: 实现设备台账和项目患者绑定界面

**Files:**
- Create: `frontend/src/pages/wearables/types.ts`
- Create: `frontend/src/pages/wearables/DeviceInventoryPage.tsx`
- Create: `frontend/src/pages/wearables/DeviceInventoryPage.test.tsx`
- Create: `frontend/src/pages/wearables/WearableBindingPanel.tsx`
- Create: `frontend/src/pages/wearables/WearableBindingPanel.test.tsx`
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.tsx`
- Modify: `frontend/src/pages/research-entry/ProjectPatientBindingCard.test.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`
- Modify: `frontend/src/app/layout/AdminLayout.tsx`

**Interfaces:**
- Produces: `/wearable-devices` 设备台账；项目患者页“患者接入”双区域。
- Consumes: Task 3/6 设备、绑定、解绑和通信测试 API。

- [ ] **Step 1: 写界面失败测试**

验证：

- 设备录入后展示固定四位简码，`0826` 不丢前导零。
- 项目患者页标题为“患者接入”。
- 小程序区域文案为“小程序临时绑定码”。
- 穿戴区域输入项文案为“设备固定简码”。
- 输入设备简码绑定后，分别展示“患者设备绑定成功”和通信测试结果。
- 解绑确认文案包含“历史研究数据不会删除”。
- 设备已绑其他患者时显示后端脱敏冲突信息。

- [ ] **Step 2: 运行失败测试**

Run: `cd frontend && npm run test -- DeviceInventoryPage ProjectPatientBindingCard WearableBindingPanel`

Expected: FAIL。

- [ ] **Step 3: 创建设备台账**

页面包含：

- 搜索固定简码、厂商标识。
- 筛选已绑定、未绑定、停用。
- 新增设备 Modal：`provider`、`external_device_id`、`identifier_type`、`model`。
- 表格：固定简码、型号、当前患者、最近通信、最近同步、操作。
- 不在列表展示位置字段。

路由使用 `/wearable-devices`，侧边栏文案“设备台账”；它是基础管理入口，不承载患者健康趋势。

- [ ] **Step 4: 升级项目患者绑定区域**

保留 `ProjectPatientBindingCard` 作为外层组件：

```tsx
<Typography.Title level={5}>患者接入</Typography.Title>
<MiniappBindingSection projectPatientId={projectPatientId} />
<WearableBindingPanel projectPatientId={projectPatientId} />
```

绑定后自动调用 `check-status`；通信失败只显示 Warning，不撤销本地绑定。响铃按钮仅在后端返回 `capabilities.ring === true` 时出现。

- [ ] **Step 5: 运行测试**

Run: `cd frontend && npm run test -- DeviceInventoryPage ProjectPatientBindingCard WearableBindingPanel`

Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/wearables frontend/src/pages/research-entry frontend/src/app
git commit -m "feat(frontend): 增加设备台账与患者设备绑定"
```

---

### Task 9: 把训练追踪升级为“训练与健康”双页签

**Files:**
- Create: `frontend/src/pages/wearables/WearableHealthTab.tsx`
- Create: `frontend/src/pages/wearables/WearableHealthTab.test.tsx`
- Create: `frontend/src/pages/wearables/WearableMetricChart.tsx`
- Modify: `frontend/src/pages/wearables/types.ts`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingPage.test.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`
- Modify: `frontend/src/pages/training-tracking/TrainingTrackingDetailPage.test.tsx`
- Modify: `frontend/src/pages/training-tracking/types.ts`
- Modify: `frontend/src/app/layout/AdminLayout.tsx`

**Interfaces:**
- Produces: 用户可见一级类目“训练与健康”，详情双页签。
- Consumes: 现有训练追踪 API 和 Task 7 穿戴查询 API。

- [ ] **Step 1: 写双页签失败测试**

断言：

```tsx
expect(screen.getByRole("tab", { name: "训练跟踪" })).toBeInTheDocument()
expect(screen.getByRole("tab", { name: "穿戴健康" })).toBeInTheDocument()
expect(screen.queryByText("设备在线")).not.toBeInTheDocument()
```

同时覆盖：

- 侧边栏和页面标题为“训练与健康”。
- 默认页签是“训练跟踪”，现有训练图表和录像按钮仍存在。
- 切换“穿戴健康”后加载设备摘要、日期、指标、间隔、趋势和日汇总。
- 步数模式隐藏日内间隔并只显示日总量。
- 未绑定设备时显示绑定引导，不显示主动测量。
- 未验证型号时远程操作按钮禁用并显示原因。
- 页面不存在“CRF 关联数据”或“预览 CRF”按钮。

- [ ] **Step 2: 运行失败测试**

Run: `cd frontend && npm run test -- TrainingTrackingPage TrainingTrackingDetailPage WearableHealthTab`

Expected: FAIL。

- [ ] **Step 3: 升级列表文案和字段**

- `患者训练追踪` 改为 `患者训练与健康`。
- “查看追踪”改为“查看训练与健康”。
- 增加“设备绑定”“最近健康同步”“近 30 天数据完整率”列。
- 保留现有 `/training-tracking` 和 `/training-tracking/patients/:id` 路由，避免旧链接失效。

- [ ] **Step 4: 增加详情双页签**

患者、项目选择器和研究周期描述放在 Tabs 外部共享。Tabs key：

```tsx
items={[
  { key: "training", label: "训练跟踪", children: <TrainingTrackingContent data={data} /> },
  { key: "wearable", label: "穿戴健康", children: <WearableHealthTab {...props} /> },
]}
```

把现有训练详情 JSX 提取为同文件内 `TrainingTrackingContent`，不修改训练统计和录像逻辑。

`WearableMetricChart` 支持心率单线、血压收缩/舒张双线、血氧单线。筛选间隔为 `raw/5m/15m/30m/1h`；步数只用日汇总表和日趋势。

- [ ] **Step 5: 运行前端测试、lint 和构建**

Run: `cd frontend && npm run test && npm run lint && npm run build`

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add frontend/src/pages/training-tracking frontend/src/pages/wearables frontend/src/app/layout/AdminLayout.tsx
git commit -m "feat(frontend): 升级训练与健康双页签"
```

---

### Task 10: 移除后端和 Web 手工健康能力

**Files:**
- Create: `backend/apps/health/migrations/0002_delete_dailyhealthrecord.py`
- Modify: `backend/apps/health/models.py`
- Modify: `backend/apps/health/serializers.py`
- Modify: `backend/apps/health/views.py`
- Modify: `backend/apps/health/urls.py`
- Modify: `backend/apps/health/tests/test_daily_health_unique.py`
- Modify: `backend/config/urls.py`
- Delete: `frontend/src/pages/health/DailyHealthPage.tsx`
- Modify: `frontend/src/app/App.tsx`
- Modify: `frontend/src/app/App.test.tsx`

**Interfaces:**
- Produces: 不再存在可写手工健康 API 和 Web 页面。
- Consumes: Task 1 新穿戴日汇总，不复用旧 `DailyHealthRecord`。

- [ ] **Step 1: 写能力移除测试**

```python
@pytest.mark.django_db
def test_manual_health_api_is_removed(doctor):
    client = APIClient()
    client.force_authenticate(doctor)
    response = client.post("/api/health/", {"record_date": "2026-07-22", "steps": 1000})
    assert response.status_code == 404
```

前端测试访问 `/health` 应重定向到默认页面，且应用中不出现“保存健康数据”。

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest apps/health/tests -q && cd ../frontend && npm run test -- App`

Expected: FAIL，旧接口和页面仍存在。

- [ ] **Step 3: 创建带数据保护的删除 migration**

Migration 必须先检查：

```python
def assert_no_manual_health_records(apps, schema_editor):
    DailyHealthRecord = apps.get_model("health", "DailyHealthRecord")
    if DailyHealthRecord.objects.exists():
        raise RuntimeError("检测到手工健康数据，停止删除；请先确认归档策略")
```

operations 顺序：

```python
migrations.RunPython(assert_no_manual_health_records, migrations.RunPython.noop),
migrations.DeleteModel(name="DailyHealthRecord"),
```

保留 `apps.health` 在 `INSTALLED_APPS` 中，以确保部署时 deletion migration 会执行；只移除 URL、模型业务代码和测试。

- [ ] **Step 4: 删除 Web 路由和页面**

- 从 `backend/config/urls.py` 删除 `path("api/health/", ...)`。
- 从 `frontend/src/app/App.tsx` 删除 `DailyHealthPage` import 和 `/health` Route。
- 删除 `DailyHealthPage.tsx`。

- [ ] **Step 5: 运行 migration 和测试**

Run: `cd backend && python manage.py makemigrations --check && pytest apps/health/tests tests/test_api_smoke.py -q`

Run: `cd frontend && npm run test -- App`

Expected: PASS；`/api/health/` 为 404。

- [ ] **Step 6: 提交**

```bash
git add -A backend/apps/health backend/config/urls.py frontend/src/app frontend/src/pages/health
git commit -m "refactor(health): 移除手工健康录入"
```

---

### Task 11: 移除微信小程序健康填报

**Files:**
- Modify: `backend/apps/patient_app/views.py`
- Modify: `backend/apps/patient_app/serializers.py`
- Modify: `backend/apps/patient_app/urls.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_api.py`
- Modify: `miniapp/src/app.config.ts`
- Modify: `miniapp/src/pages/home/index.tsx`
- Create: `miniapp/src/pages/home/homeActions.ts`
- Create: `miniapp/src/pages/home/homeActions.test.ts`
- Modify: `miniapp/src/types/patientApp.ts`
- Delete: `miniapp/src/pages/daily-health/index.tsx`

**Interfaces:**
- Produces: 患者端首页、类型和路由不再依赖健康填报。
- Consumes: 现有患者端绑定、处方和训练接口保持不变。

- [ ] **Step 1: 写患者端能力移除测试**

后端：

```python
def test_patient_app_daily_health_endpoint_is_removed(project_patient, doctor):
    client = _auth_client(project_patient, doctor)
    response = client.get("/api/patient-app/daily-health/today/")
    assert response.status_code == 404


def test_patient_app_home_has_no_manual_health_flag(project_patient, doctor):
    client = _auth_client(project_patient, doctor)
    response = client.get("/api/patient-app/home/")
    assert "has_daily_health_today" not in response.data
```

`homeActions.test.ts` 断言首页快捷操作不包含健康填报：

```typescript
import { HOME_ACTIONS } from "./homeActions"

it("does not expose manual health entry", () => {
  expect(HOME_ACTIONS.some((item) => item.key === "daily-health")).toBe(false)
})
```

- [ ] **Step 2: 运行失败测试**

Run: `cd backend && pytest apps/patient_app/tests/test_patient_app_api.py -q`

Run: `cd miniapp && npm run test`

Expected: FAIL，旧接口和入口仍存在。

- [ ] **Step 3: 删除后端患者端健康代码**

- 删除 `DailyHealthRecord` import。
- 删除 `PatientAppDailyHealthSerializer`。
- 删除 `PatientAppDailyHealthTodayView`。
- 删除 `daily-health/today/` URL。
- 从 `PatientAppHomeView` 响应删除 `has_daily_health_today`。

- [ ] **Step 4: 删除小程序页面和入口**

- 从 `app.config.ts` pages 删除 `pages/daily-health/index`。
- 删除页面文件。
- 新建 `HOME_ACTIONS` 常量并让首页从该常量渲染处方、训练和历史入口；常量不包含健康填报。
- 从首页删除健康状态卡片和跳转按钮。
- 从 `PatientAppHome` 类型删除 `has_daily_health_today`。

- [ ] **Step 5: 运行测试和构建**

Run: `cd backend && pytest apps/patient_app/tests -q`

Run: `cd miniapp && npm run test && npm run build:weapp`

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add -A backend/apps/patient_app miniapp/src
git commit -m "refactor(patient-app): 移除患者手工健康填报"
```

---

### Task 12: 完成配置、CRF 回归和全量验证

**Files:**
- Modify: `.env.example`
- Modify: `deploy/env.production.example`
- Modify: `backend/tests/test_settings.py`
- Modify: `backend/apps/crf/tests/test_crf_aggregate.py`
- Modify: `frontend/src/pages/crf/CrfPreviewPage.test.tsx`

**Interfaces:**
- Produces: 可部署配置、文档索引、CRF 不变的回归证据。
- Consumes: Tasks 1–11 全部能力。

- [ ] **Step 1: 增加配置失败测试**

`backend/tests/test_settings.py` 断言：

```python
assert settings.TIME_ZONE == "Asia/Shanghai"
assert settings.CELERY_TIMEZONE == "Asia/Shanghai"
assert "apps.wearables" in settings.INSTALLED_APPS
assert settings.MIWITRACKER_BASE_URL.startswith("https://")
```

CRF 测试断言 preview 顶层 key 仍严格为：

```python
{
    "project_patient_id",
    "patient",
    "patient_baseline",
    "project",
    "group",
    "visits",
    "missing_fields",
}
```

- [ ] **Step 2: 运行针对性回归**

Run: `cd backend && pytest apps/crf/tests tests/test_settings.py -q`

Expected: PASS；CRF 响应无穿戴健康字段。

- [ ] **Step 3: 运行后端全量验证**

Run: `cd backend && python manage.py makemigrations --check && pytest`

Expected: 全部 PASS。

- [ ] **Step 4: 运行前端全量验证**

Run: `cd frontend && npm run test && npm run lint && npm run build`

Expected: 全部 PASS。

- [ ] **Step 5: 运行小程序全量验证**

Run: `cd miniapp && npm run test && npm run build:weapp`

Expected: 全部 PASS。

- [ ] **Step 6: 人工验收关键链路**

按顺序验证：

1. 录入一台设备并取得固定四位简码。
2. 在项目患者页生成小程序临时码，确认两种码文案不同。
3. 输入设备固定简码绑定患者。
4. 查看本地绑定成功和通信测试结果分开展示。
5. 进入“训练与健康”，切换“训练跟踪/穿戴健康”。
6. 确认页签名旁没有设备在线标签。
7. 查看心率、血压、血氧趋势和日步数。
8. 解绑并改绑另一患者，确认新患者看不到旧患者原始点。
9. 确认 Web、小程序均无手工健康入口。
10. 打开 CRF 预览和导出，确认没有穿戴健康内容。

- [ ] **Step 7: 最终提交**

```bash
git add .env.example deploy/env.production.example backend frontend miniapp
git commit -m "chore(wearables): 完成穿戴接入回归与交付"
```

---

## 自检结果

- 设计稿中的设备台账、全局患者绑定、四位简码、通信测试、解绑区间、OpenAPI、动态七天补拉、原始点、日汇总、主动命令、双页签、研究汇总和移除手工录入均有对应任务。
- 同日换绑整日步数排除在 Task 4 有独立测试。
- 最近七天已解绑设备继续补拉在 Task 5 有独立测试。
- CRF 完全不变在 Task 7 和 Task 12 有后端与前端回归。
- 未验证型号安全关闭远程命令在 Task 6 有独立测试。
- 计划不包含需要执行者猜测的型号命令；生产能力映射默认空，只有现场验证后才显式启用。
- 所有提交说明均为中文。
