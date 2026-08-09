# 穿戴设备管理权限与 IMEI 录入实施计划

> 执行记录（2026-08-09, Codex）：Task 1–4 已落地于 `844ccf3`，并通过 `e391fd6` 合并到 `main`。
> 最终审查修订（2026-08-09, Codex）：补强跨厂商 IMEI 去重、通信测试自动识别型号、历史标识展示与前端规范化。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让所有医生都能管理任意已入组患者的穿戴设备，并把设备新增流程简化为只录入 15 位 IMEI。

**Architecture:** 在 `wearables` 应用内建立独立的设备管理权限查询，避免继续复用训练数据权限；设备创建接口以 `imei` 为唯一写入参数，在服务端补全现有身份字段并沿用四位简码生成器。前端只调整设备管理名称、IMEI 表单与列表，不改变路由、小程序或健康数据查询。

**Tech Stack:** Django 5、Django REST Framework、pytest-django、React 18、TypeScript、Ant Design 5、TanStack Query v5、Vitest、Testing Library。

## Global Constraints

- 所有医生和管理员均可管理任意已存在 `ProjectPatient` 的穿戴设备。
- 未入组患者没有绑定入口，不允许通过项目患者绑定接口创建绑定。
- 训练、视频、健康趋势及健康测量查询继续使用原有数据权限。
- 新增设备只接受字段 `imei`，规范化后必须是 15 位纯数字。
- 服务端固定补全 `provider="miwitracker"`、`identifier_type="imei"`、`model=""`、`enabled=true`。
- 四位固定简码必须唯一、保留前导零并继续处理并发碰撞。
- 保留所有现有数据库字段和历史数据，不新增迁移。
- “设备台账”用户界面文案统一改为“设备管理”，路由仍为 `/wearable-devices`。
- 不修改小程序端。
- 未经用户明确授权，不执行本计划中的 Git 提交步骤。

---

## 文件结构

- 新建 `backend/apps/wearables/permissions.py`：只负责设备管理范围，提供 `manageable_project_patients(user)`。
- 修改 `backend/apps/wearables/views.py`：设备管理、绑定与命令接口改用新的管理范围；健康数据查询不动。
- 修改 `backend/apps/wearables/serializers.py`：设备创建只接收 IMEI，补全既有字段并保留简码并发保护。
- 修改 `backend/apps/wearables/services/commands.py`：通信测试在设备型号为空时持久化厂商识别型号，并立即按该型号计算能力。
- 修改 `backend/apps/wearables/tests/test_binding_api.py`：覆盖跨医生管理权限、IMEI 创建、校验、重复和简码行为。
- 修改 `backend/apps/wearables/tests/test_commands.py`：同步设备命令接口的跨医生权限回归，并覆盖空型号设备的通信识别链路。
- 修改 `frontend/src/pages/wearables/DeviceInventoryPage.tsx`：设备管理文案、IMEI 单字段表单与列表列。
- 修改 `frontend/src/pages/wearables/DeviceInventoryPage.test.tsx`：覆盖新表单、校验、提交载荷和展示。
- 修改 `frontend/src/app/layout/AdminLayout.tsx`、`frontend/src/app/App.test.tsx`：菜单更名及路由回归。
- 修改 `specs/patient-rehab-system/changelog.md`：追加本次已确认行为变更。
- 修改 `specs/patient-rehab-system/prd.md`：把核心流程同步为“设备管理 + 15 位 IMEI”。
- 修改 `docs/superpowers/specs/2026-07-23-wearable-openapi-integration-design.md`：记录被本设计覆盖的旧录入规则。
- 修改本设计与本计划：实施完成后记录状态和执行 commit；仅在用户授权提交后填写 commit。

### Task 1: 建立独立的穿戴设备管理权限

**Files:**
- Create: `backend/apps/wearables/permissions.py`
- Modify: `backend/apps/wearables/views.py`
- Test: `backend/apps/wearables/tests/test_binding_api.py`
- Test: `backend/apps/wearables/tests/test_commands.py`

**Interfaces:**
- Consumes: `apps.accounts.models.User` 的 `Role`，`apps.studies.models.ProjectPatient`。
- Produces: `manageable_project_patients(user) -> QuerySet[ProjectPatient]`；医生和管理员返回全部已入组关系，其他身份返回空查询集。

- [x] **Step 1: 写入跨医生管理的失败测试**

在 `test_binding_api.py` 新增辅助对象与用例：患者主治医生、项目创建人和入组创建人均为另一名医生，当前医生仍能读取状态、绑定、通信测试和解绑。

