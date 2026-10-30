"""Sensor platform for Huawei Home Storage.

沿用 ``synology_dsm`` 的做法：实体通过 :class:`EntityDescription` 声明式定义，
公共的 unique_id / device_info 逻辑集中在 :mod:`.entity` 的基类里。

容量单位：设备侧返回 MB，这里统一乘 1024² 转成**字节**上报，由 HA 自动换算
成 GB/TB（直接报 MB 会显示成 ``4000796 MB``，需要用户心算）。
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ACCOUNT_SCOPE,
    DEVICE_SCOPE,
    USER_LEVEL_ADMIN,
)
from .coordinator import HuaweiStorageData, megabytes_to_bytes
from .entity import (
    HuaweiStorageEntity,
    HuaweiStorageEntityDescription,
    _account_key,
    main_device_identifier,
    main_device_info,
)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class HuaweiSensorDescription(HuaweiStorageEntityDescription, SensorEntityDescription):
    """Describes a Huawei Home Storage sensor."""

    value_fn: Callable[[dict[str, Any]], Any]
    attrs_fn: Callable[[dict[str, Any]], Any] | None = None
    """可选附加属性（文件名/插件名列表），写进实体 attributes。"""
    data_key: str = "albums"
    """从哪个协调器取数据：``albums``（慢）或 ``fast``。"""
    unique_suffix: str = ""
    """unique_id 后缀。单位/含义变化时加版本号，让 HA 重建实体而非沿用旧属性。"""
    scope: str = ACCOUNT_SCOPE
    """``device`` = 物理设备属性（多账号共享，只注册一份）；``account`` = 与账号可见范围有关。"""


def _count(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda data: (data.get("counts") or {}).get(key)


def _disk(field: str) -> Callable[[dict[str, Any]], Any]:
    """磁盘字段求和；``diskChangeInfo`` 为多盘位列表。"""

    def _get(data: dict[str, Any]) -> int | None:
        slots = (data.get("disk") or {}).get("diskChangeInfo") or []
        values = [s.get(field) for s in slots if s.get(field) is not None]
        return megabytes_to_bytes(sum(values)) if values else None

    return _get


def _disk_usage(data: dict[str, Any]) -> float | None:
    total = (data.get("disk") or {}).get("diskChangeInfo") or []
    total_mb = sum(s.get("totalSize") or 0 for s in total)
    used_mb = sum(s.get("usedSize") or 0 for s in total)
    if not total_mb or not total:
        return None
    return round(used_mb / total_mb * 100, 1)


def _disk_free(data: dict[str, Any]) -> int | None:
    # _disk() 已经做过 MB → 字节换算，这里不要再乘一次
    total = _disk("totalSize")(data)
    used = _disk("usedSize")(data)
    if total is None or used is None:
        return None
    return max(total - used, 0)


def _usb_connected(data: dict[str, Any]) -> int | None:
    """``/filesvc/usbStatus`` → ``{"status": bool, "info": [...]}``。"""
    usb = data.get("usb")
    if not isinstance(usb, dict):
        return None
    return int(bool(usb.get("status")))


def _device_user_count(data: dict[str, Any]) -> int | None:
    users = data.get("device_users")
    return len(users) if isinstance(users, list) else None


def _device_admin_count(data: dict[str, Any]) -> int | None:
    users = data.get("device_users")
    if not isinstance(users, list):
        return None
    return sum(1 for u in users if u.get("level") == USER_LEVEL_ADMIN)


def _account_quota_used(data: dict[str, Any]) -> int | None:
    """当前账号在该设备上占用的空间（MB → 字节）。"""
    return megabytes_to_bytes((data.get("user_data") or {}).get("usedSize"))



def _firmware_version(data: dict[str, Any]) -> str | None:
    """``/cfg/system/onlinestate`` 的 ``Version``（实测 "6.1.0.7"）。

    比 update 服务的 ``version``（该设备上恒为 "NoVersion"）可靠；
    实测该设备两个来源：onlinestate=6.1.0.7，update.version=NoVersion。
    """
    version = (data.get("online_state") or {}).get("Version")
    if not version or version in ("NoVersion", "0", 0):
        return None
    return str(version)


def _upgrade_state(data: dict[str, Any]) -> str | None:
    """``/cfg/system/onlinestate`` 的 ``UpdateState``（实测 17）。

    ``CurrentUpgradeTime`` 实测 "2026-09-10 04:24:59"，UpdateState 语义
    未全部验证，故按原始值上报，不做映射。
    """
    state = (data.get("online_state") or {}).get("UpdateState")
    return None if state is None else str(state)


def _device_info_field(field: str) -> Callable[[dict[str, Any]], Any]:
    """``/cfg/system/device_info`` 的字段（payload 在 ``body`` 下）。"""

    def _get(data: dict[str, Any]) -> Any:
        value = ((data.get("device_info") or {}).get("body") or {}).get(field)
        return None if value in (None, "") else value

    return _get


def _status_field(field: str) -> Callable[[dict[str, Any]], Any]:
    """``/cfg/system/device_status`` 的运行态字段（payload 在 ``body`` 下）。"""

    def _get(data: dict[str, Any]) -> Any:
        value = ((data.get("device_status") or {}).get("body") or {}).get(field)
        return None if value is None else value

    return _get


def _memory(field: str) -> Callable[[dict[str, Any]], Any]:
    """内存字段（``MemTotal`` / ``MemFree``，单位 kB → 字节）。"""

    def _get(data: dict[str, Any]) -> int | None:
        body = (data.get("device_status") or {}).get("body") or {}
        value = body.get(field)
        if value is None:
            return None
        try:
            return int(value) * 1024
        except (TypeError, ValueError):
            return None

    return _get


def _memory_used(data: dict[str, Any]) -> int | None:
    """已用内存 = MemTotal - MemFree（均为 kB）。"""
    body = (data.get("device_status") or {}).get("body") or {}
    total, free = body.get("MemTotal"), body.get("MemFree")
    if total is None or free is None:
        return None
    try:
        return max(int(total) - int(free), 0) * 1024
    except (TypeError, ValueError):
        return None


def _recent_file_names(data: dict[str, Any]) -> list[str] | None:
    """最近文件的文件名列表（供实体 attributes 展示）。"""
    records = ((data.get("recent_files") or {}).get("data") or {}).get("records")
    if not isinstance(records, list):
        return None
    return [r.get("name") for r in records if isinstance(r, dict) and r.get("name")][:20]


def _plugin_names(data: dict[str, Any]) -> list[str] | None:
    """已装插件的名称列表。"""
    infos = ((data.get("plugins") or {}).get("data") or {}).get("hapInfos")
    if not isinstance(infos, list):
        return None
    return [p.get("name") for p in infos if isinstance(p, dict) and p.get("name")][:20]


def _data_len(key: str, field: str) -> Callable[[dict[str, Any]], Any]:
    """``data[key]["data"][field]`` 是列表时取其长度（None 表示不可用）。"""

    def _get(data: dict[str, Any]) -> int | None:
        value = ((data.get(key) or {}).get("data") or {}).get(field)
        return len(value) if isinstance(value, list) else None

    return _get


def _recent_files_count(data: dict[str, Any]) -> int | None:
    """最近文件条数（``data["recent_files"]["data"]["records"]``）。"""
    return _data_len("recent_files", "records")(data)


def _all_files_count(data: dict[str, Any]) -> int | None:
    """全部文件条数。"""
    return _data_len("all_files", "files")(data)


def _plugin_count(data: dict[str, Any]) -> int | None:
    """已装插件数量（插件列表在 ``data["plugins"]["data"]["hapInfos"]``）。"""
    return _data_len("plugins", "hapInfos")(data)


def _plain(key: str, field: str) -> Callable[[dict[str, Any]], Any]:
    """简单取值：``data[key][field]``。"""
    return lambda data: (data.get(key) or {}).get(field)


def _nested(key: str, field: str) -> Callable[[dict[str, Any]], Any]:
    """取值：``data[key]["body"][field]``。"""
    return lambda data: ((data.get(key) or {}).get("body") or {}).get(field)


def _dev_err(field: str) -> Callable[[dict[str, Any]], Any]:
    """设备错误码：``data["dev_err"]["data"][field]``。"""
    return lambda data: ((data.get("dev_err") or {}).get("data") or {}).get(field)


def _repair_mode(data: dict[str, Any]) -> Any:
    """维修模式：``data["repair_mode"]["data"]["mode"]``（0 = 正常）。"""
    return ((data.get("repair_mode") or {}).get("data") or {}).get("mode")


def _operation_device_count(data: dict[str, Any]) -> int | None:
    """访问过设备的客户端数量。"""
    devices = (data.get("operation_devices") or {}).get("operationDevice")
    return len(devices) if isinstance(devices, list) else None


def _auto_upgrade_window(data: dict[str, Any]) -> str | None:
    """自动升级时段，形如 ``03:00-05:00``。"""
    cfg = data.get("auto_upgrade") or {}
    start, end = cfg.get("StartTime"), cfg.get("EndTime")
    if start and end:
        return f"{start}-{end}"
    return None


def _dup_field(field: str) -> Callable[[dict[str, Any]], Any]:
    """重复照片统计（``queryDuplicateScanData`` 的 ``data`` 下）。

    实测：``{"code": 0, "data": {"scanCount": 0, "scanTotal": 0,
    "scanTaskStatus": 0, "mergeCount": 0, ...}}``
    """

    def _get(data: dict[str, Any]) -> Any:
        value = ((data.get("dup") or {}).get("data") or {}).get(field)
        return None if value is None else value

    return _get


SENSORS: tuple[HuaweiSensorDescription, ...] = (
    # --- 相册统计（慢协调器）---
    HuaweiSensorDescription(
        key="photos",
        scope=ACCOUNT_SCOPE,
        translation_key="photos",
        icon="mdi:image-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count("photos"),
    ),
    HuaweiSensorDescription(
        key="videos",
        scope=ACCOUNT_SCOPE,
        translation_key="videos",
        icon="mdi:video",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count("videos"),
    ),
    HuaweiSensorDescription(
        key="albums_user",
        scope=ACCOUNT_SCOPE,
        translation_key="albums_user",
        icon="mdi:folder-multiple-image",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count("user_albums"),
    ),
    HuaweiSensorDescription(
        key="albums_face",
        scope=ACCOUNT_SCOPE,
        translation_key="albums_face",
        icon="mdi:account-group",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count("face_albums"),
    ),
    HuaweiSensorDescription(
        key="albums_scene",
        scope=ACCOUNT_SCOPE,
        translation_key="albums_scene",
        icon="mdi:image-filter-hdr",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count("scene_albums"),
    ),
    HuaweiSensorDescription(
        key="albums_place",
        scope=ACCOUNT_SCOPE,
        translation_key="albums_place",
        icon="mdi:map-marker",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count("place_albums"),
    ),
    HuaweiSensorDescription(
        key="trash",
        scope=ACCOUNT_SCOPE,
        translation_key="trash",
        icon="mdi:delete-outline",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=_count("trash"),
    ),
    # --- 磁盘容量（快协调器，单位：字节）---
    # unique_suffix="_b"：0.4.0 之前以 MB 上报，0.5.0 改字节，让 HA 重建实体
    HuaweiSensorDescription(
        key="disk_total",
        scope=DEVICE_SCOPE,
        translation_key="disk_total",
        icon="mdi:harddisk",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        data_key="fast",
        unique_suffix="_b",
        value_fn=_disk("totalSize"),
    ),
    HuaweiSensorDescription(
        key="disk_used",
        scope=DEVICE_SCOPE,
        translation_key="disk_used",
        icon="mdi:harddisk",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        data_key="fast",
        unique_suffix="_b",
        value_fn=_disk("usedSize"),
    ),
    HuaweiSensorDescription(
        key="disk_free",
        scope=DEVICE_SCOPE,
        translation_key="disk_free",
        icon="mdi:folder",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        data_key="fast",
        unique_suffix="_b",
        value_fn=_disk_free,
    ),
    HuaweiSensorDescription(
        key="disk_usage",
        scope=DEVICE_SCOPE,
        translation_key="disk_usage",
        icon="mdi:chart-donut",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        data_key="fast",
        value_fn=_disk_usage,
    ),
    HuaweiSensorDescription(
        key="account_quota_used",
        scope=ACCOUNT_SCOPE,
        translation_key="account_quota_used",
        icon="mdi:account",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="fast",
        value_fn=_account_quota_used,
    ),
    # --- 设备信息（诊断类）---
    HuaweiSensorDescription(
        key="device_users",
        scope=DEVICE_SCOPE,
        translation_key="device_users",
        icon="mdi:account-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="fast",
        value_fn=_device_user_count,
    ),
    HuaweiSensorDescription(
        key="device_admins",
        scope=DEVICE_SCOPE,
        translation_key="device_admins",
        icon="mdi:shield-account",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="fast",
        value_fn=_device_admin_count,
    ),
    HuaweiSensorDescription(
        key="disk_slots",
        scope=DEVICE_SCOPE,
        translation_key="disk_slots",
        icon="mdi:nas",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="fast",
        value_fn=lambda data: len((data.get("disk") or {}).get("diskChangeInfo") or []) or None,
    ),
    HuaweiSensorDescription(
        key="usb_devices",
        scope=DEVICE_SCOPE,
        translation_key="usb_devices",
        icon="mdi:usb",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="fast",
        # 没有 USB 数据时返回 None（未知），不要用 `or None` 把 0 变成未知
        value_fn=lambda data: (
            len((data.get("usb") or {}).get("info") or [])
            if isinstance(data.get("usb"), dict)
            else None
        ),
    ),
    HuaweiSensorDescription(
        key="firmware_version",
        scope=DEVICE_SCOPE,
        translation_key="firmware_version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_firmware_version,
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="upgrade_state",
        scope=DEVICE_SCOPE,
        translation_key="upgrade_state",
        icon="mdi:update",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_upgrade_state,
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="cpu_model",
        scope=DEVICE_SCOPE,
        translation_key="cpu_model",
        icon="mdi:cpu-64-bit",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_device_info_field("CpuName"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="cpu_cores",
        scope=DEVICE_SCOPE,
        translation_key="cpu_cores",
        icon="mdi:cpu-64-bit",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_device_info_field("CpuCores"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="serial_number",
        scope=DEVICE_SCOPE,
        translation_key="serial_number",
        icon="mdi:identifier",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_device_info_field("SerialNumber"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="cpu_usage",
        scope=DEVICE_SCOPE,
        translation_key="cpu_usage",
        icon="mdi:cpu-64-bit",
        native_unit_of_measurement="%",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        data_key="fast",
        value_fn=_status_field("Cpuusage"),
    ),
        HuaweiSensorDescription(
        key="cpu_temperature",
        scope=DEVICE_SCOPE,
        translation_key="cpu_temperature",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        data_key="fast",
        value_fn=_status_field("Cputemp"),
    ),
        HuaweiSensorDescription(
        key="memory_total",
        scope=DEVICE_SCOPE,
        translation_key="memory_total",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="fast",
        value_fn=_memory("MemTotal"),
    ),
        HuaweiSensorDescription(
        key="memory_used",
        scope=DEVICE_SCOPE,
        translation_key="memory_used",
        icon="mdi:memory",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="fast",
        value_fn=_memory_used,
    ),
        HuaweiSensorDescription(
        key="duplicate_photos",
        translation_key="duplicate_photos",
        icon="mdi:image-multiple-outline",
        state_class=SensorStateClass.MEASUREMENT,
        data_key="albums",
        value_fn=_dup_field("scanCount"),
    ),
        HuaweiSensorDescription(
        key="duplicate_scan_status",
        translation_key="duplicate_scan_status",
        icon="mdi:magnify-scan",
        data_key="albums",
        value_fn=_dup_field("scanTaskStatus"),
    ),
        HuaweiSensorDescription(
        key="samba_public_enabled",
        scope=DEVICE_SCOPE,
        translation_key="samba_public_enabled",
        icon="mdi:folder-network",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_plain("samba_public", "AnonymousEnable"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="samba_user_enabled",
        translation_key="samba_user_enabled",
        icon="mdi:folder-network-outline",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_plain("samba_user", "Enable"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="auto_upgrade",
        scope=DEVICE_SCOPE,
        translation_key="auto_upgrade",
        icon="mdi:update",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_plain("auto_upgrade", "Enable"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="auto_upgrade_window",
        scope=DEVICE_SCOPE,
        translation_key="auto_upgrade_window",
        icon="mdi:clock-time-four",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_auto_upgrade_window,
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="ipv4_address",
        scope=DEVICE_SCOPE,
        translation_key="ipv4_address",
        icon="mdi:ip-network",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_nested("wan_info", "IPv4Addr"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="ipv6_address",
        scope=DEVICE_SCOPE,
        translation_key="ipv6_address",
        icon="mdi:ip-network-outline",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_nested("wan_info", "IPv6Addr2"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="operation_devices",
        scope=DEVICE_SCOPE,
        translation_key="operation_devices",
        icon="mdi:devices",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_operation_device_count,
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="error_code",
        scope=DEVICE_SCOPE,
        translation_key="error_code",
        icon="mdi:alert-circle-outline",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_dev_err("errorCode"),
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="repair_mode",
        scope=DEVICE_SCOPE,
        translation_key="repair_mode",
        icon="mdi:wrench",
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_repair_mode,
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="recent_files",
        translation_key="recent_files",
        icon="mdi:history",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_recent_files_count,
        attrs_fn=_recent_file_names,
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="all_files",
        translation_key="all_files",
        icon="mdi:file-multiple",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,

        value_fn=_all_files_count,
        data_key="info",
    ),
        HuaweiSensorDescription(
        key="installed_plugins",
        scope=DEVICE_SCOPE,
        translation_key="installed_plugins",
        icon="mdi:puzzle",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        data_key="info",
        value_fn=_plugin_count,
        attrs_fn=_plugin_names,
    ),
)


def _pick_coordinator(
    runtime: "HuaweiStorageData", description: Any, fallback: Any = None
) -> Any:
    """按 description.data_key 选协调器。

    ``info`` = 低频静态信息（固件/硬件/Samba/网络/统计），
    ``fast`` = 1 分钟运行态，其余（默认 ``albums``）走相册协调器。
    """
    key = description.data_key
    if key == "fast":
        return runtime.fast
    if key == "info":
        return runtime.info or fallback or runtime.albums
    return fallback if fallback is not None else runtime.albums


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors.

    * ``device`` scope —— 物理设备属性（磁盘/在线/USB/用户数），与账号无关，
      挂在主设备上只注册一份。
    * ``account`` scope —— 与账号可见范围有关（相册统计、账号占用），
      **每个接入的账号各一组**（实测 763 vs 185 个相册，视角确实不同）。
    """
    runtime: HuaweiStorageData = entry.runtime_data
    entities: list[SensorEntity] = []

    # 1) 设备级实体（一次）
    for description in SENSORS:
        if description.scope != DEVICE_SCOPE:
            continue
        coordinator = _pick_coordinator(runtime, description)
        entities.append(HuaweiHomeStorageSensor(coordinator, description, runtime))

    # 2) 盘位设备（物理属性，用硬盘序列号去重）
    for slot in _disk_slots(runtime):
        entities.extend(_slot_entities(runtime, slot))

    # 3) 账号级实体：每个账号一组
    for account in runtime.accounts or [None]:
        acct_key = _account_key(account)
        coordinator = runtime.album_coordinators.get(acct_key) or runtime.albums
        for description in SENSORS:
            if description.scope != ACCOUNT_SCOPE:
                continue
            coordinator_for_desc = (
                _pick_coordinator(runtime, description, fallback=coordinator)
            )
            entities.append(
                HuaweiHomeStorageSensor(
                    coordinator_for_desc, description, runtime, account=account
                )
            )

    async_add_entities(entities)


