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
    + "renderDup:renderDup,renderDiag:renderDiag,pickToggleBar:pickToggleBar};})()");
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
R('相册', () => api.renderAlbums(d));
R('文件', () => api.renderFiles(d));
R('文件列表', () => api.renderFileList(files));
R('回收站', () => api.renderRecycle({ items: (files.files || []).slice(0, 3), count: 3 }));
R('任务', () => api.renderTasks(d));
R('搜索', () => api.renderSearch(d));
R('配置', () => api.renderConfig(d));
R('设备', () => api.renderDevice(d));
R('用户', () => api.renderUsers(d));
R('皮肤', () => api.renderSkinner());
R('重复结果', () => api.renderDup());
R('诊断', () => api.renderDiag());
R('批量工具条', () => api.pickToggleBar());

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
const checks = [
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
  ["皮肤·5套(key 齐全)", /data-skin="aurora"/.test(H.皮肤) && /data-skin="midnight"/.test(H.皮肤) && /data-skin="sand"/.test(H.皮肤) && /data-skin="forest"/.test(H.皮肤)],
  ["批量·工具条(进入按钮)", H.批量工具条.includes("批量选择") || H.批量工具条.includes("pickbar")],
];
for (const [n, ok] of checks) {
  console.log("  " + (ok ? "✅" : "❌") + " " + n);
  if (!ok) fail++;
}

console.log("\n" + (fail === 0 ? "✅ 全部通过" : "❌ 失败 " + fail + " 项"));
process.exit(fail === 0 ? 0 : 1);