```python
@pytest.mark.django_db
def test_any_doctor_can_manage_wearable_for_enrolled_patient(
    api_client, doctor, wearable_device, monkeypatch
):
    owner = User.objects.create_user(
        phone="13800008888",
        password="pass123456",
        name="项目医生",
        role=User.Role.DOCTOR,
    )
    patient = Patient.objects.create(
        name="跨医生患者",
        gender=Patient.Gender.UNKNOWN,
        age=66,
        phone="13900008888",
        primary_doctor=owner,
    )
    project = StudyProject.objects.create(name="跨医生项目", created_by=owner)
    group = StudyGroup.objects.create(project=project, name="干预组", target_ratio=1)
    project_patient = ProjectPatient.objects.create(
        project=project,
        patient=patient,
        group=group,
        created_by=owner,
    )
    monkeypatch.setattr(
        "apps.wearables.views.check_device_status",
        lambda device: {
            "device_id": device.id,
            "model": device.model,
            "online": True,
            "battery_level": 80,
            "last_communication_at": None,
            "capabilities": {"ring": False},
        },
    )
    api_client.force_authenticate(doctor)

    status_response = api_client.get(
        f"/api/wearables/project-patients/{project_patient.id}/binding/"
    )
    assert status_response.status_code == 200, status_response.data

    bind_response = api_client.post(
        f"/api/wearables/project-patients/{project_patient.id}/bind/",
        {"short_code": wearable_device.short_code},
        format="json",
    )
    assert bind_response.status_code == 201, bind_response.data

    check_response = api_client.post(
        f"/api/wearables/devices/{wearable_device.id}/check-status/",
        format="json",
    )
    assert check_response.status_code == 200, check_response.data

    unbind_response = api_client.post(
        f"/api/wearables/bindings/{bind_response.data['id']}/unbind/",
        format="json",
    )
    assert unbind_response.status_code == 200, unbind_response.data
```

同时新增不存在项目患者的边界用例：

```python
@pytest.mark.django_db
def test_wearable_binding_status_rejects_missing_project_patient(api_client, doctor):
    api_client.force_authenticate(doctor)

    response = api_client.get("/api/wearables/project-patients/999999/binding/")

    assert response.status_code == 404
```

- [x] **Step 2: 运行权限测试确认 RED**

Run:

```bash
cd backend
pytest apps/wearables/tests/test_binding_api.py::test_any_doctor_can_manage_wearable_for_enrolled_patient apps/wearables/tests/test_binding_api.py::test_wearable_binding_status_rejects_missing_project_patient -q
```

Expected: 第一条测试在设备绑定状态请求处得到 404；第二条测试通过。

- [x] **Step 3: 实现设备管理范围**

新建 `permissions.py`：

```python
from apps.accounts.models import User
from apps.studies.models import ProjectPatient


def manageable_project_patients(user):
    queryset = ProjectPatient.objects.select_related("patient", "project", "group")
    if not getattr(user, "is_authenticated", False):
        return queryset.none()
    if user.role not in {User.Role.SUPER_ADMIN, User.Role.ADMIN, User.Role.DOCTOR}:
        return queryset.none()
    return queryset
```

在 `views.py` 中导入该函数，并把以下设备管理路径中的 `accessible_project_patients()` 替换为
`manageable_project_patients()`：

```python
from .permissions import manageable_project_patients
```

- `_active_patient_binding()`；
- `_device_queryset_for_user()`；
- `_device_for_management()`；
- `ProjectPatientBindingStatusView.get()`；
- `ProjectPatientBindView.post()`，包括冲突患者脱敏名称查询；
- `WearableBindingUnbindView.post()`。

不要修改 `services/queries.py` 中的 `resolve_patient_scope()`，也不要修改训练模块的
`accessible_project_patients()`。

- [x] **Step 4: 运行权限测试确认 GREEN**

Run:

```bash
cd backend
pytest apps/wearables/tests/test_binding_api.py -q
```

Expected: 全部通过；原来“外部患者名称不可见”的测试需要按新规则改为可见的脱敏名称，因为所有
已入组患者现在都属于设备管理范围。

- [ ] **Step 5: 在用户已授权提交时创建中文提交**

```bash
git add backend/apps/wearables/permissions.py backend/apps/wearables/views.py backend/apps/wearables/tests/test_binding_api.py backend/apps/wearables/tests/test_commands.py
git commit -m "fix(wearables): 统一已入组患者设备管理权限"
```

### Task 2: 把设备创建接口收敛为 IMEI

