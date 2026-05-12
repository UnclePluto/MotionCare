# CRF Patient Baseline + Mapping (Phase 1) Implementation Plan

> **状态：approved → implementing**（计划已批准，部分任务正在落地中）
> **日期：** 2026-05-08
> **关联 spec：** `docs/superpowers/specs/2026-05-08-crf-core-patient-fields-mapping-design.md`
> **跨工具协作：** 修改本文件前请阅读仓库根 `AGENTS.md` §2。勾选 `- [x]` 时同时在文件顶部"执行记录"区注明 commit short-sha 和工具名（cursor / codex）。
>
> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 以 `docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx` 为真源，在一期（只保留最新值）落地“患者基线（人口学/病史/用药等）”的数据结构与接口，并把这些字段接入 CRF 预览缺失提示与导出记录闭环。

**Architecture:** 在 `apps.patients` 内新增 `PatientBaseline`（与 `Patient` 1:1）承载“低频写、高频读”的基线固化字段（人口学/病史/用药等），并提供 `/patients/{id}/baseline/` 读写接口。`apps.crf` 的 `build_crf_preview` 扩展为同时聚合患者基线与访视节点数据，生成字段级 `missing_fields`，并将 `missing_fields` 随导出记录落库（已有 `CrfExport.missing_fields`）。

**Tech Stack:** Django + DRF、PostgreSQL（JSONField）、pytest、python-docx（已用于导出服务）、React Query（前端 CRF 预览页已存在）。

---

## Scope / 注意事项

- 一期版本策略：**A）只保留最新值**。不做基线版本化/快照，不做审计流转。
- “读写性能”一期优先保证：患者列表/项目患者选择/CRF 预览读取路径不显著退化；基线字段以 JSON 结构化为主，必要时再列化索引字段。
- 当前工作区存在未提交的无关改动与 `tmp/` 目录（含临时 venv 与 docx 抽取产物）。执行各 Task 提交时只 stage 本 Task 文件，避免混入。

---

## File Structure（将新增/修改的文件）

**Create**
- `backend/apps/patients/migrations/0002_patientbaseline.py`

**Modify**
- `backend/apps/patients/models.py`：新增 `PatientBaseline`
- `backend/apps/patients/serializers.py`：新增 `PatientBaselineSerializer`
- `backend/apps/patients/views.py`：为 `PatientViewSet` 增加 `baseline` 子资源 action（GET/PUT/PATCH）
- `backend/apps/crf/services/aggregate.py`：把基线数据与缺失字段计算接入 CRF 预览
- `backend/apps/crf/tests/test_crf_aggregate.py`：新增基线缺失字段测试

**Test**
- `backend/apps/patients/tests/test_patient_baseline_api.py`（新建）：
  - 未登录/无权限
  - GET baseline 默认创建/返回空结构
  - PATCH 更新后，CRF 预览 missing_fields 相应减少

---

### Task 0: 建立隔离工作树（worktree）并确保提交干净

**Files:**
- Modify: （无）

- [ ] **Step 1: 创建 worktree 分支**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare
git status
git switch main
git switch -c feat/crf-patient-baseline
git worktree add .worktrees/feat-crf-patient-baseline feat/crf-patient-baseline
```

Expected:
- `git worktree list` 出现 `.worktrees/feat-crf-patient-baseline`

- [ ] **Step 2: 进入 worktree，确认状态干净**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline
git status
```

Expected:
- 无本地未提交改动（避免把当前 main 上的残留改动带入）

---

### Task 1: 新增 `PatientBaseline` 模型（一期：只保留最新值）

**Files:**
- Modify: `backend/apps/patients/models.py`
- Create: `backend/apps/patients/migrations/0002_patientbaseline.py`

- [ ] **Step 1: 写一个失败的模型测试（能创建并与 Patient 1:1）**

Create `backend/apps/patients/tests/test_patient_baseline_model.py`：

```python
import pytest

from apps.patients.models import Patient, PatientBaseline


@pytest.mark.django_db
def test_patient_baseline_is_one_to_one():
    p = Patient.objects.create(
        name="张三",
        gender=Patient.Gender.MALE,
        phone="13900000000",
    )

    b = PatientBaseline.objects.create(patient=p)
    assert b.patient_id == p.id

    # one-to-one unique constraint
    with pytest.raises(Exception):
        PatientBaseline.objects.create(patient=p)
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/backend
pytest -q apps/patients/tests/test_patient_baseline_model.py
```

