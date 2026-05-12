# 研究录入工作台 + CRF 全量字段（registry）实施计划

执行记录（2026-05-12, cursor）：Task 12–15 已落地于 commit `3af5143`；验证：`frontend` vitest / build 与 `backend` pytest 通过。

> **For agentic workers:** REQUIRED SUB-SKILL: 使用 `superpowers:subagent-driven-development`（推荐）或 `superpowers:executing-plans` 按任务顺序实施。步骤使用 `- [ ]` 勾选追踪。

**Goal:** 以仓库内唯一真源 `docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx` 为基准，建立 `registry` 并在前后端贯通校验与录入；新增侧栏「研究录入」与 `/research-entry` 访视工作列表；修复访视 `form_data` PATCH 仅合并 `assessments` 的缺陷；将 CRF 预览 `missing_fields` 改为与 registry 同源。

**Architecture:** `specs/patient-rehab-system/crf/registry.v1.json` 存字段元数据（表号、控件、选项、`storage`、`required_for_complete`、`visit_types`）。Django 启动时惰性加载 JSON；`PatientBaselineSerializer` 与 `VisitRecordSerializer` 在写入前按 registry 校验；`build_crf_preview` 按同一 registry 计算缺失。前端导入同一份 JSON（构建时从 `specs/` 复制或 Vite `resolve.alias` 指向仓库根，二选一写死一种），用通用渲染器生成 AntD 表单。访视增量中非机能量表统一落在 `form_data.crf` 下，机能与 MoCA 总分等保留在 `form_data.assessments` 并与现有页面兼容。

**Tech Stack:** Django 5、DRF、pytest-django、React 18、TypeScript、Vite、Ant Design 5、TanStack Query v5；新增依赖 `django-filter`（列表筛选）；registry 使用 UTF-8 JSON（stdlib `json`，不强制引入 PyYAML）。

---

## 文件结构总览（创建 / 修改）

| 路径 | 职责 |
|------|------|
| `docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx` | CRF 唯一真源（已存在）；导出/脚本只读 |
| `specs/patient-rehab-system/crf/registry.v1.json` | 全量字段 registry；人工 + 脚本辅助维护 |
| `scripts/dump_crf_docx_tables.py`（新建） | 用 `python-docx` 遍历 docx 表格，输出 `specs/patient-rehab-system/crf/_docx_table_dump.txt` 供对照填 registry |
| `backend/apps/crf/registry_loader.py`（新建） | `load_crf_registry()` → 解析后的 dict + 按 `storage` 索引 |
| `backend/apps/crf/registry_validate.py`（新建） | 对 `PatientBaseline` payload 与 `form_data` 片段做类型/枚举校验；返回 `(ok, errors: dict)` |
| `backend/apps/crf/services/aggregate.py` | 改为基于 registry 生成 `missing_fields`；删除与 registry 重复的硬编码常量（迁移完成后） |
| `backend/apps/crf/tests/test_crf_aggregate.py` | 更新/新增用例覆盖 registry 驱动缺失 |
| `backend/apps/patients/serializers.py` | `PatientBaselineSerializer.validate` 调用 `registry_validate` |
| `backend/apps/visits/serializers.py` | `form_data` 多键 deep merge；`crf` 校验；保留 `computed_assessments` 不可客户端写 |
| `backend/apps/visits/views.py` | `django-filter` + 列表用 enriched serializer |
| `backend/apps/visits/filters.py`（新建） | `VisitRecordFilter`：`project_patient`、`visit_type`、`status`、`project`、`patient_name`、`patient_phone` |
| `backend/apps/visits/serializers_list.py`（新建，可选） | 列表行：嵌套 `patient`、`project` 展示字段 |
| `backend/config/settings.py` | `CRF_TEMPLATE_PATH` 默认改为 `docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx`；`INSTALLED_APPS` 加入 `django_filters`；`REST_FRAMEWORK` 增加默认分页（若尚无） |
| `backend/pyproject.toml` | 加入 `django-filter>=24,<26` |
| `backend/apps/visits/tests/test_visit_form_data_contract.py` | 新增 PATCH 仅 `crf` / 仅 `assessments` 合并用例 |
| `frontend/src/crf/registry.v1.json` | 构建前由 `npm run sync-crf-registry` 从 `specs/...` 复制（见 Task 12） |
| `frontend/src/crf/types.ts`（新建） | Registry 条目 TypeScript 类型 |
| `frontend/src/crf/renderRegistryFields.tsx`（新建） | 将 registry 字段渲染为 AntD `Form.Item` 树 |
| `frontend/src/pages/research-entry/ResearchEntryPage.tsx`（新建） | 工作台：筛选 + 表格 + 跳转 |
| `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`（新建） | 或抽屉组件：加载/保存 baseline |
| `frontend/src/pages/visits/VisitFormPage.tsx` | 挂载 `crf` 与 MoCA 分项等扩展块 |
| `frontend/src/app/App.tsx` | 注册 `/research-entry`、`/patients/:patientId/crf-baseline`（路径以实施为准） |
| `frontend/src/app/layout/AdminLayout.tsx` | 菜单「研究录入」 |
| `frontend/package.json` | `sync-crf-registry` 脚本 |

