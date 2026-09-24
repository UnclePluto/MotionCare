# 单组连续录像与整文件直传实施计划

> 状态：implemented（本地实现已验证；真实云端/真机待验收）
> 日期：2026-09-24
> 实施基线：`d233c41` + 本次会话未提交的摄像头恢复修复。
> 执行方式：用户于 2026-09-24 回复“继续”批准，本会话逐项实施，已完成独立审查。
> 执行技能：`superpowers:executing-plans`。
> 工作目录：`/Users/nick/.codex/worktrees/counted-single-video-direct-upload/MotionCare`；分支 `codex/counted-single-video-direct-upload`，保留未提交改动。

**目标：** 四个计数组动作每组连续录像最多五分钟，结束即休息，在休息期间把一个完整视频直传七牛，取消新组切片与合并。

**架构：** 新增独立的整文件授权和核验接口，复用训练视频、组、计次和分析实体。小程序新队列以单文件记录，旧队列保留旧协议。录像结束意图、文件就绪和上传确认是三个不同状态。

**技术栈：** Django/DRF、现有七牛 Python SDK、httpx、Taro/React/TypeScript、pytest、Vitest。

**设计：** `docs/superpowers/specs/2026-09-24-counted-single-video-direct-upload-design.md`（用户已批准）。

## 全局约束

- 录制上限 300 秒，休息 180 秒；上限不在界面展示，不再五秒轮转录像。
- 新组一个原始文件，七牛直传；新链路不调用分片上传或创建合并任务，不适用旧的 80 MB 分片限制。
- 只有后端独立核验并绑定成功才标记已上传；分析不阻塞休息、后续组或完成计次。
- 持久化失败可在当前进程继续尝试上传临时路径，但不得声称可跨重启恢复。
- 保留旧分片补传、行走、认知游戏和现有处方/健康时间口径。
- 保留本会话已实施的原生调用等待上限、重复停止防护及迟到回调隔离。
- 不主动提交、推送、上传小程序或执行生产迁移。模型迁移文件与业务代码一起留待用户提交。
- 当前未提交改动均来自本次会话，不能按外来改动删除。实施前保留完整补丁快照；不覆盖已有文档或清理旧计划。

## 审查重点

1. SDK 在 300 秒内部自动停止与业务超时同时发生：只允许一次原生停止，UI 只进入一次休息。归 Task 3。
2. 整文件已到云端但客户端丢失响应：复验同一对象即可完成，不能要求重做或重复计次。归 Task 2、4。
3. 凭证签发后患者解绑，文件晚到：禁止绑定，且凭证失效后仍能清理该对象。归 Task 2。
4. 本地持久化失败：仍用可用临时文件上传；不能因为旧空间阈值提前阻断，也不能清理尚未确认的唯一副本。归 Task 4。
5. 旧分片队列与新整文件队列混合：各走自己的协议，互不清理、不串组。归 Task 4、5。

## Task 1：直传数据契约与单对象授权

**文件：**

- 修改 `backend/apps/training/video_models.py`、`set_models.py`、`sets.py`。
- 修改 `backend/apps/patient_app/set_views.py`、`urls.py`。
- 新建 `backend/apps/training/direct_video.py`、`backend/apps/patient_app/direct_video_views.py`。
- 新建 `backend/apps/patient_app/tests/test_direct_video_api.py`。
- 修改 `backend/config/settings.py`、`deploy/docker-compose.prod.yml`、`deploy/env.production.example`。
- 生成 `backend/apps/training/migrations/0023_counted_direct_upload.py`，依赖现有 `0022_motion_training_sets`；若期间出现新迁移，顺延而不覆盖。

**接口：**

