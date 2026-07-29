# 肩部推举分段视频 final review 统一修复报告

> 日期：2026-07-11
> 基线：`94660d5`
> 代码提交：`7956048`、`e30f3fe`
> 结论：代码与本地自动化完成；外部验收仍有缺口，状态为 `DONE_WITH_CONCERNS`。

## 变更文件

- 后端生命周期与任务：`backend/apps/training/video_models.py`、`video_tasks.py`、`tasks.py`、`qiniu.py`、`backend/apps/studies/services/unbind_project_patient.py`、`backend/config/settings.py`
- 后端合并与 staging：`backend/apps/training/video_assembly.py`、`video_staging.py`、`video_services.py`
- migration：`backend/apps/training/migrations/0006_trainingvideo_cleanup_attempt_count_and_more.py`
- 后端测试：`backend/apps/training/tests/test_qiniu.py`、`test_video_assembly.py`、`test_video_segment_concurrency.py`、`test_video_session_models.py`、`test_video_tasks.py`、`backend/apps/studies/tests/test_unbind_project_patient.py`
- miniapp：`miniapp/src/api/client.ts`、`safeError.ts`、`miniapp/src/pages/shoulder-press/api.ts`、`index.tsx`、`session.ts`、`upload.tsx`、`workflow.ts` 及对应 `api.test.ts`、`pages.test.tsx`、`workflow.test.ts`
- frontend：`frontend/src/pages/training-tracking/TrainingTrackingDetailPage.tsx`、`TrainingTrackingDetailPage.test.tsx`
- 本报告：`.superpowers/sdd/final-fix-report.md`

## 审查项处理

1. **解绑 durable cleanup**：`TrainingVideo.project_patient` 改为 nullable `SET_NULL`；解绑事务内写入 durable cleanup 状态，`on_commit` 调度 Celery。任务删除七牛对象、本地 quarantine 和数据库记录，失败指数重试，Beat 补偿；七牛 612 视为幂等成功。旧 assembly 正在运行时等待或使 stale 租约失效；覆盖 uploading、attached、失败补偿及严格目录名 orphan TTL。
2. **deadline、心跳与租约**：`assemble_video` 使用单一 monotonic deadline，所有 probe/copy/transcode/decode timeout 均取剩余时间，并在每段探测和阶段边界回调心跳。`attempt_count` 作为 claim generation；旧 worker 无法 heartbeat、mark uploading、attach 或在 takeover 后继续下一次文件写入。配置强制 stale timeout 大于 assembly timeout。
3. **FFmpeg 兼容性与完整验证**：只有全 H.264、同尺寸、音频全无或全 AAC 才尝试 copy；其余直接一次 `libx264`/AAC 转码。copy 任一执行/探测/时长/编码/完整解码失败只回退一次转码。临时输出通过 ffmpeg null sink 完整解码后才原子替换最终文件。
4. **600 秒合同**：miniapp 在 session 创建、旧 manifest 归一化和 API 最终出口统一钳制 `1..600`，12 分钟处方发送 600，并以同值驱动完成门槛。后端边界测试覆盖 600 接受、601 拒绝。
5. **staging 安全**：拒绝 staging root、session 和中间目录 symlink；根目录必须当前服务账号拥有且禁止组/其他用户写。锁文件、上传 `.part`、concat 和临时输出使用 `O_NOFOLLOW` 与 `0600`，目录为 `0700`。清理先在 staging 内原子 rename 至 `.quarantine`，再用 dirfd 递归删除；重试与 orphan 扫描均处理 quarantine，严格匹配 `<video-id>-<32hex>`。
6. **三项 Minor**：复用既有七牛对象也统一校验 MIME；重新训练先 best-effort 删除 manifest 全部分段，失败路径写入本地 orphan 诊断后再清 manifest；miniapp、frontend 和服务端摘要过滤新增 `access_key`、`accessKey`、`secret_key`、`credential_id`、`AK`、`SK`。

## Migration

- `0006_trainingvideo_cleanup_attempt_count_and_more.py`
- 新增 `cleanup_status`、`cleanup_requested_at`、`cleanup_heartbeat_at`、`cleanup_attempt_count`、`cleanup_error`。
- `TrainingVideo.project_patient` 从 `CASCADE` 改为 nullable `SET_NULL`。
- `python manage.py makemigrations --check --dry-run`：`No changes detected`。

## 命令与真实结果

- 默认 PostgreSQL 基线聚焦 pytest：`23 passed, 12 errors`；12 个错误均为本机 `localhost:5432` connection refused，未进入测试逻辑。
- SQLite 基线后端聚焦：`35 passed`。
- miniapp 基线聚焦：`39 passed`；frontend 基线聚焦：`15 passed`。
- 后端 RED：`20 failed, 35 passed, 2 skipped`，失败对应新增 cleanup/lease/deadline/codec/staging/MIME 行为。
- miniapp RED：敏感字段、重训清理和 600 秒路径按预期失败；修复后聚焦 `84 passed`。
- `DATABASE_URL=sqlite:////tmp/motioncare-final-fix-focused.sqlite3 pytest apps/patient_app/tests/test_patient_app_video_api.py apps/training/tests/test_video_tasks.py apps/training/tests/test_video_assembly.py apps/training/tests/test_video_segment_concurrency.py apps/training/tests/test_qiniu.py apps/studies/tests/test_unbind_project_patient.py -q`：`91 passed, 2 skipped`；包含真实 FFmpeg 23 段 H.264/AAC 合并。
- 后端最终：`DATABASE_URL=sqlite:////tmp/motioncare-final-fix-full.sqlite3 pytest`：`420 passed, 2 skipped in 37.79s`；skip 为 PostgreSQL-only 双连接锁测试。
- 后端最终：`ruff check .`：`All checks passed!`。
- 后端最终：`python manage.py makemigrations --check --dry-run`：`No changes detected`。
- miniapp 最终：`npm run test`：`211 passed`；`npm run build:weapp`：成功；`npm run build:h5`：成功，保留既有 bundle size warning。
- frontend 最终：`npm run test`：`137 passed`；`npm run lint`：0 error、4 个既有 fast-refresh warning；`npm run build`：成功，保留既有 chunk size warning。
- `git diff --check`：无输出。

## 外部未验证项

- 未启动真实 PostgreSQL；两个 `select_for_update` 双连接测试仍 skip，migration 在 PostgreSQL 的锁等待与执行时间未验证。
- 未执行真实七牛私有 bucket E2E；612、put/stat MIME、上传中解绑删除、重复 key 和私有下载均为 mock SDK 自动化。
- 未执行 iOS/Android 微信真机连续 10 分钟、弱网、切后台、配额和 320px 布局验收。
- 未执行真实 PP-TinyPose 从七牛下载最终视频并完成推理的 E2E。
- staging 权限与 quarantine 在 macOS 临时目录验证；生产 Linux 的 root/service-account 部署权限仍需现场检查。

## 禁止范围确认

未修改、未暂存、未提交 `.superpowers/sdd/task-5-report.md`、`docs/superpowers/README.md`、`docs/superpowers/specs/**`、`docs/superpowers/plans/**`、`specs/patient-rehab-system/changelog.md`。这些路径的既存脏改动保持原样。