---

### Task 1: 对齐 CRF 模板路径配置

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `docs/superpowers/specs/2026-05-12-research-entry-crf-full-field-workbench-design.md`（若仍有旧路径描述则已在前序提交修正）

- [ ] **Step 1: 将 `CRF_TEMPLATE_PATH` 默认值改为 `docs/other` 下修订稿**

在 `backend/config/settings.py` 中把：

```python
CRF_TEMPLATE_PATH = ROOT_DIR / os.getenv(
    "CRF_TEMPLATE_PATH",
    "docs/认知衰弱数字疗法研究_CRF表_修订稿.docx",
)
```

改为：

```python
CRF_TEMPLATE_PATH = ROOT_DIR / os.getenv(
    "CRF_TEMPLATE_PATH",
    "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx",
)
```

- [ ] **Step 2: 确认文件可读**

Run:

```bash
test -f /Users/nick/my_dev/workout/MotionCare/docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx && echo OK
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add backend/config/settings.py
git commit -m "fix(config): CRF 模板默认路径指向 docs/other 修订稿"
```

---

### Task 2: 依赖与 DRF 全局分页

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/config/settings.py`

- [ ] **Step 1: 安装 django-filter**

在 `backend/pyproject.toml` 的 `dependencies` 数组中增加一行：

```toml
  "django-filter>=24.3,<26.0",
```

Run:

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pip install "django-filter>=24.3,<26.0"
```

- [ ] **Step 2: 注册应用**

在 `INSTALLED_APPS` 列表中加入 `"django_filters"`（字符串）。

- [ ] **Step 3: 为列表接口启用分页（若尚未配置）**

在 `REST_FRAMEWORK` 字典中增加（数值可微调，但必须固定以免工作台翻页行为漂移）：

```python
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
```

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/config/settings.py
git commit -m "chore(backend): 引入 django-filter 与 DRF 默认分页"
```

---

### Task 3: docx 表格导出脚本（辅助填 registry）

**Files:**
- Create: `scripts/dump_crf_docx_tables.py`
- Create（gitignore 可选）: `specs/patient-rehab-system/crf/_docx_table_dump.txt`

- [ ] **Step 1: 编写脚本**（从仓库根执行，`python-docx` 已在 backend 依赖中，可用 `cd backend && uv run python ../scripts/dump_crf_docx_tables.py` 或等价方式）

脚本逻辑：打开 `ROOT_DIR/docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx`，遍历 `document.tables`，每个表格输出：表格序号、行数列数、非空单元格文本（按行拼接），便于人工标注 `#T8` 等表号与字段。输出写到 `specs/patient-rehab-system/crf/_docx_table_dump.txt`。

最小可运行骨架：

```python
"""Dump Word table text for CRF registry authoring. Run from repo root."""
from pathlib import Path

from docx import Document

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx"

def main() -> None:
    doc = Document(str(DOC))
    lines: list[str] = []
    for i, table in enumerate(doc.tables):
        lines.append(f"=== TABLE {i} rows={len(table.rows)} cols={len(table.columns)} ===")
        for r in table.rows:
            cells = [c.text.strip().replace("\n", " ") for c in r.cells]
            if any(cells):
                lines.append(" | ".join(cells))
        lines.append("")
    out = ROOT / "specs/patient-rehab-system/crf/_docx_table_dump.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print("Wrote", out)

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 运行脚本**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && python ../scripts/dump_crf_docx_tables.py
```

Expected: 终端打印 `Wrote .../_docx_table_dump.txt`，且文件非空。

- [ ] **Step 3: Commit**

