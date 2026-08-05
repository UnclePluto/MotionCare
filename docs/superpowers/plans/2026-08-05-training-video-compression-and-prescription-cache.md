> 状态：approved
> 日期：2026-08-05
> 范围：实施 720P 分段压缩、50MB 单段限制、40 分钟录像上限和处方缓存即时展示。
> 关联：`docs/superpowers/specs/2026-08-05-training-video-compression-and-prescription-cache-design.md`
> 实施基线 commit：de1fc9d

# 训练视频压缩与处方缓存实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让肩部推举真机录像以低档位录制并压缩到最高 720P 后可靠分段上传，同时把最长录像放宽到 40 分钟，并让处方列表利用首页缓存即时展示。

**Architecture:** 小程序新增独立的录像压缩模块和可恢复的待压缩分段状态，摄像页与强制上传页共同复用；后端只保留单段、分段数和时长边界，删除累计字节上限。处方使用进程内共享缓存，首页写入、处方页缓存优先并后台刷新，token 生命周期负责清理缓存。

**Tech Stack:** Taro 4.2、React 18、Vitest、Django 5、DRF、pytest、PostgreSQL、Celery、FFmpeg、Docker Compose、微信开发者工具 CLI。

## Global Constraints

- 微信相机默认 `resolution="low"`。
- 压缩结果最高为竖屏 `720×1280` 或横屏 `1280×720`，约 2Mbps、24fps。
- 单段上限固定为 `52428800` 字节，最长时长固定为 `2400` 秒，最多 `80` 段。
- 删除独立的完整视频总大小限制；不得用新的隐式累计阈值替代。
- 压缩失败必须保留原始持久化文件并允许重试，不得上传未压缩文件。
- 旧版待上传清单必须继续兼容读取。
- 处方缓存仅存在于当前小程序进程，token 设置、清除和失效时必须清空。
- 不升级依赖、基础镜像、数据库、Redis、FFmpeg、Nginx 或操作系统。
- 所有业务代码改动先写失败测试并观察红灯，再做最小实现。
- 所有提交信息和 Git 操作说明使用中文。

---

### Task 1: 修改后端视频边界与长视频任务配置

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/apps/training/video_services.py`
- Modify: `backend/apps/training/tasks.py`
- Modify: `backend/apps/patient_app/tests/test_patient_app_video_api.py`
- Modify: `backend/apps/training/tests/test_motion_analysis.py`
- Modify: `backend/apps/training/tests/test_video_segment_concurrency.py`
- Modify: `backend/tests/test_settings.py`
- Modify: `deploy/docker-compose.prod.yml`
- Modify: `deploy/env.production.example`

**Interfaces:**
- Produces: `TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES=52428800`
- Produces: `TRAINING_VIDEO_MAX_DURATION_SECONDS=2400`
- Produces: `TRAINING_VIDEO_MAX_SEGMENTS=80`
- Produces: `MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS=900`
- Produces: `MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS=7200`
- Removes: `settings.TRAINING_VIDEO_MAX_SIZE_BYTES`

- [ ] **Step 1: 写后端边界失败测试**

在 `backend/tests/test_settings.py` 增加默认配置断言：

```python
def test_training_video_limits_support_compressed_forty_minute_sessions():
    assert settings.TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES == 50 * 1024 * 1024
    assert settings.TRAINING_VIDEO_MAX_DURATION_SECONDS == 2400
    assert settings.TRAINING_VIDEO_MAX_SEGMENTS == 80
    assert settings.MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS == 900
    assert settings.MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS == 7200
    assert not hasattr(settings, "TRAINING_VIDEO_MAX_SIZE_BYTES")
