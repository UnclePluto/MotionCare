# 病人康复系统 Spec 索引

本目录管理医院病人康复系统的**业务级**产品、数据、接口、CRF 与早期研发计划 spec。

> 与 `docs/superpowers/` 的关系：
>
> - 本目录（`specs/patient-rehab-system/`）：偏**产品 / 业务真相**（PRD、架构、CRF 字段映射、报价用功能清单等），相对稳定，版本号化管理。
> - `docs/superpowers/`：偏**单次特性的设计稿（spec）与实施计划（plan）**，按日期归档，工作流驱动。
>
> 跨工具协作约定见仓库根 `AGENTS.md`。

## 当前文档

| 文档 | 状态 | 用途 |
| --- | --- | --- |
| `prd.md` | 草稿 0.2（核心条款已锁定，详见 changelog 0.4） | 产品需求主文档，业务真相来源 |
| `open-questions.md` | 草稿 0.2 | 待讨论问题清单 + 已确认决策表（D001–D028） |
| `architecture/2026-05-07-web-admin-architecture-antd-pro-design.md` | ✅ 已确认（已落地） | Web 后台整体架构与边界（AntD Pro + Django Session） |
| `plans/2026-05-07-web-admin-antd-pro-django-session-plan.md` | 🗄️ 历史留档 | Web 后台 MVP 早期规划版本 |
| `feature-list-for-client-quote.md` | 草稿 | 对客户报价/对外说明用的功能清单 |
| `changelog.md` | 当前版本 **0.5** | spec 版本变更记录（追加式） |

## 当前未落地但已设计的子目录

- `visuals/`：视觉稿目录，目前空（无 `.md`）

## 与 superpowers 工作流的衔接

如果用户提出新需求 / 大型重构：

1. 先在本目录 `open-questions.md` 加一条问题或在 `prd.md` 拉一个章节。
2. 然后到 `docs/superpowers/specs/` 写 design spec（按日期命名）。
3. 然后到 `docs/superpowers/plans/` 写 implementation plan。
4. 实施完成后，在本目录 `changelog.md` 追加一行版本说明。

## 建议补充文档（尚未创建）

| 文档 | 用途 |
| --- | --- |
| `crf-field-map.md` | CRF 字段与系统字段映射表（部分内容现在散落在 `docs/superpowers/specs/2026-05-08-*` 中） |
| `data-model.md` | 核心数据模型 ER 描述 |
| `api-contract.md` | Web/小程序/设备/算法接口契约 |
| `game-design.md` | 游戏机制、字段、评分规则（后置） |

## 工作方式

- 每次需求讨论先更新 `open-questions.md`。
- 已确认结论同步写入 `prd.md` 或对应专题 spec。
- 研发拆分前，先冻结一个 PRD 版本（例如 0.2、1.0）。
- 研发过程中新增范围、延期范围、风险、决策统一记录到 `changelog.md`。
- **跨工具协作**：在本目录修改 spec 前先看仓库根 `AGENTS.md` §2。
