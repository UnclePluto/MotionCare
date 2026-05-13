# 病人康复系统 Spec Changelog

## 0.6 - 2026-05-14

- 明确「研究录入」改为项目患者维度：一行代表一个患者在一个项目中的入组关系，同一患者多项目按项目拆分。
- 新增项目患者研究录入页设计：顶部 T0/T1/T2 Tab，显示时间说明；草稿可编辑，已完成只读查看。
- 覆盖旧访视编辑口径：完成态访视不再允许继续编辑，草稿态承担可编辑流程。
- 将「CRF 基线」用户可见文案改为「基线资料」，页面标题为「患者基础基线资料」；该资料仍为患者维度一人一份，不包含 T0 评估。
- 明确患者详情去掉「打开 CRF」入口，CRF 入口保留在项目相关语境。

## 0.5 - 2026-05-12

- 建立项目根 **`AGENTS.md`** 作为 AI 协作宪法，覆盖 Cursor / Codex / Claude Code / Gemini CLI 等所有 AI 编程工具的共享指令。
- 创建 `CLAUDE.md`、`GEMINI.md` 软链接到 `AGENTS.md`，确保不同工具读到同一份"项目宪法"。
- 新增 `docs/superpowers/README.md`，作为 superpowers 工作流 spec / plan 的总索引，并明确每份 spec/plan 的状态（draft/approved/implementing/implemented/superseded）。
- 修订 `specs/patient-rehab-system/README.md`：把 `feature-list-for-client-quote.md` 加入索引；明确本目录与 `docs/superpowers/` 的职责边界；标注 `visuals/` 当前为空；补充工作流衔接说明。
- 给已落地的 plan（`drop-batch-concept.md` / `post-drop-batch-consolidation-execution-plan.md`）和被替代的 plan（`patient-project-admin-and-grouping-board.md`）补充顶部状态徽章（implemented / superseded），便于任何工具一眼识别"不能回退"。
- 明确**工具切换协议**：会话切换前必须 WIP commit；进入工具时必须先 `git status` + `git log` 理解上下文；不在用户确认前覆盖另一个工具留下的改动。

## 0.4 - 2026-05-11

- 明确"患者-项目绑定关系"仅在"分组内被确认"时才形成；删除一切"加入项目"的中间语义。
- "患者池"明确为虚拟概念：表达"所有患者"，不建模为实体；项目分组看板左侧的"池"是计算视图。
- **彻底删除批次概念**（`GroupingBatch` 模型/字段/API/前端状态全部删除）。
- 重新随机时，未确认（pending）的 ProjectPatient 会与池里勾选的患者一起再次随机；已确认者保持不变。
- 已确认患者只能"从本项目移除"（解绑），解绑后回到池；在组内列表中**置灰**展示（不隐藏）。
- 患者详情"加入研究项目"快捷入口改为"直接确认入组到分组"：必须指定 `group_id`，提交即为 confirmed。

## 0.3 - 2026-05-09

- 架构设计稿补充「本地 Vite + Django」场景下的 **CSRF 信任源（`CSRF_TRUSTED_ORIGINS` / `DJANGO_CSRF_TRUSTED_ORIGINS`）** 说明，与 `backend/config/settings.py` 实现保持一致，避免本地开发反复出现 `Origin checking failed`。

## 0.2 - 2026-05-06

- 明确第一版为医院 Web 后台研究数据闭环版。
- 明确小程序、真实设备、真实游戏、视频上传、AI 动作识别后置。
- 明确患者是全局基础档案。
- 明确项目、分组、患者解耦。
- 明确随机分组确认前可调整，确认后锁定。
- 明确处方版本化、动作快照、当前生效处方训练录入规则。
- 明确健康日数据手动录入。
- 明确 CRF 可带缺失导出。