```

把 `test_upload_segment_total_size_limit_leaves_rejected_segment_no_residue` 改为
`test_upload_segment_allows_total_size_above_legacy_limit`：连续上传两个各 6 字节的分段，
断言均为 `201` 且数据库有两段，不再设置 `TRAINING_VIDEO_MAX_SIZE_BYTES`。

在 finalize 测试附近新增累计大小超过旧阈值仍成功的用例，用小尺寸 fixture 模拟
`200MB + 1` 的数据库累计值，断言 `finalize` 不因总字节数失败。

在 `backend/apps/training/tests/test_motion_analysis.py` 中删除
`TRAINING_VIDEO_MAX_SIZE_BYTES=900` override，并断言 `fake_download` 收到：

```python
assert max_bytes == job.training_video.size_bytes
```

- [ ] **Step 2: 运行后端定向测试并确认红灯**

Run:

```bash
cd backend
pytest tests/test_settings.py \
  apps/patient_app/tests/test_patient_app_video_api.py \
  apps/training/tests/test_motion_analysis.py -q
```

Expected: 默认值仍为 32MB/600 秒/120 段、总大小测试仍被拒绝、动作分析仍读取旧总大小配置。

- [ ] **Step 3: 实施服务端最小改动**

在 `backend/config/settings.py`：

```python
TRAINING_VIDEO_MAX_DURATION_SECONDS = int(
    os.getenv("TRAINING_VIDEO_MAX_DURATION_SECONDS", "2400")
)
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES = int(
    os.getenv("TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES", str(50 * 1024 * 1024))
)
TRAINING_VIDEO_MAX_SEGMENTS = int(os.getenv("TRAINING_VIDEO_MAX_SEGMENTS", "80"))
MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS = int(
    os.getenv("MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS", "900")
)
MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS = int(
    os.getenv("MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS", "7200")
)
```

彻底删除 `TRAINING_VIDEO_MAX_SIZE_BYTES`。在 `video_services.py` 删除上传阶段的
`total_size_bytes` 聚合和 finalize 阶段的完整视频总大小判断；保留分段数量、单段大小和
总时长判断。

在 `tasks.py` 改为：

```python
max_bytes=job.training_video.size_bytes
```

从并发测试的 `override_settings` 删除旧总大小字段。同步更新 Compose 环境映射与生产环境
示例，新增两个动作分析超时映射。

- [ ] **Step 4: 运行后端定向测试并确认绿灯**

Run:

```bash
cd backend
pytest tests/test_settings.py \
  apps/patient_app/tests/test_patient_app_video_api.py \
  apps/training/tests/test_motion_analysis.py \
  apps/training/tests/test_video_segment_concurrency.py -q
```

Expected: 全部通过。

- [ ] **Step 5: 提交后端边界改动**

```bash
git add backend/config/settings.py backend/apps/training/video_services.py \
  backend/apps/training/tasks.py backend/apps/patient_app/tests/test_patient_app_video_api.py \
  backend/apps/training/tests/test_motion_analysis.py \
  backend/apps/training/tests/test_video_segment_concurrency.py \
  backend/tests/test_settings.py deploy/docker-compose.prod.yml deploy/env.production.example
