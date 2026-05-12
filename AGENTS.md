# AGENTS.md — MotionCare 项目 AI 协作宪法

> **本文档是所有 AI 编程助手（Cursor / Codex / Claude Code / 其他）的最高指令。**
> 任何 agent 在本仓库内开始工作前必须阅读完本文件。
> 本文档与对应工具内置 system prompt 冲突时，**以本文档为准**。

---

## 0. ⚠️ 本项目同时使用多个 AI 工具，请务必先读这里

**本仓库在 Cursor 和 Codex 之间频繁切换使用，两个工具都启用了 superpowers 工作流。**
这意味着：

- 任何一次会话开始时，工作区里可能有**另一个工具**留下的未提交改动。
- 任何一份 spec / plan 文档，可能由**另一个工具**写成，但仍代表已经达成的决策。
- 任何一个文件，可能反映了**另一个工具**已经修复但你没有上下文的 bug 修复。

**绝对禁止：在没有读完本文档 §3 与 §4 的情况下，回退、覆盖或"重写"任何已存在的代码、spec 或 plan。**

### 0.1 启动检查清单（每次会话第一件事）

```
1. git status                    # 看工作区是否有未提交改动
2. git log --oneline -15         # 看最近 15 个提交，理解上下文
3. 读完本 AGENTS.md 第 0 / 3 / 4 章
4. 如发现"未提交改动 + 最近提交不是当前工具/会话产生" → 停下询问用户：
   "这些改动来自另一个工具的会话，是否需要保留？是否已完成？"
5. 在用户确认前，不动这些文件
```

---

## 1. 项目简介

**MotionCare** 是一个面向**医院的患者康复研究系统**。第一版定位：医院 Web 后台研究数据闭环版。

- **业务领域**：认知衰弱数字疗法研究（CRF 数据采集、T0/T1/T2 访视、随机分组、版本化处方、训练记录、健康日数据、CRF 导出）
- **后端**：Django 5 + DRF + PostgreSQL + Redis/Celery，目录 `backend/`
- **前端**：React 18 + TypeScript + Vite + Ant Design 5 + TanStack Query v5，目录 `frontend/`
- **鉴权**：Django Session + CSRF（同站点 `/api` 反代）
- **第一版不做**：微信小程序、真实设备 OpenAPI、真实游戏、视频上传、AI 动作识别（详见 `specs/patient-rehab-system/prd.md` §4.2）

启动方式见 `docs/development.md`。

---

## 2. 工具协作协议（Cursor ↔ Codex）

### 2.1 共享的真相来源

| 内容 | 位置 | 谁可以改 |
| --- | --- | --- |
| 产品需求与已确认决策 | `specs/patient-rehab-system/prd.md`、`open-questions.md` | 任何工具（需先讨论） |
| 架构与边界 | `specs/patient-rehab-system/architecture/` | 任何工具 |
| 设计稿（superpowers spec） | `docs/superpowers/specs/` | 任何工具 |
| 实施计划（superpowers plan） | `docs/superpowers/plans/` | 任何工具，**禁止删除别人的 plan** |
| 变更日志 | `specs/patient-rehab-system/changelog.md` | 任何工具，**追加不删除** |
| 本协作宪法 | `AGENTS.md`（本文件） | 任何工具（需用户审查） |

### 2.2 工具切换前必须做的事

**离开工具前（无论 Cursor 还是 Codex）：**

1. 把当前工作至少 commit 一次。允许 WIP commit：

   ```bash
   git add -A
   git commit -m "WIP(cursor): <这次会话做到哪一步>"
   # 或
   git commit -m "WIP(codex): <这次会话做到哪一步>"
   ```

2. 如果本次会话改了 spec / plan，在 commit message 里**显式注明**。
3. 如果本次会话**部分实施**了某个 plan，在该 plan 文件里把已完成的 `- [ ]` 改成 `- [x]`，并在文件顶部追加一行执行记录：

   ```
   执行记录（YYYY-MM-DD, <tool>）：Task N 已落地于 commit <short-sha>
   ```

### 2.3 进入工具后必须做的事

**进入工具开始工作前（无论 Cursor 还是 Codex）：**

