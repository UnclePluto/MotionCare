# 患者 CRF 基线表单 UX 实施计划

执行记录（2026-05-12, Cursor）：Task 1–8 已在工作区落地；验证：`backend pytest` 92 通过、`frontend npm run test` 43 通过、`npm run lint` 0 error、`npm run build` 通过。未代用户执行 git commit。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在仅 `/patients/:patientId/crf-baseline` 页面实现：主档预填（只填空）、姓名缩写四格补 `X`、单选 Radio、「其他」备注、`table_titles` 章节名、宽屏双列布局；registry 与后端校验与 spec `docs/superpowers/specs/2026-05-12-patient-crf-baseline-form-ux-design.md` 一致；访视 CRF 仍用 `Select`。

**Architecture:** 真源 `specs/patient-rehab-system/crf/registry.v1.json` 增加 `table_titles` 与字段级 `other_remark_storage`；`npm run prebuild` 通过 `sync-crf-registry.mjs` 拷贝至 `frontend/src/crf/registry.v1.json`。基线页并行拉取患者与 baseline，纯函数合并预填；`single_choice` 在基线专用渲染器中用 `Radio` + 条件备注。`PatientBaselineSerializer.validate` 构造「实例 + 本次 attrs」完整 payload 再调 `validate_patient_baseline_payload`，在其中增加「其他 + 必填」交叉校验。

**Tech Stack:** Django 5、DRF、Vitest、Ant Design 5、`pinyin-pro`（新增 npm 依赖）、TypeScript。

---

## 文件结构（创建 / 修改）

| 路径 | 职责 |
|------|------|
| `specs/patient-rehab-system/crf/registry.v1.json` | 根级 `table_titles`；含「其他」的 baseline `single_choice` 增加 `other_remark_storage`（及可选 `other_remark_widget`） |
| `frontend/src/crf/types.ts` | `CrfRegistry.table_titles`；`RegistryField.other_remark_storage`、`other_remark_widget` |
| `frontend/src/crf/nameInitials.ts` | 中文姓名 → 四格缩写（大写、补 `X`、超长截断） |
| `frontend/src/crf/nameInitials.test.ts` | 缩写纯函数单测 |
| `frontend/src/crf/baselinePrefill.ts` | `mergePatientIntoBaselineApiPayload(patient, baselineApi)`：在 **与 GET baseline 相同形状** 的对象上只填空，再交给 `baselineToFormValues`（避免在含 Dayjs 的表单态上合并） |
| `frontend/src/crf/baselinePrefill.test.ts` | 预填与不覆盖单测 |
| `frontend/src/crf/renderBaselineRegistryFields.tsx`（新建） | 基线专用：`single_choice` → Radio +「其他」备注；其余 widget 复用或小幅复制 `renderRegistryFields` 中非 choice 分支 |
| `frontend/src/crf/renderRegistryFields.tsx` | 保留 `baselineToFormValues`、`renderVisitRegistryField`；可 `export` 共享的 `widgetFormItem` 或仅 baseline 文件 import 原 `DatePicker` 等逻辑避免重复 |
| `frontend/src/pages/patients/PatientCrfBaselinePage.tsx` | `useQueries` 拉患者 + baseline；Collapse `label` 用 `table_titles`；节内 Grid 双列；改用基线渲染器 |
| `frontend/package.json` / `package-lock.json` | 增加 `pinyin-pro` |
| `backend/apps/patients/serializers.py` | `validate` 内组装完整 baseline 字典再校验 |
| `backend/apps/crf/registry_validate.py` | `other_remark` 交叉规则；对 `other_remark_storage` 路径上送的值做 `text` 规则校验 |
| `backend/apps/crf/tests/test_registry_validate.py` | monkeypatch `load_crf_registry` 测「其他 + 必填」 |
| `backend/apps/patients/tests/test_patient_baseline_api.py` | 可选：PATCH「其他」无备注返回 400（在 monkeypatch 必填字段时） |

---

### Task 1: Registry 元数据（`table_titles` + `other_remark_storage`）

**Files:**

- Modify: `specs/patient-rehab-system/crf/registry.v1.json`
- Modify: `frontend/src/crf/registry.v1.json`（运行 sync 生成，或 Task 1 完成后执行 `npm run sync-crf-registry`）

