"""媒体源：在 HA 的媒体浏览器中浏览相册、最近删除与文件空间。

提供三棵树：
  - 相册树（``getAlbumList``，含封面）
  - 最近删除（``queryBin``，返回完整元数据含路径）
  - 文件空间（``/filesvc/files`` + ``Dest-File`` 头，NAS 文件视图，可逐层
    进入目录查看全部照片/视频/文档，文件条目带缩略图。注意文件空间与
    gallery 的照片计数不是同一集合）

文件空间标识符：``<entry>|files``（根）与
``<entry>|filedir|<offset>|<目录路径>``（分页 + 目录路径，路径含 ``/``，
所以整体标识符仍用 ``|`` 分隔、路径放最后一段）。
"""
from __future__ import annotations

from typing import Any

from homeassistant.components.media_player import BrowseError, MediaClass
from homeassistant.components.media_source import (
    BrowseMediaSource,
    MediaSource,
    MediaSourceItem,
    PlayMedia,
    Unresolvable,
)
from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    FILE_ROOT_PATH,
    FILE_TYPE_ALBUM,
    FILE_TYPE_APP,
    FILE_TYPE_DIR,
    FILE_TYPE_FILE,
    FILES_PAGE_SIZE,
)
from .coordinator import HuaweiStorageData
from .entity import _account_key
from .views import build_image_url

# 说明：下面的 ``runtime`` 就是 :class:`~.coordinator.HuaweiStorageData`
# （存于 ``hass.data[DOMAIN][entry_id]``）。它提供 ``client`` / ``albums_of`` /
# ``data`` / ``title``，与旧的单协调器实现保持兼容，因此这里不做强类型标注。

SEP = "|"
TRASH_PAGE_SIZE = 100
JPEG = "image/jpeg"


async def async_get_media_source(hass: HomeAssistant) -> MediaSource:
    """注册媒体源。"""
    return HuaweiHomeStorageMediaSource(hass)


def _join(*parts: Any) -> str:
    return SEP.join(str(p) for p in parts)


def _first_cover(album: dict[str, Any]) -> dict[str, Any]:
    """取相册的第一张有效封面。``coverInfo`` 里可能是 ``None`` 元素。"""
    for item in album.get("coverInfo") or []:
        if isinstance(item, dict):
            return item
    return {}