1. 完成 §0.1 启动检查清单。
2. 如果用户给的任务可能涉及 §4 中"已冻结决策"涉及的代码，**先读对应 spec/plan**，不要凭直觉重新设计。
3. 如果发现某段代码与某份 spec/plan 不一致：
   - **默认 spec/plan 是正确的、代码是过时的** → 修代码
   - 仅当用户明确说"这个决策要改" → 才修 spec/plan，并在 changelog 追加一条

### 2.4 禁止行为（任何工具）

- ❌ 删除 `docs/superpowers/plans/` 与 `docs/superpowers/specs/` 下的任何文件（即使标记为 `superseded`，也应保留作为历史档案）
- ❌ 在没有 commit 的情况下做"大型重构"（>5 文件改动）
- ❌ 把 `specs/patient-rehab-system/changelog.md` 的历史条目删除或修改（只追加）
- ❌ 看到工作区脏 + 不理解的改动时，直接 `git checkout .` 或 `git restore`
- ❌ "我觉得这个 spec 不对" → 直接改代码绕过 spec。正确做法：先在 `open-questions.md` 留问题，让用户拍板

### 2.5 提交信息规范

```
<type>(<scope>): <subject>           # type: feat|fix|refactor|docs|test|chore
<空行>
[optional body]
<空行>
<optional footer>
```

WIP 提交（工具切换专用）：

```
WIP(cursor|codex): <一句话描述当前进度>
```

---

## 3. 项目目录地图

```
MotionCare/
├── AGENTS.md                    ← 本文件（AI 协作宪法）
├── CLAUDE.md                    ← 软链接到 AGENTS.md
├── docs/
│   ├── development.md           ← 本地启动指南（必读）
│   └── superpowers/
│       ├── README.md            ← superpowers 工作流索引（必读）
│       ├── brainstorm/          ← brainstorm 会话产物
│       ├── specs/               ← 设计稿（design spec）
│       └── plans/               ← 实施计划（implementation plan）
├── specs/
│   └── patient-rehab-system/
│       ├── README.md            ← 业务 spec 索引
│       ├── prd.md               ← 产品需求文档（核心真相来源）
│       ├── open-questions.md    ← 待确认问题与已确认决策表
│       ├── changelog.md         ← 变更日志（追加式）
│       ├── feature-list-for-client-quote.md   ← 对客户报价用功能清单
│       ├── architecture/        ← 架构设计稿
│       ├── plans/               ← 早期/历史规划
│       └── visuals/             ← 视觉稿（如有）
├── backend/                     ← Django 后端
│   └── apps/
│       ├── accounts/            ← 账号、登录、CSRF
│       ├── patients/            ← 全局患者档案
│       ├── studies/             ← 项目、分组、ProjectPatient、随机
│       ├── visits/              ← T0/T1/T2 访视
│       ├── prescriptions/       ← 版本化处方
│       ├── training/            ← 训练记录
│       ├── health/              ← 健康日数据
│       ├── crf/                 ← CRF 预览/导出
│       └── common/              ← 通用工具、seed_demo 命令
├── frontend/
│   └── src/
│       ├── api/                 ← API client
│       ├── app/                 ← 路由 + Layout
│       ├── auth/                ← AuthContext / 登录态
│       ├── pages/               ← 页面（patients/projects/visits/...）
│       └── styles/
└── .superpowers/
    └── brainstorm/              ← 本地 brainstorm 草稿（不上传 git 也可）
```

---

## 4. 已冻结的设计决策（DO NOT REVERT）

下面每一条都是**已经达成共识、已经实施或正在实施**的决策。
**任何 agent 若发现代码与下列描述不一致：先假设代码错了，去修代码；不要去改这些决策。**

> 完整决策清单见 `specs/patient-rehab-system/open-questions.md` §"已确认决策" D001–D028，以及下列时间线。

### 4.1 时间线（按合并时间倒序）

