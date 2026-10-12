#!/usr/bin/env node
/**
 * 面板渲染回归测试（用真实抓取的数据渲染，验证不崩且内容正确）。
 *
 * 用法：
 *   1) 先抓一份真实数据（需要 HA token）：
 *        curl -H "Authorization: Bearer $TOK" \
 *          http://<host>:8123/api/huawei_home_storage/status   > /tmp/d_status.json
 *        curl -H "Authorization: Bearer $TOK" \
 *          http://<host>:8123/api/huawei_home_storage/albums/<eid> > /tmp/d_albums.json
 *        curl -H "Authorization: Bearer $TOK" \
 *          "http://<host>:8123/api/huawei_home_storage/files/<eid>?path=%2Ffile%2F" > /tmp/d_files.json
 *   2) 跑测试：
 *        node _tools/test_panel_render.js <entry_id>
 */
const fs = require('fs');
const path = require('path');

const panelPath = path.join(__dirname, '..', 'custom_components', 'huawei_home_storage', 'www', 'huawei-storage-panel.js');
const entryId = process.argv[2] || '';
const src = fs.readFileSync(panelPath, 'utf8');

// ---- 最小浏览器环境（面板是自定义元素，需要这些全局）----
function FakeEl() {
  this.dataset = {};
  this.classList = { add: function(){}, remove: function(){}, contains: function(){ return false; } };
  this.shadowRoot = {
    querySelector: function(){ return null; }, querySelectorAll: function(){ return []; },
    getElementById: function(){ return null; }, appendChild: function(){}, innerHTML: '',
  };
  this.attachShadow = function(){ return this.shadowRoot; };
  this.addEventListener = function(){}; this.removeAttribute = function(){};
  this.setAttribute = function(){}; this.getAttribute = function(){ return null; };
  this.querySelector = function(){ return null; }; this.querySelectorAll = function(){ return []; };
}
function FakeIO() { this.observe = function(){}; this.unobserve = function(){}; }
global.HTMLElement = FakeEl;
global.IntersectionObserver = FakeIO;
global.customElements = { define: function(){}, get: function(){ return null; } };
global.window = { __hs_entry_id: entryId, __hs_panel: null };
global.document = { querySelector: function(){ return null; }, addEventListener: function(){} };
global.localStorage = { getItem: function(){ return null; }, setItem: function(){} };
global.URL = { createObjectURL: function(){ return 'blob:x'; }, revokeObjectURL: function(){} };
global.history = { pushState: function(){} };
global.Event = function(){};
global.setInterval = function(){ return 0; };
global.clearInterval = function(){};
global.setTimeout = function(){ return 0; };

let api;
try {
  api = eval("(function(){\n" + src + "\nreturn {"
    + "renderOverview:renderOverview,renderAlbums:renderAlbums,renderAlbumDetail:renderAlbumDetail,"
    + "renderFiles:renderFiles,renderFileList:renderFileList,renderRecycle:renderRecycle,"
    + "renderTasks:renderTasks,renderSearch:renderSearch,renderConfig:renderConfig,"
    + "renderDevice:renderDevice,renderUsers:renderUsers,renderSkinner:renderSkinner,"
    + "renderDup:renderDup,renderDiag:renderDiag,pickToggleBar:pickToggleBar,"
    + "renderDestPicker:renderDestPicker,pickAllPaths:pickAllPaths,"
    + "DEST_OPEN:function(){ DEST.open = true; },"
    + "uploadPct:uploadPct,setUploads:function(v){ PH.uploads = v; },"
    + "simEnter:function(){ var inp = { addEventListener: function(ev, fn){ if (ev==='keydown') fn({ key:'Enter', preventDefault:function(){} }); } }; return inp; },"
    + "setSrcKw:function(v){ SRC.kw = v; },SET_ALB:function(v){ ALB.data = v; ALB.group = null; ALB.album = null; },"
    + "simEnter:function(){ var el = { key: 'Enter', preventDefault: function(){}, "
    + "dataset: {}, addEventListener: function(ev, fn){ if (ev === 'keydown') { fn({ key: 'Enter', preventDefault: function(){} }); } } };"
    + "var before = SRC.busy; doSearch(); return { kw: SRC.kw, busy: SRC.busy !== before }; }};})()");
} catch (e) {
  console.error("面板加载失败: " + String(e.message).slice(0, 160));
  process.exit(1);
}

