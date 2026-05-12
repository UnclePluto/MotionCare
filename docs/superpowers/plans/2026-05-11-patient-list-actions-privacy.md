# 患者列表操作与隐私展示 Implementation Plan

> **状态：approved → implementing**（计划已批准，部分任务正在落地中）
> **日期：** 2026-05-11
> **关联 spec：** `docs/superpowers/specs/2026-05-11-patient-list-actions-privacy-design.md`
> **跨工具协作：** 修改本文件前请阅读仓库根 `AGENTS.md` §2。勾选 `- [x]` 时同时在文件顶部"执行记录"区注明 commit short-sha 和工具名（cursor / codex）。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 患者列表支持点击姓名进入详情、列表删除受保护执行、主治医生显示姓名、手机号在列表中脱敏。

**Architecture:** 后端保持兼容，在 `PatientSerializer` 中新增只读字段 `primary_doctor_name`，保留原有 `primary_doctor` ID 字段。前端只在列表渲染层做手机号脱敏；删除入口复用现有 `DELETE /api/patients/:id/` 规则，并在列表点击删除后先查询患者项目关联，存在关联时在弹窗中阻断并提示需先到项目中删除或解绑患者。

**Tech Stack:** Django REST Framework、pytest-django、React、TypeScript、Ant Design、TanStack Query、Vitest、React Testing Library。

---

## 文件结构

- 修改 `backend/apps/patients/serializers.py`：新增只读字段 `primary_doctor_name`。
- 新建 `backend/apps/patients/tests/test_patient_serializer.py`：覆盖有主治医生和无主治医生两种序列化结果。
- 修改 `frontend/src/pages/patients/PatientListPage.tsx`：新增手机号脱敏、姓名详情链接、主治医生姓名列、列表删除状态与确认弹窗，移除操作列「详情」。
- 修改 `frontend/src/app/App.test.tsx`：补充患者列表展示、跳转、删除确认、删除阻断测试。

## Task 1: 后端患者序列化字段

**Files:**
- Create: `backend/apps/patients/tests/test_patient_serializer.py`
- Modify: `backend/apps/patients/serializers.py`

- [ ] **Step 1: 写失败的序列化测试**

新建 `backend/apps/patients/tests/test_patient_serializer.py`：

```python
import pytest

from apps.patients.models import Patient
from apps.patients.serializers import PatientSerializer


@pytest.mark.django_db
def test_patient_serializer_includes_primary_doctor_name(doctor, patient):
    data = PatientSerializer(patient).data

    assert data["primary_doctor"] == doctor.id
    assert data["primary_doctor_name"] == "测试医生"


@pytest.mark.django_db
def test_patient_serializer_primary_doctor_name_is_null_without_doctor():
    patient = Patient.objects.create(
        name="无医生患者",
        gender=Patient.Gender.UNKNOWN,
        age=66,
        phone="13900009999",
        primary_doctor=None,
    )

    data = PatientSerializer(patient).data

    assert data["primary_doctor"] is None
    assert data["primary_doctor_name"] is None
```

- [ ] **Step 2: 运行后端测试并确认失败**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/patients/tests/test_patient_serializer.py -v
```

预期：两个测试都因为缺少 `primary_doctor_name` 字段失败。

- [ ] **Step 3: 实现序列化字段**

将 `backend/apps/patients/serializers.py` 更新为：

```python
from rest_framework import serializers

from .models import Patient


class EnrollProjectsSerializer(serializers.Serializer):
    project_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=False,
    )


class PatientSerializer(serializers.ModelSerializer):
    primary_doctor_name = serializers.CharField(source="primary_doctor.name", read_only=True)

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
```

- [ ] **Step 4: 运行新增后端测试并确认通过**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/patients/tests/test_patient_serializer.py -v
```

预期：`2 passed`。

- [ ] **Step 5: 运行患者删除保护测试**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/patients/tests/test_patient_delete_guard.py -v
```

预期：现有删除保护测试通过。

- [ ] **Step 6: 提交后端变更**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add backend/apps/patients/serializers.py backend/apps/patients/tests/test_patient_serializer.py
git commit -m "feat: 患者接口返回主治医生姓名"
```

预期：生成一个只包含后端序列化器和测试的提交。

## Task 2: 前端患者列表失败测试

**Files:**
- Modify: `frontend/src/app/App.test.tsx`

- [ ] **Step 1: 更新测试文件导入和 API mock**

将 `frontend/src/app/App.test.tsx` 顶部导入和 `apiClient` mock 改为：

```typescript
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";

import { App } from "./App";

const { mockGet, mockPost, mockDelete } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
  mockDelete: vi.fn(),
}));

vi.mock("../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    delete: (...args: unknown[]) => mockDelete(...args),
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
  },
}));
```

