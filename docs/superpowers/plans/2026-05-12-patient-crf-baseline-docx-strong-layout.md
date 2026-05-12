# 患者 CRF 基线 docx 强一致表格布局 Implementation Plan

执行记录（2026-05-12, Cursor / Subagent-Driven）：Task 1–12 已落地；`validate_baseline_registry_layout.py`、`backend pytest`（93）、`frontend vitest`（44）、`lint`、`build` 均通过。主要提交：`dd649c1`（spec §10）、`1987f71`（registry 生成）、`747c430`（pytest）、`a70e199`/`bb8d479`（前端表布局 + 单测）。HEAD：`bb8d479`。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基线页 `/patients/:patientId/crf-baseline` 的节顺序与 Word 修订稿表格一致；单选 Radio 横向排列；所有语义为日期的 `patient_baseline.*` 字段在 registry 中为 `widget: "date"` 并统一 DatePicker；节内以 **`<table>` + registry 双轨 `baseline_table_layout`** 还原 docx 行列（含 colspan）；`scripts/build_crf_registry_v1.py` 成为含 `table_titles` / `other_remark_storage` / 布局的**单一生成真源**，避免再跑脚本覆盖手改 JSON。

**Architecture:** 在 `registry.v1.json` 根对象增加 `baseline_section_order: string[]` 与 `baseline_table_layout: Record<table_ref, { rows: BaselineLayoutRow[] }>`（`BaselineLayoutRow` 为 `{ cells: BaselineLayoutCell[] }`，`BaselineLayoutCell` 为 `{ field_id?: string; colspan?: number; rowspan?: number; blank?: boolean }`）。`build_crf_registry_v1.py` 在输出 `doc` 时合并 `fields`、既有 `table_titles`、既有 `other_remark_*` 与新建布局结构；`npm run sync-crf-registry` 不变。前端用布局渲染表；无布局的 `table_ref` 可 **assert 不存在**（本计划要求基线涉及节全覆盖）。后端校验仍遍历 `fields`，不因布局新增路径。

**Tech Stack:** Python 3、`python-docx`（已用于 dump）、TypeScript、Ant Design 5 `Form`、Vitest、pytest。

**验收回滚参考：** 标签 `baseline-ux-acceptance-checkpoint-2026-05-12` / 提交 `e37d8a4`；HEAD 在 `6ab1378` 之后继续开发。

---

## 文件结构（创建 / 修改）

| 路径 | 职责 |
|------|------|
| `docs/superpowers/specs/2026-05-12-patient-crf-baseline-form-ux-design.md` | 追加 §10「强一致表格与节顺序」契约（或独立 spec 并在此文加链接） |
| `scripts/build_crf_registry_v1.py` | 生成 `table_titles`、`other_remark_storage`/`other_remark_widget`、`baseline_section_order`、`baseline_table_layout`；`diagnosed_at` 等改为 `date` |
| `scripts/validate_baseline_registry_layout.py`（新建） | 校验：每个基线 `field_id` 在 layout 中恰好出现一次；layout 引用的 id 均存在；`baseline_section_order` 与 layout keys 一致 |
| `specs/patient-rehab-system/crf/registry.v1.json` | 由脚本重写 |
| `frontend/src/crf/registry.v1.json` | `npm run sync-crf-registry` |
| `frontend/src/crf/types.ts` | `BaselineLayoutCell`、`BaselineLayoutRow`、`BaselineTableLayout`、`CrfRegistry` 扩展 |
| `frontend/src/crf/renderBaselineRegistryFields.tsx` | Radio 横向；可选导出「单字段渲染」供表内调用 |
| `frontend/src/crf/BaselineLayoutTable.tsx`（新建） | 读 `baseline_table_layout[#T*]` 输出 `<table>` + `<tbody>`，单元格内嵌 `Form.Item` |
| `frontend/src/pages/patients/PatientCrfBaselinePage.tsx` | 按 `baseline_section_order` 排序节；节内优先 `<BaselineLayoutTable>` |
| `frontend/package.json` | 若表样式需独立 less 则无；优先内联 `style` |
| `backend/apps/crf/tests/test_registry_baseline_layout.py`（新建） | 调用 `validate_baseline_registry_layout` 或内联断言加载后 registry |
| `frontend/src/crf/baselineSectionOrder.test.ts`（新建） | 纯函数：给定 order 与 `fieldsByTable` 重排 |

