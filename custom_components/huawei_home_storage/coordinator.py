"""数据协调器。

拆成两个协调器（参照 HA 官方 ``synology_dsm`` 的分层做法）：

* :class:`HuaweiFastCoordinator` — 在线、磁盘容量、USB、设备端用户。
  都是轻量本地请求，1 分钟一次。
* :class:`HuaweiAlbumCoordinator` — 相册统计（``getAlbumList`` 全量 700+ 条，
  集成里最重的请求），10 分钟一次。

两者共用同一个 :class:`~.api.device.HuaweiDeviceClient`：设备会话是共享的，
「按需重取 + 401 自动重试」都封装在 client 内部。云端 startService 较贵，
所以只在快协调器建立会话时执行一次。

异常统一分类（对应 ``synology_dsm`` 的 ``raise_config_entry_auth_error``）：

* 凭据/账号彻底失效 → ``ConfigEntryAuthFailed``（HA 弹出重新认证）
* 设备不可达 / 其它设备错误 → ``UpdateFailed``（HA 按退避重试）
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    ConfigEntryAuthFailed,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import HuaweiDeviceAuthError, HuaweiDeviceClient, HuaweiDeviceError
from .const import (
    ALBUM_TYPE_ALL,
    ALBUM_TYPE_FACE,
    ALBUM_TYPE_PLACE,
    ALBUM_TYPE_SCENE,
    ALBUM_TYPE_SYS_ALL,
    ALBUM_TYPE_SYS_VIDEO,
    ALBUM_TYPE_TRASH,
    ALBUM_TYPE_USER,
    API_USER_MANAGE,
    DOMAIN,
    SCAN_INTERVAL_FAST_MINUTES,
    SCAN_INTERVAL_SLOW_MINUTES,
)

_LOGGER = logging.getLogger(__name__)


def _album_total(albums: list[dict[str, Any]], album_id: int) -> int | None:
    for album in albums:
        if album.get("albumId") == album_id:
            return int(album.get("num") or 0)
    return None


def megabytes_to_bytes(value: Any) -> int | None:
    """设备侧容量单位是 MB；转成字节交给 HA 自动换算成 GB/TB。

    旧版本直接以 ``UnitOfInformation.MEGABYTES`` 上报，界面显示
    ``4000796 MB`` 需要用户心算，这里统一改为字节。
    """
    if value is None:
        return None
    try:
        return int(value) * 1024 * 1024
    except (TypeError, ValueError):
        return None


@dataclass
class HuaweiStorageData:
    """配置条目的运行期数据（``entry.runtime_data``）。

    取代旧的 ``hass.data[DOMAIN][entry_id]`` 裸 dict：类型化、可静态检查、
    卸载时随条目一起释放。
    """

    client: HuaweiDeviceClient
    fast: HuaweiFastCoordinator
    albums: HuaweiAlbumCoordinator
    title: str
    info: "HuaweiInfoCoordinator | None" = None
    #: 主设备（按物理序列号）的 device_id。多账号共用同一台，实体据此挂载。
    main_device_id: str | None = None
    #: 本条目是否是该物理设备的**主条目**（同一台设备有多个账号时只让一个
    #: 条目注册设备级实体，避免磁盘/在线等被重复建多份）。
    is_primary: bool = True
    #: 账号键 → 该账号的相册协调器。单条目模式下每个接入的账号各有一个，
    #: 因为**不同账号可见的相册范围不同**（实测 763 vs 185 个相册）。
    album_coordinators: dict[str, HuaweiAlbumCoordinator] = field(default_factory=dict)
    #: 条目内全部账号（第一个是主账号/管理员）
    accounts: list[dict[str, Any]] = field(default_factory=list)
    #: 账号键 → 客户端（主账号的键为 ""）
    clients: dict[str, Any] = field(default_factory=dict)

    @property
    def primary_account(self) -> dict[str, Any]:
        return self.accounts[0] if self.accounts else {}

    def albums_of(self, album_type: int) -> list[dict[str, Any]]:
        """主账号（第一个）的相册，兼容旧调用方。"""
        return self.albums.albums_of(album_type)

    def albums_of_account(self, account_key: str, album_type: int) -> list[dict[str, Any]]:
        """指定账号的相册列表。"""
        coord = self.album_coordinators.get(account_key)
        return coord.albums_of(album_type) if coord else []

    def counts_of_account(self, account_key: str) -> dict[str, Any]:
        coord = self.album_coordinators.get(account_key)
        return (coord.data or {}).get("counts", {}) if coord else {}

    @property
    def data(self) -> dict[str, Any]:
        """合并视图：兼容旧代码里 ``coordinator.data`` 的读法。"""
        merged: dict[str, Any] = dict(self.fast.data or {})
        merged.update(self.albums.data or {})
        return merged

    @property
    def last_update_success(self) -> bool:
        ok = self.fast.last_update_success
        for coord in self.album_coordinators.values():
            ok = ok and coord.last_update_success
        return ok and self.albums.last_update_success


class _HuaweiBaseCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """公共部分：注入 ``config_entry`` + 统一异常分类。"""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: HuaweiDeviceClient,
        *,
        name: str,
        minutes: int,
    ) -> None:
        self.client = client
        self.title = entry.title
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}:{name}",
            update_interval=timedelta(minutes=minutes),
        )

    async def _run(self, label: str, coro: Any) -> Any:
        """执行单个采集动作，异常统一分类。"""
        try:
            return await coro
        except HuaweiDeviceAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except HuaweiDeviceError as err:
            _LOGGER.debug("%s 采集失败: %s", label, err)
            raise UpdateFailed(f"设备不可达: {err}") from err


class HuaweiFastCoordinator(_HuaweiBaseCoordinator):
    """在线 / 容量 / USB / 设备端用户（轻量，1 分钟）。"""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: HuaweiDeviceClient
    ) -> None:
        super().__init__(
            hass, entry, client, name="fast", minutes=SCAN_INTERVAL_FAST_MINUTES
        )

    async def _async_setup(self) -> None:
        """首次拉取前建立设备会话（走一遍云 startService，全局只做这一次）。"""
        await self.client.async_refresh_credentials()

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "online": False,
            "disk": None,
            "user_data": None,
            "usb": None,
            "device_users": None,
            "device_status": None,
        }
        data["online"] = await self._run("心跳", self.client.async_heartbeat())

        results = await asyncio.gather(
            self._run("磁盘", self.client.async_get_disk_info()),
            self._run("账号容量", self.client.async_get_user_data()),
            self._run("USB", self.client.async_get_usb_status()),
            self._run("设备用户", self._async_fetch_device_users()),
            self._run("运行状态", self.client.async_get_device_status()),
            return_exceptions=True,
        )
        for key, result in zip(
            ("disk", "user_data", "usb", "device_users", "device_status"), results
        ):
            if isinstance(result, BaseException):
                # 单项失败不应拖垮其它实体：沿用上一轮的值
                data[key] = (self.data or {}).get(key)
                _LOGGER.debug("%s 本轮不可用: %s", key, result)
            else:
                data[key] = result
        return data

    async def _async_fetch_device_users(self) -> list[dict[str, Any]]:
        """``/account/userManageInfo`` 返回**设备上的全部用户**（数组）。

        包含管理员与所有家庭成员，与「当前配置条目的账号」无关。
        """
        data = await self.client.async_get_device_users()
        return data if isinstance(data, list) else []




class HuaweiInfoCoordinator(_HuaweiBaseCoordinator):
    """静态/低频信息（10 分钟）：固件、硬件、Samba、网络、健康、文件与插件统计。

    这些端点单个都轻，但加起来有 8 个；不放 fast（1 分钟）是为了避免
    请求风暴触发设备会话保护（2026-10-06 教训：fast 20 请求/分钟导致
    gallery 域 16106，见逆向笔记 9.3）。
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: HuaweiDeviceClient
    ) -> None:
        super().__init__(
            hass, entry, client, name="info", minutes=SCAN_INTERVAL_SLOW_MINUTES
        )

    async def _async_update_data(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "online_state": None,
            "device_info": None,
            "samba_public": None,
            "samba_user": None,
            "auto_upgrade": None,
            "wan_info": None,
            "operation_devices": None,
            "dev_err": None,
            "repair_mode": None,
            "recent_files": None,
            "all_files": None,
            "plugins": None,
        }
        results = await asyncio.gather(
            self._run("升级状态", self.client.async_get_online_state()),
            self._run("设备信息", self.client.async_get_device_info()),
            self._run("公共Samba", self.client.async_get_samba_public()),
            self._run("用户Samba", self.client.async_get_samba_user()),
            self._run("自动升级", self.client.async_get_auto_upgrade()),
            self._run("网络信息", self.client.async_get_wan_info()),
            self._run("访问设备", self.client.async_get_operation_devices()),
            self._run("错误码", self.client.async_get_dev_err_code()),
            self._run("维修模式", self.client.async_get_repair_mode()),
            self._run("最近文件", self.client.async_get_recent_files()),
            self._run("全部文件", self.client.async_get_all_files()),
            self._run("已装插件", self.client.async_get_installed_plugins()),
            return_exceptions=True,
        )
        for key, result in zip(
            (
                "online_state", "device_info", "samba_public", "samba_user",
                "auto_upgrade", "wan_info", "operation_devices", "dev_err",
                "repair_mode", "recent_files", "all_files", "plugins",
            ),
            results,
        ):
            if isinstance(result, BaseException):
                data[key] = (self.data or {}).get(key)
                _LOGGER.debug("%s 本轮不可用: %s", key, result)
            else:
                data[key] = result
        return data


