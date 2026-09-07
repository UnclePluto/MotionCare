# 小程序固定素材私有签名访问实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.
>
> 状态：implementing（用户选择子代理逐任务执行）
> 日期：2026-09-07
> 范围：固定素材签名访问、客户端接入、素材验收与微信 7.0.4 上传。
> 实施基线 commit：480a501c6b390748d09a2d228dbc7caf1e193077

**Goal:** 使用现有七牛私有空间及 cdn.whestsun.com 为 23 项固定素材提供受清单约束的临时签名，保留演示体验，完成患者 H5 更新和微信开发版 7.0.4 上传。

**Architecture:** 素材生成器同时产出前后端版本清单；匿名、限流的后端接口只签发清单内对象。客户端共用内存签名缓存，图片预取和动作说明播放器分别处理生命周期；先部署后端并验收素材，再启用新版 H5 与上传小程序。

**Tech Stack:** Django 5、DRF、Redis、七牛 Python SDK、React 18、TypeScript、Taro 4.2、Vitest、pytest-django、GitHub Actions、微信开发者工具 CLI。

**Spec:** [已批准设计](../specs/2026-09-07-miniapp-private-static-assets-design.md)

## Global Constraints

以下内容直接来自已批准 spec，适用于所有任务：

- 后端批量返回固定素材签名清单，默认有效期 10 分钟。
- 保留 8888 未登录演示模式，只能获取通用素材清单中的文件签名。
- 素材签名由后端生成，小程序不持有长期签名密钥。
- 图片仍须全部预加载成功后才能开始对应游戏。
- 动作说明语音在播放前获取有效地址，失败保留文字说明。
- 37 段内置游戏音频保持原状；本项不制作或替换题目配音。
- 对象前缀固定为 motioncare/static-assets/。
- 不修改训练视频使用的 QINIU_DOWNLOAD_DOMAIN。
- URL TTL 默认 600 秒，限定为 120–3600 秒。
- 默认每个可信客户端 IP 每 60 秒最多 60 次请求。
- 清单响应设置 Cache-Control: no-store。
- 清单只缓存在进程内存中，不写 Storage，不建立图片或语音的持久化文件缓存。
- 每次图片预取或语音播放尝试最多强制刷新一次签名并重试一次。
- 一次播放尝试包含签名请求、可能的一次刷新和媒体播放，总超时仍为 90 秒。
- 不新增数据库模型和 migration。
- 上传、平台审核和正式上架分别报告实际状态。

工程约束：保留已有 CSRF、权限与其他会话代码；当前任务在已创建的 .worktrees/game-difficulty-704 内执行。开始执行时核对最新远端，不覆盖根工作区的未提交文件。计划编写阶段不执行下面的代码、上传或提交步骤。执行阶段沿用本会话已有发布授权，提交使用明确文件列表，不暂存 node_modules 符号链接或其他任务文档。

## 文件职责与依赖

| 任务 | 主要文件 | 可独立验收结果 |
| --- | --- | --- |
| 1 | miniapp/scripts/staticAssets.mjs；新增前后端版本清单 | 同一构建产生一致且不可覆盖的版本数据 |
| 2 | 新增 backend/apps/common/miniapp_signed_assets.py、patient_app/static_asset_views.py；配置、路由、限流 | 精确签名与匿名边界、错误合同可验证 |
| 3 | 新增 miniapp/src/assets/signedAssetManifest.ts；api/client.ts | 校验、并发、TTL、错误分型与缓存独立可测 |
| 4 | gameImagePreloader.ts、gameImageAssets.ts、游戏生命周期测试 | 三并发预取、一次刷新、就绪门禁 |
| 5 | instructionAudioManifest.ts；新增 instructionPlayback.ts；motion-training/index.tsx | 异步签名、取消、重播和总超时 |
| 6 | 新增后端签名素材验收模块与管理命令 | 检查正文与私有访问，输出不含签名 |
| 7 | 两阶段部署、微信构建上传、文档执行记录 | 区分每项实际发布结果 |

依赖：Task 1 → Task 2；Task 1 → Task 3；Tasks 2/3 → Tasks 4/5；Tasks 1/2 → Task 6；全部任务 → Task 7。Task 4 与 Task 5 不并发修改共享文件。不要把七个任务拆成独立子项目，它们属于同一条素材访问链路。

---

## Task 1：统一生成清单，登记不可变后端版本

**Files**
- Modify: miniapp/scripts/staticAssets.mjs
- Modify: miniapp/scripts/build-static-assets.mjs
- Modify/Test: miniapp/scripts/staticAssets.test.mjs
- Create: miniapp/src/assets/staticAssetManifest.generated.ts
- Create: backend/apps/common/miniapp_static_asset_manifests/v-3aafe09211fd.json
- Create: backend/apps/common/miniapp_static_asset_registry.py
- Create/Test: backend/apps/common/tests/test_miniapp_static_asset_registry.py
- Modify: backend/pyproject.toml（声明 JSON package-data）

**Interfaces**
- 扩展 buildStaticAssets 参数为 { projectRoot, outputRoot, check, backendManifestRoot? }；默认后端目录取项目父目录下 backend/apps/common/miniapp_static_asset_manifests。
- 现有 GAME_IMAGE_ASSET_PATHS 与 MOTION_INSTRUCTION_AUDIO_ASSET_PATHS 的导出继续保留。
- 新增 STATIC_ASSET_MANIFEST 常量，数据为 { assetVersion, entries }，结构与当前 manifest.json 相同。
- 新增后端 REGISTERED_STATIC_ASSET_MANIFESTS: dict[str, Path] 和 load_registered_static_assets(version: str) -> dict。未知版本抛 KeyError，已登记内容损坏抛 ValueError，调用方不能传目录。

- [ ] **Step 1：补生成与不可变输出的红测。**

测试 fixture 必须传自身临时 backendManifestRoot，防止测试写入真实后端目录。现有 fixtureOptions 增加：

~~~js
backendManifestRoot: join(fixtureRoot, 'backend-manifests')
~~~

在同一 describe 中新增测试，使用现有 readFile、writeFile、buildStaticAssets：

~~~js
it('生成前后端一致的完整清单且拒绝覆盖后端版本', async () => {
  const options = fixtureOptions()
  const result = await buildStaticAssets(options)
  const serverPath = join(options.backendManifestRoot, result.assetVersion + '.json')
  const original = await readFile(serverPath, 'utf8')
  expect(JSON.parse(original)).toEqual({
    assetVersion: result.assetVersion, entries: result.entries,
  })
  const clientText = await readFile(
    join(fixtureRoot, 'src/assets/staticAssetManifest.generated.ts'), 'utf8',
  )
  expect(clientText).toContain(JSON.stringify(result.assetVersion))
  for (const entry of result.entries) expect(clientText).toContain(entry.sha256)
  try {
    await writeFile(serverPath, '{"assetVersion":"corrupted","entries":[]}')
    await expect(buildStaticAssets(options)).rejects.toThrow(/drift/i)
    await expect(buildStaticAssets({ ...options, check: true })).rejects.toThrow(/drift/i)
  } finally {
    await writeFile(serverPath, original)
  }
})
~~~