---

### Task 1: 规格增量（design spec）

**Files:**

- Modify: `docs/superpowers/specs/2026-05-12-patient-crf-baseline-form-ux-design.md`

- [ ] **Step 1: 在文末尾追加 §10（建议标题：基线 docx 强一致布局）**

正文至少包含：

- `baseline_section_order`：字符串数组，元素为基线涉及的 `table_ref`，顺序 = 修订稿中表格出现顺序（`#T0` → `#T8` → `#T9` → `#T10` → `#T11` → `#T12`），**禁止**用 `localeCompare` 对 `#T10`/`#T8` 排序。
- `baseline_table_layout[#T8].rows[]`：每行对应 docx 中该表的一行；`cells[]` 顺序 = 左→右；`field_id` 与 `build_crf_registry_v1.py` 中 `field_id` 一致。
- `blank: true`：仅占位，不绑定字段。
- `colspan`/`rowspan`：与 Word 一致时填写；前端用 `<td colSpan={n} rowSpan={m}>`。
- **B 类日期**：凡 label 与 docx 明确为「年/月/日」或「日期」且存储为单日期的 `patient_baseline.*`，`widget` 必须为 `date`，值为 `YYYY-MM-DD`。
- **访视**：明确不在本期改布局。

- [ ] **Step 2: Commit（可选）**

```bash
git add docs/superpowers/specs/2026-05-12-patient-crf-baseline-form-ux-design.md
git commit -m "docs(spec): 基线 CRF 强一致表格与节顺序契约"
```

---

### Task 2: TypeScript 类型

**Files:**

- Modify: `frontend/src/crf/types.ts`

- [ ] **Step 1: 追加类型（完整粘贴）**

```typescript
export type BaselineLayoutCell = {
  field_id?: string;
  blank?: boolean;
  colspan?: number;
  rowspan?: number;
};

export type BaselineLayoutRow = {
  cells: BaselineLayoutCell[];
};

export type BaselineTableLayoutBlock = {
  rows: BaselineLayoutRow[];
};

export type CrfRegistry = {
  template_id: string;
  template_revision: string;
  source_docx: string;
  table_titles?: Record<string, string>;
  baseline_section_order?: string[];
  baseline_table_layout?: Record<string, BaselineTableLayoutBlock>;
  fields: RegistryField[];
};
```

（若 `CrfRegistry` 已存在则合并字段，勿重复定义 `template_id` 等两次。）

