> 状态：approved
> 日期：2026-08-11
> 范围：永久切换微信小程序 AppID，并上传开发版
> 关联：`docs/superpowers/specs/2026-08-11-wechat-miniapp-appid-migration-design.md`
> 实施基线 commit：`86f9412`

# 微信小程序 AppID 永久迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 MotionCare 微信小程序永久切换到指定的新 AppID，连接现有线上 API，并上传版本 `2026.08.11.1` 到新小程序的开发版。

**Architecture:** 仅修改 Taro 微信项目的源 AppID 配置，生产构建时显式注入现有线上 API。构建产物通过静态断言核对后，提交并推送 `main`，最后使用微信开发者工具 CLI 上传开发版。

**Tech Stack:** Taro 4、React 18、Vitest、微信开发者工具 CLI、Git

## Global Constraints

- 新 AppID 固定为 `wx095c9a6c41b60112`。
- 线上 API 固定为 `https://mcare-wx.whestsun.com/api`。
- AppSecret 不得写入源码、配置文件、Git 历史、构建命令或发布日志。
- 开发版版本号固定为 `2026.08.11.1`，描述固定为 `迁移至新 AppID，连接现有线上服务`。
- 不修改后端部署、数据库、七牛云配置和现有线上服务。
- 任一测试、构建或上传步骤失败时立即停止，不得宣称发布成功。

---

## 文件结构

- Modify: `miniapp/project.config.json` — 微信开发者工具源项目配置，永久保存新的 AppID。
- Generated/Verify only: `miniapp/dist/project.config.json` — Taro 构建生成的小程序项目配置，不提交。
- Modify: `docs/superpowers/plans/2026-08-11-wechat-miniapp-appid-migration.md` — 记录执行进度和最终上传结果。

### Task 1: 同步发布基线并切换源 AppID

**Files:**
- Modify: `miniapp/project.config.json`

**Interfaces:**
- Consumes: `origin/main` 与本地 `main` 发布工作区。
- Produces: `project.config.json.appid === "wx095c9a6c41b60112"`。

- [ ] **Step 1: 核对远端基线与工作区**

Run:

```bash
git status --short
git fetch origin main
git merge-base --is-ancestor origin/main HEAD
```

Expected: 工作区无输出，远端 `main` 是当前本地提交的祖先；否则停止并先处理分叉，禁止覆盖远端提交。

- [ ] **Step 2: 运行配置断言并观察旧 AppID 失败**

Run:

```bash
node -e "const c=require('./miniapp/project.config.json'); if(c.appid!=='wx095c9a6c41b60112') throw new Error('AppID 尚未迁移')"
```

Expected: FAIL，错误为 `AppID 尚未迁移`。

- [ ] **Step 3: 修改源项目 AppID**

将 `miniapp/project.config.json` 的：

```json
"appid": "wx235eef23281228d6"
```

替换为：

```json
"appid": "wx095c9a6c41b60112"
```

不得添加 AppSecret 或新的敏感配置文件。

- [ ] **Step 4: 验证源配置切换成功**

Run:

```bash
node -e "const c=require('./miniapp/project.config.json'); if(c.appid!=='wx095c9a6c41b60112') process.exit(1); console.log(c.appid)"
git diff --check
git diff -- miniapp/project.config.json
```

Expected: 输出新 AppID；`git diff --check` 通过；差异仅包含 AppID 替换。

### Task 2: 验证小程序测试与生产构建

**Files:**
- Verify: `miniapp/package.json`
- Generated/Verify only: `miniapp/dist/project.config.json`
- Generated/Verify only: `miniapp/dist/**/*.js`

**Interfaces:**
- Consumes: Task 1 产生的新 AppID 源配置。
- Produces: 使用新 AppID 和现有线上 API 的可上传 `miniapp/dist` 产物。

- [ ] **Step 1: 运行小程序全量测试**

Run:

```bash
cd miniapp
npm test
```

Expected: Vitest 全量通过，无失败测试。

- [ ] **Step 2: 生成生产微信小程序产物**

Run:

```bash
cd miniapp
TARO_APP_CONFIG_ENV=production \
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api \
npm run build:weapp:prod
```

Expected: Taro 构建退出码为 0，生成 `miniapp/dist`。

- [ ] **Step 3: 核对产物 AppID 与线上 API**

Run:

```bash
node -e "const c=require('./miniapp/dist/project.config.json'); if(c.appid!=='wx095c9a6c41b60112') throw new Error('构建产物 AppID 错误'); console.log(c.appid)"
rg -F "https://mcare-wx.whestsun.com/api" miniapp/dist -g '*.js'
```

Expected: 第一条命令输出新 AppID；第二条命令至少命中一个构建后的 JavaScript 文件。

### Task 3: 提交并推送永久配置

**Files:**
- Modify: `miniapp/project.config.json`

**Interfaces:**
- Consumes: Task 2 已验证的源码和构建结果。
- Produces: 包含设计、计划和新 AppID 配置的远端 `main`。

- [ ] **Step 1: 确认待提交范围**

Run:

```bash
git status --short
git diff --check
git diff -- miniapp/project.config.json
```

Expected: 仅 `miniapp/project.config.json` 为待提交业务改动，构建产物不进入 Git。

- [ ] **Step 2: 提交 AppID 配置**

Run:

```bash
git add miniapp/project.config.json
git commit -m "chore(miniapp): 永久切换微信小程序AppID"
```

Expected: 生成一个仅包含 AppID 配置变更的提交。

- [ ] **Step 3: 推送 main**

Run:

```bash
git push origin main
```

Expected: 远端 `main` 快进到包含设计、计划和 AppID 配置的最新提交。

### Task 4: 上传微信开发版并记录结果

**Files:**
- Modify: `docs/superpowers/plans/2026-08-11-wechat-miniapp-appid-migration.md`

**Interfaces:**
- Consumes: Task 2 产生的 `miniapp/dist`、微信开发者工具登录态和新 AppID 开发权限。
- Produces: 新 AppID 下的开发版 `2026.08.11.1` 及可追溯执行记录。

- [ ] **Step 1: 使用微信开发者工具 CLI 上传开发版**

Run:

```bash
/Applications/wechatwebdevtools.app/Contents/MacOS/cli upload \
  --project /private/tmp/motioncare-main-release/miniapp \
  --version 2026.08.11.1 \
  --desc "迁移至新 AppID，连接现有线上服务" \
  --lang zh
```

Expected: CLI 明确输出上传成功；若提示未登录、无权限、AppID 不匹配或平台拒绝，停止并报告原始错误。

- [ ] **Step 2: 核对上传版本**

在微信开发者工具或微信公众平台的新 AppID 项目中核对：

```text
版本号：2026.08.11.1
描述：迁移至新 AppID，连接现有线上服务
```

Expected: 开发版本列表出现上述版本；未出现则不得标记完成。

- [ ] **Step 3: 更新计划执行记录**

在本文顶部追加：

```text
执行记录（2026-08-11, Codex）：AppID 已迁移，测试与生产构建通过，开发版 2026.08.11.1 已上传。
```

随后运行 `git rev-parse --short HEAD`，读取 Task 3 生成的七位配置提交号，并使用 `apply_patch` 将该输出原样写入“实施提交”一行。同时将状态改为 `implemented`、所有已完成步骤改为 `[x]`。

- [ ] **Step 4: 提交并推送执行记录**

Run:

```bash
git add docs/superpowers/plans/2026-08-11-wechat-miniapp-appid-migration.md
git commit -m "docs(miniapp): 记录新AppID开发版发布结果"
git push origin main
git status --short
```

Expected: 文档提交与推送成功，最终工作区无输出。