- [ ] **Step 2: 更新 `beforeEach` mock 数据**

将现有 `beforeEach` 整段替换为：

```typescript
beforeEach(() => {
  mockDelete.mockImplementation((url: string) => {
    if (url === "/patients/123/") {
      return Promise.resolve({ data: undefined });
    }
    return Promise.reject(new Error(`unmocked DELETE ${url}`));
  });

  mockGet.mockImplementation((url: string, config?: unknown) => {
    const params =
      typeof config === "object" && config
        ? (config as { params?: Record<string, unknown> }).params
        : undefined;

    if (url === "/me/") {
      return Promise.resolve({
        data: {
          id: 1,
          phone: "13800000000",
          name: "测试医生",
          role: "doctor",
          roles: ["doctor"],
          permissions: ["patient.read"],
        },
      });
    }
    if (url === "/studies/projects/") {
      return Promise.resolve({
        data: [{ id: 1, name: "研究项目 A" }],
      });
    }
    if (url === "/studies/projects/1/") {
      return Promise.resolve({
        data: {
          id: 1,
          name: "研究项目 A",
          description: "",
          crf_template_version: "v1",
          status: "active",
        },
      });
    }
    if (url === "/studies/groups/" && params?.project === 1) {
      return Promise.resolve({
        data: [
          { id: 10, name: "试验组", target_ratio: 1, sort_order: 0, is_active: true },
          { id: 11, name: "对照组", target_ratio: 1, sort_order: 1, is_active: true },
        ],
      });
    }
    if (url === "/studies/grouping-batches/" && params?.project === 1) {
      return Promise.resolve({ data: [] });
    }
    if (url === "/studies/project-patients/?patient=123") {
      return Promise.resolve({ data: [] });
    }
    if (url === "/studies/project-patients/?patient=124") {
      return Promise.resolve({
        data: [
          {
            id: 900,
            project: 1,
            patient_name: "王五",
            group_name: "试验组",
            grouping_status: "confirmed",
          },
        ],
      });
    }
    if (url === "/studies/project-patients/") {
      const p = params ?? {};
      if (p.patient === 101 || p.patient === 123) {
        return Promise.resolve({ data: [] });
      }
      if (p.project === 1) {
        return Promise.resolve({ data: [] });
      }
    }
    if (url === "/patients/") {
      return Promise.resolve({
        data: [
          {
            id: 123,
            name: "张三",
            gender: "male",
            age: 30,
            phone: "13800000001",
            primary_doctor: 1,
            primary_doctor_name: "测试医生",
          },
          {
            id: 124,
            name: "王五",
            gender: "female",
            age: 68,
            phone: "13900000002",
            primary_doctor: null,
            primary_doctor_name: null,
          },
        ],
      });
    }
    if (url === "/patients/123/") {
      return Promise.resolve({
        data: {
          id: 123,
          name: "张三",
          gender: "male",
          phone: "13800000001",
        },
      });
    }
    if (url === "/patients/101/") {
      return Promise.resolve({
        data: {
          id: 101,
          name: "李四",
          phone: "13800000101",
        },
      });
    }
    return Promise.reject(new Error(`unmocked GET ${url}`));
  });

  mockPost.mockImplementation((url: string) => {
    return Promise.reject(new Error(`unmocked POST ${url}`));
  });
});
```

- [ ] **Step 3: 替换旧的详情跳转测试**

将测试 `navigates to patient detail when clicking details from the patient list` 替换为：

```typescript
it("navigates to patient detail when clicking the patient name from the patient list", async () => {
  window.history.pushState({}, "", "/patients");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  await waitFor(() => {
    expect(screen.getByRole("link", { name: "张三" })).toBeInTheDocument();
  });

  expect(screen.queryByRole("link", { name: "详情" })).not.toBeInTheDocument();

  screen.getByRole("link", { name: "张三" }).click();

  await waitFor(() => {
    expect(screen.getByText("患者详情")).toBeInTheDocument();
  });
});
```

- [ ] **Step 4: 增加手机号脱敏和主治医生姓名测试**

在详情跳转测试后添加：

```typescript
it("renders masked phone and primary doctor name in the patient list", async () => {
  window.history.pushState({}, "", "/patients");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  await waitFor(() => {
    expect(screen.getByRole("link", { name: "张三" })).toBeInTheDocument();
  });

  expect(screen.getByText("138****0001")).toBeInTheDocument();
  expect(screen.queryByText("13800000001")).not.toBeInTheDocument();
  expect(screen.getByText("测试医生")).toBeInTheDocument();
  expect(screen.getAllByText("—").length).toBeGreaterThan(0);
  expect(screen.queryByText("主治医生 ID")).not.toBeInTheDocument();
  expect(screen.getByText("主治医生")).toBeInTheDocument();
});
```

