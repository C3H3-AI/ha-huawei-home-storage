# 华为家庭存储 (Huawei Home Storage)

Home Assistant 自定义集成，用于接入**华为家庭存储**（AS6020 系列）。

**纯云授权 + 局域网直连**：授权走华为账号，拿到会话后所有数据都从局域网设备的本地 API 读取，不经过第三方服务器，也**不需要在电脑上常驻任何客户端程序**。

- 支持**账号密码登录**或**设备码扫码授权**，两条路径都完全自包含
- 支持**同一台设备被多个华为账号接入**（不同账号看到各自的相册与文件）

---

## ⚠️ 免责声明与许可

- 本项目为**非官方**集成，基于对官方客户端与设备本地 API 的逆向实现，与华为无任何关联。
- 集成中内置的 OAuth `client_id` / `client_secret` 来自**华为官方客户端**，仅用于复现其授权流程。请仅用于个人自有设备的接入，自行评估合规风险。
- 设备本地 API 未公开、可能随固件更新变化，升级后可能失效。
- 建议**先在测试环境验证**，并提前备份路由器/设备配置。

**许可**：本项目采用 **GPL-3.0**（见 [LICENSE](LICENSE)）。

其中 `custom_components/huawei_home_storage/api/auth/`、`api/domain/`、`api/storage/`
下的华为账号登录实现，**移植自** [xiasi0/ha-huawei-smarthome](https://github.com/xiasi0/ha-huawei-smarthome)
（commit `04fd6e8`，2026-10-05），作者 **xiasi0**，同样以 GPL-3.0 发布，
并经原作者同意后移植（原实现在运行时依赖该集成，改动导入路径即可独立运行）。
文件头部保留了完整的来源与许可声明。

> 因 GPL-3.0 的 copyleft 特性，移植该部分后**本仓库整体以 GPL-3.0 发布**。

---

## 功能

| 能力 | 说明 |
|------|------|
| 云端授权 | 账号密码登录（默认）或设备码扫码授权 |
| 自动续期 | 会话凭据 401 时自动重新申请；每个账号使用设备分配的**独立隧道端口** |
| 多账号 | 同一台设备可被多个华为账号分别接入，互不影响 |
| 传感器 | 照片/视频总数、各类相册数、最近删除、磁盘容量与使用率、硬盘数量与分盘容量、本账号占用空间、设备用户数、USB 设备数 |
| 在线状态 | 设备可达性 + USB 设备接入（二进制传感器） |
| 媒体源 | 在 HA 媒体浏览器中浏览**相册**（含共享相册）、**文件空间目录树**（全部文件，含照片/视频原图）、**共享空间**与**最近删除**，缩略图/原图经 HA 代理 |
| **HA 备份** | **家庭存储可直接作为 HA 的备份目标**（设置 → 系统 → 备份 里可选）。纯 Core / Container 没有 Supervisor 时，不必再装 Samba 或额外插件即可把备份存到 NAS |
| 侧边栏面板 | 响应式面板（桌面侧栏 / 手机底栏），5 个视图分两组：**浏览**（概览 · 相册 · 文件）、**管理**（设备 · 用户）。真实相册逐层浏览、照片墙与全屏查看、文件空间三区切换，可在面板内直接添加华为账号，也可**新建文件夹 / 重命名 / 移动 / 复制 / 删除 / 上传** |
| 诊断 | 内置 diagnostics：隧道端口、盘位序列号、设备用户、协调器状态一键导出 |
| 服务 | 33 个：文件空间（建目录/重命名/移动/复制/删除/上传/搜索）、相册、回收站、任务中心、设备运维等，详见下文 |
| 流式传输 | 上传/下载分块进行（设备侧 `Content-Range`），大文件不占 HA 内存；实测 25 MB 往返 MD5 一致、223 MB 备份完整落盘 |

---

## 安装

### HACS（推荐）

1. HACS → 集成 → 右上角菜单 → **自定义存储库**
2. 添加 `https://github.com/C3H3-AI/ha-huawei-home-storage`，类别选 **Integration**
3. 搜索 "Huawei Home Storage" 安装，重启 Home Assistant

### 手动

把 `custom_components/huawei_home_storage` 整个目录复制到 HA 的 `/config/custom_components/` 下，重启 Home Assistant。

---

## 配置

**设置 → 设备与服务 → 添加集成 → 搜索「Huawei Home Storage」**，按向导完成：

1. **选择登录方式**：账号密码（推荐，不跳浏览器）或设备码扫码授权
2. **登录华为账号**：输入账号密码；若华为要求二次验证，会让你**选择验证码接收方式**：
   - **短信验证码** —— 发送到账号绑定的手机，稍等片刻即可收到
   - **已登录设备推送** —— 在已登录该账号的华为手机上查看挑战码

   只有华为提供多个渠道时才会出现该选择步骤；只有一个渠道时自动跳过。
3. **选择设备**：从账号下选择要接入的家庭存储设备

**一台设备 = 一个配置条目**。之后接入更多账号（家人共享同一台设备）无需重新配置：

```
家庭存储 → ⚙️ 配置 → 添加账号 / 移除账号 / 重新登录某个账号
```

每个账号独立持有登录态与设备会话，**相册统计互不相同**（各账号可见范围不同），
而磁盘、在线状态、文件空间等设备属性全局只有一份。

> 管理员账号（设备上的 level=1 用户）会排在第一位并标注「（管理员）」：它权限更大，
> 文件空间浏览用的就是它的会话。

---

## 实体

设备按**物理设备**组织，多个华为账号接入同一台设备时汇聚到同一台设备下，账号作为其下的分支：

```
家庭存储（序列号 SN-EXAMPLE-0001）
├── 账号 137****6363           该账号可见的相册统计、账号占用
└── 账号 137****2663           另一账号的相册统计、账号占用
```

磁盘容量、在线状态、USB 接入、设备用户数等属于**物理设备属性**，无论多少个账号接入都只有一份。
分盘位的容量也是直接挂在设备上的普通传感器（用「硬盘 1 / 硬盘 2」前缀区分），
**不会为每块硬盘单独建一个子设备**——一块盘只有两个传感器，单独建设备反而把设备列表撑得很乱。

**设备级实体**（挂在设备本身，多账号不重复）

| 实体 | 说明 |
|------|------|
| `binary_sensor.*_online` | 设备是否可达 |
| `binary_sensor.*_usb_device` | 是否有 USB 设备接入 |
| `sensor.*_disk_total` / `_disk_used` / `_disk_free` | 磁盘总容量（自动换算 GB/TB） |
| `sensor.*_disk_usage` | 磁盘总使用率（%） |
| `sensor.*_disks` | 硬盘数量 |
| `sensor.*_device_users` / `_administrators` | 设备上的用户数 / 管理员数 |
| `sensor.*_usb_devices` | USB 设备数量 |
| `sensor.*_disk_1_total` / `_disk_1_used` … | 每块硬盘的分盘容量（同一设备下的普通传感器） |

**账号级实体**（每个账号一份，数值随账号可见范围不同）

| 实体 | 说明 |
|------|------|
| `sensor.*_photos` | 照片总数 |
| `sensor.*_videos` | 视频总数 |
| `sensor.*_albums_user` | 用户相册数 |
| `sensor.*_albums_face` | 人物相册数 |
| `sensor.*_albums_scene` | 场景相册数 |
| `sensor.*_albums_place` | 地点相册数 |
| `sensor.*_trash` | 最近删除数量 |
| `sensor.*_account_usage` | 本账号在设备上占用的空间 |

在线状态、容量、用户数每 **1 分钟**刷新；相册统计（较重的全量请求）每 **10 分钟**刷新。

---

## 媒体源

在 **媒体 → Huawei Home Storage** 中浏览：

- 先按**账号**分叉（各账号可见的相册与文件不同）
  - **相册**：全部相册（含封面与照片数），其中**共享相册**（家庭共享的用户自建相册，`albumType=6`）
    需额外取一次列表后并入，与客户端侧边栏「共享 → 共享相册」一致
  - **文件空间**：设备的 NAS 文件视图（`category=user`），从 `/file/` 逐层进入目录，照片/视频可直接播放（原图/原片下载）
  - **共享空间**：共享目录（`category=public`）——与「文件空间」是设备上的**两个独立空间**
  - **最近删除**：逐条列出，支持分页

缩略图与原图由 HA 代理转发（路径 `/api/huawei_home_storage/image/<entry_id>/...`），
浏览器无需携带设备凭据。

> 注意：文件空间是 NAS 文件视图，与「相册」的照片计数不是同一集合（可能部分重叠）。

## HA 备份（存到家庭存储）

家庭存储会作为一个**备份目标**出现在 **设置 → 系统 → 备份** 里，可以和「本地」
一起选，也可以只选它。

> 这一条对**纯 Core / Container 安装**（没有 Supervisor）尤其有用 ——
> 官方只能存本地磁盘，想存 NAS 一般要装 Samba 或额外插件，现在不需要了。

### 备份存放位置

默认 `/file/HomeAssistant/`（**我的文件**空间）。目录不存在时会自动创建。

每个备份由两个文件组成：

| 文件 | 内容 |
|------|------|
| `<备份名> <日期>.tar` | 备份本体（HA 标准格式，内含 `backup.json` + `homeassistant.tar.gz`）|
| `<同名>.ha-backup.json` | 元数据边车 —— 列出/下载/删除都靠它定位，**请勿单独删除或改名** |

### 工作方式

- **上传**：边收边发、分块上传，因此几百 MB ~ GB 的备份**不会占用 HA 内存**
  （实测 223 MB 备份完整落盘，25 MB 往返 MD5 一致）。
- **列举**：读取各备份的元数据边车，不必下载整个 tar。
- **下载/恢复**：流式读取，恢复走 HA 标准流程。
- **删除**：与文件空间一致 —— **一律移入设备回收站**（可逆）。想彻底清除请在
  设备 App / PC 客户端的回收站里操作。

### 注意

- 备份目录必须位于**已存在的空间**（我的文件 / 共享）；选「共享」时其他家庭成员也能看到备份。
- 删除是移入回收站，因此**不会立即释放空间**；长期使用建议定期清理回收站。
- 备份文件较大时（含数据库通常几百 MB），首次上传受局域网带宽限制，属正常现象。

---

## 侧边栏面板

侧边栏点击 **家庭存储** 进入。桌面为左侧栏、**手机自动切换为底部栏**（820px 断点），
导航按用途分两组：

| 分组 | 视图 | 内容 |
|------|------|------|
| 浏览 | **概览** | 容量环、照片/视频/文件数、设备状态、设备用户数、快捷操作 |
| 浏览 | **相册** | 设备上的**真实相册**，按「智能分类 / 人物 / 地点 / 场景 / 我的相册」分组切换；点进相册看照片墙（每页 100 张，可继续加载），点照片全屏查看 |
| 浏览 | **文件** | 文件空间逐层浏览：**我的文件** / **共享** / **最近删除** 三个独立空间，面包屑导航，图片以缩略图墙呈现，其他文件列出大小与时间。支持**新建文件夹**、每行的 **⋯** 菜单（重命名 / 复制到 / 移动到 / 删除）与**上传文件**（带进度）|
| 管理 | **设备** | 硬件（型号/固件/CPU/温度/内存）、存储（容量与盘位）、网络与共享（IPv4/v6、SMB、自动升级）、设备操作（硬盘休眠 / 弹出 USB / 重启） |
| 管理 | **用户** | 设备成员、登录账号（各账号可见照片数），以及**在面板内直接添加华为账号** |

### 面板内添加账号

**管理 → 用户 → ＋ 添加华为账号**：输入账号密码 → 选择验证码接收方式（华为下发短信
或推送到已登录设备）→ 填入验证码 → 完成。**无需重启 HA**，也无需进入集成配置页。

> 面板与配置流走**同一段**收尾逻辑（取设备凭据 + 写入账号列表），因此两条路径行为一致。
> 密码按既有约定保存在配置条目中（后续自动续期需要），仅用于该账号的设备凭据申请。

### 隐私

面板只展示**脱敏后**的信息：账号显示为 `137****6363`，设备序列号显示为
`A4DE****0588`；设备成员的**真实姓名与 ID 不下发到前端**，只显示成员数量与角色。

### 图片显示说明

- 照片墙与原图查看都经 HA 代理（`/api/huawei_home_storage/image/...`），浏览器不需要设备凭据。
- 相册原图多为 **HEIC**，浏览器（Chrome/Firefox）**无法直接渲染 HEIC**。因此面板浏览时
  使用设备生成的 JPEG 预览图（`lcd`），点「原图」下载时给的是**真正的原文件**。
- 缩略图按需加载（滚动到可视区域才取），并限制并发，避免一次打开几百张照片时压垮设备会话。

### 升级后看不到新界面？

面板脚本带版本号缓存穿透，正常情况下刷新即可。若仍显示旧界面，请**强制刷新**
（Windows `Ctrl+F5` / macOS `Cmd+Shift+R`）。

---

## 服务

所有服务都接受可选的 `entry_id`（多设备时指定目标条目，留空用第一个）。
写操作返回 `{ok, ...}`；只读服务（`query_files` / `file_detail` / `search_files` /
`task_status` / `list_recycle`）直接返回结果，需在调用时带 `return_response: true`。

### 文件空间（NAS）—— 建目录 / 重命名 / 移动 / 删除 / 上传

| 服务 | 说明 |
|------|------|
| `create_folder` | 新建目录（`path` 单个或 `paths` 批量；重名报错，不自动改名） |
| `rename_path` | 重命名（`old_path` → `new_path`；目录带尾斜杠、文件不带） |
| `move_paths` | 把若干文件/目录移动到 `dest_dir` |
| `copy_paths` | 把若干文件/目录复制到 `dest_dir`（同空间；目标目录需已存在） |
| `delete_paths` | 删除文件/目录 —— **一律移入回收站**（可逆） |
| `upload_file` | 上传文本（`content`）或 HA 主机上的文件（`local_path`） |
| `cancel_upload` | 取消进行中的上传（需 `prepareUpload` 的 `fileId`） |
| `copy_to_album` | 把文件空间里的照片复制进相册 |
| `list_recycle` | 列回收站（返回的 `rid` 供恢复用） |
| `recover_recycle` | 从回收站恢复（给 `rid`，或给 `paths`/`names` 自动匹配） |
| `query_files` | 列最近/全部/指定目录/相册照片（只读） |
| `file_detail` | 文件/目录详情（`/file/` 这类有效路径可用） |
| `photo_info` | 把相册照片的 `fileId` 换成完整元数据（含 `hdcFilePath` 原图路径） |
| `search_files` | 按关键字搜索（设备参数未解出，目前返回失败，调用需容错） |
| `task_status` | 查任务中心（`filesvc` / `trans` / `gallery`；`all_tasks: true` 取 trans 全表） |
| `clean_task_records` | 清除任务中心的历史记录（只影响任务列表显示，不碰任何文件） |
| `get_task` | 按 `taskId` 精确查单个任务详情 |
| `add_to_album` | 把已有照片加进相册（用相册域 `fileId`；重复添加幂等） |
| `share_to_person` | 把照片共享到人物相册（`ownerId` 用设备用户 id；文件名与相册名留空会自动补全） |
| `album_info` | 单个相册的元数据与**封面原图路径**（相册列表封面为空时的兜底） |
| `album_changes` | 相册增量表：哪些相册有变动（只读） |

字段示例（`entry_id` 在多设备时才需要，单设备可全省）：

```yaml
# ① 建目录：单个 / 批量（批量是逐个建，设备侧批量接口参数未解出）
service: huawei_home_storage.create_folder
data:
  path: /file/备份/
  category: user          # user = 我的文件；public = 共享

service: huawei_home_storage.create_folder
data:
  paths:
    - /file/归档/
    - /file/临时/
  category: user

# ② 改名 / 移动 / 复制（复制与移动同构，目标目录需已存在）
service: huawei_home_storage.rename_path
data:
  old_path: /file/备份/
  new_path: /file/备份_2026/

service: huawei_home_storage.move_paths
data:
  paths: ["/file/临时/"]
  dest_dir: /file/归档/
  category: user

service: huawei_home_storage.copy_paths
data:
  paths: ["/file/备份/"]
  dest_dir: /file/归档/
  category: user

# ③ 上传：文本或 HA 主机上的文件（二选一）
service: huawei_home_storage.upload_file
data:
  dest_path: /file/备份/note.txt
  content: "hello from HA"

service: huawei_home_storage.upload_file
data:
  dest_path: /file/备份/config.yaml
  local_path: /config/configuration.yaml
  category: user

# ④ 删除（进回收站）+ 回收站列表 / 恢复
service: huawei_home_storage.delete_paths
data:
  paths: ["/file/临时/"]

service: huawei_home_storage.list_recycle
data:
  limit: 50

service: huawei_home_storage.recover_recycle
data:
  paths: ["/file/临时/"]        # 也可直接给 rid

# ⑤ 搜索（参数由穷举实测得出）
service: huawei_home_storage.search_files
data:
  keyword: 发票
  category: user
  limit: 20

# ⑥ 任务中心（删除/移动/复制都是异步任务）
service: huawei_home_storage.task_status
data:
  service: filesvc           # filesvc / trans / gallery

service: huawei_home_storage.get_task
data:
  task_id: 18

# ⑦ 相册：加入相册 / 共享到人物 / 相册详情 / 照片元数据
service: huawei_home_storage.add_to_album
data:
  album_id: 13
  file_ids: [281474976755920]

service: huawei_home_storage.share_to_person
data:
  album_id: 13
  owner_id: 10001
  file_ids: [281474976755920]

service: huawei_home_storage.album_info
data:
  album_id: 16

service: huawei_home_storage.photo_info
data:
  file_ids: [281474976755033]

# ⑧ 运维：凭据刷新 / 备份目标相关见「HA 备份」一节
service: huawei_home_storage.refresh_credentials
data: {}
```

响应里统一带 `ok`：只读服务直接返回结果（如 `items` / `count`），
写服务返回 `{ok: true, ...}`。失败时 `ok: false` 且 `error` 写明设备返回码。

> ⚠️ **删除只会进回收站**：集成不提供永久删除 —— 设备侧 `type=delete` 与
> `/filesvc/recycleDelFiles` 的参数都没解出（实测恒 `1101`）。回收站条目请在
> 华为家庭存储客户端里清。
> ⚠️ **删除 / 移动是异步任务**：返回 `ok: true` 只表示设备已受理，
> 真实进度用 `task_status` 查（实测个别条目会在设备侧失败，但受理时仍返回 `code 0`）。

### 相册（照片 / 视频）

| 服务 | 说明 |
|------|------|
| `delete_media` | 把照片/视频移入回收站（可恢复，不会永久删除） |
| `recover_media` | 从回收站恢复照片/视频 |
| `duplicate_scan` | 启动/停止重复照片扫描（不删照片） |
| `duplicate_scan_result` | 查询重复照片扫描的结果（先 `duplicate_scan` 跑 start 后再查） |
| `list_albums` | 列相册。`album_type=0` 是分类相册；**不含 type=6**，要共享相册请传 `6` |
| `album_photos` | 列相册内照片（含路径与缩略图），支持 `last_cre_time`/`last_row_id` 游标分页 |
| `list_trash` | 回收站查询，返回**完整元数据**（含原图路径） |

### 设备 / 账号运维

| 服务 | 说明 |
|------|------|
| `refresh_credentials` | 强制重新申请设备会话凭据（设备报 401 或凭据过期时用） |
| `reboot_device` | ⚠️ 重启存储设备（服务中断约 1-2 分钟） |
| `disk_sleep` | 磁盘休眠（可恢复） |
| `usb_plug_out` | ⚠️ 弹出 USB 设备（正在读写的文件会中断） |
| `device_diagnostics` | 设备诊断快照：一次取回设备错误码、维修模式、Samba 共享状态（排障用） |

---

## 自动化蓝图（开箱即用）

仓库自带 `blueprints/automation/huawei_home_storage/`，装好集成后可在
**设置 → 自动化与场景 → 创建自动化 → 使用蓝图** 里直接导入：

| 蓝图 | 作用 |
|------|------|
| **定期清理临时目录** | 按计划把指定目录清进**回收站**（不是永久删除，可在客户端还原），完成后可选通知 |
| **设备离线自动恢复凭据并通知** | 设备离线满一定时长后先自动刷新会话凭据自愈，仍离线再发通知 |

导入后只需选实体 / 填路径即可，不用自己写 YAML。

> 蓝图的触发器和动作都基于上面的服务，逻辑可直接照抄改成自己的自动化。

---

## 已知限制

- 「最近删除」中已删除条目的缩略图资源可能已被回收，此时缩略图会回退到原图。
- 设备按客户端会话分配独立的隧道端口（如 8471/8472、8431/8432），集成已自动适配；频繁重建会话可能触发限流。
- 容量传感器以**字节**上报（设备侧原单位为 MB，集成内部已换算），由 HA 自动显示为 GB/TB。
- 相册内照片为**分页**获取，超大相册需点「加载更多」继续。
- 相册浏览使用 JPEG 预览图：设备原图多为 HEIC，浏览器无法渲染；点「下载原图」得到的才是原文件。
- 文件空间是 NAS 文件视图，与「相册」的照片集合**不是同一份**（可能部分重叠）。

---

## 排错

**集成加载失败 / 实体不可用**

1. 确认设备与 HA 在同一局域网（`https://<设备IP>:<隧道端口>` 可达）
2. 导出诊断：设备页 → 集成 → **下载诊断**。其中 `tunnel` 段会显示当前账号实际使用的
   隧道端口、`identity` 段显示设备与账号信息，可直接定位凭据/端口问题
3. 查看日志：**设置 → 系统 → 日志**，过滤 `huawei_home_storage`
4. 凭据问题可调用服务 `huawei_home_storage.refresh_credentials` 后重试

**从 0.8.x 升级**

分盘容量传感器改为直接挂在设备下（不再每块硬盘单独建子设备），
原有的「磁盘 1 / 磁盘 2」子设备会自动清理掉。**实体本身不变**
（`unique_id` 沿用旧格式，实体 ID 与历史统计都保留），只是归属从子设备移到主设备，
无需手工干预。若仍看到残留的「磁盘 N」空设备，重启一次 HA Core 即可。

**⚠️ 本次升级需要重新登录一次账号**

本版本**不再与 `huawei_smarthome` 集成共用客户端身份**。

0.8.x 移植上游登录实现时沿用了它的存储键
（`huawei_smarthome/device_identity.json`），导致两个集成拿到**完全相同的
`device_id`** —— 对华为云而言就是同一个「伪装 iPhone 客户端」。同一客户端身份
被两个集成分别登录，会话互相顶掉，这正是「huawei home smart 突然需要重新登录」
的原因。本版本改用独立命名空间（`huawei_home_storage/...`），两边彻底隔离。

升级后各账号会生成新的 `device_id`（云端视为新客户端），因此**首次刷新会失败一次**，
随后自动用已保存的账号密码重新登录 —— 通常无需你干预。若该账号登录时华为要求
二次验证，则会弹出**验证码接收方式选择**（短信 / 已登录设备推送），按提示完成即可。

**与上游 `huawei_smarthome` 集成的关系**

本集成**不依赖**也**不影响** `huawei_smarthome`。请确保系统里只有一个
`huawei_smarthome` 集成目录：若你把旧目录改名成 `zz_xxx` 之类，
HA 仍会按 `manifest.json` 里的 `domain` 加载它（目录名不参与判断），
要真正停用必须删除目录或禁用/删除它的配置条目。

**从 0.4.x 升级到 0.5.x**

磁盘容量实体的单位从 MB 改为字节（HA 自动换算 GB/TB），`unique_id` 相应加了 `_b`
后缀。升级后旧实体会显示为「不可用」，在实体注册表里删除旧的三项
（`disk_total` / `disk_used` / `disk_free`）即可，历史数据不受影响。

**修改代码后不生效**

删除 `custom_components/huawei_home_storage/__pycache__` 并重启 HA Core（仅重载配置条目不会重新加载 Python 代码）。

---

## 许可

[GPL-3.0](LICENSE) — 因移植了 `ha-huawei-smarthome`（作者 xiasi0，同样 GPL-3.0）
的华为账号登录实现，本项目整体采用 GPL-3.0 发布。
