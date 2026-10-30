# Changelog

本项目遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

（暂无）

## [0.11.1] - 2026-10-30

### 修复

* **多账号下「重命名相册 / 设为封面 / 移出相册」直接 400** —— 这三个服务的
  `schema` 漏了 `account` 字段，而面板在选择账号时一定会带上它，被判定为
  未知参数。单账号下不会触发（面板此时不传），所以本机怎么点都正常。
* **`remove_album_members` 会静默动错账号** —— 它的处理函数用的是
  `runtime.client`（固定主账号），却接收 `account` 参数。多账号下从第二个
  账号的相册移出照片，实际会打到主账号的同名相册上。比报错更危险：参数收了
  却不用。

### 测试

* 新增 `test_panel_acc_arg_requires_schema_support`：**面板凡是带 `accArg()`
  的调用，对应服务 schema 必须声明 `ACCOUNT_FIELD`**。这类"面板对、服务也
  对、拼起来才错"的缺陷，只有把两边放在一起比对才抓得到。
* `ALBUM_SERVICES` 补入上述三个服务，要求处理函数必须走 `_client_for()`。
* 两处断言都做了变异验证（还原缺陷 → 确认变红）。其中一处最初写成固定
  900 字符窗口，会跨进下一个注册块导致假阴性，已改为按 `supports_response`
  截断。

## [0.11.0] - 2026-10-30

> 本文只列**使用者能感知的变化**。协议逆向过程不随仓库发布。

### 新增

* **`device_users` 服务** —— 列出设备管理员与成员（昵称 / 等级 / 已用空间）。
* **`download_file` 服务** —— 把设备文件**流式**下载到 HA 主机（内存≈一个分块）。
  `local_path` 限定在 `/config/uploads` 下，防止写穿容器覆盖 `secrets.yaml` / `.storage`。
* **任务中心「重试」** —— 失败任务可重试（`retry_task`）。⚠️ 逆推实现，
  本机无失败任务，未真机验证。
* **相册：重命名 / 设为封面** —— 面板相册详情新增两个入口（仅共享相册）。
* **相册内搜索** —— 面板相册页可按关键词搜本相册的照片。
* **上传进度条** —— 面板上传照片时显示逐张进度。
* **服务总数 34 → 62**。

### 修复

* **设封面固定 `30111`** —— 改名与设封面共用 `/gallery/albumCfg`，但报文是两套；
  同时传 `albumName` + `coverId` 会被拒。此前遇到的都是"缺字段"，这次是**多传**。
* **「共享给家人」必然失败** —— 相册视图没透传 `ownerId` / `userIds`，面板拿不到
  归属人。看着像设备不支持，实际是后端少给了一个字段。
* **相册写服务 4 处漏 `await`** —— 一调用就 HTTP 500，且日志被 500 吞掉看不到栈。
  受影响：新建 / 删除相册、把照片加进相册、共享给家人。
* **从相册移出固定 `30110`** —— `delAlbumMemb` 缺
  `clientType` / `deviceId` / `albumName` / `addTime`。
* **上传固定 `1101`** —— 报文键名用错（`dataList` + `hash` → `files`）。
  与插件反编译的结论相反，以抓包为准。
* **`copy_to_album` 假成功** —— `dest.dirs` 缺 `addTime`：任务 `progress=100`、
  `errorInfo` 为空，但数据凭空消失。
* **`move_paths` / `copy_paths` 固定 `1018`** —— 任务名用了单调时钟，与真实
  Unix 毫秒差 5 个数量级。
* **上传后文件时间显示 1970** —— `ctime` / `mtime` 传成了分块偏移。
* **中文文件名上传失败** —— `transfer.py` 的 `Content-Disposition` 未做百分号编码。
* **多账号缩略图 / 原图串号** —— `build_image_url` 少 `acct` 段。因为贪婪路由不会
  404，症状只是"图裂"，很容易被当成设备慢。
* **「新建文件夹 → 立刻上传」必失败** —— `mkdir` 是异步任务，目录未索引时设备直接
  断开连接。改为轮询到目录真的可列出再返回。
* **连续上传第 5 个起失败** —— 设备对换票有频率限制，改为 45 秒内复用凭据。
* **回收站恢复 100% 失败** —— 列表走 `public`、恢复/删除走 `user`，查的和删的不是
  同一个空间。条目都在，但每一条恢复都失败。
* **「共享给家人」用错相册类型** —— `album_type` 硬编码成 23（人物相册），
  改为取目标相册的真实 type。
* **账号隔离三处缺口（IDOR）** —— 上传视图可往别人账号写文件、账号原图视图可读
  别人的原图、status 下发全部账号。三处统一走 `_gate_account()`。
* **按用户分配账号（隐私隔离）从未生效** —— `views.py` 一直在读映射，但没有任何
  地方写过它，逻辑一次都没执行。已补写入端。

