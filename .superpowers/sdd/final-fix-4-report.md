# MotionCare 第三轮闭环复审 Important 修复报告

> 日期：2026-07-11
> 基线：`565dcf4`
> 代码提交：`5184392`
> 范围：仅修复 canonical move 租约竞态与 0008 数据迁移语义。

## 修复结果

1. canonical 发布改为在同一数据库事务内按 `ProjectPatient（若仍存在） -> TrainingVideo -> VideoAssemblyJob` 锁序重新校验 status、generation、attempt key 与 canonical key；事务只覆盖短时七牛 canonical stat/move/stat 和 `qiniu_object_hash`、heartbeat 发布状态写入，不覆盖 FFmpeg、本地合并或大文件 attempt upload。
2. canonical 已存在且 hash/size 匹配时跳过 attempt upload，仍进入上述事务重新校验租约并记录发布状态。模拟 move 已成功但 DB 写失败后，下一次执行可识别 canonical、跳过重复上传并完成发布状态记录。
3. 新增 `0009_repair_qiniu_canonical_keys`，不修改已提交 0008。未 attached 且旧 job key 为 attempt key 时保留 attempt 字段并重建 approved canonical；attached 历史对象保留 `TrainingVideo.object_key`；`project_patient=NULL` 时仅从该视频自己的 prescription 关系稳定回溯，不关联其它患者。tombstone canonical 与 retain/delete 语义同步。

## 测试证据

- RED：`pytest apps/training/tests/test_video_publish_concurrency.py apps/training/tests/test_qiniu_cleanup_migration.py -q` -> `3 failed`，失败原因为事务发布入口和 0009 尚不存在。
- 新增回归：PostgreSQL 两连接 fake move 阻塞期间，stale recovery 与 unbind 均不能接管；释放后 generation/解绑状态一致。DB 发布状态写失败后重试识别 canonical 并继续。
- 聚焦：`pytest apps/training/tests/test_qiniu.py apps/training/tests/test_video_tasks.py apps/training/tests/test_video_publish_concurrency.py apps/training/tests/test_video_qiniu_cleanup_migration.py apps/training/tests/test_video_session_migration.py apps/studies/tests/test_unbind_project_patient.py apps/patient_app/tests/test_patient_app_video_api.py -q` -> `93 passed`。
- 全量首次：`pytest` -> `450 passed, 1 failed`；新 MigrationExecutor 文件排序导致后续既有 transaction 测试在 flush 后缺 seed 数据。仅调整新测试文件名后重跑。
- 全量最终：`pytest` -> `451 passed`。
- Ruff：`ruff check .` -> `All checks passed!`。
- Migration：`python manage.py makemigrations --check --dry-run` -> `No changes detected`。
- Django：`python manage.py check` -> `System check identified no issues (0 silenced)`。
- Diff：`git diff --check` -> 无输出，退出码 0。
- 按要求未修改 miniapp/frontend，因此未重跑其测试与构建。

## External Gaps

- 未连接真实七牛私有 bucket；move 的 200/612/614、真实网络超时和远端最终一致性由 mock 覆盖，仍需部署环境联调。
- 并发接管使用真实 PostgreSQL 行锁和两个数据库连接，但 move 使用可控阻塞 fake；未执行真实七牛请求阻塞期间的解绑/恢复演练。
- DB 失败使用 `DatabaseError` 注入验证事务回滚与重试；未进行数据库进程宕机或 Celery worker 强杀演练。