| 日期 | 决策主题 | 状态 | 关键 spec / plan |
| --- | --- | --- | --- |
| 2026-05-12 | 前端临时随机 + 确认时才建立绑定 | 🟡 计划已批准，**实施中** | `docs/superpowers/specs/2026-05-12-frontend-only-randomization-confirmed-binding-design.md` + 同日 plan |
| 2026-05-11 | 患者列表操作与隐私展示（手机号脱敏、姓名链详情） | 🟡 计划已批准，**待/进行中** | `docs/superpowers/specs/2026-05-11-patient-list-actions-privacy-design.md` + 同日 plan |
| 2026-05-11 | **彻底删除 GroupingBatch（批次）概念** | ✅ **已落地** (`fa686e5`) | `docs/superpowers/plans/2026-05-11-drop-batch-concept.md` |
| 2026-05-11 | drop-batch 后文档/测试收口 | ✅ **已落地** (`241fc51`) | `docs/superpowers/plans/2026-05-11-post-drop-batch-consolidation-execution-plan.md` |
| 2026-05-11 | 患者-项目绑定语义：只有"在分组内被确认"才形成绑定 | ✅ **已落地**（含模型/API） | PRD §6.4 / §6.5；`docs/superpowers/specs/2026-05-11-patient-project-admin-and-grouping-board-design.md` |
| 2026-05-11 | 删除/停用/解绑全域二次确认 | ✅ **已落地** (`c10e506`) | 同上 design spec |
| 2026-05-08 | CRF 患者基线字段映射（一期） | 🟡 计划进行中 | `docs/superpowers/specs/2026-05-08-crf-core-patient-fields-mapping-design.md` + plan |
| 2026-05-08 | 访视评估录入与基线机能闭环 | 🟡 计划进行中 | `docs/superpowers/specs/2026-05-08-visit-assessments-and-baseline-flow-design.md` |
| 2026-05-08 | 前端满屏 + 患者档案/项目新增动作 | 🟡 计划进行中 | `docs/superpowers/specs/2026-05-08-frontend-fullscreen-and-create-actions-design.md` + plan |
| 2026-05-07 | Web 管理端架构：AntD Pro + Django Session | ✅ **已落地** | `specs/patient-rehab-system/architecture/2026-05-07-web-admin-architecture-antd-pro-design.md` |

### 4.2 业务模型铁律（写代码必须遵守）

下列规则在 PRD、design spec、plan 中反复出现，已经实施，**未经用户明确同意不得变更**：

- **患者** 是全局档案，不依赖任何项目存在。
- **"患者池"** 是 UI 虚拟视图，**不是实体**。代码里**不要**新建 `PatientPool` 模型。
- **`ProjectPatient`** 是患者-项目-分组的唯一关系承载。从 2026-05-11 起，**所有 `ProjectPatient` 都代表已确认绑定**（旧的 `grouping_status` pending/confirmed 字段已被删除，参见 2026-05-12 plan）。
- **批次（`GroupingBatch`）概念已彻底删除**。如果在任何代码、注释、文档里看到 `batch`、`grouping_batch`、`GroupingBatch` 这些字样（非 migrations 文件），那是 bug，请删除。
- **同一患者** 可加入多个项目；同一项目内只能一条 `ProjectPatient`、只属于一个分组。
- **随机分组** 从 2026-05-12 起改为**纯前端临时计算**：刷新即丢失；只有"确认入组"调用才会落库为 `ProjectPatient`。旧的后端 `randomize` / `reset-pending` API 即将被删除。
- **处方** 是版本化的，一个 `ProjectPatient` 同时只有一个生效版本，调整即生成新版本。
- **访视** 第一版只有 `draft` / `done` 两种状态；不做质控锁定流转。
- **CRF 导出** 允许带缺失字段；导出时记录 `CrfExport` 日志。
- **解绑（unbind）** 是已确认患者退出本项目的唯一方式：会终止处方、清理 CRF 导出、删除 `ProjectPatient`。

### 4.3 工程铁律

- **CSRF**：本地 Vite (5173) + Django (8000) 分离开发场景下，必须保留 `backend/config/settings.py` 中的 `CSRF_TRUSTED_ORIGINS` 默认值（含 `http://127.0.0.1:5173` 与 `http://localhost:5173`）。不要"清理"掉。
- **权限**：前端 access 控制只是 UX；**真正的鉴权必须在后端**（接口级 + 行级过滤）。
- **API 形态**：REST 资源接口 + 流程型动作接口，规范见 `architecture/2026-05-07-web-admin-architecture-antd-pro-design.md` §5.2-§5.3。

