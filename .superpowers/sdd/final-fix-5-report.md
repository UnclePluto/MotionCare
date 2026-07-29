# Final Fix 5 Report

基线：`ab172a8`

范围：仅修复 `0009` 在真实解绑组合下的七牛 canonical key 数据迁移边界；未修改 `0009`、控制器文档或其它模块。

## 根因

`0009_repair_qiniu_canonical_keys` 在 `TrainingVideo.project_patient_id` 与关联
`Prescription.project_patient_id` 均为 `NULL` 时，仍拼接 canonical key，生成了
`training-videos/None/...`。此外，它以 `status == attached` 无条件保留 canonical，
覆盖了 `cleanup_requested_at` 已存在时必须删除的语义。

## 修复

- 新增后续数据迁移 `0010_repair_unbound_qiniu_canonical_keys`，不修改已提交 `0009`。
- 仅在视频或处方仍有可安全确认的 `project_patient_id` 时推导 canonical key。
- 无法安全推导时，不再生成 `training-videos/None/...`；保留 attempt key 与最大尝试次数，
将 job/tombstone canonical 清空，以便 tombstone 继续枚举 attempt 对象清理。
- 有真实 `TrainingVideo.object_key` 或非 attempt 的 job key 时，使用该实际 key 同步
job/tombstone；不伪造 canonical。
- `cleanup_requested_at` 非空优先：即使视频状态为 `attached`，tombstone 也设为
`retain_canonical=False`。
- 未请求清理的 attached 历史对象保留真实 `TrainingVideo.object_key`。
- 迁移仅在值变化时写入 tombstone；重复执行不改变 job/tombstone 状态。反向迁移为 noop。

## RED / GREEN

RED：在迁移目标仍为 `0009` 时，真实解绑的 failed 视频断言失败：
`qiniu_object_key` 为 `training-videos/None/...`，而预期为空。

GREEN：迁移测试覆盖以下场景并通过：

- 视频和处方均解绑、只有 attempt key。
- attached 且 `cleanup_requested_at` 非空，保留实际对象 key 供删除且不保留 canonical。
- 无法安全推导归属但存在实际 job key，tombstone 使用该 key 清理。
- 未 attached 且不可推导的对象不保留/生成 `training-videos/None/...`。
- 直接重复调用 `0010` 迁移后 job/tombstone（含 tombstone `updated_at`）不变。

## 验证

- `cd backend && pytest apps/training/tests/test_video_qiniu_cleanup_migration.py apps/studies/tests/test_unbind_project_patient.py -q`：3 passed。
- `cd backend && pytest`：451 项收集，命令成功退出。
- `cd backend && ruff check .`：All checks passed。
- `cd backend && python manage.py makemigrations --check --dry-run`：No changes detected。
- `cd backend && python manage.py check`：System check identified no issues (0 silenced)。
- `git diff --check`：通过，无输出。

代码提交：`f6eeeef fix(training): 修复解绑视频迁移边界`