git commit -m "feat(training): 放宽压缩录像时长与分段边界"
```

---

### Task 2: 建立可恢复的 720P 分段压缩模型

**Files:**
- Create: `miniapp/src/pages/shoulder-press/compression.ts`
- Create: `miniapp/src/pages/shoulder-press/compression.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/session.ts`
- Modify: `miniapp/src/pages/shoulder-press/session.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/workflow.ts`
- Modify: `miniapp/src/pages/shoulder-press/workflow.test.ts`

**Interfaces:**
- Produces: `MAX_SHOULDER_PRESS_SEGMENT_SIZE_BYTES`
- Produces: `shoulderPressCompressionScale(width, height): number`
- Produces: `compressSavedShoulderPressSegment(input, dependencies)`
- Produces: `appendPendingCompressionSegment(...)`
- Produces: `completePendingSegmentCompression(...)`
- Produces: `markPendingSegmentCompressionFailed(...)`
- Produces: `isCompressedShoulderPressSegment(...)`

- [ ] **Step 1: 写压缩参数与会话恢复失败测试**

`compression.test.ts` 使用字面量断言：

```typescript
expect(shoulderPressCompressionScale(1080, 1920)).toBeCloseTo(2 / 3)
expect(shoulderPressCompressionScale(1920, 1080)).toBeCloseTo(2 / 3)
expect(shoulderPressCompressionScale(640, 480)).toBe(1)
```

模拟依赖并断言 `compressVideo` 收到原始持久化路径、`bitrate: 2000`、`fps: 24` 和计算后的
`resolution`；压缩结果等于 50MB 时成功，超过 50MB 时抛出包含实际体积的中文错误。
实现时为不含 `quality` 的参数定义项目内窄类型，再在唯一的 Taro 调用边界做类型适配；
不得为了满足旧类型声明传入会覆盖精细参数的 `quality`。

`session.test.ts` 增加：

- 待压缩原始分段先写入清单并计入时长。
- 压缩成功后同一 index 转为 `compressed`。
- 压缩失败保留 `rawSavedFilePath` 和错误。
- 旧版没有 `compressionState` 的分段加载为 `compressed`。
- 2400 秒允许，2400001ms 拒绝。

- [ ] **Step 2: 运行定向测试并确认红灯**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/compression.test.ts \
  src/pages/shoulder-press/session.test.ts \
  src/pages/shoulder-press/workflow.test.ts
```

Expected: 新模块和新状态函数尚不存在，测试失败。

- [ ] **Step 3: 实施压缩模块**

`compression.ts` 定义：

```typescript
export const MAX_SHOULDER_PRESS_SEGMENT_SIZE_BYTES = 50 * 1024 * 1024
export const SHOULDER_PRESS_VIDEO_BITRATE_KBPS = 2000
export const SHOULDER_PRESS_VIDEO_FPS = 24
```

`shoulderPressCompressionScale` 按横竖屏目标计算 `Math.min(1, ...)`。
`compressSavedShoulderPressSegment` 必须依次执行原始 `getVideoInfo`、`compressVideo`、
压缩结果 `getVideoInfo` 和 `saveFile`，返回压缩后的永久路径、时长和字节数。不得传
`quality`，因为微信会忽略同时传入的码率、帧率和 resolution。

- [ ] **Step 4: 实施可判别分段状态**

在 `session.ts` 把分段改为：

```typescript
type PendingCompressionSegment = {
  index: number
  compressionState: 'pending_compression' | 'compression_failed'
  rawSavedFilePath: string
  durationMs: number
  compressionError?: string
}

type CompressedSegment = {
  index: number
  compressionState: 'compressed'
  savedFilePath: string
  durationMs: number
  sizeBytes: number
  uploadState: 'pending' | 'uploading' | 'uploaded'
  sha256?: string
}
```

加载旧分段时补为 `compressionState: 'compressed'`。上传 workflow 只接受
`isCompressedShoulderPressSegment(segment) === true` 的分段；遇到待压缩分段必须停止，
不得把原始路径交给 `uploadFile`。`ShoulderPressUploadEvent.state` 改为显式联合
`'pending' | 'uploading' | 'uploaded' | 'finalized'`，不能再从只对 compressed 分段存在的
`uploadState` 索引类型。

- [ ] **Step 5: 运行定向测试并确认绿灯**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/compression.test.ts \
  src/pages/shoulder-press/session.test.ts \
  src/pages/shoulder-press/workflow.test.ts
```

Expected: 全部通过。

- [ ] **Step 6: 提交压缩领域模型**

```bash
git add miniapp/src/pages/shoulder-press/compression.ts \
  miniapp/src/pages/shoulder-press/compression.test.ts \
  miniapp/src/pages/shoulder-press/session.ts \
  miniapp/src/pages/shoulder-press/session.test.ts \
  miniapp/src/pages/shoulder-press/workflow.ts \
  miniapp/src/pages/shoulder-press/workflow.test.ts
