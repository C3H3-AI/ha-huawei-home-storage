"""Binary sensor platform for Huawei Home Storage."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_SCOPE
from .coordinator import HuaweiStorageData
from .entity import HuaweiStorageEntity, HuaweiStorageEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class HuaweiBinarySensorDescription(
    HuaweiStorageEntityDescription, BinarySensorEntityDescription
):
    """华为家庭存储二进制传感器描述。"""

    scope: str = DEVICE_SCOPE
    """在线状态与 USB 接入都是物理设备属性，挂在主设备下且只注册一份。"""


BINARY_SENSORS: tuple[HuaweiBinarySensorDescription, ...] = (
    HuaweiBinarySensorDescription(
        key="online",
        translation_key="online",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
    HuaweiBinarySensorDescription(
        key="usb",
        translation_key="usb",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up binary sensors.

    在线状态与 USB 接入都是**物理设备属性**，与账号无关；unique_id 挂在设备
    序列号上，多账号接入时 HA 注册表天然去重，只保留一份。
    """
    runtime: HuaweiStorageData = entry.runtime_data
    async_add_entities(
        HuaweiDeviceBinarySensor(runtime.fast, description, runtime)
        for description in BINARY_SENSORS
    )


class HuaweiDeviceBinarySensor(HuaweiStorageEntity, BinarySensorEntity):
    """设备在线状态与 USB 接入状态。"""

    entity_description: HuaweiBinarySensorDescription

    def __init__(
        self,
        coordinator: Any,
        description: HuaweiBinarySensorDescription,
        runtime: HuaweiStorageData,
    ) -> None:
        super().__init__(
            coordinator,
            description,
            coordinator.config_entry,
            runtime.main_device_id,
            runtime.primary_account or None,
        )

    @property
    def is_on(self) -> bool | None:
        data = self.coordinator.data
        if not data:
            return None
        if self.entity_description.key == "usb":
            usb = data.get("usb")
            if not isinstance(usb, dict) or "status" not in usb:
                return None
            return bool(usb.get("status"))
        return bool(data.get("online"))