后端测试读取实际生成清单，断言 23 项唯一 key、规范媒体类型及带哈希路径。增加恶意版本参数：

~~~python
import pytest
from apps.common.miniapp_static_asset_registry import load_registered_static_assets

@pytest.mark.parametrize("version", [
    "../training", "/etc/passwd", "v-000000000000", "v-3aafe09211fd/../x",
])
def test_unregistered_version_is_not_a_filesystem_path(version):
    with pytest.raises(KeyError):
        load_registered_static_assets(version)

def test_current_manifest_contains_only_product_assets():
    result = load_registered_static_assets("v-3aafe09211fd")
    assert result["assetVersion"] == "v-3aafe09211fd"
    assert len(result["entries"]) == 23
    assert len({entry["key"] for entry in result["entries"]}) == 23
    assert {entry["kind"] for entry in result["entries"]} == {
        "game-image", "motion-instruction-audio",
    }
~~~

- [ ] **Step 2：运行新增测试并确认缺少生成文件/模块导致失败。**

~~~sh
cd miniapp
npm run test -- scripts/staticAssets.test.mjs
cd ../backend
python -m pytest apps/common/tests/test_miniapp_static_asset_registry.py -q
~~~

- [ ] **Step 3：实现生成器与注册表。**

生成器使用同一次 buildEntries 的 manifest 字符串写后端 JSON，不重新扫描图片或重复生成哈希。写后端文件之前：

~~~js
await mkdir(backendManifestRoot, { recursive: true })
const backendPath = join(backendManifestRoot, assetVersion + '.json')
if (await exists(backendPath)) {
  await assertFileEquals(backendPath, manifest)
} else if (check) {
  throw new Error('Static asset output drift: missing backend manifest')
} else {
  await writeFile(backendPath, manifest, { flag: 'wx' })
}
~~~

同名并发创建收到 EEXIST 时重新校验正文；不覆盖。新增前端文件内容：

~~~js
const completeClientManifest =
  '// 此文件由 scripts/build-static-assets.mjs 自动生成，请勿手动修改。\n' +
  'export const STATIC_ASSET_MANIFEST = ' +
  JSON.stringify({ assetVersion, entries }, null, 2) + ' as const\n'
~~~

check 模式检查后端文件与三个前端清单；正常模式可以重写前端当前版本表，但不删除历史后端版本。后端注册表采用明确映射：

~~~python
MANIFEST_ROOT = Path(__file__).with_name("miniapp_static_asset_manifests")
REGISTERED_STATIC_ASSET_MANIFESTS = {
    "v-3aafe09211fd": MANIFEST_ROOT / "v-3aafe09211fd.json",
}
~~~

load_registered_static_assets 先在映射中查找，随后 json.loads；利用现有 CANONICAL_ASSET_SPECS 检查每个 key 对应 kind/contentType/extension、sizeBytes 为非负整数且不是 bool、sha256 满足小写 64 位十六进制，relativePath 严格等于 version/key.hash12.extension。检查缺项、重复项及 assetVersion；函数不调用七牛或数据库。

将下列 package-data 加入 backend/pyproject.toml，使源码镜像和打包安装均带 JSON：

~~~toml
[tool.setuptools.package-data]
"apps.common" = ["miniapp_static_asset_manifests/*.json"]
~~~

- [ ] **Step 4：生成当前真实版本、重跑测试和 check。**

~~~sh
cd miniapp
npm run build:static-assets
npm run check:static-assets
npm run test -- scripts/staticAssets.test.mjs
cd ../backend
python -m pytest apps/common/tests/test_miniapp_static_asset_registry.py -q
~~~

预期仍为 v-3aafe09211fd，无图片或语音正文变化；检查新增 JSON 恰为 23 项。

- [ ] **Step 5：提交该任务的代码、生成清单和测试。**

提交说明：feat(素材): 生成并登记前后端固定版本清单。仅暂存本任务 Files，不提交素材输出目录。

---

## Task 2：后端批量签名接口、限流与部署配置

**Files**
- Create: backend/apps/common/miniapp_signed_assets.py
- Create: backend/apps/patient_app/static_asset_views.py
- Modify: backend/apps/patient_app/urls.py
- Modify: backend/apps/patient_app/throttles.py
- Modify: backend/config/settings.py
- Modify: backend/config/environment.py
- Modify: deploy/docker-compose.prod.yml、deploy/env.production.example
- Create/Test: backend/apps/patient_app/tests/test_static_asset_manifest_api.py
- Create/Test: backend/apps/patient_app/tests/test_static_asset_manifest_throttle.py
- Modify/Test: backend/tests/test_settings.py、backend/tests/test_deploy_workflow.py

**Interfaces**
- build_signed_static_asset_manifest(version: str, *, now: int | None = None) -> dict
- validate_miniapp_static_asset_settings(base_url: str, ttl: str | int) -> tuple[str, int]
- StaticAssetManifestView: GET /api/patient-app/static-assets/?version=...
- MiniappStaticAssetRateThrottle，配置：
  MINIAPP_STATIC_ASSET_BASE_URL；
  MINIAPP_STATIC_ASSET_URL_TTL_SECONDS=600；
  MINIAPP_STATIC_ASSET_RATE_LIMIT_REDIS_URL；
  MINIAPP_STATIC_ASSET_RATE_LIMIT_REQUESTS=60；
  MINIAPP_STATIC_ASSET_RATE_LIMIT_WINDOW_SECONDS=60。

- [ ] **Step 1：写接口的固定范围、期限与错误红测。**

在接口测试文件定义以下 autouse fixture（独立限流测试文件不用它），导入 pytest 与 urllib.parse 的 urlsplit、parse_qs：

~~~python
@pytest.fixture(autouse=True)
def static_asset_settings(settings, monkeypatch):
    settings.QINIU_ACCESS_KEY = "test-access-key"
    settings.QINIU_SECRET_KEY = "test-secret-key"
    settings.MINIAPP_STATIC_ASSET_BASE_URL = "https://cdn.example.com/motioncare/static-assets"
    settings.MINIAPP_STATIC_ASSET_URL_TTL_SECONDS = 600
    monkeypatch.setattr(
        "apps.patient_app.throttles.MiniappStaticAssetRateThrottle.allow_request",
        lambda self, request, view: True,
    )
~~~

核心断言：

