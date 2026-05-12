# 患者列表 / 详情 / 独立编辑页 Implementation Plan

执行记录（2026-05-12, Cursor）：Task 1–8 已在会话内落地；验证：`backend pytest` 46 passed，`frontend` vitest 18 passed、`npm run lint`、`npm run build` 通过。未执行 git commit（遵循 AGENTS「不主动提交」）。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 患者列表支持手机号脱敏、整行进详情、操作列「编辑」进 `/patients/:id/edit`、「删除」带二次确认；去掉列表编辑 Modal；详情页改为只读展示并保留停用/删除/入组；编辑页实现生日驱动只读年龄（C2）；后端补充 `primary_doctor_name` 与生日写入时归一化 `age`。

**Architecture:** 前端新增轻量工具模块（脱敏、周岁计算）、可选共享「删除影响」文案构建函数供列表与详情复用；`PatientDetailPage` 拆为 Descriptions + 原有业务块，`PatientEditPage` 承载原 PATCH 表单逻辑；路由将 `/patients/:patientId/edit` 置于 `/patients/:patientId` 之前避免把 `edit` 解析为 id。后端在 `PatientSerializer` 增加只读 `primary_doctor_name`，并在 `validate` 中在显式提交 `birth_date` 时同步 `age`（空生日则 `age` 置空）。

**Tech Stack:** Django 5、DRF、pytest；React 18、TypeScript、Vite、Vitest、TanStack Query v5、Ant Design 5、React Router 6、dayjs。

**关联设计（实施前请先落盘或确认已存在）：** `docs/superpowers/specs/2026-05-12-patient-list-detail-edit-routing-design.md`（若尚无文件，按 Task 1 全文创建）。与 `docs/superpowers/specs/2026-05-11-patient-list-actions-privacy-design.md` 的关系：本计划 **取代** 其中「姓名链进详情」「列表编辑 Modal」等已过期段落，其余（脱敏形状、删除守卫文案、`primary_doctor_name`）与之对齐。

---

## 文件结构（将创建 / 修改）

| 路径 | 职责 |
|------|------|
| `docs/superpowers/specs/2026-05-12-patient-list-detail-edit-routing-design.md` | 冻结本次已确认需求与边界 |
| `backend/apps/patients/serializers.py` | `primary_doctor_name`、`validate` 归一化 `age` |
| `backend/apps/patients/tests/test_patient_serializer_primary_doctor_name.py` | 序列化字段与 `age` 归一化测试 |
| `frontend/src/pages/patients/phoneMask.ts` | 列表手机号脱敏纯函数 |
| `frontend/src/pages/patients/phoneMask.test.ts` | 脱敏单元测试 |
| `frontend/src/pages/patients/ageFromBirthDate.ts` | 按「今天」计算周岁（与后端算法一致） |
| `frontend/src/pages/patients/ageFromBirthDate.test.ts` | 周岁边界用例 |
| `frontend/src/pages/patients/patientDeleteModalCopy.ts` | 由 `projectPatients` + 项目名映射生成删除弹窗 `blockedReason` / `impactSummary` |
| `frontend/src/pages/patients/PatientEditPage.tsx` | 编辑表单页（PATCH）、生日 → 只读年龄 |
| `frontend/src/pages/patients/PatientDetailPage.tsx` | 改为只读展示 + 跳转编辑 + 保留原动作与表格 |
| `frontend/src/pages/patients/PatientListPage.tsx` | 行点击、脱敏、操作列、删除弹窗、移除编辑 Modal |
| `frontend/src/pages/patients/PatientListPage.test.tsx` | 列表交互与脱敏 |
| `frontend/src/app/App.tsx` | 注册 `/patients/:patientId/edit` 路由（在 `:patientId` 之前） |
| `frontend/src/app/App.test.tsx` | 更新导航断言；必要时 mock `patch`/`delete` |

---

### Task 1: 设计 spec 落盘

**Files:**

- Create: `docs/superpowers/specs/2026-05-12-patient-list-detail-edit-routing-design.md`

- [ ] **Step 1: 写入下列完整内容（新建文件）**