- [ ] **Step 2: 构建**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run build
```

Expected: exit 0。

---

### Task 3: 校验脚本（布局与 fields 一致）

**Files:**

- Create: `scripts/validate_baseline_registry_layout.py`

- [ ] **Step 1: 实现脚本（完整文件）**

```python
#!/usr/bin/env python3
"""校验 registry.v1.json 中基线 layout 与 fields 一致。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REG = ROOT / "specs" / "patient-rehab-system" / "crf" / "registry.v1.json"


def main() -> int:
    doc = json.loads(REG.read_text(encoding="utf-8"))
    fields = doc.get("fields", [])
    by_id = {f["field_id"]: f for f in fields if isinstance(f, dict) and "field_id" in f}
    baseline_ids = {
        f["field_id"]
        for f in fields
        if isinstance(f.get("storage"), str) and f["storage"].startswith("patient_baseline.")
    }
    order = doc.get("baseline_section_order")
    layout = doc.get("baseline_table_layout") or {}
    if not isinstance(order, list) or not all(isinstance(x, str) for x in order):
        print("ERROR: baseline_section_order 必须是非空字符串数组", file=sys.stderr)
        return 1
    seen: set[str] = set()
    for ref in order:
        block = layout.get(ref)
        if not block or not isinstance(block.get("rows"), list):
            print(f"ERROR: baseline_table_layout 缺少节 {ref}", file=sys.stderr)
            return 1
        for row in block["rows"]:
            for cell in row.get("cells", []):
                fid = cell.get("field_id")
                if not fid:
                    continue
                if fid in seen:
                    print(f"ERROR: field_id 重复出现在 layout 中: {fid}", file=sys.stderr)
                    return 1
                seen.add(fid)
                if fid not in by_id:
                    print(f"ERROR: layout 引用未知 field_id: {fid}", file=sys.stderr)
                    return 1
    missing = baseline_ids - seen
    if missing:
        print(f"ERROR: 下列基线字段未出现在 layout 中: {sorted(missing)}", file=sys.stderr)
        return 1
    extra = seen - baseline_ids
    if extra:
        print(f"ERROR: layout 出现非基线 field_id: {sorted(extra)}", file=sys.stderr)
        return 1
    print("OK baseline layout covers", len(baseline_ids), "fields")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: 在布局 JSON 尚未完整前运行应失败；Task 6 完成后应通过**

```bash
cd /Users/nick/my_dev/workout/MotionCare && python3 scripts/validate_baseline_registry_layout.py
```

---

### Task 4: 扩展 `build_crf_registry_v1.py` — 根元数据与节顺序

**Files:**

- Modify: `scripts/build_crf_registry_v1.py`

- [ ] **Step 1: 在 `main()` 里 `fields` 组装完毕之后、写 `doc` 之前，定义常量**

```python
BASELINE_SECTION_ORDER = ["#T0", "#T8", "#T9", "#T10", "#T11", "#T12"]

TABLE_TITLES = {
    "#T0": "筛选与受试者标识",
    "#T8": "人口学信息",
    "#T9": "手术史与过敏史",
    "#T10": "合并症、既往史与家族史",
    "#T11": "生活方式",
    "#T12": "合并用药",
}
```

（表题须与 `docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx` 核对；若有差异以 docx 为准。）

- [ ] **Step 2: 扩展 `field()` 辅助函数签名**（保持向后兼容），支持 `other_remark_storage: str | None = None`、`other_remark_widget: str | None = None`；若非 `None` 则写入字段 dict。

- [ ] **Step 3: 为 `dm_marital` / `dm_ethnicity` / `dm_insurance` 三处 `field(...)` 调用传入**（与当前 JSON 一致）：

```python
other_remark_storage="patient_baseline.demographics.marital_status_other_remark",
other_remark_widget="text",
```

（ethnicity / insurance 同理，路径见当前 `registry.v1.json`。）

- [ ] **Step 4: 将所有 `*_diagnosed_at` 的 widget 从 `"text"` 改为 `"date"`**（`diseases` 循环内三处 `field(...)`）。

- [ ] **Step 5: `doc` 合并输出**

```python
doc = {
    "template_id": "cognitive_frailty_digital_therapy_crf",
    "template_revision": "1.1（修订稿 2026-04-28）",
    "source_docx": "docs/other/认知衰弱数字疗法研究_CRF表_修订稿.docx",
    "table_titles": TABLE_TITLES,
    "baseline_section_order": BASELINE_SECTION_ORDER,
    "baseline_table_layout": baseline_table_layout(),  # Task 5 实现
    "fields": fields,
}
```

在 Task 5 完成前可临时 `baseline_table_layout: {}` 使脚本可运行，但 Task 6 前必须通过 `validate_baseline_registry_layout.py`。

---

### Task 5: `baseline_table_layout()` 实现（与 `_docx_table_dump.txt` 对照）

**Files:**

- Modify: `scripts/build_crf_registry_v1.py`

- [ ] **Step 1: 新增函数 `baseline_table_layout() -> dict`**

实现策略（**强一致、单脚本真源**）：人工按 `specs/patient-rehab-system/crf/_docx_table_dump.txt` 中 **TABLE 1（封面）**、**TABLE 9（人口学）**、**TABLE 10–13** 的行顺序构造 `rows`；**#T10** 疾病块用循环生成三列 `[{fid}_family, {fid}_personal, {fid}_diagnosed_at]`，与当前 `diseases` 列表顺序一致。

**#T0 示例（两列，与 TABLE 1 非完全等价时可按「编号 + 姓名缩写」两行两列简化，以 field 为准）：**

```python
def baseline_table_layout() -> dict:
    return {
        "#T0": {
            "rows": [
                {"cells": [{"field_id": "pb_subject_id"}, {"field_id": "pb_name_initials"}]},
            ]
        },
        # Task 5 Step 2: 填满 #T8…#T12
    }
```

- [ ] **Step 2: #T8（TABLE 9）**  
  按 dump 行顺序，每 doc 行对应一个 `row`；若一行仅一个「项目」（如居住地址占满宽），使用单 cell `colspan: 2` 或两列中第二列 `blank: true`——与 docx 视觉一致即可，在 spec §10 用一句话说明「宽字段 colspan 规则」。

- [ ] **Step 3: #T9–#T12**  
  对照 dump TABLE 10–13 与现有 `field_id` 列表写完所有行。

- [ ] **Step 4: 运行生成与校验**

```bash
cd /Users/nick/my_dev/workout/MotionCare && python3 scripts/build_crf_registry_v1.py
python3 scripts/validate_baseline_registry_layout.py
python3 -m json.tool specs/patient-rehab-system/crf/registry.v1.json > /dev/null
```

Expected: `Wrote ...`、`OK baseline layout covers N fields`。

---

### Task 6: 同步前端 registry

**Files:**

- 由命令刷新 `frontend/src/crf/registry.v1.json`

- [ ] **Step 1:**

```bash
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run sync-crf-registry
```

---

### Task 7: 后端测试（加载 registry 不崩 + 日期字段）

**Files:**

- Create: `backend/apps/crf/tests/test_registry_baseline_layout.py`

- [ ] **Step 1: 测试 `diagnosed_at` 走 date 校验**

```python
import pytest

from apps.crf.registry_validate import validate_patient_baseline_payload


@pytest.mark.django_db
def test_comorbidity_diagnosed_at_rejects_bad_date():
    errors = validate_patient_baseline_payload(
        {
            "comorbidities": {
                "cm_coronary": {"family": "否", "personal": "否", "diagnosed_at": "not-a-date"},
            }
        }
    )
    assert "comorbidities.cm_coronary.diagnosed_at" in errors
```

（与 `build_crf_registry_v1.py` 中 `storage` 为 `patient_baseline.comorbidities.{fid}.diagnosed_at`、`fid` 为 `cm_coronary` 等一致。）

- [ ] **Step 2: 运行**

```bash
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest apps/crf/tests/test_registry_baseline_layout.py -q
```

---

### Task 8: `BaselineLayoutTable.tsx` 与表内控件

**Files:**

- Create: `frontend/src/crf/BaselineLayoutTable.tsx`
- Modify: `frontend/src/crf/renderBaselineRegistryFields.tsx`（导出 `renderBaselineFieldControl` 或拆分「仅控件」供表内使用，避免 `Form.Item` 双重包裹）

- [ ] **Step 1: 导出无外层 `Form.Item` 的控件渲染**（示意）

在 `renderBaselineRegistryFields.tsx` 增加：

```tsx
export function BaselineFieldControl(props: { field: RegistryField }): ReactNode {
  // 与现有逻辑相同，但不包 Form.Item；single_choice 仍用 Radio.Group + 其他备注分支
}
```

原 `renderBaselineRegistryField` 改为：

```tsx
export function renderBaselineRegistryField(field: RegistryField): ReactNode {
  const label = field.hint ? `${field.label_zh}（${field.hint}）` : field.label_zh;
  const name = baselineStorageToFormName(field.storage);
  if (!name) return null;
  return (
    <Form.Item name={name} label={label} id={`registry-field-${field.field_id}`}>
      <BaselineFieldControl field={field} />
    </Form.Item>
  );
}
```

（若 `single_choice` 结构复杂，可保留独立组件但统一由 `Form.Item` 包裹一层。）

- [ ] **Step 2: `BaselineLayoutTable.tsx` 骨架**

```tsx
import { Form } from "antd";
import type { BaselineTableLayoutBlock, RegistryField } from "./types";
import { renderBaselineRegistryField } from "./renderBaselineRegistryFields";

export function BaselineLayoutTable(props: {
  block: BaselineTableLayoutBlock;
  fieldById: Map<string, RegistryField>;
}): React.ReactElement {
  const { block, fieldById } = props;
  return (
    <table className="crf-baseline-table" style={{ width: "100%", borderCollapse: "collapse" }}>
      <tbody>
        {block.rows.map((row, ri) => (
          <tr key={ri}>
            {row.cells.map((cell, ci) => {
              const cs = cell.colspan ?? 1;
              const rs = cell.rowspan ?? 1;
              if (cell.blank) {
                return <td key={ci} colSpan={cs} rowSpan={rs} style={{ border: "1px solid #d9d9d9" }} />;
              }
              const f = cell.field_id ? fieldById.get(cell.field_id) : undefined;
              return (
                <td key={ci} colSpan={cs} rowSpan={rs} style={{ border: "1px solid #d9d9d9", padding: 8, verticalAlign: "top" }}>
                  {f ? renderBaselineRegistryField(f) : null}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 3: 确认 `DatePicker` 已在 `widget === "date"` 分支**（Task 4 改 widget 后自动覆盖 `diagnosed_at`）。

---

### Task 9: Radio 横向与换行

**Files:**

- Modify: `frontend/src/crf/renderBaselineRegistryFields.tsx`

- [ ] **Step 1: 去掉每个 `Radio` 的 `display: "block"`**，改为在 `Radio.Group` 上：

```tsx
<Radio.Group style={{ display: "flex", flexWrap: "wrap", gap: "8px 16px" }}>
```

- [ ] **Step 2: Vitest 快照或冒烟**（可选）：`npm run test` 全绿即可。

---

### Task 10: `PatientCrfBaselinePage` 接线

**Files:**

- Modify: `frontend/src/pages/patients/PatientCrfBaselinePage.tsx`

- [ ] **Step 1: 构建 `fieldById`**

```tsx
const fieldById = useMemo(() => {
  const m = new Map<string, RegistryField>();
  for (const f of registry.fields as RegistryField[]) {
    m.set(f.field_id, f);
  }
  return m;
}, []);
```

- [ ] **Step 2: 用 `baseline_section_order` 排序节**

```tsx
const orderedSections = useMemo(() => {
  const order = registry.baseline_section_order;
  const map = new Map(fieldsByTable);
  if (!order?.length) return fieldsByTable;
  const out: [string, RegistryField[]][] = [];
  for (const ref of order) {
    const row = map.get(ref);
    if (row) out.push(row);
  }
  for (const [ref, fields] of map) {
    if (!order.includes(ref)) out.push([ref, fields]);
  }
  return out;
}, [fieldsByTable, registry.baseline_section_order]);
```

- [ ] **Step 3: Collapse `items` 使用 `orderedSections`，`children` 为**

```tsx
import { BaselineLayoutTable } from "../../crf/BaselineLayoutTable";

const layout = registry.baseline_table_layout?.[tableRef];
children: layout ? (
  <BaselineLayoutTable block={layout} fieldById={fieldById} />
) : (
  <Alert type="error" message={`缺少 baseline_table_layout：${tableRef}`} />
),
```

（本计划要求布局全覆盖；若需软降级可改为旧 Grid，但**与「不分期强一致」冲突**，默认硬错误更易发现遗漏。）

- [ ] **Step 4: 删除节内原 `display:grid` 包裹**（由 table 负责排版）；保留表单 `maxWidth: 1120` 或按表宽微调。

---

### Task 11: 纯函数测试 `orderedSections`

**Files:**

- Create: `frontend/src/crf/baselineSectionOrder.test.ts`

- [ ] **Step 1:**

```typescript
import { describe, expect, it } from "vitest";

function orderSections(
  pairs: [string, { field_id: string }[]][],
  order: string[],
): string[] {
  const map = new Map(pairs);
  const out: string[] = [];
  for (const ref of order) {
    if (map.has(ref)) out.push(ref);
  }
  for (const [ref] of map) {
    if (!order.includes(ref)) out.push(ref);
  }
  return out;
}

describe("orderSections", () => {
  it("puts #T8 before #T10 when order says so", () => {
    const pairs: [string, { field_id: string }[]][] = [
      ["#T10", [{ field_id: "a" }]],
      ["#T8", [{ field_id: "b" }]],
    ];
    expect(orderSections(pairs, ["#T0", "#T8", "#T10"])).toEqual(["#T8", "#T10"]);
  });
});
```

- [ ] **Step 2:** `npx vitest run src/crf/baselineSectionOrder.test.ts`

---

### Task 12: 全量验证与提交

**Files:**

- Modify: `docs/superpowers/plans/2026-05-12-patient-crf-baseline-docx-strong-layout.md`（勾选已完成 `- [x]`）
- Modify: `docs/superpowers/specs/2026-05-12-patient-crf-baseline-form-ux-design.md`（实施基线 commit 行，实施完成后更新）

- [ ] **Step 1:**

```bash
cd /Users/nick/my_dev/workout/MotionCare && python3 scripts/validate_baseline_registry_layout.py
cd /Users/nick/my_dev/workout/MotionCare/backend && pytest -q
cd /Users/nick/my_dev/workout/MotionCare/frontend && npm run test && npm run lint && npm run build
```

Expected: 全部通过。

- [ ] **Step 2: Commit（建议拆分 2–3 条）**

```bash
git add scripts/build_crf_registry_v1.py scripts/validate_baseline_registry_layout.py specs/patient-rehab-system/crf/registry.v1.json
git commit -m "feat(crf): registry 基线节顺序、table_titles 与 docx 强一致 layout 生成"

git add frontend/src/crf frontend/src/pages/patients/PatientCrfBaselinePage.tsx
git commit -m "feat(frontend): 基线页按 layout 渲染表格与 Radio 横向"

git add backend/apps/crf/tests/test_registry_baseline_layout.py docs/superpowers/specs
git commit -m "test(crf): 基线确诊日期校验；docs(spec) 强一致布局契约"
```

---

## Plan 自检（对照 brainstorming 结论）

| 结论 | Task |
|------|------|
| 节顺序 = docx，不用 `localeCompare` | Task 4、10、11 |
| 单选一行 | Task 9 |
| B：语义日期 → `date` + DatePicker | Task 4（widget）、Task 8 |
| 强一致表格 `<table>` + 双轨 layout | Task 3、5、6、8、10 |
| 不分期（一次交付全部基线节） | Task 5 覆盖 `#T0`–`#T12` 全部 |
| `build_crf_registry_v1.py` 为真源 | Task 4–6；手改 `registry.v1.json` 禁止作为主流程 |
| 回滚点 | 文首 **验收回滚参考**；实施中勿删 tag |

**占位扫描：** 无 TBD；Task 5 中「#T8…#T12 逐行对照 dump」为实施者当场打开 `_docx_table_dump.txt` 与 docx 核对，非占位。

**类型一致：** `field_id`、`table_ref`、`baseline_section_order` 与现有 registry 字段命名一致。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-05-12-patient-crf-baseline-docx-strong-layout.md`. Two execution options:

**1. Subagent-Driven（推荐）** — 每个 Task 新开子代理，任务间 review，迭代快  

**2. Inline Execution** — 本会话用 executing-plans 按 Task 顺序执行并设检查点  

**Which approach?**