- [ ] **Step 1: 在 `registry.v1.json` 根对象、`fields` 数组之前插入 `table_titles`**

当前 baseline 字段使用的 `table_ref` 仅有：`#T0`、`#T8`、`#T9`、`#T10`、`#T11`、`#T12`。插入内容（**实施时须与 `docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx` 表题逐字核对**，若有出入以 docx 为准）：

```json
"table_titles": {
  "#T0": "筛选与受试者标识",
  "#T8": "人口学信息",
  "#T9": "手术史与过敏史",
  "#T10": "合并症、既往史与家族史",
  "#T11": "生活方式",
  "#T12": "合并用药"
},
```

- [ ] **Step 2: 为含「其他」的 baseline 单选题增加 `other_remark_storage`**

在下列三个字段对象上增加属性（与现有 `field_id` 同级），路径指向 `demographics` 内新键（PATCH 时随表单一并提交）：

| field_id | 新增键 |
|----------|--------|
| `dm_marital` | `"other_remark_storage": "patient_baseline.demographics.marital_status_other_remark"` |
| `dm_ethnicity` | `"other_remark_storage": "patient_baseline.demographics.ethnicity_other_remark"` |
| `dm_insurance` | `"other_remark_storage": "patient_baseline.demographics.insurance_type_other_remark"` |

（可选）统一增加 `"other_remark_widget": "text"`。

- [ ] **Step 3: 同步到前端并校验 JSON**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run sync-crf-registry
python3 -m json.tool /Users/nick/my_dev/workout/MotionCare/specs/patient-rehab-system/crf/registry.v1.json > /dev/null
```

Expected: sync 打印 `synced .../frontend/src/crf/registry.v1.json`；`json.tool` 无报错。

- [ ] **Step 4: Commit（可选）**

```bash
git add specs/patient-rehab-system/crf/registry.v1.json frontend/src/crf/registry.v1.json
git commit -m "feat(crf): registry 增加 table_titles 与 other_remark_storage"
```

---

### Task 2: 前端类型

**Files:**

- Modify: `frontend/src/crf/types.ts`

- [ ] **Step 1: 扩展类型定义**

将 `RegistryField` 与 `CrfRegistry` 改为（保留现有字段，追加可选字段）：

```typescript
export type RegistryField = {
  field_id: string;
  table_ref: string;
  label_zh: string;
  widget: string;
  storage: string;
  required_for_complete?: boolean;
  visit_types?: string[] | null;
  options?: string[];
  hint?: string;
  doc_table_index?: number;
  other_remark_storage?: string;
  other_remark_widget?: "text" | "textarea";
};

export type CrfRegistry = {
  template_id: string;
  template_revision: string;
  source_docx: string;
  table_titles?: Record<string, string>;
  fields: RegistryField[];
};
```

- [ ] **Step 2: 类型检查**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run build
```

Expected: `tsc` 通过（若仅改 types 且无引用错误应通过）。

---

### Task 3: `pinyin-pro` 与姓名缩写纯函数

**Files:**

- Modify: `frontend/package.json`、`frontend/package-lock.json`
- Create: `frontend/src/crf/nameInitials.ts`
- Create: `frontend/src/crf/nameInitials.test.ts`

- [ ] **Step 1: 安装依赖**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm install pinyin-pro
```

- [ ] **Step 2: 实现 `crfNameInitialsFour`**

`frontend/src/crf/nameInitials.ts`：

```typescript
import { pinyin } from "pinyin-pro";