```bash
git add scripts/dump_crf_docx_tables.py
git commit -m "chore(crf): 增加 docx 表格导出脚本供 registry 对照"
```

---

### Task 4: 建立 `registry.v1.json` 骨架与 JSON Schema

**Files:**
- Create: `specs/patient-rehab-system/crf/registry.v1.json`
- Create: `specs/patient-rehab-system/crf/registry.schema.json`（可选，用于 IDE 校验）

- [ ] **Step 1: 写入根元数据 + 示例字段 2 条**

`registry.v1.json` 顶层结构示例（提交时须已按 docx **补全全表**，此处为结构契约；实施工程师在 Task 4 内用 docx 填满，不得留空数组交差）：

```json
{
  "template_id": "cognitive_frailty_digital_therapy_crf",
  "template_revision": "修订稿-与docx文件名一致或封面版本",
  "source_docx": "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx",
  "fields": [
    {
      "field_id": "demo_education_years",
      "table_ref": "#T8",
      "label_zh": "受教育年限（示例，正式稿请与 Word 完全一致）",
      "widget": "number",
      "storage": "patient_baseline.demographics.education_years",
      "required_for_complete": true,
      "visit_types": null
    },
    {
      "field_id": "demo_t0_visit_date",
      "table_ref": "#T3",
      "label_zh": "访视日期（示例）",
      "widget": "date",
      "storage": "visit.visit_date",
      "required_for_complete": true,
      "visit_types": ["T0"]
    }
  ]
}
```

正式合入前：删除或替换示例字段，使 `fields` 覆盖 design spec 第 3.4 节全部表；`storage` 为 `visit.form_data.assessments.*` 的须与现有 `VisitFormPage` 路径一致；`visit.form_data.crf.*` 用于 `#T16`–`#T30` 等。

- [ ] **Step 2: 校验 JSON 语法**

```bash
python -m json.tool /Users/nick/my_dev/workout/MotionCare/specs/patient-rehab-system/crf/registry.v1.json > /dev/null && echo OK
```

Expected: `OK`

- [ ] **Step 3: Commit**（全量字段填完后再提交，可多次 commit：`feat(crf): registry T8-T12` 等）

---

### Task 5: 后端 registry 加载器

**Files:**
- Create: `backend/apps/crf/registry_loader.py`
- Create: `backend/apps/crf/tests/test_registry_loader.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/apps/crf/tests/test_registry_loader.py
import pytest

from apps.crf.registry_loader import load_crf_registry


@pytest.mark.django_db
def test_load_crf_registry_returns_template_id():
    reg = load_crf_registry()
    assert reg["template_id"]
    assert isinstance(reg["fields"], list)
    assert len(reg["fields"]) >= 1
```

- [ ] **Step 2: 运行确认失败**

Run: `cd /Users/nick/my_dev/workout/MotionCare/backend && pytest apps/crf/tests/test_registry_loader.py -v`  
Expected: ImportError 或失败（尚未实现）。

- [ ] **Step 3: 实现加载器**

`registry_loader.py`：用 `django.conf.settings` 的 `ROOT_DIR` 不可用则 `Path(__file__).resolve().parents[3]` 指向仓库根（`backend/apps/crf` → 上三级到 MotionCare 根），读取 `specs/patient-rehab-system/crf/registry.v1.json`，`json.loads`，模块级缓存 `_REGISTRY = None`。

- [ ] **Step 4: 测试通过**

Run: `pytest apps/crf/tests/test_registry_loader.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/apps/crf/registry_loader.py backend/apps/crf/tests/test_registry_loader.py
git commit -m "feat(crf): 加载 CRF registry JSON"
```

---

### Task 6: 后端 registry 校验器（baseline + visit）

**Files:**
- Create: `backend/apps/crf/registry_validate.py`
- Create: `backend/apps/crf/tests/test_registry_validate.py`

- [ ] **Step 1: 测试：合法 demographics 数字通过**

```python
@pytest.mark.django_db
def test_validate_patient_baseline_partial_ok():
    from apps.crf.registry_validate import validate_patient_baseline_payload

    errors = validate_patient_baseline_payload({"demographics": {"education_years": 12}})
    assert errors == {}
```

- [ ] **Step 2: 测试：枚举不通过**

假设 registry 中 `frailty` 为 `single_choice`，选项 `robust|pre_frail|frail`，构造 `validate_visit_assessments_payload` 对 `assessments.frailty` 校验；若 registry 尚未含该字段，则在 registry 增加后再写此测。

