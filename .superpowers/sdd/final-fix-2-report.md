# 肩部推举完整分支复审追加修复报告

> 日期：2026-07-11
> 基线：`3c23444`
> 代码提交：`6f2cae1`
> 范围：最终分支复审的 3 Important + 2 Minor
> 结论：本地代码、真实 FFmpeg 与自动化验证完成；真实七牛、PostgreSQL 双连接和微信真机仍属于外部验收缺口。

## 变更文件

- 七牛上传与任务状态机：`backend/apps/training/qiniu.py`、`video_tasks.py`、`video_models.py`、`backend/config/settings.py`
- migration：`backend/apps/training/migrations/0007_videoassemblyjob_qiniu_upload_deadline_at.py`
- FFmpeg 与 staging：`backend/apps/training/video_assembly.py`、`video_staging.py`
- 后端测试：`backend/apps/training/tests/test_qiniu.py`、`test_video_assembly.py`、`test_video_segment_concurrency.py`、`test_video_tasks.py`
- miniapp：`miniapp/src/pages/shoulder-press/index.tsx`、`recorder.ts`、`session.ts`、`pageState.ts` 及对应测试
- 部署说明：`docs/development.md`

## 逐项方案

### Important 1：七牛 generation fencing 与迟到清理

- 每次 assembly attempt 使用独立对象 key：`training-videos/attempts/<video-id>-<client-session-uuid>/attempt-<generation>.mp4`。旧 worker 只持有并删除自己的 key，不能覆盖或删除新 attempt 的合法对象。
- `VideoAssemblyJob.qiniu_upload_deadline_at` 持久化每次上传截止时间；上传前写入 attempt key 和 deadline 后才调用 SDK。attach 在持锁事务内同时校验 job 状态、`attempt_count` 和对象 key。
- 七牛 `put_file` 增加 `progress_handler`，每次进度回调刷新数据库 heartbeat；使用 monotonic 总 deadline，并显式设置 SDK 单请求 timeout/retry 上界。deadline 前、中、后均检查，超时抛出安全错误。
- SDK 不能提供跨请求硬取消，因此采用 durable tombstone：解绑行和 attached job 的 cleanup 状态保留到 `upload deadline + late completion grace`。清理先立即 quarantine 本地文件并扫描全部已开始 attempt key，窗口结束后再次扫描，确认迟到对象已删除才删除解绑数据库行或标记 cleanup succeeded。
- Beat 同时补偿解绑 cleanup 和 attached 旧 attempt cleanup；staging TTL 被配置校验为必须覆盖上传 deadline 与迟到补偿窗口。过期会话也删除全部可能的 attempt key。
- 回归覆盖：双 worker takeover 后旧 worker 只删 attempt 1、attempt 2 正常 attach；解绑第一次扫描后模拟旧上传迟到复活，第二次扫描删除；attached cleanup 只删旧 attempt 并保留当前对象；上传进度 heartbeat、deadline 和 SDK 请求上界。

### Important 2：FFmpeg 损坏检测与 copy 兼容合同

- 完整 null-sink decode 增加 `-xerror`；转码输入同样增加 `-xerror`，避免损坏输入被容错转码后静默接受。
- `VideoProbe` 增加 H.264 profile、level、pixel format、平均帧率、time base，以及 AAC sample rate、channel layout。
- 只有浏览器安全 H.264（Baseline/Main/High、level <= 4.2、`yuv420p`）且所有视频关键参数一致，音频全无或 AAC 的采样率/声道布局一致且安全时才尝试 copy。字段缺失、参数不安全或不一致时直接执行一次转码。
- 输出 probe 再按同一浏览器安全合同检查，并执行全文件 `-xerror` decode 后才原子发布。
- 真实集成测试生成 3 秒 H.264 MP4，破坏 `mdat` 中间数据；该文件仍可被 ffprobe 探测，但 assembly 现在非零失败。23 段真实 H.264/AAC 合并测试继续通过。

### Important 3：600 秒 recorder/页面竞态

- 服务端硬上限保持 `600000ms`，不修改或伪造 `getVideoInfo` 返回的真实媒体时长。
- miniapp 使用 `597000ms` 录制停止点，为真机 callback/媒体时长偏差留 3 秒安全余量。Recorder 根据剩余预算设置每个 `startRecord.timeout`：前 19 段 30 秒，第 20 段只申请 27 秒。
- 最终 generation 的 timeout callback 进入 finishing 状态并禁止自动续段；与页面 hard-stop timer 或 `finish()` 同时发生时，generation fencing 保证不会启动第 21 段或重复交付。
- 页面同时使用精确剩余时间 timer、1 秒 UI 轮询兜底和 recorder `onMaxDuration` 回调触发强制完成。
- manifest 仍使用 `getVideoInfo` 的真实 duration；若设备异常导致累计值仍超过 `600000ms`，拒绝写入并删除该孤立本地文件，绝不提交超限合同。
- 回归测试模拟 20 个 generation、第 20 段 timeout 与 finish 竞争，断言只启动 20 次、最终 timeout 为 27 秒、累计交付 `597000ms`；页面和 manifest 测试断言上传合同不超过 `600000ms`。

