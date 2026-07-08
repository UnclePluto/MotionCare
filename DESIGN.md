---
name: "MotionCare Patient Miniapp"
description: "患者端微信小程序，服务每日康复训练、健康填报和认知游戏回流。"
colors:
  ink: "#073b4c"
  text: "#164e63"
  muted: "#52727d"
  primary: "#0798b2"
  action: "#11a36a"
  sun: "#ffb84d"
  coral: "#ff6b5a"
  danger: "#c2412d"
  page-cyan: "#e9fbff"
  page-mint: "#f6fff7"
  page-warm: "#fff4d6"
  game-cyan: "#e5fbff"
  game-mint: "#eafbf0"
  white: "#ffffff"
  warning-text: "#8a4f05"
  countdown-text: "#b05f00"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Helvetica, Arial, sans-serif"
    fontSize: "42px"
    fontWeight: 900
    lineHeight: 1.18
    letterSpacing: "0"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Helvetica, Arial, sans-serif"
    fontSize: "36px"
    fontWeight: 900
    lineHeight: 1.22
    letterSpacing: "0"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Helvetica, Arial, sans-serif"
    fontSize: "27px"
    fontWeight: 900
    lineHeight: 1.35
    letterSpacing: "0"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Helvetica, Arial, sans-serif"
    fontSize: "24px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0"
  label:
    fontFamily: "-apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Helvetica, Arial, sans-serif"
    fontSize: "22px"
    fontWeight: 800
    lineHeight: 1.35
    letterSpacing: "0"
rounded:
  sm: "16px"
  md: "18px"
  panel: "16px"
  hero: "16px"
  game: "16px"
  pill: "999px"
spacing:
  xs: "8px"
  sm: "10px"
  md: "14px"
  lg: "16px"
  xl: "18px"
  xxl: "22px"
  panel: "28px"
  page-x: "28px"
  page-y: "38px"
  page-bottom: "64px"
components:
  button-primary:
    backgroundColor: "{colors.action}"
    textColor: "{colors.white}"
    rounded: "{rounded.pill}"
    padding: "0 24px"
    height: "94px"
    typography: "{typography.title}"
  button-secondary:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.pill}"
    padding: "0 24px"
    height: "94px"
    typography: "{typography.title}"
  card-panel:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "28px"
  input:
    backgroundColor: "{colors.white}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "0 22px"
    height: "94px"
    typography: "{typography.title}"
---

# Design System: MotionCare Patient Miniapp

## 1. Overview

**Creative North Star: "海风里的康复工作台"**

MotionCare 患者端小程序的视觉系统来自现有 `miniapp/src/app.scss`：浅青、浅绿和暖黄渐变承载页面底色，深海蓝绿文字保证可读性，海水青蓝和清新绿色承担行动与训练反馈。整体不是医院后台的表单系统，也不是儿童化小游戏，而是一个成人患者每天能稳定使用的移动端康复工作台。

界面密度偏舒适，卡片和按钮触控面积大，字体偏大且加粗。基础页面用浅色任务 hero、半透明白色面板、清楚的进度条和更松的卡片间距建立层级；游戏页面在同一色系内提高活力，使用更大的游戏舞台、图片卡片、声音反馈和明确的暂停、静音、结束控制。

系统明确拒绝三类方向：医生后台或 Ant Design 表单的缩小版；幼儿化游戏包装；旅游宣传页式的海南视觉。海南线索应体现在清爽色彩、图像资源和轻量训练场景中，不应变成营销口号。

**Key Characteristics:**
- 大字号、高权重、低记忆负担。
- 浅青到浅绿、暖黄的背景层，深海蓝绿承载正文。
- 主行动使用绿色到青蓝渐变，状态反馈必须有文字。
- 卡片可用于移动端任务块，但不能堆成后台信息表。
- 游戏页可以更活力，但仍保持成人、可信、清楚。

## 2. Colors

色彩是“海岛康复”而不是“旅游海报”：清爽浅底色给患者安全感，深海文字保证可读性，青蓝和绿色只在行动、进度和反馈上发力。

### Primary
- **海水青蓝** (`#0798b2`): 用于品牌标记、轻量标签、输入边框、游戏卡片边框和当前选中线索。它是识别色，不应铺满大面积背景。
- **康复行动绿** (`#11a36a`): 用于主按钮、成功状态、进度条和正确反馈。主按钮通常以 `#11a36a` 到 `#0798b2` 的渐变出现。

### Secondary
- **阳光黄** (`#ffb84d`): 用于进度条、资源加载、提醒和游戏阶段提示。它提供活力，但不承担主要 CTA。
- **活力珊瑚** (`#ff6b5a`): 用于游戏色块、拼图选中态和少量强调。避免和错误状态混用。

