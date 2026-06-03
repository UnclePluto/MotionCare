> 状态：review
> 日期：2026-06-01
> 范围：微信小程序患者端游戏体验优化；视觉风格、TTS 配音、反馈短句池、游戏配图全量替换。
> 关联：`docs/superpowers/specs/2026-05-16-wechat-miniapp-real-games-design.md`、`docs/superpowers/specs/2026-05-16-wechat-miniapp-remaining-real-games-design.md`
> 决策更新：患者端小程序游戏视觉不再沿用医生端/Ant Design 风格；本设计只影响小程序游戏体验，不改变医生端、训练记录 API 或游戏判分主链路。

# 微信小程序游戏体验打磨设计

## 背景

小程序 6 个真实游戏已经可以从当前处方进入并完成训练记录回传，但患者端体验仍有明显临时实现痕迹：

- 游戏页视觉仍偏后台表单和 Ant Design 卡片感，不适合患者端小游戏。
- 语音引导由 macOS `say` 生成，机械感强。
- 游戏配图由脚本手写 SVG 生成，视觉质感不足。
- 正确/错误反馈文案和音频过于单一，连续训练时重复感明显。

本设计对患者端游戏体验做一次集中打磨，目标是让游戏部分更像独立的移动端康复小游戏，而不是医生端后台的缩小版。

## 已确认决策

1. 视觉方向采用「海岛活力康复」：清爽、明亮、年轻、亲和，可保留海南康复线索，但不做旅游宣传页。
2. 患者端小程序不需要和医生端统一视觉，也不继续沿用 Ant Design 风格。
3. 配音采用年轻、清亮、有活力的女声，语速略快但不催促，语气鼓励、陪伴。
4. TTS 使用小米 MiMo V2.5 TTS 能力生成静态音频资源；仓库只保存生成后的音频，不保存 API Key。
5. 成功/失败反馈改为多条简短短句随机展示和播放，避免单调；每条语音尽量短，减少播放占用训练时长。
6. 游戏配图全量替换：`pattern_*` 5 张、`category_*` 5 张、`sound_*` 5 张、`puzzle_*` 3 张，共 18 张。
7. 图片使用 ChatGPT 图像生成能力生成统一风格的位图资源；生成后落入小程序静态资源目录。
8. 本期不改变游戏玩法规则、训练记录接口、补传机制、医生端展示和后端模型。

## 目标

- 将游戏页视觉从后台卡片风格调整为移动端游戏化界面。
- 替换机械 TTS，生成自然、有活力的年轻女声引导音频。
- 用短句池替代固定正确/错误反馈，降低重复感和等待感。
- 用统一风格位图替代现有简易 SVG 图，提升图案记忆、分类切换、声音辨别和拼图的视觉质量。
- 保持现有 Taro 微信端构建、游戏状态机、上传补传和测试主链路稳定。

## 非目标

- 不重做 6 个游戏的玩法算法。
- 不新增动态在线 TTS、动态在线图片生成或资源管理后台。
- 不把小米 API Key 写入仓库、前端代码、小程序包或文档。
- 不改医生端视觉，不改后台 API，不改训练记录表结构。
- 不做角色 IP、宠物系统、成长系统或完整游戏化任务系统。

## 视觉设计

### 总体气质

「海岛活力康复」应满足：

- 明亮清爽：主背景使用浅青、浅蓝、柔和暖黄，避免后台灰底和大面积深色。
- 游戏感：按钮、计时、反馈、卡片更像轻量游戏控件，减少表格、分隔线和后台信息密度。
- 成人友好：不儿童化，不使用幼儿插画或过度卡通字体。
- 适老清晰：保持高对比、大字号、明确点击区域和稳定布局。

建议视觉 token：

| 用途 | 建议 |
| --- | --- |
| 背景 | `#E8FAFF` 到 `#FFF7DE` 的轻微纵向渐变，局部用浅绿色过渡 |
| 主色 | 海水青蓝 `#00A9CE` |
| 强调色 | 活力珊瑚 `#FF6B6B`、阳光黄 `#FFB703` |
| 成功色 | 清新绿 `#2EC4B6` |
| 文字 | 深海蓝绿 `#073B4C` |
| 容器 | 半透明白底，较大圆角，弱边框，不做 Ant Design 卡片堆叠 |

### 页面结构

游戏页继续由 `miniapp/src/pages/game-session/index.tsx` 承载，但样式应在 `miniapp/src/app.scss` 中针对 `.game-session-page` 重写：

- 顶部状态区：剩余时间、完成数/正确数、暂停/静音等操作更紧凑。
- 游戏主体区：每个游戏使用一个强视觉主舞台，不再像表单卡片。
- 操作按钮：使用大触控区域，主按钮圆润、色彩明确。
- 反馈区：短文案即时出现，避免长段解释占屏。
- 结果页：突出完成感和上传状态，但不做后台统计表风格。

## TTS 设计

### 生成方式

新增或替换现有音频生成脚本，使用小米 MiMo V2.5 TTS：

- API 基础地址：`https://api.xiaomimimo.com/v1`
- 模型：优先使用 `mimo-v2.5-tts-voicedesign`
- 输入约定：`user` 消息放音色描述，`assistant` 消息放待合成文本
- 音频格式：先请求 `wav`，本地再转为小程序现用的 `m4a`
- Key 来源：只读环境变量 `MIMO_API_KEY`

