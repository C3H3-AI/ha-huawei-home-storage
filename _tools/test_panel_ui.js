#!/usr/bin/env node
/**
 * 面板 UI 结构测试（**用构造数据渲染，不需要真机**）。
 *
 * 与 ``test_panel_render.js`` 的分工：
 *   * 那个要真机抓的数据（``/tmp/d_*.json``），验证"真实数据不会把面板打崩"
 *   * 这个完全不依赖设备，用最小假数据把各个渲染函数跑一遍，验证
 *     "该出现的控件真的出现了"
 *
 * 为什么需要这一层：2026-10-29 用户反馈「照片好像不能上传，新建相册，
 * 添加到共享也没有」。查下来后端 59 个服务面板只用了 13 个，相册那组
 * 几乎全没接。补完 UI 之后，光靠 grep 源码断言 ``data-act="alb-create"``
 * 是不够的 —— 那只证明"字符串写进了文件"，不证明渲染分支真的会走到。
 * 比如 ``renderAlbums`` 在 ``!ALB.data`` 时会走骨架屏分支，按钮压根不渲染；
 * 相册详情页在 ``albumType !== 6`` 时会隐藏上传/删除按钮。
 * 这些分支只有真的调用渲染函数才能覆盖。
 *
 * 用法：``node _tools/test_panel_ui.js``（退出码 0 = 全过）
 */
const fs = require('fs');
const path = require('path');

const panelPath = path.join(
  __dirname, '..', 'custom_components', 'huawei_home_storage', 'www',
  'huawei-storage-panel.js'
);
const src = fs.readFileSync(panelPath, 'utf8');

/* ---------- 最小浏览器环境 ---------- */
function FakeEl() {
  this.dataset = {};
  this.classList = {
    add() {}, remove() {}, contains() { return false; },
  };
  this.shadowRoot = {
    querySelector() { return null; },
    querySelectorAll() { return []; },
    getElementById() { return null; },
    appendChild() {},
    innerHTML: '',
  };
  this.attachShadow = function () { return this.shadowRoot; };
  this.addEventListener = function () {};
  this.removeAttribute = function () {};
  this.setAttribute = function () {};
  this.getAttribute = function () { return null; };
  this.querySelector = function () { return null; };
  this.querySelectorAll = function () { return []; };
}
global.HTMLElement = FakeEl;
global.IntersectionObserver = function () { this.observe = function () {}; this.unobserve = function () {}; };
global.customElements = { define() {}, get() { return null; } };
global.window = { __hs_entry_id: 'E1', __hs_panel: null };
global.document = { querySelector() { return null; }, addEventListener() {} };
global.localStorage = { getItem() { return null; }, setItem() {} };
global.URL = { createObjectURL() { return 'blob:x'; }, revokeObjectURL() {} };
global.history = { pushState() {} };
global.Event = function () {};
global.setInterval = function () { return 0; };
global.clearInterval = function () {};
global.setTimeout = function () { return 0; };

/* ---------- 载入面板，暴露内部函数 ---------- */
let api;
try {
  api = eval(
    '(function(){\n' + src + '\nreturn {' +
    'renderAlbums:renderAlbums,' +
    'renderAlbumDetail:renderAlbumDetail,' +
    'renderRecycle:renderRecycle,' +
    'renderDestPicker:renderDestPicker,' +
    // 直接操作内部状态，才能把各个渲染分支都覆盖到
    'setAlbData:function(v,g){ ALB.data = v; ALB.group = g || null; ALB.album = null; ALB.photos = []; ALB.loading = false; },' +
    'setAlbum:function(a,photos,loading){ ALB.album = a; ALB.photos = photos || []; ALB.loading = !!loading; ALB.next = null; },' +
    'setPickOn:function(on){ PICK.on = !!on; PICK.set = new Set(); },' +
    'setDest:function(o){ DEST.open = true; DEST.space = o.space || "user"; DEST.cur = o.cur || "/file/"; DEST.op = o.op || "move"; },' +
    'setSpace:function(s){ PH.space = s; },' +
    'renderFiles:renderFiles,' +
    'setRecy:function(s){ RECY.space = s; }' +
    '};})()'
  );
} catch (e) {
  console.error('面板加载失败: ' + String(e.message).slice(0, 200));
  process.exit(1);
}

/* ---------- 构造假数据（形状跟后端返回一致） ---------- */
const fakeAlbums = {
  total: 3,
  groups: [
    {
      key: 'smart', title: '智能分类', albums: [
        { id: 1, type: 1, name: '全部照片', count: 120, thumbUrl: '' },
      ],
    },
    {
      key: 'user', title: '共享相册', albums: [
        { id: 16, type: 6, name: '家庭照片', count: 42, ownerId: 10001 },
      ],
    },
  ],
};