**Files:**
- Modify: `backend/apps/wearables/serializers.py`
- Modify: `backend/apps/wearables/views.py`
- Modify: `backend/apps/wearables/services/commands.py`
- Test: `backend/apps/wearables/tests/test_binding_api.py`
- Test: `backend/apps/wearables/tests/test_commands.py`

**Interfaces:**
- Consumes: `generate_device_short_code() -> str` 与 `WearableDevice` 现有唯一约束。
- Produces: `POST /api/wearables/devices/` 请求 `{ "imei": "15位数字" }`；响应继续返回完整 `WearableDeviceSerializer` 字段。

- [x] **Step 1: 把设备创建测试改为新契约并先确认失败**

把测试辅助函数改为：

```python
def _device_payload(**overrides):
    payload = {"imei": "860123456789012"}
    payload.update(overrides)
    return payload
```

新增或更新下列断言：

```python
@pytest.mark.django_db
def test_device_create_from_imei_fills_identity_defaults_and_short_code(
    api_client, doctor
):
    api_client.force_authenticate(doctor)

    response = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert response.status_code == 201, response.data
    assert response.data["provider"] == "miwitracker"
    assert response.data["external_device_id"] == "860123456789012"
    assert response.data["identifier_type"] == "imei"
    assert response.data["model"] == ""
    assert response.data["enabled"] is True
    assert re.fullmatch(r"\d{4}", response.data["short_code"])
```

```python
@pytest.mark.django_db
@pytest.mark.parametrize("imei", ["", "12345678901234", "1234567890123456", "12345678901234A"])
def test_device_create_rejects_invalid_imei(api_client, doctor, imei):
    api_client.force_authenticate(doctor)

    response = api_client.post("/api/wearables/devices/", {"imei": imei}, format="json")

    assert response.status_code == 400, response.data
    assert "imei" in response.data
```

```python
@pytest.mark.django_db
def test_device_create_reports_duplicate_imei(api_client, doctor):
    api_client.force_authenticate(doctor)
    first = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    duplicate = api_client.post("/api/wearables/devices/", _device_payload(), format="json")

    assert first.status_code == 201, first.data
    assert duplicate.status_code == 409, duplicate.data
    assert duplicate.data == {"detail": "该 IMEI 已存在。"}
```

同步更新简码碰撞测试，使所有创建设备请求只传 `imei`，并为每次真正新增使用不同的合法 IMEI。

- [x] **Step 2: 运行创建接口测试确认 RED**

Run:

```bash
cd backend
pytest apps/wearables/tests/test_binding_api.py -q
```

Expected: IMEI 新契约测试因 `imei` 不是现有序列化字段而失败。

- [x] **Step 3: 实现 IMEI 序列化与服务端默认值**

在 `WearableDeviceSerializer` 增加：

```python
imei = serializers.RegexField(
    r"^[0-9]{15}$",
    write_only=True,
    required=False,
    trim_whitespace=True,
    error_messages={"invalid": "IMEI 必须是 15 位数字。"},
)
```

把 `imei` 加入 `fields` 和 `IDENTITY_FIELDS`。在 `validate()` 中保证创建只能提交 `imei`，
并在 `Meta.extra_kwargs` 中把 `provider`、`external_device_id`、`identifier_type` 和 `model`
设为 `required=False`，避免模型字段在 IMEI 映射前触发必填校验。验证逻辑使用：

```python
def validate(self, attrs):
    provided_fields = set(self.initial_data.keys())
    if self.instance is None:
        rejected_fields = provided_fields - {"imei"}
        if rejected_fields:
            raise serializers.ValidationError(
                {field: "新增设备只允许提交 IMEI。" for field in rejected_fields}
            )
        if "imei" not in attrs:
            raise serializers.ValidationError({"imei": "请输入 IMEI。"})
        return attrs

    rejected_fields = provided_fields - self.UPDATEABLE_FIELDS
    if rejected_fields:
        errors = {}
        for field in rejected_fields:
            if field in self.IDENTITY_FIELDS:
                errors[field] = "设备真实身份字段创建后不可修改。"
            else:
                errors[field] = "该字段不可通过设备管理接口修改。"
        raise serializers.ValidationError(errors)
    return attrs
```

更新仍只允许 `model` 和 `enabled`。

将 `create()` 改为先构造固定字段，再沿用原来的简码重试：

