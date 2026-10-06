"""华为账号登录所需常量（移植自 ha-huawei-smarthome）。

来源：https://github.com/xiasi0/ha-huawei-smarthome
      commit 04fd6e8115c3d7bb30e5866b138b30fba7379b36 (2026-10-05)
许可：GPL-3.0（与上游一致；本仓库整体采用 GPL-3.0）

只保留账号密码登录主路径实际用到的常量，上游的设备/家庭/MQTT 相关
常量与本集成无关，未搬运。
"""

from __future__ import annotations

# --- 客户端身份（登录请求的 UA / 版本标识）---
SMART_HOME_APP_ID = "com.huawei.smarthome"
SMART_HOME_IOS_APP_ID = "com.huawei.smarthome-ios"
SMART_HOME_OAUTH_CLIENT_ID = "10406921"
SMART_HOME_ACCOUNT_VERSION = "69100"
SMART_HOME_ACCOUNT_CLIENT_VERSION = "ios_HwID_6.10.0.300"
SMART_HOME_ACCOUNT_USER_AGENT = (
    "SmartHome/17.0.3.320 CFNetwork/1335.0.3.4 Darwin/21.6.0"
)
SMART_HOME_USER_AGENT = "SmartHome/1.0.842 (iPhone; iOS 15.8.8; Scale/2.00)"

# --- 服务端点 ---
ACCOUNT_BASE_URL = "https://hwid-drcn.platform.hicloud.com"
OAUTH_BASE_URL = "https://oauth-login.platform.hicloud.com"
SMART_HOME_BASE_URL = "https://smarthome.hicloud.com"
HMS_LITE_TOKEN_PATH = "/smart-life/v2/hms-lite/token"

# --- 身份存储键 ---
# ⚠️ 必须使用本集成自己的命名空间，**绝不能**沿用上游的 "huawei_smarthome/..."。
#
# 2026-10-06 故障复盘（用户报告「huawei home smart 突然需要重新登录」）：
# 移植时为了「同一账号在两个集成间身份一致」而沿用了上游键名
# "huawei_smarthome/device_identity.json"，而该键正好等于上游
# domain=huawei_smarthome 集成（com.xiasi0 ha-huawei-smarthome）自己的
# IDENTITY_STORAGE_KEY。后果有两层，且都是真实的：
#
#   1. 文件层：两个集成读写同一个 .storage 文件。双方的 storage_lock() 各自
#      定义在自己模块里、互不可见，等于没有互斥；且我方
#      async_get_or_create() 每次调用都会重写该文件，承担了本不该承担的
#      写风险。
#   2. 云端层（更关键）：ClientIdentityStore 复用已有记录，于是本集成与上游
#      拿到**完全相同的 device_id / pushtmid / identity_fingerprint**——即对
#      华为云而言是同一个「伪装 iPhone 客户端」。同一客户端身份被两个集成
#      分别登录，会话互相顶掉，上游于是反复要求重新登录。
#
# 注意上游作者本人的新版（huawei_smarthome_author）也已把键改成
# "huawei_smarthome_author/..." 自行隔离——说明这是公认的坑，我们当时漏改了。
# 本集成现在使用独立命名空间，两个集成的 device_id 从此互不相干。
#
# 升级影响：本键变更后，各账号会生成全新 device_id，华为云端视为新客户端，
# 因此 0.8.x 升级到本版本后**需要重新登录一次**（首次刷新失败会走已保存的
# 账号密码自动重登；若触发短信验证码，见 config_flow 的渠道选择步骤）。
IDENTITY_STORAGE_KEY = "huawei_home_storage/device_identity.json"

# --- 会话模型 ---
UNASSIGNED_HOME_ID = "__unassigned__"