~~~python
def test_anonymous_manifest_contains_exact_signed_objects(client, monkeypatch):
    monkeypatch.setattr("apps.common.miniapp_signed_assets.time.time", lambda: 1_800_000_000)
    response = client.get("/api/patient-app/static-assets/", {"version": "v-3aafe09211fd"})
    assert response.status_code == 200
    data = response.json()
    assert data["issued_at"] == 1_800_000_000
    assert data["expires_at"] == 1_800_000_600
    assert len(data["assets"]) == 23
    assert response["Cache-Control"] == "no-store"
    for asset in data["assets"]:
        url = urlsplit(asset["url"])
        params = parse_qs(url.query)
        assert url.scheme == "https"
        assert url.netloc == "cdn.example.com"
        assert url.path == "/motioncare/static-assets/" + asset["relative_path"]
        assert params["e"] == ["1800000600"]
        assert len(params["token"]) == 1

@pytest.mark.parametrize("query", [
    "", "version=v-3aafe09211fd&version=v-3aafe09211fd",
    "version=v-3aafe09211fd&key=training/video.mp4",
    "version=../private", "url=https://example.com/private",
])
def test_rejects_noncanonical_queries(client, query):
    assert client.get("/api/patient-app/static-assets/?" + query).status_code == 400
~~~

导入 urllib.parse 的 urlsplit、parse_qs；参数化增加 unknown version 404、POST/HEAD/OPTIONS 405。用 mock signer 抛出包含密钥与签名的异常，断言 503 正文及 caplog 均不含异常原文。已登录请求返回与匿名相同 key 集合；PatientAppMeView 仍需真实鉴权。

限流测试复制现有 demo throttle 的 FakeRedis（或抽取纯测试 helper），使用本视图真实 throttle，60 次 200、第 61 次 429；伪造 X-Forwarded-For 不绕过；Redis 异常 503；429 时 signer 调用次数不增加。

- [ ] **Step 2：运行红测。**

~~~sh
cd backend
python -m pytest apps/patient_app/tests/test_static_asset_manifest_api.py apps/patient_app/tests/test_static_asset_manifest_throttle.py -q
~~~

- [ ] **Step 3：实现精确签名，不引入任意 Key 签名能力。**

签名模块消费 Task 1 registry，导入现有 apps.training.qiniu.private_download_url：

~~~python
def build_signed_static_asset_manifest(version, *, now=None):
    manifest = load_registered_static_assets(version)
    base = settings.MINIAPP_STATIC_ASSET_BASE_URL
    if not base or not settings.QINIU_ACCESS_KEY or not settings.QINIU_SECRET_KEY:
        raise ValueError("固定素材签名配置不可用")
    issued_at = int(time.time()) if now is None else now
    expires_at = issued_at + settings.MINIAPP_STATIC_ASSET_URL_TTL_SECONDS
    assets = []
    for entry in manifest["entries"]:
        assets.append({
            "key": entry["key"],
            "relative_path": entry["relativePath"],
            "url": private_download_url(
                base + "/" + entry["relativePath"], expires_at=expires_at,
            ),
            "content_type": entry["contentType"],
            "size_bytes": entry["sizeBytes"],
            "sha256": entry["sha256"],
        })
    return {
        "asset_version": version, "issued_at": issued_at,
        "expires_at": expires_at, "assets": assets,
    }
~~~

视图 authentication_classes=[]、permission_classes=[AllowAny]、http_method_names=["get"]。依次检查 query keys 恰为 {"version"}、getlist 长度为 1、re.fullmatch("v-[a-f0-9]{12}", version)，否则 400；先判断 REGISTERED_STATIC_ASSET_MANIFESTS 成员再构建，未知为 404。签名构建异常整体返回 {"detail":"训练素材暂时不可用，请稍后重试"}、503，不能输出 exc。覆盖 finalize_response 设置全部响应 no-store；DRF APIException 保留规范状态，未知异常脱敏。

- [ ] **Step 4：接入配置与现有 Redis 限流。**

validate_miniapp_static_asset_settings 使用 urlsplit：空 base 允许启动但接口 503；非空必须 HTTPS、有 hostname、无凭据/query/fragment/backslash，pathname 去尾斜杠后恰为 /motioncare/static-assets，拒绝显式端口；TTL 必须整数 120–3600。异常只写字段名，不回显配置。正数限流参数沿用当前 settings 的 _positive_int_env。

新增 throttle 子类引用 RedisFixedWindowRateThrottle，namespace 为 miniapp-static-assets；unavailable_exception_class 的 503 提示为“训练素材服务繁忙，请稍后重试”。

Compose 在 backend-environment 中加入非密钥配置，base 默认现有正式地址，TTL/请求数/窗口为 600/60/60，Redis URL 使用现有 backend-redis-url anchor。env.production.example 同步。不得替换 QINIU_DOWNLOAD_DOMAIN 或其他视频变量；不得改现有 H5 缺少变量时保留旧镜像的行为。

配置测试参数覆盖 TTL 119/120/600/3600/3601、非整数、HTTP、错误路径、用户名、query、fragment；部署测试验证 Compose 能向后端传入新增配置且仍保留视频变量。

- [ ] **Step 5：跑本任务与现有权限测试后提交。**

~~~sh
cd backend
python -m pytest apps/patient_app/tests/test_static_asset_manifest_api.py apps/patient_app/tests/test_static_asset_manifest_throttle.py tests/test_settings.py tests/test_deploy_workflow.py apps/training/tests/test_motion_analysis.py -q
python -m ruff check .
~~~

本机已有 QINIU_BUCKET 覆盖默认值时，以 QINIU_BUCKET=motioncare-training 运行测试，不修改生产桶名。提交说明：feat(素材): 提供固定清单的私有签名接口。

---

## Task 3：客户端签名校验、并发缓存与错误分型

**Files**
- Create: miniapp/src/assets/signedAssetManifest.ts
- Create/Test: miniapp/src/assets/signedAssetManifest.test.ts
- Create/Test helper: miniapp/src/assets/signedAssetFixtures.test-helper.ts
- Modify/Test: miniapp/src/api/client.ts、miniapp/src/api/client.test.ts

**Interfaces**
~~~ts
export type StaticAssetKey = typeof STATIC_ASSET_MANIFEST.entries[number]['key']
export type SignedAssetManifest = {
  assetVersion: string
  issuedAt: number
  expiresAt: number
  urls: Record<StaticAssetKey, string>
}
export class SignedAssetManifestError extends Error {
  constructor(public readonly retryable: boolean) {
    super('训练素材暂时不可用，请稍后重试')
  }
}
export function parseSignedAssetManifest(value: unknown): SignedAssetManifest
export function fetchSignedAssetManifest(options?: {
  forceRefresh?: boolean
}): Promise<SignedAssetManifest>
export function mayRefreshSignedAssets(error: unknown): boolean
~~~

publicRequest 的返回类型保持不变；仅对 HTTP 错误新增 PublicRequestError(message: string, statusCode: number)，继承 Error。保留 safeApiErrorMessage，不清 token、不跳转登录。普通 request 的 401/403 行为保持原样。