- `POST /api/patient-app/training-video-direct-uploads/`：`client_session_id`、`motion_attempt_id`、`size_bytes`、`duration_ms`；归属和实际起止从已恢复的组读取。
- 返回 `video_id`、`status`；未完成时附 `upload_url`、`upload_token`、`object_key`、`expires_at`。已绑定时不再签发凭证。
- `TrainingVideo.upload_mode`：`segments`（历史默认）或 `direct`；`direct_upload_expires_at` 可空。复用 `size_bytes`、实际时长等元数据字段固定一次授权的文件快照。
- `MotionTrainingSet.completion_reason`：`manual`（历史默认）或 `time_limit`；完成及恢复接口读取、保存、回传此值，重复声明必须一致。
- 直传上传域名由 `QINIU_DIRECT_UPLOAD_URL` 明确配置，无生产默认域名猜测；`QINIU_DIRECT_UPLOAD_TOKEN_TTL_SECONDS` 默认 3600，正整数。

- [x] 编写公共接口失败测试：使用现有 `counted_client()` 创建归属明确且已完成的组，授权 100 MB 文件应成功；他人组、未完成组、已放弃尝试、改变已授权文件大小或时长应失败。

```python
response = client.post("/api/patient-app/training-video-direct-uploads/", {
    "client_session_id": str(uuid.uuid4()),
    "motion_attempt_id": attempt_id,
    "size_bytes": 100 * 1024 * 1024,
    "duration_ms": 120000,
}, format="json")
assert response.status_code == 201
video = TrainingVideo.objects.get(pk=response.data["video_id"])
assert video.upload_mode == "direct"
assert not VideoAssemblyJob.objects.filter(training_video=video).exists()
```

- [x] 运行 `cd backend && .venv/bin/pytest apps/patient_app/tests/test_direct_video_api.py -q`，确认新接口尚不存在导致失败。
- [x] 在用户项目关系锁内校验有效组尝试，按患者与客户端编号幂等创建视频；同一组已有正式视频返回已有记录。新授权只接受 1–300000 毫秒的声明时长，与组起止差允许 5 秒容差。
- [x] 对象键采用服务器生成的 `training-videos/direct/<video-id>-<client-session-id>.mp4`；凭证限定该空间与键，启用 `insertOnly` 和视频类型检测。

```python
policy = {
    "insertOnly": 1,
    "detectMime": 1,
    "mimeLimit": "video/mp4;video/quicktime",
    "fsizeMin": video.size_bytes,
    "fsizeLimit": video.size_bytes,
}
token = Auth(settings.QINIU_ACCESS_KEY, settings.QINIU_SECRET_KEY).upload_token(
    video.bucket, video.object_key,
    settings.QINIU_DIRECT_UPLOAD_TOKEN_TTL_SECONDS,
    policy=policy,
)
```

`fsizeLimit` 固定为本次声明文件大小，用于约束单对象凭证，不设置 80 MB 业务阈值。URL 必须为配置的 HTTPS 上传域名，拒绝带凭据、查询参数或片段。

- [x] 生成迁移并运行相关接口测试；运行 `makemigrations --check --dry-run`，预期无遗漏模型改动。凭证策略解码测试只使用测试密钥，不输出真实凭证。

## Task 2：云端核验、幂等绑定与清理

**文件：**

- 扩展 Task 1 的 `direct_video.py`、`direct_video_views.py` 与接口测试。
- 修改 `backend/apps/training/qiniu.py`、`video_tasks.py`、`tasks.py` 和必要的清理测试。
- 新建 `backend/apps/training/tests/test_direct_video_storage.py`。

**接口：**

- `POST /api/patient-app/training-video-direct-uploads/<video_id>/complete/`：允许空 JSON；只处理服务器预分配的对象，不接受客户端对象键或 URL。
- 返回 `video_id`、`status`；对象尚未到达时保持待上传，不创建训练记录。
- `read_private_video_info(object_key) -> dict`：对服务器配置的私有下载域名构造 `?avinfo` 签名 URL，返回媒体元信息。
- `verify_direct_video(project_patient, video_id) -> TrainingVideo`：远端读取在短数据库事务之外，绑定前重新加锁检查身份、尝试与不可变元数据。

- [x] 先增加失败测试，覆盖对象不存在、错误类型/大小、无视频流、非有限时长、时长超过 305 秒、声明时长相差超过 5 秒；均不得创建记录、触发分析或报告已上传。

