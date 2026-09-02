# 微信小程序包体与固定素材 CDN 优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 18 张固定游戏图片和 5 段动作说明语音迁移到稳定公开 CDN，把主包与游戏分包分别控制在 1.2 MiB 和 1.3 MiB 内，同时保留游戏音频本地播放和现有训练语义。

**Architecture:** 使用可复现 Node 构建脚本从仓库源素材生成内容哈希文件、统一 JSON 清单和两份按包边界拆分的 TypeScript 清单；七牛发布由复用现有后端凭据的幂等 Django 命令完成。动作说明播放器直接读取稳定 HTTPS M4A，图片型游戏进入正式训练前用 `Taro.getImageInfo` 以最多 3 并发预取全部所需图片，但不调用 `saveFile`；生产构建后按 `dist/app.json` 自动计算主包、分包和总包体积。

**Tech Stack:** Taro 4.2、React 18、TypeScript 5.4、Vitest 3、Node.js ESM、Sharp、Django 5、pytest、七牛 Python SDK、微信小程序 `Taro.getImageInfo` / `Taro.createInnerAudioContext`

**Spec:** `docs/superpowers/specs/2026-09-02-wechat-miniapp-package-size-and-game-assets-cdn-design.md`

> 状态：implementing
> 日期：2026-09-02
> 范围：18 张游戏图片、5 段动作说明语音、CDN 发布、运行时预取和包体预算。
> 实施基线 commit：`8e6f3c2`
> Codex 本地实施记录（2026-09-02）：Task 1 `125b38c`、`355c174`（固定素材生成与音频锁定）；Task 2 `5d28fda`、`601da05`（CDN 配置与路径校验）；Task 3 `fc702fb`、`d216bf1`（本地发布/check-only 与公开 URL 校验实现）；Task 4 `1936f39`（动作语音 CDN 接线）；Task 5 `a118aa0`（游戏图片 key 与移除本地图片）；Task 6 `ae04475`、`1fc0d8c`（预取器与取消竞态）；Task 7 `99b9409`、`7d160a3`、`6e1601a`（页面门禁与迟到错误隔离）；Task 8 `a62cea3`（包体预算门禁）。
> 本地验证记录（2026-09-02）：23 项素材 `build/check/check-only` 通过；后端 `905` 项、小程序 `826` 项、前端 `265` 项测试通过；前端 lint `0` error（`5` 个既有 warning）且 build 通过；使用示例 HTTPS API/CDN 构建变量完成生产微信构建，实测主包 `490570` 字节、游戏分包 `1033774` 字节、总包 `1524344` 字节。
> 外部延期：真实七牛上传、正式 CDN 正文/媒体类型/缓存头探测、微信合法域名确认、开发者工具依赖分析、iOS/Android 真机及微信体验版/正式版上传均待用户授权，未纳入本地完成范围。

## Global Constraints

- 当前生产基线：主包 `1,505.3 KiB`、`pages/game-session` 分包 `1,887.3 KiB`、总包 `3,392.6 KiB`。
- 完成预算：主包不超过 `1.2 MiB`、游戏分包不超过 `1.3 MiB`、任一分包不超过 `1.5 MiB`；微信硬上限为主包/单分包 `2 MiB`、总包 `20 MiB`。
- 只外置 18 张固定游戏图片和 5 段动作说明语音；37 段游戏音频、网络告警音频和运动视频不迁移。
- 5 段动作说明语音必须保持当前已验收 M4A 字节内容，不重新生成、不重新转码、不替换音色。
- 图案/分类/声音卡输出 `256×256 WebP Q85`；拼图输出 `384×384 WebP Q85`；全部去除元数据。
- CDN 对象使用内容哈希文件名、稳定公开 HTTPS URL 和不可变缓存；旧对象不得覆盖或删除。
- 图片型游戏只有在本次需要的全部图片预取成功后才能开始；失败不得写训练开始、逐题结果或上传记录。
- 动作说明语音是增强能力；网络或播放失败必须保留文字并允许预览和训练。
- 不新增 `Taro.saveFile`；不得改变肩部推举录像持久化文件清理和空间预检语义。
- 不修改后端模型、migration、API、训练记录结构、游戏玩法、计分、难度或补传契约。
- 不启用 Taro `mini.optimizeMainPackage`，不继续拆分页面或修改现有 `pages/game-session` 分包边界。
- 用户已授权本隔离分支使用中文规范提交；仍禁止 merge、push、真实七牛上传、正式 CDN 探测和微信版本上传。
- 保留其它会话的未提交文件，不修改 `.impeccable/critique/` 和 `.风格复制模式.swn`。

## File Structure

### 新建

