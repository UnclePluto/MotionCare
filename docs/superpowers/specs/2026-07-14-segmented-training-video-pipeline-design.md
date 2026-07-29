> 状态：approved
> 日期：2026-07-14
> 范围：肩部推举长时录像的 30 秒连续分片、业务服务器临时接收、任务化合并、完整视频上传七牛与临时文件清理。
> 关联：`docs/superpowers/specs/2026-07-08-shoulder-press-video-analysis-design.md`
> 修订（2026-07-14, codex）：纠正旧设计中“单文件录像、小程序直传七牛”的错误记录，恢复已确认的分片中转与服务端合并链路。

# 肩部推举分片录像与视频处理任务设计

## 1. 背景与纠正范围

`2026-07-08-shoulder-press-video-analysis-design.md` 错误记录为“小程序录制单个最长 10 分钟视频并直传七牛”。微信 `CameraContext.startRecord` 单段录像最多 30 秒，该记录既无法支持长时训练，也不符合产品确认的上传链路。

本设计替代旧设计中所有关于录制时长、上传对象、上传路径、完成时点和临时文件清理的描述。旧设计中的肩部推举动作范围、医生端视频审阅和 PP-TinyPose 训练后分析仍然有效。

## 2. 已确认决策

1. 训练总时长不设业务硬上限，只由用户结束或页面隐藏触发收尾。
2. 小程序连续录制，每 30 秒形成一个有序 MP4 分片。
3. 当前分片结束后立即开始下一段录像，同时把上一段保存并加入上传队列。
4. 分片只上传 MotionCare 业务服务器，不直传七牛。
5. 分片上传失败不打断后续录像，失败分片进入本地重试队列。
6. 小程序进入后台、接电话或摄像页隐藏时，自动结束本次训练并进入收尾，不自动恢复录像。
7. 业务服务器接收全部分片后，由任务系统调用 FFmpeg 按序合并。
8. 业务服务器只把合并后的完整视频上传七牛，七牛不存在 30 秒分片。
9. 七牛确认完整视频上传成功后，业务服务器不保留任何视频文件。
10. 只有最终视频可用后才创建一条 `TrainingRecord`。
11. 处理失败的业务服务器临时文件保留 48 小时，期间允许服务端自动重试和运维手动重投；超时后删除并标记 `expired`。运维重投不建设页面。
12. 服务端自动完成合并、七牛上传、校验和清理；患者端与医生端不提供视频任务管理页面或操作按钮。

## 3. 总体时序

```text
患者点击开始训练
  -> 创建 TrainingVideo 会话
  -> 5 秒倒计时
  -> 录制分片 0
  -> 30 秒回调：立即录制分片 1，同时持久化并上传分片 0
  -> 30 秒回调：立即录制分片 2，同时持久化并上传分片 1
  -> ...
  -> 用户结束或页面隐藏
  -> 停止并保存最后分片，不再启动下一段
  -> 上传页等待本地队列清空
  -> finish 会话
  -> 创建 VideoProcessingJob
  -> 校验连续分片
  -> FFmpeg 合并
  -> ffprobe 校验
  -> 上传完整 MP4 到七牛
  -> 校验七牛返回 key/hash
  -> 创建 TrainingRecord 并绑定 TrainingVideo
  -> 删除业务服务器所有分片、合并文件和工作目录
  -> 小程序显示训练完成
```

## 4. 数据模型

### 4.1 TrainingVideo

继续作为一次完整训练录像和最终视频的聚合根，不为分片创建训练记录。

新增或调整字段：

```text
status:
  recording | uploading | queued | validating_segments | merging |
  verifying_merge | uploading_qiniu | verifying_qiniu | cleaning | attached |
  processing_failed | expired
segment_count
uploaded_segment_count
duration_seconds
recording_finished_at
processing_expires_at
storage_backend: qiniu_kodo
bucket
object_key          # 最终完整视频 key
object_hash         # 最终完整视频 hash
size_bytes          # 最终完整视频大小
training_record nullable
failure_reason
```

### 4.2 TrainingVideoSegment

```text
training_video
sequence_index
status: pending | uploaded | failed
server_file_path
content_type
size_bytes
duration_seconds
object_hash
upload_attempts
failure_reason
uploaded_at
created_at / updated_at
```

约束：

- `(training_video_id, sequence_index)` 唯一。
- `sequence_index` 从 0 开始，finish 时必须连续到 `segment_count - 1`。
- `server_file_path` 必须位于服务端受控临时目录，不能由客户端指定。
- 分片不保存七牛 bucket、key 或上传凭证。

