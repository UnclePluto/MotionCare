---
title: "访视评估录入与基线机能闭环（一期设计）"
date: "2026-05-08"
status: "draft-approved"
scope: "医院 Web 后台研究数据闭环版（第一期）"
---

## 背景

`specs/patient-rehab-system/prd.md` 第一版以“医院 Web 后台研究数据闭环版”为目标，CRF 是核心交付物。在前一份设计 `2026-05-08-crf-core-patient-fields-mapping-design.md` 中，我们已经把“病史/药史/人口学”这类**真正基线固化的信息**沉到 `PatientBaseline`。本设计聚焦下一段闭环：**机能与认知评估**（SPPB、TUG、握力、衰弱判定、MoCA 等）在 T0/T1/T2 反复采集的数据，应该如何放置、录入、校验、并为未来“基于处方完成情况自动评分”留好接口。

## 业务场景

1. 医生录入患者基础信息（姓名/性别/年龄、病史、药史等）→ `Patient + PatientBaseline`（已实现）。
2. 医生在医院进行一套评估（SPPB / TUG / 握力 / MoCA / 衰弱），结果写入 T0 访视。
3. 医生为患者开具处方（动作、频次、组数）。
4. 患者按处方周期训练，训练结果回传形成健康曲线。
5. 到访视周期，患者回院再次评估，写入 T1（之后 T2 同此流程）。

## 目标与非目标

### 目标（一期）

- 把 T0/T1/T2 的“评估录入 → CRF 缺失提示”闭环跑通。
- 评估字段在 `Visit.form_data` 内按命名空间区分：
  - `assessments`：医生人工值（CRF 默认取此）。
  - `computed_assessments`：系统计算/未来自动评分用，**一期不写入**。
- 替换前端 `VisitFormPage` 占位实现，提供最小可用的评估录入页，含“系统预填值”读取通道。

### 非目标（一期 NO）

- 不抽 `VisitAssessment` 子表（评估指标尚未冻结，过早结构化）。
- 不实现“基于处方完成情况自动评分”的算法服务，仅约定接口与数据契约。
- 不做电子签名 / 质控流转 / 数据锁定。
- 不做 baseline 版本化（沿用 PatientBaseline 一期“只保留最新值”策略）。

## 数据契约

### `Visit.form_data` schema（一期）

`Visit` 模型不变（`project_patient + visit_type(T0/T1/T2)` 唯一），仍是单 JSONField。约定结构：

```jsonc
{
  "assessments": {
    "sppb": {
      "balance": 4,
      "gait": 3,
      "chair_stand": 2,
      "total": 9,
      "note": ""
    },
    "moca": {
      "total": 22,
      "subscores": {},
      "note": ""
    },
    "tug_seconds": 12.4,
    "grip_strength_kg": 28,
    "frailty": "pre_frail"
  },

  "computed_assessments": {
    "sppb": {
      "total": 8.5,
      "balance": 3,
      "gait": 3,
      "chair_stand": 2,
      "source": "training_completion@v1",
      "computed_at": "2026-05-08T10:00:00+08:00"
    }
  }
}
```

### 约束

- `assessments` 与 `computed_assessments` 两个 key 必须存在；后端聚合层将 `None` 归一为 `{}`。
- 一期对 `assessments.*` 仅做最小类型校验（数字/字符串/枚举），不强制必填。
- `computed_assessments` 一期由后端 serializer 直接丢弃外部输入，避免被前端误填。
- `frailty` 枚举：`robust | pre_frail | frail`（与 docx 一致）。

### CRF 取值优先级

- 一期固定：CRF 预览/导出 **始终读取 `assessments.*`**。
- 二期可演进：增加 `use_computed: bool` 切换源；本期不实现，但契约允许。

## CRF 缺失提示扩展

沿用 `apps/crf/services/aggregate.py::build_crf_preview` 的 `missing_fields: list[str]` 机制。Label 风格与现有保持一致（中文、`{visit_type}.{label}`）。一期最小必填集（仅 SPPB 总分 + MoCA 总分，分别覆盖 T0/T1/T2）：

- `T0.SPPB总分` / `T0.MoCA总分`
- `T1.SPPB总分` / `T1.MoCA总分`
- `T2.SPPB总分` / `T2.MoCA总分`

判定规则：当 `form_data.assessments.sppb.total` 为 `None / "" / 缺 key` 时报告缺失（与 Task3 中 `education_years` 的判定一致，**不把 `0` 当缺失**）；MoCA 同理。

> 一期保持最小必填集，避免一次性把 docx 所有评估字段都纳入缺失校验。

## 接口与录入流程

### 后端

- 沿用 `VisitRecordViewSet`（`/api/visits/`），无新增 URL：
  - `GET /api/visits/?project_patient=<id>` 列出 T0/T1/T2 三条
  - `GET /api/visits/{id}/` 读单条
  - `PATCH /api/visits/{id}/` 写：
    - 归一化 `form_data`（缺 key 自动补 `{}`）
    - 丢弃外部传入的 `computed_assessments`
    - `assessments` 已知字段做最小类型校验，未知字段保留
    - partial 语义：未传字段不被清空