- [ ] **Step 1：写完整有效 fixture 与缓存红测。**

fixture 文件消费 Task 1 的 STATIC_ASSET_MANIFEST，输出完整 23 项，不调用生产 parser：

~~~ts
export function signedAssetFixture(issuedAt = 1_800_000_000, token = 'fixture:signature') {
  return {
    asset_version: STATIC_ASSET_MANIFEST.assetVersion,
    issued_at: issuedAt, expires_at: issuedAt + 600,
    assets: STATIC_ASSET_MANIFEST.entries.map((entry) => ({
      key: entry.key, relative_path: entry.relativePath,
      content_type: entry.contentType, size_bytes: entry.sizeBytes, sha256: entry.sha256,
      url: 'https://cdn.example.com/motioncare/static-assets/' + entry.relativePath +
        '?e=' + (issuedAt + 600) + '&token=' + encodeURIComponent(token),
    })),
  }
}
~~~

测试模块明确初始化 mock；保留实际错误类以参数化返回状态。fixture helper 导入 ./staticAssetManifest.generated 的 STATIC_ASSET_MANIFEST。测试 setup 如下：

~~~ts
const api = vi.hoisted(() => ({ publicRequest: vi.fn() }))
vi.mock('../api/client', async (importOriginal) => ({
  ...await importOriginal<typeof import('../api/client')>(),
  publicRequest: api.publicRequest,
}))
beforeEach(() => {
  vi.resetModules()
  api.publicRequest.mockReset()
  vi.useFakeTimers()
  vi.setSystemTime(0)
  vi.stubEnv('TARO_APP_ASSET_BASE_URL', 'https://cdn.example.com/motioncare/static-assets')
})
afterEach(() => { vi.useRealTimers(); vi.unstubAllEnvs() })
~~~

核心缓存用例：

~~~ts
it('同版本请求合并，540 秒后更新签名', async () => {
  api.publicRequest.mockResolvedValue(signedAssetFixture())
  const { fetchSignedAssetManifest } = await import('./signedAssetManifest')
  await Promise.all([fetchSignedAssetManifest(), fetchSignedAssetManifest()])
  expect(api.publicRequest).toHaveBeenCalledTimes(1)
  vi.setSystemTime(539_000)
  await fetchSignedAssetManifest()
  expect(api.publicRequest).toHaveBeenCalledTimes(1)
  vi.setSystemTime(540_000)
  await fetchSignedAssetManifest()
  expect(api.publicRequest).toHaveBeenCalledTimes(2)
})
~~~

该用例 beforeEach 的客户端时钟设为 0，刻意不同于服务端时间。另用受控 Promise 覆盖 30 秒网络耗时扣除、时钟回拨、第一次拒绝后第二次成功、旧请求晚于强制刷新返回、并发 forceRefresh 合并。

参数化变异 fixture：缺项、重复 key、错误版本/sha/size/type/path、HTTP、跨域、路径穿越、userinfo、fragment、缺 token、重复 e/token、未知 query、e 不匹配、非整数时戳、TTL<120 或 >3600。全部必须拒绝且错误不包含 URL。publicRequest 测试覆盖 404/429 有 statusCode、错误脱敏且不读写 token。

- [ ] **Step 2：运行红测。**

~~~sh
cd miniapp
npm run test -- src/assets/signedAssetManifest.test.ts src/api/client.test.ts
~~~

- [ ] **Step 3：实现响应 parser 和 HTTP 状态分型。**

parser 先检查普通对象、整数 issued_at/expires_at、120≤差值≤3600，再检查版本和 23 项。以编译清单 key 查找 expected，逐项精确比较；禁止未知或重复 key。使用 staticAssetUrl(expected.relativePath) 构造期望的无签名 URL，仅用于比较 origin/pathname，不拿它下载。

对带签名地址执行 URL 解析；检查 HTTPS、origin/pathname 与 expected 一致、无 userinfo/hash/backslash；query keys 恰为 e/token 且各一次，e 为 expires_at 的十进制字符串，token 非空且具备七牛 AK:signature 形式。最后返回 urls 映射，不存原始响应的其他字段。

mayRefreshSignedAssets 对 SignedAssetManifestError 返回其 retryable；HTTP 400/401/403/404/405/429 和 parser 错误不可自动重试，网络错误及 5xx 可重试。图片/播放器自身下载错误由各消费者决定尝试一次刷新；不得把取消当网络错误。

- [ ] **Step 4：实现内存缓存，隔离迟到响应。**

模块状态由 cached（有效已完成清单）和 inflight（generation、startedAt、force、promise）组成。forceRefresh 使旧普通请求失效；已有同代强制刷新则复用。每次新请求递增 generation；旧请求成功或失败都不能修改新代状态。

缓存有效截止时间：

~~~ts
const ttlMs = (manifest.expiresAt - manifest.issuedAt) * 1000
const usableUntil = startedAt + ttlMs - 60_000
if (Date.now() < startedAt || Date.now() >= usableUntil) {
  throw new SignedAssetManifestError(true)
}
~~~

记录最近一次观察的客户端时间；若 now 小于它，清理 cached 并使旧 inflight 失效。返回有效清单时同时更新观察时间。缓存命中必须 now>=startedAt 且 now<usableUntil。请求开始时调用：

~~~ts
publicRequest<unknown>(
  '/patient-app/static-assets/?version=' +
  encodeURIComponent(STATIC_ASSET_MANIFEST.assetVersion),
)
~~~

catch 只在本次仍为当前 generation 时清理自己的 inflight；返回新的脱敏 SignedAssetManifestError，禁止向页面传播原始下载 URL。不改动存储或登录态。

- [ ] **Step 5：测试通过后提交。**

~~~sh
cd miniapp
npm run test -- src/assets/signedAssetManifest.test.ts src/api/client.test.ts
~~~

提交说明：feat(素材): 校验并缓存临时签名清单。


---

## Task 4：游戏图片接入签名，保留三并发与开始门禁

**Files**
- Modify: miniapp/src/pages/game-session/gameImagePreloader.ts
- Modify: miniapp/src/pages/game-session/gameImageAssets.ts
- Modify/Test: miniapp/src/pages/game-session/gameImagePreloader.test.ts
- Modify/Test: miniapp/src/pages/game-session/gameImageAssets.test.ts
- Modify/Test: miniapp/src/pages/game-session/index.integration.test.tsx

**Interfaces**
- 消费 Task 3 的 fetchSignedAssetManifest、SignedAssetManifest、mayRefreshSignedAssets。
- GameImagePreloadOptions 增加可选 loadSignedManifest: typeof fetchSignedAssetManifest，默认真实实现；原调用方无需传新参数。
- gameImageRemoteUrl(key: GameImageKey, manifest: SignedAssetManifest): string，从 manifest.urls 取已校验地址。
- preloadGameImages 的返回类型、取消错误、进度、临时路径和页面门禁不变。