git commit -m "feat(miniapp): 建立可恢复的录像分段压缩"
```

---

### Task 3: 接入低档位录制、压缩重试与 40 分钟收尾

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Modify: `miniapp/src/pages/shoulder-press/pageState.ts`
- Modify: `miniapp/src/pages/shoulder-press/pageState.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/recorder.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`
- Modify: `miniapp/src/app.scss`

**Interfaces:**
- Consumes: Task 2 的压缩模块与分段状态函数。
- Produces: 摄像页实时压缩、上传页冷启动补压缩、40 分钟安全停止。

- [ ] **Step 1: 写页面集成失败测试**

在 `pages.test.tsx` 扩展 Taro mock：`compressVideo` 返回压缩临时路径，两个
`getVideoInfo` 分别返回原始尺寸和压缩结果。

新增行为断言：

- `Camera.props.resolution === 'low'`。
- 原始 `saveFile` 完成后先持久化 `pending_compression`，再调用压缩。
- 原始 `saveFile` 在 iOS 失败时继续沿用现有临时路径兜底并立即压缩，不能回退已经发布的
  真机兼容修复。
- 上传 API 使用压缩后的永久路径和压缩后大小。
- 压缩成功删除原始永久文件，上传成功删除压缩文件。
- 压缩失败显示“录像压缩失败，可重试”，且 `uploadVideoSegment` 未调用。
- 强制上传页冷启动时先恢复压缩，再开始创建服务端会话和上传。
- 40 分钟时 recorder 的 `maxDurationMs` 为 `2_397_000`。

更新 `pageState.test.ts` 的硬边界断言为 `2_400_000`、安全停止为 `2_397_000`、格式化结果
为 `40:00`。

- [ ] **Step 2: 运行页面定向测试并确认红灯**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pages.test.tsx \
  src/pages/shoulder-press/pageState.test.ts \
  src/pages/shoulder-press/recorder.test.ts
```

Expected: 相机仍为 medium、没有压缩调用、时长仍为 10 分钟。

- [ ] **Step 3: 接入摄像页压缩**

`camera.tsx` 调整 `persistRecordedSegment`：

1. 原始临时文件 `saveFile`。
2. 用原始永久路径原子写入待压缩分段。
3. 调用 Task 2 压缩模块。
4. 更新同一 index 为 compressed。
5. 保存会话后删除原始永久文件。
6. 触发既有单并发后台上传。

相机 JSX 改为 `resolution='low'`。压缩异常通过既有 recorder 失败分段机制显示并允许重试，
不得丢失已经写入 session 的原始分段。

- [ ] **Step 4: 接入强制上传页补压缩**

`upload.tsx` 在创建服务端会话前，按 index 查找首个未压缩分段并执行压缩。压缩失败时保持
上传页 `0/N`、显示重试按钮和错误；成功后继续原有 `ensureVideoSession -> status ->
segments -> finalize` 流程。重新训练清理 raw 与 compressed 两类路径。

- [ ] **Step 5: 更新 40 分钟边界**

`pageState.ts`：

```typescript
export const SHOULDER_PRESS_HARD_LIMIT_MS = 2_400_000
export const SHOULDER_PRESS_RECORDING_STOP_MS = 2_397_000
```

`session.ts` 的预计时长规范化上限与 manifest 累计上限同步改为 2400 秒。

- [ ] **Step 6: 运行页面定向测试并确认绿灯**

Run:

```bash
cd miniapp
npm test -- src/pages/shoulder-press/pages.test.tsx \
  src/pages/shoulder-press/pageState.test.ts \
  src/pages/shoulder-press/recorder.test.ts
```

Expected: 全部通过。

- [ ] **Step 7: 提交摄像与上传集成**

```bash
git add miniapp/src/pages/shoulder-press/camera.tsx \
  miniapp/src/pages/shoulder-press/upload.tsx \
  miniapp/src/pages/shoulder-press/pageState.ts \
  miniapp/src/pages/shoulder-press/pageState.test.ts \
  miniapp/src/pages/shoulder-press/recorder.test.ts \
  miniapp/src/pages/shoulder-press/pages.test.tsx miniapp/src/app.scss
git commit -m "feat(miniapp): 接入低档位录像压缩与四十分钟训练"
```