- `miniapp/resources/game-images/source/*.png`：18 张原始 PNG，移出 Taro `sourceRoot` 后继续纳入版本控制。
- `miniapp/resources/motion-instruction-audio/source/*.m4a`：5 段已验收 M4A，移出 Taro `sourceRoot`。
- `miniapp/scripts/staticAssets.mjs`：素材规格、哈希、转换、清单生成和 check 模式的纯实现。
- `miniapp/scripts/staticAssets.test.mjs`：资源数量、尺寸、哈希、版本确定性和生成清单测试。
- `miniapp/scripts/build-static-assets.mjs`：生成外部发布目录和两份 TypeScript 清单的 CLI。
- `miniapp/scripts/verify-static-assets.mjs`：下载 23 个公开 URL，校验正文 SHA-256、媒体类型和缓存头。
- `miniapp/src/assets/staticAssetUrl.ts`：运行时基础 URL 规范化和相对路径拼接。
- `miniapp/src/assets/staticAssetUrl.test.ts`：URL 拼接和非法输入测试。
- `miniapp/src/pages/game-session/gameImageAssetManifest.generated.ts`：仅进入游戏分包的 18 项生成清单。
- `miniapp/src/features/motion-training/instructionAudioAssetManifest.generated.ts`：仅进入主包的 5 项生成清单。
- `miniapp/src/pages/game-session/gameImageAssets.ts`：游戏图片 key、每款游戏需求集合和完整临时路径映射。
- `miniapp/src/pages/game-session/gameImageAssets.test.ts`：18 项映射、按游戏取集和路径解析测试。
- `miniapp/src/pages/game-session/gameImagePreloader.ts`：最多 3 并发、全有或全无、可失效的图片预取器。
- `miniapp/src/pages/game-session/gameImagePreloader.test.ts`：成功、失败、并发、进度、重试代次和取消测试。
- `miniapp/scripts/weappPackageSize.mjs`：主包/分包分类、字节统计、预算判定和最大文件报告。
- `miniapp/scripts/weappPackageSize.test.mjs`：临时目录下的包体分类与阈值测试。
- `miniapp/scripts/check-weapp-package-size.mjs`：对 `dist` 执行包体门禁的 CLI。
- `backend/apps/common/miniapp_static_assets.py`：读取清单、校验本地对象、幂等发布七牛并拒绝冲突。
- `backend/apps/common/management/commands/publish_miniapp_static_assets.py`：`--source-root` / `--check-only` 管理命令。
- `backend/apps/common/tests/test_miniapp_static_assets.py`：清单校验、已存在、上传、冲突和脱敏错误测试。

### 修改

- `miniapp/package.json`、`miniapp/package-lock.json`：增加 `sharp` 和资源/包体脚本。
- `miniapp/.gitignore`：忽略 `output/static-assets/`，保留生成的 TypeScript 清单。
- `miniapp/config/buildEnvironment.ts`、`miniapp/config/buildEnvironment.test.ts`：校验 `TARO_APP_ASSET_BASE_URL`。
- `miniapp/config/index.ts`：注入资源基础 URL，删除游戏图片复制规则。
- `miniapp/.env.development`、`miniapp/.env.production`：增加公开资源基础 URL 配置示例。
- `miniapp/project.config.json`：开启开发者工具上传压缩保护。
- `miniapp/src/features/motion-training/instructionAudioManifest.ts`、对应测试：本地静态导入改为 CDN URL。
- `miniapp/src/pages/shoulder-press/pages.test.tsx`：把动作说明语音断言同步为稳定 CDN URL，保留页面行为断言。
- `miniapp/src/pages/game-session/patternSequence.ts`、`categorySwitch.ts`、`soundDiscrimination.ts`、`puzzle.ts` 及对应测试：从本地 `imageSrc` 改为稳定图片 key。
- `miniapp/src/pages/game-session/index.tsx`、`index.integration.test.tsx`：接入图片准备状态、进度、失败、重试和临时路径渲染。
- `miniapp/src/app.scss`：增加游戏素材准备和失败状态样式。
- `miniapp/src/pages/shoulder-press/assets/audio/*.m4a`：删除两个未被构建引用的重复源文件。

---

### Task 1: 建立可复现的固定素材生成管线

**Files:**
- Create: `miniapp/scripts/staticAssets.mjs`
- Create: `miniapp/scripts/staticAssets.test.mjs`
- Create: `miniapp/scripts/build-static-assets.mjs`
- Create: `miniapp/resources/game-images/source/*.png`
- Create: `miniapp/resources/motion-instruction-audio/source/*.m4a`
- Create: `miniapp/src/pages/game-session/gameImageAssetManifest.generated.ts`
- Create: `miniapp/src/features/motion-training/instructionAudioAssetManifest.generated.ts`
- Modify: `miniapp/package.json`
- Modify: `miniapp/package-lock.json`
- Modify: `miniapp/.gitignore`

**Interfaces:**
- Produces: `buildStaticAssets({ projectRoot, outputRoot, check }): Promise<StaticAssetBuildResult>`。
- Produces: `StaticAssetBuildResult = { assetVersion: string; manifestPath: string; entries: StaticAssetEntry[] }`。
- Produces: `GAME_IMAGE_ASSET_PATHS` 常量和 `GeneratedGameImageKey = keyof typeof GAME_IMAGE_ASSET_PATHS`，值为 `<asset-version>/<hashed-file>.webp`。
- Produces: `MOTION_INSTRUCTION_AUDIO_ASSET_PATHS: Record<MotionSourceKey, string>`，值为 `<asset-version>/<hashed-file>.m4a`。
- Produces: `miniapp/output/static-assets/current-version.txt`，只包含本次确定性 `assetVersion`。

- [x] **Step 1: 写素材规格和确定性失败测试**

在 `staticAssets.test.mjs` 固定全部业务 key，不能用目录扫描结果替代期望集合：

```js
const expectedGameImageKeys = [
  'pattern_sun', 'pattern_coconut', 'pattern_boat', 'pattern_lighthouse', 'pattern_shell',
  'category_pineapple', 'category_bird', 'category_train', 'category_drum', 'category_phone',
  'sound_bird', 'sound_train', 'sound_phone', 'sound_laugh', 'sound_drum',
  'puzzle_beach', 'puzzle_garden', 'puzzle_lighthouse',
]

const expectedMotionAudioKeys = [
  'motion-aerobic-high-knee',
  'motion-balance-sit-stand',
  'motion-resistance-row',
  'motion-resistance-leg-kickback',
  'motion-resistance-shoulder-press',
]

it('builds 18 images and 5 unchanged motion audios with a deterministic version', async () => {
  const first = await buildStaticAssets(fixtureOptions())
  const second = await buildStaticAssets(fixtureOptions())
  expect(first.assetVersion).toMatch(/^v-[a-f0-9]{12}$/)
  expect(second.assetVersion).toBe(first.assetVersion)
  expect(first.entries.filter((item) => item.kind === 'game-image').map((item) => item.key)).toEqual(expectedGameImageKeys)
  expect(first.entries.filter((item) => item.kind === 'motion-instruction-audio').map((item) => item.key)).toEqual(expectedMotionAudioKeys)
})
```