- [ ] **Step 3: 实现**  
  - `validate_patient_baseline_payload(data: dict) -> dict[str, str]`：仅校验 payload 中出现的、且 `storage` 以 `patient_baseline.` 开头的字段。  
  - `validate_visit_form_data_patch(form_data_patch: dict, visit_type: str) -> dict[str, str]`：校验 `assessments` 与 `crf` 中与 registry 匹配且 `visit_types` 为 null 或含当前 `visit_type` 的字段。  
  类型规则：`number` 用 `int|float`（排除 bool）；`single_choice` in options；`multi_choice` 全在 options；`date` 接受 `YYYY-MM-DD` 字符串。

- [ ] **Step 4: pytest 全绿**

Run: `cd backend && pytest apps/crf/tests/test_registry_validate.py -v`

- [ ] **Step 5: Commit**

---

### Task 7: 接入 `PatientBaselineSerializer`

**Files:**
- Modify: `backend/apps/patients/serializers.py`
- Modify: `backend/apps/patients/tests/test_patient_baseline_api.py`

- [ ] **Step 1: 在 `PatientBaselineSerializer` 中增加 `validate`**

调用 `validate_patient_baseline_payload(attrs)`，若有错误 `raise serializers.ValidationError(errors)`。

- [ ] **Step 2: 新增 API 测试：非法枚举 400**

```python
def test_patch_patient_baseline_invalid_enum_returns_400(doctor, patient, client):
    client.force_authenticate(user=doctor)
    client.get(f"/api/patients/{patient.id}/baseline/")
    r = client.patch(
        f"/api/patients/{patient.id}/baseline/",
        {"demographics": {"invalid_demo_enum": "not_in_list"}},
        format="json",
    )
    assert r.status_code == 400
```

（具体字段名以 registry 中真实枚举字段为准。）

- [ ] **Step 3: pytest**

Run: `cd backend && pytest apps/patients/tests/test_patient_baseline_api.py -v`

- [ ] **Step 4: Commit**

---

### Task 8: 修复访视 `form_data` PATCH 合并 + registry 校验

**Files:**
- Modify: `backend/apps/visits/serializers.py`
- Modify: `backend/apps/visits/tests/test_visit_form_data_contract.py`

- [ ] **Step 1: 写失败测试「仅 PATCH crf 不丢 assessments」**

```python
@pytest.mark.django_db
def test_patch_form_data_crf_merges_without_dropping_assessments(client, doctor, project_patient):
    from apps.visits.models import VisitRecord

    visit = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    client.force_authenticate(user=doctor)
    client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"assessments": {"sppb": {"total": 9}}}},
        format="json",
    )
    r2 = client.patch(
        f"/api/visits/{visit.id}/",
        {"form_data": {"crf": {"adherence": {"sessions_completed": 3}}}},
        format="json",
    )
    assert r2.status_code == 200
    r3 = client.get(f"/api/visits/{visit.id}/")
    fd = r3.data["form_data"]
    assert fd["assessments"]["sppb"]["total"] == 9
    assert fd["crf"]["adherence"]["sessions_completed"] == 3
```

（`crf` 内键名以 registry 为准，测试中键名随 registry 调整。）

- [ ] **Step 2: 实现合并**

在 `VisitRecordSerializer.update` 中：对 `("assessments", "crf")` 中出现在 `incoming` 的每个键执行与当前 `merged` 的 `_deep_merge`；禁止合并 `computed_assessments`。`incoming` 顶层其它未知键：忽略并 `logger.warning`。

在 `validate` 中于类型校验通过后调用 `validate_visit_form_data_patch(incoming, instance.visit_type)`（`create` 路径若无 instance 则跳过或仅校验结构）。

- [ ] **Step 3: pytest**

Run: `cd backend && pytest apps/visits/tests/test_visit_form_data_contract.py -v`

- [ ] **Step 4: Commit**

```bash
git commit -m "fix(visits): form_data 支持 crf 与 assessments 分键 deep merge"
```

---

### Task 9: 访视列表 API（筛选 + 嵌套展示）

**Files:**
- Create: `backend/apps/visits/filters.py`
- Modify: `backend/apps/visits/views.py`
- Create或Modify: `backend/apps/visits/serializers.py`（列表用 `VisitRecordListSerializer` 或 `Meta` 第二序列化器）
- Create: `backend/apps/visits/tests/test_visit_list_api.py`