class HuaweiAlbumCoordinator(_HuaweiBaseCoordinator):
    """相册统计（慢，10 分钟）。

    相册服务（``/gallery/*``）与设备其它能力是**独立**的：实测设备相册库异常时
    ``getAlbumList`` 返回 ``{"code": 16106}``，而 heartBeat / diskChange /
    filesvc 均正常。因此这里失败时**只标记自身不可用**，不把整个条目拖进
    ``setup_retry`` —— 否则相册一挂，磁盘容量、在线状态等全部跟着消失。
    """

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: HuaweiDeviceClient
    ) -> None:
        super().__init__(
            hass, entry, client, name="albums", minutes=SCAN_INTERVAL_SLOW_MINUTES
        )
        #: 最近一次相册服务错误的描述（设备 /gallery/* 故障时非空）
        self.last_error: str | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        # albumType=0 一次返回全量系统/人物/地点/场景相册（不分页），但**不含用户
        # 相册（type=6）**，所以单独补取一次再合并去重。
        try:
            albums = await self._run(
                "相册列表", self.client.async_get_album_list(ALBUM_TYPE_ALL)
            )
            user_albums = await self._run(
                "用户相册", self.client.async_get_album_list(ALBUM_TYPE_USER)
            )
        except ConfigEntryAuthFailed:
            # 凭据/账号失效是全局问题，交给外层处理（会触发重新认证）
            raise
        except UpdateFailed as err:
            # 相册服务（/gallery/*）单独异常：保留上一轮数据 + 记录错误码，
            # 不把整个条目拖进 setup_retry（磁盘/在线/文件空间照常工作）。
            #
            # 已实测：设备相册服务整体故障时，全部 /gallery/* 端点都返回
            # {"code": 16106}，而 heartBeat / diskChange / filesvc 正常；
            # PC 客户端此时同样拿不到数据（其相册来自本地 gallery.db 缓存），
            # 说明这是设备侧状态，与凭据、deviceId、请求格式均无关。
            self.last_error = str(err)
            _LOGGER.warning("相册统计本轮不可用（设备相册服务异常，其它功能正常）: %s", err)
            data = dict(self.data or {"albums": {}, "counts": {}})
            data["gallery_error"] = str(err)
            return data

        self.last_error = None
        known = {(a.get("albumType"), a.get("albumId")) for a in albums}
        albums += [
            a for a in user_albums if (a.get("albumType"), a.get("albumId")) not in known
        ]

        buckets: dict[int, list[dict[str, Any]]] = {}
        for album in albums:
            buckets.setdefault(int(album.get("albumType") or 0), []).append(album)

        counts = {
            "photos": _album_total(albums, ALBUM_TYPE_SYS_ALL),
            "videos": _album_total(albums, ALBUM_TYPE_SYS_VIDEO),
            "user_albums": len(buckets.get(ALBUM_TYPE_USER, [])),
            "face_albums": len(buckets.get(ALBUM_TYPE_FACE, [])),
            "scene_albums": len(buckets.get(ALBUM_TYPE_SCENE, [])),
            "place_albums": len(buckets.get(ALBUM_TYPE_PLACE, [])),
            "trash": next(
                (
                    int(a.get("num") or 0)
                    for a in albums
                    if int(a.get("albumType") or 0) == ALBUM_TYPE_TRASH
                ),
                None,
            ),
        }
        # 重复照片扫描结果（POST，只读）。与相册同域，失败沿用上一轮值。
        try:
            dup = await self.client.async_query_duplicate_scan()
        except Exception as err:  # noqa: BLE001
            _LOGGER.debug("重复照片统计本轮不可用: %s", err)
            dup = (self.data or {}).get("dup")

        return {
            "albums": {ALBUM_TYPE_ALL: albums, **buckets},
            "counts": counts,
            "dup": dup,
        }

    def albums_of(self, album_type: int) -> list[dict[str, Any]]:
        return (self.data or {}).get("albums", {}).get(album_type, [])