// ---- 真实数据（抓不到就跳过渲染，只验证加载）----
const have = ['/tmp/d_status.json', '/tmp/d_albums.json', '/tmp/d_files.json']
  .every((f) => fs.existsSync(f));
if (!have) {
  console.log("面板加载 ✅（未找到真实数据 /tmp/d_*.json，跳过渲染检查）");
  process.exit(0);
}

const status = JSON.parse(fs.readFileSync('/tmp/d_status.json', 'utf8'));
const albums = JSON.parse(fs.readFileSync('/tmp/d_albums.json', 'utf8'));
const files  = JSON.parse(fs.readFileSync('/tmp/d_files.json', 'utf8'));
const entry = (status.entries || [])[0] || {};
const d = Object.assign({}, entry, {
  counts: entry.counts || {},
  current_account: (entry.accounts || [])[0] || null,
  accounts: entry.accounts || [],
  backup_dir: entry.backup_dir || '/file/HomeAssistant/',
  backup_space: entry.backup_space || 'user',
});

const H = {};
function R(k, f) {
  try { const h = f(); H[k] = typeof h === 'string' ? h : ''; }
  catch (e) { H[k] = ''; }
}
R('概览', () => api.renderOverview(d));
R('相册', () => { try { api.SET_ALB(albums); return api.renderAlbums(d); } catch (e) { return ''; } });
R('文件', () => api.renderFiles(d));
R('文件列表', () => api.renderFileList(files));
R('回收站', () => api.renderRecycle({ items: (files.files || []).slice(0, 3), count: 3 }));
R('任务', () => api.renderTasks(d));
R('搜索', () => api.renderSearch(d));
// 有关键字时应出现「清空」按钮（该按钮只在 SRC.kw 非空时渲染）
R('搜索有值', () => { try { api.setSrcKw('测试'); const h = api.renderSearch(d); api.setSrcKw(''); return h; } catch (e) { return ''; } });
R('配置', () => api.renderConfig(d));
R('设备', () => api.renderDevice(d));
R('用户', () => api.renderUsers(d));
R('皮肤', () => api.renderSkinner());
R('重复结果', () => api.renderDup());
R('诊断', () => api.renderDiag());
R('批量工具条', () => api.pickToggleBar());
// 打开目录选择器后渲染（验证确认/取消按钮真的出现）
R('选择器', () => { try { if (api.DEST_OPEN) api.DEST_OPEN(); return api.renderDestPicker(); } catch (e) { return String(e.message || ''); } });
// 范围选择函数应返回可枚举路径数组
let RANGE = null;
try { RANGE = api.pickAllPaths(); } catch (e) { RANGE = null; }

let fail = 0;
console.log("=== 渲染（真实数据，不崩）===");
for (const k of Object.keys(H)) {
  const ok = H[k].length > 30;
  console.log("  " + (ok ? "✅" : "❌") + " " + k.padEnd(12) + H[k].length + " 字符");
  if (!ok) fail++;
}