```markdown
> 状态：approved
> 日期：2026-05-12
> 范围：患者列表、详情只读、独立编辑路由、生日驱动年龄、列表删除与脱敏
> 关联：`docs/superpowers/plans/2026-05-12-patient-list-detail-edit-routing.md`
> 取代说明：覆盖 `2026-05-11-patient-list-actions-privacy-design.md` 中「姓名链进详情」「列表 Modal 编辑」等段落；脱敏规则、删除守卫与主治医生姓名列与其一致。

# 患者列表、详情与编辑路由设计

## 列表 `/patients`

- 手机号：展示层脱敏，11 位为 `前三位 + **** + 后四位`；过短/异常时首尾各 1 位中间 `*`，空为 `—`。
- 点击表格行（`onRow`）进入 `/patients/:id`；操作列「编辑」「删除」`stopPropagation`。
- 操作列：「编辑」→ `/patients/:id/edit`；无「详情」链接；「删除」危险按钮 → 二次确认弹窗（逻辑同详情页：有关联项目则阻断并展示原因；否则可删）。成功后 `invalidateQueries(['patients'])`。
- 列：姓名、性别、年龄、手机号（脱敏）、主治医生（`primary_doctor_name`，无则 `—`）；移除「主治医生 ID」列。
- 移除列表「编辑患者」Modal 及 `editId` 相关状态与请求。

## 详情 `/patients/:id`

- 人口学信息以只读展示（`Descriptions` 或等价）；「编辑档案」按钮 → `/patients/:id/edit`。
- 保留：加入项目、停用/启用、删除、项目参与表、相关 Modal。

## 编辑 `/patients/:id/edit`

- 表单字段：姓名、性别、出生日期、年龄（只读，由出生日期与今天计算）、手机号、备注。
- 未选出生日期：年龄区展示提示文案；保存时 `birth_date: null` 且 `age: null`（与后端 validate 一致）。
- 保存成功 → 提示并 `navigate(/patients/:id)`；取消 → `navigate(-1)` 或回详情。

## 后端

- `PatientSerializer` 增加只读 `primary_doctor_name`（来自 `primary_doctor.name`）。
- 当请求体 **显式包含** `birth_date` 键时：`null` → `age` 置 `null`；有日期 → `age` 按公历周岁重算。其它 PATCH 不强行改 `age`。

## 非目标

- 新建患者 Modal 暂不强制生日 + C2（可后续迭代）。
```

- [ ] **Step 2: 自检** — 通读一遍无 `TBD`、无自相矛盾。

- [ ] **Step 3: 提交（若你允许在本仓库提交）**

```bash
git add docs/superpowers/specs/2026-05-12-patient-list-detail-edit-routing-design.md
git commit -m "docs(spec): 患者列表详情编辑路由与 C2 年龄设计"
```

---

### Task 2: 后端 `primary_doctor_name` 与 `birth_date` → `age`（TDD）

**Files:**

- Modify: `backend/apps/patients/serializers.py`
- Create: `backend/apps/patients/tests/test_patient_serializer_primary_doctor_name.py`

- [ ] **Step 1: 新建失败测试**

创建 `backend/apps/patients/tests/test_patient_serializer_primary_doctor_name.py`：

```python
import datetime

import pytest
from apps.patients.models import Patient
from apps.patients.serializers import PatientSerializer


@pytest.mark.django_db
def test_serializer_exposes_primary_doctor_name(doctor):
    p = Patient.objects.create(
        name="甲",
        gender=Patient.Gender.MALE,
        age=40,
        phone="13900000001",
        primary_doctor=doctor,
    )
    data = PatientSerializer(instance=p).data
    assert data["primary_doctor_name"] == doctor.name


@pytest.mark.django_db
def test_validate_clears_age_when_birth_date_nulled(patient):
    patient.birth_date = datetime.date(1950, 6, 1)
    patient.age = 75
    patient.save()
    ser = PatientSerializer(instance=patient, data={"birth_date": None}, partial=True)
    assert ser.is_valid(), ser.errors
    inst = ser.save()
    assert inst.birth_date is None
    assert inst.age is None


@pytest.mark.django_db
def test_validate_recomputes_age_when_birth_date_set(patient):
    patient.birth_date = None
    patient.age = 99
    patient.save()
    ser = PatientSerializer(
        instance=patient,
        data={"birth_date": datetime.date(2000, 1, 1)},
        partial=True,
    )
    assert ser.is_valid(), ser.errors
    inst = ser.save()
    assert inst.birth_date == datetime.date(2000, 1, 1)
    expected = datetime.date.today().year - 2000
    if (datetime.date.today().month, datetime.date.today().day) < (1, 1):
        expected -= 1
    assert inst.age == expected
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest apps/patients/tests/test_patient_serializer_primary_doctor_name.py -v
```

