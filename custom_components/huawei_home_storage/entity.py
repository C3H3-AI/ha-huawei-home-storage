"""统一实体基类：集中处理 unique_id / 设备归属 / 翻译。

参照 HA 官方 ``synology_dsm`` 的 ``entity.py`` 分层方式，把公共部分从
``sensor.py`` / ``binary_sensor.py`` 抽到这里，避免两个平台各写一份。

## 设备组织方式

以**物理设备**为条目，而不是以配置条目为单位：

```
家庭存储（序列号 SN-EXAMPLE-0001）        ← 主设备，identifier = 序列号
├── 账号 137****6363                       ← 子设备，via_device_id → 主设备
│   ├── 照片总数 / 磁盘容量 / 在线 …          （该账号可见的实体）
│   ├── 磁盘 1（SN WD-EXAMPLE-0001）        ← 孙级子设备（盘位）
│   └── 磁盘 2（SN WD-EXAMPLE-0002）
└── 账号 137****2663                       ← 另一子设备
    └── …
```

**为什么以序列号为主标识**：同一台物理设备可以被多个华为账号接入，但**物理上
只有一台**。早前用 ``entry_id`` 作标识，导致两个账号各生成一台设备、同两块盘
也各生成一次，设备列表被拆成 6 条。改用序列号后，多个账号自动汇聚到同一台
设备下，账号成为分支。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ACCOUNT_SCOPE,
    CONF_ACCOUNT,
    CONF_DEVICE_MODEL,
    CONF_DEVICE_SN,
    DEVICE_SCOPE,
    DOMAIN,
    MANUFACTURER,
    MODEL,
)

if TYPE_CHECKING:
    from .coordinator import _HuaweiBaseCoordinator


@dataclass(frozen=True, kw_only=True)
class HuaweiStorageEntityDescription(EntityDescription):
    """家庭存储通用实体描述。"""


def _mask(value: str | None) -> str:
    """账号脱敏：保留前 3 后 4 位。"""
    if not value:
        return ""
    return value if len(value) <= 7 else f"{value[:3]}****{value[-4:]}"


def _account_key(account: dict[str, Any] | None) -> str:
    """账号在条目内的稳定标识（unique_id / 协调器索引共用）。"""
    if not account:
        return ""
    return str(account.get("key") or account.get("account") or account.get("uid") or "")


def main_device_identifier(entry: Any) -> tuple[str, str]:
    """主设备标识与名称。

    优先用设备**序列号**（跨账号唯一标识同一台物理设备）；序列号缺失时
    退化用云侧 devId —— 两者都不是账号相关，天然满足「一台设备一台条目」。
    """
    sn = str(entry.data.get(CONF_DEVICE_SN) or "").strip()
    dev_id = str(entry.data.get("device_id") or "").strip()
    identifier = sn or dev_id or entry.entry_id
    return identifier, f"家庭存储 {sn}".strip() if sn else "家庭存储"


def account_device_identifier(entry: Any, account: dict[str, Any] | None = None) -> tuple[str, str]:
    """账号子设备标识与名称：``<主标识>@<账号key>``。

    单条目多账号模式下，``account`` 由调用方显式传入（``entry.data`` 顶层只
    保存主账号）；为空时回退到旧的单账号读法，保证向后兼容。
    """
    main_id, _ = main_device_identifier(entry)
    if account is not None:
        key = str(account.get("key") or account.get("account") or account.get("uid") or "")
        raw = str(account.get("account") or "")
    else:
        key = str(entry.data.get(CONF_ACCOUNT) or entry.data.get("uid") or "")
        raw = str(entry.data.get(CONF_ACCOUNT) or "")
    label = _mask(raw) or key
    return f"{main_id}@{key}", f"账号 {label}"


def main_device_info(entry: Any) -> DeviceInfo:
    """主设备信息。

    **不声明 MAC 连接**：华为路由器等集成也按 MAC 注册局域网设备，同一 MAC 被
    两处声明会抛 ``DeviceConnectionCollisionError`` 导致实体注册失败。
    MAC 仍保留在配置条目与侧边栏面板中展示。
    """
    identifier, name = main_device_identifier(entry)
    info = DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        name=name,
        manufacturer=MANUFACTURER,
        model=str(entry.data.get(CONF_DEVICE_MODEL) or MODEL),
    )
    if entry.data.get(CONF_DEVICE_SN):
        info["serial_number"] = entry.data[CONF_DEVICE_SN]
    return info


class HuaweiStorageEntity(CoordinatorEntity["_HuaweiBaseCoordinator"]):
    """所有家庭存储实体的基类。

    实体默认挂在**账号子设备**下（``<主标识>@<账号>``），由
    ``async_added_to_hass`` 通过 ``via_device_id`` 关联到主设备，实现
    「以设备为条目，账号按设备划分」。
    """

    _attr_has_entity_name = True

    entity_description: HuaweiStorageEntityDescription

    def __init__(
        self,
        coordinator: "_HuaweiBaseCoordinator",
        description: HuaweiStorageEntityDescription,
        entry: Any,
        main_device_id: str | None = None,
        account: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._entry = entry
        self._main_device_id = main_device_id
        self._account = account
        version_suffix = getattr(description, "unique_suffix", "")
        scope = getattr(description, "scope", ACCOUNT_SCOPE)
        if scope == DEVICE_SCOPE:
            # 设备级实体：unique_id 与 device_info 都挂在**物理设备**上
            # （不含 entry_id / 账号）。同一台设备无论多少账号接入，HA 注册表
            # 天然去重，只保留一份。
            info = main_device_info(entry)
            key = next(iter(info["identifiers"]))[1]
            self._attr_unique_id = f"{key}_{description.key}{version_suffix}"
        else:
            # 账号级实体：unique_id 含账号 key，多账号各一份
            info = account_device_info(entry, account)
            acct_key = (
                str((account or {}).get("key") or (account or {}).get("account") or "")
                or str(entry.data.get(CONF_ACCOUNT) or entry.entry_id)
            )
            self._attr_unique_id = (
                f"{entry.entry_id}_{acct_key}_{description.key}{version_suffix}"
            )
        if main_device_id and scope != DEVICE_SCOPE:
            # 设备级实体本身就属于主设备，无需 via
            info["via_device_id"] = main_device_id
        self._attr_device_info = info

    async def async_added_to_hass(self) -> None:
        """兜底：若构造时主设备还没就绪，这里再补一次 via_device_id。

        ⚠️ 若实体本身就**属于主设备**（如盘位容量传感器，`device_info` 就是主设备），
        再补 ``via_device_id`` 会让主设备变成自己的父设备（自引用），必须跳过。
        """
        await super().async_added_to_hass()
        if self._is_on_main_device():
            return
        if not (self._attr_device_info or {}).get("via_device_id"):
            self._attach_to_main_device()

    def _is_on_main_device(self) -> bool:
        """实体的 device_info 是否已经就是主设备本身。"""
        info = self._attr_device_info or {}
        return any(
            item[0] == DOMAIN and item[1] == main_device_identifier(self._entry)[0]
            for item in info.get("identifiers", [])
        )

    def _attach_to_main_device(self) -> None:
        """通过 ``via_device_id`` 关联主设备。"""
        from homeassistant.helpers import device_registry as dr

        registry = dr.async_get(self.hass)
        main = registry.async_get_device(
            identifiers={(DOMAIN, main_device_identifier(self._entry)[0])}
        )
        if main is None:
            return
        info = dict(self._attr_device_info or {})
        if info.get("via_device_id") == main.id:
            return
        info["via_device_id"] = main.id
        self._attr_device_info = info


def account_device_info(
    entry: Any, account: dict[str, Any] | None = None
) -> DeviceInfo:
    """账号子设备的 DeviceInfo（主设备信息 + 账号名）。"""
    identifier, name = account_device_identifier(entry, account)
    info = DeviceInfo(
        identifiers={(DOMAIN, identifier)},
        name=name,
        manufacturer=MANUFACTURER,
        model=str(entry.data.get(CONF_DEVICE_MODEL) or MODEL),
    )
    if entry.data.get(CONF_DEVICE_SN):
        info["serial_number"] = entry.data[CONF_DEVICE_SN]
    return info