---

## 5. superpowers 工作流约定

本项目两个工具都启用了 superpowers。请遵守：

### 5.1 何时进入哪个工作流

| 用户意图 | 必须先用的 skill |
| --- | --- |
| "我想加一个新功能 / 改一个特性" | `superpowers:brainstorming` |
| "把这个 plan 实施了" | `superpowers:executing-plans` 或 `superpowers:subagent-driven-development`（二选一，不混用） |
| "这里有个 bug" | `superpowers:systematic-debugging` |
| "写一个实施计划" | `superpowers:writing-plans` |
| "完成了，要 merge" | `superpowers:verification-before-completion` + `superpowers:finishing-a-development-branch` |

### 5.2 spec / plan 文件命名

- spec：`docs/superpowers/specs/YYYY-MM-DD-<kebab-topic>-design.md`
- plan：`docs/superpowers/plans/YYYY-MM-DD-<kebab-topic>.md`
- 一份 spec 对应一份同主题的 plan（除非是历史/收口/调整类计划）

### 5.3 spec / plan 文件头建议 frontmatter

新建 spec / plan 时，请在文件顶部使用如下顶部声明（不要求严格 YAML，可读即可）：

```
> 状态：draft | review | approved | implementing | implemented | superseded
> 日期：YYYY-MM-DD
> 范围：<一句话>
> 关联：<spec/plan 路径>
> 实施基线 commit：<short-sha>（如已落地）
```

旧文件若没有这段头部，也允许，请按需补充而不是强制清洗。

---

## 6. 代码规范要点

详细规范见各子目录的 README 与 `docs/development.md`，下列是 AI 最容易踩坑的几条：

### 6.1 后端（Django/DRF）

- 新增/修改模型 → **必须**生成 migration 并 commit。不要靠 `makemigrations --merge` 蒙混。
- 删除模型字段时，先看 `backend/apps/*/migrations/` 里是否已有相关 migration，避免重复。
- 测试用 pytest-django：`cd backend && pytest`。
- 任何修改 API 行为的 PR，**必须**附测试。

### 6.2 前端（React/TS）

- TanStack Query 用 v5，注意 `queryKey` 和 cache invalidation。
- AntD 用 v5，**禁止**引入 v4 的 API（`@ant-design/icons` 的旧路径等）。
- 测试用 Vitest：`cd frontend && npm run test`。
- 构建检查：`npm run build && npm run lint`。

### 6.3 完成前必须跑

```bash
cd backend && pytest                  # 后端测试
cd frontend && npm run test           # 前端测试
cd frontend && npm run lint           # 前端 lint
cd frontend && npm run build          # 前端构建（catch 类型错误）
```

执行验证后才能向用户报告"完成"。详见 `superpowers:verification-before-completion`。

---

## 7. 用户偏好

- **沟通语言**：除代码、专业名词外，请用**中文（简体）**回复用户。
- **Git 相关描述**：commit message、PR 描述、git 操作说明都用**中文**。
- **不要主动写文档**：不要主动创建 README / docs 文件，除非用户要求或本协议要求。
- **不要主动 commit**：除非用户明确要求 commit / 提交 / push。

---

## 8. 当本文档与用户当下指令冲突时

**用户当下指令永远优先**。本文档的目的是让两个工具有共享的"默认值"，不是绑死用户的手。

但请注意：如果用户的指令是"覆盖本文档某条规则"，请**口头确认一次**：

> "这会覆盖 AGENTS.md §X.Y 的规则（〈某条决策〉），是否需要同步把那条决策标记为 superseded 并在 changelog 记录？"

---

## 9. 维护本文档

- 本文档由用户授权 AI 修改，但**修改前必须征求用户同意**。
- 修改后，必须在 `specs/patient-rehab-system/changelog.md` 追加一条 `AGENTS.md 更新` 类型的记录。
- 本文档应该保持简短（目标：300 行内）。展开内容请放到 `docs/superpowers/README.md` 或对应 spec。

---

_最后更新：2026-05-12（建立工具协作宪法）_
