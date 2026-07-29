> 状态：implementing
> 日期：2026-07-14
> 范围：实现肩部推举 30 秒连续分片录制、业务服务器临时接收、自动合并并上传七牛、成功清理和 48 小时失败保留。
> 关联：`docs/superpowers/specs/2026-07-14-segmented-training-video-pipeline-design.md`
> 实施基线：当前工作区中的肩部推举录像、医生审阅与动作分析未提交实现
> 执行记录（2026-07-14, codex）：Task 1-10 已落地于当前工作区；真实七牛发布验收等待配置 AK/SK 与下载域名，尚未提交。
> 复核记录（2026-07-14, codex）：补齐页面隐藏收尾、上传确认崩溃恢复、缺片响应上限、任务互斥/崩溃重投及过期清理竞态；全量测试与二次代码审查通过。

# 肩部推举分片录像与服务端视频任务实施计划

## 目标

把现有“单文件录制 + 小程序直传七牛/本地 complete”链路替换为以下闭环：小程序每 30 秒连续轮转录像，分片只上传业务服务器；用户结束后业务服务器自动校验、FFmpeg 合并、上传完整视频到七牛、创建唯一训练记录并清理全部服务端视频文件。失败分片在手机本地重试，服务端失败文件最多保留 48 小时。

## 全局约束

- 只改肩部推举 `source_key = motion-resistance-shoulder-press` 的录像链路，其他训练入口不变。
- 患者身份和 `ProjectPatient` 只能从 bearer token 推导。
- 七牛 AK/SK 只在业务服务器；小程序不能获得上传凭证或七牛 key。
- 患者端和医生端不建设视频任务管理页面，不提供服务端任务重试按钮。
- 医生端播放和 PP-TinyPose 分析只读取最终七牛完整视频。
- `training` 的 `0002` 已应用，新增 `0003`，不改写历史迁移。
- 全程按 TDD：先新增失败测试，再做最小实现并回归。
- 本次不主动执行 git commit；只有用户明确要求后才提交。

---

## Task 1：分片会话与处理任务模型

**文件：**

- 修改：`backend/apps/training/video_models.py`
- 新建：`backend/apps/training/migrations/0003_segmented_training_video_pipeline.py`
- 修改：`backend/config/settings.py`
- 修改：`.env.example`
- 测试：`backend/apps/training/tests/test_training_video_segments.py`

### 步骤

1. 先写模型测试，覆盖 `TrainingVideoSegment` 的 `(training_video, sequence_index)` 唯一约束、`VideoProcessingJob` 一对一约束、默认状态和 48 小时过期时间。
2. 运行：

   ```bash
   cd backend && pytest apps/training/tests/test_training_video_segments.py -q
   ```

   预期：因模型不存在而失败。
3. 扩展 `TrainingVideo` 状态和会话统计字段，新增 `TrainingVideoSegment`、`VideoProcessingJob`。
4. 增加配置：`TRAINING_VIDEO_TEMP_ROOT`、单分片大小/时长限制、FFmpeg/ffprobe 命令、处理过期时间、自动重试上限和间隔。
5. 生成并检查 `0003`：

   ```bash
   cd backend && .venv/bin/python manage.py makemigrations training
   cd backend && .venv/bin/python manage.py migrate
   ```

6. 重跑模型测试，预期通过。

## Task 2：患者端会话、分片上传与状态查询 API

**文件：**

- 修改：`backend/apps/patient_app/serializers.py`
- 修改：`backend/apps/patient_app/views.py`
- 修改：`backend/apps/patient_app/urls.py`
- 重构：`backend/apps/training/video_services.py`
- 测试：`backend/apps/patient_app/tests/test_patient_app_video_api.py`

### 步骤

1. 用新 API 测试替换旧 upload-intent/complete 测试，覆盖：
   - 创建会话只接收 `prescription_action`。
   - 分片 multipart 上传到业务服务器。
   - 相同序号、相同 SHA-256 重复上传幂等。
   - 相同序号、不同内容返回 409。
   - 其他患者不能访问会话。
   - 状态查询只返回展示字段，不返回服务端路径、七牛凭证或任务操作。
2. 运行目标测试，确认新路由不存在而失败。
3. 实现：

   ```text
   POST /api/patient-app/training-video-sessions/
   POST /api/patient-app/training-video-sessions/{video_id}/segments/
   GET  /api/patient-app/training-video-sessions/{video_id}/
   ```

4. 分片先写受控临时目录，再在数据库事务中记录 hash、大小和时长；冲突时删除本次临时副本，不覆盖已有分片。
5. 删除患者端旧上传凭证、直传七牛和客户端 complete 路由及 serializer/service 入口。
6. 重跑目标测试，预期通过。

