> 状态：approved
> 日期：2026-08-11
> 范围：将微信小程序永久迁移到新的 AppID，并先上传开发版
> 关联：`docs/superpowers/plans/2026-08-11-wechat-miniapp-appid-migration.md`

# 微信小程序 AppID 永久迁移设计

## 目标

将 MotionCare 微信小程序的项目配置永久切换到用户指定的新 AppID，继续连接现有线上接口 `https://mcare-wx.whestsun.com/api`，完成一次可核验的微信开发版上传。

## 配置与安全边界

- 在干净的 `main` 发布工作区修改 `miniapp/project.config.json` 中的 `appid`。
- 不在源码、配置文件、Git 历史、构建命令或发布日志中保存 AppSecret。开发者工具上传不依赖 AppSecret。
- 使用生产构建配置，并显式指定现有线上 API 地址。
- 构建后核对 `miniapp/dist/project.config.json`，确保产物使用新的 AppID。
- 不修改后端部署、数据库、七牛云配置和现有线上服务。

## 发布流程

1. 确认 `main` 发布工作区干净并同步远端。
2. 修改源项目 AppID。
3. 运行小程序全量测试和生产构建。
4. 核对构建产物中的 AppID 与 API 地址。
5. 以中文提交信息提交并推送到 `main`。
6. 通过微信开发者工具 CLI 上传开发版：
   - 版本号：`2026.08.11.1`
   - 描述：`迁移至新 AppID，连接现有线上服务`
7. 仅在 CLI 明确返回成功且新 AppID 后台出现该版本时，报告开发版发布完成。

## 异常处理

- 若微信开发者工具未登录、当前账号缺少新 AppID 的开发权限或平台拒绝上传，则停止在上传步骤，保留已验证的提交与构建结果，并报告原始错误。
- 若新 AppID 尚未配置 `https://mcare-wx.whestsun.com` 为合法服务器域名，上传本身可能成功，但真机 API 请求会失败；需要在微信公众平台补充域名后再验证。
- 若测试或生产构建失败，不推送、不上传，先修复或向用户报告阻塞。

## 验收标准

- `main` 中的微信项目 AppID 已永久切换。
- 小程序全量测试和生产构建通过。
- 构建产物使用新的 AppID，并连接 `https://mcare-wx.whestsun.com/api`。
- 微信开发者工具确认开发版上传成功，版本号为 `2026.08.11.1`。