预期：导入/字段错误失败。

- [ ] **Step 3: 最小实现** — 修改 `backend/apps/patients/serializers.py`：

在文件顶部增加：

```python
import datetime
```

将 `PatientSerializer` 替换为下列等价实现（保留 `Meta` 中现有 `fields`，并入新字段与 `validate`；若 `fields` 列表顺序不同以项目惯例为准，但必须包含 `primary_doctor_name`）：

```python
class PatientSerializer(serializers.ModelSerializer):
    primary_doctor_name = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Patient
        fields = [
            "id",
            "name",
            "gender",
            "birth_date",
            "age",
            "phone",
            "primary_doctor",
            "primary_doctor_name",
            "symptom_note",
            "is_active",
        ]
        read_only_fields = ["id", "primary_doctor_name"]

    def get_primary_doctor_name(self, obj: Patient) -> str | None:
        if obj.primary_doctor_id:
            return obj.primary_doctor.name
        return None

    @staticmethod
    def _age_from_birth(birth: datetime.date) -> int:
        today = datetime.date.today()
        years = today.year - birth.year
        if (today.month, today.day) < (birth.month, birth.day):
            years -= 1
        return years

    def validate(self, attrs: dict) -> dict:
        if "birth_date" not in attrs:
            return attrs
        bd = attrs.get("birth_date")
        if bd is None:
            attrs["age"] = None
        else:
            attrs["age"] = self._age_from_birth(bd)
        return attrs
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest apps/patients/tests/test_patient_serializer_primary_doctor_name.py -v
```

预期：3 passed。

- [ ] **Step 5: 全量患者相关测试**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest apps/patients/ -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/apps/patients/serializers.py backend/apps/patients/tests/test_patient_serializer_primary_doctor_name.py
git commit -m "feat(patients): 序列化主治医生姓名并在更新生日时归一化年龄"
```

---

### Task 3: 前端脱敏与周岁工具（TDD）

**Files:**

- Create: `frontend/src/pages/patients/phoneMask.ts`
- Create: `frontend/src/pages/patients/phoneMask.test.ts`
- Create: `frontend/src/pages/patients/ageFromBirthDate.ts`
- Create: `frontend/src/pages/patients/ageFromBirthDate.test.ts`

- [ ] **Step 1: 脱敏测试文件（先写测试）**

`frontend/src/pages/patients/phoneMask.test.ts`：

```typescript
import { describe, expect, it } from "vitest";
import { maskPhoneForList } from "./phoneMask";

describe("maskPhoneForList", () => {
  it("masks standard 11-digit mainland number", () => {
    expect(maskPhoneForList("13812345678")).toBe("138****5678");
  });

  it("returns em dash for empty", () => {
    expect(maskPhoneForList("")).toBe("—");
    expect(maskPhoneForList("   ")).toBe("—");
  });

  it("strips non-digits then masks short numbers", () => {
    expect(maskPhoneForList("12")).toBe("1*2");
  });
});
```

- [ ] **Step 2: 实现 `phoneMask.ts`**

```typescript
/** 列表展示用：不改变存储值。11 位：前三 + **** + 后四；否则首尾各 1 位中间 *；空为 — */
export function maskPhoneForList(raw: string): string {
  const s = raw.trim();
  if (!s) return "—";
  const d = s.replace(/\D/g, "");
  if (d.length >= 11) {
    return `${d.slice(0, 3)}****${d.slice(-4)}`;
  }
  if (d.length <= 1) return "—";
  return `${d[0]}${"*".repeat(Math.max(1, d.length - 2))}${d[d.length - 1]}`;
}
```

运行：`cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run test -- --run src/pages/patients/phoneMask.test.ts`

- [ ] **Step 3: 周岁测试与实现**

`frontend/src/pages/patients/ageFromBirthDate.test.ts`：

```typescript
import dayjs from "dayjs";
import { describe, expect, it, vi, afterEach } from "vitest";
import { ageFromBirthDate } from "./ageFromBirthDate";