### 变更（破坏性）

**不可逆操作现在必须显式确认**（`confirm` 值须完全相等，大小写敏感）：

| 服务 | 需要的 confirm 值 |
|---|---|
| `shutdown_device` | `SHUTDOWN` |
| `reboot_device` | `REBOOT` |
| `empty_recycle` | `EMPTY_RECYCLE` |
| `permanent_delete_recycle_items` | `PERMANENT_DELETE` |
| `delete_paths`（仅 `skip_recycle: true` 时） | `PERMANENT_DELETE` |
| `del_album` | `DELETE_ALBUM` |
| `merge_face_albums` | `MERGE_FACE_ALBUMS` |

**已有自动化升级后会失败**（返回 `ok: false` 并在 `error` 里说明），请在调用处补上：

```yaml
service: huawei_home_storage.reboot_device
data:
  confirm: "REBOOT"
```

起因：`shutdown_device` 曾在空 payload 下真的把设备关机（需物理按键才能开机）。
`delete_paths` 默认（`skip_recycle: false`）进回收站、可逆，**不需要** confirm。

**`share_to_person` 语义收窄**：此前被定义了两次（Python 后者覆盖前者），实际生效的
那版与文档写的不一致，按文档调用必然报错。现拆开：

| 服务 | 语义 | 主要参数 |
|---|---|---|
| `share_to_person` | 按**相册**共享到人物 | `album_id`, `owner_id`, `file_ids` |
| `share_files_to_person`（新） | 按**文件**分享给用户 | `file_ids`, `receiver_user_ids` |

若你之前靠 `receiver_user_id` 调 `share_to_person`，请改用 `share_files_to_person`。

### 移除

* **面板「隐藏相册」入口** —— 设备返回 `code 0` 但 `hiddenStatus` 不变，属假成功。
  服务保留并标注「设备接受但无效果」，测试加断言防止入口被加回来。
* **`translations/zh.json`** —— HA 只加载 `zh-Hans` / `zh-Hant`，该文件从未生效。

### 安全

* 清除仓库里 6 类真实身份标识（姓名与昵称、账号长 ID、含 MAC 的 deviceId、
  设备序列号、账号脱敏串、导出文件名）。
* 新增 `NoRealIdentityInRepoTest` 防回归。

### 测试

* 离线套件 **7 个 / 188 用例**，不需要安装 Home Assistant，也不需要真实设备；
  CI 新增 `offline-tests` job。
* 新增断言一律做**变异验证**（还原缺陷 → 确认变红）。累计抓出 **5 条恒真假测试**，
  共性都是**断言的关键字出现在注释里**——注释越认真解释"为什么要这样做"，
  越容易把断言弄废。规则：匹配赋值语法、先剥离注释再匹配。

### 已知限制

* 除 5 个相册服务外，其余服务**固定作用于主账号**（`runtime.client` 绑定主账号）。
  多账号下"看"没问题，"写"会找错地方。这是架构层面的，需逐个改造 + 真机验证。
* 相册域上传 `/gallery/prepareUpload` 仍未跑通，照片进相册走
  「文件空间上传 + `copy_to_album` 跨域复制」两步。
* `add_album` / `del_album` / `empty_recycle` / `merge_face_albums` 部分仍是逆向
  推断实现，未逐项真机验证，面板与 `services.yaml` 已如实标注。

## [0.10.0] - 2026-10-08

### 新增

- **HA 备份目标** —— 家庭存储可直接作为 Home Assistant 的备份目的地，
  出现在 **设置 → 系统 → 备份** 里。对**纯 Core / Container 安装（无 Supervisor）**
  尤其有意义：官方只能备份到本地磁盘，此前想存 NAS 需要 Samba 或额外插件。
  - 备份**流式分块上传**，几百 MB ~ GB 不占 HA 内存（无需先落盘）；
    总大小取自 `AgentBackup.size`。
  - 每个备份附一个 `.ha-backup.json` **边车元数据**，列举时只读小文件，
    不必把整个 tar 从设备拉下来。
  - 增删配置条目（多设备 / 多账号）时备份目标**即时刷新**，不必重启 HA。
  - 删除走设备回收站（可逆）。
- **侧边栏面板重建** —— 导航按用途分「浏览」与「管理」两组、共 5 个视图，
  替换原来的平铺列表与「照片与文件」混合视图。
  - **相册**：接入设备上的**真实相册**（智能分类 / 人物 / 地点 / 场景 / 我的相册），
    封面、照片墙、全屏查看（下载原图 + 左右翻页）。
  - **文件**：我的文件 / 共享 / 最近删除三个**独立空间**，面包屑导航。
  - **文件操作**：新建文件夹、重命名、复制、移动、删除（进回收站）。
  - **浏览器上传**：带进度条；上传走新增的流式接口，内存只占一个分块。
  - **面板内添加华为账号**：密码 + 短信 / 已登录设备推送验证码，
    无需重启 HA，与配置流共用同一段收尾逻辑。
  - 手机端自动切换为**底部栏**；缩略图按需加载并限制并发
    （滚动到可视区才取、最多 6 个并发），打开几百张照片不会压垮设备会话。
