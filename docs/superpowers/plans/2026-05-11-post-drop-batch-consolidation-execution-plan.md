# MotionCare：drop-batch 后文档、测试与验收收口 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development（推荐：每任务独立子代理 + 双阶段 review）或 superpowers:executing-plans（本会话逐步执行）。步骤使用 `- [ ]` 勾选跟踪。

> **执行方式说明：** `subagent-driven-development` 与 `executing-plans` **二选一**执行本计划，不要并行混用两套流程。执行前若须在 `main` 上动代码，须征得负责人同意；否则按 `using-git-worktrees` 开分支或 worktree。

**Goal:** 在已合并 **无 `GroupingBatch`** 的后端/主线实现（`randomize` / `reset-pending` / `confirm-grouping` / `enroll-projects` 含 `enrollments` + 直接 `confirmed`）之上，**对齐** `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md` 与 `docs/superpowers/plans/2026-05-11-drop-batch-concept.md` 的**文档真相与验收勾选**；补齐 **Vitest 组件级**看板用例；建立可重复的 **验证命令**（verification-before-completion）。

**Architecture:** 以 **`2026-05-11-drop-batch-concept.md`** 为 API/数据语义来源；以 **`2026-05-11-patient-project-admin-and-grouping-board-design.md`** 为交互与合规（二次确认、解绑后果等）来源。二者冲突时 **以 drop-batch 与当前 `main` 代码为准**，并 **回写 design spec**。应用代码仅在验收发现缺口时修改。

**Tech Stack:** Django 5、DRF、pytest；Vite、React 18、TypeScript、Vitest、TanStack Query v5、Ant Design 5、@dnd-kit。

---

## 文件与职责

| 路径 | 职责 |
|------|------|
| `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md` | 删除过时「GroupingBatch 仍存在」表述；入组/患者池/随机范围与 `main` 一致 |
| `docs/superpowers/plans/2026-05-11-drop-batch-concept.md` | 状态改为已落地或部分落地；第四节勾选与证据 |
| `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx` | 新建：池过滤 + 已确认标签 |
| `specs/patient-rehab-system/README.md` 等（可选） | 与 C1 一致的术语补充 |

---

### Task 1: 回写 design spec（与 `main` 一致）

**Files:**

- Modify: `docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md`

- [ ] **Step 1: 替换「实现备注」中关于 `GroupingBatch` 的段落**

将含「当前代码存在 `GroupingBatch`…」的 **实现备注** 整段替换为：

```markdown
**实现备注（给工程，非产品文案）**：`GroupingBatch` 模型及 `ProjectPatient.grouping_batch` 已从应用 schema 移除（见 `studies` 迁移 `0002_remove_projectpatient_grouping_batch_and_more`）。随机与确认由 `POST /api/studies/projects/{id}/randomize/`、`reset-pending/`、`confirm-grouping/` 与 `ProjectPatient.grouping_status` 承担。**解绑** 为 `POST /api/studies/project-patients/{id}/unbind/`（实现见 `backend/apps/studies/`）。
```

- [ ] **Step 2: 更新「加入研究项目」目标条文**

将「加入后请到**各项目详情看板**完成勾选与随机分组」改为与当前 API 一致：

- 入参为 **`enrollments: [{ project_id, group_id }, ...]`**；服务端 **直接创建 `ProjectPatient` 且 `grouping_status=confirmed`**（见 `PatientViewSet.enroll_projects`）。
- 若产品仍希望「先入组再随机」的流程，须在 **单独产品决策** 后改代码；**在改代码前** design spec 不得再写「仅看板入组」单一流程。

（实现者将上述两句合并为一条 spec 正文 bullet。）

- [ ] **Step 3: 更新「患者池」与「随机分组范围」**

- **患者池**：UI 展示全库患者，但 **已存在任意本项目 `ProjectPatient`（pending 或 confirmed）的患者** 不出现在池中；解绑后重新出现（与 `ProjectGroupingBoard` 中 `enrolledPatientIds` 逻辑一致）。
- **随机分组**：与后端 `randomize` 一致——**池内勾选的患者 id + 本项目内所有 `grouping_status=pending` 且已分配 `group` 的入组行** 一并参与重新分配；**confirmed** 不变。

- [ ] **Step 4: 简化「项目删除」规则表述**

与 `StudyProjectViewSet.destroy` 对齐：存在 **任意** `ProjectPatient` 即禁止删除；删除「待确认分组工作集 / 批次」等旧措辞。

- [ ] **Step 5: 修订记录**

追加一行：`2026-05-11：与已合并 drop-batch 实现及 enroll-projects 直接确认入组对齐。`

- [ ] **Step 6: Git 提交**

```bash
git add docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md
git commit -m "docs(spec): 与drop-batch主线实现同步"
```

---

### Task 2: 更新 `drop-batch-concept` 计划状态与验收勾选

**Files:**

- Modify: `docs/superpowers/plans/2026-05-11-drop-batch-concept.md`

- [ ] **Step 1: 更新文件头「状态」与「基线」**

- `状态：` 改为 `已落地（主线）` 或 `已落地，文档收口见 2026-05-11-post-drop-batch-consolidation-execution-plan.md`。
- `基线：` 更新为当前 `main` 上代表 drop-batch 合并的 commit（如 `fa686e5`，以 `git log -1 --oneline` 为准）。

- [ ] **Step 2: 第四节验收准则改为已勾选（仅在有证据时勾选）**

在运行完 **Task 5** 的验证命令后，将下列项改为 `- [x]`（若任一项失败则 **不得** 勾选）：