```python
def create(self, validated_data):
    imei = validated_data.pop("imei")
    if WearableDevice.objects.filter(
        identifier_type="imei",
        external_device_id=imei,
    ).exists():
        raise IntegrityError("duplicate IMEI")
    device_values = {
        "provider": "miwitracker",
        "external_device_id": imei,
        "identifier_type": "imei",
        "model": "",
        "enabled": True,
    }
    for _ in range(32):
        try:
            with transaction.atomic():
                return WearableDevice.objects.create(
                    short_code=generate_device_short_code(),
                    **device_values,
                )
        except IntegrityError:
            if WearableDevice.objects.filter(
                provider="miwitracker",
                external_device_id=imei,
            ).exists():
                raise
    raise ShortCodeExhausted("设备固定简码生成冲突，请重试。")
```

创建测试同时覆盖：历史设备属于其他 provider，但 `identifier_type="imei"` 且 IMEI 相同时，
新增接口仍返回 `409 {"detail": "该 IMEI 已存在。"}`。

在 `check_device_status()` 中，设备现有型号为空且厂商响应的设备标识与请求设备一致时，保存厂商
返回的非空型号，并在同次通信测试中按该型号计算能力；已有型号不被覆盖。响应设备标识不一致或
型号超过数据库字段长度上限时，抛出厂商通信错误且不更新状态。对应命令测试覆盖“空型号设备 →
通信测试识别型号 → 型号能力命令可用”、标识不匹配和超长型号三个分支。

在 `WearableDeviceListCreateView.create()` 的 `IntegrityError` 分支返回：

```python
return Response({"detail": "该 IMEI 已存在。"}, status=status.HTTP_409_CONFLICT)
```

不修改模型字段和 migration。

- [x] **Step 4: 运行接口测试确认 GREEN**

Run:

```bash
cd backend
pytest apps/wearables/tests/test_binding_api.py apps/wearables/tests/test_commands.py -q
python manage.py makemigrations --check --dry-run
```

Expected: 测试全部通过；Django 输出 `No changes detected`。

- [ ] **Step 5: 在用户已授权提交时创建中文提交**

```bash
git add backend/apps/wearables/serializers.py backend/apps/wearables/views.py backend/apps/wearables/services/commands.py backend/apps/wearables/tests/test_binding_api.py backend/apps/wearables/tests/test_commands.py
git commit -m "feat(wearables): 支持仅凭IMEI录入设备"
```

### Task 3: 更新设备管理页面

**Files:**
- Modify: `frontend/src/pages/wearables/DeviceInventoryPage.tsx`
- Modify: `frontend/src/pages/wearables/DeviceInventoryPage.test.tsx`
- Modify: `frontend/src/app/layout/AdminLayout.tsx`
- Modify: `frontend/src/app/App.test.tsx`

**Interfaces:**
- Consumes: `POST /wearables/devices/` 的 `{ imei: string }` 请求及完整设备响应。
- Produces: “设备管理”页面、15 位 IMEI 单字段弹窗、IMEI 列和“搜索固定简码或 IMEI”。

- [x] **Step 1: 先更新前端测试表达新行为**

把 `DeviceInventoryPage.test.tsx` 的创建用例改为：

```tsx
it("只填写十五位IMEI即可录入并展示系统固定简码", async () => {
  mockPost.mockResolvedValue({
    data: device({ external_device_id: "860123456789012" }),
  });
  renderPage();

  expect(await screen.findByText("设备管理")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "新增设备" }));
  expect(screen.queryByLabelText("厂商")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("标识类型")).not.toBeInTheDocument();
  expect(screen.queryByLabelText("设备型号")).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("IMEI"), {
    target: { value: "860123456789012" },
  });
  fireEvent.click(screen.getByRole("button", { name: "录入设备" }));

  expect(await screen.findByText("0826")).toBeInTheDocument();
  expect(screen.getByText("860123456789012")).toBeInTheDocument();
  expect(mockPost).toHaveBeenCalledWith("/wearables/devices/", {
    imei: "860123456789012",
  });
});
```

新增无效 IMEI 不提交测试：

```tsx
it("拒绝非十五位数字IMEI", async () => {
  renderPage();
  fireEvent.click(await screen.findByRole("button", { name: "新增设备" }));
  fireEvent.change(screen.getByLabelText("IMEI"), { target: { value: "1234A" } });
  fireEvent.click(screen.getByRole("button", { name: "录入设备" }));

  expect(await screen.findByText("IMEI 必须是 15 位数字")).toBeInTheDocument();
  expect(mockPost).not.toHaveBeenCalled();
});
```

把 `App.test.tsx` 的路由断言改为查找“设备管理”。

- [x] **Step 2: 运行前端测试确认 RED**

Run:

```bash
cd frontend
npm run test -- src/pages/wearables/DeviceInventoryPage.test.tsx src/app/App.test.tsx
```

Expected: 因旧标题和旧四字段表单而失败。