- [ ] **Step 1：加入有界刷新红测，替换原匿名地址 fixture。**

现有测试的 beforeEach 将基础地址设为 https://cdn.example.com/motioncare/static-assets，并使用 Task 3 的完整 fixture 经 parser 生成 manifest。原受控下载 helper 的 sourceToKey 用 gameImageRemoteUrl(key, manifest) 建表。核心新增测试：

~~~ts
import { parseSignedAssetManifest } from '../../assets/signedAssetManifest'
import { signedAssetFixture } from '../../assets/signedAssetFixtures.test-helper'

it('下载失败只刷新一次并返回临时文件', async () => {
  const manifest = parseSignedAssetManifest(signedAssetFixture())
  const loadSignedManifest = vi.fn().mockResolvedValue(manifest)
  const getImageInfo = vi.fn()
    .mockRejectedValueOnce(new Error('下载失败'))
    .mockResolvedValueOnce({ path: '/tmp/sun.webp' })
  const paths = await preloadGameImages(['pattern_sun'], {
    getImageInfo, loadSignedManifest, isCurrent: () => true, onProgress: vi.fn(),
  })
  expect(paths.pattern_sun).toBe('/tmp/sun.webp')
  expect(loadSignedManifest.mock.calls).toEqual([[], [{ forceRefresh: true }]])
  expect(getImageInfo).toHaveBeenCalledTimes(2)
})

it('没有图片时不获取清单', async () => {
  const loadSignedManifest = vi.fn()
  const onProgress = vi.fn()
  await preloadGameImages([], {
    getImageInfo: vi.fn(), loadSignedManifest, isCurrent: () => true, onProgress,
  })
  expect(loadSignedManifest).not.toHaveBeenCalled()
  expect(onProgress).toHaveBeenLastCalledWith({ completed: 0, total: 0, percent: 100 })
})
~~~

补受控 Promise 用例：清单未返回就退出时不下载；下载途中退出时不更新进度；连续两次下载失败后结束；429/404 不刷新；多个下载同时失败仍只一次刷新；旧一轮下载全部结束前不开新一轮，峰值并发保持 3；已成功图片不重复下载。页面测试保留失败重试/返回、开始按钮门禁，并加入图片就绪后推进 600 秒不重新预取、不重新出题。

- [ ] **Step 2：运行红测。**

~~~sh
cd miniapp
npm run test -- src/pages/game-session/gameImagePreloader.test.ts src/pages/game-session/gameImageAssets.test.ts src/pages/game-session/index.integration.test.tsx
~~~

- [ ] **Step 3：改为受控签名地址和两次尝试。**

~~~ts
export function gameImageRemoteUrl(
  key: GameImageKey, manifest: SignedAssetManifest,
): string {
  return manifest.urls[key]
}
~~~

删除 gameImageAssets 中只用于生成匿名地址的 staticAssetUrl 导入，保留 GeneratedGameImageKey 类型和四个游戏的 key 表。预加载先去重并发出 0 进度，空集合立即返回。外层最多两次尝试；每轮先 assertCurrent，再 await loadSignedManifest，返回后再次 assertCurrent。第二轮调用 { forceRefresh: true }。

现有 worker 改为从尚未成功的 key 队列取项，调用 gameImageRemoteUrl(key, manifest)。保留 await 下载前后的 assertCurrent。单轮出现第一个错误即设置 terminal，阻止领取新任务或写入旧结果。用 Promise.allSettled 等本轮 worker 结束，再决定重试，防止重试与旧下载叠加超过三个。完成数从 loadedPaths 中的成功项计数，进度只增不减。

清单请求 catch 使用 mayRefreshSignedAssets；下载失败允许刷新一次；取消始终直接抛 GameImagePreloadCancelledError。外层尝试次数同时限制清单与下载重试，不能各自刷新一次。全部成功后再次 assertCurrent 返回；终局错误只传脱敏消息。继续由现有页面 generation 控制重试按钮及游戏计时，签名缓存到期不订阅、不清空 loadedPaths。

- [ ] **Step 4：运行本任务测试，确认旧游戏行为通过后提交。**

执行 Step 2 的同一组命令。仅暂存本任务 Files，提交说明：feat(小游戏): 使用签名预取图片并限制刷新次数。

---

## Task 5：动作说明异步取签名，统一播放生命周期

**Files**
- Modify: miniapp/src/features/motion-training/instructionAudioManifest.ts
- Modify/Test: miniapp/src/features/motion-training/instructionAudioManifest.test.ts
- Create: miniapp/src/features/motion-training/instructionPlayback.ts
- Create/Test: miniapp/src/features/motion-training/instructionPlayback.test.ts
- Modify: miniapp/src/pages/motion-training/index.tsx
- Modify/Test: miniapp/src/pages/shoulder-press/pages.test.tsx

**Interfaces**
- hasMotionInstructionAudio(sourceKey: unknown): sourceKey is MotionSourceKey，同步纯判断。
- getMotionInstructionAudioSrc(sourceKey: unknown, options?: { forceRefresh?: boolean }): Promise<string | undefined>，未知动作不发请求。
- createInstructionPlayback(options?: InstructionPlaybackOptions): InstructionPlayback。
- 复用 alertAudio.ts 的 MotionTrainingAudioPlayer；不改网络告警的 15 秒超时。

~~~ts
export type InstructionPlaybackResult = 'played' | 'failed' | 'cancelled'
export type InstructionPlayback = {
  play: (sourceKey: unknown) => Promise<InstructionPlaybackResult>
  stop: () => void
  dispose: () => void
}
export type InstructionPlaybackOptions = {
  player?: MotionTrainingAudioPlayer
  resolveSource?: typeof getMotionInstructionAudioSrc
  timeoutMs?: number
}
~~~

- [ ] **Step 1：写异步取地址和取消/总超时红测。**

manifest 测试 mock 签名客户端：五个正式动作返回对应签名；未知动作返回 undefined 且不发请求；仅导入模块不发请求；hasMotionInstructionAudio 不触发 Promise 或网络。

controller 测试使用 vi.useFakeTimers，afterEach 恢复。取消核心用例：

~~~ts
it('停止后迟到的签名不会启动播放器', async () => {
  let release!: (src: string) => void
  const resolveSource = vi.fn(() => new Promise<string>((resolve) => { release = resolve }))
  const player = { play: vi.fn(), stop: vi.fn(), dispose: vi.fn() }
  const controller = createInstructionPlayback({ player, resolveSource })
  const result = controller.play('motion-resistance-shoulder-press')
  controller.stop()
  await expect(result).resolves.toBe('cancelled')
  release('https://cdn.example.com/delayed.m4a?e=1&token=test')
  await Promise.resolve()
  expect(player.play).not.toHaveBeenCalled()
})

