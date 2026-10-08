"""Constants for the Huawei Home Storage integration."""
from __future__ import annotations

from homeassistant.const import Platform

DOMAIN = "huawei_home_storage"
MANUFACTURER = "Huawei"
MODEL = "Home Storage (AS6020-02)"

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
]

# ---------------------------------------------------------------------------
# 配置条目数据键
# ---------------------------------------------------------------------------
CONF_HOST = "host"                  # 设备局域网 IP（授权后自动从凭据的 httpsUrl 取得，可手动覆盖）
CONF_REFRESH_TOKEN = "refresh_token"  # 华为账号 refresh_token（长期）
CONF_DEVICE_ID = "device_id"        # 云侧存储设备 devId（授权时由云接口枚举得到）
CONF_DEV_MAC = "dev_mac"            # 本集成冒充的客户端 MAC，startService 用；留空则自动派生
CONF_PRODUCT = "product"            # 客户端主机名，startService 用
CONF_UID = "uid"                    # 华为账号 uid（从 id_token 解析）
CONF_USER = "user"                  # 设备侧用户标识（取凭据时由设备返回）
# 华为账号密码登录（登录实现自包含分发，不跳浏览器；不再依赖 huawei_smarthome）
CONF_LOGIN_METHOD = "login_method"
CONF_ACCOUNT = "account"            # 华为账号（手机号/邮箱）
CONF_PASSWORD = "password"          # 华为账号密码（同样存于配置条目）
CONF_SMART_SESSION = "smart_session"  # 账号模式下持久化的会话字段（续期/重启复用）
#: 验证码投递渠道（短信 or 已登录设备推送）；仅在华为返回多个渠道且需要
#: 用户选择时用到，不写入条目数据。
CONF_CHALLENGE_CHANNEL = "challenge_channel"
# 单条目多账号：entry.data[CONF_ACCOUNTS] 是一个「账号列表」
CONF_ACCOUNTS = "accounts"            # list[dict]，每个账号含 account/dev_mac/uid/user/session

LOGIN_METHOD_ACCOUNT = "account"    # 账号密码（登录实现随本仓库分发）
LOGIN_METHOD_DEVICE_CODE = "device_code"
# 以下均来自云端设备列表 devInfo，仅用于展示/设备注册，无需用户输入
CONF_DEVICE_MAC = "device_mac"      # 设备网卡 MAC（devInfo.mac）
CONF_DEVICE_SN = "device_sn"        # 设备序列号（devInfo.sn）
CONF_DEVICE_MODEL = "device_model"  # 设备型号（devInfo.model / hwv）

DEFAULT_PRODUCT = "home-assistant"

#: 配置条目的数据结构版本。
#: HA 用它决定是否调用 ``async_migrate_entry``；条目 version 高于本值时 HA 会
#: 直接拒绝加载（2026-10-06 踩过：条目被抬到 3 而本集成只支持 1，
#: 表现为条目读不出 data、配置流没有入口）。
ENTRY_VERSION = 1

# ---------------------------------------------------------------------------
# 华为账号 OAuth（设备码流程）
# ---------------------------------------------------------------------------
OAUTH_CLIENT_ID = "105739747"
OAUTH_CLIENT_SECRET = (
    "c556ae2544f62beb6bef3de49a7395ddbb07930f3efb4f3290f295c7dd1b8187"
)
OAUTH_SCOPE = "openid https://www.huawei.com/auth/account/base.profile"
OAUTH_DEVICE_CODE_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/device/code"
OAUTH_TOKEN_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/token"
OAUTH_UA = "okhttp/4.9.3"
# 授权页必须带 user_code，否则报 1102 user code is empty
OAUTH_VERIFY_URL = "https://oauth-login.cloud.huawei.com/oauth2/v3/device/verify"

# ---------------------------------------------------------------------------
# smarthome 云（凭据下发）
# ---------------------------------------------------------------------------
SMARTHOME_BASE = "https://smarthome.hicloud.com"
API_CLOUD_LOGIN = "/message-center/v1/login"
API_CLOUD_DEVICES = "/smart-life/v3/devices"
API_CLOUD_HOMES = "/home-manager/v1/homes"
CLOUD_PROD_ID = "KX01"              # 华为家庭存储的产品标识
CLOUD_APP = "MemoSpace"
CLOUD_CURVE = "secp256r1"

MQTT_HOST = "smarthome.hicloud.com"
MQTT_PORT = 8883
MQTT_CMD_TOPIC = "/smartHome/signaltrans/v2/categories/command"
MQTT_DEFAULT_TOPIC = "smarthome.notify.app.v1"
MQTT_TIMEOUT = 30

