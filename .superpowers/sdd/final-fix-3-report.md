# MotionCare 肩部推举视频最终修复 3 报告

基线：`c468ec8`

代码提交：

- `46e5a15 fix(video): 补齐七牛清理与运行环境防线`
- `bc45777 fix(miniapp): 修复录像启动与尾段保存竞态`

## 修复结果

1. 新增去患者化 `QiniuCleanupTombstone`，只保存视频会话 UUID、bucket、attempt key 前缀/最大序号、canonical key 与调度状态。记录不会因连续未发现对象自动删除；Beat 按 `next_check_at`、退避和 100 条批次持续 stat/delete。attached/处理中保留 canonical，解绑/过期不保留任何 key；`TrainingVideo` 删除后 tombstone 仍保留。
2. `VideoAssemblyJob.qiniu_object_key` 保持 approved canonical key，attempt key 使用独立字段。Worker 上传 attempt 后在 lease 复核通过时执行同 bucket、`force=false` 的 `BucketManager.move`，随后 stat 校验；612/目标已存在时回查 canonical。move 后 DB attach 前崩溃的重试直接复用匹配 canonical，不二次上传；stale worker不 move、不删除 canonical。
3. Recorder 的 `startRecord.success/fail` 同时校验 generation、`mode=recording` 与 `state=starting`。starting 窗口的 pause/finish 不会被迟到回调复活；页面 hide 在 start command 未 settle 时排队 pause。
4. timeout 尾段只有 `onSegment` 成功后才触发最大时长完成；失败 path 不进入 delivered，并可按原 path 重试。页面在 saveFile/getVideoInfo/manifest 失败后停止 force timer并阻断上传页，提供“重试保存尾段/重新训练”。测试覆盖 570000ms + 30001ms、saveFile 失败及下一 timer tick。
5. 新会话同时验证 FFmpeg、FFprobe 可执行与 staging root；Celery 使用异常可传播的 worker bootstep 验证两个二进制和共享 staging root 权限，不在 Django import/manage.py/migration 阶段执行。
6. 已复核 `docs/development.md` 的二进制、0700 staging root、同一 service user 与四进程共享目录说明，本轮未修改文档、spec、plan、changelog 或 `.superpowers/sdd/task-5-report.md`。

## 验证证据

- 后端聚焦：`pytest apps/training/tests/test_qiniu.py apps/training/tests/test_video_tasks.py apps/training/tests/test_video_worker_health.py apps/patient_app/tests/test_patient_app_video_api.py -q` -> `88 passed in 35.20s`。
- 后端全量：`pytest -q` -> `447 passed in 179.99s`。
- PostgreSQL 并发聚焦：`pytest apps/training/tests/test_video_segment_concurrency.py -q` -> `8 passed in 4.53s`。
- miniapp 聚焦：`npm run test -- src/pages/shoulder-press/pages.test.tsx src/pages/shoulder-press/recorder.test.ts` -> `35 passed`。
- miniapp 全量：`npm run test` -> `18 files passed, 219 tests passed`。
- Ruff：`ruff check .` -> `All checks passed!`。
- migration drift：`python manage.py makemigrations --check --dry-run` -> `No changes detected`。
- Django check：`python manage.py check` -> `System check identified no issues (0 silenced)`。
- 微信构建：`npm run build:weapp` -> `Compiled successfully in 14.19s`。
- H5 构建：`npm run build:h5` -> `exit 0`, `Compiled successfully in 34.79s`；存在既有 webpack `[hash]` deprecation 与 bundle size 两项警告。
- diff：`git diff --check` -> 无输出。
- frontend 未修改，按用户指令未重跑 frontend 测试/lint/build。

## 外部缺口与 concern

- 未连接真实七牛私有 bucket，未实测真实分片迟到提交、同 bucket move 的 612/614 响应、跨进程接管及长期 Beat 扫描；本轮通过 SDK 7.18.0 mock 合同测试覆盖。
- 未在 iOS/Android 微信真机连续录制 10 分钟，starting/stop 回调反序、hide、来电/锁屏、600 秒边界与本地文件配额仍需真机验收。
- 未以生产 Linux service user 实际启动 Web、两个 Celery worker 和 Beat；bootstep 异常传播、二进制检查及 staging 0700 权限已用自动测试覆盖。
- 未执行真实 PP-TinyPose 从七牛 canonical 对象下载、推理和肩推计数 E2E。
- H5 构建仍有既有 bundle size 与 webpack deprecation 警告，不阻断本轮修复。

结论：`DONE_WITH_CONCERNS`。代码与本地自动验证完成；concern 仅为上述真实外部环境/真机验收及既有构建警告。