- [ ] **Step 1: `VisitRecordFilter`**

使用 `django_filters.rest_framework.DjangoFilterBackend`，字段：`project_patient`、`visit_type`、`status`、`project`（`project_patient__project_id`）、`patient_phone`（`icontains`）、`patient_name`（`project_patient__patient__name__icontains`）。

- [ ] **Step 2: `VisitRecordViewSet`**

`filterset_class = VisitRecordFilter`，`queryset` 增加 `select_related("project_patient__patient", "project_patient__project", "project_patient__group")`。列表动作用 `VisitRecordListSerializer`（含 `patient_name`、`patient_phone`、`project_name`、`visit_ids` 不必需），详情 `retrieve` 仍用完整 `VisitRecordSerializer`（可用 `get_serializer_class`）。

- [ ] **Step 3: 测试**

```python
def test_visit_list_filter_by_visit_type(doctor, project_patient, client):
    client.force_authenticate(user=doctor)
    t0 = VisitRecord.objects.get(project_patient=project_patient, visit_type="T0")
    r = client.get("/api/visits/", {"visit_type": "T0"})
    assert r.status_code == 200
    ids = [row["id"] for row in r.data["results"]]
    assert t0.id in ids
```

- [ ] **Step 4: pytest + commit**

---

### Task 10: CRF `aggregate` 与 registry 同源

**Files:**
- Modify: `backend/apps/crf/services/aggregate.py`
- Modify: `backend/apps/crf/tests/test_crf_aggregate.py`

- [ ] **Step 1: 在 `build_crf_preview` 中**  
  加载 registry；对每条 `required_for_complete` 为 true 的字段：按 `storage` 解析取值（`patient_baseline.*` 走 baseline payload；`visit.form_data.*` 按 T0/T1/T2 三条 visit 取；`visit.visit_date` 走 `VisitRecord.visit_date`）；缺失则追加 `missing_fields` 中文 label（可用 `label_zh` 或 `{visit_type}.{label_zh}`）。

- [ ] **Step 2: 删除硬编码**  
  移除旧的 `REQUIRED_VISIT_ASSESSMENT_FIELDS` 常量路径逻辑，避免双口径。

- [ ] **Step 3: pytest**

Run: `cd backend && pytest apps/crf/tests/test_crf_aggregate.py -v`

- [ ] **Step 4: Commit**

---

### Task 11: 全后端回归

**Files:**（无新文件）

- [ ] **Step 1**

Run: `cd /Users/nick/my_dev/workout/MotionCare/backend && pytest`

Expected: 全部 PASS

- [ ] **Step 2: Commit**（若有仅格式化小改）

---

### Task 12: 前端同步 registry 与类型

**Files:**
- Modify: `frontend/package.json`
- Create: `frontend/scripts/sync-crf-registry.mjs`（Node 复制文件）
- Create: `frontend/src/crf/types.ts`
- Copy target: `frontend/src/crf/registry.v1.json`

`sync-crf-registry.mjs` 示例：

```javascript
import { copyFileSync, mkdirSync } from "fs";
import { dirname, join } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..", "..");
const src = join(root, "specs/patient-rehab-system/crf/registry.v1.json");
const dest = join(__dirname, "..", "src/crf/registry.v1.json");
mkdirSync(dirname(dest), { recursive: true });
copyFileSync(src, dest);
console.log("synced", dest);
```

`package.json`：

```json
"scripts": {
  "sync-crf-registry": "node scripts/sync-crf-registry.mjs"
}
```