- [ ] **Step 5: 增加无项目关联患者的删除测试**

继续添加：

```typescript
it("deletes an unlinked patient from the patient list after confirmation", async () => {
  window.history.pushState({}, "", "/patients");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  await waitFor(() => {
    expect(screen.getByRole("link", { name: "张三" })).toBeInTheDocument();
  });

  const row = screen.getByRole("link", { name: "张三" }).closest("tr");
  expect(row).not.toBeNull();
  fireEvent.click(within(row as HTMLTableRowElement).getByRole("button", { name: "删除" }));

  await waitFor(() => {
    expect(screen.getByText("确认删除患者档案？")).toBeInTheDocument();
    expect(screen.getByText("当前未检测到研究项目入组关联。")).toBeInTheDocument();
  });

  fireEvent.click(screen.getByRole("button", { name: "删除" }));

  await waitFor(() => {
    expect(mockDelete).toHaveBeenCalledWith("/patients/123/");
  });
});
```

- [ ] **Step 6: 增加有关联患者的删除阻断测试**

继续添加：

```typescript
it("blocks patient list deletion when the patient is linked to a project", async () => {
  window.history.pushState({}, "", "/patients");
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  render(
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>,
  );

  await waitFor(() => {
    expect(screen.getByRole("link", { name: "王五" })).toBeInTheDocument();
  });

  const row = screen.getByRole("link", { name: "王五" }).closest("tr");
  expect(row).not.toBeNull();
  fireEvent.click(within(row as HTMLTableRowElement).getByRole("button", { name: "删除" }));

  await waitFor(() => {
    expect(screen.getByText("当前无法执行该操作")).toBeInTheDocument();
    expect(screen.getByText(/需先到项目中删除或解绑该患者/)).toBeInTheDocument();
  });

  expect(screen.getByRole("button", { name: "删除" })).toBeDisabled();
  expect(mockDelete).not.toHaveBeenCalledWith("/patients/124/");
});
```

- [ ] **Step 7: 运行前端测试并确认失败**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm test -- src/app/App.test.tsx
```

预期：新增或更新的患者列表测试失败，因为当前 UI 仍显示「详情」操作、明文手机号、主治医生 ID，且没有列表删除流程。

## Task 3: 前端患者列表实现

**Files:**
- Modify: `frontend/src/pages/patients/PatientListPage.tsx`

- [ ] **Step 1: 增加删除弹窗导入、类型字段和状态**

在 `frontend/src/pages/patients/PatientListPage.tsx` 中更新导入：

```typescript
import { apiClient } from "../../api/client";
import { useAuth } from "../../auth/AuthContext";
import { DestructiveActionModal } from "../components/DestructiveActionModal";
```

更新 `PatientRow`：

```typescript
type PatientRow = {
  id: number;
  name: string;
  gender: string;
  age: number | null;
  phone: string;
  primary_doctor: number | null;
  primary_doctor_name?: string | null;
};
```

在 `backendDetail` 后增加：

```typescript
function maskPhone(phone?: string | null): string {
  if (!phone) return "—";
  if (phone.length >= 7) {
    return `${phone.slice(0, 3)}****${phone.slice(-4)}`;
  }
  if (phone.length <= 2) {
    return "*".repeat(phone.length);
  }
  return `${phone[0]}${"*".repeat(phone.length - 2)}${phone[phone.length - 1]}`;
}
```

在 `PatientListPage` 内、`editId` 状态后增加：

```typescript
const [deleteTarget, setDeleteTarget] = useState<PatientRow | null>(null);
const [deleteBlockedReason, setDeleteBlockedReason] = useState<string | null>(null);
const [deleteImpactSummary, setDeleteImpactSummary] = useState<string[]>([]);
const [deleteCheckLoading, setDeleteCheckLoading] = useState(false);
```

- [ ] **Step 2: 增加删除 mutation 和项目关联预检**

在 `updateMutation` 后增加：

```typescript
const deleteMutation = useMutation({
  mutationFn: async () => {
    if (!deleteTarget) return;
    await apiClient.delete(`/patients/${deleteTarget.id}/`);
  },
  onSuccess: async () => {
    message.success("患者档案已删除");
    setDeleteTarget(null);
    setDeleteBlockedReason(null);
    setDeleteImpactSummary([]);
    await qc.invalidateQueries({ queryKey: ["patients"] });
  },
  onError: (err: unknown) => {
    setDeleteBlockedReason(backendDetail(err) ?? "删除失败，请稍后重试或联系管理员。");
  },
});