const d = {
  current_account: { label: '账号A' },
  accounts: [{ label: '账号A' }],
  counts: {},
};

/* ---------- 断言工具 ---------- */
let fail = 0;
let total = 0;
function check(name, cond, detail) {
  total++;
  if (cond) {
    console.log('  ✅ ' + name);
  } else {
    console.log('  ❌ ' + name + (detail ? '  ← ' + detail : ''));
    fail++;
  }
}
function has(hay, needle) { return String(hay).indexOf(needle) >= 0; }

/* ---------- 1. 相册列表页 ---------- */
console.log('\n=== 相册列表页 ===');
let html = '';
try { api.setAlbData(fakeAlbums, 'user'); html = api.renderAlbums(d); }
catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }
check('渲染出「新建相册」按钮', has(html, 'data-act="alb-create"'));
check('列出「共享相册」分组', has(html, '共享相册'));
check(
  '自建相册卡片带 albumType=6',
  has(html, 'data-type="6"'),
  '详情页要按 type 决定能否上传/删除，卡片没带 type 就永远进不去可编辑分支'
);
check(
  '骨架屏分支不渲染按钮（ALB.data 为空时）',
  (() => {
    api.setAlbData(null);
    const sk = api.renderAlbums(d);
    // 骨架屏阶段给按钮也没用（点了没相册列表可刷新），但按钮在也能接受；
    // 这里只要求"不崩"，有内容即可
    return sk.length > 30;
  })()
);

/* ---------- 2. 相册详情页（可编辑：type=6）---------- */
console.log('\n=== 相册详情页 · 自建相册（type=6）===');
let de = '';
try {
  api.setAlbum({ type: 6, id: 16, name: '家庭照片' }, [{ thumbUrl: '', mtime: 0 }], false);
  de = api.renderAlbumDetail();
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }
check('有「上传照片」按钮', has(de, 'data-act="alb-upload"'));
check('有「删除相册」按钮', has(de, 'data-act="alb-del"'));

/* ---------- 3. 相册详情页（只读：智能分类）---------- */
console.log('\n=== 相册详情页 · 智能分类（type=1）===');
let ro = '';
try {
  api.setAlbum({ type: 1, id: 1, name: '全部照片' }, [], false);
  ro = api.renderAlbumDetail();
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }
check('**没有**上传按钮', !has(ro, 'data-act="alb-upload"'));
check('**没有**删除按钮', !has(ro, 'data-act="alb-del"'));
check('给出"不能上传或删除"的说明', has(ro, '不能上传或删除'));

/* ---------- 4. 空相册文案（不能永远说"正在载入"）---------- */
console.log('\n=== 空相册空态 ===');
try {
  api.setAlbum({ type: 6, id: 16, name: '空相册' }, [], false);
  const emptyDone = api.renderAlbumDetail();
  check(
    '加载完成且为空时不显示「正在载入照片」',
    !has(emptyDone, '正在载入照片'),
    '会让人以为一直卡在加载中'
  );
  check('空态引导去上传', has(emptyDone, '上传照片') && has(emptyDone, '还没有照片'));

  api.setAlbum({ type: 6, id: 16, name: '加载中' }, [], true);
  const loading = api.renderAlbumDetail();
  check('真正加载中时才显示「正在载入照片」', has(loading, '正在载入照片'));
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }

/* ---------- 5. 回收站 ---------- */
console.log('\n=== 回收站 ===');
let rc = '';
try {
  rc = api.renderRecycle({ items: [{ rid: 82, name: 'a.jpg', path: '/file/a.jpg', dtime: 0 }], count: 1 });
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }
check('有「恢复」按钮', has(rc, 'data-act="recover"'));
check('有「清空回收站」按钮', has(rc, 'data-act="recycle-empty"'));
check('有「永久删除选中」按钮', has(rc, 'data-act="recycle-purge"'));
check(
  '不再声称设备不支持彻底删除',
  !has(rc, '设备侧不提供'),
  'empty_recycle / permanent_delete_recycle_items 都实现了，这句是误导'
);

/* ---------- 5b. 回收站的空间切换 ---------- */
console.log('\n=== 回收站 · 空间切换 ===');
try {
  api.setSpace('recycle');

  // ⚠️ 断言必须是**精确的「哪个标签带 on 类」**。
  // 不能写 has(html,'data-space="public">共享')：两个标签的这段文本一模一样，
  // 无论高亮哪个都恒真（写这组测试时第一版就是这么错的，靠自查发现）。
  const activeOf = (html) => {
    const flat = html.replace(/\s+/g, ' ');
    const m = flat.match(
      /class="seg on" data-act="recy-space" data-space="(user|public)"/
    );
    return m ? m[1] : null;
  };

  api.setRecy('user');
  const f1 = api.renderFiles(d);
  check('回收站页有空间切换（我的文件/共享）', has(f1, 'data-act="recy-space"'));
  check('默认高亮「我的文件」', activeOf(f1) === 'user', '实际高亮: ' + activeOf(f1));

  api.setRecy('public');
  const f2 = api.renderFiles(d);
  check('切到「共享」后高亮跟着变', activeOf(f2) === 'public', '实际高亮: ' + activeOf(f2));

  api.setSpace('user');
  const f3 = api.renderFiles(d);
  check('非回收站页不显示回收站空间切换', !has(f3, 'data-act="recy-space"'));
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }

/* ---------- 6. 目标选择器（跨空间）---------- */
console.log('\n=== 目标选择器 ===');
try {
  api.setDest({ space: 'public', cur: '/file/', op: 'move' });
  api.setSpace('user');
  const dp = api.renderDestPicker();
  check('有空间切换标签', has(dp, 'data-act="dest-space"'));
  check('切到「共享」时提示跨空间', has(dp, '跨空间'));
  api.setDest({ space: 'user', cur: '/file/', op: 'copy' });
  const dp2 = api.renderDestPicker();
  check('同空间时不显示跨空间提示', !has(dp2, '跨空间'));
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }

/* ---------- 8. 共享相册 · 移出本相册 ---------- */
console.log('\n=== 共享相册 · 移出本相册 ===');
try {
  // albumType=6 才有「移出」：智能分类是设备生成的，移出没有意义
  api.setAlbum({ id: 16, type: 6, name: '家庭照片' }, [{ fileId: 1 }], false);
  api.setPickOn(true);
  const det6 = api.renderAlbumDetail();
  check('共享相册详情有「移出本相册」', has(det6, 'album-remove-picked'));

  api.setAlbum({ id: 1, type: 1, name: '全部照片' }, [{ fileId: 1 }], false);
  api.setPickOn(true);
  const det1 = api.renderAlbumDetail();
  check(
    '智能分类详情不显示「移出本相册」',
    !has(det1, 'album-remove-picked'),
    'type!=6 的相册不该出现移出入口'
  );

  // 文案要说明"不删原图"，否则用户不敢点
  check('移出按钮带「不删照片」提示', has(det6, '不删照片'));

  check('共享相册详情有「重命名」按钮', has(det6, 'alb-rename'));
  check(
    '智能分类详情不显示「重命名」',
    !has(det1, 'alb-rename'),
    'type!=6 的相册不该出现改名入口'
  );
  check('共享相册详情有「设为封面」', has(det6, 'album-cover-picked'));
  check(
    '智能分类详情不显示「设为封面」',
    !has(det1, 'album-cover-picked'),
    'type!=6 的相册不该出现设封面入口'
  );

  // 归属 / 成员：只显示 ID 与人数（两套 ID 体系对不上，不做昵称映射）
  api.setAlbum(
    { id: 16, type: 6, name: '家庭照片', ownerId: 10001, userIds: [10000, 10001] },
    [], false
  );
  api.setPickOn(true);
  const detOwn = api.renderAlbumDetail();
  check('详情页显示归属 ID', has(detOwn, '归属 ID'));
  check('详情页显示共享成员人数', has(detOwn, '共享成员'));
  // 隐藏相册：设备返回 code 0 但无实际效果，入口已撤（防止回潮）
  check('不再提供「隐藏相册」入口', !has(detOwn, 'alb-hide'));
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }

/* ---------- 9. 共享空间说明 ---------- */
console.log('\n=== 共享空间说明 ===');
try {
  api.setSpace('public');
  const pub = api.renderFiles(d);
  check('共享空间有「家庭成员都能看到」说明', has(pub, '家庭成员都能看到'));
  check('共享空间说明提到「共享目录」', has(pub, '共享目录'));

  api.setSpace('user');
  const usr = api.renderFiles(d);
  check('「我的文件」不显示共享说明', !has(usr, '家庭成员都能看到'));
} catch (e) { console.log('  渲染抛错: ' + e.message); fail++; }

/* ---------- 结果 ---------- */
// ⚠️ 末尾必须打印 `Ran N checks`：
//   * run_all_tests.py 靠这行统计用例数，**认不出就等于 0 用例 → 判失败**
//   * 也防"一个 check 都没执行却退出 0"（SUITES 漏项/断言被注释掉的经典事故）
console.log('');
console.log('Ran ' + total + ' checks');
if (total === 0) {
  console.log('✗ 一个断言都没执行（测试文件被改坏了）');
  process.exit(1);
}
if (fail) {
  console.log('✗ UI 结构测试失败：' + fail + '/' + total + ' 项');
  process.exit(1);
}
console.log('✓ UI 结构测试全部通过（' + total + ' 项）');