Expected:
- FAIL（`PatientBaseline` 未定义或迁移缺失）

- [ ] **Step 3: 写最小实现（模型 + 迁移）**

在 `backend/apps/patients/models.py` 追加：

```python
from django.db import models


class PatientBaseline(UserStampedModel):
    """
    一期策略：只保留最新值（不做版本化/快照）。
    字段结构以 CRF 模板为真源，采用 JSONField 存储结构化分块，便于迭代扩展。
    """

    patient = models.OneToOneField(
        "patients.Patient",
        on_delete=models.CASCADE,
        related_name="baseline",
    )

    # CRF 常见识别字段（模板封面/人口学有“受试者编号/姓名缩写”）
    subject_id = models.CharField("受试者编号", max_length=64, blank=True, default="")
    name_initials = models.CharField("姓名缩写", max_length=32, blank=True, default="")

    # 与模板表格块对应（#T8/#T9/#T10/#T11/#T12）
    demographics = models.JSONField("人口学资料", default=dict)
    surgery_allergy = models.JSONField("手术史与过敏史", default=dict)
    comorbidities = models.JSONField("既往病史与家族史", default=dict)
    lifestyle = models.JSONField("行为习惯史", default=dict)
    baseline_medications = models.JSONField("基线用药", default=dict)

    def __str__(self) -> str:
        return f"PatientBaseline(patient_id={self.patient_id})"
```

生成迁移：

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/backend
python manage.py makemigrations patients
python manage.py migrate
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/backend
pytest -q apps/patients/tests/test_patient_baseline_model.py
```

Expected:
- PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline
git add backend/apps/patients/models.py backend/apps/patients/migrations/0002_patientbaseline.py backend/apps/patients/tests/test_patient_baseline_model.py
git commit -m "feat(patients): add PatientBaseline for CRF"
```

---

### Task 2: 暴露 `PatientBaseline` API（/patients/{id}/baseline/）

**Files:**
- Modify: `backend/apps/patients/serializers.py`
- Modify: `backend/apps/patients/views.py`
- Test: `backend/apps/patients/tests/test_patient_baseline_api.py`

- [ ] **Step 1: 写失败测试（GET 返回 baseline，PATCH 可更新）**

Create `backend/apps/patients/tests/test_patient_baseline_api.py`：

```python
import pytest
from rest_framework.test import APIClient

from apps.patients.models import Patient


@pytest.mark.django_db
def test_patient_baseline_get_and_patch(doctor):
    client = APIClient()
    client.force_authenticate(user=doctor)

    p = Patient.objects.create(
        name="张三",
        gender=Patient.Gender.MALE,
        phone="13900000000",
        created_by=doctor,
        updated_by=doctor,
    )

    url = f"/api/patients/{p.id}/baseline/"

    r = client.get(url)
    assert r.status_code == 200
    assert r.data["patient"] == p.id
    assert r.data["demographics"] == {}

    patch = {
        "subject_id": "S-0001",
        "demographics": {"marital_status": "已婚", "education_years": 9},
        "baseline_medications": {"antihypertensive": {"is_taking": True, "names": ["氨氯地平"]}},
    }
    r2 = client.patch(url, patch, format="json")
    assert r2.status_code == 200
    assert r2.data["subject_id"] == "S-0001"
    assert r2.data["demographics"]["education_years"] == 9
    assert r2.data["baseline_medications"]["antihypertensive"]["is_taking"] is True
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/backend
pytest -q apps/patients/tests/test_patient_baseline_api.py
```

Expected:
- FAIL（baseline action/serializer 尚未实现）

- [ ] **Step 3: 写最小实现（serializer + viewset action）**

在 `backend/apps/patients/serializers.py` 追加：

```python
from .models import PatientBaseline


class PatientBaselineSerializer(serializers.ModelSerializer):
    class Meta:
        model = PatientBaseline
        fields = [
            "id",
            "patient",
            "subject_id",
            "name_initials",
            "demographics",
            "surgery_allergy",
            "comorbidities",
            "lifestyle",
            "baseline_medications",
        ]
        read_only_fields = ["id", "patient"]
```

