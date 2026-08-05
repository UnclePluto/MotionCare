> 状态：implemented
> 日期：2026-08-05
> 范围：肩部推举录像取消压缩，改为 15 秒原始分段直接上传，并避免正常流程占用微信持久化文件空间。
> 关联：`docs/superpowers/specs/2026-08-05-training-video-compression-and-prescription-cache-design.md`
>
> 审批记录（2026-08-05）：用户确认取消客户端分段大小拦截、保留服务端 80MB
> 基础设施安全上限，并同意正常路径不调用 `saveFile`、仅在上传失败时尝试持久化。

# 训练视频原始分段直传设计

## 1. 背景与根因

当前小程序对每个 30 秒录像分段依次执行原始文件 `saveFile`、`compressVideo` 和压缩结果
`saveFile`。微信小程序持久化文件与用户文件共享约 200MB 空间，原始分段与压缩分段在
处理期间同时占用空间。真机约录制两至三分钟后，累计文件达到额度，`saveFile` 返回
`the maximum size of the file storage limit is exceeded`，导致上传尚未开始便失败。

该问题发生在微信客户端文件生命周期，不是 MotionCare API、Nginx 或七牛云上传失败。
缩短分段只能推迟额度耗尽，不能解决持续持久化带来的累计占用。

## 2. 已确认决策

1. `Camera` 继续使用 `resolution="low"`，不升级 Taro 或其它运行环境。
2. 取消 `compressVideo`，每个相机原始 MP4 分段直接上传 MotionCare API。
3. 标准分段从 30 秒缩短为 15 秒，最长录像保持 40 分钟。
4. 正常分段不调用 `saveFile`，直接使用相机临时路径写入清单并单并发上传。
5. 上传成功后立即清理本地路径；上传失败时才尝试 `saveFile` 保存该失败分段。
6. 如果失败分段因微信空间不足无法持久化，保留当前临时路径供本次进程内重试，并明确提示；
   小程序被强制关闭后该未持久化分段允许丢失，已上传分段不受影响。
7. 客户端删除 50MB 业务拦截；服务端保留 80MB 单请求安全上限。
8. 完整视频不设置累计字节上限，服务端仍按 40 分钟、连续分段和会话归属做校验。
9. 40 分钟包含 160 个标准分段；服务端允许最多 200 段，为暂停产生的短尾段保留余量。
10. 旧版 `pending_compression`、`compression_failed` 和 `compressed` 清单必须兼容：
    原始待压缩分段升级后读取实际文件信息并直接转为待上传，不再执行压缩。

## 3. 客户端数据流

正常路径：

```text
Camera 每 15 秒返回临时 MP4
  -> getVideoInfo / getFileInfo 读取真实时长和字节数
  -> 原子追加为待上传分段（标记 temporary）
  -> 建立或复用服务端视频会话
  -> 单并发 uploadFile
  -> 服务端确认哈希
  -> 标记 uploaded 并尽力删除本地临时文件
```

失败路径：

```text
uploadFile 失败
  -> 若分段仍是 temporary，调用一次 saveFile
  -> 成功：清单路径替换为持久化路径并标记 saved
  -> 失败：保留临时路径和原始上传错误，允许当前进程重试
  -> 后续进入强制上传页，按分段序号继续上传
```

录像继续采用单并发上传。网络持续失败时，不为所有后续分段重复制造持久化副本；失败分段
按顺序重试，避免再次把 200MB 持久化空间作为完整录像缓存。

## 4. 清单兼容

新分段继续使用现有可上传分段字段，增加本地文件状态：

```text
savedFilePath
durationMs
sizeBytes
uploadState = pending | uploading | uploaded
localFileState = temporary | save_failed | saved
```

`save_failed` 表示本次进程已尝试持久化但微信空间不足，后续上传重试不得反复调用
`saveFile`。历史 `compressed` 分段缺少 `localFileState` 时按 `saved` 读取。历史
`pending_compression` / `compression_failed` 分段保留原始路径与时长，在上传页通过
`getFileInfo` 获得精确大小后原位转换为可上传分段，序号和会话标识保持不变。

用户可见文案不再出现“压缩训练分段”“录像压缩失败”或“分段超过 50MB”。旧清单文件
不存在时显示录像文件已失效并引导重新训练，不能提交虚假大小。

## 5. 服务端边界

```text
TRAINING_VIDEO_SEGMENT_MAX_SIZE_BYTES = 83886080
TRAINING_VIDEO_MAX_DURATION_SECONDS = 2400
TRAINING_VIDEO_MAX_SEGMENTS = 200
```

- 声明大小和流式落盘仍执行 80MB 双层安全校验。
- Nginx `client_max_body_size 80m` 保持不变。
- 不恢复完整视频累计大小限制。
- 会话、患者、处方动作、连续索引、实际大小、哈希和总时长校验保持不变。
- FFmpeg 合并、七牛最终对象上传、任务互斥和患者数据隔离保持不变。

15 秒低分辨率分段预期显著低于 80MB。该限制是异常请求与磁盘保护，不在小程序端作为
业务错误预判。

## 6. 测试与验收

### 小程序

- 连续录像的 `startRecord.timeout` 为 15 秒。
- 新分段不调用 `saveFile` 或 `compressVideo`，直接上传相机临时路径。
- 上传失败才调用一次 `saveFile`；成功后清单切换到持久化路径，失败时仍可重试。
- 旧待压缩清单不调用 `compressVideo`，读取精确大小后上传原始路径。
- 上传页不显示压缩阶段和 50MB 错误文案。
- 40 分钟标准录像可产生并提交 160 段；短尾段不超过服务端 200 段上限。
- 生产构建保持相机 `resolution="low"`。

### 后端

- 默认单段安全上限为 80MB、最长 2400 秒、最多 200 段。
- 80MB 边界在应用层允许，超过边界在声明和流式落盘两层拒绝。
- 累计视频大小继续不设业务上限。
- 现有视频会话归属、并发分段、幂等、合并与七牛任务测试保持通过。

## 7. 非目标

- 不增加新的转码或客户端压缩方案。
- 不升级 Taro、Django、Nginx、FFmpeg、Celery、基础镜像或系统依赖。
- 不改变医生端视频审阅、动作分析与七牛存储结构。
- 不保证未持久化且尚未上传的临时分段在小程序进程被强制终止后仍可恢复。