it('90 秒包含等待签名时间，超时后不重试', async () => {
  const resolveSource = vi.fn(() => new Promise<string>(() => {}))
  const player = { play: vi.fn(), stop: vi.fn(), dispose: vi.fn() }
  const controller = createInstructionPlayback({ player, resolveSource })
  const result = controller.play('motion-resistance-shoulder-press')
  await vi.advanceTimersByTimeAsync(90_000)
  await expect(result).resolves.toBe('failed')
  expect(resolveSource).toHaveBeenCalledTimes(1)
  expect(player.play).not.toHaveBeenCalled()
})
~~~

再覆盖首播 false 后 forceRefresh 一次成功；两次 false 返回 failed；签名 429/404 直接失败；60 秒取签名后播放只能再用 30 秒；连续 play 取消前次；dispose 后迟到结果无副作用。页面现有测试调整原同步 mock，覆盖自动一次、重播、隐藏/切动作、签名失败显示文字且仍可开始训练。

- [ ] **Step 2：运行红测。**

~~~sh
cd miniapp
npm run test -- src/features/motion-training/instructionAudioManifest.test.ts src/features/motion-training/instructionPlayback.test.ts src/pages/shoulder-press/pages.test.tsx
~~~

- [ ] **Step 3：实现异步 manifest。**

~~~ts
export function hasMotionInstructionAudio(sourceKey: unknown): sourceKey is MotionSourceKey {
  return isOfficialMotionSourceKey(sourceKey)
}

export async function getMotionInstructionAudioSrc(
  sourceKey: unknown, options?: { forceRefresh?: boolean },
): Promise<string | undefined> {
  if (!hasMotionInstructionAudio(sourceKey)) return undefined
  const manifest = await fetchSignedAssetManifest(options)
  return manifest.urls[sourceKey]
}
~~~

删除模块级 MOTION_INSTRUCTION_AUDIO_SRC，不在渲染或条件判断中调用异步 getter；全部引用点改用 hasMotionInstructionAudio。生成的相对路径表仍可保留供一致性检查。

- [ ] **Step 4：实现控制器和页面接入。**

控制器默认创建独立 createMotionTrainingAudioPlayer({ timeoutMs: 90_000 })。每次 play 先 stop 前次，再新建 operation（settled、timer、resolve），active 指向该 operation；启动时即创建唯一总计时器。finish(result) 仅一次执行，先标 settled 并清 timer，只有 active 仍为本次才清空 active，然后停止播放器并 resolve。stop 调 finish('cancelled')；总超时调 finish('failed')。dispose 先 stop 再 player.dispose，之后的 play 返回 cancelled。

异步执行最多两轮，轮内代码顺序：

~~~ts
for (let attempt = 0; attempt < 2; attempt += 1) {
  if (operation.settled) return
  try {
    const src = await resolveSource(sourceKey, attempt === 0 ? undefined : { forceRefresh: true })
    if (operation.settled) return
    if (!src) { finish('failed'); return }
    const played = await player.play(src)
    if (operation.settled) return
    if (played) { finish('played'); return }
  } catch (error) {
    if (operation.settled) return
    if (!mayRefreshSignedAssets(error)) { finish('failed'); return }
  }
}
finish('failed')
~~~

上述 operation、finish、resolveSource、player 均在同一 play 闭包内按前段定义；异步执行本身的返回值不作为公开 Promise。公开 Promise 由 finish 结算，因此取消/超时即使底层请求未返回也能及时结束。finish 必须先标 settled 再 stop，避免停止回调引起重试。结束后不取消共用签名请求。

页面 ref 改为 InstructionPlayback，playInstruction 在 await 控制器前记录 page/source/play generation，返回后仍校验可见性及代次；仅 failed 显示“语音播放失败，请阅读文字说明”。原自动一次标记在取签名前设置；隐藏、动作切换、开始训练和卸载均 stop/dispose，沿用现有跳转与按钮排版。

- [ ] **Step 5：测试通过后提交。**

执行 Step 2，并运行 src/features/motion-training/alertAudio.test.ts 保证网络告警不回归。仅暂存本任务 Files，提交说明：feat(语音): 播放前获取签名并隔离离页回调。

---

## Task 6：新增私有素材验收命令，验证正文与过期访问

**Files**
- Create: backend/apps/common/miniapp_signed_asset_verification.py
- Create: backend/apps/common/management/commands/verify_miniapp_signed_assets.py
- Create/Test: backend/apps/common/tests/test_miniapp_signed_asset_verification.py
- Preserve: miniapp/scripts/verify-static-assets.mjs（旧公开模式保留）

**Interfaces**

~~~python
@dataclass(frozen=True)
class VerificationResponse:
    status: int
    content_type: str
    body: bytes

@dataclass(frozen=True)
class VerifiedSignedAsset:
    key: str
    size_bytes: int
    sha256: str

class SignedAssetVerificationError(Exception):
    pass

def fetch_verification_response(url: str) -> VerificationResponse:
    """20 秒超时，禁止自动重定向，HTTP 错误返回状态，不泄露 URL。"""

def verify_signed_static_assets(
    source_root: Path,
    api_base_url: str,
    *,
    fetch: Callable[[str], VerificationResponse] = fetch_verification_response,
) -> list[VerifiedSignedAsset]:
    """固定 23 项正文验收及同对象无签名、篡改、过期拒绝检查。"""
~~~

- [ ] **Step 1：编写不联网的验收红测。**

测试复用现有纯函数 static_asset_fixture，转换为格式合法的测试版本；不读取真实生产凭据。测试模块导入 json、time、pytest、Path、urlsplit、urlencode、private_download_url，以及本任务的函数和数据类。fixture 不调用生产签名清单构建函数，独立组装预期响应：

~~~python
from apps.common.tests.test_miniapp_static_assets import static_asset_fixture

