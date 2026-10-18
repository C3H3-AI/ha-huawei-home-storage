# 家庭存储 · 相册上传协议逆向记录（未完成，存档用）

日期：2026-10-18
状态：**协议结构已破解，真机未跑通（`code=30104`）**
素材：`home_datacenter.apk`（家庭存储插件，45,183,177 字节）
解包产物：`plugin_re/dc/`（32,443 smali，**完整无空文件**）

> ⚠️ 解包陷阱：`/tmp` 是 tmpfs 且容易写满 —— 满盘解包会产生 37% 空文件，
> `grep` 全无输出但看起来"解包成功"。**必须解到真实磁盘**（本项目用
> `/media/duola/devdata/...`）。校验方法：`find . -name "*.smali" -size 0 | wc -l` 应为 0。

---

## 1. 结论先行

设备存在**第二套上传域** `/gallery/*`，与文件空间的 `/filesvc/*` 平行。
我们此前只用 `/filesvc/prepareUpload`，拿到的 fileId 属**文件域（288…）**，
而 `/gallery/addAlbumMemb` 只认**相册域（281…）** —— 这是「上传照片进相册」
一直失败（实测 `code=30101`）的**根因**：走错了域，不是参数问题。

---

## 2. 端点证据（`retrofit/api/TransmissionApi.smali`）

⚠️ **方法名不可信**：混淆导致方法名与端点错位（如 `preUploadGallery`
实际指向 `/gallery/prepareUpload`，但 `preUploadFile` 却指向
`/gallery/getAllTaskStatus`）。**必须解析注解，不能按方法名推断**。

正确解析结果：

| 方法 | 端点 |
|---|---|
| `filePrepare` / `filePrepareUpload` | `POST /filesvc/prepareUpload` |
| `galleryPrepare` / `galleryPrepareUpload` / `preUploadGallery` | `POST /gallery/prepareUpload` |
| `upload` / `uploadTask` | `POST /upload`（数据通道） |
| `getGalleryAllTask` | `POST /gallery/getAllTaskStatus` |
| `getFileServiceAllTask` | `POST /filesvc/getAllTaskStatus` |
| `getBackupRemotePath` | `GET /filesvc/backupDir` |

解析方法（可复用）：

```python
blocks = re.split(r'\.method ', smali_src)
for b in blocks[1:]:
    name = b.split('(')[0].strip()
    m = re.search(r'\.annotation runtime Lretrofit2/http/(\w+);\s*value = "([^"]+)"', b)
```

---

## 3. 请求体结构（`transmission2/model/PreUploadReqModel.smali`）

```java
class PreUploadReqModel {
    String deviceId;
    int    uploadType;      // <init>(I, String)
    List   dataList;        // initDataListFrom(List)
}

class PreUploadRequestInfo {   // ← 从 MainTaskInfo 逐字段复制
    String path, srcPath, viewPath, hash, sessionId;
    long   fileId, fileSize, taskId;
    int    fileVer, orientation;
}
```

**注意**：不是 `filesmanage/model/GalleryPrepareUploadRequestBean`（那是
`files`/`hdcPath`/`fileHash` 的另一套，用于别的调用路径）。用错模型 →
设备直接 `status=3 (PARAM_INVALID)`。

实测有效的请求体形状（`status` 从 3 变成业务码 30104，说明结构对了）：

```json
{"deviceId":"…","uploadType":1,
 "dataList":[{"path":"/DCIM/Camera/x.jpg","srcPath":"/win/C/tmp/x.jpg",
              "viewPath":"DCIM/Camera/x.jpg","fileId":0,"fileSize":41351,
              "fileVer":0,"hash":"<真实MD5>","orientation":0,
              "sessionId":"","taskId":0}]}
```

---

## 4. 数据通道 query（`transmission2/tasks/UploadTask.smali`）

App 实发 **18 个**（⚠️ **没有 `serviceType`**，之前多传被疑为问题之一）：

```
category clientType comment ctime deviceId fileId fileVer mediaType
mtime orientation service size sourceAlbum srcPath takenTime uploadType
usb viewPath
```

HTTP 头：`Content-Disposition` `Content-Range` `Dest-File` `File-Size`
`X-Session-ID` `Expect: 100-continue`（缺 Expect 直接 500）

`service` 取值来自 `MainTaskInfo.getNonNullServiceType().getName()` →
`ServiceType` 枚举（`transmission2/constant/ServiceType.smali`）：
`filesvc`/`FILE`、`gallery`/`GALLERY`、`safebox`/`SAFE_BOX`、`unknown`/`UNKNOWN`

---

## 5. 状态机（`transmission2/constant/PreStatus.smali`）

```
NO_CONFLICT=0  NAME_CONFLICT=1  FILE_EXISTED=2  PARAM_INVALID=3
INNER_ERROR=4  FILE_RENAMED=5  PATH_OCCUPIED=6  PREPARED=7
UPLOADING=8   NOT_SUPPORT=9   FILE_NAME_ILLEGAL=0xa
FILE_PRE_LOCAL_EXPIRED=0x64  ...SERVER_EXPIRED=0x65
DISK_PREPARATION=0x1fa5   INCORRECT_INPUT_PARAM=0x7595
```

`FILE_EXISTED` = 秒传命中（App 直接用已有 fileId 跳上传）。

---

## 6. 当前卡点

`/gallery/prepareUpload` 返回 **`code=30104`**（`code=0` 但业务失败）。

已排除：模型结构、路径格式、多余 query、字段类型、空 hash。
`30104` 在插件里**无定义**（`StorageErrorCode` 是空壳，只有 `OK`），
故属服务端业务码。

⚠️ 另见 `rename_media`(`/gallery/modifyFileAttr`) 也返回 30104 ——
可能是相册域的通用权限/参数码，未必只属于上传。

**下一步**：抓包（App 上传一张照片），拿到真实请求体即可定位。

---

## 7. 已实现（代码在 `repo/`，默认行为不变）

- `const.py`：`API_GALLERY_PREPARE_UPLOAD`、`SERVICE_TYPE_*` 枚举
- `transfer.py`：`upload_stream(service_type=…, file_bytes=…)`
  —— 默认仍 `SERVICE_TYPE_FILE`，**对现有上传零影响**
- `services.py`：`upload_to_album` 服务（未跑通前不要合入主干）

---

## 8. 复现步骤

```bash
URL="https://store-drcn.hispace.dbankcloud.com/dl/appdl/application/apk/9b/9b6efd101bd444eaa1c847b335e337e4/com.huawei.datacenter.2605141637.apk"
OUT=/media/duola/devdata/AI-workspace/.dsh-im/work/huawei/plugin_re
mkdir -p "$OUT" && curl -sL "$URL" -o "$OUT/home_datacenter.apk"
java -jar <apktool.jar> d -f --no-res -o "$OUT/dc" "$OUT/home_datacenter.apk"
find "$OUT/dc" -name '*.smali' -size 0 | wc -l   # 必须为 0
```

插件 URL 来源：App 数据库
`/data/user/0/com.huawei.smarthome/databases/SmartHome.db` 的
`PluginApkTable.url`（智慧生活打开设备页时自动下载）。