```python
first = client.post(f"/api/patient-app/training-video-direct-uploads/{video.id}/complete/", {}, format="json")
second = client.post(f"/api/patient-app/training-video-direct-uploads/{video.id}/complete/", {}, format="json")
assert first.data["status"] == second.data["status"] == "attached"
assert TrainingRecord.objects.filter(video=video).count() == 1
assert not VideoAssemblyJob.objects.filter(training_video=video).exists()
```

- [x] 运行上述两组测试并看到新核验功能失败后，实现七牛 `stat` 和 `avinfo` 核验。使用现有 `httpx`，连接/读取分别设置 5/15 秒期限，禁止重定向，响应体最多 1 MB；错误摘要不包含签名 URL 或密钥。
- [x] 核对真实视频时长、流类型及文件大小，要求七牛返回合法 ETag。保存真实媒体信息，排除封装等待时间；媒体不兼容时报告失败，不偷偷恢复转码/拼接流程。
- [x] 将原 `attach_training_video()` 的记录创建、视频绑定、`attach_set_video()` 和 `ensure_motion_analysis_job()` 提取为共享绑定步骤；旧合并入口继续保留原租约检查。新直传入口在项目关系、视频和组锁内调用，不制造合并任务来复用代码。
- [x] 凭证签发时持久化截止时间；过期或解绑清理复用已有七牛清理墓碑，安排最终删除在最后一次凭证到期后并留 300 秒余量。新直传清理跳过本地分片目录依赖；阻止已进入清理的对象续签和绑定。
- [x] 新增“解绑与核验并发”“最后一次授权后晚到对象”“云端成功但客户端没收到响应”的回归。期限内不把墓碑永久归档，保证最终检查覆盖晚到写入。
- [x] 运行 `pytest apps/patient_app/tests/test_direct_video_api.py apps/training/tests/test_direct_video_storage.py apps/training/tests/test_video_tasks.py apps/patient_app/tests/test_motion_sets_api.py -q`，预期全部通过，旧视频发布与计次无回归。

## Task 3：单次录像与立即休息

**文件：**

- 修改 `miniapp/src/features/motion-training/countedRecorder.ts`、`countedRecorder.test.ts`、`CountedCamera.tsx`、`recordingTrace.ts`、`recordingTrace.test.ts`。
- 修改 `miniapp/src/pages/shoulder-press/pages.test.tsx`。

**接口：**

- `CountedTrainingRecorder` 每实例只拥有一次启动、一份录像结果。
- `finish(reason: 'manual' | 'time_limit')` 幂等地请求结束。
- `onEnding(endedAtMs, reason)` 在结束意图时触发一次，用于启动休息；`onVideo(path, durationMs)` 在有效文件返回时交付一次。
- 保留 `onFatalError`、等待较慢提示和 `discard()`；删除自动续录、片段累计与五秒定时器。

- [x] 先把原五秒分段测试替换为一组一次录像的失败测试，保留原无回调、重复完成、重做与迟到回调隔离测试。

```typescript
await recorder.start()
await vi.advanceTimersByTimeAsync(299000)
expect(camera.startRecord).toHaveBeenCalledTimes(1)
expect(camera.stopRecord).not.toHaveBeenCalled()
const result = recorder.finish('manual')
expect(onEnding).toHaveBeenCalledTimes(1)
expect(camera.stopRecord).toHaveBeenCalledTimes(1)
stopOptions.success({ tempVideoPath: 'whole.mp4' })
await result
expect(onVideo).toHaveBeenCalledTimes(1)
```