再断言：15 张卡片图为 `256×256`、3 张拼图为 `384×384`、M4A 输出 SHA-256 与源文件相同、每个文件名包含其 SHA-256 前 12 位、`--check` 在生成文件漂移时失败。

- [x] **Step 2: 运行测试并确认模块不存在**

Run:

```bash
cd miniapp
npx vitest run scripts/staticAssets.test.mjs
```

Expected: FAIL，错误包含 `Cannot find module './staticAssets.mjs'`。

- [x] **Step 3: 安装仅用于开发构建的 Sharp**

Run:

```bash
cd miniapp
npm install --save-dev sharp
```

Expected: `sharp` 只出现在 `devDependencies`，不会进入小程序运行包。

- [x] **Step 4: 复制源素材到 Taro sourceRoot 之外的权威目录**

先复制而不删除 `src` 中的运行时文件，使 Task 1 独立完成后现有小程序仍可构建；本地运行时副本分别在
Task 4 和 Task 5 接线完成后删除：

```bash
mkdir -p miniapp/resources/game-images/source
mkdir -p miniapp/resources/motion-instruction-audio/source
cp miniapp/src/pages/game-session/assets/images/game-session/*.png miniapp/resources/game-images/source/
cp miniapp/src/features/motion-training/assets/audio/instructions/*.m4a miniapp/resources/motion-instruction-audio/source/
```

Expected: 18 张 PNG 与 5 段 M4A 数量不变；M4A SHA-256 仍为现有验收值。

- [x] **Step 5: 实现转换、哈希、版本和生成清单**

`staticAssets.mjs` 必须使用 `node:crypto` 计算 SHA-256，使用 Sharp 对卡片图执行
`resize(256, 256).webp({ quality: 85 })`，对拼图执行 `resize(384, 384).webp({ quality: 85 })`。
版本计算固定为：按 `kind:key:sha256` 排序后连接，整体 SHA-256 前 12 位加 `v-`。

生成的统一 `manifest.json` 每项结构固定为：

```js
{
  kind: 'game-image',
  key: 'pattern_sun',
  relativePath: 'v-4c2f61a0d9b8/pattern_sun.93ac94f1550d.webp',
  contentType: 'image/webp',
  sizeBytes: 18234,
  sha256: '93ac94f1550d7fd34ecb22ca31f6e5d6a6489cff4ae56ac9c32693517ea4602f',
  width: 256,
  height: 256,
}
```

音频项使用 `kind: 'motion-instruction-audio'`、`contentType: 'audio/mp4'`，不包含宽高。脚本原子写入
`output/static-assets/<asset-version>/`，写入 `output/static-assets/current-version.txt`，并生成两份无交叉条目的
TypeScript 清单。

- [x] **Step 6: 生成真实产物并验证测试通过**

Run:

```bash
cd miniapp
npm run build:static-assets
npx vitest run scripts/staticAssets.test.mjs
npm run check:static-assets
```

Expected: 23 个外部文件生成；图片合计约 `298 KiB`；音频合计约 `1,028 KiB`；测试与 check 模式通过。

- [x] **Step 7: 仅在用户授权后提交本任务**

```bash
git add miniapp/package.json miniapp/package-lock.json miniapp/.gitignore miniapp/resources miniapp/scripts miniapp/src/pages/game-session/gameImageAssetManifest.generated.ts miniapp/src/features/motion-training/instructionAudioAssetManifest.generated.ts
git commit -m "feat(小程序): 建立固定素材生成管线"
```

---

### Task 2: 注入并校验统一 CDN 基础 URL

**Files:**
- Create: `miniapp/src/assets/staticAssetUrl.ts`
- Create: `miniapp/src/assets/staticAssetUrl.test.ts`
- Modify: `miniapp/config/buildEnvironment.ts`
- Modify: `miniapp/config/buildEnvironment.test.ts`
- Modify: `miniapp/config/index.ts`
- Modify: `miniapp/.env.development`
- Modify: `miniapp/.env.production`
- Modify: `miniapp/project.config.json`

**Interfaces:**
- Produces: `resolveAssetBaseUrl({ configuredUrl, target, environment }): string`，供 Taro 构建配置调用。
- Produces: `staticAssetUrl(relativePath: string, baseUrl?: string): string`，供两个运行时清单调用。
- Defines: `process.env.TARO_APP_ASSET_BASE_URL`。

- [x] **Step 1: 写构建环境和运行时 URL 失败测试**

在 `buildEnvironment.test.ts` 追加：

```ts
it('正式微信构建要求绝对 HTTPS 素材地址', () => {
  expect(() => resolveAssetBaseUrl({ configuredUrl: '', target: 'weapp', environment: 'production' })).toThrow('素材地址')
  expect(() => resolveAssetBaseUrl({ configuredUrl: 'http://cdn.example.com/assets', target: 'weapp', environment: 'production' })).toThrow('HTTPS')
  expect(resolveAssetBaseUrl({ configuredUrl: 'https://cdn.example.com/assets/', target: 'weapp', environment: 'production' })).toBe('https://cdn.example.com/assets')
})
```

在 `staticAssetUrl.test.ts` 断言：基础 URL 尾斜杠和相对路径首斜杠均被规范化；空相对路径、`..`、绝对 URL
和协议相对 URL 被拒绝；结果等于 `https://cdn.example.com/assets/v-a1/file.webp`。

- [x] **Step 2: 运行测试并确认失败**

Run:

```bash
cd miniapp
npx vitest run config/buildEnvironment.test.ts src/assets/staticAssetUrl.test.ts
```

Expected: FAIL，缺少 `resolveAssetBaseUrl` 和 `staticAssetUrl`。

- [x] **Step 3: 实现构建期校验与运行时拼接**

