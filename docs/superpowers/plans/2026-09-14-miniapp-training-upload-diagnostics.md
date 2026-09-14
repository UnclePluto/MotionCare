# 小程序训练录像诊断日志实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox syntax for tracking.
> 状态：implemented
> 日期：2026-09-14
> 关联：../specs/2026-09-14-miniapp-training-upload-diagnostics-design.md
> 实施基线：c58d7aa
> 执行记录（2026-09-14, codex）：用户已批准方案，独立工作区开发；按用户偏好不主动提交。Task 1 已实现且通过需求、代码质量审查；完整后端 1266 项通过，审查后定向 34 项通过，迁移无漂移，Ruff 通过。

**Goal:** 录像上传失败可由业务服务器查询，离线日志恢复后补报，十五天自动清理。
**Architecture:** 客户端独立有界队列和低层错误采集；服务端患者认证诊断接口、独立数据库表和 Celery 清理。依照设计契约按事件 ID 去重。
**Tech Stack:** Taro / TypeScript / Vitest、Django / DRF / Celery / pytest。

## Task 1：服务端接收、查询和清理

Files: `backend/apps/patient_app/diagnostic_views.py`、`urls.py`；`backend/apps/training/diagnostic_models.py`、`upload_diagnostics.py`、`models.py`、`tasks.py`、`migrations/0016_traininguploaddiagnostic.py`；`backend/config/settings.py`；`backend/apps/training/management/commands/training_upload_diagnostics.py`；`backend/apps/patient_app/tests/test_training_upload_diagnostics.py`。

- [x] 编写 API 集成测试，构造设计中的事件负载，验证成功、重复、未登录、其他患者 video_id、无 video_id、恶意摘要、超长和未知字段；调用 `client.post('/api/patient-app/training-upload-diagnostics/', payload, format='json')`。
- [x] 运行新增测试确认缺少路由时失败。
- [x] 新增 `TrainingUploadDiagnostic` 模型，联合唯一键 `(project_patient, event_id)`，`received_at` 索引；只保存允许字段。
- [x] 实现现有 Bearer 认证的 API，字段白名单和归属校验，在事务中 `get_or_create`；仅返回已接收事件 UUID。
- [x] 实现 `cleanup_training_upload_diagnostics` Celery 任务和每小时调度，删除 `received_at__lte=now-timedelta(days=15)`；实现同截止条件的查询命令。
- [x] 生成 migration；运行 `pytest apps/patient_app/tests/test_training_upload_diagnostics.py` 和迁移无漂移检查。

## Task 2：客户端持久化、补报与采集

Files: `miniapp/src/features/motion-training/diagnostics.ts`、`diagnostics.acceptance.test.ts`、`api.ts`、`api.test.ts`、`miniapp/src/app.ts`、`miniapp/src/auth/token.ts`；录像 `camera.tsx`、`upload.tsx` 及关联测试。

- [x] 先写队列失败重启补报和 15 天到期测试；运行 `npm test -- diagnostics.acceptance.test.ts` 确认失败。
- [x] 导出非抛出型 `reportTrainingDiagnostic(stage, error, context)`，本地同步保存再异步补报；100 条上限；错误对象按白名单提取 code、errMsg、HTTP 状态，双重脱敏，拒绝凭证、路径和响应体。
- [x] 实现专用请求 `/patient-app/training-upload-diagnostics/`，不使用带登录跳转的普通 request；只有匹配 event_id 的 200 才删除日志。网络/5xx/429 退避保留，永久非法事件丢弃，认证失败暂停。
- [x] app 前台启动补报，后台停止计时器，网络恢复触发单通道补报；当前登录作用域隔离队列，演示模式不留记录。
- [x] 在会话创建/状态/分片/完成请求失败处保留底层错误，在相机与文件处理错误处接入诊断；用户提示维持现状，不阻塞上传或改变重试语义。
- [x] 验证并发、ACK 丢失、重复事件、存储异常、退出登录、演示隔离、分片和完成请求失败的端到端调用。

## Task 3：集成与验证

- [x] 分别进行需求符合性和代码质量审查，修复所有确认的问题。
- [x] `cd backend && pytest`、`python manage.py makemigrations --check --dry-run`、新增迁移检查。
- [x] `cd frontend && npm run test && npm run lint && npm run build`。
- [x] `cd miniapp && npm test && npm run build:weapp:prod`，检查类型、包体积和构建结果。
- [x] 更新此计划执行记录，报告代码与验证结果，明确尚未部署或上传微信的部分；不自动提交或发布。

## 最终验证记录（2026-09-14，Codex）

- Task 2 和整体需求、代码质量审查通过；已修复异步失败跨账号归属、首次登录网络恢复监听两项审查发现。
- 后端全量 1266 项通过；后续新增隐私校验测试后定向 34 项通过。迁移无漂移，相关 Python 文件 Ruff 通过。
- 管理端 317 项测试通过；lint 零错误、5 项已有 Fast Refresh 警告；生产构建通过（已有大分块提示）。
- 小程序最终 58 个文件、1006 项测试通过；生产微信构建通过；主包 499.22 KiB、总包 1510.70 KiB，包体检查通过。
- 小程序额外 `tsc --noEmit` 仍有 202 项既有错误；与隔离的实施基线源码比较，错误内容完全一致，无新增。生产构建工具在沙箱内遇到本机系统配置异常，改在正常本机权限下验证成功。
- 凭证存储向后兼容封装为凭证与随机诊断作用域的原子值，队列仅保存随机作用域，不复制凭证。异步采集绑定操作开始时的作用域。当前无实际压缩调用，保留诊断阶段及历史状态兼容。
- 差异格式检查通过；临时测试数据库已清理。改动仅在独立工作区，未提交、未部署、未上传微信；需发布服务端迁移、服务与新版小程序后才开始收集实际故障。