- [x] `cd miniapp && npm test -- src/features/motion-training/countedRecorder.test.ts`，确认现有五秒循环使测试失败。
- [x] 设置微信原生录制上限 300 秒。手动在期限前结束时只调用一次 `stopRecord`；到限由 SDK 自动停止，业务 300 秒定时器只标记结束、进入休息并监视结果，不再额外调用原生停止。手动结束若恰好到限，同样加入在途结果。
- [x] SDK 自动回调早于正常上限且没有手动结束意图时按异常中断处理，不能因为回调携带视频就自动确认完成。SDK 回调、业务定时器和手动按钮的各种先后顺序都必须只交付一次。
- [x] 页面增加独立的结束/休息状态：结束意图立即停止组计时并进入休息；文件交付后再安全登记已做完并启动上传。等待文件期间不能开始下一组；网络上传慢且文件可用时可在休息结束后继续。
- [x] 去掉三十分钟定时放弃、临近上限文案和保存“最后一段”的文案；演示模式也在五分钟自然进入休息，但不创建真实文件或上传。
- [x] 增加页面测试：点击后未收到录像即显示休息，五分钟静默进入休息，最后一组展示完成/待上传，失败不虚报，缺失回调达到最终期限可重做，休息音频不再次占用正在录制的麦克风。音频开始与文件就绪协调，文字休息计时即时开始。
- [x] 运行录像器、诊断和页面测试，预期全过。用本机真实 SDK JavaScript 定时器加模拟原生回调回放五分钟边界，确认业务与 SDK 不重复停止；此测试不代替真机。

## Task 4：整文件队列、持久化与小程序直传

**文件：**

- 新建 `miniapp/src/features/motion-training/directUpload.ts`、`directUpload.test.ts`、`countedFiles.ts`、`countedFiles.test.ts`。
- 修改 `countedSession.ts`、`countedUpload.test.ts`、`CountedCamera.tsx`、`pages/shoulder-press/pages.test.tsx`。
- 将原分片上传分支移入 `countedLegacyUpload.ts`，仅由旧记录调用。

**接口：**

```typescript
type CountedVideoFile = {
  path: string
  durationMs: number
  sizeBytes: number
  persistence: 'saved' | 'temporary'
}
type DirectAttemptData = {
  uploadMode: 'direct'
  video?: CountedVideoFile
  completionReason: 'manual' | 'time_limit'
}
```

- 老记录缺少 `uploadMode` 时保持 `segments` 旧行为；新组只写一个 `video` 字段，不向片段数组塞一个元素冒充新设计。
- `prepareCountedFile(tempPath, durationMs) -> Promise<CountedVideoFile>`：先尝试一次持久化，再从最终可用路径读取元数据；失败保留可用临时文件，不与上传并发移动路径。
- `uploadDirectVideo({file, grant, onProgress})`：通过 `Taro.uploadFile` 向已验证 HTTPS 授权 URL 发送一个表单文件、`key` 与短期 `token`，不发送患者 API 的 Authorization 头。
- `syncCountedQueue()`：恢复组 → 查询/核验已有云端对象 → 获取凭证 → 完整文件上传 → 后端核验 → 持久化已上传标志 → 清理本地文件。

- [x] 先增加失败测试：新队列不调用分片接口，100 MB 文件不被旧阈值拒绝；保存失败仍上传临时路径，服务器未确认不能删除文件；账号变化中止后续状态写入。

```typescript
expect(uploadVideoSegment).not.toHaveBeenCalled()
expect(nativeUpload.mock.calls[0][0]).toMatchObject({
  url: 'https://upload.example.test',
  name: 'file',
  filePath: 'whole.mp4',
  formData: { key: 'server-key.mp4', token: 'test-scoped-token' }
})
expect(countedSessions(1)[0].attempts[0].uploaded).not.toBe(true)
expect(removeFile).not.toHaveBeenCalled()
```

- [x] 运行 `npm test -- src/features/motion-training/directUpload.test.ts src/features/motion-training/countedFiles.test.ts src/features/motion-training/countedUpload.test.ts`，看到未实现直传分支导致失败。
- [x] 实现上传响应校验，只接受对象键与预分配一致的成功响应；凭证过期重新向业务后端授权，同组同文件幂等重试。每次重试先核验云端，覆盖上传成功但响应丢失情形。
- [x] 继续按患者隔离且单并发上传多组队列，保留真实字节进度、速度、指数退避和手动重试；上传百分之百仍需后端确认。
- [x] 替换固定“保存文件超过 35 MB”门槛；不把已保存文件列表推算成真实设备剩余空间。保留针对未传文件的保护和实际写入失败提示。不得假定五分钟视频一定低于设备额度。
- [x] 完成标志先写入本地队列再清理文件；清理失败保留可再次清理路径，不能因删除失败再次上传或丢失追踪。临时文件与持久化文件使用正确删除方式。
- [x] 补齐重启恢复、保存成功但读元数据失败、临时文件失效、三组并存、云端已成功但本地文件丢失、旧分片混合、账号切换及旧方补传测试。
- [x] 运行 Task 3、4 所有测试与 `npm run typecheck`，预期通过。