class HuaweiHomeStorageMediaSource(MediaSource):
    """家庭存储媒体源。"""

    name = "华为家庭存储"

    def __init__(self, hass: HomeAssistant) -> None:
        super().__init__(DOMAIN)
        self.hass = hass

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _entries(self) -> dict[str, Any]:
        return self.hass.data.get(DOMAIN, {}) or {}

    def _coordinator(self, entry_id: str) -> Any | None:
        return self._entries().get(entry_id)

    # ------------------------------------------------------------------
    # resolve
    # ------------------------------------------------------------------
    async def async_resolve_media(self, item: MediaSourceItem) -> PlayMedia:
        parts = (item.identifier or "").split(SEP)
        if len(parts) >= 3:
            runtime = self._coordinator(parts[0])
            if runtime is None:
                raise Unresolvable(f"配置条目不存在: {parts[0]}")
            rest = parts[1:]
            # 剥掉可选的账号段：<entry>|<acctKey>|photo|<设备路径>
            accounts = getattr(runtime, "accounts", None) or []
            known = {_account_key(a) for a in accounts} - {""}
            account_key = ""
            if rest and rest[0] in known:
                account_key = rest[0]
                rest = rest[1:]
            if rest and rest[0] == "photo":
                device_path = SEP.join(rest[1:])
                return PlayMedia(
                    build_image_url(parts[0], device_path, account=account_key),
                    _mime_for(device_path),
                )
        raise Unresolvable(f"无法解析的媒体标识: {item.identifier}")

    # ------------------------------------------------------------------
    # browse
    # ------------------------------------------------------------------
    async def async_browse_media(self, item: MediaSourceItem) -> BrowseMediaSource:
        identifier = item.identifier or ""
        if not identifier:
            return self._browse_root()
        parts = identifier.split(SEP)
        entry_id = parts[0]
        runtime = self._coordinator(entry_id)
        if runtime is None:
            raise BrowseError(f"配置条目不存在: {entry_id}")

        # 账号分叉：<entry>|<acctKey>|<section>…；不带 acctKey 的旧标识走主账号。
        rest = parts[1:]
        account_key = ""
        accounts = getattr(runtime, "accounts", None) or []
        known = {_account_key(a) for a in accounts} - {""}
        if rest and rest[0] in known:
            account_key = rest[0]
            rest = rest[1:]

        section = rest[0] if rest else ""
        if section == "":
            return self._browse_entry(entry_id, runtime, account_key)
        if section == "albums":
            return self._browse_albums(entry_id, runtime, account_key)
        if section == "album":
            return self._browse_album(entry_id, runtime, rest)
        if section == "files":
            return await self._browse_files(
                entry_id, runtime, FILE_ROOT_PATH, 0, account_key
            )
        if section == "filedir":
            # filedir|<offset>|<目录路径>：路径可能本身含 "|"（几乎不可能，
            # 但 SEP.join 兜底），offset 固定在 rest[1]
            offset = int(rest[1]) if len(rest) > 1 else 0
            dir_path = SEP.join(rest[2:]) or FILE_ROOT_PATH
            return await self._browse_files(
                entry_id, runtime, dir_path, offset, account_key
            )
        if section == "trash":
            offset = int(rest[1]) if len(rest) > 1 else 0
            return await self._browse_trash(entry_id, runtime, offset, account_key)
        raise BrowseError(f"未知标识: {identifier}")

    def _client_of(self, runtime: Any, account_key: str) -> Any:
        """取账号对应的设备客户端（无该账号时退回主账号）。

        各账号隧道端口不同（设备按 client 会话分配），所以图片/文件必须经
        对应账号的会话取，不能混用。
        """
        clients = getattr(runtime, "clients", None) or {}
        if account_key and account_key in clients:
            return clients[account_key]
        accounts = getattr(runtime, "accounts", None) or []
        if accounts:
            primary_key = _account_key(accounts[0])
            if primary_key in clients:
                return clients[primary_key]
        return runtime.client

    # -- 各级浏览 ----------------------------------------------------------
    def _browse_root(self) -> BrowseMediaSource:
        children = [
            BrowseMediaSource(
                domain=DOMAIN,
                identifier=entry_id,
                media_class=MediaClass.DIRECTORY,
                media_content_type="",
                title=coordinator.title,
                can_play=False,
                can_expand=True,
                children_media_class=MediaClass.DIRECTORY,
                thumbnail=None,
            )
            for entry_id, coordinator in self._entries().items()
        ]
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=None,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=self.name,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.DIRECTORY,
            thumbnail=None,
        )

    def _browse_entry(
        self, entry_id: str, runtime: Any, account_key: str = ""
    ) -> BrowseMediaSource:
        """条目根节点。多账号时先按账号分叉，每个账号下再分相册/文件/回收站。"""
        accounts = getattr(runtime, "accounts", None) or []
        if not account_key and len(accounts) > 1:
            # 账号分叉层
            children = []
            for index, account in enumerate(accounts):
                key = _account_key(account)
                masked = _mask_account(account.get("account"))
                counts = runtime.counts_of_account(key) if key else {}
                n_albums = len(runtime.albums_of_account(key, 0)) if key else 0
                children.append(
                    self._node(
                        _join(entry_id, key),
                        f"账号 {masked}" + ("（管理员）" if index == 0 else ""),
                        MediaClass.DIRECTORY,
                        f"{n_albums} 个相册" if n_albums else "",
                    )
                )
            return BrowseMediaSource(
                domain=DOMAIN,
                identifier=entry_id,
                media_class=MediaClass.DIRECTORY,
                media_content_type="",
                title=runtime.title,
                can_play=False,
                can_expand=True,
                children=children,
                children_media_class=MediaClass.DIRECTORY,
            )

        accounts = getattr(runtime, "accounts", None) or []
        main_key = _account_key(accounts[0]) if accounts else ""
        counts = runtime.counts_of_account(account_key or main_key)
        n_albums = len(self._albums_of(runtime, account_key, 0))
        prefix = _join(entry_id, account_key) if account_key else entry_id
        children = [
            self._node(
                _join(prefix, "albums"),
                "相册",
                MediaClass.DIRECTORY,
                f"共 {n_albums} 个相册" if n_albums else "",
            ),
            self._node(
                _join(prefix, "files"),
                "文件空间",
                MediaClass.DIRECTORY,
                "全部文件（NAS 视图）",
            ),
            self._node(
                _join(prefix, "trash", 0),
                "最近删除",
                MediaClass.DIRECTORY,
                f"{counts.get('trash') if counts.get('trash') is not None else '?'} 项",
            ),
        ]
        title = runtime.title
        if account_key:
            masked = _mask_account(
                next(
                    (a.get("account") for a in accounts if _account_key(a) == account_key),
                    "",
                )
            )
            title = f"{title} · {masked}"
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=prefix,
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.DIRECTORY,
        )

    def _albums_of(self, runtime: Any, account_key: str, album_type: int) -> list[Any]:
        """取指定账号的相册；未指定账号时用主账号。"""
        accounts = getattr(runtime, "accounts", None) or []
        key = account_key or (_account_key(accounts[0]) if accounts else "")
        if key:
            got = runtime.albums_of_account(key, album_type)
            if got:
                return got
        return runtime.albums_of(album_type)

    def _browse_albums(
        self, entry_id: str, runtime: Any, account_key: str = ""
    ) -> BrowseMediaSource:
        prefix = _join(entry_id, account_key) if account_key else entry_id
        albums = self._albums_of(runtime, account_key, 0)
        children = []
        for album in albums:
            album_type = int(album.get("albumType") or 0)
            album_id = album.get("albumId")
            cover = _first_cover(album)
            thumb = cover.get("thumbFilePath") or cover.get("lcdFilePath")
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=_join(prefix, "album", album_type, album_id),
                    media_class=MediaClass.ALBUM,
                    media_content_type="",
                    title=f"{album.get('albumName')}（{album.get('num', 0)}）",
                    can_play=False,
                    can_expand=True,
                    thumbnail=build_image_url(entry_id, thumb) if thumb else None,
                )
            )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_join(prefix, "albums"),
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title="相册",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.ALBUM,
        )

    def _browse_album(
        self, entry_id: str, runtime: Any, rest: list[str], account_key: str = ""
    ) -> BrowseMediaSource:
        prefix = _join(entry_id, account_key) if account_key else entry_id
        album_type = int(rest[1])
        album_id = int(rest[2])
        albums = self._albums_of(runtime, account_key, album_type)
        album = next(
            (
                a
                for a in albums
                if int(a.get("albumId") or 0) == album_id
            ),
            None,
        )
        if album is None:
            raise BrowseError(f"相册不存在: {album_type}/{album_id}")
        cover = _first_cover(album)
        children = []
        for field in ("hdcFilePath", "lcdFilePath", "thumbFilePath"):
            path = cover.get(field)
            if path:
                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=_join(prefix, "photo", path),
                        media_class=MediaClass.IMAGE,
                        media_content_type=JPEG,
                        title=f"{album.get('albumName')} · {field}",
                        can_play=True,
                        can_expand=False,
                        thumbnail=build_image_url(entry_id, path),
                    )
                )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_join(prefix, "album", album_type, album_id),
            media_class=MediaClass.ALBUM,
            media_content_type="",
            title=f"{album.get('albumName')}（{album.get('num', 0)}）",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.IMAGE,
            thumbnail=(
                build_image_url(entry_id, cover.get("thumbFilePath"))
                if cover.get("thumbFilePath")
                else None
            ),
        )

    async def _browse_files(
        self,
        entry_id: str,
        runtime: Any,
        dir_path: str,
        offset: int,
        account_key: str = "",
    ) -> BrowseMediaSource:
        """浏览文件空间目录（NAS 视图）。

        目录条目继续展开（拼出完整路径），文件条目可直接播放，
        由数据通道按完整路径取原图/视频。
        """
        prefix = _join(entry_id, account_key) if account_key else entry_id
        client = self._client_of(runtime, account_key)
        result = await client.async_list_files(
            dir_path=dir_path, offset=offset, limit=FILES_PAGE_SIZE
        )
        files = result.get("files") or []
        total = result.get("count")

        children: list[BrowseMediaSource] = []
        # 上一页
        if offset > 0:
            prev_off = max(0, offset - FILES_PAGE_SIZE)
            children.append(
                self._node(
                    _join(prefix, "filedir", prev_off, dir_path),
                    "◀ 上一页",
                    MediaClass.DIRECTORY,
                )
            )
        for entry in files:
            etype = entry.get("type")
            name = entry.get("name") or ""
            if etype in (FILE_TYPE_DIR, FILE_TYPE_ALBUM, FILE_TYPE_APP):
                sub_path = dir_path + name + "/"
                count = entry.get("count")
                subtitle = f"{count} 项" if count is not None else ""
                children.append(
                    self._node(
                        _join(prefix, "filedir", 0, sub_path),
                        name,
                        MediaClass.DIRECTORY,
                        subtitle,
                    )
                )
            else:
                # 文件条目：path 常为空 → 完整路径 = 当前目录 + name
                full_path = entry.get("path") or (dir_path + name)
                thumb = entry.get("thumb") or ""
                mtype = _mime_for(name)
                media_class = (
                    MediaClass.VIDEO if mtype.startswith("video") else MediaClass.IMAGE
                )
                children.append(
                    BrowseMediaSource(
                        domain=DOMAIN,
                        identifier=_join(prefix, "photo", full_path),
                        media_class=media_class,
                        media_content_type=mtype,
                        title=name,
                        can_play=True,
                        can_expand=False,
                        thumbnail=(
                            build_image_url(entry_id, thumb) if thumb else None
                        ),
                    )
                )
        # 下一页：优先用服务端 count；没有则按满页推断
        if (total is not None and offset + len(files) < total) or (
            total is None and len(files) >= FILES_PAGE_SIZE
        ):
            children.append(
                self._node(
                    _join(prefix, "filedir", offset + FILES_PAGE_SIZE, dir_path),
                    "下一页 ▶",
                    MediaClass.DIRECTORY,
                )
            )
        if not children:
            children.append(
                self._node(
                    _join(prefix, "filedir", 0, dir_path),
                    "（空目录）",
                    MediaClass.DIRECTORY,
                )
            )
        page_no = offset // FILES_PAGE_SIZE + 1
        title = dir_path.rstrip("/") or "文件空间"
        if page_no > 1:
            title = f"{title}（第 {page_no} 页）"
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_join(prefix, "filedir", offset, dir_path),
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=title,
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.DIRECTORY,
        )

    async def _browse_trash(
        self, entry_id: str, runtime: Any, offset: int, account_key: str = ""
    ) -> BrowseMediaSource:
        prefix = _join(entry_id, account_key) if account_key else entry_id
        client = self._client_of(runtime, account_key)
        items = await client.async_query_bin(
            offset=offset, num=TRASH_PAGE_SIZE
        )
        children = []
        for item in items:
            raw = item.get("hdcFilePath") or ""
            if not raw:
                continue
            thumb = item.get("thumbFilePath") or raw
            name = (item.get("fileSrcPath") or raw).rsplit("/", 1)[-1]
            children.append(
                BrowseMediaSource(
                    domain=DOMAIN,
                    identifier=_join(prefix, "photo", raw),
                    media_class=MediaClass.IMAGE,
                    media_content_type=JPEG,
                    title=name,
                    can_play=True,
                    can_expand=False,
                    thumbnail=build_image_url(entry_id, thumb),
                )
            )
        if len(items) >= TRASH_PAGE_SIZE:
            children.append(
                self._node(
                    _join(prefix, "trash", offset + TRASH_PAGE_SIZE),
                    "下一页 ▶",
                    MediaClass.DIRECTORY,
                    "",
                )
            )
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=_join(prefix, "trash", offset),
            media_class=MediaClass.DIRECTORY,
            media_content_type="",
            title=f"最近删除（第 {offset // TRASH_PAGE_SIZE + 1} 页）",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.IMAGE,
        )

    @staticmethod
    def _node(
        identifier: str,
        title: str,
        media_class: str,
        subtitle: str = "",
    ) -> BrowseMediaSource:
        return BrowseMediaSource(
            domain=DOMAIN,
            identifier=identifier,
            media_class=media_class,
            media_content_type="",
            title=f"{title} · {subtitle}" if subtitle else title,
            can_play=False,
            can_expand=True,
            thumbnail=None,
        )


def _mask_account(value: str | None) -> str:
    """账号脱敏（媒体源标题用）。"""
    if not value:
        return ""
    return value if len(value) <= 7 else f"{value[:3]}****{value[-4:]}"


def _mime_for(path: str) -> str:
    lower = path.lower()
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith((".mp4", ".mov")):
        return "video/mp4"
    return JPEG
