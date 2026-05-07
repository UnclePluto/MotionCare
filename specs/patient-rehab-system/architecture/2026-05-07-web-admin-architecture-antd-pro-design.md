# Web 管理端整体架构（Ant Design Pro + Django Session）设计稿

> 状态：已确认（用于进入实现计划）
> 日期：2026-05-07
> 范围：第一版「医院 Web 后台研究数据闭环版」（见 `specs/patient-rehab-system/prd.md`）

## 1. 背景与目标

第一版目标是让医院医生在 Web 后台完成研究数据闭环：患者档案、项目与分组、随机分组批次、T0/T1/T2 访视、版本化处方、训练记录代录入、健康日数据、CRF 预览与 DOCX/PDF 导出。

本设计稿聚焦“整体架构与边界”，要求：

- **前端 UI** 采用 **Ant Design Pro**（布局、菜单、路由、表格/表单模式）
- **鉴权** 采用 **Django Session + Cookie**（并配合 CSRF）
- 存在一个**静态资源服务器**用于处方相关视频与游戏资源图片，且**第一版先公开访问**

## 2. 非目标（第一版不做/后置）

- 患者小程序端
- 真实设备 OpenAPI 自动同步、设备 TCP 直连
- 视频上传、真实游戏交互、AI 动作识别评分
- 电子签名、复杂质控流转
- 统计显著性分析与自动研究结论
- 静态资源鉴权（签名 URL/临时凭证）与防盗链（后续阶段再做）

## 3. 总体拓扑与边界（推荐方案）

### 3.1 组件划分

- **Web 管理端（Ant Design Pro）**
  - 职责：路由/布局（Sider+Header+Content）、页面渲染（表格/表单/详情）、前端可见性权限（菜单/按钮显示与禁用）、调用 API、错误提示与空态
  - 产物：纯静态站点（HTML/CSS/JS），可托管在静态站点/CDN/对象存储

- **API 后端（Django）**
  - 职责：Session 登录态、CSRF、接口级授权、数据行级过滤、核心业务与数据聚合（CRF 预览/导出）、导出日志
  - 约束：**任何“能不能看/能不能改”的最终裁决必须在后端**

- **统一入口（反向代理/网关，关键）**
  - 对外暴露 `admin` 域名（例如 `https://admin.xxx.com`）
  - 提供同站点路径代理：`/api/*` → 转发到 Django
  - 目标：让浏览器视角下的 API 仍是同站点请求，从而让 **Session + Cookie + CSRF** 简化为标准形态

- **静态资源域名（assets，独立且公开）**
  - 用于处方相关视频/图片等，第一版公开直链访问
  - 后端保存 URL（或 key+拼接规则），前端直接引用

### 3.2 为什么推荐“同站点 /api 反代”

在前端静态站点与后端 API 分离的同时，通过网关把 API 代理成 `admin` 同站点路径：

- 避免跨站点 Cookie 的 SameSite 复杂配置与浏览器差异
- 降低 CSRF/CORS 调试成本
- 满足“工程解耦 + Session 省心”的双目标

## 4. 鉴权与权限（后端强制 + 前端可见性）

### 4.1 登录态（Session + CSRF）

- 登录：前端调用 `POST /api/auth/login`（或 Django 自带登录），成功后后端 `Set-Cookie: sessionid=...`
- CSRF（Django 标准模式）：
  - 前端先 `GET /api/auth/csrf` 获取 `csrftoken`
  - 之后所有**写操作**带 `X-CSRFToken: <token>`

### 4.2 权限模型（建议）

- 角色：`super_admin` / `admin` / `doctor`
- 权限点（permission codes）：按“资源.动作”命名，示例：
  - `patient.read` / `patient.write`
  - `project.read` / `project.write`
  - `randomization.confirm`
  - `visit.write`
  - `prescription.terminate`
  - `crf.export`

> 说明：第一版可先用“角色 → 权限点集合”的简单映射；后续再演进为更细粒度策略（如项目范围、科室范围等）。

### 4.3 前端路由/菜单对齐（AntD Pro 常规做法）

- 前端维护**完整路由表**（包含 `access` / permission code）
- 启动时调用 `GET /api/me` 获取：
  - 用户信息（姓名/角色）
  - 权限点列表（或 role + permissions）
- 前端据此过滤菜单/路由/按钮，并提供 401/403 统一处理
- 后端仍必须在每个接口做最终拦截（前端隐藏不等于安全）

## 5. 领域模型与 API 边界（与 PRD 对齐）

### 5.1 核心对象与关系（摘要）

- `Patient`：全局基础档案
- `Project`：研究项目（绑定 CRF 模板版本、访视计划）
- `Group`：项目分组（配置比例）
- `ProjectPatient`：患者加入项目后的承载关系（项目内分组、访视、处方、训练、CRF 均挂在此维度）
- `RandomizationBatch`：分组批次（支持后续新患者继续入组）
- `Visit`：T0/T1/T2（draft/done）
- `Prescription`：版本化处方（同一时刻唯一生效）
- `TrainingRecord`：训练记录（仅允许基于当前生效处方录入）
- `DailyHealth`：健康日数据（患者维度按日唯一）
- `CrfExport`：CRF 导出记录（含缺失字段清单）

### 5.2 REST 资源接口（建议路径）

- 患者：
  - `GET/POST /api/patients`
  - `GET/PATCH /api/patients/{id}`
  - `GET/PATCH /api/patients/{id}/daily-health?date=YYYY-MM-DD`
- 项目：
  - `GET/POST /api/projects`
  - `GET/PATCH /api/projects/{id}`
  - `GET/POST /api/projects/{id}/groups`
  - `GET /api/projects/{id}/project-patients`
- 项目患者维度：
  - `GET /api/project-patients/{id}`
  - `GET/POST /api/project-patients/{id}/visits`
  - `GET/POST /api/project-patients/{id}/prescriptions`
  - `GET/POST /api/project-patients/{id}/training-records`

### 5.3 流程型动作接口（匹配“批次/锁定”语义）

- 创建分组批次并入组：`POST /api/projects/{id}/randomization-batches`（body：`patientIds`）
- 生成草案：`POST /api/randomization-batches/{id}/generate`（也可创建时自动生成）
- 调整草案：`PATCH /api/randomization-batches/{id}/assignments`
- 确认锁定：`POST /api/randomization-batches/{id}/confirm`

### 5.4 CRF 聚合接口

- 预览：`GET /api/project-patients/{id}/crf/preview?templateVersion=...&visit=T1`
- 导出：`POST /api/project-patients/{id}/crf/exports`（body：`format=docx|pdf` 等）
- 导出记录：`GET /api/project-patients/{id}/crf/exports`

## 6. 错误处理与一致性约定

- 统一错误结构：`{ code, message, details? }`
- 鉴权/授权：
  - 401：未登录（前端跳登录/提示）
  - 403：无权限（前端 403 页/提示）
- 参数/字段校验：400 返回字段级错误，便于 ProForm/ProTable 直接展示
- 业务冲突：409（例如批次已 confirm 仍尝试调整 assignments）

## 7. 风险与后续演进

- **跨站点资源**：第一版公开直链可行，但后续若涉及患者隐私/版权，需引入签名 URL 或临时凭证
- **权限范围（PRD Q005）**：医生范围（仅自己 vs 同项目共享）会影响后端数据行级过滤策略，建议尽早确认
- **CRF 模板一致性（PRD Q001/Q002）**：若导出需要严格对齐 Word 模板，后续实现需优先验证 DOCX 渲染方案与版式控制能力

