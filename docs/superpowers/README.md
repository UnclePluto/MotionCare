# Superpowers 工作流索引

本目录用于管理 MotionCare 项目使用 superpowers 流程产出的设计稿（spec）与实施计划（plan）。

> **本目录的真相来源约定见仓库根 `AGENTS.md` §3、§4、§5。任何 AI agent 在本目录创建/修改文件前必须读 `AGENTS.md`。**

## 目录结构

```text
docs/superpowers/
├── README.md            ← 本文件（spec/plan 总索引）
├── brainstorm/          ← brainstorm 会话产物（草稿、问题、决策草案）
├── specs/               ← 设计稿（design spec），定义"做什么"
└── plans/               ← 实施计划（implementation plan），定义"怎么做"
```

## 设计稿（specs/）当前清单

| 文件 | 主题 | 状态 |
| --- | --- | --- |
| `specs/2026-05-08-crf-core-patient-fields-mapping-design.md` | CRF 核心患者字段映射（一期） | draft-approved |
| `specs/2026-05-08-visit-assessments-and-baseline-flow-design.md` | 访视评估录入 + 基线机能闭环 | draft-approved |
| `specs/2026-05-08-frontend-fullscreen-and-create-actions-design.md` | 前端满屏 + 新增动作（患者档案/项目） | draft-approved |
| `specs/2026-05-11-patient-project-admin-and-grouping-board-design.md` | 患者档案 + 研究项目 + 分组看板 | approved（drop-batch 后已对齐主线） |
| `specs/2026-05-11-patient-list-actions-privacy-design.md` | 患者列表操作与隐私展示 | approved |
| `specs/2026-05-12-frontend-only-randomization-confirmed-binding-design.md` | 前端临时随机 + 确认时建绑定 | approved |
| `specs/2026-05-14-project-patient-research-entry-tabs-design.md` | 项目患者维度研究录入 + T0/T1/T2 Tab + 基线资料命名 | approved |

## 实施计划（plans/）当前清单

| 文件 | 主题 | 状态 | 关联 spec |
| --- | --- | --- | --- |
| `plans/2026-05-08-crf-patient-baseline-mapping-phase1.md` | CRF 基线 + mapping 一期 | implementing | `specs/2026-05-08-crf-core-patient-fields-mapping-design.md` |
| `plans/2026-05-08-frontend-fullscreen-and-create-actions.md` | 前端满屏 + 新增动作 | implementing | `specs/2026-05-08-frontend-fullscreen-and-create-actions-design.md` |
| `plans/2026-05-11-drop-batch-concept.md` | **删除批次概念**，重构随机/确认/池语义 | ✅ **implemented** (`fa686e5`) | 来自 `2026-05-11-patient-project-admin-and-grouping-board-design.md` |
| `plans/2026-05-11-post-drop-batch-consolidation-execution-plan.md` | drop-batch 后文档/测试收口 | ✅ **implemented** (`241fc51`) | 同上 + `drop-batch-concept.md` |
| `plans/2026-05-11-patient-project-admin-and-grouping-board.md` | 患者/项目/分组看板（早期版） | 🗄️ **superseded** by `drop-batch-concept.md` | （历史留档） |
| `plans/2026-05-11-patient-list-actions-privacy.md` | 患者列表操作 + 隐私 | implementing | `specs/2026-05-11-patient-list-actions-privacy-design.md` |
| `plans/2026-05-12-frontend-only-randomization-confirmed-binding.md` | 前端临时随机 + 确认入组绑定 | implementing | `specs/2026-05-12-frontend-only-randomization-confirmed-binding-design.md` |
| `plans/2026-05-14-project-patient-research-entry-tabs.md` | 项目患者维度研究录入 + T0/T1/T2 Tab + 基线资料命名 | approved | `specs/2026-05-14-project-patient-research-entry-tabs-design.md` |

## 状态语义

| 状态 | 含义 | 是否允许改实现来"反悔" |
| --- | --- | --- |
| `draft` | 起草中 | — |
| `review` | 等用户审查 | — |
| `approved` | 已批准，等开工 | ❌ 不能反悔，要改请走 changelog |
| `implementing` | 在写代码 / 部分落地 | ❌ 不能反悔 |
| `implemented` | 全部落地，已合并 main | ❌❌ 严禁回滚（除非新决策替代） |
| `superseded` | 已被新计划替代 | 历史留档，不删除 |

## 工作流入口（superpowers skills）

| 我要做的事 | 该用的 skill |
| --- | --- |
| 创意 / 需求探索 | `superpowers:brainstorming` |
| 写实施计划 | `superpowers:writing-plans` |
| 执行已有计划 | `superpowers:executing-plans` 或 `superpowers:subagent-driven-development`（**二选一**，不混用） |
| 调试 bug | `superpowers:systematic-debugging` |
| TDD 写功能 | `superpowers:test-driven-development` |
| 完成前验证 | `superpowers:verification-before-completion` |
| 走 PR / 合并 | `superpowers:finishing-a-development-branch` |

## 命名约定

- spec：`docs/superpowers/specs/YYYY-MM-DD-<kebab-topic>-design.md`
- plan：`docs/superpowers/plans/YYYY-MM-DD-<kebab-topic>.md`
- 同一主题的 spec 与 plan 使用**相同的日期前缀和主题**（除非 plan 是 consolidation / supersede 性质，需要另开日期）

## 重要：跨工具使用约定

本项目同时被 Cursor 与 Codex 使用。**在本目录改任何文件前，请先看仓库根 `AGENTS.md` §2（工具协作协议）**。

特别是：

1. 永远**不要删除** `specs/` 或 `plans/` 下的任何文件，即使标记为 `superseded`。
2. 修改已存在的 spec/plan 时，在文件头追加一行说明：

   ```text
   修订（YYYY-MM-DD, <cursor|codex>）：<改了什么 / 为什么>
   ```

3. plan 中的 `- [ ]` 改为 `- [x]` 时，同时在文件顶部"执行记录"区写明 commit short-sha 和工具名。

_最后更新：2026-05-12_