正式微信构建为空、非绝对地址或非 HTTPS 时抛错；development 微信构建允许绝对 HTTP/HTTPS，非微信目标
未配置时返回空字符串。`staticAssetUrl` 默认读取 `process.env.TARO_APP_ASSET_BASE_URL`，并拒绝路径穿越：

```ts
export function staticAssetUrl(relativePath: string, baseUrl = process.env.TARO_APP_ASSET_BASE_URL): string {
  const normalizedPath = relativePath.replace(/^\/+/, '')
  if (!baseUrl || !normalizedPath || normalizedPath.split('/').includes('..') || /^[a-z]+:/i.test(normalizedPath)) {
    throw new Error('固定素材路径无效')
  }
  return `${baseUrl.replace(/\/+$/, '')}/${normalizedPath}`
}
```

- [x] **Step 4: 接入 Taro 配置和环境样例**

`config/index.ts` 读取 `TARO_APP_ASSET_BASE_URL`，通过 `resolveAssetBaseUrl` 校验，并注入：

```ts
defineConstants: {
  'process.env.TARO_APP_API_BASE_URL': JSON.stringify(apiBaseUrl),
  'process.env.TARO_APP_ASSET_BASE_URL': JSON.stringify(assetBaseUrl),
}
```

`.env.development` 与 `.env.production` 增加公开 URL 配置行；`project.config.json` 把
`setting.minified` 改为 `true`。基础 URL 可以公开，但不得加入七牛 Access Key、Secret Key 或上传 token。

- [x] **Step 5: 运行测试与生产配置探针**

Run:

```bash
cd miniapp
npx vitest run config/buildEnvironment.test.ts src/assets/staticAssetUrl.test.ts
TARO_APP_API_BASE_URL=https://api.example.com/api TARO_APP_ASSET_BASE_URL=https://cdn.example.com/motioncare/static-assets npm run build:weapp:prod
```

Expected: 测试通过，生产构建成功，`dist/app.js` 中不含七牛密钥或上传 token。

- [x] **Step 6: 仅在用户授权后提交本任务**

```bash
git add miniapp/config miniapp/src/assets miniapp/.env.development miniapp/.env.production miniapp/project.config.json
git commit -m "feat(小程序): 配置固定素材 CDN 地址"
```

---

### Task 3: 建立七牛幂等发布与公开 URL 校验

**Files:**
- Create: `backend/apps/common/miniapp_static_assets.py`
- Create: `backend/apps/common/management/commands/publish_miniapp_static_assets.py`
- Create: `backend/apps/common/tests/test_miniapp_static_assets.py`
- Create: `miniapp/scripts/verify-static-assets.mjs`
- Modify: `miniapp/package.json`

**Interfaces:**
- Produces: `validate_miniapp_static_assets(source_root: Path) -> list[PreparedStaticAsset]`。
- Produces: `publish_miniapp_static_assets(source_root: Path) -> list[PublishedStaticAsset]`。
- Object key: `motioncare/static-assets/<asset-version>/<hashed-file>`。
- CLI: `python manage.py publish_miniapp_static_assets --source-root <version-dir> [--check-only]`。
- CLI: `node scripts/verify-static-assets.mjs --manifest <manifest.json> --base-url <https-url>`。

- [x] **Step 1: 写本地清单与七牛幂等失败测试**

测试必须覆盖：清单缺项、路径越界、SHA-256 不匹配、媒体类型不允许、远端不存在后上传、远端 hash/大小匹配时跳过、
远端冲突时拒绝覆盖、七牛异常不泄露 Access Key/Secret Key、`--check-only` 不发起网络操作，以及发布模块不暴露删除旧对象的路径。

核心断言：

```py
def test_conflicting_remote_object_is_rejected_without_overwrite(tmp_path, monkeypatch):
    source_root = static_asset_fixture(tmp_path)
    upload = Mock()
    monkeypatch.setattr(assets, "stat_object_metadata_or_none", Mock(return_value={
        "hash": "other-etag", "fsize": 123, "mimeType": "image/webp",
    }))
    monkeypatch.setattr(assets, "upload_static_asset", upload)

    with pytest.raises(CommandError, match="远端固定素材冲突"):
        assets.publish_miniapp_static_assets(source_root)

    upload.assert_not_called()
```

- [x] **Step 2: 运行后端测试并确认模块不存在**

Run:

```bash
cd backend
pytest apps/common/tests/test_miniapp_static_assets.py -q
```

Expected: FAIL，缺少 `apps.common.miniapp_static_assets`。

- [x] **Step 3: 实现本地校验和幂等上传**

复用 `apps.training.qiniu.stat_object_metadata_or_none` 和现有七牛配置；上传使用 `qiniu.put_file`，token
采用 `insertOnly: 1`，并显式传入清单媒体类型。上传前后都校验七牛 etag、字节数和媒体类型；远端存在但不一致时
抛 `CommandError`，绝不覆盖。该模块不得导入或调用七牛删除接口，旧版本目录由存储生命周期策略显式排除清理。
日志和命令错误只包含业务 key/object key，不包含 SDK 原始异常或凭据。

- [x] **Step 4: 实现管理命令和公开 URL 校验脚本**

管理命令输出每项的 `key object_key size_bytes 已存在|已上传`。`verify-static-assets.mjs` 对 manifest 的 23 项逐一
`fetch`，要求 200、正文 SHA-256 匹配、图片 `image/webp`、音频 `audio/mp4`，并要求
`Cache-Control` 同时含 `max-age=31536000` 与 `immutable`。

- [x] **Step 5: 运行单元测试与本地 check-only**

Run:

```bash
cd backend
pytest apps/common/tests/test_miniapp_static_assets.py -q
motioncare_asset_version=$(< ../miniapp/output/static-assets/current-version.txt)
python manage.py publish_miniapp_static_assets --source-root "../miniapp/output/static-assets/$motioncare_asset_version" --check-only
```