---

### Task 4: 实施处方缓存优先与后台刷新

**Files:**
- Create: `miniapp/src/pages/prescription/cache.ts`
- Create: `miniapp/src/pages/prescription/cache.test.ts`
- Modify: `miniapp/src/pages/home/index.tsx`
- Modify: `miniapp/src/pages/prescription/index.tsx`
- Modify: `miniapp/src/auth/token.ts`
- Modify: `miniapp/src/api/client.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Produces: `readCurrentPrescriptionCache()`
- Produces: `writeCurrentPrescriptionCache(value)`
- Produces: `clearCurrentPrescriptionCache()`

- [ ] **Step 1: 写缓存与页面行为失败测试**

`cache.test.ts` 验证 null 处方也可缓存、读取返回当前进程值、clear 后为空。

在 `pages.test.tsx` 增加：

- 首页请求成功后写缓存。
- 命中缓存时 `PrescriptionPage` 首次渲染已经包含动作名称，不显示“正在加载”。
- 后台请求成功替换旧版本。
- 后台请求失败保留缓存动作并显示轻量刷新错误。

在 token/client 测试中断言设置新 token、清除 token 和 401/403 都调用缓存清理。

- [ ] **Step 2: 运行缓存定向测试并确认红灯**

Run:

```bash
cd miniapp
npm test -- src/pages/prescription/cache.test.ts \
  src/pages/shoulder-press/pages.test.tsx \
  src/api/client.test.ts
```

Expected: 缓存模块不存在，处方页仍清空后等待网络。

- [ ] **Step 3: 实施进程内缓存**

`cache.ts` 使用模块级状态和显式命中标记，区分“未缓存”和“已缓存 null”：

```typescript
let hasCachedValue = false
let cachedValue: CurrentPrescription = null
```

首页请求成功时写入 `body.current_prescription`。处方页用缓存初始化 state；`useDidShow`
保留现有 data 和 loaded，后台刷新后更新缓存与页面。缓存刷新失败时已有内容不清空。

`token.ts` 在 `setPatientAppToken` 和 `clearPatientAppToken` 中清理缓存，避免账号切换串数据。

- [ ] **Step 4: 运行缓存定向测试并确认绿灯**

Run:

```bash
cd miniapp
npm test -- src/pages/prescription/cache.test.ts \
  src/pages/shoulder-press/pages.test.tsx \
  src/api/client.test.ts
```

Expected: 全部通过。

- [ ] **Step 5: 提交处方性能优化**

```bash
git add miniapp/src/pages/prescription/cache.ts \
  miniapp/src/pages/prescription/cache.test.ts \
  miniapp/src/pages/home/index.tsx miniapp/src/pages/prescription/index.tsx \
  miniapp/src/auth/token.ts miniapp/src/api/client.test.ts \
  miniapp/src/pages/shoulder-press/pages.test.tsx
git commit -m "perf(miniapp): 缓存处方并后台刷新"
```

---

### Task 5: 完整验证与发布准备

**Files:**
- No production source changes expected; verification failures return to the owning task.
- Update execution record: `docs/superpowers/plans/2026-08-05-training-video-compression-and-prescription-cache.md`

- [ ] **Step 1: 运行完整后端测试**

Run:

```bash
cd backend
pytest
```

Expected: 0 failed。

- [ ] **Step 2: 运行完整小程序测试**

Run:

```bash
cd miniapp
npm test
```

Expected: 0 failed。

- [ ] **Step 3: 执行生产构建和静态检查**

Run:

```bash
cd miniapp
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api npm run build:weapp:prod
cd ..
git diff --check
rg -n -m 1 'https://mcare-wx\\.whestsun\\.com/api' miniapp/dist
```

Expected: 构建成功、无空白错误、构建产物使用生产 API。

- [ ] **Step 4: 审查最终差异与配置残留**

Run:

```bash
rg -n 'TRAINING_VIDEO_MAX_SIZE_BYTES|600_000|597_000|Math\\.min\\(600' \
  backend miniapp/src deploy