@pytest.fixture
def verification_fixture(tmp_path, settings, monkeypatch):
    old_root = static_asset_fixture(tmp_path)
    root = old_root.rename(tmp_path / "v-000000000001")
    manifest = json.loads((root / "manifest.json").read_text())
    manifest["assetVersion"] = root.name
    for entry in manifest["entries"]:
        entry["relativePath"] = root.name + "/" + Path(entry["relativePath"]).name
    manifest_path = root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest))
    monkeypatch.setattr(
        "apps.common.miniapp_static_asset_registry.REGISTERED_STATIC_ASSET_MANIFESTS",
        {root.name: manifest_path},
    )
    settings.QINIU_ACCESS_KEY = "test-ak"
    settings.QINIU_SECRET_KEY = "test-sk"
    settings.MINIAPP_STATIC_ASSET_BASE_URL = "https://cdn.example.com/motioncare/static-assets"
    issued_at = int(time.time())
    payload = {
        "asset_version": root.name, "issued_at": issued_at,
        "expires_at": issued_at + 600, "assets": [],
    }
    bodies = {}
    for entry in manifest["entries"]:
        url = private_download_url(
            settings.MINIAPP_STATIC_ASSET_BASE_URL + "/" + entry["relativePath"],
            expires_at=issued_at + 600,
        )
        payload["assets"].append({
            "key": entry["key"], "relative_path": entry["relativePath"], "url": url,
            "content_type": entry["contentType"], "size_bytes": entry["sizeBytes"],
            "sha256": entry["sha256"],
        })
        bodies[url] = VerificationResponse(
            200, entry["contentType"], (root / Path(entry["relativePath"]).name).read_bytes(),
        )
    api_url = "https://api.example.com/api/patient-app/static-assets/?" + urlencode(
        {"version": root.name},
    )
    bodies[api_url] = VerificationResponse(
        200, "application/json", json.dumps(payload).encode(),
    )
    def responses(url):
        return bodies.get(url, VerificationResponse(401, "application/json", b"{}"))
    return root, responses
~~~

篡改测试在 responses 外包一层，仅替换相应 URL 的返回值；不改测试清单生成器，以免让预期与实现一起犯错。

~~~python
def test_verifies_content_and_rejects_unsigned_access(verification_fixture):
    root, responses = verification_fixture
    calls = []

    def fetch(url):
        calls.append(url)
        return responses(url)

    results = verify_signed_static_assets(root, "https://api.example.com/api", fetch=fetch)
    assert len(results) == 23
    assert all(result.size_bytes > 0 for result in results)
    assert len(calls) >= 27  # 接口、23 项正文、三种拒绝检查
~~~

参数化模拟：任一正文损坏、字节数错误、类型不符、302、签名指向其他来源、少一项、异常版本、匿名200、篡改200、过期200均抛 SignedAssetVerificationError。用 capsys/caplog 检查异常和命令输出不包含完整 URL 或 token。Expired 测试由真实测试签名函数生成过期URL，不以“乱造一个 token”替代过期检查。

- [ ] **Step 2：运行红测。**

~~~sh
cd backend
python -m pytest apps/common/tests/test_miniapp_signed_asset_verification.py -q
~~~

- [ ] **Step 3：实现本地校验、受控下载与拒绝验收。**

先调用 validate_miniapp_static_assets(source_root)，读取并核对本地版本与 load_registered_static_assets。api_base_url 必须绝对 HTTPS、无 userinfo/query/fragment、路径以 /api 结束。请求地址：

~~~python
manifest_url = (
    api_base_url.rstrip("/") + "/patient-app/static-assets/?version=" +
    quote(asset_version, safe="")
)
~~~

使用 urllib.request.OpenerDirector 和禁止重定向的 HTTPRedirectHandler（redirect_request 返回 None）；HTTPError 转为 VerificationResponse，其他网络异常抛固定脱敏错误并 from None。请求超时 20 秒。真实 fetch 最多读取 32 MiB+1，超过 32 MiB 抛脱敏错误；内容验证时检查精确 size。签名接口正文另检查不能超过 256 KiB。

在任何下载前核对接口字段、版本、23 keys、metadata、签名来源路径、e/token 与共同期限，规则与 Task 3 一致，后端复用 Task 1 的已登记清单。对各 URL 调 fetch 并验证：

~~~python
if response.status != 200:
    raise SignedAssetVerificationError(asset.key + " 下载状态不正确")
if response.content_type.split(";", 1)[0].strip().lower() != asset.content_type:
    raise SignedAssetVerificationError(asset.key + " 媒体类型不一致")
if len(response.body) != asset.size_bytes:
    raise SignedAssetVerificationError(asset.key + " 字节数不一致")
if hashlib.sha256(response.body).hexdigest() != asset.sha256:
    raise SignedAssetVerificationError(asset.key + " SHA-256 不一致")
~~~

全部有效下载完成后，对首个真实对象依次检查去 query、替换 token 为明确无效值、用 private_download_url(unsigned_url, expires_at=int(time.time())-60) 生成的过期正确签名；均必须返回 401 或 403。有效对象已预热 CDN，所以能发现缓存绕过有效期。404 不能当作已存在对象的鉴权拒绝。任何失败中止并输出业务 key 和固定原因，禁止打印请求对象或底层异常。

命令参数 --source-root（Path，required）和 --api-base-url（required）；捕获 SignedAssetVerificationError 转 CommandError(str(error)) from None。成功逐行输出 key、字节数、SHA-256 已校验及三种拒绝检查通过。不要要求 public/immutable 缓存头，不修改 CDN 或空间配置。

- [ ] **Step 4：测试通过后提交。**

执行 Step 2，连同 apps/common/tests/test_miniapp_static_assets.py 回归上传不可覆盖。仅暂存本任务 Files，提交说明：test(素材): 增加私有下载完整性和过期验收命令。

---

## Task 7：完整验证、两阶段上线与微信 7.0.4 上传

**Files**
- Modify: 本计划、关联私有签名 spec、docs/superpowers/README.md、specs/patient-rehab-system/changelog.md（只追加执行事实）
- Runtime: miniapp/output/static-assets、miniapp/dist（不提交）
- External: 现有七牛固定素材前缀、GitHub 构建变量与部署流水线、微信开发版上传

**Interfaces**
- 消费 Tasks 1–6 已通过测试的代码和命令。
- 输入正式 API=https://mcare-wx.whestsun.com/api；素材 base=https://cdn.whestsun.com/motioncare/static-assets；微信版本=7.0.4。
- 输出分别记录后端部署、23 项素材验收、H5 更新、开发版上传、合法域名与真机结果。

- [ ] **Step 1：核对工作区与全量验证基线。**

在当前隔离工作区检查差异、最新远端和本任务提交，保留其他会话内容及两个 node_modules symlink。读取 verification-before-completion 与 requesting-code-review，按其要求审查已完成实现，处理实际问题后再验证。以下命令分目录执行，每次记录实际退出码和结果；任一步失败先诊断，不继续发布客户端。

~~~sh
git status --short
git fetch origin
git log --oneline -15
git diff --check
~~~

~~~sh
cd backend
QINIU_BUCKET=motioncare-training python -m pytest
python -m ruff check apps/common/miniapp_static_asset_registry.py apps/common/miniapp_signed_assets.py apps/common/miniapp_signed_asset_verification.py apps/patient_app/static_asset_views.py apps/patient_app/throttles.py
~~~

上述 QINIU_BUCKET 仅限测试进程：本地 .env 的 motioncare 与两项既有骨架测试默认不同。实际上传必须沿用真实 .env，不使用测试桶名。Python 使用项目现有 .venv 对应解释器；在执行前确认 sys.executable 与 pytest 可用性，不能使用系统缺依赖环境冒充测试失败。

~~~sh
cd frontend
npm run test
npm run lint
npm run build
~~~