# ---------------------------------------------------------------------------
# 设备本地 API
# ---------------------------------------------------------------------------
DEVICE_UA = "okhttp/4.9.3"
DATA_UA = "Windows App/3.0.3.386"
DEVICE_PORT = 8471                  # 控制通道（Token + Cookie: ID=<session>）
DATA_PORT = 8472                    # 数据/图片通道（Token=dataToken + Cookie=dataSession）
DEVICE_CLIENT_TYPE = 3

API_HEARTBEAT = "/access/heartBeat"
API_ALBUM_LIST = "/gallery/getAlbumList"
API_ALBUM_INC = "/gallery/albumIncInfo"          # 增量表；集成未使用（见 API 清单）
API_PHOTOS_INC = "/gallery/getIncPhotosInfoTable"
API_QUERY_BIN = "/gallery/queryBin"
API_FILES = "/filesvc/files"
API_RECYCLE = "/filesvc/recycleFiles"
API_USB_STATUS = "/filesvc/usbStatus"
# 上传第一步：申请文件占位，返回 fileId + sessionId（实测 2026-10-08 可用）
API_PREPARE_UPLOAD = "/filesvc/prepareUpload"
# 取消上传（端点实测存在，2026-10-08）
API_CANCEL_UPLOAD = "/filesvc/cancelUpload"
# 文件空间批量操作（删除/移动等），靠 query 的 operation= 区分（实测 2026-10-08）
API_BATCH_OPERATION = "/filesvc/batchOperation"
# 建目录 / 重命名（抓包实据 + 基线实测 code 0，2026-10-08）
API_MKDIR = "/filesvc/mkdir"
API_RENAME = "/filesvc/rename"
# 全文件视图 / 文件详情 / 搜索（静态提取 + 实测端点存在）
API_FILES_ALL = "/filesvc/allFiles"
API_FILE_DETAIL = "/filesvc/detail"
API_FILE_SEARCH = "/filesvc/search"
# 传输任务：移动 / 复制 / 跨服务复制（抓包实据 2026-10-08）
API_TRANS_MOVE = "/trans/move"
API_TRANS_COPY = "/trans/copy"
API_TRANS_ACROSSCOPY = "/trans/acrosscopy"
API_DISK_CHANGE = "/devmanage/diskChange"
API_USER_MANAGE = "/account/userManageInfo"
API_USER_DATA = "/account/userDataStatisInfo"
# ---- 扩展能力（实测可用性见逆向笔记第 8 节）----
API_ONLINE_STATE = "/cfg/system/onlinestate"          # 固件/升级状态
API_DEVICE_INFO = "/cfg/system/device_info"           # CPU/序列号
API_DEVICE_STATUS = "/cfg/system/device_status"       # 运行态(CPU/温度/内存)
API_SAMBA_PUBLIC = "/api/app/publicsamba"
API_SAMBA_USER = "/api/app/usersamba"
API_AUTO_UPGRADE = "/cfg/system/autoupgrade"
API_WAN_INFO = "/cfg/system/wan_info_tmp"
API_OPERATION_DEVICE = "/dfx/getOperationDevice"
API_DEV_ERR_CODE = "/devmanage/devErrCode"
API_REPAIR_MODE_CHECK = "/devmanage/repairModeCheck"
API_FILES_RECENT = "/filesvc/recent"
API_FILES_ALL = "/filesvc/allFiles"
API_PLUGIN_INSTALLED = "/acelite/installed_infos"
API_DUP_QUERY = "/gallery/queryDuplicateScanData"
API_DUP_CTRL = "/gallery/ctrlDuplicateScanTask"
DUP_ACT_START = "start"
DUP_ACT_STOP = "stop"
API_DEL_MEDIA = "/gallery/delFile"                    # 进回收站(可逆)
API_RECOVER_MEDIA = "/gallery/recoverFile"            # 恢复
API_DEVICE_REBOOT = "/devmanage/deviceReboot"         # 用户显式触发
API_DISK_SLEEP = "/devmanage/diskSleep"
API_USB_PLUG_OUT = "/devmanage/usbPlugOut"

PHOTO_PAGE_SIZE = 500               # getIncPhotosInfoTable 固定每页 500

