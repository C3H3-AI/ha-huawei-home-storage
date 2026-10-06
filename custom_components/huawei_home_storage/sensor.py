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
from homeassistant.const import EntityCategory, UnitOfInformation
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
)


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
        coordinator = runtime.fast if description.data_key == "fast" else runtime.albums
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
                runtime.fast if description.data_key == "fast" else coordinator
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