def _disk_slots(runtime: HuaweiStorageData) -> list[dict[str, Any]]:
    disk = (runtime.fast.data or {}).get("disk") or {}
    return [s for s in disk.get("diskChangeInfo") or [] if s.get("isExist")]


def _slot_entities(runtime: HuaweiStorageData, slot: dict[str, Any]) -> list[SensorEntity]:
    """按盘位生成容量传感器。

    ⚠️ 这些传感器**直接挂在主设备上**，不再每个盘位单独建一个设备节点
    （用户 2026-10-06 反馈：「硬盘就两个传感器，没必要单独设备出来，
    直接在存储设备里面显示好了」）。两块盘共 4 个实体，原来会多出
    2 个只有 2 个传感器的设备节点，在设备列表里很吵。

    做法与 core 的 ``reolink``（HDD 传感器）一致：
    实体挂宿主设备，用 ``translation_placeholders`` 的 ``{slot}`` 区分是几号盘。

    ``unique_id`` 仍以**硬盘序列号**为主体（物理属性）：同一盘位换盘会得到
    新实体，而不会把新盘的数据接到旧盘的统计历史上。
    """
    out: list[SensorEntity] = []
    raw_slot = slot.get("slot")
    slot_no = int(raw_slot) if raw_slot is not None else 0
    for field, key, translation in (
        ("totalSize", "total", "disk_slot_total"),
        ("usedSize", "used", "disk_slot_used"),
    ):
        desc = HuaweiSensorDescription(
            key=f"disk_slot{slot_no}_{key}",
            translation_key=translation,
            icon="mdi:harddisk",
            native_unit_of_measurement=UnitOfInformation.BYTES,
            device_class=SensorDeviceClass.DATA_SIZE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            entity_category=EntityCategory.DIAGNOSTIC,
            data_key="fast",
            value_fn=lambda data, f=field, s=slot_no: _slot_value(data, s, f),
        )
        out.append(
            HuaweiHomeStorageSensor(
                runtime.fast, desc, runtime, slot_no=slot_no, slot_sn=slot.get("sn")
            )
        )
    return out