### 4.3 VideoProcessingJob

```text
training_video one-to-one
status:
  queued | validating_segments | merging | verifying_merge |
  uploading_qiniu | verifying_qiniu | cleaning |
  succeeded | failed | expired
progress_percent
attempt_count
max_attempts
next_retry_at
current_stage
failure_reason
started_at
finished_at
expires_at
created_at / updated_at
```

同一 `TrainingVideo` 同时只能有一个处理任务。重复 finish 或重复投递必须返回已有任务，不得创建并行合并。

## 5. 小程序录制与本地队列

摄像页状态机：

```text
preparing -> countdown -> recording
recording -> rotating_segment -> recording
recording -> finishing
```

- 使用同一个 `CameraContext` 管理当前摄像页。
- `startRecord.timeoutCallback` 返回分片时，先调用下一次 `startRecord`，再处理上一分片，缩短录像间隙。
- 用户点击结束时调用 `stopRecord`，保存最后一个非空分片。
- 页面隐藏按用户结束处理，但不再启动下一段。
- 总计时跨分片连续累加，不在 30 秒处归零。

本地队列项：

```text
videoId
sequenceIndex
savedFilePath
durationSeconds
sizeBytes
status: pending | uploading | retrying | uploaded
retryCount
lastError
createdAt
```

- 分片返回后使用 `Taro.saveFile` 持久保存，再原子写入本地队列。
- 录制期间上传并发数固定为 1，避免上传争抢摄像资源。
- 上传成功且后端确认后立即调用文件系统 API 删除手机本地分片，并移出队列。
- 上传失败采用递增退避，不暂停录制、不弹出阻断对话框。
- 本地空间不足或保存失败时立即结束训练，保留已有队列并进入恢复上传页。
- 小程序异常退出后，下次启动恢复队列和 `videoId`，直接进入上传页；不恢复摄像。

## 6. 患者端 API

```text
POST /api/patient-app/training-video-sessions/
POST /api/patient-app/training-video-sessions/{video_id}/segments/
POST /api/patient-app/training-video-sessions/{video_id}/finish/
GET  /api/patient-app/training-video-sessions/{video_id}/
```

### 6.1 创建会话

请求只包含 `prescription_action`。后端从患者 token 推导 `ProjectPatient`，校验当前 active 处方和肩部推举动作，创建 `recording` 状态的 `TrainingVideo`。

### 6.2 上传分片

使用 `multipart/form-data` 上传：

```text
sequence_index
duration_seconds
file
```

幂等规则：

- 首次上传创建 `TrainingVideoSegment` 并写入受控临时路径。
- 相同序号和相同 hash 重复提交返回原记录。
- 相同序号但不同 hash 返回 409，不覆盖已上传分片。
- 会话 finish 后拒绝新增分片。

### 6.3 结束会话

请求：

```json
{
  "segment_count": 3,
  "duration_seconds": 70,
  "training_date": "2026-07-14"
}
```

后端校验 `0..segment_count-1` 全部存在且为 uploaded。通过后设置 `queued`、创建唯一 `VideoProcessingJob`，在事务提交后投递 Celery。分片缺失返回 409，并返回缺失序号供小程序继续上传。

### 6.4 查询处理结果

查询接口返回分片总数、已上传数、任务阶段、进度、错误和最终训练记录。该接口只用于页面轮询展示，不暴露七牛上传、任务重试或清理操作。

## 7. 视频处理任务系统

Celery 任务 `process_training_video_job(job_id)` 按以下阶段执行：

1. **validating_segments**：数据库加锁，确认会话已 finish、序号连续、文件存在、hash 与数据库一致。
2. **merging**：在独立临时工作目录生成 concat 清单。优先执行 FFmpeg concat demuxer 流复制；流参数不兼容时回退 H.264/AAC 转码，并启用 `faststart`。
3. **verifying_merge**：使用 ffprobe 检查最终文件可读、包含视频流，最终时长与分片时长总和在允许编码误差内。
4. **uploading_qiniu**：业务服务器使用后端 AK/SK 上传唯一完整 MP4，七牛 key 由后端生成。
5. **verifying_qiniu**：校验七牛返回的 key/hash 与目标对象一致。
6. **cleaning**：原子创建唯一 `TrainingRecord`、绑定最终 `TrainingVideo`，再删除业务服务器分片、合并文件和工作目录。
7. **succeeded**：更新为 `attached`，供小程序和医生端读取。