Expected: 测试通过；check-only 输出 23 项本地校验结果且不访问七牛。

- [ ] **Step 6: 外部发布检查点（待用户授权）**

> 本地实施未读取真实凭据、未上传七牛、未探测正式 CDN，也未确认微信合法域名；待用户授权并提供合规发布环境后执行。

在已有七牛凭据和公开 CDN 域名的环境执行：

```bash
cd backend
motioncare_asset_version=$(< ../miniapp/output/static-assets/current-version.txt)
python manage.py publish_miniapp_static_assets --source-root "../miniapp/output/static-assets/$motioncare_asset_version"
cd ../miniapp
npm run verify:static-assets -- --manifest "output/static-assets/$motioncare_asset_version/manifest.json" --base-url https://cdn.whestsun.com/motioncare/static-assets
```

执行前先确认 `cdn.whestsun.com` 已加入微信小程序合法业务域名，并确认七牛对象生命周期规则不会清理
`motioncare/static-assets/` 下的历史版本。Expected: 23 项均显示“已上传”或“已存在”；公开 URL 正文、媒体类型和
不可变缓存头全部通过。若 CDN 域名尚未配置 `immutable` 缓存头，先在七牛控制台完成域名响应头配置，再重跑验证，
不能降低脚本要求。

- [x] **Step 7: 仅在用户授权后提交本任务**

```bash
git add backend/apps/common/miniapp_static_assets.py backend/apps/common/management/commands/publish_miniapp_static_assets.py backend/apps/common/tests/test_miniapp_static_assets.py miniapp/scripts/verify-static-assets.mjs miniapp/package.json
git commit -m "feat(部署): 增加小程序固定素材发布校验"
```

---

### Task 4: 将动作说明语音切换为稳定 CDN URL

**Files:**
- Modify: `miniapp/src/features/motion-training/instructionAudioManifest.ts`
- Modify: `miniapp/src/features/motion-training/instructionAudioManifest.test.ts`
- Modify: `miniapp/src/pages/shoulder-press/pages.test.tsx`
- Delete: `miniapp/src/features/motion-training/assets/audio/instructions/*.m4a`
- Delete: `miniapp/src/pages/shoulder-press/assets/audio/network_slow_paused.m4a`
- Delete: `miniapp/src/pages/shoulder-press/assets/audio/upload_recovered.m4a`

**Interfaces:**
- Consumes: `MOTION_INSTRUCTION_AUDIO_ASSET_PATHS` 与 `staticAssetUrl(relativePath)`。
- Preserves: `MOTION_INSTRUCTION_AUDIO_SRC: Record<MotionSourceKey, string>`。
- Preserves: `getMotionInstructionAudioSrc(sourceKey: unknown): string | undefined`。

- [x] **Step 1: 把本地资源测试改为 CDN 契约并确认失败**

将现有 `existsSync` 断言替换为：

```ts
it('maps every official motion source key to one immutable CDN m4a', () => {
  expect(Object.keys(MOTION_INSTRUCTION_AUDIO_SRC)).toEqual([...OFFICIAL_MOTION_SOURCE_KEYS])
  for (const sourceKey of OFFICIAL_MOTION_SOURCE_KEYS) {
    expect(getMotionInstructionAudioSrc(sourceKey)).toMatch(
      new RegExp(`^https://cdn\\.example\\.com/assets/v-[a-f0-9]{12}/${sourceKey}\\.[a-f0-9]{12}\\.m4a$`),
    )
  }
})
```

使用 `vi.resetModules()` 和 `vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/assets')` 后再
`await import('./instructionAudioManifest')`，确保环境变量在模块求值前生效；未知 key 仍返回 `undefined`。
运行后应因当前结果仍是本地
`/features/motion-training/assets/audio/instructions/motion-resistance-row.m4a` 而失败。

- [x] **Step 2: 删除静态导入并接入生成清单**

`instructionAudioManifest.ts` 的实现收敛为：

```ts
export const MOTION_INSTRUCTION_AUDIO_SRC = Object.fromEntries(
  OFFICIAL_MOTION_SOURCE_KEYS.map((sourceKey) => [
    sourceKey,
    staticAssetUrl(MOTION_INSTRUCTION_AUDIO_ASSET_PATHS[sourceKey]),
  ]),
) as Record<MotionSourceKey, string>
```

不得修改运动说明页、播放器 90 秒超时、自动播放代次隔离、重播、隐藏/卸载停止和错误文案。
同步把 `pages.test.tsx` 中 5 个本地动作说明路径断言改成与生成清单一致的 CDN URL；只改资源地址期望，不弱化行为断言。

- [x] **Step 3: 删除已外置说明语音与未使用重复告警音频**

删除 `features/motion-training/assets/audio/instructions/` 下 5 个已外置文件；删除
`pages/shoulder-press/assets/audio/` 下两个未被引用的文件；保留
`features/motion-training/assets/audio/` 下公共文件。运行 `rg` 确认源码没有肩部推举旧资源路径。

- [x] **Step 4: 运行语音和页面回归测试**

Run:

```bash
cd miniapp
npx vitest run src/features/motion-training/instructionAudioManifest.test.ts src/features/motion-training/alertAudio.test.ts src/pages/shoulder-press/pages.test.tsx
```

Expected: 5 个 URL 映射、未知 key、自动播放、重播、失败文字降级和页面生命周期测试全部通过。

- [x] **Step 5: 仅在用户授权后提交本任务**

```bash
git add miniapp/src/features/motion-training/instructionAudioManifest.ts miniapp/src/features/motion-training/instructionAudioManifest.test.ts miniapp/src/pages/shoulder-press/pages.test.tsx miniapp/src/pages/shoulder-press/assets/audio
git commit -m "feat(小程序): 动作说明语音改用 CDN"
```

---

### Task 5: 将游戏玩法资源从本地路径改为稳定图片 key

