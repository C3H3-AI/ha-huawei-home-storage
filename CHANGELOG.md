# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [0.9.0] - 2026-10-07

### 新增

- **设备动作按钮**（`button` 平台）：磁盘休眠、弹出 USB、重启设备。
  三个动作都是**物理设备**操作，统一按 `DEVICE_SCOPE` 挂主设备，
  多账号接入时注册表天然去重，只保留一份。
  仅暴露**可恢复**动作；关机 / 格式化 / 恢复出厂一律不提供。
- **服务**：
  - `duplicate_scan` —— 扫描重复文件
  - `query_files` —— 按条件查询文件（`source=dir` 亦可用）
  - `delete_media` —— 删除照片
  - `recover_media` —— 从回收站恢复照片
  - `refresh_credentials` —— 手动刷新设备凭据
  共 5 个服务，均配 `services.yaml` 与中英翻译。
- **文件空间传感器**：文件 / 相册维度的用量与统计。
- **媒体源**：相册与文件空间的浏览入口。

### 修复

- `query_files` 在 `source=dir` 时返回空结果。
- 按钮归属修正为设备级（原按账号级会重复注册）。
- 写入 `lab` 相册的删除 / 恢复流程已可用，并支持查询相册照片 id。
- 完成 v0.8.0 架构移植的若干遗漏（作用域、信息刷新、重复 payload）。

### 安全

- **清除仓库历史中的个人隐私信息**（手机号、设备序列号、内网地址），
  并新增提交期隐私扫描钩子（`_tools/`），防止再次误提交。

## [0.8.0] - 2026-10-06

### 新增

- 内置华为账号登录实现。
- 盘位容量传感器改挂主设备。
- 与上游 `huawei_smarthome` 集成**彻底解耦身份**（不再共享 `device_id`）。
- 移植**短信验证码登录**：支持验证码渠道选择。

[0.9.0]: https://github.com/C3H3-AI/ha-huawei-home-storage/releases/tag/v0.9.0
[0.8.0]: https://github.com/C3H3-AI/ha-huawei-home-storage/releases/tag/v0.8.0