## Task 3：finish 幂等、缺片校验与任务投递

**文件：**

- 修改：`backend/apps/patient_app/serializers.py`
- 修改：`backend/apps/patient_app/views.py`
- 修改：`backend/apps/patient_app/urls.py`
- 修改：`backend/apps/training/video_services.py`
- 修改：`backend/apps/training/tasks.py`
- 测试：`backend/apps/patient_app/tests/test_patient_app_video_api.py`

### 步骤

1. 先写测试覆盖：缺失序号返回 409 和 `missing_segments`；finish 后拒绝新分片；重复 finish 只创建一个 job；只在事务提交后调用 `.delay()`。
2. 运行目标测试，确认失败。
3. 实现：

   ```text
   POST /api/patient-app/training-video-sessions/{video_id}/finish/
   ```

   请求包含 `segment_count`、`duration_seconds`、`training_date`。
4. 在 `select_for_update` 事务中校验 `0..segment_count-1`，创建唯一 `VideoProcessingJob`，并通过 `transaction.on_commit` 自动投递处理任务。
5. 重复 finish 返回同一任务；不创建 `TrainingRecord`。
6. 重跑目标测试，预期通过。

## Task 4：FFmpeg 合并、七牛自动上传与成功清理

**文件：**

- 新建：`backend/apps/training/video_processing.py`
- 重构：`backend/apps/training/qiniu.py`
- 修改：`backend/apps/training/tasks.py`
- 修改：`backend/pyproject.toml`
- 测试：`backend/apps/training/tests/test_video_processing.py`
- 测试：`backend/apps/training/tests/test_qiniu.py`

### 步骤

1. 先写单元测试覆盖：分片按序生成 concat 清单；流复制失败回退 H.264/AAC；ffprobe 校验；固定七牛 key；已存在且元数据匹配时复用；不匹配时拒绝覆盖。
2. 写任务集成测试，mock FFmpeg 和七牛适配器，覆盖状态顺序：

   ```text
   validating_segments -> merging -> verifying_merge ->
   uploading_qiniu -> verifying_qiniu -> cleaning -> succeeded
   ```

3. 运行目标测试，确认失败。
4. 增加官方七牛 Python SDK 依赖，由业务服务器执行 `put_file` 和对象 `stat`；保留私有下载 URL 功能。
5. 用 `subprocess.run([...], check=True, timeout=...)` 调用 FFmpeg/ffprobe，不使用 shell 拼接。
6. 上传完成后在事务内创建唯一 `TrainingRecord`、绑定 `TrainingVideo`；只有数据库绑定成功才进入清理阶段。
7. 清理阶段删除全部分片、合并输出和工作目录；清理失败不得标记成功，需进入自动重试。
8. 重跑任务与七牛测试，预期通过。

## Task 5：自动重试、48 小时过期和零留存

**文件：**

- 修改：`backend/apps/training/tasks.py`
- 修改：`backend/config/settings.py`
- 测试：`backend/apps/training/tests/test_video_processing.py`

### 步骤

1. 先写测试覆盖：阶段失败写入 `failed/current_stage/next_retry_at`；调度器只重投到期且未过期任务；超过 48 小时标记 `expired` 并删除服务端全部视频；成功任务临时目录为空。
2. 运行目标测试，确认失败。
3. 新增 Celery Beat 定时项：短周期扫描自动重试，小时级扫描过期清理。
4. 每次失败递增 `attempt_count`，使用有上限的指数退避；在 `expires_at` 前由后端自动重投，不暴露患者端重试 API。
5. 清理函数保证幂等，文件不存在视为已清理。
6. 重跑目标测试，预期通过。

## Task 6：医生端播放与动作分析兼容新最终视频

**文件：**

- 修改：`backend/apps/training/video_services.py`
- 修改：`backend/apps/training/video_views.py`
- 修改：`backend/apps/training/tracking.py`
- 修改：`backend/apps/training/tests/test_training_video_api.py`
- 修改：`backend/apps/training/tests/test_tracking_api.py`
- 修改：`backend/apps/training/tests/test_motion_analysis.py`

### 步骤

1. 先调整测试：只有 `attached` 且具有最终七牛对象的录像可生成下载 URL和分析任务；处理中录像不出现在训练记录中。
2. 运行三个目标测试文件，确认旧模型假设导致失败。
3. 移除医生端“本地完整视频”分支；最终视频统一按七牛私有 URL 播放。
4. 保持现有前端接口形状，避免医生端 UI 无关重构。
5. 重跑目标测试，预期通过。

## Task 7：小程序分片 API 与持久化重试队列