/** CRF 受试者姓名缩写：拼音首字母大写，不足四位右侧补 X，超过四位截断。 */
export function crfNameInitialsFour(fullName: string): string {
  const name = fullName.trim();
  if (!name) return "XXXX";
  const initials = pinyin(name, { pattern: "first", type: "string" }) as string;
  const letters = initials
    .replace(/\s+/g, "")
    .toUpperCase()
    .replace(/[^A-Z]/g, "");
  const core = letters.slice(0, 4);
  if (core.length >= 4) return core.slice(0, 4);
  return core + "X".repeat(4 - core.length);
}
```

若运行时 `pinyin` 的 `type: "string"` 与仓库中 `pinyin-pro` 版本 API 不一致，以该版本 README 为准，保持行为：首字母、大写、非 A–Z 剔除、截断/补位不变。

- [ ] **Step 3: 编写 Vitest**

`frontend/src/crf/nameInitials.test.ts`：推荐 **不 mock** `pinyin-pro`，用固定真实汉字断言「长度为 4」「仅含 A–Z」「不足四位含 X」；另测 `trim()` 与空串返回 `XXXX`。若必须 mock，令 `pinyin` 返回带空格首字母串（如 `"z s"`）→ 去空格后 `ZS` → 期望 `ZSXX`。

- [ ] **Step 4: 运行测试**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npx vitest run src/crf/nameInitials.test.ts
```

Expected: PASS。

---

### Task 4: 预填合并 `baselinePrefill`

**Files:**

- Create: `frontend/src/crf/baselinePrefill.ts`
- Create: `frontend/src/crf/baselinePrefill.test.ts`

- [ ] **Step 1: 定义患者 DTO 与 `mergePatientIntoBaselineApiPayload`**

`frontend/src/crf/baselinePrefill.ts`：入参 `baselineApi` 为 `GET /patients/{id}/baseline/` 的 JSON（日期字段为 **YYYY-MM-DD 字符串**，数字为 number），出参同形，仅补空字段：

```typescript
export type PatientPrefillSource = {
  name: string;
  gender: string;
  birth_date: string | null;
  age: number | null;
};

function isEmpty(v: unknown): boolean {
  if (v === null || v === undefined) return true;
  if (typeof v === "string") return v.trim() === "";
  return false;
}

import { crfNameInitialsFour } from "./nameInitials";

/** 仅填空：不覆盖 baseline 中已有非空值（API 层）。 */
export function mergePatientIntoBaselineApiPayload(
  patient: PatientPrefillSource,
  baselineApi: Record<string, unknown>,
): Record<string, unknown> {
  const out = { ...baselineApi, demographics: { ...((baselineApi.demographics as object) ?? {}) } };
  const demo = out.demographics as Record<string, unknown>;

  if (isEmpty(out.name_initials) && patient.name?.trim()) {
    out.name_initials = crfNameInitialsFour(patient.name);
  }
  if (isEmpty(demo.birth_date) && patient.birth_date) {
    demo.birth_date = patient.birth_date;
  }
  if (isEmpty(demo.age_years) && patient.age != null) {
    demo.age_years = patient.age;
  }
  if (isEmpty(demo.gender)) {
    if (patient.gender === "male") demo.gender = "男";
    else if (patient.gender === "female") demo.gender = "女";
  }
  return out;
}
```

页面中的顺序应为：`const merged = mergePatientIntoBaselineApiPayload(patient, baseline); form.setFieldsValue(baselineToFormValues(merged));`

- [ ] **Step 2: Vitest 覆盖不覆盖已有值**

```typescript
import { describe, expect, it } from "vitest";
import { mergePatientIntoBaselineApiPayload } from "./baselinePrefill";

describe("mergePatientIntoBaselineApiPayload", () => {
  it("does not overwrite existing name_initials", () => {
    const base = { name_initials: "ABCD", demographics: {} };
    const r = mergePatientIntoBaselineApiPayload(
      { name: "新名字", gender: "male", birth_date: null, age: null },
      base,
    );
    expect(r.name_initials).toBe("ABCD");
  });
});
```