describe("ageFromBirthDate", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("returns full years before birthday this year", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-15"));
    expect(ageFromBirthDate(dayjs("2000-06-20"))).toBe(25);
  });

  it("returns full years on or after birthday this year", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-06-20"));
    expect(ageFromBirthDate(dayjs("2000-06-20"))).toBe(26);
  });
});
```

`frontend/src/pages/patients/ageFromBirthDate.ts`：

```typescript
import type { Dayjs } from "dayjs";
import dayjs from "dayjs";

/** 按「今天」公历周岁，与后端 PatientSerializer._age_from_birth 语义对齐 */
export function ageFromBirthDate(birth: Dayjs): number {
  const today = dayjs();
  let years = today.year() - birth.year();
  if (today.month() < birth.month() || (today.month() === birth.month() && today.date() < birth.date())) {
    years -= 1;
  }
  return years;
}
```

运行：`cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run test -- --run src/pages/patients/ageFromBirthDate.test.ts`

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/patients/phoneMask.ts frontend/src/pages/patients/phoneMask.test.ts frontend/src/pages/patients/ageFromBirthDate.ts frontend/src/pages/patients/ageFromBirthDate.test.ts
git commit -m "feat(frontend): 患者列表手机号脱敏与周岁计算工具"
```

---

### Task 4: 删除弹窗文案共享模块

**Files:**

- Create: `frontend/src/pages/patients/patientDeleteModalCopy.ts`

- [ ] **Step 1: 从 `PatientDetailPage.tsx` 抽出与 `deleteImpactBlocked` / `deleteImpactSummary` 相同语义的纯函数**

实现 `patientDeleteModalCopy.ts`（根据当前详情页字符串 **逐字搬迁**，避免文案漂移）：

```typescript
export type ProjectPatientLite = { project: number };

export function buildPatientDeleteModalCopy(
  projectPatients: ProjectPatientLite[],
  projectNameById: Record<number, string>,
): { blocked: string | null; summary: string[] } {
  if (projectPatients.length > 0) {
    const names = projectPatients
      .map((r) => projectNameById[r.project] ?? `项目 #${r.project}`)
      .join("、");
    return {
      blocked: `该患者仍关联 ${projectPatients.length} 个研究项目，系统禁止物理删除。请先在各项目看板「解绑」或改用「停用档案」。关联项目：${names}`,
      summary: [],
    };
  }
  return {
    blocked: null,
    summary: [
      "将永久删除该患者档案及本地可恢复副本（若存在），且不可恢复。",
      "当前未检测到研究项目入组关联。",
    ],
  };
}
```

- [ ] **Step 2: `PatientDetailPage` 改为调用该函数生成传给 `DestructiveActionModal` 的 props**（删除原有内联模板字符串拼接，行为不变）。

- [ ] **Step 3: 提交**

```bash
git add frontend/src/pages/patients/patientDeleteModalCopy.ts frontend/src/pages/patients/PatientDetailPage.tsx
git commit -m "refactor(frontend): 抽取患者删除弹窗文案构建"
```

---

### Task 5: 新建 `PatientEditPage` 与路由

**Files:**

- Create: `frontend/src/pages/patients/PatientEditPage.tsx`
- Modify: `frontend/src/app/App.tsx`

- [ ] **Step 1: 在 `App.tsx` 的 `PatientDetailPage` 路由 **上方** 增加：**

```tsx
import { PatientEditPage } from "../pages/patients/PatientEditPage";
```

```tsx
<Route path="/patients/:patientId/edit" element={<PatientEditPage />} />
<Route path="/patients/:patientId" element={<PatientDetailPage />} />
```

- [ ] **Step 2: 创建 `PatientEditPage.tsx`** — 从当前 `PatientDetailPage` 中 **剪切** 表单相关 state（`form`、`saveMutation` 的 `mutationFn` 字段与 `onFinish`）、表单项布局；PATCH 载荷与现详情页一致，但年龄控件改为：

```tsx
<Form.Item label="年龄" shouldUpdate={(p, c) => p.birth_date !== c.birth_date}>
  {() => {
    const bd = form.getFieldValue("birth_date") as Dayjs | undefined;
    if (!bd) {
      return <Input readOnly placeholder="请先选择出生日期" value="" />;
    }
    return <Input readOnly value={String(ageFromBirthDate(bd))} />;
  }}
