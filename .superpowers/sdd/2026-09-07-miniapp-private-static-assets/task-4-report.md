# Task 4 实施报告

## 实施结果

- 游戏图片预加载改为先获取 `SignedAssetManifest`，再从已校验的 `manifest.urls` 下载图片。
- 一次预取最多两轮，第二轮是唯一一次 `forceRefresh`；清单错误按 `mayRefreshSignedAssets` 判断，图片下载错误允许刷新一次。
- 每轮第一个错误会阻止继续领任务和写入迟到结果，`Promise.allSettled` 等旧 worker 全部结束后才进入下一轮，总并发峰值保持 3。
- 已成功图片在第二轮复用；进度只增不减；空 key 立即返回且不请求清单。
- 取消、页面卸载、动作切换和迟到回调继续由 `isCurrent` / generation 隔离；图片就绪后经过 600 秒不会重新预取或提前出题。
- 修复 Taro 4.2 `URL` polyfill 忽略 base pathname 的兼容问题：校验相对路径后先拼出绝对地址，再交给 URL 解析并保留 origin/path 边界检查。
- 签名 URL 在使用 `URLSearchParams` 前严格解码原始 query，避免 Taro 吞掉 `&x=%` 这类非法参数；仍只允许各一个 `e` 和 `token`。

## TDD 证据

### RED

命令：

`npm run test -- src/pages/game-session/gameImagePreloader.test.ts src/pages/game-session/gameImageAssets.test.ts src/pages/game-session/index.integration.test.tsx`

实现前结果：51 项中 8 项按预期失败，分别暴露未加载签名清单、下载不刷新、错误未脱敏、404/429 未分型、旧 worker 未收束重试及成功项未复用；页面既有门禁测试保持通过。

Taro 兼容根因由主控用真实 `TaroURLProvider` 稳定复现：相对 URL 构造结果从 `/motioncare/static-assets/` 逃到站点根路径；带 `&x=%` 的 query 被 Taro `URLSearchParams` 隐藏。随后加入真实 provider 与非法 query 回归测试。

### GREEN

- `npm run test -- src/pages/game-session/gameImagePreloader.test.ts src/pages/game-session/gameImageAssets.test.ts src/pages/game-session/index.integration.test.tsx`：3 文件，59/59 通过。
- `npm run test -- src/assets/staticAssetUrl.test.ts src/assets/signedAssetManifest.test.ts`：2 文件，100/100 通过。
- `git diff --check`：通过。
- 额外执行 `npx tsc --noEmit`，被仓库既存类型错误阻断；错误分布于 API、运动训练、Taro 声明及既有测试，Task 4 改动文件未出现新增诊断。本任务未扩大范围修复这些既有问题。

## 变更文件

- `miniapp/src/assets/staticAssetUrl.ts`
- `miniapp/src/assets/staticAssetUrl.test.ts`
- `miniapp/src/assets/signedAssetManifest.ts`
- `miniapp/src/assets/signedAssetManifest.test.ts`
- `miniapp/src/pages/game-session/gameImageAssets.ts`
- `miniapp/src/pages/game-session/gameImageAssets.test.ts`
- `miniapp/src/pages/game-session/gameImagePreloader.ts`
- `miniapp/src/pages/game-session/gameImagePreloader.test.ts`
- `miniapp/src/pages/game-session/index.integration.test.tsx`

## 自审

- 核对了外层重试预算：清单与下载共享一次强制刷新预算，不会分别刷新。
- 核对了 worker 收束：第二轮只在第一轮所有 worker settled 后创建，迟到成功不会写路径或进度。
- 核对了页面生命周期：默认真实清单加载器由预加载器注入，页面无需订阅签名 TTL，已有临时路径不会因缓存到期清空。
- 核对了安全边界：未放宽 scheme、origin、pathname、userinfo、fragment、参数数量和 token 格式校验。

## 顾虑

- 仓库当前全量 TypeScript 检查存在大量既有失败；本任务按 brief 仅以聚焦 Vitest 作为提交门禁，全套验证留给 Task 7。

## 评审修复（2026-09-07）

- 在真实 `TaroURLProvider` global stub 下加入 `&x=%` 非法 query 拒绝断言。为验证测试有效性，临时移除 `signedUrl` 的 raw-query 防护后运行：该用例按预期失败，并输出 Taro 的 decode 警告；恢复防护后 38/38 通过。
- 迁移被整体改写遗漏的五类既有边界：初始取消零请求、取消后异步 reject 归一、下载失败后会话失效、`undefined` rejection 阻止迟到进度、非正并发归一为 1。
- 补充共享预算混合路径：初次清单可刷新失败、强制刷新成功、随后下载失败时，只请求两次清单且不产生第三次请求。
- 修复未改生产实现，仅增强回归覆盖。

修复验证：

- RED mutation：`npm run test -- src/assets/staticAssetUrl.test.ts -t "使用 Taro URL 实现"`，1 项失败，原因是移除 raw-query 防护后非法 `%` 参数被 Taro 隐藏且 parser 未抛错。
- GREEN：`npm run test -- src/pages/game-session/gameImagePreloader.test.ts`，18/18 通过。
- GREEN：`npm run test -- src/assets/staticAssetUrl.test.ts src/assets/signedAssetManifest.test.ts`，100/100 通过。