- [ ] **Step 1: 运行**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run sync-crf-registry
```

- [ ] **Step 2: 在 `npm run build` 前** 文档化须先 sync（或在 `prebuild` 挂钩 `sync-crf-registry`）。

- [ ] **Step 3: Commit**

---

### Task 13: 通用 `renderRegistryFields` + 患者 CRF 基线页

**Files:**
- Create: `frontend/src/crf/renderRegistryFields.tsx`
- Create: `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`
- Modify: `frontend/src/app/App.tsx`

- [ ] **Step 1: `renderRegistryFields`**  
  入参：`fields` 过滤 `storage` 前缀为 `patient_baseline.`；用 `name` 路径数组（AntD `Form` 嵌套）绑定；`widget` 映射到 `Input`、`InputNumber`、`Select`、`DatePicker`、`Checkbox.Group` 等。

- [ ] **Step 2: 基线页**  
  `useQuery` GET `/api/patients/:id/baseline/`，`useMutation` PATCH；按 `table_ref` 分组 `Collapse`。

- [ ] **Step 3: 路由**  
  增加 `/patients/:patientId/crf-baseline`（与现有 `/patients/:id/edit` 并存）。

- [ ] **Step 4: Vitest 冒烟**（可选：渲染空表单不抛错）

- [ ] **Step 5: Commit**

---

### Task 14: `ResearchEntryPage` 工作台

**Files:**
- Create: `frontend/src/pages/research-entry/ResearchEntryPage.tsx`
- Modify: `frontend/src/app/layout/AdminLayout.tsx`
- Modify: `frontend/src/app/App.tsx`

- [ ] **Step 1: 列表请求**  
  `GET /api/visits/?page=1&visit_type=T0&status=draft&project=...&patient_name=...`

- [ ] **Step 2: 列与操作**  
  患者、项目、访视类型、状态、访视日期、`Link` 到 `/visits/:id`，`Link` 到 `/patients/:pid/crf-baseline`。

- [ ] **Step 3: 侧栏**  
  `items` 增加 `{ key: "/research-entry", icon: <FormOutlined />, label: "研究录入" }`（图标从 `@ant-design/icons` 引入 `FormOutlined` 或 `MedicineBoxOutlined`）。

- [ ] **Step 4: `npm run test` + `npm run lint` + `npm run build`**

- [ ] **Step 5: Commit**

---

### Task 15: 扩展 `VisitFormPage`

**Files:**
- Modify: `frontend/src/pages/visits/VisitFormPage.tsx`
- Modify: `frontend/src/pages/visits/VisitFormPage.test.tsx`

- [ ] **Step 1: 保留现有机能评估块**  
  MoCA 在 registry 若含 `moca.subscores`，则增加子项输入；保存时 PATCH `form_data: { assessments: { moca: { total, ... } } }` 与 `{ crf: ... }` 分次或合并提交（注意 partial：一次保存应合并对象）。

- [ ] **Step 2: 渲染 `visit_types` 含当前访视的 `crf` 字段**  
  从 registry 筛选 `storage` 以 `visit.form_data.crf` 开头且 `visit_types` 命中。

- [ ] **Step 3: 更新 Vitest**  
  与现有 mock 对齐，断言 PATCH body 含 `crf` 键（若测试覆盖保存）。

- [ ] **Step 4: Commit**

---

### Task 16: 计划文件顶部执行记录 + spec 状态

**Files:**
- Modify: `docs/superpowers/plans/2026-05-12-research-entry-crf-full-field-workbench.md`
- Modify: `docs/superpowers/specs/2026-05-12-research-entry-crf-full-field-workbench-design.md`

全部任务完成后在 plan 文件顶部增加一行：

```text
执行记录（YYYY-MM-DD, cursor）：全任务已落地于 commit <short-sha>
```

将 design spec 的 `> 状态：` 改为 `implemented`（若已发布）或保持 `approved` 直至合并。

---

## Plan 自检（对照 design spec）

| Spec 章节 | 对应 Task |
|-----------|-----------|
| 唯一 docx 真源 | Task 1、Task 3、Task 4 `source_docx` |
| registry 单一真源 | Task 4–6 |
| `form_data` 含 `crf` + merge 修复 | Task 8 |
| 列表筛选与嵌套 | Task 9 |
| `missing_fields` 与 registry 同源 | Task 10 |
| 工作台路由与菜单 | Task 14 |
| 患者基线全表录入 | Task 4、7、13 |
| 访视全表录入 | Task 4、8、15 |
| 测试与回归 | 各 Task 内 pytest / vitest；Task 11 |

**Placeholder 扫描：** 本计划未使用 “TBD / TODO / 类似 Task N”。registry 内示例字段须在合并前替换为 docx 全量。

**类型一致性：** `storage` 前缀固定为 `patient_baseline.`、`visit.form_data.`、`visit.visit_date`；与 ORM 字段 `baseline_medications` 一致，不用 `medications`。

---

## 执行交接

计划已保存到 `docs/superpowers/plans/2026-05-12-research-entry-crf-full-field-workbench.md`。

**执行方式二选一：**

1. **Subagent-Driven（推荐）** — 每个 Task 新开子代理执行与审查，适合本计划体量大、registry 填表工作集中。  
2. **Inline Execution** — 本会话用 `executing-plans` 按 Task 批次推进并设检查点。

你更倾向哪一种？