</Form.Item>
```

`birth_date` `onChange` 时除默认行为外可 `form.setFieldValue('age', ageFromBirthDate(...))` 以便提交（若 PATCH 仍发送 `age` 字段）；**保存时**：

```typescript
birth_date: values.birth_date ? values.birth_date.format("YYYY-MM-DD") : null,
age: values.birth_date ? ageFromBirthDate(values.birth_date) : null,
```

页面 `extra`：`Button` 返回详情 `navigate(/patients/${id})`。

无效 `id` 时渲染 `Alert` 与详情页一致。

- [ ] **Step 3: 手动 smoke** — 浏览器打开 `/patients/101/edit`（本地种子数据）保存一次。

- [ ] **Step 4: 提交**

```bash
git add frontend/src/pages/patients/PatientEditPage.tsx frontend/src/app/App.tsx
git commit -m "feat(frontend): 新增患者档案编辑页与路由"
```

---

### Task 6: `PatientDetailPage` 只读化

**Files:**

- Modify: `frontend/src/pages/patients/PatientDetailPage.tsx`

- [ ] **Step 1: 移除人口学 `Form` / `saveMutation` / `PatientFormValues`（已迁至编辑页）。**

- [ ] **Step 2: 用 `Descriptions`（或 `Typography` + 行布局）展示：**姓名、性别、出生日期、年龄（有 `birth_date` 时用 `ageFromBirthDate(dayjs(patient.birth_date))` 展示；否则 `—`）、手机号、备注、档案状态。

- [ ] **Step 3: `extra` 区在「加入研究项目」左侧或右侧增加 `Link`/`Button`：`编辑档案` → `/patients/${id}/edit`（`useNavigate` 或 `Link` 均可）。

- [ ] **Step 4: 运行前端测试并修正**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run test -- --run
```

`App.test.tsx` 中「打开 `/patients/101` 用 `getByDisplayValue` 断言输入框」会失败：改为断言手机号文本出现，例如 `expect(screen.getByText("13800000101")).toBeInTheDocument()`（若 Descriptions 将值放在子节点，可用 `getByText` 或 `findByText`）。

- [ ] **Step 5: 提交**

```bash
git add frontend/src/pages/patients/PatientDetailPage.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): 患者详情改为只读并链接至编辑页"
```

---

### Task 7: `PatientListPage` 行为对齐

**Files:**

- Modify: `frontend/src/pages/patients/PatientListPage.tsx`
- Create: `frontend/src/pages/patients/PatientListPage.test.tsx`

- [ ] **Step 1: 类型 `PatientRow` 增加 `primary_doctor_name?: string | null`。**

- [ ] **Step 2: 表格 `columns`：**手机号 `render` 使用 `maskPhoneForList`；主治医生列用 `primary_doctor_name`；移除「主治医生 ID」列；操作列仅「编辑」（`navigate` 到 `/patients/${row.id}/edit` 或 `Link`）与「删除」；移除「详情」`Link`。

- [ ] **Step 3: `Table` 增加 `onRow`：**

```tsx
onRow={(record) => ({
  onClick: () => navigate(`/patients/${record.id}`),
  style: { cursor: "pointer" },
})}
```

编辑、删除按钮：`onClick={(e) => { e.stopPropagation(); ... }}`。