def _slot_value(data: dict[str, Any], slot_no: int, field: str) -> int | None:
    for s in (data.get("disk") or {}).get("diskChangeInfo") or []:
        # 注意：slot=0 是合法值，不能写成 `s.get("slot") or -1`（falsy 陷阱）
        if s.get("slot") == slot_no and s.get("isExist"):
            return megabytes_to_bytes(s.get(field))
    return None


class HuaweiHomeStorageSensor(HuaweiStorageEntity, SensorEntity):
    """A Huawei Home Storage sensor."""

    entity_description: HuaweiSensorDescription

    def __init__(
        self,
        coordinator: Any,
        description: HuaweiSensorDescription,
        runtime: HuaweiStorageData,
        *,
        slot_no: int | None = None,
        slot_sn: str | None = None,
        account: dict[str, Any] | None = None,
    ) -> None:
        entry = coordinator.config_entry
        super().__init__(
            coordinator, description, entry, runtime.main_device_id, account
        )
        self._slot_no = slot_no
        if slot_no is None:
            return
        # 盘位传感器：挂在**主设备**下（不再单独建设备节点）。
        # - unique_id **沿用旧格式** ``{主标识}@disk:{硬盘SN}_{total|used}``：
        #   实体注册表按 unique_id 查得到旧记录，``async_get_or_create`` 会走
        #   ``_async_update_entity`` 把 device_id 改挂到主设备，**实体 ID 与历史
        #   统计都保留**，不会变成孤儿。序列号缺失时退回盘位号。
        # - 名字用 {slot} 占位符区分几号盘，翻译见 entity.sensor.disk_slot_*。
        identifier = f"{main_device_identifier(entry)[0]}@disk:{slot_sn or f'slot{slot_no}'}"
        self._attr_unique_id = f"{identifier}_{description.key.rsplit('_', 1)[-1]}"
        self._attr_translation_placeholders = {"slot": str(slot_no + 1)}
        self._attr_device_info = main_device_info(entry)

    @property
    def native_value(self) -> Any:
        if not self.coordinator.data:
            return None
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """附加属性（如最近文件/插件名列表）。"""
        fn = getattr(self.entity_description, "attrs_fn", None)
        if fn is None or not self.coordinator.data:
            return None
        try:
            value = fn(self.coordinator.data)
        except Exception:  # noqa: BLE001
            return None
        if isinstance(value, list):
            return {"items": value}
        if isinstance(value, dict):
            return value
        return None