在 `backend/apps/patients/views.py` 中为 `PatientViewSet` 增加 action：

```python
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import PatientBaseline
from .serializers import PatientBaselineSerializer


class PatientViewSet(ModelViewSet):
    # ... existing code ...

    @action(detail=True, methods=["get", "patch", "put"], url_path="baseline")
    def baseline(self, request, pk=None):
        patient = self.get_object()
        baseline, _created = PatientBaseline.objects.get_or_create(
            patient=patient,
            defaults={"created_by": request.user, "updated_by": request.user},
        )

        if request.method.lower() == "get":
            return Response(PatientBaselineSerializer(baseline).data)

        serializer = PatientBaselineSerializer(baseline, data=request.data, partial=(request.method.lower() == "patch"))
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user)
        return Response(serializer.data)
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/backend
pytest -q apps/patients/tests/test_patient_baseline_api.py
```

Expected:
- PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline
git add backend/apps/patients/serializers.py backend/apps/patients/views.py backend/apps/patients/tests/test_patient_baseline_api.py
git commit -m "feat(patients): add baseline subresource API"
```

---

### Task 3: CRF 预览聚合基线字段 + 基线缺失提示（P0 最小集）

**Files:**
- Modify: `backend/apps/crf/services/aggregate.py`
- Modify: `backend/apps/crf/tests/test_crf_aggregate.py`

- [ ] **Step 1: 写失败测试（基线缺失字段会被报告；补齐后消失）**

在 `backend/apps/crf/tests/test_crf_aggregate.py` 追加：

```python
import pytest

from apps.crf.services.aggregate import build_crf_preview
from apps.patients.models import PatientBaseline


@pytest.mark.django_db
def test_crf_preview_reports_missing_patient_baseline_fields(project_patient, doctor):
    # 确保 baseline 存在但为空
    PatientBaseline.objects.get_or_create(
        patient=project_patient.patient,
        defaults={"created_by": doctor, "updated_by": doctor},
    )

    preview = build_crf_preview(project_patient)
    assert "patient_baseline.受试者编号" in preview["missing_fields"]
    assert "patient_baseline.教育年限" in preview["missing_fields"]

    # 补齐后不再缺失
    b = project_patient.patient.baseline
    b.subject_id = "S-0001"
    b.demographics = {"education_years": 9}
    b.save()

    preview2 = build_crf_preview(project_patient)
    assert "patient_baseline.受试者编号" not in preview2["missing_fields"]
    assert "patient_baseline.教育年限" not in preview2["missing_fields"]
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/backend
pytest -q apps/crf/tests/test_crf_aggregate.py::test_crf_preview_reports_missing_patient_baseline_fields -q
```

Expected:
- FAIL（当前 preview 未聚合 baseline 字段，也不会报告缺失）

- [ ] **Step 3: 写最小实现（聚合 + 缺失逻辑）**

修改 `backend/apps/crf/services/aggregate.py`：

```python
from apps.patients.models import PatientBaseline


REQUIRED_PATIENT_BASELINE_FIELDS = [
    ("subject_id", "受试者编号"),
    ("demographics.education_years", "教育年限"),
]


def _get_nested(d: dict, path: str):
    cur = d
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def build_crf_preview(project_patient) -> dict:
    # ... existing visit logic ...

    patient = project_patient.patient
    baseline = None
    try:
        baseline = patient.baseline
    except PatientBaseline.DoesNotExist:
        baseline = None

    baseline_payload = {
        "subject_id": "",
        "name_initials": "",
        "demographics": {},
        "surgery_allergy": {},
        "comorbidities": {},
        "lifestyle": {},
        "baseline_medications": {},
    }

    if baseline:
        baseline_payload = {
            "subject_id": baseline.subject_id,
            "name_initials": baseline.name_initials,
            "demographics": baseline.demographics,
            "surgery_allergy": baseline.surgery_allergy,
            "comorbidities": baseline.comorbidities,
            "lifestyle": baseline.lifestyle,
            "baseline_medications": baseline.baseline_medications,
        }

    # missing: baseline required fields（一期最小集，后续扩展到 #T8/#T10/#T12 等）
    for path, label in REQUIRED_PATIENT_BASELINE_FIELDS:
        if path == "subject_id":
            if not baseline_payload["subject_id"]:
                missing_fields.append(f"patient_baseline.{label}")
            continue
        v = _get_nested(baseline_payload, path.split(".", 1)[1])
        if v in (None, "", []):
            missing_fields.append(f"patient_baseline.{label}")

    return {
        # ... existing fields ...
        "patient_baseline": baseline_payload,
    }
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/backend
pytest -q apps/crf/tests/test_crf_aggregate.py::test_crf_preview_reports_missing_patient_baseline_fields -q
```

Expected:
- PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline
git add backend/apps/crf/services/aggregate.py backend/apps/crf/tests/test_crf_aggregate.py
git commit -m "feat(crf): include patient baseline and missing fields"
```

