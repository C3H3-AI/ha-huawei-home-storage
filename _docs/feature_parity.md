# 功能对标：App 插件 vs 本集成

> 生成日期：2026-10-18
> 依据：`home_datacenter.apk`（家庭存储插件 45,183,177 B）解包后的 32,443 个 smali，
> 与本仓库 `const.py` 的 `API_*` 常量逐端点比对。

## 结论概览

| 指标 | 数量 |
|---|---|
| App 插件端点（`/gallery/*` + `/filesvc/*`） | **79**（gallery 53 / filesvc 26）|
| 本集成已实现端点 | **46**（gallery 28 / filesvc 18）|
| 交集（两边都有）| 45 |
| 表面缺口 | 34 |
| **其中已有等价功能**（别名/异域/异步版）| 17 |
| **真正缺失** | **17** |

即：**真实覆盖率 ≈ 79/(79+17) ≈ 82%**。

> ⚠️ "已有等价功能"的判定依据是端点语义，不代表行为完全一致；
> 标注为待实测的部分见下表状态列。

---

## 一、真正缺失的 17 个端点

### A. 相册推荐与智能整理（App 核心卖点）

| 端点 | 作用 | 价值 | 备注 |
|---|---|---|---|
| `/gallery/getRecommendAlbums` | 推荐相册 | 中 | App 首页「为你推荐」 |
| `/gallery/getNewRecommendInfo` | 新推荐信息 | 低 | |
| `/gallery/hideRecommendAlbum` | 隐藏推荐相册 | 低 | 需写操作 |
| `/gallery/getDynamicInfo` | 动态 / 时光轴 | **高** | App「回忆/动态」是差异��功能 |

**评估**：只读为主，风险低。`getDynamicInfo` 最值得先做。

### B. 重复照片完整流程（本集成目前只有 `duplicate_scan`）

| 端点 | 作用 | 风险 |
|---|---|---|
| `/gallery/autoMergeDuplicateMedia` | 自动合并重复照片 | 中（写）|
| `/gallery/delDuplicateMediaStart` | 启动删除重复项 | **高（不可逆删除）** |
| `/gallery/delDuplicateMediaResult` | 删除结果 | 只读 |
| `/gallery/queryDuplicateMergeResult` | 合并结果查询 | 只读 |

**评估**：`delDuplicateMediaStart` 属破坏性操作，若实现必须套用本仓库的
`_confirm_field()` 确认机制（见 PR #38）。

### C. 任务中心增强

| 端点 | 作用 | 价值 |
|---|---|---|
| `/gallery/retryTask` | 失败任务重试 | **高**（上传/同步失败只能干等）|
| `/gallery/getCapacitySupportStatus` | 容量支持状态 | 低 |

### D. 大批量同步（面板性能相关）

| 端点 | 作用 | 价值 |
|---|---|---|
| `/gallery/getFullPhotosInfoTable` | 全量照片信息表 | **高**（2.5 万张照片逐张拉取不可行）|
| `/gallery/getBatchPicsInfo` | 批量图片信息 | 中（减少往返）|

### E. 文件空间补充

| 端点 | 作用 | 价值 |
|---|---|---|
| `/filesvc/redundancy` | 冗余度 | 低 |
| `/filesvc/backupDir` | 备份远端路径 | 低 |
| `/filesvc/recoverProgress` | 恢复进度 | 中 |

### F. 重复扫描（filesvc 侧）

| 端点 | 作用 | 价值 |
|---|---|---|
| `/filesvc/ctrlDuplicateScanTask` | 控制扫描任务 | 中 |
| `/filesvc/getDuplicateFiles` | 查重复文件 | 中 |
| `/filesvc/queryDuplicateScanData` | 查扫描数据 | 中 |

---

## 二、判定为「已有等价功能」的 17 项（避免重复开发）

| App 端点 | 本集成对应 |
|---|---|
| `/filesvc/createDirs` | `create_folder` → `/filesvc/mkdir` |
| `/filesvc/remove` | `delete_paths` |
| `/filesvc/delRecentRecord` | `delete_paths`（最近记录）|
| `/filesvc/cleanTaskRecord` | `clean_task_records` |
| `/gallery/cleanBin` | `empty_recycle`（`recycleDelFiles?action=clear`）|
| `/gallery/cleanBinAsync` | 同上（异步版）|
| `/gallery/cleanRecord` | `clean_task_records` |
| `/gallery/cleanTaskRecord` | `clean_task_records` |
| `/gallery/recoverFileAsync` | `recover_recycle` |
| `/gallery/delFileAsync` | `delete_media` |
| `/gallery/getAllTask` | `get_task` / `all_trans_tasks` |
| `/gallery/getAllTaskStatus` | `task_status` |
| `/gallery/getTaskStatus` | 同上 |
| `/gallery/queryTaskProgress` | `task_status`（含进度）|
| `/gallery/getDuplicateFiles` | `duplicate_scan_result` |
| `/gallery/getSelAlbumsInfo` | `album_info` |

---

## 三、本集成独有（App 插件搜不到）

| 端点 | 来源 |
|---|---|
| `/filesvc/cancelUpload` | PCAP 抓包（App 插件里未搜到常量）|

另有 `/devmanage/*`、`/cfg/system/*`、`/api/app/*samba` 系列来自 PCAP
抓包，不在插件常量池内。

---

## 四、本机实测状态（AS6020-02，2026-10-17/18）

| 服务 | 实测结果 |
|---|---|
| `list_all_albums` / `album_info` / `album_photos` | ✅ 可用 |
| `device_diagnostics` / `installed_plugins` / `recent_files` | ✅ 可用 |
| `all_trans_tasks` / `list_recycle` / `task_status` | ✅ 可用 |
| `disk_info` | ❌ 两端点均 `code=1` |
| `raid_status` | ❌ `code=22`（非 RAID 机型，符合预期）|
| `search_album_photos` | ❌ `/gallery/search` `code=1` |
| `rename_media` | ❌ `code=30104` |
| `hide_albums` | ❌ `code=30102` |
| `remove_album_members` | ❌ `code=30110` |

> `30104` 同时出现在 `rename_media` 与 `/gallery/prepareUpload`，疑似相册域
> 通用错误码（权限或参数族），详见 `_docs/gallery_upload_reverse.md`。

---

## 五、建议实施顺序

1. **`getDynamicInfo`**（动态/时光轴）—— 只读，价值高，无风险
2. **`getFullPhotosInfoTable`**（全量照片表）—— 解锁面板批量加载
3. **`retryTask`**（任务重试）—— 实用性高
4. **`getRecommendAlbums`**（推荐相册）—— 只读
5. B 组重复照片流程 —— 破坏性，需确认机制 + 充分实测

---

## 六、方法论备忘

**端点提取**（注意：方法名不可信，混淆会导致名实不符）：

```python
blocks = re.split(r'\.method ', smali_src)
for b in blocks[1:]:
    m = re.search(r'\.annotation runtime Lretrofit2/http/(\w+);\s*value = "([^"]+)"', b)
```

**解包陷阱**：`/tmp` 为 tmpfs，写满时 apktool 会静默产生空文件
（本次 37% smali 为 0 字节，`grep` 全部无输出却看似成功）。
必须解到真实磁盘并校验：

```bash
find "$OUT" -name '*.smali' -size 0 | wc -l   # 必须为 0
```