**Files:**
- Create: `miniapp/src/pages/game-session/gameImageAssets.ts`
- Create: `miniapp/src/pages/game-session/gameImageAssets.test.ts`
- Modify: `miniapp/src/pages/game-session/patternSequence.ts`
- Modify: `miniapp/src/pages/game-session/patternSequence.test.ts`
- Modify: `miniapp/src/pages/game-session/categorySwitch.ts`
- Modify: `miniapp/src/pages/game-session/categorySwitch.test.ts`
- Modify: `miniapp/src/pages/game-session/soundDiscrimination.ts`
- Modify: `miniapp/src/pages/game-session/soundDiscrimination.test.ts`
- Modify: `miniapp/src/pages/game-session/puzzle.ts`
- Modify: `miniapp/src/pages/game-session/puzzle.test.ts`
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/game-session/index.integration.test.tsx`
- Modify: `miniapp/config/index.ts`
- Delete: `miniapp/src/pages/game-session/assets/images/game-session/*.png`

**Interfaces:**
- Produces: `GameImageKey`，精确包含 18 个生成清单 key。
- Produces: `GameImagePathMap = Record<GameImageKey, string>`。
- Produces: `requiredGameImageKeys(gameCode: GameCode | null): readonly GameImageKey[]`。
- Produces: `gameImageRemoteUrl(key: GameImageKey): string`。
- Produces: `loadedGameImagePath(paths: GameImagePathMap, key: GameImageKey): string`。

- [x] **Step 1: 写 18 项映射和按游戏需求失败测试**

```ts
it('loads only the image set required by each game', () => {
  expect(requiredGameImageKeys('game-memory-color-sequence')).toEqual([])
  expect(requiredGameImageKeys('game-executive-inhibition')).toEqual([])
  expect(requiredGameImageKeys('game-memory-pattern-sequence')).toEqual([
    'pattern_sun', 'pattern_coconut', 'pattern_boat', 'pattern_lighthouse', 'pattern_shell',
  ])
  expect(requiredGameImageKeys('game-audiovisual-puzzle')).toEqual([
    'puzzle_beach', 'puzzle_garden', 'puzzle_lighthouse',
  ])
})
```

同一测试文件还要完整断言分类 5 项、声音 5 项、所有集合并集恰好等于生成清单 18 项，未知/空 game code 返回空集合。

- [x] **Step 2: 运行测试并确认模块不存在**

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/gameImageAssets.test.ts
```

Expected: FAIL，缺少 `gameImageAssets.ts`。

- [x] **Step 3: 实现 key、需求集合和远端 URL**

`gameImageRemoteUrl` 只组合生成清单和 `staticAssetUrl`；`loadedGameImagePath` 在完整映射缺 key 时抛
`游戏图片尚未准备完成：<key>`，不静默退回远端 URL。

- [x] **Step 4: 把四个玩法模块改为 key，不改变研究数据 key**

- `PatternToken`：把 `imageSrc` 改为 `imageKey: GameImageKey`。
- `CategoryItem`：把 `imageSrc` 改为 `imageKey: GameImageKey`。
- `SoundCard`：保留用于数据的声音类别，图片字段改为 `imageKey: GameImageKey`；删除 `CATEGORY_IMAGE_SRC`。
- `PuzzleRound`：继续保留 `imageKey: 'beach' | 'garden' | 'lighthouse'` 作为上传明细；新增
  `imageAssetKey: GameImageKey` 供渲染，不能把上传的 `image_key` 改成带 `puzzle_` 前缀的新值。

修改对应测试，断言生成题目携带稳定 key，不再包含 `/pages/game-session/assets/images/`。

为保持本任务独立可构建，页面在 Task 5 暂时通过 `gameImageRemoteUrl(imageKey)` 渲染 CDN URL；Task 7 再统一替换为
预取完成的 `wxfile://` 临时路径。集成测试必须断言 Task 5 后页面不再渲染本地图片路径。

- [x] **Step 5: 删除本地游戏图片和复制规则并运行玩法测试**

删除 `src/pages/game-session/assets/images/game-session/` 下 18 张已外置 PNG；从 `config/index.ts` 删除对应 copy pattern，
保留两个音频 copy pattern。

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/gameImageAssets.test.ts src/pages/game-session/patternSequence.test.ts src/pages/game-session/categorySwitch.test.ts src/pages/game-session/soundDiscrimination.test.ts src/pages/game-session/puzzle.test.ts src/pages/game-session/index.integration.test.tsx
```

Expected: 全部通过；玩法返回结构除图片字段外保持现有计分和数据语义。

- [x] **Step 6: 仅在用户授权后提交本任务**

```bash
git add miniapp/src/pages/game-session miniapp/config/index.ts
git commit -m "refactor(小游戏): 使用固定图片资源键"
```

---

### Task 6: 实现全有或全无的游戏图片预取器

**Files:**
- Create: `miniapp/src/pages/game-session/gameImagePreloader.ts`
- Create: `miniapp/src/pages/game-session/gameImagePreloader.test.ts`

**Interfaces:**
- Consumes: `GameImageKey`、`GameImagePathMap`、`gameImageRemoteUrl(key)`。
- Produces: `GameImageLoadProgress = { completed: number; total: number; percent: number }`。
- Produces: `preloadGameImages(keys, options): Promise<GameImagePathMap>`。
- Options: `{ getImageInfo, onProgress, isCurrent, concurrency?: number }`，默认并发 `3`。
- Produces: `GameImagePreloadCancelledError`，调用方静默忽略；其它失败进入可重试错误态。

- [x] **Step 1: 写成功、并发和全有或全无失败测试**

核心测试使用可控 Promise 证明任意时刻最多 3 个请求：

```ts
it('limits requests to three and returns a complete map', async () => {
  let active = 0
  let peak = 0
  const getImageInfo = vi.fn(async ({ src }: { src: string }) => {
    active += 1
    peak = Math.max(peak, active)
    await Promise.resolve()
    active -= 1
    return { path: `wxfile://${src.split('/').at(-1)}` }
  })

  const result = await preloadGameImages(PATTERN_IMAGE_KEYS, {
    getImageInfo,
    onProgress: vi.fn(),
    isCurrent: () => true,
  })

  expect(peak).toBeLessThanOrEqual(3)
  expect(Object.keys(result)).toHaveLength(5)
})
```

另写测试：空 key 立即返回并报告 100%；单项失败时 Promise reject 且不返回部分 map；`isCurrent` 变 false 时抛取消错误；
进度依次单调到 100；重复 key 去重；`concurrency: 0` 被规范为 1。

- [x] **Step 2: 运行测试并确认失败**

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/gameImagePreloader.test.ts
```

Expected: FAIL，缺少预取模块。

- [x] **Step 3: 实现 worker-pool 预取器**

实现固定 worker 数量从共享索引取 key；每次调用前后检查 `isCurrent()`；仅当全部 key 成功且当前轮次仍有效时，
把 `Partial<Record<GameImageKey, string>>` 收窄为完整 `GameImagePathMap`。Taro 适配器调用：

```ts
({ src }) => Taro.getImageInfo({ src }).then((result) => ({ path: result.path }))
```

不得调用 `downloadFile`、`saveFile` 或文件系统 API。

- [x] **Step 4: 运行测试并确认通过**

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/gameImagePreloader.test.ts
```

Expected: 所有预取状态、并发和取消测试通过。

- [x] **Step 5: 仅在用户授权后提交本任务**

```bash
git add miniapp/src/pages/game-session/gameImagePreloader.ts miniapp/src/pages/game-session/gameImagePreloader.test.ts
git commit -m "feat(小游戏): 增加图片素材预取器"
```

---

### Task 7: 把图片准备状态接入游戏页面

**Files:**
- Modify: `miniapp/src/pages/game-session/index.tsx`
- Modify: `miniapp/src/pages/game-session/index.integration.test.tsx`
- Modify: `miniapp/src/app.scss`
- Verify: `miniapp/src/pages/shoulder-press/pages.test.tsx`

**Interfaces:**
- Consumes: `requiredGameImageKeys(gameCode)`、`preloadGameImages(keys, options)`、`loadedGameImagePath(paths, key)`。
- Adds page state: `imageAssetStatus: 'idle' | 'loading' | 'ready' | 'failed'`。
- Adds page state: `imageAssetProgress: GameImageLoadProgress`、`loadedGameImagePaths: GameImagePathMap | null`。
- Adds: `prepareGameImages(): Promise<void>`，使用递增 generation 让旧回调失效。

- [x] **Step 1: 在页面集成测试中先写素材门禁失败用例**

在 Taro mock 增加 `getImageInfo`。至少覆盖：

```ts
it('blocks an image game until every required image is ready', async () => {
  taroMock.getImageInfo.mockImplementation(() => new Promise(() => undefined))
  const page = await renderGamePage('game-memory-pattern-sequence')
  expect(textContent(page.element)).toContain('正在准备训练图片')
  expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(true)
})

it('keeps non-image games independent from the CDN', async () => {
  const page = await renderGamePage('game-memory-color-sequence')
  expect(findButtonByText(page.element, '开始游戏').props.disabled).toBe(false)
  expect(taroMock.getImageInfo).not.toHaveBeenCalled()
})
```

再写：5 项全部成功后启用开始；部分失败显示“训练图片加载失败”；重试创建新 generation；卸载后迟到回调不更新；
点击开始前不会写训练记录；四款图片游戏渲染使用 `wxfile://` 临时路径。

- [x] **Step 2: 运行页面测试并确认当前仍可直接开始**

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/index.integration.test.tsx
```

Expected: 新测试 FAIL，当前“开始游戏”未受图片状态控制。

- [x] **Step 3: 接入准备状态和重试流程**

动作/游戏 code 确认后自动调用 `prepareGameImages()`：无图片游戏同步设为 `ready`；图片游戏设为 `loading` 并显示
`已完成/总数` 与百分比。`startIntro()` 首行增加 `imageAssetStatus !== 'ready'` 拦截；失败状态只提供“重新加载”和
“返回当前运动计划”。页面卸载、动作变化和重试前递增 generation。

- [x] **Step 4: 所有图片渲染统一解析临时路径**

图案、分类、声音卡和拼图 `<Image src>` 都调用 `loadedGameImagePath(loadedGameImagePaths, imageKey)`；拼图上传明细继续使用
`beach|garden|lighthouse`。预取成功后不再依赖单张 `onError` 继续训练；若渲染阶段仍触发错误，立即暂停/阻止本题并
回到可重试素材错误态，不能用文字占位提交正式结果。

- [x] **Step 5: 增加适老化准备与失败样式**

在 `.game-session-page` 作用域内增加进度轨道、百分比、错误文案和两个大按钮；复用现有颜色 token 和最小触控尺寸，
不得影响主包其它页面或底部训练控制条。

- [x] **Step 6: 运行页面与全游戏回归测试**

Run:

```bash
cd miniapp
npx vitest run src/pages/game-session/index.integration.test.tsx src/pages/game-session/*.test.ts src/pages/shoulder-press/pages.test.tsx
```

Expected: 图片门禁、失败、重试、取消、临时路径，以及现有六款游戏计分/暂停/上传测试全部通过。

- [x] **Step 7: 仅在用户授权后提交本任务**

```bash
git add miniapp/src/pages/game-session/index.tsx miniapp/src/pages/game-session/index.integration.test.tsx miniapp/src/app.scss
git commit -m "feat(小游戏): 训练前预取固定图片"
```

---

### Task 8: 建立包体门禁并完成端到端验证

**Files:**
- Create: `miniapp/scripts/weappPackageSize.mjs`
- Create: `miniapp/scripts/weappPackageSize.test.mjs`
- Create: `miniapp/scripts/check-weapp-package-size.mjs`
- Modify: `miniapp/package.json`
- Verify: `miniapp/dist/app.json`
- Verify: `docs/superpowers/specs/2026-09-02-wechat-miniapp-package-size-and-game-assets-cdn-design.md`
- Verify: `docs/superpowers/plans/2026-09-02-wechat-miniapp-package-size-and-static-assets-cdn.md`

**Interfaces:**
- Produces: `measureWeappPackages({ distRoot, appConfig }): PackageSizeReport`。
- Produces: `assertPackageBudgets(report, budgets): void`。
- CLI: `npm run check:weapp-package-size`。

- [x] **Step 1: 写主包/分包分类和预算失败测试**

临时 `dist` fixture 包含根文件、普通页面、`pages/game-session` 分包和第二个假分包。断言：

```js
expect(report.main.bytes).toBe(400)
expect(report.subpackages['pages/game-session'].bytes).toBe(900)
expect(report.total.bytes).toBe(1500)
expect(() => assertPackageBudgets(report, {
  main: 1200 * 1024,
  subpackage: 1500 * 1024,
  hardPackage: 2 * 1024 * 1024,
  hardTotal: 20 * 1024 * 1024,
})).not.toThrow()
```

再分别制造主包软预算、分包软预算、2 MiB 硬上限、20 MiB 总上限和禁止目录存在，确认错误包含包名、实际字节、阈值和
最大的 10 个文件。

- [x] **Step 2: 运行测试并确认模块不存在**

Run:

```bash
cd miniapp
npx vitest run scripts/weappPackageSize.test.mjs
```

Expected: FAIL，缺少 `weappPackageSize.mjs`。

- [x] **Step 3: 实现真实字节统计和 CLI**

递归使用 `fs.stat().size`，从 `dist/app.json` 的 `subPackages` 或 `subpackages` 读取 root；任何位于分包 root 下的文件只计入
该分包，其余计入主包。CLI 项目预算固定为主包 `1.2 MiB`、任一分包 `1.5 MiB`，并额外断言：

```text
dist/pages/game-session/assets/images 不存在
dist/features/motion-training/assets/audio/instructions 不存在
pages/game-session <= 1.3 MiB
```

- [x] **Step 4: 运行完整自动化验证**

Run:

```bash
cd backend
pytest
cd ../miniapp
npm run test
TARO_APP_API_BASE_URL=https://api.example.com/api TARO_APP_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets npm run build:weapp:prod
npm run check:weapp-package-size
npm run check:static-assets
cd ../frontend
npm run test
npm run lint
npm run build
```

Expected: 后端与小程序全量测试通过；生产构建成功；主包约 `477 KiB`、游戏分包约 `1,005 KiB`、总包约
`1,482 KiB`，允许代码与清单产生少量差异，但必须满足全部预算。

- [x] **Step 5: 验证代码包没有固定外部素材和密钥**

Run:

```bash
cd miniapp
find dist -type f \( -path '*game-session/assets/images/*' -o -path '*audio/instructions/*' \)
rg -n "QINIU_ACCESS_KEY|QINIU_SECRET_KEY|uploadToken" dist
```

Expected: 两条命令均无输出；游戏本地 M4A 和公共网络告警 M4A 仍存在。

- [ ] **Step 6: 微信开发者工具与真机验收（待用户授权）**

> 本地实施未打开微信开发者工具、未上传微信版本，也未执行 iOS/Android 真机发布验收；待用户授权后执行。

在微信开发者工具确认代码依赖分析与脚本报告一致；在 iOS、Android 各检查图案、分类、声音、拼图首次加载、缓存后再次进入、
断网失败和重试；检查 5 个动作说明语音自动播放、重播、断网文字降级；确认颜色顺序和数字抑制在 CDN 故障时仍可开始，
游戏声音辨别音频无额外网络等待。

- [x] **Step 7: 更新本地执行记录但不删除历史**

本地代码落地后保持 spec 与 plan 状态为 `implementing`，在顶部追加 Task 1–8 commit 与范围并勾选已完成的本地项；记录实际主包、
游戏分包和总包字节。只追加 changelog 新条目，不修改 0.24 及更早历史；外部发布和真机项完成前不得标记为 `implemented`。

- [x] **Step 8: 仅在用户授权后提交本任务**

```bash
git add miniapp/scripts/weappPackageSize.mjs miniapp/scripts/weappPackageSize.test.mjs miniapp/scripts/check-weapp-package-size.mjs miniapp/package.json docs/superpowers/specs/2026-09-02-wechat-miniapp-package-size-and-game-assets-cdn-design.md docs/superpowers/plans/2026-09-02-wechat-miniapp-package-size-and-static-assets-cdn.md specs/patient-rehab-system/changelog.md
git commit -m "test(小程序): 增加代码包体预算门禁"
```

---

## 实施完成检查表

- [ ] 23 个 CDN 固定素材使用内容哈希文件名并通过远端正文与缓存头校验。（本地内容哈希与文件校验已完成；远端正文和缓存头待用户授权）
- [x] 5 段动作说明 M4A 与已验收源文件 SHA-256 一致。
- [x] 游戏分包仍包含 37 段本地游戏 M4A，不包含 18 张游戏图片。
- [x] 主包不包含 5 段动作说明 M4A，语音失败不阻塞训练。
- [x] 图片型游戏全量预取成功后才开始；无图片游戏不请求 CDN。
- [x] 小程序未新增 `saveFile`、`downloadFile` 或固定素材文件系统持久化。
- [x] 主包、游戏分包、任一分包和总包均通过软预算与微信硬上限。
- [x] 后端 pytest、小程序 Vitest、生产构建、静态资源 check、包体 check 全部通过。
- [ ] 微信开发者工具、iOS、Android 真机验收通过。（待用户授权）