**文件：**

- 重构：`miniapp/src/pages/shoulder-press/api.ts`
- 重构：`miniapp/src/pages/shoulder-press/session.ts`
- 新建：`miniapp/src/pages/shoulder-press/segmentQueue.ts`
- 修改：`miniapp/src/pages/shoulder-press/api.test.ts`
- 修改：`miniapp/src/pages/shoulder-press/session.test.ts`
- 新建：`miniapp/src/pages/shoulder-press/segmentQueue.test.ts`

### 步骤

1. 先写测试覆盖：创建会话；分片固定上传业务服务器；队列按序、单并发；失败递增退避但保留条目；后端确认后 `unlink` 并移除队列；应用重启可恢复。
2. 运行：

   ```bash
   cd miniapp && npm test -- src/pages/shoulder-press/api.test.ts src/pages/shoulder-press/session.test.ts src/pages/shoulder-press/segmentQueue.test.ts
   ```

   预期：新接口和队列函数不存在而失败。
3. 删除 upload token/provider/key 数据结构，改成 `videoId + segments[] + finishing metadata`。
4. `Taro.uploadFile` 始终请求 `/patient-app/training-video-sessions/{id}/segments/` 并携带 bearer token。
5. 队列上传成功后立即删除对应持久文件；失败不删除、不阻塞录制。
6. 重跑目标测试，预期通过。

## Task 8：连续录制状态机与页面隐藏收尾

**文件：**

- 重构：`miniapp/src/pages/shoulder-press/camera.tsx`
- 新建：`miniapp/src/pages/shoulder-press/recordingMachine.ts`
- 新建：`miniapp/src/pages/shoulder-press/recordingMachine.test.ts`
- 修改：`miniapp/src/app.scss`

### 步骤

1. 先用纯状态机测试覆盖：5 秒倒计时；30 秒回调先触发下一段再入队上一段；总计时不归零；手动结束和 `useDidHide` 保存最后分片且不再启动；重复回调不产生重复序号。
2. 运行目标测试，确认失败。
3. 摄像页开始倒计时前创建服务端会话；保持屏幕常亮。
4. `timeoutCallback` 中同步启动下一次 `startRecord`，再异步 `saveFile`、写队列并触发单并发上传。
5. 用户结束或页面隐藏后停止当前段，保存最后分片并跳转上传页；本地保存失败则结束录制并保留可恢复状态。
6. 删除“单次录像最长 30 秒”文案，展示连续总时长。
7. 重跑状态机和小程序相关测试，预期通过。

## Task 9：上传/处理只读进度页与异常恢复

**文件：**

- 重构：`miniapp/src/pages/shoulder-press/upload.tsx`
- 修改：`miniapp/src/pages/shoulder-press/index.tsx`
- 修改：`miniapp/src/pages/prescription/index.tsx`
- 修改：`miniapp/src/pages/shoulder-press/session.test.ts`
- 修改：`miniapp/src/app.scss`

### 步骤

1. 先写测试覆盖：页面先排空本地分片队列，再调用 finish；缺片时继续上传；finish 后只轮询状态；没有七牛上传/服务端重试按钮；成功清理本地会话并返回处方；重启时自动恢复上传页。
2. 运行目标测试，确认失败。
3. 页面展示“上传分片 N/M、视频处理中、训练已保存”；服务端内部错误只显示通用等待/失败提示。
4. `attached/succeeded` 后清空本地会话并显示训练完成；`expired` 才提示重新训练。
5. 动作讲解页和处方页检测未完成会话，自动恢复到上传页，不恢复摄像。
6. 重跑全部小程序测试并构建：

   ```bash
   cd miniapp && npm test
   cd miniapp && npm run build:weapp
   ```

## Task 10：全量回归与真机验收准备

### 步骤

1. 后端全量验证：

   ```bash
   cd backend && pytest
   cd backend && .venv/bin/ruff check .
   cd backend && .venv/bin/python manage.py makemigrations --check
   ```

2. 医生前端验证：

   ```bash
   cd frontend && npm run test
   cd frontend && npm run lint
   cd frontend && npm run build
   ```

3. 小程序验证：

   ```bash
   cd miniapp && npm test
   cd miniapp && npm run build:weapp
   ```

4. 启动 Django、Celery worker、Celery Beat、医生端 Vite 和小程序 watch build。
5. 本地 FFmpeg 验收至少 70 秒三分片，确认：一个最终视频、一个训练记录、服务端临时目录为空。
6. 真机验收前检查七牛 AK/SK、bucket 和下载域名；未配置真实凭证时明确标记“七牛发布链路未实测”，不作通过声明。