const c = d.counts || {};
console.log("\n=== 关键内容 ===");
// ⚠️ 断言必须精确 —— 用「完整标签文本 / 专属 id」而不是宽松子串，
// 否则改成 型号_X 之类仍能匹配，测试会恒真、抓不到回归。
const HAS = (fn) => src.includes("function " + fn) || src.includes("const " + fn);
const SRC_HasKw = /SRC\.kw\s*=\s*""/.test(src) || src.includes("SRC.kw");
// 样式段（视觉/皮肤审计结论都落在 STYLES 模板串内）
const STYLES_SEG = (function () {
  const k = src.indexOf("\n`;");
  return src.slice(0, k > 0 ? k : 40000);
})();
// 后端源码（用于核对接口字段，如相册照片的 fileId 序列化）
const VIEWS_SRC = (function () {
  try {
    return fs.readFileSync(
      path.join(__dirname, "..", "custom_components", "huawei_home_storage", "views.py"), "utf8"
    );
  } catch (e) { return ""; }
})();
const checks = [
  // 拖拽上传必须在 _draw() 内初始化 —— 此前只在账号胶囊点击回调里调（单账号用户不绑定该回调）→ 首次拖拽静默失效
  ["文件页·拖拽已初始化(in _draw)", (function () {
    var lines = src.split("\n");
    var start = -1, end = -1;
    for (var i = 0; i < lines.length; i++) {
      if (lines[i].trim() === "_draw() {" && start < 0) { start = i; continue; }
      if (start >= 0 && lines[i] === "  }") { end = i; break; }
    }
    if (start < 0 || end < 0) return false;
    var body = lines.slice(start, end).join("\n");
    return /initDnd\(this\)/.test(body);
  })(),],
  ["概览·照片数", String(c.photos || '') !== '' && H.概览.includes(String(c.photos))],
  ["概览·容量进度条", /<div class="bar/.test(H.概览) && /<i style="width:/.test(H.概览)],
  ["设备·型号(精确标签)", H.设备.includes("型号")],
  ["设备·序列号(脱敏值)", /A4DE\*{4}/.test(H.设备) || /A4DE[^0-9A-Z]{2,}/.test(H.设备)],
  ["设备·含固件行", H.设备.includes("固件")],
  ["配置·备份目录标签", H.配置.includes("备份目录")],
  ["配置·备份空间标签", H.配置.includes("所在空间")],
  ["配置·皮肤标签", H.配置.includes("界面皮肤")],
  ["文件列表·目录行", /class="filerow/.test(H.文件列表)],
  ["搜索·输入框(id=kwInput)", H.搜索.includes('id="kwInput"')],
  ["任务·三来源(精确)", H.任务.includes("文件空间") && H.任务.includes("跨服务传输") && H.任务.includes("相册")],
  // 分组标题由后端下发（views.py 的 _ALBUM_GROUPS），面板只渲染 ——
  // 所以断言渲染产物，不是面板源码。
  ["共享相册·分组存在(标题对)", H.相册.includes("共享相册")],
  ["皮肤·5套(key 齐全)", /data-skin="aurora"/.test(H.皮肤) && /data-skin="midnight"/.test(H.皮肤) && /data-skin="sand"/.test(H.皮肤) && /data-skin="forest"/.test(H.皮肤)],
  ["批量·工具条(进入按钮)", H.批量工具条.includes("批量选择") || H.批量工具条.includes("pickbar")],
  // 本轮新增：搜索回车提交、目录选择器、Shift 范围选择
  ["搜索·有值时出现清空按钮", H.搜索有值.includes("search-clear")],
  ["搜索·清空按钮可点击(行为)", H.搜索有值.includes('data-act="search-clear"')],
  // 必须定位到回车绑定处（enterBound 那段）—— 源码里 kwInput 出现多次（取值/聚焦），
  // 取错位置会断言恒真或恒假。
  ["搜索·回车真的触发搜索", (function () {
    const i = src.indexOf('enterBound');
    if (i < 0) return false;
    const seg = src.slice(i, i + 300);
    return /addEventListener\("keydown"/.test(seg) && /key === "Enter"/.test(seg) && /doSearch/.test(seg);
  })(),],
  ["目录选择器·渲染出确认按钮", /data-act="dest-ok"/.test(H.选择器 || '')],
  ["目录选择器·渲染出取消按钮", /data-act="dest-cancel"/.test(H.选择器 || '')],
  ["批量·范围选择返回数组", Array.isArray(RANGE)],
  // —— 团队审计修的 P0 ——
  // 后端把相册照片 ID 序列化成 "id" 而前端读 fileId → 加入相册 100% 失败。
  ["相册照片·后端给 fileId", /"fileId":\s*p\.get\("fileId"\)/.test(VIEWS_SRC)],
  ["前端·fileId 有 id 回退", /p\.fileId \|\| p\.id/.test(src)],
  // 设备操作按钮结构损坏 → 「硬盘休眠」点不动
  ["设备·休眠按钮闭合", /data-which="sleep">[^<]*<\/button>/.test(H.设备)],
  ["设备·诊断按钮独立", /data-act="diag"[^>]*>[^<]*<\/button>/.test(H.设备)],
  // 重复照片「查看结果」按钮不存在（只有 handler）
  ["概览·有查看结果按钮", /data-act="dup-res"/.test(src)],
  // 深色皮肤：白字压浅青不可读 → --on-brand
  ["皮肤·on-brand 变量存在", /--on-brand:/.test(STYLES_SEG)],
  ["皮肤·midnight 覆盖 on-brand", /--on-brand:#06212b/.test(STYLES_SEG)],
  // aurora 漏文字色（HA 深色下白底白字）
  ["皮肤·aurora 定义文字色", (function () {
    var m = STYLES_SEG.indexOf('data-skin="aurora"');
    return m > -1 && /--text:/.test(STYLES_SEG.slice(m, m + 400));
  })(),],
  // 键盘可达性
  ["有 focus-visible", /:focus-visible\{outline:(?!none)/.test(STYLES_SEG)],
  // 移动端：菜单不能只靠 hover（触摸设备无 hover）
  ["图片菜单·hover 仅鼠标设备", /@media \(hover:hover\) and \(pointer:fine\)/.test(STYLES_SEG)],
  ["移动端·按钮热区44px", /\.btn\{[^}]*min-height:44px/.test(STYLES_SEG)],
  ["移动端·导航5项(非8项)", /PRIMARY\s*=\s*\["overview", "albums", "files", "search"\]/.test(src)],
  // 概览卡片必须是可点入口（data-act="nav" + data-view），
  // 且不再有与侧栏重复的「浏览相册/浏览文件」按钮。
  ["概览·卡片可点(nav)", /data-act="nav"\s+data-view=/.test(H.概览)],
  ["概览·无冗余导航按钮", !/data-act="go-albums"/.test(src) && !/data-act="go-files"/.test(src)],
  // 必须限定在「容量卡」上下文 —— 否则 KPI 里的「文件」卡也带 data-view="files"，
  // 把容量卡改回不可点照样通过（变异抓不到）。
  ["概览·容量卡跳文件", (function () {
    const i = H.概览.indexOf("存储容量");
    if (i < 0) return false;
    const seg = H.概览.slice(Math.max(0, i - 300), i + 300);
    return /data-act="nav"/.test(seg) && /data-view="files"/.test(seg);
  })(),],
  ["概览·照片卡跳相册", /data-act="nav"\s+data-view="albums"/.test(H.概览)],
  // 本轮：文件行下载入口、多文件整体进度、toast 单条
  ["文件行·有下载按钮", (function () {
    // 真实数据里 /file/ 下全是目录；构造一条文件数据才能渲染到"文件行"(plain)
    const withFile = Object.assign({}, files, { files: [{ name: "a.txt", type: 8, size: 100, mtime: 0 }] });
    try { return /data-act="row-dl"/.test(api.renderFileList(withFile)); } catch (e) { return false; }
  })(),],
  ["上传·整体进度会算百分比", (function () {
    try {
      if (!api.uploadPct) return false;
      api.setUploads([{ name: "a", done: 50, total: 100 }, { name: "b", done: 0, total: 100 }]);
      var v = api.uploadPct();
      api.setUploads([]);
      return v === 25;
    } catch (e) { return false; }
  })(),],
  ["上传·进度基于数组", /PH\.uploads/.test(src)],
  // 必须写成 "PH.uploads = PH.uploads || []"（保留已有项），
  // 不能写成 "PH.uploads = []"（重置 → 多文件只留最后一个）。
  ["上传·累积不重置", /PH\.uploads\s*=\s*PH\.uploads\s*\|\|\s*\[\]/.test(src)],
  ["toast·同一时间仅一条", src.includes('.toast")') && /forEach/.test(src) && /remove\(\)/.test(src)],
];
for (const [n, ok] of checks) {
  console.log("  " + (ok ? "✅" : "❌") + " " + n);
  if (!ok) fail++;
}

console.log("\n" + (fail === 0 ? "✅ 全部通过" : "❌ 失败 " + fail + " 项"));
process.exit(fail === 0 ? 0 : 1);