git status --short
git diff --stat HEAD
```

Expected: 业务代码和部署配置不再依赖旧总大小或 10 分钟常量；仅历史 migration、spec 或明确
兼容测试可以保留旧字样。

- [ ] **Step 5: 更新计划执行记录并提交验证收口**

在计划顶部追加执行记录，列出各任务 commit 与完整验证结果，然后：

```bash
git add docs/superpowers/plans/2026-08-05-training-video-compression-and-prescription-cache.md
git commit -m "docs(training): 记录视频压缩与处方缓存实施结果"
```

---

### Task 6: 稳定发布服务端与微信开发版

**Files:**
- Production runtime: `/opt/motioncare-prod/.env`
- Deployment workflow: `.github/workflows/deploy-production.yml`
- Miniapp artifact: `miniapp/dist`

**Interfaces:**
- Consumes: 已通过完整验证的 `main` HEAD。
- Produces: 生产 API/Celery 使用新边界；微信平台存在新的开发版本与真机二维码。

- [ ] **Step 1: 发布前核对生产配置并备份**

只读检查当前 `/opt/motioncare-prod/.env` 和容器环境。发布前更新为：

```text
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES=52428800
TRAINING_VIDEO_MAX_DURATION_SECONDS=2400
TRAINING_VIDEO_MAX_SEGMENTS=80
MOTION_ANALYSIS_DOWNLOAD_DEADLINE_SECONDS=900
MOTION_ANALYSIS_STALE_TIMEOUT_SECONDS=7200
```

不得修改数据库、Redis、镜像基础版本或 Nginx 80MB 上限。

- [ ] **Step 2: 推送 main 并监控生产工作流**

```bash
git push origin main
release_run_id="$(gh run list --workflow deploy-production.yml --limit 1 --json databaseId --jq '.[0].databaseId')"
gh run watch "$release_run_id" --exit-status
```

Expected: 构建、测试、镜像推送、数据库备份、migrate 和容器健康检查全部成功。

- [ ] **Step 3: 核对线上容器实际值**

在服务器执行只读检查：

```bash
docker inspect motioncare-api --format '{{range .Config.Env}}{{println .}}{{end}}' \
  | grep -E '^TRAINING_VIDEO_|^MOTION_ANALYSIS_'
docker ps --format '{{.Names}}\t{{.Status}}'
```

Expected: API、Celery、Beat 使用 50MB、2400 秒、80 段、900 秒下载 deadline 和 7200 秒
analysis stale timeout；所有 MotionCare 容器 healthy/running。

- [ ] **Step 4: 上传微信小程序开发版本**

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli upload \
  --project /Users/nick/my_dev/workout/MotionCare/.worktrees/release-production-20260804/miniapp \
  --version 2026.08.05.6 \
  --desc '支持720P录像压缩与处方即时展示' \
  --lang zh
```

当前已上传版本为 `2026.08.05.5`，本次固定使用下一个版本 `2026.08.05.6`。

- [ ] **Step 5: 生成真机二维码并完成烟测**

生成图片二维码后验证：

1. 首页点击“查看处方”，训练列表首屏立即出现。
2. 开始肩部推举，录制超过 30 秒。
3. 第一段压缩并显示 `1/1`，不出现“分段过大”。
4. 压缩/上传失败时原始文件仍可重试。
5. 完成短训练后服务端进入 queued/assembling，不要求等待 40 分钟。

- [ ] **Step 6: 发布完成记录**

记录最终 commit、GitHub Actions run、生产镜像 SHA、小程序开发版本和二维码路径。若任何
检查失败，停止后续发布并保留当前可回滚版本，不执行依赖升级或临时环境改造。
