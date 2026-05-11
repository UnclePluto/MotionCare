# 病人康复系统 Spec 索引

本目录用于管理医院病人康复系统的产品、数据、接口、游戏、CRF 和研发计划 spec。

## 当前文档

| 文档 | 状态 | 用途 |
| --- | --- | --- |
| `prd.md` | 草稿 0.2 | 产品需求主文档 |
| `open-questions.md` | 草稿 0.2 | 待讨论问题和决策记录 |
| `architecture/2026-05-07-web-admin-architecture-antd-pro-design.md` | 已确认 | Web 后台整体架构与边界 |
| `plans/2026-05-07-web-admin-antd-pro-django-session-plan.md` | 历史留档 | Web 后台 MVP 实施计划（早期规划版本） |
| `changelog.md` | 见文件内版本（当前含 **0.4**） | spec 版本变更记录 |

## 建议补充文档

| 文档 | 用途 |
| --- | --- |
| `crf-field-map.md` | CRF 字段与系统字段映射 |
| `data-model.md` | 核心数据模型 |
| `api-contract.md` | Web、小程序、设备和算法接口契约 |
| `game-design.md` | 游戏机制、字段和评分规则 |
| `plans/` | 研发阶段拆分与任务计划（可按日期/主题分文件） |
| `changelog.md` | spec 版本变更记录 |

## 工作方式

- 每次需求讨论先更新 `open-questions.md`。
- 已确认的结论同步写入 `prd.md` 或对应专题 spec。
- 研发拆分前，先冻结一个 PRD 版本，例如 0.2 或 1.0。
- 研发过程中新增范围、延期范围、风险和决策统一记录到 spec 中。
