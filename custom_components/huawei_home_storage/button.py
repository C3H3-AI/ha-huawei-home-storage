"""Button platform for Huawei Home Storage.

三个动作都是**物理设备**操作（重启设备、磁盘休眠、弹出 USB），因此统一用
``DEVICE_SCOPE``：unique_id 挂在设备序列号上、不带账号前缀，多账号接入时
HA 注册表天然去重只保留一份。

只暴露**可恢复**的设备动作；关机/格式化/恢复出厂一律不提供。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DEVICE_SCOPE
from .coordinator import HuaweiStorageData
from .entity import HuaweiStorageEntity, HuaweiStorageEntityDescription

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class HuaweiButtonDescription(
    HuaweiStorageEntityDescription, ButtonEntityDescription
):
    """设备动作按钮描述。"""

    scope: str = DEVICE_SCOPE
    """重启/休眠/弹出 USB 都是物理设备动作，挂在主设备下且只注册一份。"""


BUTTONS: tuple[HuaweiButtonDescription, ...] = (
    HuaweiButtonDescription(
        key="disk_sleep",
        translation_key="disk_sleep",
        icon="mdi:sleep",
    ),
    HuaweiButtonDescription(
        key="usb_plug_out",
        translation_key="usb_plug_out",
        icon="mdi:usb-port",
    ),
    HuaweiButtonDescription(
        key="device_reboot",
        translation_key="device_reboot",
        icon="mdi:restart",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Any,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up buttons.

    设备动作与账号无关：``scope=DEVICE_SCOPE``，不传 account。
    """
    runtime: HuaweiStorageData = entry.runtime_data
    async_add_entities(
        HuaweiDeviceButton(runtime.fast, description, runtime)
        for description in BUTTONS
    )


class HuaweiDeviceButton(HuaweiStorageEntity, ButtonEntity):
    """可恢复的设备动作按钮。"""

    entity_description: HuaweiButtonDescription

    def __init__(
        self,
        coordinator: Any,
        description: HuaweiButtonDescription,
        runtime: HuaweiStorageData,
    ) -> None:
        super().__init__(
            coordinator,
            description,
            coordinator.config_entry,
            runtime.main_device_id,
        )

    async def async_press(self) -> None:
        """执行动作。"""
        client = getattr(self.coordinator, "client", None)
        if client is None:
            _LOGGER.error("设备客户端不可用")
            return
        key = self.entity_description.key
        try:
            if key == "disk_sleep":
                await client.async_post_disk_sleep()
            elif key == "usb_plug_out":
                await client.async_post_usb_plug_out()
            elif key == "device_reboot":
                await client.async_post_device_reboot()
        except Exception as err:  # noqa: BLE001
            _LOGGER.error("%s 执行失败: %s", key, err)
            return
        await self.coordinator.async_request_refresh()