- [ ] **Step 4: 删除流程** — 组件内 `useState<number | null>(null)` 表示待删 id；点击删除 `stopPropagation` 后设置 id 并打开 `DestructiveActionModal`；`useQuery` `enabled: deleteTargetId != null` 拉取 `/studies/project-patients/?patient=` 与详情相同；`buildPatientDeleteModalCopy` 生成 props；确认时 `apiClient.delete(/patients/${id}/)`，成功则 `invalidateQueries(['patients'])` 并关弹窗。

需在文件顶部为 `apiClient` 增加 `delete` 使用方式（与详情一致）。若 `apiClient` 无 `delete` 方法封装，使用 `apiClient.delete` axios 实例（与现有 `get`/`post`/`patch` 同源）。

- [ ] **Step 5: 删除整个「编辑患者」`Modal` 及 `editId` / `editingPatient` / `editForm` / `updateMutation` 相关代码；保留「新建患者」Modal。**

- [ ] **Step 6: 列表页测试 `PatientListPage.test.tsx`** — 使用 `QueryClientProvider` + `MemoryRouter` 或 `render` 包装 `PatientListPage` + `Route`，mock `apiClient`：

```typescript
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { PatientListPage } from "./PatientListPage";

const mockGet = vi.fn();
const mockDelete = vi.fn();

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...a: unknown[]) => mockGet(...a),
    delete: (...a: unknown[]) => mockDelete(...a),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn(), eject: vi.fn() } },
  },
}));

// beforeEach: mockGet /patients/ 返回含 phone、primary_doctor_name 的行
// render 后断言 maskPhoneForList 结果
// fireEvent.click 行 → 断言 navigate 或当前路由（可用 createMemoryRouter 数据路由 API）
```

使用 `@testing-library/react` 的 `fireEvent.click`（仓库未安装 `@testing-library/user-event`）。

最小断言集：（1）脱敏手机号可见；（2）不存在「详情」链接；（3）点行触发导航（可通过 `MemoryRouter` 初始 `initialEntries` + `Routes` 嵌套 `PatientListPage` 并 assert `screen.getByText('患者详情')` 在路由切换后出现——若过重可只测 `maskPhoneForList` 已在列渲染，行点击用 integration 在 `App.test`）。

- [ ] **Step 7: 更新 `App.test.tsx` 中「从列表点详情」用例** — 改为 `fireEvent.click(screen.getByText('张三').closest('tr')!)` 或等价方式点击整行，断言出现详情标题；`/patients/` mock 数据须含 `primary_doctor_name`。

- [ ] **Step 8: `npm run lint && npm run build`**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run lint && npm run build
```

- [ ] **Step 9: 提交**

```bash
git add frontend/src/pages/patients/PatientListPage.tsx frontend/src/pages/patients/PatientListPage.test.tsx frontend/src/app/App.test.tsx
git commit -m "feat(frontend): 患者列表脱敏、行导航、编辑路由与删除"
```

---

### Task 8: 全仓验证

- [ ] **Step 1:**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest
```

- [ ] **Step 2:**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run test -- --run && npm run lint && npm run build
```

- [ ] **Step 3: 提交（若有仅格式化的小差异）**

---

## Self-review（对照 spec）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 列表脱敏、无详情链、编辑进 `/edit`、行进详情、删除弹窗 | Task 7 |
| 详情只读 + 编辑入口 | Task 6 |
| 编辑页 C2 + PATCH `age`/`birth_date` 一致 | Task 5 + Task 3 + Task 2 |
| `primary_doctor_name` | Task 2 + Task 7 |
| 删除守卫与文案 | Task 4 + Task 7 |
| 路由顺序 | Task 5 |

**占位符扫描：** 本计划不含 `TBD` / 空实现步骤。

**类型一致：** `ProjectPatientLite` 与列表删除预检返回的 `project` 字段一致（DRF 列表项含 `project: number`）。

---

## 执行交接

**计划已保存至：** `docs/superpowers/plans/2026-05-12-patient-list-detail-edit-routing.md`

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派生子代理，Task 间人工快速 review。须配合 **superpowers:subagent-driven-development**。
2. **Inline Execution** — 本会话内按 Task 顺序实施，使用 **superpowers:executing-plans** 与检查点。

你希望采用哪一种？
