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
| 侧边栏面板 | 状态总览卡片（已接入 HA 翻译）+ 一键刷新凭据 |
| 诊断 | 内置 diagnostics：隧道端口、盘位序列号、设备用户、协调器状态一键导出 |
| 服务 | `huawei_home_storage.refresh_credentials` 手动刷新设备会话 |

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
| `task_status` | 查任务中心（`filesvc` / `trans`；`all_tasks: true` 取 trans 全表） |

字段示例（`target` 泛指上述服务，`entry_id` 均可选）：

```yaml
service: huawei_home_storage.create_folder
data:
  path: /file/备份/
  category: user          # user = 我的文件；public = 共享

service: huawei_home_storage.rename_path
data:
  old_path: /file/备份/
  new_path: /file/备份_2026/

service: huawei_home_storage.upload_file
data:
  dest_path: /file/备份/note.txt
  content: "hello from HA"
```

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

### 设备 / 账号运维

| 服务 | 说明 |
|------|------|
| `refresh_credentials` | 强制重新申请设备会话凭据（设备报 401 或凭据过期时用） |
| `reboot_device` | ⚠️ 重启存储设备（服务中断约 1-2 分钟） |
| `disk_sleep` | 磁盘休眠（可恢复） |
| `usb_plug_out` | ⚠️ 弹出 USB 设备（正在读写的文件会中断） |

---

## 已知限制

- 「最近删除」中已删除条目的缩略图资源可能已被回收，此时缩略图会回退到原图。
- 设备按客户端会话分配独立的隧道端口（如 8471/8472、8431/8432），集成已自动适配；频繁重建会话可能触发限流。
- 磁盘容量单位为 MB。

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