- `POST /api/visits/` 一期不开放（访视由 `ensure_default_visits` 在加入项目时自动建好）。
- 权限沿用 `IsAdminOrDoctor`。
- 状态变更走独立 PATCH（`{status: "completed"}`）。

### 评分预填接口（仅契约，不实现）

- 内部接口名：`apps/visits/services/compute_assessments.py::compute_for_visit(visit) -> dict`
- 调用方与时机：留待二期算分模块实现。一期前端不会主动触发该计算。
- 写入位置：`Visit.form_data.computed_assessments`，由后端内部接口写入；外部 PATCH 不允许修改。

### 前端录入流程（最小可用）

- 入口：`ProjectPatientsTab` 行操作里加 `T0 / T1 / T2` 跳转链接，点击进入 `/visits/:visitId`（避免本期改项目患者详情页结构）。
- 路由：新增 `/visits/:visitId` → `VisitFormPage`。
- 页面结构（一个 `Card` + 一个 `Form`）：
  1. 头部：访视类型标签（T0/T1/T2）、访视日期、状态显示
  2. 评估块（一期字段集）：
     - SPPB（balance / gait / chair_stand / total）
     - MoCA（total）
     - TUG（秒）
     - 握力（kg）
     - 衰弱判定（robust / pre_frail / frail）
  3. 底部：
     - **保存**（`PATCH form_data.assessments`，partial 写入；body 只包含改动键）
     - **标记已完成**（独立按钮，独立 `PATCH {status: "completed"}`）
- 预填行为：进入页面时若 `assessments.<field>` 为空且 `computed_assessments.<field>` 存在，输入框默认值取 `computed_assessments.<field>`，并显示“系统预填值”浅提示。医生编辑后保存即写入 `assessments`，`computed_assessments` 不变。

### 错误与权限

- 字段类型不合法返回 400，错误信息标识具体字段路径。
- 已完成访视仍允许授权医生编辑（PRD §6.6）。
- 一期不做并发乐观锁；前端通过“只发改动键”降低误覆盖风险。

## 测试策略

### 后端

- `apps/visits/tests/test_visit_form_data_contract.py`：
  - PATCH `assessments.sppb.total=9` 后回读匹配
  - PATCH 含 `computed_assessments` 时被丢弃
  - PATCH 不带 `assessments` 时已有 `assessments` 不被清空
  - 非法类型返回 400
- `apps/visits/tests/test_status_transition.py`：
  - 独立 PATCH `status=completed` 成功
  - 已完成态再 PATCH `form_data` 仍允许
- `apps/crf/tests/test_crf_aggregate.py` 扩展：
  - 评估缺失时 `missing_fields` 包含 `T0/T1/T2.SPPB总分` 与 `T0/T1/T2.MoCA总分`
  - 写入 SPPB/MoCA 总分后对应缺失项消失
  - `total = 0` 不视为缺失

### 前端

- `frontend/src/pages/visits/VisitFormPage.test.tsx`（新建）：
  - 渲染评估块默认值匹配 `assessments` 已存值
  - `assessments` 缺失而 `computed_assessments` 存在时输入框默认值取 computed 并显示预填提示
  - 修改 SPPB total 后保存，PATCH body 仅含 `form_data.assessments.sppb.total`
  - 点击“标记已完成”触发独立 PATCH `{status: "completed"}`
- `ProjectPatientsTab` 行操作出现 T0/T1/T2 链接并跳转 `/visits/:visitId`

## 一期验收点

- 项目患者行点 T0 → 进入访视页 → 录 `SPPB total = 9`、`MoCA total = 22` → 保存
- 回到 CRF 预览页该项目患者，`missing_fields` 中不再出现 `T0.SPPB总分 / T0.MoCA总分`
- 重复 T1：录入后 `T1.SPPB总分 / T1.MoCA总分` 缺失项消失
- 不传 `computed_assessments` 时数据库该字段为 `{}`；后续算分服务接入后，前端自动以 `computed_assessments` 作为预填值，无需改前端代码

## 影响面与回滚

| 模块 | 一期变更 |
|---|---|
| `apps/visits/serializers.py` | 新增 `form_data` 归一化与最小类型校验，丢弃外部 `computed_assessments` |
| `apps/visits/views.py` | 沿用 `ModelViewSet`，仅 PATCH 写入；保留 `IsAdminOrDoctor` |
| `apps/crf/services/aggregate.py` | `missing_fields` 增加 6 项（T0/T1/T2 的 SPPB/MoCA 总分） |
| `frontend/src/pages/visits/VisitFormPage.tsx` | 替换占位实现：评估块表单 + 保存 + 标记已完成 + 系统预填 |
| `frontend/src/app/App.tsx` | 注册 `/visits/:visitId` 路由 |
| `frontend/src/pages/projects/ProjectPatientsTab.tsx` | 行操作加 T0/T1/T2 跳转链接 |

回滚策略：所有变更均可由对应 commit 单独回退；无 DB schema 改动（仅 JSONField 内部约定）。

## 后续可演进方向（明确不在一期）

- 引入 `VisitAssessment` 子表，把 `assessments` 字段提升为列存储
- 实现 `compute_for_visit(visit)` 算分服务
- CRF 导出支持在 `assessments` 与 `computed_assessments` 之间切换源
- 评估指标必填集扩展（覆盖 docx 全部评估表格字段）