音色描述建议：

```text
年轻女性，中文普通话，声音清亮自然、富有活力，像专业康复训练陪伴员。
语气积极鼓励但不夸张，语速略快但不催促，咬字清楚，适合移动端小游戏短提示。
```

安全要求：

- 不在代码、文档、日志和提交中保存真实 API Key。
- 本地运行时用环境变量注入，例如 `MIMO_API_KEY=... npm run generate-game-audio`。
- 生成脚本输出中避免打印 Authorization 或完整请求体。

### 音频清单

保留现有 intro、倒计时、开始、完成、提前结束、点击音效的资源语义：

```text
miniapp/src/pages/game-session/assets/audio/game-session/
```

新增正确/错误短句池，建议文件名：

```text
correct_1.m4a
correct_2.m4a
correct_3.m4a
correct_4.m4a
wrong_1.m4a
wrong_2.m4a
wrong_3.m4a
wrong_4.m4a
```

旧 `correct.m4a` / `wrong.m4a` 可在过渡期保留为 fallback。代码层把 `correct` / `wrong` 从单值资源改为数组资源，随机选择。

### 反馈短句

短句需要简洁、成人化、低挫败感：

正确反馈候选：

- 很好
- 答对啦
- 继续保持
- 反应很快

错误反馈候选：

- 没关系
- 再试一题
- 慢慢来
- 调整一下

展示文字与播放音频使用同一条随机结果，避免文字和声音不一致。每条音频应尽量短，理想播放时长控制在 1 秒左右。

## 图片资源设计

### 替换范围

全量替换现有 18 张游戏图：

```text
pattern_sun
pattern_coconut
pattern_boat
pattern_lighthouse
pattern_shell
category_pineapple
category_bird
category_train
category_drum
category_phone
sound_bird
sound_train
sound_phone
sound_laugh
sound_drum
puzzle_beach
puzzle_garden
puzzle_lighthouse
```

### 生成原则

- 使用 ChatGPT 图像生成能力生成位图资源，统一为「海岛活力康复」插画风格。
- 单个物体图用于选项识别，应清晰居中、背景干净、边缘明确。
- 拼图图用于切片，构图必须有可辨识的整体画面和局部特征。
- 不在图片中生成文字，避免小程序缩放后不可读。
- 输出格式优先 PNG；如果包体明显过大，再压缩为 WebP 或优化 PNG。

实现目录使用游戏分包资源路径：

```text
miniapp/src/pages/game-session/assets/images/game-session/
```

现有 `.svg` 资源在 PNG 稳定后删除，避免继续打入小程序包体。

## 代码影响范围

预计修改：

- `miniapp/src/app.scss`：游戏页视觉样式重写。
- `miniapp/src/pages/game-session/gameAudio.ts`：支持正确/错误短句池和随机选择。
- `miniapp/src/pages/game-session/index.tsx`：反馈展示使用随机短句结果，必要时调整游戏页结构 class。
- `miniapp/src/pages/game-session/gameCatalog.ts`、玩法模块或资源清单：图片路径从 `.svg` 切换为新 `.png`。
- `miniapp/scripts/generate-game-audio.mjs`：从 macOS `say` 改为小米 TTS 生成。
- `miniapp/src/pages/game-session/assets/audio/game-session/`：替换或新增 TTS 音频。
- `miniapp/src/pages/game-session/assets/images/game-session/`：新增 18 张统一风格图片。
- `miniapp/src/app.config.ts`、`miniapp/config/index.ts`：游戏页和游戏资源进入分包，避免主包被图片/音频撑大。
- 相关测试：覆盖反馈随机资源选择和现有游戏逻辑不回退。

不应修改：

- 后端模型和迁移。
- `/api/patient-app/training-records/` 接口契约。
- 医生端页面。
- 游戏判分公式和补传策略，除非实现时发现现有逻辑阻塞体验优化。

## 验证

实施完成后至少执行：

```bash
cd miniapp && npm run test
cd miniapp && npm run build:weapp
```

手动检查：

- 微信开发者工具打开 `miniapp/dist`。
- 进入至少 3 个游戏：颜色顺序、声音辨别、拼图。
- 检查首屏、准备页、游戏中、暂停、结果页在手机模拟器中无明显重叠。
- 连续答对/答错多次，确认反馈文案和音频有随机变化。
- 静音开关仍生效，音频播放失败不阻塞游戏。
- 新图片在小程序中正常加载，不拉伸、不裁切关键主体。

## 风险与兜底

- TTS 生成失败：保留脚本错误提示；已生成音频仍可使用；旧音频可作为临时 fallback。
- 图片生成质量不稳定：先生成候选图并人工筛选，再写入资源目录；不满意的图不替换引用。
- 小程序包体增加：必要时压缩 PNG 或改为 WebP，优先保证拼图图片质量。
- 反馈随机导致测试不稳定：随机函数应可注入或在测试中用集合断言，不依赖固定句子。
- 视觉改动影响其他小程序页面：样式限定在 `.game-session-page` 下，避免影响首页、处方、健康填报。