- [ ] **Step 3: 运行测试**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npx vitest run src/crf/baselinePrefill.test.ts
```

Expected: PASS。

---

### Task 5: 基线专用渲染（Radio + 其他备注）

**Files:**

- Create: `frontend/src/crf/renderBaselineRegistryFields.tsx`
- Modify: `frontend/src/crf/renderRegistryFields.tsx`（按需导出 `baselineToFormValues` 或拆分 import，避免循环依赖）

- [ ] **Step 1: 实现 `renderBaselineRegistryField`**

要点：

- `single_choice`：`Form.Item` 包裹 `Radio.Group`，`options.map` → `Radio value={o}` 子节点。
- 若 `field.options?.includes("其他")` 且 `field.other_remark_storage`：用 `baselineStorageToFormName(field.other_remark_storage)` 得备注 `name` 数组；在 `Radio.Group` 下增加 `Form.Item`（`noStyle` + `shouldUpdate` 或 `Form.useWatch`）当主字段值为「其他」时渲染 `Input` / `Input.TextArea`（由 `other_remark_widget` 决定）。
- `number` / `date` / `text` / `textarea`：可从 `renderRegistryFields.tsx` 复制与 `renderBaselineRegistryField` 相同的 JSX 片段，或把非 choice 抽成共享内部函数放在 `renderRegistryFields.tsx` 并 export。

**禁止**修改 `renderVisitRegistryField` 内 `single_choice` 仍使用 `Select` 的行为。

- [ ] **Step 2: 导出 `baselineToFormValues`**

确保 `PatientCrfBaselinePage` 仍从同一模块导入 `baselineToFormValues`；若移到 `baselineFormValues.ts` 需同步所有 import（YAGNI：优先保留在 `renderRegistryFields.tsx` export）。

---

### Task 6: `PatientCrfBaselinePage` 接线

**Files:**

- Modify: `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`

- [ ] **Step 1: 并行请求患者与 baseline**

使用 `useQueries` 或两个 `useQuery`，第二个 `enabled` 在 `id` 有效时 true。

- [ ] **Step 2: `useEffect` 合并初值**

顺序：`mergePatientIntoBaselineApiPayload(patient, baseline)` → `baselineToFormValues(merged)` → `form.setFieldsValue(...)`。仅在两请求均 success 后执行；注意依赖数组避免无限循环。

- [ ] **Step 3: Collapse 标题**

```typescript
const title = registry.table_titles?.[tableRef] ?? tableRef;
```

- [ ] **Step 4: 双列布局**

在每个 `Collapse` 的 `children` 外包一层：

```tsx
<div
  style={{
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 360px), 1fr))",
    columnGap: 24,
    rowGap: 0,
  }}
>
```

并在 `window.matchMedia("(min-width: 1200px)")` 时更倾向两列：可用 `useMediaQuery`（antd `Grid.useBreakpoint`）当 `screens.xl` 为 true 时设置 `gridTemplateColumns: "1fr 1fr"`，否则 `1fr`。与 spec「min-width: 1200px」对齐即可。

- [ ] **Step 5: 放宽表单宽度**

例如 `style={{ maxWidth: 1120 }}`（按布局微调）。

- [ ] **Step 6: 将 `renderBaselineRegistryField` 替换原 `renderBaselineRegistryField` import 来源**

指向 `renderBaselineRegistryFields.tsx`。

- [ ] **Step 7: 构建**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run build && npm run lint
```

Expected: 无 TS / ESLint 错误。

---

### Task 7: 后端完整 payload 与 `other_remark` 校验

**Files:**

- Modify: `backend/apps/patients/serializers.py`
- Modify: `backend/apps/crf/registry_validate.py`
- Modify: `backend/apps/crf/tests/test_registry_validate.py`

- [ ] **Step 1: `PatientBaselineSerializer.validate` 合并实例后再校验**

在 `PatientBaselineSerializer.validate` 中，在调用 `validate_patient_baseline_payload` 之前构造 `full`：

```python
def validate(self, attrs: dict) -> dict:
    attrs = super().validate(attrs)
    inst = self.instance
    full: dict = {}
    for k in _BASELINE_REGISTRY_FIELD_NAMES:
        if k in attrs:
            full[k] = attrs[k]
        elif inst is not None:
            full[k] = getattr(inst, k)
    if not any(k in attrs for k in _BASELINE_REGISTRY_FIELD_NAMES):
        return attrs
    errors = validate_patient_baseline_payload(full)
```

注意：`for k in _BASELINE_REGISTRY_FIELD_NAMES` 若 `attrs` 含某键则用 attrs 覆盖；若本次 PATCH 未传某 JSON 字段则用实例上的 dict，以便交叉校验能看到当前库里的 `marital_status`。

修正逻辑应为：

```python
full = {}
for k in _BASELINE_REGISTRY_FIELD_NAMES:
    if inst is not None:
        full[k] = getattr(inst, k)
for k in _BASELINE_REGISTRY_FIELD_NAMES:
    if k in attrs:
        full[k] = attrs[k]
```