~~~sh
cd miniapp
npm run build:static-assets
npm run check:static-assets
npm run test
TARO_APP_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets npm run build:weapp
npm run check:weapp-package-size
TARO_APP_CONFIG_ENV=production TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api TARO_APP_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets npm run build:h5
~~~

保留独立 TypeScript 检查的既有问题记录；若新增相关类型错误则修复，不能把构建通过写成独立类型检查通过。CI 本身仍跑既有完整校验。开发和 H5 构建顺序执行，最终待上传目录由 Step 5 的生产微信构建生成。

- [ ] **Step 2：生成并上传 23 项固定对象。**

先本地 check-only，再使用已配置的真实七牛凭据上传；不打印环境文件。source-root 固定为实际生成版本目录：

~~~sh
cd backend
python manage.py publish_miniapp_static_assets --source-root ../miniapp/output/static-assets/v-3aafe09211fd --check-only
python manage.py publish_miniapp_static_assets --source-root ../miniapp/output/static-assets/v-3aafe09211fd
~~~

确认输出每项为已上传或已存在。遇到对象正文/元数据冲突停止，不覆盖对象，不删除历史，不将空间公开。只读检查该前缀没有会删除在用素材的生命周期规则；若平台无权限查证，列为明确外部待核实项。

- [ ] **Step 3：先部署后端，保持客户端变量未启用。**

~~~sh
gh variable list --json name,value --jq '.[] | select(.name == "TARO_APP_ASSET_BASE_URL")'
~~~

预期当前未设置。若其他操作者已设置非空值，不擅自清除；先核实当前线上 H5 和接口依赖，再调整发布顺序。更新本计划任务勾选、spec 为 implementing，把已验证内容与测试结果追加到 changelog；按任务明确文件列表提交文档。使用 git diff --cached --stat 确认无密钥、素材输出、符号链接或其他会话文件。

若远端主线前进，先把合法新改动合入隔离分支并重跑受影响检查。禁止强推。核对发布提交后执行：

~~~sh
git push origin HEAD:main
motioncare_release_sha=$(git rev-parse HEAD)
gh run list --workflow deploy-production.yml --commit "$motioncare_release_sha" --limit 5 --json databaseId,status,conclusion,url,event
~~~

读取该提交的部署 run id 后使用 gh run watch，等待期间不超过 60 秒无进度沟通。此阶段 GitHub 素材变量仍为空，流水线复用旧 H5，只上线新后端能力。确认 verify/publish/deploy 成功及线上 API 可达。

- [ ] **Step 4：真实签名验收后启用并部署患者 H5。**

~~~sh
cd backend
MINIAPP_STATIC_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets python manage.py verify_miniapp_signed_assets --source-root ../miniapp/output/static-assets/v-3aafe09211fd --api-base-url https://mcare-wx.whestsun.com/api
~~~

验收失败则保留旧客户端，修复明确的部署或 CDN 问题；不以关闭私有空间鉴权绕过失败。验收通过后回仓库根执行：

~~~sh
gh variable set TARO_APP_ASSET_BASE_URL --body 'https://cdn.whestsun.com/motioncare/static-assets'
git fetch origin main
git rev-parse HEAD origin/main
~~~

仅两行提交相同才发起同一代码版本的第二阶段部署；若不同，核对新增主线内容再选择对应已验证发布分支，不误发未知代码。

~~~sh
gh workflow run deploy-production.yml --ref main
gh run list --workflow deploy-production.yml --event workflow_dispatch --limit 5 --json databaseId,headSha,status,conclusion,url
~~~

选中 headSha 等于本次发布提交的新 run，等待完成，核对 H5 镜像本次确实重建。浏览器用 8888 演示验证四款图片游戏、五项动作说明；通过 Network/页面状态查看23项清单及签名下载成功，输出报告避免含完整 URL。演示不读真实 token、处方、历史、待上传数据，不上传结果；真实患者路径只能在已授权测试账号验证读取与预览，不制造研究训练记录。

- [ ] **Step 5：生产微信构建、包体检查、上传开发版 7.0.4。**

~~~sh
cd miniapp
TARO_APP_API_BASE_URL=https://mcare-wx.whestsun.com/api TARO_APP_ASSET_BASE_URL=https://cdn.whestsun.com/motioncare/static-assets npm run build:weapp:prod
npm run check:weapp-package-size
/Applications/wechatwebdevtools.app/Contents/MacOS/cli islogin --lang zh
/Applications/wechatwebdevtools.app/Contents/MacOS/cli upload --project "$PWD" --version 7.0.4 --desc '小游戏难度及私有素材加载优化' --lang zh --info-output /tmp/motioncare-weapp-704-upload.json
~~~

先检查生产 dist 的 API 来源和素材来源符合上文，且未打入私钥或本地 HTTP API；检查采用只输出通过/失败的断言，不打印密钥。上传前确认 project.config.json 指向当前 dist。CLI 上传成功信息和版本号保存作为证据；成功仅代表开发版上传，不能写“已正式上线”。

微信平台核实 cdn.whestsun.com 为 downloadFile 合法域名，并在不开启“忽略合法域名校验”的真机环境检查图片下载及语音播放。若平台需要用户扫码/管理员权限或真机配合，先完成其余可做工作，再明确报告该具体步骤需要协助；不以开发工具本地勾选跳过域名校验当作通过。

- [ ] **Step 6：回归并记录各阶段事实。**

核对六款游戏难度、2 秒展示、分类答题文案、医生难度入口、四原因选项、训练记录菜单移除仍符合 480a501；这次不新增题目语音制作。验证失败时不覆盖此前上线成果。客户端可以退回匹配的已验证版本；仍有签名客户端在用时，后端保留签名接口和所有在用版本。

本计划顶部追加执行日期、任务对应提交和实际测试数字，勾选真正完成步骤；changelog 只追加发布记录。所有验收完成才将 spec/索引标为 implemented，若真机/平台仍待完成则保留 implementing 并说明欠缺。不要仅为改“完成”状态触发一次不必要的生产部署。

最终报告分别列出：后端部署结果与流水线链接、23 项真实素材结果、H5 版本、7.0.4 CLI 上传结果、合法域名/真机状态、平台审核/正式上架状态。不存在的证据不得补写为通过。

## 计划自审与交接

覆盖关系：spec §3 → Task 1；§4 → Task 2；§5 → Task 3；§6.1 → Task 4；§6.2 → Task 5；§7 → Tasks 6/7；§8/9 → Task 7。已明确限流失败关闭、同一操作一次刷新、旧响应隔离、90 秒总上限、私有空间不变、旧版本兼容及两阶段发布。

本文件是待执行计划，不代表代码实现、测试、素材上传或微信上传已完成。执行方式由用户选择：子代理逐任务实施并审查，或在当前会话按 executing-plans 分批实施。