- 后端 pytest 全绿  
- 前端 vitest 全绿  
- 应用代码（排除 `**/migrations/**`）中无 `GroupingBatch` / `grouping_batch` / `grouping-batches` / `create_grouping_batch` / `discard-grouping-draft`  
- `enroll-projects` 为 `enrollments` + confirmed（已由 `test_enroll_projects.py` 覆盖则勾选）

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/plans/2026-05-11-drop-batch-concept.md
git commit -m "docs(plan): drop-batch计划状态与验收勾选同步主线"
```

---

### Task 3: 字符串审计（应用代码）

**Files:** 无代码修改，仅命令输出归档到 PR 描述或本计划备注。

- [ ] **Step 1: 在仓库根执行（有 `rg` 用 `rg`，否则用 IDE / `git grep` 等价搜索）**

```bash
rg "GroupingBatch|grouping_batch|grouping-batches|create_grouping_batch|discard-grouping-draft" \
  --glob "*.py" --glob "*.ts" --glob "*.tsx" \
  --glob '!**/migrations/**'
```

- [ ] **Step 2: 预期**

**无匹配**（仅允许出现在 `migrations/` 下的历史迁移中）。若有匹配，创建 **Task 3b** 删除残留并补测。

---

### Task 4: 新增 `ProjectGroupingBoard.test.tsx`

**Files:**

- Create: `frontend/src/pages/projects/ProjectGroupingBoard.test.tsx`

- [ ] **Step 1: 写入以下完整测试文件**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ProjectGroupingBoard } from "./ProjectGroupingBoard";

const { mockGet, mockPost } = vi.hoisted(() => ({
  mockGet: vi.fn(),
  mockPost: vi.fn(),
}));

vi.mock("../../api/client", () => ({
  apiClient: {
    get: (...args: unknown[]) => mockGet(...args),
    post: (...args: unknown[]) => mockPost(...args),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("ProjectGroupingBoard", () => {
  beforeEach(() => {
    mockGet.mockReset();
    mockPost.mockReset();
    mockGet.mockImplementation((url: string, config?: unknown) => {
      const params =
        typeof config === "object" && config
          ? (config as { params?: Record<string, unknown> }).params
          : undefined;

      if (url === "/patients/") {
        return Promise.resolve({
          data: [
            { id: 1, name: "池外甲", gender: "male", phone: "13900000001" },
            { id: 201, name: "已入组乙", gender: "female", phone: "13900000201" },
            { id: 202, name: "待确认丙", gender: "male", phone: "13900000202" },
          ],
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
      if (url === "/studies/project-patients/" && params?.project === 1) {
        return Promise.resolve({
          data: [
            {
              id: 9001,
              project: 1,
              patient: 201,
              patient_name: "已入组乙",
              patient_phone: "13900000201",
              group: 10,
              grouping_status: "confirmed",
            },
            {
              id: 9002,
              project: 1,
              patient: 202,
              patient_name: "待确认丙",
              patient_phone: "13900000202",
              group: 11,
              grouping_status: "pending",
            },
          ],
        });
      }
      return Promise.reject(new Error(`unmocked GET ${url}`));
    });
  });

  it("患者池不包含已入本项目者且列内已确认卡片含已确认标签", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <ProjectGroupingBoard projectId={1} />
      </QueryClientProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText(/患者池/)).toBeInTheDocument();
    });
    expect(screen.getByText(/池外甲/)).toBeInTheDocument();
    expect(screen.queryByText(/已入组乙/)).not.toBeInTheDocument();
    expect(screen.queryByText(/待确认丙/)).not.toBeInTheDocument();
    expect(screen.getAllByText("已确认").length).toBeGreaterThan(0);
  });
});
```

- [ ] **Step 2: 运行 Vitest**

```bash
cd frontend && npx vitest run src/pages/projects/ProjectGroupingBoard.test.tsx
```

Expected: **PASS**（组件含 `Link`，须 **`MemoryRouter`** 包裹；断言池过滤须用 **`within(患者池 Card)`**，避免与列内姓名冲突。）

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/projects/ProjectGroupingBoard.test.tsx
git commit -m "test(frontend): ProjectGroupingBoard池过滤与已确认标签"
```

---

### Task 5: 全量验证（verification-before-completion）

- [ ] **Step 1: 后端**

```bash
cd backend && pytest -q
```

Expected: **全部通过**（当前基线为 43 passed，若数量变化以 0 failures 为准）。

- [ ] **Step 2: 前端**

```bash
cd frontend && npm run test
cd frontend && npm run build
cd frontend && npm run lint
```

Expected: **test 0 failed**；**build exit 0**；**lint 0 errors**（warnings 可接受但须在 PR 中列出）。

- [ ] **Step 3: 将命令输出摘要附在 PR 或回复负责人**（满足「证据先于结论」）。

---

## 自检（spec 覆盖）

| 设计要点 | Task |
|----------|------|
| 无批次、randomize/reset/confirm | Task 1、2、3 |
| 患者池过滤 | Task 1、4 |
| enrollments 直接确认 | Task 1 |
| 验收可重复 | Task 5 |

---

## 执行交接

计划已保存至：`docs/superpowers/plans/2026-05-11-post-drop-batch-consolidation-execution-plan.md`。

**1. Subagent-Driven（推荐）** — 每 Task 派独立子代理，spec review → code quality review → 勾选。  
**2. Inline executing-plans** — 在本会话按 Task 1→5 顺序执行，每 Task 后停顿检查。

请选择其一执行；完成 **Task 5** 前不得声明「计划已完成」。
