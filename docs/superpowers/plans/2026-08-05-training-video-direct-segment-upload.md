# 训练视频原始分段直传 Implementation Plan

> 状态：implemented
> 执行记录（2026-08-05, codex）：Task 1–6 已完成并通过发布前验证。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 取消肩部推举客户端视频压缩和正常路径持久化，将录像改为 15 秒原始分段直接上传，同时兼容旧清单并保留服务端 80MB 安全边界。

**Architecture:** 相机生成的临时 MP4 读取真实媒体信息后直接进入现有单并发上传队列；只有上传失败的分段才尝试 `saveFile`。现有清单结构增加 `localFileState`，旧待压缩分段在上传页转换为可上传原始分段，服务端继续负责大小、时长、连续性、归属与并发隔离。

**Tech Stack:** Taro 4.2、React 18、TypeScript、Vitest、Django 5、DRF、pytest

## Global Constraints

- 相机继续使用 `resolution="low"`，不得升级 Taro 或其它依赖。
- 标准分段固定为 15 秒，最长录像保持 2400 秒。
- 客户端不得调用 `compressVideo`，正常路径不得调用 `saveFile`。
- 上传失败时最多为该失败分段尝试一次 `saveFile`。
- 单段服务端安全上限为 83886080 字节，完整视频不设累计字节上限。
- 服务端最多接受 200 段，索引、时长、归属和幂等校验保持不变。

---

### Task 1: 15 秒录像轮转

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/recorder.ts`
- Test: `miniapp/src/pages/shoulder-press/recorder.test.ts`

**Interfaces:**
- Consumes: `ShoulderPressRecorder.start()` 与微信 `CameraContext.startRecord`
- Produces: 每代录像向相机传入不超过 15 秒的 `timeout`

- [x] **Step 1: 写失败测试**

新增行为测试：首次和自动轮转的 `startRecord` 都收到 `timeout: 15`；剩余 7 秒时收到
`timeout: 7` 并触发最长时长收尾。

- [x] **Step 2: 运行测试确认 RED**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/recorder.test.ts`

Expected: 现有实现传入 `timeout: 30`，测试按预期失败。

- [x] **Step 3: 实现最小修改**

将 `TIMEOUT_SEGMENT_MS` 改为 `15000`，并从该常量推导 `timeoutSeconds`，不得保留独立的
硬编码 `30`。

- [x] **Step 4: 运行测试确认 GREEN**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/recorder.test.ts`

Expected: PASS。

### Task 2: 原始临时分段直接进入上传队列

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/session.ts`
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Test: `miniapp/src/pages/shoulder-press/session.test.ts`
- Test: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Produces: `appendUploadableShoulderPressSegment(session, { filePath, durationMs, sizeBytes, localFileState })`
- Produces: 可上传分段字段 `localFileState: 'temporary' | 'save_failed' | 'saved'`
- Consumes: `Taro.getVideoInfo`、`Taro.getFileInfo`

- [x] **Step 1: 写失败测试**

覆盖以下行为：

- 新分段用精确字节数和时长写入清单，状态为 `temporary`。
- 相机分段处理调用 `getVideoInfo` 与 `getFileInfo` 后立即触发上传。
- 正常路径不调用 `saveFile` 和 `compressVideo`。
- 历史已压缩分段缺少 `localFileState` 时兼容归一化为 `saved`。

- [x] **Step 2: 运行测试确认 RED**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: 缺少新接口，且现有实现仍调用 `saveFile`、`compressVideo`，测试失败。

- [x] **Step 3: 实现最小修改**

在 `session.ts` 新增精确字节追加接口和本地文件状态；在 `camera.tsx` 删除压缩依赖，
`persistRecordedSegment` 直接读取原始临时文件信息、写清单并触发后台上传。保持
`clientSessionId` 所有权检查和串行清单写入。

- [x] **Step 4: 运行测试确认 GREEN**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: PASS。

### Task 3: 上传失败时按需持久化

**Files:**
- Create: `miniapp/src/pages/shoulder-press/localFile.ts`
- Modify: `miniapp/src/pages/shoulder-press/camera.tsx`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Test: `miniapp/src/pages/shoulder-press/localFile.test.ts`
- Test: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Produces: `saveTemporaryShoulderPressSegmentForRetry(filePath, saveFile)`
- Consumes: 分段的 `localFileState`

- [x] **Step 1: 写失败测试**

覆盖：临时分段上传失败后调用一次 `saveFile` 并替换清单路径；已经持久化的分段不重复
调用；`saveFile` 失败时保留原临时路径和可重试上传错误。