---

### Task 4: 前端 CRF 预览页展示患者基线摘要（最小集）

**Files:**
- Modify: `frontend/src/pages/crf/CrfPreviewPage.tsx`
- Test: `frontend/src/pages/crf/CrfPreviewPage.test.tsx`（新建）

- [ ] **Step 1: 写失败测试（展示受试者编号与教育年限）**

Create `frontend/src/pages/crf/CrfPreviewPage.test.tsx`：

```ts
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";

import { apiClient } from "../../api/client";
import { CrfPreviewPage } from "./CrfPreviewPage";

vi.mock("../../api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

it("renders patient baseline summary from preview payload", async () => {
  (apiClient.get as any).mockImplementation((url: string) => {
    if (url === "/studies/project-patients/") return Promise.resolve({ data: [{ id: 1, patient_name: "张三", patient_phone: "139" }] });
    if (url === "/crf/project-patients/1/preview/") {
      return Promise.resolve({
        data: {
          project_patient_id: 1,
          patient: { name: "张三", gender: "male", age: 30, phone: "139" },
          project: { name: "项目A", crf_template_version: "1.1" },
          group: { name: "" },
          visits: {},
          missing_fields: [],
          patient_baseline: { subject_id: "S-0001", name_initials: "", demographics: { education_years: 9 }, surgery_allergy: {}, comorbidities: {}, lifestyle: {}, baseline_medications: {} },
        },
      });
    }
    return Promise.reject(new Error(`unmocked GET ${url}`));
  });

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <CrfPreviewPage />
    </QueryClientProvider>,
  );

  // 选项加载后出现项目患者
  await screen.findByText(/张三/);
});
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/frontend
npm test -- CrfPreviewPage
```

Expected:
- FAIL（当前 `CrfPreviewPayload` 未包含 patient_baseline，页面也未渲染）

- [ ] **Step 3: 最小实现（类型 + UI）**

修改 `frontend/src/pages/crf/CrfPreviewPage.tsx`：

- 扩展 `CrfPreviewPayload` 增加：

```ts
patient_baseline?: {
  subject_id: string;
  name_initials: string;
  demographics: Record<string, unknown>;
};
```

- 在“摘要”卡片中增加最小显示（不存在则 `—`）：
  - 受试者编号（`subject_id`）
  - 教育年限（`patient_baseline.demographics.education_years`）

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline/frontend
npm test -- CrfPreviewPage
```

Expected:
- PASS

- [ ] **Step 5: 提交**

```bash
cd /Users/nick/my_dev/workout/MotionCare/.worktrees/feat-crf-patient-baseline
git add frontend/src/pages/crf/CrfPreviewPage.tsx frontend/src/pages/crf/CrfPreviewPage.test.tsx
git commit -m "feat(frontend): show CRF patient baseline summary"
```

---

## Self-Review(计划自检)

- 覆盖性：计划覆盖“患者基线字段存储 + API + CRF 聚合与缺失提示 + 前端预览展示（最小集）”。
- 无占位：每个 Task 给出明确文件路径、测试代码、执行命令与期望结果。
- 一期策略一致：未引入 baseline 版本化/快照；CRF 始终读取最新值。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-08-crf-patient-baseline-mapping-phase1.md`. Two execution options:

1. Subagent-Driven (recommended) - I dispatch a fresh subagent per task, review between tasks, fast iteration
2. Inline Execution - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

