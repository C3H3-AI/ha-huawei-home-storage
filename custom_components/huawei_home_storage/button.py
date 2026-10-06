"""Button platform for Huawei Home Storage.

只暴露**可恢复**的设备动作；关机/格式化/恢复出厂/删除照片一律不提供。
重启按钮为用户显式触发（集成绝不自动重启）。
"""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import HuaweiStorageData
from .entity import HuaweiStorageEntity

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 1

BUTTONS: tuple[ButtonEntityDescription, ...] = (
    ButtonEntityDescription(
        key="disk_sleep",
        translation_key="disk_sleep",
        icon="mdi:sleep",
    ),
    ButtonEntityDescription(
        key="usb_plug_out",
        translation_key="usb_plug_out",
        icon="mdi:usb-port",
    ),
    ButtonEntityDescription(
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
    """Set up buttons."""
    runtime: HuaweiStorageData = entry.runtime_data
    async_add_entities(
        HuaweiDeviceButton(runtime.fast, description, runtime)
        for description in BUTTONS
    )


class HuaweiDeviceButton(HuaweiStorageEntity, ButtonEntity):
    """可恢复的设备动作按钮。"""

    entity_description: ButtonEntityDescription

    def __init__(
        self,
        coordinator: Any,
        description: ButtonEntityDescription,
        runtime: HuaweiStorageData,
    ) -> None:
        super().__init__(
            coordinator,
            description,
            coordinator.config_entry,
            runtime.main_device_id,
            runtime.primary_account or None,
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