幂等与并发：

- 任务启动时使用数据库行锁；`succeeded/expired` 任务直接返回。
- 每一阶段开始前读取当前状态，重试从可恢复阶段继续。
- `TrainingVideo.training_record` 一对一约束和服务层锁共同防止重复训练记录。
- 七牛最终 key 固定，重复上传不得生成多个最终对象。重试上传前先查询该 key：对象存在且 hash、大小匹配时直接进入 `verifying_qiniu`；对象不存在时上传；对象存在但元数据不匹配时任务失败并等待人工处理，禁止静默覆盖。

## 8. 重试、过期与清理

- 自动重试采用递增间隔；合并或七牛上传失败不要求患者重新上传分片。
- 失败任务保留业务服务器临时视频 48 小时，并由服务端调度器自动重试。
- Celery Beat 每小时执行过期扫描：超过 `expires_at` 的失败任务标记 `expired`，删除全部业务服务器视频文件。
- 七牛上传成功后，无论数据库后续步骤是否重试，都不得再次生成不同 key 的完整视频。
- 业务服务器成功链路结束时视频文件零留存；数据库只保存元数据和七牛最终对象信息。
- 临时目录使用 `try/finally` 防止进程异常留下本次合并副本；原始分片仅由成功清理或 48 小时过期任务删除。

## 9. 小程序上传与处理页

按后端状态显示：

```text
正在上传分片 N/M
正在校验分片
正在合并视频
正在上传完整视频
正在清理临时文件
训练已保存
```

- 分片上传阶段展示字节进度和待重试数量。
- finish 后轮询任务状态，不允许提前返回完成页。
- 服务端自动执行合并、七牛上传、校验、重试和清理；页面不提供任务管理或重试按钮。
- `failed` 只展示处理未完成及稍后查看提示，不向患者暴露内部任务阶段和运维错误详情。
- `expired` 明确提示临时视频已清理，需要重新训练。
- 只有 `attached/succeeded` 展示训练完成页并刷新处方进度。

## 10. 医生端与动作分析

- 医生端只获取七牛最终完整视频的短有效期下载 URL。
- 训练追踪只展示一条肩部推举训练记录和一个最终视频。
- PP-TinyPose 只分析最终完整视频，不读取业务服务器分片。
- 视频任务未成功前不允许创建动作分析任务。

## 11. 安全与运维

- 患者 API 始终从 bearer token 推导患者和项目，不接受客户端患者 ID 或项目 ID。
- 分片路径由后端生成，并校验路径位于配置的临时根目录内。
- 限制单分片最大时长、最大文件大小和允许的 MIME 类型；训练总时长不设业务硬上限。
- 业务服务器必须配置足够的临时磁盘监控、FFmpeg、ffprobe、Celery worker 和 Celery Beat。
- 七牛 AK/SK 只存在业务服务器环境变量中。
- 当前本地环境若未配置七牛 AK/SK，只能完成分片接收和 FFmpeg 合并测试，不能宣称七牛发布链路验收通过。

## 12. 测试与验收

### 小程序

- 30 秒回调先启动下一段，再持久化和排队上一段。
- 分片上传失败继续录制，并进入重试队列。
- 手动结束和页面隐藏都保存最后分片且不再启动下一段。
- 上传确认后删除手机本地分片。
- 异常重启恢复未上传队列和任务轮询。

### 后端 API

- 相同会话和序号上传幂等，不同 hash 冲突。
- finish 拒绝缺失或断号分片，并返回缺失序号。
- 重复 finish 只创建一个 `VideoProcessingJob`。
- finish 后拒绝新分片。

### 任务系统

- FFmpeg 严格按序合并。
- 七牛只收到一个最终完整 MP4，不存在分片对象。
- 七牛上传并绑定成功后业务服务器视频零留存。
- 合并失败和七牛失败可在 48 小时内重试。
- 超过 48 小时自动删除业务服务器临时视频并标记 expired。
- 重复执行任务不重复创建 `TrainingRecord`。

### 端到端

- 真机连续录制至少 70 秒，业务服务器收到 3 个连续分片。
- 结束后任务完成，七牛只有一个完整视频。
- 医生端可连续播放完整视频，训练追踪只有一条记录。
- 服务端会话临时目录为空。

## 13. 非目标

- 不在小程序端合并或转码 MP4。
- 不把七牛作为分片暂存区。
- 不在训练中做实时动作识别或纠错。
- 不支持中断后恢复同一次摄像录制，只恢复分片上传和处理任务。