### Tertiary
- **危险红棕** (`#c2412d`): 仅用于错误、危险动作和失败信息。错误区域使用浅红背景配深红文字，不使用纯红大块刺激患者。

### Neutral
- **深海墨蓝** (`#073b4c`): 标题、数值、重要说明和按钮文字。正文可读性的底线。
- **深青正文** (`#164e63`): 次一级项目名或说明文字，在浅底上保持足够对比。
- **静音青灰** (`#52727d`): 辅助说明、加载文字和次要信息。不要继续变浅。
- **浅青页面底** (`#e9fbff`): 基础页面起始背景。
- **浅绿过渡** (`#f6fff7` / `#eafbf0`): 页面中段和游戏状态过渡。
- **柔暖黄底** (`#fff4d6`): 页面底部、游戏页面和提醒区域的温和收束。
- **半透明白面板** (`rgba(255, 255, 255, 0.92)`): 面板、卡片、输入底色。保持轻盈但必须可读。

### Named Rules

**The Deep Text Rule.** 正文和数值优先使用 `#073b4c`、`#164e63` 或 `#52727d`，不要在浅青、浅绿、暖黄背景上继续使用浅灰。

**The Accent Belongs To Action Rule.** `#0798b2` 和 `#11a36a` 用于当前选择、主行动、训练反馈和进度，不用作随意装饰。

**The Coral Is Not Error Rule.** `#ff6b5a` 是活力强调，错误仍使用 `#c2412d`。

## 3. Typography

**Display Font:** `-apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif`
**Body Font:** `-apple-system, BlinkMacSystemFont, "Helvetica Neue", Helvetica, Arial, sans-serif`
**Label/Mono Font:** 无独立字体

**Character:** 单一系统无衬线字体体系，依靠大字号、高字重和稳定行高建立层级。它应像康复陪伴员一样清楚直接，不追求品牌展示字体。

### Hierarchy
- **Display** (`900`, `42px`, `1.18`): 基础页面 hero 主标题，如“今日康复”“当前处方”。只用于页面主任务。
- **Headline** (`900`, `36px`, `1.22`): 游戏页主标题，略小于基础页标题，避免在控制密集页面压迫内容。
- **Title** (`900`, `27px`, `1.35`): 章节标题、数值、按钮文字和重要操作文案。
- **Body** (`400`, `24px`, `1.5`): 说明文字、段落和较长提示。长文应尽量短句化，避免超过 65 到 75 个字符的阅读负担。
- **Label** (`800`, `22px`, `1.35`): 字段标签、统计标签和状态说明。标签不使用全大写或字距扩张。
- **Game Count** (`900`, `64px`, `1.15`): 只用于游戏倒计时和强瞬时提示，不能泛化到普通页面。

### Named Rules

**The One Family Rule.** 小程序只使用一套系统无衬线字体，不为标题、按钮或游戏标签另引入装饰字体。

**The Large But Stable Rule.** 患者端可以大字号，但不使用随视口缩放的流体标题；布局稳定比戏剧化更重要。

## 4. Elevation

当前系统使用短阴影加半透明白底形成移动端层级。阴影是“可触摸面板”和“游戏卡片”的提示，不是装饰；同一个元素不要同时用强边框和重阴影制造后台卡片感。

### Shadow Vocabulary
- **Panel Ambient** (`0 6px 14px rgba(7, 59, 76, 0.08)`): 页面 hero、面板、动作卡、历史行、字段卡和拼图预览图。用于主要任务块。
- **Button Lift** (`0 8px 14px rgba(17, 163, 106, 0.18)`): 主按钮，强调可点击行动。
- **Secondary Lift** (`0 6px 14px rgba(7, 59, 76, 0.08)`): 次按钮和小型图片序列块。
- **Game Card Lift** (`0 6px 14px rgba(7, 59, 76, 0.08)`): 游戏方块、数字题、声音卡、拼图块。
- **Selected Ring** (`0 0 0 6px rgba(255, 107, 90, 0.16)`): 拼图或游戏选中态。用来表达状态，不作为静态装饰。

### Named Rules

**The State First Rule.** 阴影增强必须服务于状态：主行动、可点击、选中、预览或反馈。静态内容块保持轻，不使用大 blur 的后台卡片阴影。

## 5. Components

组件系统以大触控区、明确层级和可读状态为核心。所有交互组件必须有可理解的禁用、加载或失败反馈。