# 文件空间目录浏览（/filesvc/files）：必须带 Dest-File 请求头（目录路径的
# 全字节百分号编码，含尾斜杠），否则返回 1101。dirType=6 为用户文件视图。
FILE_FILES_DIR_TYPE = 6
FILE_FILES_CATEGORY = "user"
FILE_FILES_SORT = "timeDesc"
FILES_PAGE_SIZE = 200               # filesvc/files 单页上限
# ⚠️ 设备硬上限：实测 num=500 可用，num=1000 起报 30101（越界）
ALBUM_PAGE_SIZE = 500             # 相册照片单页（getAlbumInfo 的 num 上限 500）
# filesvc/files 的条目 type：2 文件夹 / 4 相册 / 6 应用 / 8 普通文件
FILE_TYPE_DIR = 2
FILE_TYPE_ALBUM = 4
FILE_TYPE_APP = 6
FILE_TYPE_FILE = 8
FILE_ROOT_PATH = "/file/"           # 文件空间根目录（Dest-File 用，必须带尾斜杠）

# ---- 备份目标（backup.py）----
CONF_BACKUP_DIR = "backup_dir"        # 备份存放目录（默认 /file/HomeAssistant/）
CONF_BACKUP_SPACE = "backup_space"    # user = 我的文件；public = 共享
DEFAULT_BACKUP_DIR = "/file/HomeAssistant/"
BACKUP_META_SUFFIX = ".ha-backup.json"  # 与 tar 同名的边车元数据（列出备份时只读它）
DATA_BACKUP_AGENT_LISTENERS = "huawei_home_storage_backup_agent_listeners"  # 备份目标监听器

# 相册类型（getAlbumList albumType）
ALBUM_TYPE_ALL = 0                  # 0 = 返回全部相册（推荐）
ALBUM_TYPE_SYS_ALL = 1              # 所有照片（albumId=1）
ALBUM_TYPE_SYS_VIDEO = 2            # 视频（albumId=2）
ALBUM_TYPE_USER = 6                 # 用户/相册（含“照片”总相册）
ALBUM_TYPE_TRASH = 7                # 最近删除（albumId=-1）
ALBUM_TYPE_PLACE = 22               # 地点
ALBUM_TYPE_FACE = 23                # 人脸 / 人物
ALBUM_TYPE_SCENE = 24               # 场景

ALBUM_TYPE_NAMES = {
    ALBUM_TYPE_USER: "用户相册",
    ALBUM_TYPE_TRASH: "最近删除",
    ALBUM_TYPE_PLACE: "地点",
    ALBUM_TYPE_FACE: "人物",
    ALBUM_TYPE_SCENE: "场景",
}

MEDIA_TYPE_IMAGE = 1
MEDIA_TYPE_VIDEO = 3

# 8472 图片下载：/download + 全字节百分号编码的设备路径 + 固定查询串
DATA_DOWNLOAD_PATH = "/download"
DATA_DOWNLOAD_QUERY = "type=download&category=&usb=false&service=gallery&fileVer="

# 图片资源档位（assets[].name / 元数据字段名）
ASSET_THUMB = "thumb"
ASSET_LCD = "lcd"
ASSET_RAW = "raw"

# ---------------------------------------------------------------------------
# 实体归属范围
# ---------------------------------------------------------------------------
# 同一台物理设备可被多个华为账号接入。实测两账号下 22 个实体里有 16 个数值
# 完全相同（磁盘、在线、USB、用户数…）——这些是**设备自身属性**，与用哪个
# 账号登录无关，多账号时只应保留一份。
DEVICE_SCOPE = "device"
"""设备级：挂在主设备下，同一物理设备只注册一份。"""

ACCOUNT_SCOPE = "account"
"""账号级：与账号的可见范围有关（如各账号相册数不同），每个账号一份。"""

# ---------------------------------------------------------------------------
# 默认轮询
# ---------------------------------------------------------------------------
# 快轮询：在线 / 容量 / USB / 设备用户（轻量本地请求）
SCAN_INTERVAL_FAST_MINUTES = 1
# 慢轮询：相册统计（getAlbumList 全量 700+ 条，是集成里最重的请求）
SCAN_INTERVAL_SLOW_MINUTES = 10
# 兼容旧常量名
SCAN_INTERVAL_MINUTES = SCAN_INTERVAL_SLOW_MINUTES
REQUEST_TIMEOUT = 20

# ---------------------------------------------------------------------------
# 设备端用户 / USB / 磁盘
# ---------------------------------------------------------------------------
# /account/userManageInfo 的 level：1 = 管理员，2 = 家庭成员
USER_LEVEL_ADMIN = 1
USER_LEVEL_MEMBER = 2
# /devmanage/diskChange 的 availableState（实测 1 = 正常）
DISK_STATE_OK = 1
# 分盘位传感器的前缀（拼进 unique_id / 子设备标识）
DISK_SLOT_PREFIX = "disk_slot"