const openDeleteModal = async (row: PatientRow) => {
  setDeleteTarget(row);
  setDeleteBlockedReason(null);
  setDeleteImpactSummary([]);
  setDeleteCheckLoading(true);
  try {
    const r = await apiClient.get<unknown[]>(`/studies/project-patients/?patient=${row.id}`);
    const linkedCount = r.data.length;
    if (linkedCount > 0) {
      setDeleteBlockedReason(
        `该患者仍关联 ${linkedCount} 个研究项目，系统禁止物理删除。需先到项目中删除或解绑该患者。`,
      );
      return;
    }
    setDeleteImpactSummary([
      "将永久删除该患者档案及本地可恢复副本（若存在），且不可恢复。",
      "当前未检测到研究项目入组关联。",
    ]);
  } catch (err) {
    setDeleteBlockedReason(backendDetail(err) ?? "删除前检查失败，请稍后重试或联系管理员。");
  } finally {
    setDeleteCheckLoading(false);
  }
};
```

- [ ] **Step 3: 替换患者表格列**

将 `Table<PatientRow>` 的 `columns` 数组替换为：

```typescript
columns={[
  {
    title: "姓名",
    dataIndex: "name",
    render: (name: string, row) => <Link to={`/patients/${row.id}`}>{name}</Link>,
  },
  {
    title: "性别",
    dataIndex: "gender",
    render: (v: string) => genderLabel[v] ?? v,
  },
  { title: "年龄", dataIndex: "age" },
  {
    title: "手机号",
    dataIndex: "phone",
    render: (phone: string | null) => maskPhone(phone),
  },
  {
    title: "主治医生",
    dataIndex: "primary_doctor_name",
    render: (name: string | null | undefined) => name ?? "—",
  },
  {
    title: "操作",
    key: "actions",
    render: (_: unknown, row) => (
      <Space>
        <Button type="link" style={{ padding: 0 }} onClick={() => setEditId(row.id)}>
          编辑
        </Button>
        <Button danger type="link" style={{ padding: 0 }} onClick={() => void openDeleteModal(row)}>
          删除
        </Button>
      </Space>
    ),
  },
]}
```

- [ ] **Step 4: 增加列表删除确认弹窗**

在编辑患者 `Modal` 后、`</Card>` 前增加：

```typescript
<DestructiveActionModal
  open={deleteTarget != null}
  title="确认删除患者档案？"
  okText="删除"
  impactSummary={deleteImpactSummary}
  blockedReason={deleteBlockedReason}
  confirmLoading={deleteCheckLoading || deleteMutation.isPending}
  onCancel={() => {
    setDeleteTarget(null);
    setDeleteBlockedReason(null);
    setDeleteImpactSummary([]);
  }}
  onConfirm={() => {
    if (deleteBlockedReason || deleteCheckLoading) return;
    void deleteMutation.mutateAsync();
  }}
/>
```

- [ ] **Step 5: 运行前端测试并确认通过**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm test -- src/app/App.test.tsx
```

预期：`App.test.tsx` 全部通过。

- [ ] **Step 6: 提交前端变更**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare
git add frontend/src/pages/patients/PatientListPage.tsx frontend/src/app/App.test.tsx
git commit -m "feat: 优化患者列表操作与隐私展示"
```

预期：生成一个只包含患者列表 UI 和前端测试的提交。

## Task 4: 最终验证

**Files:**
- Verify only; no planned edits.

- [ ] **Step 1: 运行聚焦后端测试**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend
pytest apps/patients/tests/test_patient_serializer.py apps/patients/tests/test_patient_delete_guard.py -v
```

预期：患者序列化和删除保护测试通过。

- [ ] **Step 2: 运行聚焦前端测试**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm test -- src/app/App.test.tsx
```

预期：`App.test.tsx` 通过。

- [ ] **Step 3: 运行前端 lint**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run lint
```

预期：lint 成功退出。

- [ ] **Step 4: 运行前端构建**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend
npm run build
```

预期：TypeScript 和 Vite 构建成功。

- [ ] **Step 5: 检查最终 git 状态**

执行：

```bash
cd /Users/nick/my_dev/workout/MotionCare
git status --short
```

预期：只剩执行前已经存在的无关工作区改动；本计划产生的后端提交和前端提交已完成。

## Self-Review

- Spec coverage：计划覆盖姓名点击进详情、移除操作列「详情」、列表删除及阻断、主治医生姓名字段、列表手机号脱敏、详情和编辑完整手机号保留、后端与前端聚焦验证。
- Placeholder scan：未发现未决标记、延后实现或无代码的笼统步骤；所有代码变更步骤都给出具体代码。
- Type consistency：字段和状态命名统一使用 `primary_doctor_name`、`PatientRow`、`maskPhone`、`deleteTarget`、`deleteBlockedReason`、`deleteImpactSummary` 和 `/studies/project-patients/?patient=:id`。