- [x] **Step 2: 运行测试确认 RED**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/localFile.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: 新辅助函数不存在，上传失败没有按需持久化，测试失败。

- [x] **Step 3: 实现最小修改**

新增无 UI 的文件生命周期辅助函数；在相机后台上传和强制上传页的失败分支调用。成功时
原子写入新路径与 `saved` 状态，失败时不得覆盖原始上传错误或删除临时路径。

- [x] **Step 4: 运行测试确认 GREEN**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/localFile.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: PASS。

### Task 4: 旧待压缩清单无压缩迁移

**Files:**
- Modify: `miniapp/src/pages/shoulder-press/session.ts`
- Modify: `miniapp/src/pages/shoulder-press/upload.tsx`
- Delete: `miniapp/src/pages/shoulder-press/compression.ts`
- Delete: `miniapp/src/pages/shoulder-press/compression.test.ts`
- Test: `miniapp/src/pages/shoulder-press/session.test.ts`
- Test: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Produces: `promoteLegacyShoulderPressSegment(session, index, { sizeBytes })`
- Consumes: 历史 `rawSavedFilePath` 与 `durationMs`

- [x] **Step 1: 写失败测试**

构造 `pending_compression` 和 `compression_failed` 清单，断言上传页只调用
`getFileInfo`，保持原序号与时长转换后上传原始路径；断言不调用 `compressVideo`。

- [x] **Step 2: 运行测试确认 RED**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: 现有上传页进入压缩阶段，测试失败。

- [x] **Step 3: 实现最小修改**

将上传页 `compression` 阶段改为 `preparing`；旧清单读取精确大小后原位转换为可上传
分段，删除已无引用的压缩模块和压缩专用测试。用户文案统一为“准备/上传训练分段”。

- [x] **Step 4: 运行测试确认 GREEN**

Run: `cd miniapp && npm test -- src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/pages.test.tsx`

Expected: PASS，代码中不再引用 `compressVideo`。

### Task 5: 服务端 80MB 与 200 段安全边界

**Files:**
- Modify: `backend/config/settings.py`
- Modify: `backend/tests/test_settings.py`
- Modify: `deploy/docker-compose.prod.yml`
- Modify: `deploy/env.production.example`
- Test: `backend/apps/patient_app/tests/test_patient_app_video_api.py`

**Interfaces:**
- Produces: `TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES=83886080`
- Produces: `TRAINING_VIDEO_MAX_SEGMENTS=200`

- [x] **Step 1: 写失败测试**

更新默认配置测试，并增加 80MB 声明边界允许、超过 80MB 拒绝以及第 199 段允许、第 200
索引拒绝的 API 行为覆盖。

- [x] **Step 2: 运行测试确认 RED**

Run: `cd backend && pytest tests/test_settings.py apps/patient_app/tests/test_patient_app_video_api.py -q`

Expected: 当前默认值仍为 50MB/80 段，边界测试失败。

- [x] **Step 3: 实现最小修改**

仅调整 Django 默认值、Compose 默认映射和生产环境示例；保留声明与流式落盘双重校验，
不得新增完整视频累计大小限制。

- [x] **Step 4: 运行测试确认 GREEN**

Run: `cd backend && pytest tests/test_settings.py apps/patient_app/tests/test_patient_app_video_api.py -q`

Expected: PASS。

### Task 6: 回归与生产构建验证

**Files:**
- Modify only if a verification failure exposes an in-scope regression.

**Interfaces:**
- Consumes: Tasks 1–5 的最终实现
- Produces: 可发布的小程序和后端变更

- [x] **Step 1: 扫描残留旧行为**

Run: `rg -n "compressVideo|压缩训练分段|录像压缩失败|50MB|TIMEOUT_SEGMENT_MS = 30000" miniapp/src backend/config deploy`

Expected: 生产代码不再包含客户端压缩与 50MB 业务限制；历史文档不在扫描范围。

- [x] **Step 2: 运行小程序完整验证**

Run: `cd miniapp && npm test && npm run build:weapp:prod`

Expected: 全部测试与生产构建通过。

- [x] **Step 3: 运行后端完整验证**

Run: `cd backend && pytest && ruff check . && python manage.py makemigrations --check --dry-run`

Expected: 全部测试通过、Ruff 无错误、没有新迁移。

- [x] **Step 4: 检查差异和工作区**

Run: `git diff --check && git status --short`

Expected: 仅包含本计划涉及的代码、测试、规格、计划和变更日志；不提交或推送，等待用户明确指令。