- [x] **Step 3: 实现菜单、页面和表单调整**

在 `AdminLayout.tsx` 把菜单标签改为“设备管理”。

在 `DeviceInventoryPage.tsx`：

```tsx
type DeviceFormValues = { imei: string };
```

创建请求只提交：

```tsx
await apiClient.post<WearableDevice>("/wearables/devices/", {
  imei: values.imei.trim(),
});
```

把页面标题和加载错误改为“设备管理”，搜索框文案改为“搜索固定简码或 IMEI”，并在表格固定
简码之后新增：

```tsx
{
  title: "IMEI",
  dataIndex: "external_device_id",
  width: 180,
  render: (value: string, device: WearableDevice) =>
    device.identifier_type === "imei" ? value : "—",
}
```

新增设备 Modal 只保留：

```tsx
<Form.Item
  label="IMEI"
  name="imei"
  rules={[
    { required: true, message: "请输入 IMEI" },
    {
      transform: (value: string) => value.trim(),
      pattern: /^\d{15}$/,
      message: "IMEI 必须是 15 位数字",
    },
  ]}
>
  <Input inputMode="numeric" placeholder="请输入设备的 15 位 IMEI" />
</Form.Item>
```

加载失败固定展示“设备管理加载失败”，不透传后端内部错误；前端测试同时覆盖历史非 IMEI 标识、
带首尾空格的合法 IMEI 和加载失败文案。

- [x] **Step 4: 运行前端目标测试确认 GREEN**

Run:

```bash
cd frontend
npm run test -- src/pages/wearables/DeviceInventoryPage.test.tsx src/app/App.test.tsx
```

Expected: 全部通过。

- [ ] **Step 5: 在用户已授权提交时创建中文提交**

```bash
git add frontend/src/pages/wearables/DeviceInventoryPage.tsx frontend/src/pages/wearables/DeviceInventoryPage.test.tsx frontend/src/app/layout/AdminLayout.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): 简化设备管理IMEI录入"
```

### Task 4: 文档收口与完整验证

**Files:**
- Modify: `specs/patient-rehab-system/changelog.md`
- Modify: `specs/patient-rehab-system/prd.md`
- Modify: `docs/superpowers/README.md`
- Modify: `docs/superpowers/specs/2026-07-23-wearable-openapi-integration-design.md`
- Modify: `docs/superpowers/specs/2026-08-09-wearable-management-permission-design.md`
- Modify: `docs/superpowers/plans/2026-08-09-wearable-management-permission-and-imei-entry.md`

**Interfaces:**
- Consumes: Task 1-3 的最终行为和测试结果。
- Produces: 追加式变更记录、工作区实施状态、核心 PRD 与历史覆盖说明、完整验证证据。

- [x] **Step 1: 追加变更日志并更新实施状态**

在 `specs/patient-rehab-system/changelog.md` 顶部日期区域追加，不修改历史条目：

```markdown
- 穿戴设备管理权限改为所有医生和管理员均可管理任意已入组患者，不再复用训练数据权限。
- “设备台账”更名为“设备管理”；新增设备只录入 15 位 IMEI，其余身份字段和四位固定简码由服务端生成。
```

工作区实现但尚未提交、合并时，设计状态保持 `implementing`；合并 main 后才能改为
`implemented`。在本计划顶部追加实际执行记录；只有存在提交时才填写真实 short SHA，否则写明
“工作区实现，未提交”，不得伪造 commit。

- [x] **Step 2: 运行后端完整验证**

Run:

```bash
cd backend
pytest
python manage.py makemigrations --check --dry-run
```

Expected: 全部测试通过；无待生成 migration。

- [x] **Step 3: 运行前端完整验证**

Run:

```bash
cd frontend
npm run test
npm run lint
npm run build
```

Expected: 测试、lint 和生产构建全部通过，无新增错误。

- [x] **Step 4: 检查最终差异只包含批准范围**

Run:

```bash
git status --short
git diff --check
git diff --stat
```

Expected: 仅包含本计划列出的后端、前端、spec、plan 和 changelog 文件；无空白错误。

- [ ] **Step 5: 在用户已授权提交时创建中文收口提交**

```bash
git add docs/superpowers/README.md docs/superpowers/specs/2026-07-23-wearable-openapi-integration-design.md docs/superpowers/specs/2026-08-09-wearable-management-permission-design.md docs/superpowers/plans/2026-08-09-wearable-management-permission-and-imei-entry.md specs/patient-rehab-system/changelog.md specs/patient-rehab-system/prd.md
git commit -m "docs(wearables): 记录设备管理权限与IMEI录入"
```