### Minor 1：orphan 双标识归属

- session/quarantine 目录正则同时解析 `video_id` 和 `session_id`。
- 只有数据库记录的 `id` 与 `client_session_id.hex` 同时匹配才视为有归属；existing video id 配 wrong UUID 的普通目录与 quarantine 在 TTL 后都会清理。
- 扫描容忍并发 quarantine 导致的 `FileNotFoundError`。

### Minor 2：staging root 0700

- staging root 现在要求当前服务账号持有且权限精确为 `0700`，`0755` 等可被其他用户枚举的目录会被拒绝。
- `docs/development.md` 改用 `install -d -m 0700 -o "$SERVICE_USER" -g "$SERVICE_GROUP"`，并说明 Django Web、默认 worker、video assembly worker 和 Beat 必须使用同一 OS 服务账号。

## TDD 证据

- 后端 RED：新增 FFmpeg probe 合同测试首次 collection 以 `VideoProbe.__init__() got an unexpected keyword argument 'video_profile'` 失败；其余目标测试为 `5 failed`，分别暴露共享 key、tombstone 提前删除、wrong UUID orphan、上传 deadline API 缺失和 `0755` root 未拒绝。
- miniapp RED：`3 failed, 37 passed`；失败分别为第 20 段没有剩余 timeout、页面没有 597 秒停止预算、manifest 接受 `600001ms`。
- 最小 GREEN：后端目标 `6 passed`；miniapp recorder/session/page `48 passed`。

## 最终命令与真实输出

- 后端聚焦：`DATABASE_URL=sqlite:////tmp/motioncare-fix2-final-focused.sqlite3 .venv/bin/pytest apps/training/tests/test_qiniu.py apps/training/tests/test_video_assembly.py apps/training/tests/test_video_tasks.py apps/training/tests/test_video_segment_concurrency.py apps/training/tests/test_video_session_models.py apps/patient_app/tests/test_patient_app_video_api.py apps/studies/tests/test_unbind_project_patient.py -q` -> `106 passed, 2 skipped in 8.08s`。
- 后端全量：`DATABASE_URL=sqlite:////tmp/motioncare-fix2-full.sqlite3 .venv/bin/pytest -q` -> `433 passed, 2 skipped in 37.30s`。
- Ruff：`ruff check .` -> `All checks passed!`。
- migration：`python manage.py makemigrations --check --dry-run` -> `No changes detected`。
- miniapp 肩推聚焦：6 个 shoulder-press 测试文件 -> `102 passed`。
- miniapp 全量：`npm run test` -> `213 passed`。
- miniapp 微信构建：`npm run build:weapp` -> `Compiled successfully in 1.79s`。
- miniapp H5 构建：`npm run build:h5` -> `compiled with 2 warnings in 3667 ms`；成功，警告为既有 asset/entrypoint size，另有 Webpack `[hash]` deprecation warning。
- `git diff --check` -> 无输出。

## 外部验收缺口

- 未连接真实 PostgreSQL；2 个双连接 `select_for_update` 测试仍按设计 skip，migration 的 PostgreSQL 锁等待和执行时间未现场验证。
- 未连接真实七牛私有 bucket；SDK 自动化覆盖 attempt key、进度、deadline、612、重复对象、解绑迟到补偿，但真实网络中断、分片重试与最终对象列表仍需现场验证。
- 未在 iOS/Android 微信真机连续录制 10 分钟；第 20 段 timeout/finish、后台切换、弱网、文件时长漂移和本地配额仍需真机验收。
- 未执行真实 PP-TinyPose 从最终七牛对象下载并完成推理的 E2E。
- staging `0700` 在本机临时目录自动化验证；生产 Linux 的 systemd/Celery service user、owner/mode 仍需部署现场检查。

## 禁止范围确认

未修改、未暂存、未提交 `.superpowers/sdd/task-5-report.md`、`docs/superpowers/README.md`、`docs/superpowers/specs/**`、`docs/superpowers/plans/**`、`specs/patient-rehab-system/changelog.md`。这些路径的既存脏改动保持原样。本轮唯一提交的既有 docs 文件为用户允许的 `docs/development.md`。