### Buttons
- **Shape:** 全胶囊按钮，`border-radius: 999px`，最小高度 `94px`；紧凑按钮最小高度 `72px`。
- **Primary:** 白字，背景为 `#11a36a` 到 `#0798b2` 渐变，字重 `900`，字号 `27px`，用于“当前处方”“继续训练”“开始游戏”“保存”等主动作。
- **Hover / Focus:** 小程序端没有传统 hover，视觉反馈应通过加载态、禁用态、触摸态和状态文案表达。禁用态使用 `opacity: 0.58`。
- **Secondary / Danger:** 次按钮使用半透明白底和深海文字；危险按钮使用浅红底和 `#c2412d`，不得伪装成普通次按钮。

### Chips
- **Style:** 胶囊形，`padding: 8px 16px`，字号 `22px`，字重 `900`。
- **Game Chip:** 青蓝文字 `#056271` 配青蓝透明底，用于游戏动作。
- **Training Chip:** 绿色文字 `#087148` 配绿色透明底，用于常规训练动作。

### Cards / Containers
- **Corner Style:** 基础面板、页面 hero 和游戏 hero 均为 `16px`，输入和小卡保持 `16px`，按钮使用胶囊。
- **Background:** 半透明白底为主，hero 和统计卡叠加浅青、浅绿或暖黄渐变。
- **Shadow Strategy:** 使用 Panel Ambient；卡片之间通过间距和内容层级区分，不使用彩色侧边条。
- **Border:** `1px solid rgba(7, 59, 76, 0.12)` 是默认面板边界；游戏卡片常用 `2px solid rgba(7, 152, 178, 0.18)`。
- **Internal Padding:** 常规面板 `28px`，hero `38px 30px`，游戏控制条 `20px`，字段卡 `28px`。

### Inputs / Fields
- **Style:** 输入框最小高度 `94px`，`padding: 0 22px`，`border: 2px solid rgba(7, 152, 178, 0.18)`，圆角 `16px`，白底。
- **Focus:** 当前实现没有单独 focus token；新增时应提高青蓝边框可见度，而不是添加复杂发光。
- **Error / Disabled:** 错误使用浅红底、红棕文字和明确文案。禁用状态不要只靠低透明度，关键操作还需要说明。

### Navigation
- **Style:** 小程序页面主要依赖页面内主按钮和 `Taro.navigateTo` 流转，没有全局底部导航。
- **Default / Active:** 页面 hero 负责说明当前任务；主按钮负责下一步。新增导航必须保持同样大触控区和明确文案。
- **Mobile Treatment:** 所有按钮栅格在双列时必须保证最长按钮文案不挤压；关键主行动可跨两列使用 `.full-button`。

### Game Stage
- **Color / Number / Image Tiles:** 最小高度约 `148px` 到 `176px`，两列或三列网格，`16px` 圆角，白底、青蓝边框和轻阴影。
- **Feedback Pill:** `border-radius: 999px`，绿色文字和浅绿底，字号 `30px`，用于短句反馈，如“很好”“再试一题”。
- **Control Bar:** 三列控制，剩余时间跨整行展示。暂停、静音和提前结束必须常驻且不遮挡题目。
- **Puzzle:** 拼图预览图 `380px` 高，拼图块使用正方形比例和选中 ring，先点击交换，不做拖拽。

## 6. Do's and Don'ts

### Do:
- **Do** 使用 `#073b4c` 作为标题和关键数值，确保浅色背景上的可读性。
- **Do** 把主动作做成 `94px` 高的胶囊按钮，文案使用“开始游戏”“保存”“继续训练”这类动词加对象。
- **Do** 让每个页面先回答下一步，患者不应为了理解流程阅读长段说明。
- **Do** 在训练反馈、音频失败、补传、暂停和提前结束时同时提供文字提示。
- **Do** 保留海南康复线索在色彩、图像和轻量场景中，但让康复任务始终优先。
- **Do** 在游戏中使用短反馈句池，避免连续训练时重复同一句。

### Don't:
- **Don't** 把患者端做成医生后台或 Ant Design 表单的缩小版。不要使用过密表格、管理端卡片堆叠和弱对比灰字。
- **Don't** 儿童化游戏包装。避免幼儿插画、夸张卡通字体、过度奖励话术和把训练结果游戏化到掩盖医疗目的。
- **Don't** 做旅游宣传页。不要让海岛图像、暖黄底色或口号抢走训练任务。
- **Don't** 使用 `border-left` 或 `border-right` 大于 `1px` 的彩色侧边条作为卡片装饰。
- **Don't** 用颜色作为唯一状态。正确、错误、补传、暂停和禁用都需要文字或结构辅助。
- **Don't** 让动画决定内容是否出现。内容默认可见，动效只表达状态变化。