## Task 5：规格收口、整体验证与上线检查

**文件：**

- 修改正式规格 `specs/patient-rehab-system/motion-set-prescription-prd.md` 及原计数组设计中的被替代段落。
- 仅追加 `specs/patient-rehab-system/changelog.md`。
- 更新本计划完成标记及新设计状态；保留所有历史文档。

- [x] 记录新旧协议切换和字段默认值，明确五分钟属于技术结束来源而非患者主动计数确认；取消新组提前上限提示和三十分钟失败规则。
- [x] 本地运行后端全量测试；本机七牛空间环境值与旧测试固定值存在差异时，使用测试期配置 `QINIU_BUCKET=motioncare-training`，不得改生产配置以迎合测试。

```bash
cd backend && QINIU_BUCKET=motioncare-training .venv/bin/pytest
cd miniapp && npm test && npm run typecheck && npm run build:weapp:dev
cd frontend && npm run test && npm run lint && npm run build
git diff --check
```

- [x] 独立审查所有本次变更，重点检查权限、五分钟双停止、云端核验与并发绑定、未上传文件清理、旧队列兼容。发现问题先补失败测试再修复。
- [ ] 上线顺序：部署后端新增接口及迁移 → 配置对应存储区的七牛 HTTPS 上传域名及微信合法域名 → 在测试环境核验真实整文件直传与私有媒体信息 → 发布小程序。新模式可用前不能让小程序发送新协议。
- [ ] 真机验收：iPhone 13 连续三组；短组手动完成、接近五分钟手动完成、到五分钟自动结束；慢回调、弱网重试、后台/重启补传、存储接近满。记录设备/微信/基础库版本、文件大小、每组开始停止次数、云端确认时间和异常次数。
- [x] 实施完成报告区分自动化通过、测试环境真实云端验证和真机验收；未执行的项目如实列明，不称故障率已降低，不自动发布。

## 资料与已核对事实

- 本机微信基础库实现将原生单次录制期限截断为 300 秒，到期内部调用停止方法。
- 七牛 [上传策略](https://developer-doc.qiniu.com/products/kodo/development-guidelines/security/1-put-policy) 支持单对象范围、禁止覆盖、文件大小与类型约束；凭证不等于账号密钥。
- 七牛 [音视频元信息](https://developer.qiniu.com/dora/api/audio-and-video-metadata-information-avinfo) 可读取真实媒体信息；私有访问需签名，该能力上线前须用本项目存储与域名验证。
- 本计划不执行云端写入、生产迁移、代码提交或发布；这些动作仍按用户届时的明确授权执行。

## 实施验证记录（2026-09-24）

- 后端最终全量 1600 通过（251.94 秒）；额外补充未完成组授权与跨患者完成登记边界后，新接口 25 项测试全部通过。
- 小程序本地清理修复后全量 1201 测试通过，TypeScript 检查与微信构建通过。
- 管理端 340 测试通过，lint 无错误（既有 5 条警告），构建通过。
- 微信基础库 3.16.0 与 3.17.0 实际 JavaScript 的十个定时器回放通过：手动、五分钟自动、同时手动、迟到文件、永久缺回调；均仅一次原生启动/停止。原生回调为模拟，不等同于真机。
- 独立审查发现的临时文件存储保护问题已经补失败测试并修复；另补末组等待文件时不显示上一轮休息的回归。
- 已修复本地清理边界：云端确认上传后，删除接口明确报告文件不存在时视为清理完成并移除队列路径；其它删除错误保留重试。
- 实施决定：隔离工作区保留原目录；遵守不自动提交的约定。因此后续仍需整合工作区并提交，未自动部署、迁移生产数据库或发布小程序。
- 本次未运行真实七牛写入/avinfo 连通性测试，未做 iPhone 13 验收；上述两个复选项有意保留未完成。
