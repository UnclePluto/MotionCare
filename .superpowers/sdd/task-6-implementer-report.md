# Task 6 实施报告：通信测试、型号能力和远程命令

## 范围与结果

- 新增 `CapabilityProfile` 与安全关闭的 `MODEL_CAPABILITIES`；生产默认映射为空，测试仅用 monkeypatch 注入已验证型号能力。
- 新增安全状态查询、响铃、患者主动测量、受限配置和指定指标主动同步 API。
- 状态响应严格只包含设备 ID、型号、在线状态、电量、最近通信时间；不保存或返回位置数据。
- 远程命令只允许明确白名单中的非破坏性命令；未知型号、未知命令和停用设备均被拒绝。
- 命令日志记录安全参数摘要、厂商返回码和最终状态，过滤 AccessToken、Password、KEY 等敏感字段。
- 主动测量的排队结果在 10、20、30、40、50、60 秒进行最多六次轮询；只接受请求时间之后的真实点，支持成功、离线和超时，绝不伪造测量数据。
- 主动同步仅派发既有独立指标同步任务，指标固定白名单为心率、血压、血氧、步数。

## 验证（2026-07-24）

- `DATABASE_URL=sqlite:////tmp/motioncare-wearable-task6.sqlite3 .venv/bin/pytest apps/wearables/tests/test_commands.py apps/wearables/tests/test_provider_miwitracker.py -q`：53 passed。
- `DATABASE_URL=sqlite:////tmp/motioncare-wearable-task6.sqlite3 .venv/bin/pytest -q`：420 项测试，退出码 0。
- `DATABASE_URL=sqlite:////tmp/motioncare-wearable-task6.sqlite3 .venv/bin/ruff check apps/wearables`：通过。
- `DATABASE_URL=sqlite:////tmp/motioncare-wearable-task6.sqlite3 .venv/bin/python manage.py makemigrations --check --dry-run`：无迁移变更。
- `DATABASE_URL=sqlite:////tmp/motioncare-wearable-task6.sqlite3 .venv/bin/python manage.py check`：通过。
- `git diff --check`：通过。

## 顾虑

- 生产能力表故意保持为空；医院完成实机型号和命令参数验证后，必须单独评审并显式加入映射，不能依据厂商文档推测。

## 审查修复（2026-07-24）

- 增加 `WearableCommandLog.requested_at`、`poll_attempts`、`poll_deadline_at` 和 `next_poll_at`，以及迁移 `0003_wearablecommandlog_next_poll_at_and_more`。
- 空、空白或未知型号无法发送命令；即使能力表被误配空型号键也安全拒绝。
- 在实际调用厂商 `send_command()` 前紧邻地持久化 `requested_at`；轮询只接受严格晚于该时间的真实点。
- 轮询通过事务和 `select_for_update()` 原子认领到期计划点；持久化计数限制为请求后第 10/20/30/40/50/60 秒最多六次。重复、乱序、终态或过期投递不会再访问厂商。SQLite 测试验证认领条件；PostgreSQL 部署应补充并发 worker 的行锁等待集成测试。
- 配置接口按 setting 使用严格字段 schema；参数净化覆盖大小写、连字符/下划线变化和嵌套敏感键。

### TDD 证据

- 原实现 RED 证据已保留：首次创建 `test_commands.py` 后运行失败于 `ModuleNotFoundError: No module named 'apps.wearables.capabilities'`（`1 error in 0.07s`）。
- 本次修复 RED：`test_blank_or_unknown_model_cannot_send_even_if_mapping_is_misconfigured[None]` 失败，实际输出为 `Failed: DID NOT RAISE UnsupportedCapability`。
- 本次 GREEN：`pytest apps/wearables/tests/test_commands.py apps/wearables/tests/test_provider_miwitracker.py -q` 为 `77 passed in 4.06s`。