再 `validate_patient_baseline_payload(full)`。

- [ ] **Step 2: 在 `registry_validate.py` 增加 `_validate_other_remarks`**

在 `validate_patient_baseline_payload` 末尾、`return errors` 前：

- 遍历 `reg["fields"]` 中 `storage` 以 `patient_baseline.` 开头且含 `other_remark_storage` 的字段。
- `parent_parts` = 主字段 `storage` 去前缀后 split。
- `present_parent, parent_val = _get_submitted_value(data, parent_parts)`。
- `remark_path` = `other_remark_storage` 去 `patient_baseline.` 后 split。
- `present_r, remark_val = _get_submitted_value(data, remark_parts)`。
- 若 `present_parent` 且 `parent_val == "其他"`：
  - 若 `field.get("required_for_complete")` 且 `remark` 空白 → `errors[".".join(remark_parts)] = "选择「其他」时必须填写备注"`。
- 若 `present_r` 且 `remark_val` 非空且非 str → 类型错误。

（文案可与项目现有中文错误风格统一。）

- [ ] **Step 3: pytest（monkeypatch 最小 registry）**

在 `test_registry_validate.py` 增加：

```python
def test_other_requires_remark_when_required(monkeypatch):
    fake = {
        "fields": [
            {
                "field_id": "t",
                "widget": "single_choice",
                "storage": "patient_baseline.demographics.ethnicity",
                "options": ["汉族", "其他"],
                "required_for_complete": True,
                "other_remark_storage": "patient_baseline.demographics.ethnicity_other_remark",
            }
        ]
    }

    def _load():
        return fake

    monkeypatch.setattr("apps.crf.registry_validate.load_crf_registry", _load)
    errors = validate_patient_baseline_payload(
        {"demographics": {"ethnicity": "其他", "ethnicity_other_remark": ""}}
    )
    assert "demographics.ethnicity_other_remark" in errors
```

再写一个 `remark` 已填时 `errors` 不含该键的用例。

- [ ] **Step 4: 运行后端测试**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest apps/crf/tests/test_registry_validate.py apps/patients/tests/test_patient_baseline_api.py -q
```

Expected: 全部 PASS。

---

### Task 8: 收尾与 spec 实施基线

**Files:**

- Modify: `docs/superpowers/specs/2026-05-12-patient-crf-baseline-form-ux-design.md`（填写「实施基线 commit」短 SHA）

- [ ] **Step 1: 全量验证（AGENTS 6.3）**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run test && npm run lint && npm run build
```

- [ ] **Step 2: 更新 design spec 头部「实施基线 commit」**

填本次合并或主干上实施完成后的短 SHA。

- [ ] **Step 3: Commit（可选）**

按仓库约定一条或多条中文 message 提交。

---

## Plan 自检（对照 spec）

| Spec 章节 | 对应 Task |
|-----------|-----------|
| `table_titles` | Task 1、2、6 |
| `other_remark_storage` + 必填交叉 | Task 1、5、7 |
| 预填只填空、性别/年龄/出生日期/缩写 | Task 3、4、6 |
| 基线 Radio、非访视 | Task 5、6 |
| 双列断点 ≥1200px | Task 6 |
| 后端校验 | Task 7 |
| 测试 | Task 3–4、7、8 |

**占位扫描：** 本计划无 TBD /「后续再写」类步骤。  
**命名一致：** `other_remark_storage`、`table_titles`、`crfNameInitialsFour`、`mergePatientIntoBaselineApiPayload` 全文一致。

**可选后续（本 plan 不强制）：** `build_crf_preview` 的 `missing_fields` 在「必填 + 其他 + 空备注」场景的增强；若当前 registry 无 `required_for_complete` +「其他」组合，可仅保留校验逻辑待模板变更。

---

## 执行方式（实施完成后由执行者选用）

Plan 已保存到 `docs/superpowers/plans/2026-05-12-patient-crf-baseline-form-ux.md`。

**1. Subagent-Driven（推荐）** — 每个 Task 新开子代理，任务间人工快速 review。  
**2. Inline Execution** — 本会话用 executing-plans 按 Task 顺序执行并设检查点。

你更倾向哪一种？