- **文件空间与运维服务补齐到 22 个**：`create_folder`（建目录）、`rename_path`、
  `move_paths`、`copy_paths`、`delete_paths`、`upload_file`、`cancel_upload`、
  `copy_to_album`、`list_recycle`、`recover_recycle`、`search_files`、`task_status`、
  `photo_info`、`file_detail`，以及 `reboot_device`、`disk_sleep`、`usb_plug_out`。
- **文件上传打通**（两段式 + 分块，`Expect: 100-continue` 必需）。
- **相册与空间补齐**：相册增加「所有照片 / 视频」；**共享空间**（`category=public`）
  与文件空间分离；回收站恢复。

### 修复

- **共享相册未出现在相册列表**：`albumType=6` 需单独取一次列表后并入。
- **共享相册计数与列表不一致**：改用协调器缓存，徽标计数与列表对齐。
- **文件空间 / 共享空间的缩略图一律取不到**：图片代理把 `category` 硬编码为
  `public`，导致 `/file/` 路径 404（实测 `category=""` → 200，
  `category="public"` → 取不到）。现按序尝试 `""` 再 `"public"`。
  此问题同时影响媒体源与面板。
- **面板首屏必然报「未连接到 Home Assistant」**：取 `hass` 的辅助函数依赖一个
  只在首次绘制时才赋值的全局，而首次取数跑在它之前；导致配置条目 id 取空、
  文件页卡在「载入中…」。
- **面板每 60 秒自动刷新会清空已加载的缩略图**（整屏重绘）→ 改为静默刷新，
  只更新顶栏。
- **面板无法调用写服务**：本集成的写服务均为 `SupportsResponse.ONLY`，
  而前端 `hass.callService(..., true)` **不会透传** `return_response`
  （报 `The action requires responses and must be called with return_response=True`）
  → 改走 WebSocket 的 `call_service`。
- **设备页硬件信息只显示 2 行**：字段名与后端不一致
  （`cpu_model` / `cpu_temperature` / `memory_used` 等），且错误是静默的。
- **备份目标的三个绑定缺陷**（均为测试中实测发现）：
  1. HA 传给备份代理的是**它自己的 `backup_id`**（如 `67980322`）而**不是文件名** ——
     最初拿它比对文件名，导致所有下载 / 恢复 **404**；
  2. 列举时把**边车文件名**当成了基名，下载会返回几百字节的 json 而非 tar 本体；
  3. 边车元数据的扁平 / 嵌套两种格式都需兼容（否则早期写入的文件读不出来）。

### 文档

- 服务翻译补齐到 22 个（`en` / `zh-Hans` / `strings.json`）。
- README 新增「侧边栏面板」与「HA 备份」两个章节；修正过时描述
  （「磁盘容量单位为 MB」—— 自 0.5.0 起即为字节）；补充已知限制
  （回收站不立即释放空间、原图 HEIC 无法在浏览器渲染、相册分页）。

## [0.9.1] - 2026-10-07

### 修复

- **相册统计偶发硬失败**：设备下发的解密结果偶有非合法 JSON，
  此前 `JSONDecodeError` 会逃出类型化异常体系，绕过协调器的降级分支，
  直接报 `Unexpected error fetching ... albums data`。
  现已包装为 `HuaweiCloudError`，走优雅降级（保留上轮数据 + 下轮重试），
  且日志不记录明文内容。
- **HA 2027.8 兼容**：`DeviceRegistry.async_get_device` 已被 HA 弃用
  （2027.8.0 移除），2 处调用改用新 API `async_get_devices`。
  为兼容 `hacs.json` 声明的 HA ≥ 2024.7.0，通过 `hasattr` 能力探测自动回退，
  不抬高最低版本要求。语义保持**跨配置条目**查找（同一物理设备被多账号
  接入时复用同一主设备），避免设备树断开。
- **瞬时故障不再误弹重新认证**：此前所有云侧错误都被归为认证失败，
  一次 MQTT 超时就会让 HA 弹出「重新认证」要求重输账号密码。
  现在只有凭据真正失效才触发重新认证，瞬时故障走重试。
- **诊断信息脱敏加固**：诊断包（用于提交 issue 的那份）中账号对象的
  `key` / `account` 字段未脱敏，会带出登录账号。现按三层加固：
  语义层打码账号类字段（保留 `138****8000` 可读掩码便于排查）、
  修复掩码函数对 ≤7 字符值原样返回的漏洞、并新增按**值特征**的兜底扫描
  （不看字段名，杜绝白名单枚举遗漏）。实测同一份诊断包
  9 处泄漏 → 0 处。

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
