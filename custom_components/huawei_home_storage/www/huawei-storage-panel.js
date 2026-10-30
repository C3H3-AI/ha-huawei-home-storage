/* 家庭存储面板
 * 结构：侧栏/底栏按「浏览」「管理」分组
 *   浏览 → 概览 · 相册(真实相册) · 文件(我的文件/共享/最近删除)
 *   管理 → 设备(硬件+存储+网络+操作) · 用户(成员+账号+登录)
 * 视觉：温润数据中心风（青蓝品牌 + 柔和纵深 + 毛玻璃）
 */
const STYLES = String.raw`
:host{
  /* ============ 主题变量（默认：HA 原生跟随模式）============ */
  --bg:var(--primary-background-color,#f4f6fa);
  --card:var(--card-background-color,var(--ha-card-background,#ffffff));
  --text:var(--primary-text-color,#17202a);
  --text2:var(--secondary-text-color,#64748b);
  --divider:var(--divider-color,#e6eaf0);

  /* 品牌：青蓝 */
  --brand:#0a76a8;   /* 白字对比 3.66→5.04:1 */
  --brand-2:#12b3e8;
  --brand-soft:rgba(14,143,196,.10);
  --brand-line:rgba(14,143,196,.24);

  --ok:#2fa563;  --warn:#e0902a;  --danger:#d94f45;
  --ok-soft:rgba(47,165,99,.12);
  --warn-soft:rgba(224,144,42,.14);
  --danger-soft:rgba(217,79,69,.12);

  /* 间距刻度（此前只有 --gap，且全站仅 4 处引用 → 名存实亡） */
  --sp-1:4px; --sp-2:8px; --sp-3:12px; --sp-4:16px; --sp-5:20px; --sp-6:24px; --sp-7:32px;
  /* 圆角刻度（此前圆角有 6/9/10/12/14/15/18px 七种散值） */
  --r-xs:4px; --r-sm:8px; --r-md:12px; --r-lg:18px; --r-xl:22px; --r-pill:999px;
  --on-brand:#ffffff;        /* 压在品牌色上的前景色；深色皮肤会覆盖 */
  --radius:18px;
  --radius-s:12px;
  --gap:20px;
  --topbar:62px;

  /* 现代纵深：多层柔和阴影（此前总 alpha 仅 .09，卡片与背景几乎无分离） */
  --sh-1:0 1px 2px rgba(15,23,42,.05),0 1px 3px rgba(15,23,42,.06),0 2px 8px rgba(15,23,42,.05);
  --sh-3:0 12px 28px -6px rgba(15,23,42,.16),0 4px 12px -4px rgba(15,23,42,.10);
  --sh-2:0 6px 16px -4px rgba(15,23,42,.14),0 2px 6px -2px rgba(15,23,42,.08);
  --ring:0 0 0 1px rgba(15,23,42,.045);

  --font-display:'Baloo 2','HarmonyOS Sans SC','PingFang SC','Hiragino Sans GB','Microsoft YaHei',system-ui,sans-serif;
  --font-body:'IBM Plex Sans','HarmonyOS Sans SC','PingFang SC','Microsoft YaHei',system-ui,sans-serif;

  /* 玻璃质感强度（0=关闭，1=最强）—— 皮肤可覆盖 */
  --glass:0;
  --glass-blur:16px;
  --surface-alpha:1;
  --accent-glow:none;
}

/* ============ 皮肤：极光（玻璃拟态·青蓝）============ */
:host([data-skin="aurora"]){
  --glass:1; --glass-blur:18px; --surface-alpha:.72;
  --bg:linear-gradient(150deg,#eaf6fb 0%,#f4f8fc 45%,#eef4fb 100%);
  --card:rgba(255,255,255,.72);
  --brand:#0a76a8; --brand-2:#29c2f0;
  /* 本皮肤强制浅色卡片，若 HA 是深色主题会继承浅色文字 → 必须写死深色文字 */
  --text:#0f2b3d; --text2:#4a6478; --divider:rgba(15,60,90,.12);
  --accent-glow:0 4px 14px rgba(14,143,196,.28);
  --sh-2:0 10px 30px -6px rgba(14,143,196,.22),0 2px 8px -2px rgba(15,23,42,.08);
}
/* ============ 皮肤：墨夜（深色·霓虹点缀）============ */
:host([data-skin="midnight"]){
  --glass:1; --glass-blur:20px; --surface-alpha:.62;
  --bg:radial-gradient(1200px 600px at 15% -10%,#16283a 0%,#0d1620 55%,#0a1119 100%);
  --card:rgba(28,40,54,.66);
  --text:#e8eef6; --text2:#93a4b8; --divider:rgba(255,255,255,.10);
  --brand:#38d6f5; --brand-2:#5ce1c0;
  --brand-soft:rgba(56,214,245,.14); --brand-line:rgba(56,214,245,.30);
  --on-brand:#06212b;          /* 白字压浅青=1.62:1 → 深青=9.61:1 */
  --accent-glow:0 4px 16px rgba(56,214,245,.35);
  --sh-1:0 1px 2px rgba(0,0,0,.30),0 2px 6px rgba(0,0,0,.22);
  --sh-2:0 12px 34px -8px rgba(0,0,0,.6),0 2px 8px -2px rgba(0,0,0,.4);
  --sh-3:0 16px 40px -8px rgba(0,0,0,.72),0 4px 14px -4px rgba(0,0,0,.5);
  --ring:0 0 0 1px rgba(255,255,255,.07);
}
/* ============ 皮肤：暖砂（浅色·暖调柔和）============ */
:host([data-skin="sand"]){
  --bg:linear-gradient(160deg,#fdf8f2 0%,#fbf3ea 50%,#f7efe4 100%);
  --card:rgba(255,253,250,.86);
  --text:#3d3226; --text2:#6f6053; --divider:rgba(120,95,70,.14);
  --brand:#c8763c; --brand-2:#e0a066;
  --brand-soft:rgba(200,118,60,.12); --brand-line:rgba(200,118,60,.26);
  --accent-glow:0 4px 14px rgba(200,118,60,.22);
  --radius:16px;
}
/* ============ 皮肤：森屿（自然·青绿）============ */
:host([data-skin="forest"]){
  --glass:1; --glass-blur:16px; --surface-alpha:.70;
  --bg:linear-gradient(155deg,#eef7f0 0%,#e8f2ec 50%,#e3efe7 100%);
  --card:rgba(252,255,253,.74);
  --text:#22362c; --text2:#557063; --divider:rgba(60,100,80,.14);
  --brand:#2fa563; --brand-2:#57c48c;
  --brand-soft:rgba(47,165,99,.12); --brand-line:rgba(47,165,99,.26);
  --accent-glow:0 4px 14px rgba(47,165,99,.24);
}

*{box-sizing:border-box}
/* 键盘焦点：此前只有 outline:none + 10% 透明度的环，键盘用户几乎看不见 */
:focus{outline:none}
:focus-visible{outline:2px solid var(--brand);outline-offset:2px;border-radius:var(--r-sm)}
:host{
  display:block;
  background:var(--bg);
  color:var(--text);
  font:400 14px/1.55 var(--font-body);
  -webkit-font-smoothing:antialiased;
  min-height:100%;
}
.app{display:flex;flex-direction:column;min-height:100%}

/* ========== 顶栏 ========== */
.topbar{
  position:sticky;top:0;z-index:20;height:var(--topbar);
  display:flex;align-items:center;gap:12px;padding:0 20px;
  background:color-mix(in srgb,var(--card) calc(var(--surface-alpha)*100%),transparent);
  backdrop-filter:blur(calc(var(--glass)*var(--glass-blur))) saturate(1.5);
  -webkit-backdrop-filter:blur(calc(var(--glass)*var(--glass-blur))) saturate(1.5);
  border-bottom:1px solid var(--divider);
}
.brand{display:flex;align-items:center;gap:11px;font-family:var(--font-display);
  font-weight:700;font-size:17px;letter-spacing:.2px;flex:none}
.brand .logo{
  width:36px;height:36px;border-radius:var(--r-md);display:grid;place-items:center;
  background:linear-gradient(140deg,var(--brand-2),var(--brand));color:var(--on-brand);font-size:18px;
  box-shadow:var(--accent-glow),inset 0 1px 0 rgba(255,255,255,.28);
}
.brand .sub{font-family:var(--font-body);font-weight:500;font-size:12px;color:var(--text2)}
.spacer{flex:1}

/* 皮肤切换器 */
.skinner{display:flex;align-items:center;gap:3px;padding:3px;border-radius:999px;
  background:var(--divider);flex:none}
.skinner button{width:24px;height:24px;border-radius:50%;border:0;cursor:pointer;
  padding:0;display:grid;place-items:center;font-size:11px;transition:transform .16s}
.skinner button:hover{transform:scale(1.15)}
.skinner button.on{box-shadow:0 0 0 2px var(--brand)}

.pill{display:inline-flex;align-items:center;gap:7px;font-size:12px;font-weight:600;
  padding:6px 13px;border-radius:999px;background:var(--ok-soft);color:var(--ok);flex:none}
.pill.off{background:var(--danger-soft);color:var(--danger)}
.dot{width:7px;height:7px;border-radius:50%;background:currentColor;
  box-shadow:0 0 0 3px color-mix(in srgb,currentColor 20%,transparent)}
.dot.live{animation:pulse 2.4s ease-in-out infinite}
@keyframes pulse{
  0%,100%{box-shadow:0 0 0 3px color-mix(in srgb,currentColor 20%,transparent)}
  50%{box-shadow:0 0 0 6px color-mix(in srgb,currentColor 8%,transparent)}
}

/* 账号切换 */
.accts{display:flex;align-items:center;gap:6px}
.accts:empty{display:none}
.acct{display:inline-flex;align-items:center;gap:7px;cursor:pointer;
  padding:6px 12px;border-radius:999px;font-size:12px;font-weight:600;
  border:1px solid var(--divider);background:color-mix(in srgb,var(--card) 80%,transparent);color:var(--text2);
  transition:background .16s,color .16s,border-color .16s;white-space:nowrap}
.acct:hover{background:var(--brand-soft);color:var(--text)}
.acct.on{background:var(--brand-soft);color:var(--brand);border-color:var(--brand-line)}
.acct .av{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;
  background:linear-gradient(140deg,var(--brand-2),var(--brand));color:var(--on-brand);
  font-size:10.5px;font-weight:700;flex:none}
.acct .badge{font-size:10px;font-weight:700;padding:1px 6px;border-radius:99px;
  background:var(--brand);color:var(--on-brand)}

/* ========== 主体 ========== */
.body{flex:1;display:flex;align-items:flex-start}
.nav{width:224px;flex:none;position:sticky;top:var(--topbar);
  height:calc(100vh - var(--topbar));overflow:auto;
  padding:16px 11px;background:color-mix(in srgb,var(--card) 70%,transparent);
  border-right:1px solid var(--divider)}
.nav button{width:100%;display:flex;align-items:center;gap:12px;
  padding:11px 13px;margin-bottom:4px;border:0;border-radius:var(--radius-s);
  background:transparent;color:var(--text2);font-family:var(--font-body);
  font-size:13.5px;font-weight:500;cursor:pointer;text-align:left;
  transition:background .16s,color .16s,transform .16s}
.nav button:hover{background:var(--brand-soft);color:var(--text);transform:translateX(2px)}
.nav button.active{background:var(--brand-soft);color:var(--brand);font-weight:650;
  box-shadow:inset 0 0 0 1px var(--brand-line)}
.nav .ico{width:20px;text-align:center;font-size:16px;line-height:1}
.nav .sec{margin:18px 13px 7px;font-size:10.5px;font-weight:700;letter-spacing:1.1px;
  color:var(--text2);text-transform:uppercase;opacity:.7}
.nav .sec:first-child{margin-top:4px}
/* 桌面用分组侧栏；移动端切到 5 项 + 更多抽屉（由 media 块切换） */
.nav-mob{display:none}
.nav-desk{display:block}

.main{flex:1;min-width:0;padding:var(--gap);max-width:1240px;margin:0 auto;width:100%;
  animation:fadeUp .45s cubic-bezier(.22,1,.36,1) both}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
h2.view-title{margin:2px 0 18px;font-family:var(--font-display);font-size:22px;font-weight:700;letter-spacing:-.2px}
.vhead{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.vhead h2{margin:0;font-family:var(--font-display);font-size:22px;font-weight:700;letter-spacing:-.2px}
.vhead .sub{font-size:12px;color:var(--text2)}

/* ========== 卡片 ========== */
.card{background:color-mix(in srgb,var(--card) calc(var(--surface-alpha)*100%),transparent);
  border-radius:var(--radius);box-shadow:var(--sh-1),var(--ring);
  padding:20px;margin-bottom:var(--gap);transition:box-shadow .2s;
  backdrop-filter:blur(calc(var(--glass)*var(--glass-blur)));
  -webkit-backdrop-filter:blur(calc(var(--glass)*var(--glass-blur)))}
.card:hover{box-shadow:var(--sh-3),var(--ring)}
.card-h{display:flex;align-items:center;gap:10px;margin:0 0 15px;
  font-family:var(--font-display);font-size:15.5px;font-weight:700}
.card-h::before{content:"";width:3px;height:15px;border-radius:var(--r-xs);flex:none;
  background:linear-gradient(180deg,var(--brand-2),var(--brand))}
.card-h .hint{margin-left:auto;font-family:var(--font-body);font-size:12px;
  font-weight:500;color:var(--text2)}

.grid{display:grid;gap:13px;grid-template-columns:repeat(auto-fill,minmax(158px,1fr))}
.grid.kpi{grid-template-columns:repeat(auto-fill,minmax(196px,1fr))}

/* ========== KPI ========== */
.tile{position:relative;overflow:hidden;border-radius:var(--r-lg);
  box-shadow:var(--sh-1),var(--ring);padding:16px;display:flex;gap:14px;align-items:center;
  background:color-mix(in srgb,var(--card) calc(var(--surface-alpha)*100%),transparent);
  transition:transform .18s cubic-bezier(.22,1,.36,1),box-shadow .18s}
.tile::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--brand);opacity:.85}
.tile:hover{transform:translateY(-4px);box-shadow:var(--sh-3),var(--ring)}
.tile .ico{width:44px;height:44px;flex:none;border-radius:var(--r-md);display:grid;place-items:center;
  background:var(--brand-soft);color:var(--brand);font-size:20px}
.tile .lab{font-size:11.5px;color:var(--text2);margin-bottom:4px;font-weight:500}
.tile .val{font-family:var(--font-display);font-size:24px;font-weight:700;line-height:1.1;
  letter-spacing:-.4px;font-variant-numeric:tabular-nums}
.tile-link{cursor:pointer}
.tile-link:hover{transform:translateY(-3px);box-shadow:var(--sh-2),var(--ring)}
.tile-link:active{transform:translateY(-1px)}
.tile.warn::before{background:var(--warn)}
.tile.warn .ico{background:var(--warn-soft);color:var(--warn)}
.tile.good::before{background:var(--ok)}
.tile.good .ico{background:var(--ok-soft);color:var(--ok)}
.tile.danger::before{background:var(--danger)}
.tile.danger .ico{background:var(--danger-soft);color:var(--danger)}

.bar{height:10px;border-radius:99px;background:var(--divider);overflow:hidden;margin-top:12px}
.bar > i{display:block;height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--brand-2),var(--brand));
  box-shadow:0 0 10px rgba(14,143,196,.35);transition:width .6s cubic-bezier(.4,0,.2,1)}
.bar.warn > i{background:linear-gradient(90deg,#f0b055,var(--warn));box-shadow:0 0 10px rgba(224,144,42,.35)}
.bar.danger > i{background:linear-gradient(90deg,#e8705f,var(--danger));box-shadow:0 0 10px rgba(217,79,69,.35)}

.row{display:flex;align-items:center;gap:12px;padding:11px 2px;border-bottom:1px solid var(--divider)}
.row:last-child{border-bottom:0}
.row .k{color:var(--text2);font-size:13px;min-width:112px}
.row .v{margin-left:auto;font-weight:600;font-size:13.5px;text-align:right;
  word-break:break-all;font-variant-numeric:tabular-nums}

/* ========== 按钮 ========== */
.btn{display:inline-flex;align-items:center;justify-content:center;gap:7px;
  padding:9px 16px;min-height:38px;border-radius:var(--r-sm);cursor:pointer;
  border:1px solid var(--divider);
  background:color-mix(in srgb,var(--card) 85%,transparent);color:var(--text);
  font-family:var(--font-body);font-size:13.5px;font-weight:600;
  transition:background .16s,box-shadow .16s,transform .1s;text-decoration:none}
.btn:hover{background:var(--brand-soft);box-shadow:var(--sh-1)}
.btn:active{transform:scale(.97)}
.btn.pri{background:linear-gradient(140deg,var(--brand-2),var(--brand));
  border-color:transparent;color:var(--on-brand);box-shadow:var(--accent-glow)}
.btn.pri:hover{filter:brightness(1.07)}
.btn.danger{background:var(--danger);border-color:var(--danger);color:var(--on-brand)}
.btn.danger:hover{filter:brightness(1.06)}
.btn.sm{min-height:32px;padding:5px 11px;font-size:12.5px;border-radius:var(--r-sm)}
.btn[disabled]{opacity:.55;cursor:not-allowed;transform:none}
.actions{display:flex;flex-wrap:wrap;gap:11px}

/* 分段控件 */
.segs{display:flex;gap:6px;flex-wrap:wrap}
.seg{padding:8px 14px;border-radius:999px;font-size:13px;font-weight:600;cursor:pointer;
  border:1px solid var(--divider);
  background:color-mix(in srgb,var(--card) 85%,transparent);color:var(--text2);
  transition:background .16s,color .16s,border-color .16s}
.seg:hover{background:var(--brand-soft);color:var(--text)}
.seg.on{background:var(--brand-soft);color:var(--brand);border-color:var(--brand-line)}
.seg .n{font-size:11px;opacity:.75;margin-left:5px}

/* 搜索框 */
.searchbar{display:flex;gap:8px;margin-bottom:16px}
.searchbar input{flex:1;padding:11px 15px;border-radius:var(--r-md);font-size:14px;
  border:1px solid var(--divider);
  background:color-mix(in srgb,var(--card) 85%,transparent);color:var(--text);
  font-family:var(--font-body)}
.searchbar input:focus{outline:none;border-color:var(--brand);
  box-shadow:0 0 0 3px color-mix(in srgb,var(--brand) 28%,transparent)}
.searchbar .btn{flex:none}

/* ========== 相册网格 ========== */
.albums{display:grid;gap:16px;grid-template-columns:repeat(auto-fill,minmax(190px,1fr))}
.alb{position:relative;border-radius:var(--r-lg);overflow:hidden;cursor:pointer;
  background:color-mix(in srgb,var(--card) 85%,transparent);
  box-shadow:var(--sh-1),var(--ring);
  transition:transform .18s cubic-bezier(.22,1,.36,1),box-shadow .18s}
.alb:hover{transform:translateY(-4px);box-shadow:var(--sh-3),var(--ring)}
.alb .cov{position:relative;aspect-ratio:1;background:var(--divider);overflow:hidden}
.alb .cov img{width:100%;height:100%;object-fit:cover;display:block}
.alb .cov .ph{width:100%;height:100%;display:grid;place-items:center;font-size:30px;
  background:linear-gradient(140deg,var(--brand-soft),transparent);color:var(--brand)}
.alb .meta{padding:9px 11px 11px}
.alb .nm{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.alb .ct{font-size:11.5px;color:var(--text2);margin-top:2px}

/* ========== 照片网格 ========== */
.phgrid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(170px,1fr))}
.ph{position:relative;aspect-ratio:1;border-radius:var(--r-md);overflow:hidden;cursor:pointer;
  background:var(--divider);box-shadow:var(--sh-1);
  transition:transform .18s cubic-bezier(.22,1,.36,1),box-shadow .18s}
.ph:hover{transform:translateY(-3px) scale(1.02);box-shadow:var(--sh-2),var(--ring);z-index:2}
.ph img{width:100%;height:100%;object-fit:cover;display:block}
.ph .cap{position:absolute;left:0;right:0;bottom:0;padding:12px 8px 5px;font-size:11px;color:#fff;
  background:linear-gradient(transparent,rgba(0,0,0,.72));
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sk{width:100%;height:100%;background:
  linear-gradient(100deg,var(--divider) 30%,color-mix(in srgb,var(--divider) 55%,var(--card)) 50%,var(--divider) 70%);
  background-size:220% 100%;animation:shimmer 1.3s linear infinite}
/* 骨架卡片：比纯色块更有结构感 */
.skel{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(148px,1fr))}
.skel i{display:block;aspect-ratio:1;border-radius:var(--r-md);background:
  linear-gradient(100deg,var(--divider) 30%,color-mix(in srgb,var(--divider) 55%,var(--card)) 50%,var(--divider) 70%);
  background-size:220% 100%;animation:shimmer 1.3s linear infinite}
@keyframes shimmer{from{background-position:120% 0}to{background-position:-120% 0}}

/* 文件行 */
.filerow{display:flex;align-items:center;gap:12px;padding:11px 4px;border-bottom:1px solid var(--divider)}
.filerow.dir{cursor:pointer}
.filerow.dir:hover{background:var(--brand-soft);border-radius:var(--r-sm)}
.filerow:last-child{border-bottom:0}
.filerow .fico{width:34px;height:34px;flex:none;border-radius:var(--r-sm);display:grid;place-items:center;
  background:var(--brand-soft);color:var(--brand);font-size:16px}
.filerow .fmain{flex:1;min-width:0}
.filerow .fname{font-size:13.5px;font-weight:500;word-break:break-all}
.filerow .fsub{font-size:11.5px;color:var(--text2);margin-top:1px}
.filerow .fsize{font-size:12px;color:var(--text2);flex:none;font-variant-numeric:tabular-nums}

.crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:3px;font-size:13px;margin-bottom:14px}
.crumbs a{color:var(--brand);cursor:pointer;text-decoration:none;padding:3px 7px;border-radius:var(--r-xs)}
.crumbs a:hover{background:var(--brand-soft)}
.crumbs .sep{color:var(--text2)}

/* 拖拽上传 */
.main.dropping{outline:2px dashed var(--brand);outline-offset:-8px;border-radius:var(--r-md);
  background:var(--brand-soft)}
.dropzone{position:fixed;inset:0;z-index:900;display:grid;place-items:center;
  background:color-mix(in srgb,var(--brand) 12%,transparent);pointer-events:none;
  font-size:16px;font-weight:700;color:var(--brand)}

/* 批量选择 */
.pickbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 12px;
  border-radius:var(--r-md);background:var(--brand-soft);margin-bottom:12px}
.pickbar .cnt{font-size:13px;font-weight:600;color:var(--brand)}
.pickbar .cnt b{font-size:15px}
.pickbox{width:20px;height:20px;flex:none;border-radius:var(--r-sm);border:2px solid var(--divider);
  cursor:pointer;display:grid;place-items:center;transition:background .14s,border-color .14s}
.pickbox:hover{border-color:var(--brand)}
.pickbox.on{background:var(--brand);border-color:var(--brand)}
.pickbox.on::after{content:"";width:9px;height:5px;border-left:2px solid var(--on-brand);
  border-bottom:2px solid var(--on-brand);transform:rotate(-45deg) translateY(-1px)}
.filerow.picked{background:var(--brand-soft);border-radius:var(--r-sm)}
.ph.picked{box-shadow:0 0 0 3px var(--brand),var(--sh-2)}
.ph .pickbox{position:absolute;top:6px;left:6px;z-index:3}
.filerow.picked .fname{color:var(--brand);font-weight:600}

/* 文件操作：磁贴上的 ⋯ 与操作菜单 */
.phmenu{position:absolute;top:6px;right:6px;min-height:30px;padding:2px 9px;font-size:15px;
  border-radius:var(--r-sm);background:rgba(0,0,0,.55);color:#fff;border:0;
  transition:opacity .15s;backdrop-filter:blur(4px);z-index:4}
/* ⚠️ 此前 opacity:0 + 仅 .ph:hover 显示 —— 触摸设备没有 hover，图片上的「⋯」
   永远看不见 → 手机上图片的重命名/移动/复制/删除完全不可达。
   改为：只有鼠标设备用 hover 显隐，触摸设备默认常显。 */
@media (hover:hover) and (pointer:fine){
  .phmenu{opacity:0}
  .ph:hover .phmenu{opacity:1}
}
.menu{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.menu button{width:100%;text-align:left;justify-content:flex-start;gap:9px}
.menu button.danger{color:var(--danger);border-color:var(--danger-soft)}

/* ========== 大图查看器 ========== */
.viewer{position:fixed;inset:0;z-index:999;background:rgba(10,14,20,.94);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  animation:vfade .2s ease both;outline:none}
@keyframes vfade{from{opacity:0}to{opacity:1}}
.viewer img{max-width:94vw;max-height:78vh;object-fit:contain;border-radius:var(--r-md);
  box-shadow:0 20px 60px rgba(0,0,0,.5)}
.viewer .vbar{position:absolute;top:0;left:0;right:0;display:flex;align-items:center;gap:10px;
  padding:14px 18px;color:#fff;font-size:13px}
.viewer .vbar .btn{min-height:36px;padding:6px 14px}
.viewer .vmeta{color:#c3cad6;font-size:12px;margin-top:12px;text-align:center;padding:0 18px}
.viewer .nav{position:absolute;top:50%;transform:translateY(-50%);width:46px;height:46px;
  border-radius:50%;border:0;background:rgba(255,255,255,.14);color:#fff;font-size:20px;
  cursor:pointer;display:grid;place-items:center}
.viewer .nav:hover{background:rgba(255,255,255,.26)}
.viewer .nav.prev{left:14px}
.viewer .nav.next{right:14px}

/* ========== 登录弹窗 ========== */
.modal{position:fixed;inset:0;z-index:1000;display:flex;align-items:center;justify-content:center;
  background:rgba(10,14,20,.6);backdrop-filter:blur(6px);-webkit-backdrop-filter:blur(6px);
  animation:vfade .2s ease both;padding:18px}
.mbox{width:100%;max-width:420px;max-height:88vh;overflow:auto;
  background:color-mix(in srgb,var(--card) 95%,transparent);
  border-radius:var(--r-lg);box-shadow:0 24px 60px rgba(10,14,20,.35);padding:24px;
  animation:mup .26s cubic-bezier(.22,1,.36,1) both}
@keyframes mup{from{opacity:0;transform:translateY(14px) scale(.98)}to{opacity:1;transform:none}}
.mbox h3{margin:0 0 6px;font-family:var(--font-display);font-size:17px;font-weight:700}
.mbox p.sub{margin:0 0 18px;font-size:12.5px;color:var(--text2);line-height:1.5}
.field{margin-bottom:14px}
.field label{display:block;font-size:12px;font-weight:600;color:var(--text2);margin-bottom:6px}
.field input,.field select{width:100%;padding:11px 13px;border-radius:var(--r-sm);font-size:14px;
  border:1px solid var(--divider);
  background:color-mix(in srgb,var(--card) 85%,transparent);color:var(--text);font-family:var(--font-body)}
.field input:focus,.field select:focus{outline:none;border-color:var(--brand);
  box-shadow:0 0 0 3px var(--brand-soft)}
.merr{background:var(--danger-soft);color:var(--danger);font-size:12.5px;font-weight:500;
  padding:9px 12px;border-radius:var(--r-sm);margin-bottom:14px}
.mnote{background:var(--brand-soft);color:var(--brand);font-size:12px;padding:9px 12px;
  border-radius:var(--r-sm);margin-bottom:14px;line-height:1.5}
.mactions{display:flex;gap:10px;margin-top:6px}
.mactions .btn{flex:1}
.steps{display:flex;gap:6px;margin-bottom:18px}
.steps i{flex:1;height:3px;border-radius:var(--r-xs);background:var(--divider)}
.steps i.on{background:var(--brand)}

/* ========== 用户 ========== */
.users{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}
.ucard{border-radius:var(--r-md);box-shadow:var(--sh-1),var(--ring);
  background:color-mix(in srgb,var(--card) calc(var(--surface-alpha)*100%),transparent);
  padding:15px;display:flex;gap:12px;align-items:center}
.ucard .uav{width:40px;height:40px;flex:none;border-radius:50%;display:grid;place-items:center;
  background:var(--brand-soft);color:var(--brand);font-size:15px;font-weight:700}
.ucard.admin .uav{background:var(--warn-soft);color:var(--warn)}
.ucard .un{font-weight:600;font-size:13.5px}
.ucard .ur{font-size:11.5px;color:var(--text2);margin-top:2px}
.utag{margin-left:auto;font-size:10px;font-weight:700;padding:3px 8px;border-radius:99px;
  background:var(--brand-soft);color:var(--brand)}
.ucard.admin .utag{background:var(--warn-soft);color:var(--warn)}

/* ========== 其他 ========== */
.slot{border:1.5px dashed var(--divider);border-radius:var(--r-lg);padding:28px 18px;text-align:center;
  color:var(--text2);font-size:13px}
.slot .em{display:block;font-size:34px;margin-bottom:10px;opacity:.55}
.slot .tip{display:block;margin-top:6px;font-size:12px;opacity:.8}
.slot.sm{padding:18px 14px}
.note{font-size:12px;color:var(--text2);margin-top:12px;line-height:1.6}
.err{background:var(--danger-soft);color:var(--danger);border-radius:var(--r-md);padding:12px 14px;
  font-size:13px;margin-bottom:14px}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:2000;
  background:var(--brand);color:var(--on-brand);padding:10px 18px;border-radius:999px;font-size:13px;
  font-weight:600;box-shadow:var(--sh-2);animation:vfade .2s ease both}
.more{display:flex;justify-content:center;margin-top:16px}

/* ========== 手机 ========== */
@media (max-width:820px){
  .topbar{padding:0 14px;height:56px}
  .brand{font-size:16px}
  .brand .logo{width:32px;height:32px;font-size:16px}
  .brand .sub{display:none}
  .accts{max-width:44vw;overflow-x:auto;padding:2px}
  .acct{padding:5px 10px;font-size:11.5px}
  .nav{position:fixed;bottom:0;left:0;right:0;top:auto;width:auto;height:auto;
    display:flex;overflow-x:auto;border-right:0;border-top:1px solid var(--divider);
    padding:7px 8px calc(7px + env(safe-area-inset-bottom));gap:3px;z-index:30;
    background:color-mix(in srgb,var(--card) 93%,transparent);
    backdrop-filter:blur(16px) saturate(1.5);-webkit-backdrop-filter:blur(16px) saturate(1.5);
    box-shadow:0 -6px 20px rgba(15,23,42,.10)}
  .nav .sec{display:none}
  .nav-desk{display:none}
  .nav-mob{display:flex;width:100%;align-items:center;gap:2px}
  /* 「更多」抽屉：展开时在底栏之上横排显示任务/设备/用户/配置 */
  .morebar{display:flex;flex-wrap:wrap;gap:6px;padding:8px 10px;border-top:1px solid var(--divider);width:100%}
  .morebar .btn{flex:0 0 auto;min-height:40px}
  /* ⚠️ 8 项 ×60px + gap ≈ 509px > 414px 屏宽 → 必定横滑，第 6–8 项看不见。
     改为 5 个主入口 + 「更多」抽屉（见 _renderNav 的移动端分组）。 */
  .nav button{flex:1;min-width:0;flex-direction:column;gap:3px;padding:8px 2px;
    font-size:11px;text-align:center;margin:0;border-radius:var(--r-md);
    min-height:48px;justify-content:center}
  .nav button:hover{transform:none}
  /* 移动端恢复 active 描边（此前 box-shadow:none → 完全看不出当前在哪一页） */
  .nav button.active{background:var(--brand-soft);color:var(--brand);
    box-shadow:inset 0 0 0 1.5px var(--brand-line)}
  .nav button .ico{font-size:21px;line-height:1}
  .main{padding:14px 13px calc(92px + env(safe-area-inset-bottom))}
  h2.view-title,.vhead h2{font-size:18px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px}
  .grid.kpi{grid-template-columns:repeat(2,1fr);gap:10px}
  .tile{padding:13px;border-radius:var(--r-md)}
  .tile .val{font-size:19px}
  .card{padding:15px;border-radius:var(--r-md);margin-bottom:14px}
  .row .k{min-width:88px;font-size:12px}
  .row .v{font-size:12.5px}
  .btn{flex:1;min-width:calc(50% - 6px);min-height:44px}
  .btn.sm{min-height:40px;padding:8px 14px}
  /* 复选框视觉 24px，热区外扩到 ~44px（此前仅 20px，手机上极难点中） */
  .pickbox{width:24px;height:24px;position:relative}
  .pickbox::before{content:"";position:absolute;inset:-10px}
  .phmenu{min-height:36px;padding:4px 11px;font-size:16px}
  .albums{grid-template-columns:repeat(2,1fr);gap:10px}
  .alb .meta{padding:7px 8px 9px}
  .alb .nm{font-size:12px}
  .phgrid{grid-template-columns:repeat(2,1fr);gap:8px}
  .users{grid-template-columns:repeat(2,1fr);gap:10px}
  .ucard{padding:12px}
  .modal{align-items:flex-end;padding:0}
  .mbox{max-width:none;border-radius:var(--r-lg) 20px 0 0;max-height:92vh;
    padding-bottom:calc(24px + env(safe-area-inset-bottom))}
  .viewer .nav{width:40px;height:40px}
  .searchbar{flex-wrap:wrap}
}

`;

/* ===================== 工具 ===================== */
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

/** 等待若干毫秒（用于"设备索引还没跟上"这类可重试场景）。 */
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

const fmtSize = (b) => {
  if (b == null || isNaN(b)) return "—";
  const u = ["B", "KB", "MB", "GB", "TB", "PB"];
  let i = 0;
  let v = Number(b);
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return v.toFixed(i === 0 ? 0 : (v < 10 ? 1 : 0)) + " " + u[i];
};

const fmtDate = (ms) => {
  const n = Number(ms) || 0;
  if (!n) return "";
  const d = new Date(n < 1e12 ? n * 1000 : n);
  if (isNaN(d.getTime())) return "";
  const p = (x) => String(x).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
};

const maskSn = (sn) => {
  const s = String(sn || "");
  return s.length > 8 ? s.slice(0, 4) + "****" + s.slice(-4) : s;
};

/* ===================== 状态 ===================== */
const PH = { path: "/file/", space: "user", data: null, upload: null, uploads: [] };
const TASK = { src: "filesvc", data: null, err: "", counts: {} };

/**
 * 回收站的空间。
 *
 * ⚠️ **必须独立于 ``PH.space``**（2026-10-29 修）：
 * 回收站页是 ``PH.space === "recycle"`` 这个**第三态**，此时
 * ``curSpace()`` 会落回 ``"user"``（因为它只认 ``"public"``）。而回收站
 * 视图后端在**不传 space 时默认 ``"public"``**。于是：
 *
 *   列表：不传 space → 后端给 public 空间的回收站
 *   恢复：curSpace() → user 空间
 *
 * 两边看的根本不是同一个回收站 —— 用户在「最近删除」里看到条目、点恢复，
 * **必然对不上**（user 空间没有那个 rid）。而且因为列表本身有内容，
 * 现象不是"空的"，而是"每一条都恢复失败"，极难往"空间错了"上想。
 *
 * 现在列表与所有操作（恢复/永久删除/清空）统一走这个值，界面上可以显式
 * 切换，不再依赖一个被 recycle 状态污染的变量。
 */
const RECY = { space: "user" };

/* ============ 重复照片扫描 ============ */
const DUP = { taskId: null, res: null, busy: false, err: "" };

/* ============ 设备诊断（错误码 / 维修模式 / Samba）============ */
const DIAG = { res: null, busy: false, err: "" };

/** 多文件整体进度（按字节，不按文件数）。 */
function uploadPct() {
  const us = PH.uploads || [];
  if (!us.length) return 0;
  let tot = 0, done = 0;
  for (const u of us) { tot += u.total || 0; done += u.done || 0; }
  return tot ? Math.min(100, Math.round((done / tot) * 100)) : 0;
}

function renderDiag() {
  if (DIAG.err) return `<div class="err">${esc(DIAG.err)}</div>`;
  if (DIAG.busy) return `<div class="slot sm">读取诊断信息…</div>`;
  if (!DIAG.res) return `<div class="slot sm">点「读取诊断」查看设备错误码、维修模式与共享状态</div>`;
  // 真实返回：{ ok, result: { dev_err_code:{data:{devErr,errorCode}}, repair_mode:{data:{mode}},
  //   samba_public:{Smb1Enable,...}, samba_user:{...} } }
  const r = DIAG.res || {};
  const body = r.result || r || {};
  const dec = (body.dev_err_code || {}).data || {};
  const rep = (body.repair_mode || {}).data || {};
  const sp = body.samba_public || {};
  const su = body.samba_user || {};
  const onOff = (v) => (v == null ? "" : (v ? "开启" : "关闭"));
  const rows = [
    ["设备错误码 devErr", dec.devErr != null ? dec.devErr : ""],
    ["错误码 errorCode", dec.errorCode != null ? dec.errorCode : ""],
    ["维修模式", rep.mode != null ? (rep.mode === 0 ? "关闭" : "开启(" + rep.mode + ")") : ""],
    ["SMB 匿名共享", sp.Smb1Enable != null ? onOff(sp.Smb1Enable) : (sp.Enable != null ? onOff(sp.Enable) : "")],
    ["SMB 账号共享", su.Smb1Enable != null ? onOff(su.Smb1Enable) : (su.Enable != null ? onOff(su.Enable) : "")],
  ].filter(([, v]) => v !== "" && v != null);
  if (!rows.length) return `<div class="slot sm">未返回可展示字段</div>`;
  return `<div class="card">
    <div class="card-h">诊断<span class="hint">排障用</span></div>
    ${rows.map(([k, v]) => `<div class="row"><span class="k">${esc(k)}</span><span class="v">${esc(String(v))}</span></div>`).join("")}
  </div>`;
}

async function diagLoad() {
  const panel = window.__hs_panel;
  DIAG.busy = true; DIAG.err = "";
  if (panel) panel._draw();
  try {
    DIAG.res = await svc("device_diagnostics", {});
  } catch (e) { DIAG.err = String(e.message || e); }
  DIAG.busy = false;
  if (panel) panel._draw();
}

function renderDup() {
  if (DUP.err) return `<div class="err">${esc(DUP.err)}</div>`;
  if (DUP.busy) return `<div class="slot sm">扫描中…（设备侧异步，可稍后点「查看结果」）</div>`;
  if (!DUP.res) return `<div class="slot">点「扫描重复照片」开始；扫描是设备侧异步任务，
    开始后点「查看结果」取最新结果。</div>`;
  // 真实返回：{ ok, result: { data: { fileInfo:[{path,lcdPath,hash,size,result,...}], code, hasMore,
  //   mergeCount, mergeTotal } } }
  const body = (DUP.res || {}).result || DUP.res || {};
  const data = body.data || body || {};
  const list = data.fileInfo || data.files || [];
  const total = data.mergeCount || data.mergeTotal || list.length;
  if (!list.length) return `<div class="slot">暂无重复照片结果（可能仍在扫描）</div>`;
  // 多账号下必须带 acct 段，否则缩略图走主账号会话（第二个账号的图取不到）
  const accSeg = SEL.account ? "acct/" + encodeURIComponent(SEL.account) + "/" : "";
  const base = "/api/huawei_home_storage/image/" + (window.__hs_entry_id || "") + "/" + accSeg;
  return `<div class="card">
    <div class="card-h">重复照片<span class="hint">${list.length} 项 · 合并计数 ${total}</span></div>
    <div class="phgrid">
      ${list.slice(0, 60).map((f) => {
        const thumb = f.lcdPath || f.path || "";
        return `<div class="ph" data-act="file-open"
          data-url="${esc(thumb ? base + "thumb" + thumb : "")}">
          ${thumb ? `<img data-src="${esc(base + "thumb" + thumb)}" alt="" style="opacity:0">`
                  : `<div class="sk"></div>`}
          <span class="cap">${esc(String(f.path || "").split("/").pop() || "")}</span>
        </div>`;
      }).join("")}
    </div>
    ${data.hasMore ? '<div class="note">还有更多，结果按 limit 截断</div>' : ""}
  </div>`;
}

async function dupStart() {
  const panel = window.__hs_panel;
  DUP.busy = true; DUP.err = ""; DUP.res = null;
  if (panel) panel._draw();
  try {
    const r = await svc("duplicate_scan", { act: "start" });
    // 返回 { act, result: { data: { taskId } } } —— taskId 用于查结果
    const data = (r && r.result && r.result.data) || r || {};
    DUP.taskId = data.taskId || data.task_id || null;
    toast(DUP.taskId ? "扫描已启动（taskId " + DUP.taskId + "）" : "扫描已启动");
  } catch (e) { DUP.err = String(e.message || e); }
  DUP.busy = false;
  if (panel) panel._draw();
}

async function dupResult() {
  const panel = window.__hs_panel;
  if (!DUP.taskId) { toast("请先启动扫描"); return; }
  DUP.busy = true; DUP.err = "";
  if (panel) panel._draw();
  try {
    DUP.res = await svc("duplicate_scan_result", { task_id: DUP.taskId, limit: 100 });
  } catch (e) { DUP.err = String(e.message || e); }
  DUP.busy = false;
  if (panel) panel._draw();
}

/* ============ 批量选择（多选后批量操作）============ */
const PICK = { on: false, set: new Set(), base: "/file/", last: null };

/** 当前列表所有可勾选路径（顺序稳定，供 Shift 范围选择用）。 */
function pickAllPaths() {
  const base = PH.path || "/file/";
  const files = (PH.data && PH.data.files) || [];
  return files.map((f) => base + f.name + (f.type === 8 ? "" : "/"));
}

function pickCount() { return PICK.set.size; }

function togglePick(path) {
  if (PICK.set.has(path)) PICK.set.delete(path); else PICK.set.add(path);
  return PICK.set.size;
}

function pickToggleBar() {
  // 顶部工具条：进入/退出多选模式 + 批量操作
  if (!PICK.on) {
    return `<div class="actions" style="margin-bottom:12px">
      <button class="btn sm" data-act="pick-on">批量选择</button>
    </div>`;
  }
  const n = pickCount();
  return `<div class="pickbar">
    <span class="cnt">已选 <b>${n}</b> 项</span>
    <button class="btn sm" data-act="pick-all">全选</button>
    <button class="btn sm" data-act="pick-none">取消全选</button>
    <span class="spacer" style="flex:1"></span>
    <button class="btn sm" data-act="pick-move" ${n ? "" : "disabled"}>移动</button>
    <button class="btn sm" data-act="pick-copy" ${n ? "" : "disabled"}>复制</button>
    <button class="btn sm danger" data-act="pick-del" ${n ? "" : "disabled"}>删除</button>
    <button class="btn sm" data-act="pick-off">退出</button>
  </div>`;
}

async function pickRun(op) {
  const ids = [...PICK.set];
  if (!ids.length) { toast("请先选择文件"); return; }
  const label = op === "move" ? "移动" : op === "copy" ? "复制" : "删除";
  if (op === "delete") {
    if (!window.confirm("删除选中的 " + ids.length + " 项？\n\n会移入设备回收站，可恢复。")) return;
  } else {
    // 用目录选择器代替手输路径（手打 /file/xxx/ 容易错）
    openDestPicker(async (dest, destSpace) => {
      try {
        // ⚠️ 必须传 dest_category（2026-10-29 修）：后端
        // ``move_paths`` / ``copy_paths`` 一直支持跨空间（src_category /
        // dst_category），yaml 也声明了，但面板从来没传 —— 于是「移到共享」
        // 这个操作在 UI 上根本不存在。不传时后端把 dest_category 兜底成
        // category，等于永远只在原空间内操作。
        await svc(op === "move" ? "move_paths" : "copy_paths", {
          paths: ids,
          dest_dir: dest,
          category: curSpace(),
          dest_category: destSpace || curSpace(),
        });
        toast("已" + label + " " + ids.length + " 项");
        PICK.on = false; PICK.set.clear();
        loadFiles();
      } catch (e) { toast(label + "失败：" + String(e.message || e)); }
    }, op);
    return;
  }
  try {
    await svc("delete_paths", { paths: ids, category: curSpace() });
    toast("已删除（进回收站）" + ids.length + " 项");
    PICK.on = false; PICK.set.clear();
    loadFiles();
  } catch (e) { toast("删除失败：" + String(e.message || e)); }
}
const SRC = { kw: "", res: null, busy: false, err: "" };

/* ============ 皮肤 ============ */
const SKINS = [
  { key: "native",   icon: "◐", title: "跟随 HA 主题" },
  { key: "aurora",   icon: "◍", title: "极光（玻璃·青蓝）" },
  { key: "midnight", icon: "◑", title: "墨夜（深色·霓虹）" },
  { key: "sand",     icon: "◒", title: "暖砂（浅色暖调）" },
  { key: "forest",   icon: "◓", title: "森屿（自然青绿）" },
];
const SKIN_KEY = "huawei_storage_skin";
let CUR_SKIN = "native";
try { CUR_SKIN = localStorage.getItem(SKIN_KEY) || "native"; } catch (e) { CUR_SKIN = "native"; }

function applySkin(key) {
  CUR_SKIN = key;
  try { localStorage.setItem(SKIN_KEY, key); } catch (e) { /* 隐私模式下忽略 */ }
  const host = document.querySelector("huawei-storage-panel");
  if (!host) return;
  if (key === "native") host.removeAttribute("data-skin");
  else host.setAttribute("data-skin", key);
}

function renderSkinner() {
  return `<div class="skinner" title="切换界面皮肤">
    ${SKINS.map((x) => `<button data-act="skin" data-skin="${x.key}"
      class="${x.key === CUR_SKIN ? "on" : ""}" title="${x.title}"
      style="background:${skinSwatch(x.key)}">${x.icon}</button>`).join("")}
  </div>`;
}

function skinSwatch(key) {
  const map = {
    native:   "linear-gradient(135deg,#e8eef5,#c8d4e2)",
    aurora:   "linear-gradient(135deg,#29c2f0,#0e8fc4)",
    midnight: "linear-gradient(135deg,#38d6f5,#1a2b3d)",
    sand:     "linear-gradient(135deg,#e0a066,#c8763c)",
    forest:   "linear-gradient(135deg,#57c48c,#2fa563)",
  };
  return map[key] || map.native;
}
const SEL = { entry: null, account: null };
const ALB = { data: null, group: null, album: null, photos: [], next: null, loading: false, err: "",
              /** 上传照片到相册的进度：{ name, done, total, pct, phase } | null */
              up: null };


/* ===================== 后端调用 ===================== */
function hassOf() {
  // ⚠️ 不能只依赖 window.__hs_panel：它是在首次 _draw() 里才赋值的，
  // 而首次 _load() 跑在 _draw() 之前 —— 那样首屏必然报「未连接到 Home Assistant」。
  const p = window.__hs_panel;
  if (p && (p.hass || p._hass)) return p.hass || p._hass;
  const el = document.querySelector("huawei-storage-panel");
  if (el && (el.hass || el._hass)) {
    window.__hs_panel = el;
    return el.hass || el._hass;
  }
  return null;
}

async function apiGet(path) {
  const h = hassOf();
  if (!h) throw new Error("未连接到 Home Assistant");
  const r = await h.fetchWithAuth(path);
  if (!r.ok) throw new Error("HTTP " + r.status);
  return r.json();
}

/* 图片懒加载：fetchWithAuth → blob（<img> 无法携带认证头）
 * 限并发 + IntersectionObserver，避免一次打出上百请求压垮设备会话。 */
const IMG_QUEUE = [];
let IMG_RUNNING = 0;
const IMG_MAX = 6;

function pumpImages() {
  while (IMG_RUNNING < IMG_MAX && IMG_QUEUE.length) {
    const job = IMG_QUEUE.shift();
    IMG_RUNNING++;
    loadOneImage(job).finally(() => { IMG_RUNNING--; pumpImages(); });
  }
}

async function loadOneImage({ img, url }) {
  if (!img.isConnected || img.dataset.done) return;
  img.dataset.done = "1";
  try {
    const h = hassOf();
    const r = await h.fetchWithAuth(url);
    if (!r.ok) throw new Error("HTTP " + r.status);
    const blobUrl = URL.createObjectURL(await r.blob());
    // ⚠️ 缩略图数量可达数千（633 个相册封面 / 无限加载的照片），
    // 每个 blob 不释放会一直占内存。图被移除/替换时释放它。
    img.dataset.blobUrl = blobUrl;
    img.addEventListener("load", function onLoad() {
      // 图已解码进 <img>，blob URL 不再需要（保留 src 显示的副本）
      // 注意：不能立刻 revoke，否则已解码图像仍显示但无法再引用；
      // 改为在 img 从 DOM 移除时统一释放（见 releaseImageBlob）。
      img.removeEventListener("load", onLoad);
    });
    img.dataset.loaded = "1";
    img.src = blobUrl;
    img.style.opacity = "1";
  } catch (e) {
    img.style.opacity = ".25";
    img.dataset.failed = "1";
  }
}

/** 释放一个 <img> 持有的 blob URL（在从 DOM 移除前调用）。 */
function releaseImageBlob(img) {
  const u = img && img.dataset && img.dataset.blobUrl;
  if (u) {
    try { URL.revokeObjectURL(u); } catch (e) { /* 已释放 */ }
    delete img.dataset.blobUrl;
  }
}

/** 重绘前清空区域：释放该区域所有缩略图 blob，避免切换视图后残留。 */
function releaseImagesIn(root) {
  if (!root) return;
  root.querySelectorAll("img[data-blob-url]").forEach(releaseImageBlob);
}

/* 模块级 observer：**必须复用并清理**。
   此前每次 queueImages 都 new 两个 IntersectionObserver 且从不 disconnect ——
   而 queueImages 在每次 _draw 都调用，来回切视图会累积几十上百个 observer（内存泄漏）。 */
let _ioLoad = null;      // 进入可视区 → 加入加载队列
let _ioRecycle = null;   // 离屏 → 回收 blob
let _ioLastRoot = null;

function _ensureObservers() {
  if (!_ioLoad) {
    _ioLoad = new IntersectionObserver((entries) => {
      entries.forEach((en) => {
        if (!en.isIntersecting) return;
        const img = en.target;
        _ioLoad.unobserve(img);
        IMG_QUEUE.push({ img, url: img.dataset.src });
        pumpImages();
      });
    }, { rootMargin: "300px" });

    // 离屏回收：释放已加载图的 blob，避免长列表无限增长内存。
    // 注意 rootMargin 比加载的小（0 vs 300），避免在预加载区来回抖动。
    _ioRecycle = new IntersectionObserver((ents) => {
      ents.forEach((en) => {
        const img = en.target;
        if (en.isIntersecting) return;
        if (img.dataset.loaded === "1" && img.dataset.src) {
          releaseImageBlob(img);
          img.removeAttribute("src");
          img.dataset.loaded = "0";
        }
      });
    }, { rootMargin: "0px", threshold: 0 });
  }
}

function queueImages(root) {
  if (!root || !root.querySelectorAll) return;
  const imgs = [...root.querySelectorAll("img[data-src]")];
  if (!imgs.length) return;
  _ensureObservers();
  // 换了渲染根节点 → 旧节点的监听已随 DOM 移除，解绑避免残留引用
  if (_ioLastRoot && _ioLastRoot !== root) {
    try { _ioLoad.disconnect(); _ioRecycle.disconnect(); } catch (e) { /* 已断开 */ }
    _ioLoad = null; _ioRecycle = null;
    _ensureObservers();
  }
  _ioLastRoot = root;
  imgs.forEach((im) => { _ioLoad.observe(im); _ioRecycle.observe(im); });
}

/** 组件卸载/离开时彻底清理 observer（配合 disconnectedCallback）。 */
function cleanupImages() {
  try { if (_ioLoad) _ioLoad.disconnect(); if (_ioRecycle) _ioRecycle.disconnect(); } catch (e) { /* 已断开 */ }
  _ioLoad = null; _ioRecycle = null; _ioLastRoot = null;
  IMG_QUEUE.length = 0;
}

/* ===================== 视图 ===================== */

/* ---------- 概览 ---------- */
function renderOverview(d) {
  const c = d.counts || {};
  const dk = d.disk || {};
  const pct = dk.total ? Math.round((dk.used / dk.total) * 100) : 0;
  const cls = pct >= 90 ? "danger" : pct >= 75 ? "warn" : "";
  const online = !!d.online;
  const albums = (c.face_albums || 0) + (c.place_albums || 0) + (c.scene_albums || 0);

  // 概览既是看板也是入口：卡片可点（data-act="nav"），直接跳对应视图。
  // 原来的「浏览相册/浏览文件」按钮已删 —— 它们和侧栏导航完全重复。
  return `
    <h2 class="view-title">概览</h2>
    <div class="card tile-link" data-act="nav" data-view="files">
      <div class="card-h">存储容量
        <span class="hint">${fmtSize(dk.used || 0)} / ${fmtSize(dk.total || 0)}</span></div>
      <div style="font-family:var(--font-display);font-size:34px;font-weight:700;font-variant-numeric:tabular-nums;letter-spacing:-.5px">
        ${pct}%<span style="font-size:14px;font-weight:500;color:var(--text2);margin-left:8px">
        已使用</span></div>
      <div class="bar ${cls}"><i style="width:${pct}%"></i></div>
      <div style="display:flex;gap:18px;margin-top:12px;font-size:12.5px;color:var(--text2)">
        <span>已用 <b style="color:var(--text)">${fmtSize(dk.used || 0)}</b></span>
        <span>可用 <b style="color:var(--text)">${fmtSize(dk.free || 0)}</b></span>
        <span style="margin-left:auto;color:var(--brand)">查看文件</span>
      </div>
    </div>

    <div class="grid kpi">
      <div class="tile tile-link" data-act="nav" data-view="albums"><div class="ico">IMG</div><div>
        <div class="lab">照片</div><div class="val">${c.photos ?? "-"}</div></div></div>
      <div class="tile tile-link" data-act="nav" data-view="albums"><div class="ico">VID</div><div>
        <div class="lab">视频</div><div class="val">${c.videos ?? "-"}</div></div></div>
      <div class="tile tile-link" data-act="nav" data-view="files"><div class="ico">DOC</div><div>
        <div class="lab">文件</div><div class="val">${c.all_files ?? "-"}</div></div></div>
      <div class="tile tile-link ${online ? "good" : "danger"}" data-act="nav" data-view="device">
        <div class="ico">NET</div><div>
        <div class="lab">设备状态</div><div class="val">${online ? "在线" : "离线"}</div></div></div>
      <div class="tile tile-link" data-act="nav" data-view="users"><div class="ico">USR</div><div>
        <div class="lab">设备用户</div><div class="val">${(d.device_users || []).length}</div></div></div>
      <div class="tile tile-link" data-act="nav" data-view="albums"><div class="ico">ALB</div><div>
        <div class="lab">智能相册</div><div class="val">${albums || "-"}</div></div></div>
    </div>

    ${(c.duplicate_photos || DUP.taskId || DUP.res) ? `<div class="card" style="margin-top:var(--gap)">
      <div class="card-h">重复照片
        <span class="hint">${c.duplicate_photos != null ? c.duplicate_photos + " 张" : ""}</span></div>
      ${renderDup()}
    </div>` : ""}
    <div class="card" style="margin-top:var(--gap)">
      <div class="card-h">操作</div>
      <div class="actions">
        <button class="btn pri" data-act="refresh">刷新凭据</button>
        <button class="btn" data-act="dup">扫描重复照片</button>
        <button class="btn sm" data-act="dup-res">查看结果</button>
      </div>
      <div class="note">导航直接点上面的卡片：容量/文件→文件，照片/视频/智能相册→相册，状态→设备，用户→用户。</div>
    </div>`;
}

/* ---------- 相册 ---------- */
function renderAlbums(d) {
  const cur = d.current_account;
  if (ALB.album) return renderAlbumDetail(d);

  if (!ALB.data) {
    setTimeout(() => loadAlbums(), 0);
    return `
      <div class="vhead"><h2>相册</h2>
        <span class="sub">${cur ? "账号 " + esc(cur.label || "") : ""}</span></div>
      <div class="albums">${Array.from({ length: 8 }).map(() =>
        `<div class="alb"><div class="cov"><div class="sk"></div></div>
         <div class="meta"><div class="nm">&nbsp;</div><div class="ct">&nbsp;</div></div></div>`).join("")}
      </div>`;
  }
  if (ALB.data._err) return `<h2 class="view-title">相册</h2>
    <div class="err">相册载入失败：${esc(ALB.data._err)}</div>`;

  const groups = ALB.data.groups || [];
  if (!groups.length) return `<h2 class="view-title">相册</h2>
    <div class="slot">没有可显示的相册</div>`;

  const g = (ALB.group && groups.find((x) => x.key === ALB.group)) || groups[0];
  const albums = g.albums || [];

  return `
    <div class="vhead"><h2>相册</h2>
      <span class="sub">共 ${ALB.data.total || 0} 个</span>
      <span class="spacer"></span>
      <button class="btn sm pri" data-act="alb-create">＋ 新建相册</button>
      ${cur ? `<span class="acct on"><span class="av">${esc((cur.label || "?").slice(0, 2))}</span>
        ${esc(cur.label || "")}</span>` : ""}
    </div>
    <div class="segs" style="margin-bottom:16px">
      ${groups.map((x) => `<span class="seg ${x.key === g.key ? "on" : ""}"
        data-act="alb-group" data-key="${esc(x.key)}">${esc(x.title)}
        <span class="n">${x.albums.length}</span></span>`).join("")}
    </div>
    ${g.key === "user" ? `<div class="note" style="margin-bottom:12px;color:var(--brand)">
      <b>共享相册</b>：家庭成员共同维护的相册（设备 albumType=6）。
      可以新建、上传、把照片加进来或移出；这里的改动<b>全家都能看到</b>。
    </div>` : `<div class="note" style="margin-bottom:12px;color:var(--text2)">
      设备自动生成的分类（${esc(g.title)}），只读 —— 不能新建、上传或删除。
    </div>`}
    ${albums.length ? `<div class="albums">
      ${albums.map((a) => `
        <div class="alb" data-act="alb-open" data-type="${a.type}" data-id="${a.id}"
             data-name="${esc(a.name)}">
          <div class="cov">
            ${a.thumbUrl ? `<img data-src="${esc(a.thumbUrl)}" alt="" style="opacity:0">`
                         : `<div class="ph">🖼️</div>`}
          </div>
          <div class="meta"><div class="nm">${esc(a.name)}</div>
            <div class="ct">${a.count} 张</div></div>
        </div>`).join("")}
    </div>` : `<div class="slot">该分类暂无相册</div>`}`;
}

/* ---------- 相册操作（用新服务 add_to_album / share_to_person）---------- */
async function albumAddTo(albumId, albumType, fileIds, albumName) {
  // ⚠️ file_ids 必须是**相册域的 fileId**（不是文件空间的 fid）
  try {
    await svc("add_to_album", {
      album_id: Number(albumId),
      album_type: Number(albumType),
      file_ids: fileIds,
      album_name: albumName || "",
      ...accArg(),
    });
    toast("已加入相册 " + (fileIds.length || 0) + " 项");
  } catch (e) {
    toast("加入相册失败：" + String(e.message || e));
  }
}

async function albumShareToPerson(albumId, ownerId, fileIds, albumName, albumType) {
  // ⚠️ album_type 必须用**目标相册的真实类型**（2026-10-29 修）。
  //
  // 这里原本硬编码 23（人物相册），但调用方给它的是「共享相册」分组里的
  // 相册（albumType=6）。于是发出去的是 `album_id=<6号相册的id>` +
  // `album_type=23` —— 后端拿着这个 id 去 23 号相册里找，必然找不到或
  // 操作到错的相册。表现为"共享失败"却看不出原因。
  try {
    await svc("share_to_person", {
      album_id: Number(albumId),
      album_type: Number(albumType || 6),
      owner_id: String(ownerId),
      file_ids: fileIds,
      album_name: albumName || "",
      ...accArg(),
    });
    toast("已共享给家人");
  } catch (e) {
    toast("共享失败：" + String(e.message || e));
  }
}

/* ---------- 相册管理：新建 / 删除 / 上传照片 ---------- */

/**
 * 拉「共享相册」（albumType=6）列表，不污染相册页状态。
 *
 * 单独写这个而不是复用 ``loadAlbums()``：后者会把结果写进 ``ALB.data``
 * 并触发重绘，在文件页弹窗时用会把用户切走。
 */
async function fetchUserAlbums() {
  const eid = window.__hs_entry_id || "";
  if (!eid) return [];
  const acc = SEL.account ? `?account=${encodeURIComponent(SEL.account)}` : "";
  const res = await apiGet(
    `/api/huawei_home_storage/albums/${encodeURIComponent(eid)}${acc}`
  );
  const groups = res.groups || [];
  const g = groups.find((x) => x.key === "user");
  return (g && g.albums) || [];
}

/**
 * 把**文件空间里的一个路径**复制进相册（``/trans/acrosscopy``）。
 *
 * 全面板只有这一处调 ``copy_to_album``，上传流程和右键菜单共用，
 * 免得两边对 ``category`` / ``album_category`` 的理解慢慢分叉。
 *
 * @returns {Promise<{ok:boolean, error?:string}>} 不抛异常，方便调用方汇总
 */
async function copyPathToAlbum(path, albumId, albumName, albumType, space) {
  // ⚠️ 需要重试（2026-10-29 加）：
  // ``copy_to_album`` 在设备侧是按**路径**找 fid（后端 ``async_find_entry``
  // 列父目录逐个比对名字），而"刚上传完立刻加入相册"是最主要的用法 ——
  // 设备对新文件的目录索引有延迟，此时会返回「找不到源文件」。
  // 那不是真失败，等几百毫秒再查就有了。不重试的话，用户看到的是
  // "上传成功但加入相册失败"，而文件明明就在那儿。
  //
  // 只对"找不到源文件"这类**可重试**的错误重试；其它错误（比如相册 id 错、
  // 空间不匹配）立刻返回，免得白等 3 轮还掩盖真实原因。
  const RETRYABLE = /找不到源文件|not\s*found|不存在|no\s*such/i;
  const delays = [600, 1200, 2000];
  let last = { ok: false, error: "" };

  for (let attempt = 0; attempt <= delays.length; attempt++) {
    last = await copyPathToAlbumOnce(path, albumId, albumName, albumType, space);
    if (last.ok) return last;
    if (attempt >= delays.length) break;
    if (!RETRYABLE.test(last.error || "")) return last;
    await sleep(delays[attempt]);
  }
  return last;
}

/** 把文件空间的一个路径复制进相册，单次尝试（不重试）。 */
async function copyPathToAlbumOnce(path, albumId, albumName, albumType, space) {
  try {
    const res = await svc("copy_to_album", {
      paths: [path],
      album_id: Number(albumId),
      album_type: Number(albumType),
      album_name: albumName || "",
      // 源文件在哪个空间，就告诉后端去哪个空间找 fid；
      // 目标相册也在同一空间（user/public 各自独立），所以两个都传。
      album_category: space,
      category: space,
      ...accArg(),
    });
    if (res && res.ok === false) {
      return { ok: false, error: res.error || "设备拒绝" };
    }
    return { ok: true };
  } catch (e) {
    return { ok: false, error: String(e.message || e) };
  }
}

/**
 * 文件页右键「加入相册（共享）」：选一个目标相册，把该文件复制进去。
 *
 * 🚨 **当前没有调用方**（2026-10-29 真机实测后移除了右键入口）。
 *
 * 它背后是 ``copy_to_album``，实测**假成功**：返回 ``code=0``、传输任务
 * ``progress=100``，但相册里什么都不会多出来。既然做不到，就不该给入口 ——
 * 用户点了看到"已加入相册"再去找不到，比没有按钮更糟。
 *
 * 函数与 ``copyPathToAlbum`` 的重试壳暂时保留，等 ``copy_to_album`` 在设备侧
 * 弄明白之后再接回 UI（见 ``services.py::_copy_to_album`` 的排查记录）。
 *
 * 为什么叫「共享」：设备上用户自建/家庭共建的相册都是 ``albumType=6``，
 * 在原生 App 里归在「共享」下（实测成员是两个 ownerId）。集成沿用这个叫法，
 * 免得用户以为还有个"私人相册"选项。
 */
async function openAlbumTargetPicker(filePath, fileName) {
  const panel = window.__hs_panel;
  const host = (panel && panel.shadowRoot) || document.body;
  let albums = [];
  let err = "";
  try {
    albums = await fetchUserAlbums();
  } catch (e) {
    err = String(e.message || e);
  }

  const m = document.createElement("div");
  m.className = "modal";
  m.innerHTML = `
    <div class="mbox">
      <h3>加入相册</h3>
      <p class="sub">${esc(fileName)} · 选择目标相册（共享）</p>
      ${err ? `<div class="err">${esc(err)}</div>` : ""}
      ${!albums.length
        ? `<div class="slot sm">还没有自建相册。先到「相册」页点「＋ 新建相册」。</div>`
        : `<div>${albums.map((x) => `<div class="filerow dir" data-id="${x.id}"
            data-name="${esc(x.name)}">
            <span class="fico">[A]</span>
            <span class="fmain"><span class="fname">${esc(x.name)}</span>
              <span class="fsub">${x.count} 张</span></span></div>`).join("")}</div>`}
      <div class="mactions"><button class="btn" data-close>取消</button></div>
    </div>`;
  host.appendChild(m);
  const close = () => m.remove();
  m.addEventListener("click", async (e) => {
    if (e.target === m || e.target.closest("[data-close]")) { close(); return; }
    const row = e.target.closest("[data-id]");
    if (!row) return;
    close();
    const space = curSpace();
    const r = await copyPathToAlbum(
      filePath, Number(row.dataset.id), row.dataset.name, 6, space
    );
    if (r.ok) {
      toast("已加入相册「" + row.dataset.name + "」");
    } else {
      toast("加入相册失败：" + r.error);
    }
  });
}

/**
 * 新建相册。
 *
 * ⚠️ ``album_type`` 必须传 **6**。设备把 6 号当作「共享相册」（家庭多成员
 * 共建，实测 ownerId 有 10001/10002 两个归属人），服务端默认值 0 在设备上
 * 不是一个合法的用户相册类型 —— 传 0 建出来的东西不会出现在任何分组里。
 * 面板的相册列表也是按 ``_ALBUM_GROUPS`` 里的 ("user", "共享相册", (6,))
 * 展示的，类型对不上就"建了但看不到"。
 */
async function createAlbum(name) {
  const nm = String(name || "").trim();
  if (!nm) { toast("相册名不能为空"); return; }
  try {
    const res = await svc("add_album", { name: nm, album_type: 6, ...accArg() });
    if (res && res.ok === false) {
      toast("新建相册失败：" + (res.error || "设备拒绝"));
      return;
    }
    toast("已创建相册：" + nm);
    ALB.data = null;            // 强制重新拉列表
    ALB.group = "user";         // 切到共享相册分组，能立刻看到新建的
    await loadAlbums();
  } catch (e) {
    toast("新建相册失败：" + String(e.message || e));
  }
}

/**
 * 删除相册（不可逆）。
 *
 * ⚠️ 后端自 2026-10-29 起要求 ``confirm: "DELETE_ALBUM"``，不传会被拒。
 * 这里两层确认：先是浏览器的 confirm 弹窗（防误点），再是给后端的 confirm
 * 字段（防绕过 UI 直接调服务）。
 */
async function deleteAlbum() {
  const a = ALB.album;
  if (!a) return;
  const n = ALB.photos ? ALB.photos.length : 0;
  const ok = window.confirm(
    `删除相册「${a.name}」？\n\n` +
    `⚠️ 不可逆：删的是相册本身，不是把照片移进回收站。\n` +
    `家庭成员共享的照片会一起从这个相册消失，没有撤销。\n\n` +
    (n ? `（当前已载入 ${n} 张，实际数量可能更多）\n\n` : "")
  );
  if (!ok) return;
  try {
    const res = await svc("del_album", {
      album_id: Number(a.id),
      album_type: Number(a.type),
      confirm: "DELETE_ALBUM",
      ...accArg(),
    });
    if (res && res.ok === false) {
      toast("删除相册失败：" + (res.error || "设备拒绝"));
      return;
    }
    toast("已删除相册：" + a.name);
    ALB.album = null; ALB.photos = []; ALB.next = null;
    ALB.data = null;
    await loadAlbums();
  } catch (e) {
    toast("删除相册失败：" + String(e.message || e));
  }
}

/**
 * 相册重命名（``POST /gallery/albumCfg``，2026-10-30 抓包确认的写接口）。
 *
 * 三个"重命名"别搞混：
 *   * ``rename_path``   —— 文件空间的文件/目录名
 *   * ``rename_media``  —— 单张照片的名字
 *   * ``album_rename``  —— **相册本身**（本函数）
 */
async function renameAlbum() {
  const a = ALB.album;
  if (!a) return;
  const oldName = String(a.name || "");
  openPrompt({
    title: "重命名相册",
    label: "新名称",
    value: oldName,
    hint: "共享相册改名后，家庭成员那边也会看到。",
    onOk: async (name) => {
      const nm = String(name || "").trim();
      if (!nm) { toast("相册名不能为空"); return; }
      if (nm === oldName) { toast("名称没有变化"); return; }
      try {
        const res = await svc("album_rename", {
          album_id: Number(a.id),
          new_name: nm,
          album_type: Number(a.type) || 6,
          ...accArg(),
        });
        if (res && res.ok === false) {
          toast("重命名失败：" + (res.error || "设备拒绝"));
          return;
        }
        toast("已重命名为 " + nm);
        // 就地改本地状态，避免整页重拉；列表缓存放掉，返回时重新取
        a.name = nm;
        ALB.data = null;
        const panel = window.__hs_panel;
        if (panel) panel._draw();
      } catch (e) {
        toast("重命名失败：" + String(e.message || e));
      }
    },
  });
}

/** 上传照片进相册的进度条。 */
function renderAlbumUpload() {
  const u = ALB.up;
  if (!u) return "";
  const label = u.phase === "copy" ? "收进相册…" : "上传中…";
  return `<div class="card" style="padding:12px 16px;margin-bottom:12px">
    <div style="display:flex;align-items:center;gap:10px;font-size:12.5px;margin-bottom:8px">
      <b>${esc(label)} ${esc(u.name || "")}</b>
      <span style="flex:1"></span>
      <span style="color:var(--brand);font-weight:600">${u.pct || 0}%</span>
    </div>
    <div class="bar"><i style="width:${u.pct || 0}%"></i></div>
    <div class="note" style="margin-top:8px">${esc(u.msg || "")}</div>
  </div>`;
}

/**
 * 上传照片到**当前打开的相册**。
 *
 * 这里是整个面板最容易做错的一处，说明白为什么分两步：
 *
 * 1. **先传到文件空间**（``/filesvc/prepareUpload`` + ``/upload``）。
 *    直接把照片"传进相册"需要走相册域（``/gallery/prepareUpload``），
 *    那条路**至今没跑通**（卡 ``code=30104``）。
 *
 * 2. **再用 ``copy_to_album`` 跨域复制进相册**（``/trans/acrosscopy``）。
 *    这条是抓包实证过的路径（capture.jsonl L268）：源是 filesvc 的 fid，
 *    目标是 gallery 的 albumId。它不需要相册域 fileId，所以能绕开 30104。
 *
 * 关键点：**不能**拿上传返回的 fileId 去调 ``add_to_album`` —— 那是文件域
 * 的 id（288…），相册接口只认相册域（281…），会被拒 ``code=30101``。
 * 必须让后端按**路径**重新解析 fid（``copy_to_album`` 的 paths 参数）。
 */
/**
 * ✅ ``copy_to_album`` 在补上 ``addTime`` 之后**真机可用**（2026-10-29 复测）。
 *
 * 这里曾挂着一段"不调 copy_to_album"的说明，因为当时它是**假成功**：
 * 返回 ``code=0``、任务 ``progress=100``，但相册一张不多、文件空间也没副本。
 * 后来拿抓包报文逐字段对比，发现 ``dest.dirs`` 少了一个 ``addTime`` ——
 * 设备对它做"字段存在性"校验，缺了不报错、只是什么都不做。
 *
 * 教训：**异步任务的 ``code=0`` 不等于数据到了**。所以现在每次收进相册
 * 之后都会用 ``albumPhotoCount`` 回查一遍相册张数，没变就如实报失败。
 */
async function albumUploadFiles(files) {
  const a = ALB.album;
  if (!a) return;
  const panel = window.__hs_panel;
  // ⚠️ 固定 "user"，**不要**用 curSpace()（2026-10-29 修）：
  // 相册页没有空间概念（相册视图不传 category），而 ``PH.space`` 是**文件页**
  // 的状态。用户在文件页切到「共享」再点进相册，``PH.space`` 仍是 "public"，
  // 照片就会被悄悄传到共享空间的暂存目录、``copy_to_album`` 也用 public ——
  // 而相册页显示的相册跟这个空间没有关系。固定用默认空间，行为可预期。
  const space = "user";
  // 暂存目录：不污染用户的目录树，传完就留在那儿（用户可在文件页清理）
  const staging = "/file/_相册导入/";
  let okCount = 0;
  const failures = [];
  // 复核基线：异步任务只告诉我们"受理了"，必须回查相册本身
  const before = await albumPhotoCount(a);

  for (const file of files) {
    ALB.up = { name: file.name, pct: 0, phase: "upload", msg: "传到文件空间…" };
    if (panel) panel._draw();
    try {
      const dest = staging + file.name;
      await uploadRaw(file, dest, space, (pct) => {
        if (!ALB.up) return;
        ALB.up.pct = pct;
        if (panel) panel._draw();
      });
      // 第二步：收进相册（``/trans/acrosscopy``）
      //
      // ✅ 2026-10-29 真机打通：这一步以前是"假成功"（返回 code 0、任务
      // progress 100，但相册一张不多），原因是 dest 少了 ``addTime`` 字段。
      // 补上后实测：临时相册 0 张 → 3 秒内变 1 张。
      //
      // ⚠️ 所以这里**必须复查**再报成功（下面的 albumPhotoCount）：
      // 异步任务的 code=0 不代表数据真的到了，只代表任务被受理。
      ALB.up.phase = "copy";
      ALB.up.pct = 100;
      ALB.up.msg = "已上传，正在收进相册…";
      if (panel) panel._draw();
      const r = await copyPathToAlbum(dest, a.id, a.name, a.type, space);
      if (!r.ok) {
        failures.push(`${file.name}：${r.error}`);
      } else if (before !== null) {
        // 设备索引有延迟，最多等 ~6s（0.8s × 8 次）
        let now = before;
        for (let i = 0; i < 8; i += 1) {
          now = await albumPhotoCount(a);
          if (now !== null && now > before + okCount) break;
          await sleep(800);
        }
        if (now !== null && now > before + okCount) {
          okCount += 1;
        } else {
          failures.push(`${file.name}：设备返回成功但相册没变化`);
        }
      } else {
        okCount += 1;
      }
    } catch (e) {
      failures.push(`${file.name}：${String(e.message || e)}`);
    }
  }

  ALB.up = null;
  if (panel) panel._draw();
  if (okCount) {
    toast(`已把 ${okCount} 张收进「${a.name}」`);
    await loadAlbumPage(false);
  }
  if (failures.length) {
    // 分开报：上传成功但收不进相册的情况必须让用户知道照片在哪
    toast(`有 ${failures.length} 张没进相册（照片仍在「文件」→「_相册导入」）：` +
          failures.slice(0, 2).join("；"));
  }
}

/** 选中文件后上传（相册页按钮触发）。 */
function pickAndUploadToAlbum() {
  const panel = window.__hs_panel;
  const host = (panel && panel.shadowRoot) || document.body;
  const inp = document.createElement("input");
  inp.type = "file";
  // 相册页只收媒体：设备侧 copy_to_album 对非图片/视频没有意义
  inp.accept = "image/*,video/*";
  inp.multiple = true;
  inp.style.display = "none";
  inp.addEventListener("change", () => {
    const fs = Array.from(inp.files || []);
    inp.remove();
    if (fs.length) albumUploadFiles(fs);
  });
  host.appendChild(inp);
  inp.click();
}


/**
 * 相册详情顶部的「归属 / 共享成员」行。
 *
 * ⚠️ 只显示 ID 与人数，**不要试图把 ownerId 映射成昵称**：相册里的
 * ``ownerId`` 是家庭内序号（10001/10002），而 ``/account/userManageInfo``
 * 返回的是账号维度长 ID（2850086……），两套体系对不上
 * （2026-10-30 实测）。硬映射只会显示错人。
 */
function renderAlbumOwnerRow() {
  const a = ALB.album;
  if (!a) return "";
  const members = a.userIds || [];
  if (!a.ownerId && !members.length) return "";
  const bits = [];
  if (a.ownerId) bits.push(`归属 ID：<b>${esc(String(a.ownerId))}</b>`);
  if (members.length) bits.push(`共享成员：<b>${members.length}</b> 人`);
  return `<div class="note" style="margin-bottom:10px;color:var(--text2)">${bits.join(" · ")}</div>`;
}

function renderAlbumDetail() {
  const a = ALB.album;
  const photos = ALB.photos || [];
  // 只有**用户自建/共享相册**（albumType=6）能删、能往里传照片。
  // 智能分类/人物/地点/场景（1/2/22/23/24）是设备自动生成的，删不掉也塞不进。
  const editable = Number(a.type) === 6;
  return `
    <div class="vhead">
      <button class="btn sm" data-act="alb-back">← 返回相册</button>
      <h2>${esc(a.name)}</h2>
      <span class="sub">已载入 ${photos.length} 张</span>
      <span class="spacer"></span>
      ${editable ? `<button class="btn sm pri" data-act="alb-upload"
        title="先传到文件空间，再自动收进本相册">⬆ 上传照片</button>
      <button class="btn sm" data-act="alb-rename" title="改名后家庭成员都会看到">✏️ 重命名</button>
      <button class="btn sm danger" data-act="alb-del">🗑 删除相册</button>` : ""}
    </div>
    ${editable ? `<div class="note" style="margin-bottom:12px;color:var(--warn)">
      上传是<b>两步</b>：先传到「文件」→「_相册导入」，再跨域复制进本相册。
      第二步走 <code>/trans/acrosscopy</code>，真机实测可用，但设备索引有延迟
      （通常 1–3 秒）。若提示"设备返回成功但相册没变化"，照片仍在
      「文件」→「_相册导入」里，可稍后重试或直接去那儿看。
    </div>` : `<div class="note" style="margin-bottom:12px;color:var(--text2)">
      这是设备自动生成的「${esc(a.name)}」分类，不能上传或删除。
      要在「共享相册」里管理自建相册，请先切到那个分组。
    </div>`}
    ${renderAlbumOwnerRow()}
    ${ALB.up ? renderAlbumUpload() : ""}
    ${ALB.err ? `<div class="err">${esc(ALB.err)}</div>` : ""}
    ${pickToggleBar()}
    ${PICK.on ? `<div class="pickbar">
      <span class="cnt">已选 <b>${pickCount()}</b> 张</span>
      <button class="btn sm" data-act="pick-all-photos">全选</button>
      <button class="btn sm" data-act="pick-none">取消</button>
      <span class="spacer" style="flex:1"></span>
      <button class="btn sm pri" data-act="album-add-picked"
        ${pickCount() ? "" : "disabled"}>加入相册</button>
      ${editable ? `<button class="btn sm" data-act="album-remove-picked"
        ${pickCount() ? "" : "disabled"}
        title="只解除与相册的关联，不删照片">移出本相册</button>
      <button class="btn sm" data-act="album-cover-picked"
        ${pickCount() === 1 ? "" : "disabled"}
        title="把选中的这张设为相册封面">设为封面</button>` : ""}
      <button class="btn sm" data-act="album-share-picked"
        ${pickCount() ? "" : "disabled"}>共享给家人</button>
      <button class="btn sm" data-act="pick-off">退出</button>
    </div>` : ""}
    ${photos.length ? `<div class="phgrid">
      ${photos.map((p, i) => {
        const pth = "photo:" + i;
        const on = PICK.set.has(pth);
        return `<div class="ph ${on ? "picked" : ""}" data-act="photo-open" data-idx="${i}">
          ${PICK.on ? `<span class="pickbox ${on ? "on" : ""}" data-act="pick" data-path="${esc(pth)}"></span>` : ""}
          ${p.thumbUrl ? `<img data-src="${esc(p.thumbUrl)}" alt="" style="opacity:0">`
                       : `<div class="sk"></div>`}
          ${p.mtime ? `<span class="cap">${esc(fmtDate(p.mtime).slice(5, 16))}</span>` : ""}
        </div>`;
      }).join("")}
    </div>` : `<div class="slot">${ALB.loading
        ? "正在载入照片…"
        : (editable
            ? "这个相册还没有照片。点上方「⬆ 上传照片」即可。"
            : "这个相册暂无照片")}</div>`}
    ${renderAlbumOp()}
    ${(ALB.next && (ALB.next.last_cre_time || ALB.next.last_row_id))
      ? `<div class="more"><button class="btn" data-act="alb-more"
           ${ALB.loading ? "disabled" : ""}>${ALB.loading ? "载入中…" : "加载更多"}</button></div>`
      : (photos.length ? `<div class="note" style="text-align:center">已到末尾</div>` : "")}`;
}

async function loadAlbums() {
  const eid = window.__hs_entry_id || "";
  if (!eid) return;
  try {
    const acc = SEL.account ? `?account=${encodeURIComponent(SEL.account)}` : "";
    ALB.data = await apiGet(`/api/huawei_home_storage/albums/${encodeURIComponent(eid)}${acc}`);
  } catch (e) {
    ALB.data = { groups: [], total: 0, _err: String(e.message || e) };
  }
  const panel = window.__hs_panel;
  if (panel && panel._view === "albums") panel._draw();
}

async function openAlbum(type, id, name) {
  // ⚠️ 不要只存 {type,id,name}：相册对象里的 ownerId / userIds / hidden
  // 是「共享给家人」「隐藏/恢复」要用的，丢了就只能显示 "-" 或猜状态。
  const groups = (ALB.data && ALB.data.groups) || [];
  let full = null;
  for (const g of groups) {
    for (const a of g.albums || []) {
      if (Number(a.id) === Number(id) && Number(a.type) === Number(type)) full = a;
    }
  }
  ALB.album = full || { type, id, name };
  ALB.photos = [];
  ALB.next = null;
  ALB.err = "";
  const panel = window.__hs_panel;
  if (panel) panel._draw();
  await loadAlbumPage(false);
}

/**
 * 数一遍某个相册里现在有多少张照片（**用于复核异步任务是否真的生效**）。
 *
 * 为什么需要它：``copy_to_album`` 走的是 ``/trans/acrosscopy`` 异步任务，
 * 设备返回 ``code=0``、任务 ``progress=100``，但 2026-10-29 实测过一种
 * "假成功" —— 数据什么都没变。只凭返回值报成功，就是在骗用户。
 *
 * 上限 300 张：够判断"有没有多出来"，又不至于为了复核拉整本相册。
 */
async function albumPhotoCount(album) {
  const eid = window.__hs_entry_id || "";
  if (!eid || !album) return null;
  const q = new URLSearchParams({ num: "300" });
  if (SEL.account) q.set("account", SEL.account);
  try {
    const res = await apiGet(`/api/huawei_home_storage/album/${encodeURIComponent(eid)}`
      + `/${album.type}/${album.id}?${q}`);
    return (res.photos || []).length;
  } catch (e) {
    return null;   // 复核失败不该反过来把成功判成失败
  }
}

async function loadAlbumPage(append) {
  const eid = window.__hs_entry_id || "";
  if (!eid || !ALB.album) return;
  // ⚠️ 竞态防护：记录发起请求时的「相册 + 账号」快照。此前只校验 _view==="albums" ——
  // A→B 快切时两者都是 albums 视图，慢的旧请求返回后会覆盖新相册的照片（串数据）。
  const snapKey = String(ALB.album.type) + ":" + String(ALB.album.id) + ":" + String(SEL.account || "");
  ALB.loading = true;
  try {
    const q = new URLSearchParams({ num: "100" });
    if (SEL.account) q.set("account", SEL.account);
    if (append && ALB.next) {
      q.set("last_cre_time", String(ALB.next.last_cre_time || 0));
      q.set("last_row_id", String(ALB.next.last_row_id || 0));
    }
    const res = await apiGet(`/api/huawei_home_storage/album/${encodeURIComponent(eid)}`
      + `/${ALB.album.type}/${ALB.album.id}?${q}`);
    // 期间切了相册/账号 → 丢弃本次结果，避免串数据
    const nowKey = ALB.album
      ? String(ALB.album.type) + ":" + String(ALB.album.id) + ":" + String(SEL.account || "")
      : null;
    if (nowKey !== snapKey) { ALB.loading = false; return; }
    ALB.photos = append ? ALB.photos.concat(res.photos || []) : (res.photos || []);
    ALB.next = res.next || null;
  } catch (e) {
    ALB.err = String(e.message || e);
  }
  ALB.loading = false;
  const panel = window.__hs_panel;
  if (panel && panel._view === "albums") panel._draw();
}

/* ---------- 文件 ---------- */
function renderFiles(d) {
  const cur = d.current_account;
  const space = PH.space;
  return `
    <div class="vhead"><h2>文件</h2>
      <span class="spacer"></span>
      ${cur ? `<span class="acct on"><span class="av">${esc((cur.label || "?").slice(0, 2))}</span>
        ${esc(cur.label || "")}</span>` : ""}
    </div>
    <div class="segs" style="margin-bottom:16px">
      <span class="seg ${space === "user" ? "on" : ""}" data-act="fs-space" data-space="user">我的文件</span>
      <span class="seg ${space === "public" ? "on" : ""}" data-act="fs-space" data-space="public">共享</span>
      <span class="seg ${space === "recycle" ? "on" : ""}" data-act="fs-space" data-space="recycle">最近删除</span>
      ${space === "recycle" ? `<span class="spacer" style="flex:1"></span>
        <span class="seg ${RECY.space === "user" ? "on" : ""}"
          data-act="recy-space" data-space="user">我的文件</span>
        <span class="seg ${RECY.space === "public" ? "on" : ""}"
          data-act="recy-space" data-space="public">共享</span>` : ""}
      ${space !== "recycle" ? `<span class="spacer" style="flex:1"></span>
        <button class="btn sm" data-act="fs-mkdir">＋ 新建文件夹</button>
        <button class="btn sm pri" data-act="fs-upload">⬆ 上传文件</button>
        <input type="file" id="fsFile" style="display:none">` : ""}
    </div>
    ${renderDestPicker()}
    ${pickToggleBar()}
    ${space === "public" ? `<div class="note" style="margin-bottom:10px;color:var(--brand)">
      <b>共享空间</b>：这里的文件和文件夹<b>家庭成员都能看到、都能改</b>。
      新建的文件夹就是「共享目录」，所有人可见 —— 不需要再单独授权给谁。
    </div>` : ""}
        <div class="note" style="margin-bottom:12px;color:var(--text2)">
      这里上传的是<b>文件空间</b>，不会自动进相册 —— 两者是设备上的独立存储。
      想把它们放进相册：右键该文件 → <b>🖼️ 加入相册</b>，或直接到相册页点
      <b>⬆ 上传照片</b>（那会先传到「_相册导入」再自动收进相册）。
    </div>
${(PH.uploads && PH.uploads.length) ? `<div class="card" style="padding:12px 16px">
      <div style="display:flex;align-items:center;gap:10px;font-size:12.5px;margin-bottom:8px">
        <b>上传 ${PH.uploads.length} 个文件</b>
        <span style="flex:1"></span>
        <span style="color:var(--brand);font-weight:600">${uploadPct()}%</span>
      </div>
      <div class="bar"><i style="width:${uploadPct()}%"></i></div>
      <div class="note" style="margin-top:8px">
        ${PH.uploads.map((u) => `<div>${u.done >= u.total ? "✓" : "…"} ${esc(u.name)}
          <span style="color:var(--text2)">${fmtSize(u.done)}/${fmtSize(u.total)}</span></div>`).join("")}
      </div>
    </div>` : ""}
    <div id="fsBody"><div class="slot sm">载入中…</div></div>`;
}

async function loadFiles() {
  const panel = window.__hs_panel;
  const eid = window.__hs_entry_id || "";
  const box = panel && panel.shadowRoot.getElementById("fsBody");
  if (!eid || !box) return;
  box.innerHTML = `<div class="slot sm">载入中…</div>`;
  try {
    if (PH.space === "recycle") {
      // ⚠️ 必须显式传 space，否则后端默认 "public"，与恢复操作（user）错位。
      const q = new URLSearchParams({ space: RECY.space });
      if (SEL.account) q.set("account", SEL.account);
      const res = await apiGet(`/api/huawei_home_storage/recycle/${encodeURIComponent(eid)}?${q}`);
      releaseImagesIn(box);
      box.innerHTML = renderRecycle(res);
      if (panel) panel._wire(box);
      return;
    }
    const q = new URLSearchParams({ path: PH.path, space: PH.space });
    if (SEL.account) q.set("account", SEL.account);
    const res = await apiGet(`/api/huawei_home_storage/files/${encodeURIComponent(eid)}?${q}`);
    PH.data = res;
    releaseImagesIn(box);          // ← 先释放旧缩略图的 blob
    box.innerHTML = renderFileList(res);
    if (panel) panel._wire(box);
    queueImages(box);
  } catch (e) {
    box.innerHTML = `<div class="err">载入失败：${esc(String(e.message || e))}</div>`;
  }
}

function crumbsHtml(path) {
  const parts = String(path).split("/").filter(Boolean);
  let acc = "";
  const out = [`<a data-act="fs-go" data-path="/file/">根目录</a>`];
  for (const p of parts) {
    if (p === "file") continue;
    acc += "/" + p;
    out.push(`<span class="sep">›</span><a data-act="fs-go" data-path="${esc(acc)}/">${esc(p)}</a>`);
  }
  const parent = path.replace(/[^/]+\/$/, "") || "/file/";
  const up = path !== "/file/"
    ? `<span style="flex:1"></span>
       <button class="btn sm" data-act="fs-go" data-path="${esc(parent)}">⬆ 上一级</button>`
    : "";
  return `<div class="crumbs">${out.join("")}${up}</div>`;
}

function renderFileList(res) {
  const files = res.files || [];
  const dirs = files.filter((f) => f.type !== 8);
  const others = files.filter((f) => f.type === 8);
  const imgs = others.filter((f) => (f.mime || "").startsWith("image/"));
  const plain = others.filter((f) => !(f.mime || "").startsWith("image/"));
  const base = res.path || "/file/";

  return `
    ${crumbsHtml(base)}
    ${dirs.length ? `<div class="card">
      <div class="card-h">📁 文件夹<span class="hint">${dirs.length} 个</span></div>
      ${dirs.map((f) => {
        const pth = base + f.name + "/";
        const on = PICK.set.has(pth);
        return `<div class="filerow dir ${on ? "picked" : ""}" data-act="fs-go"
          data-path="${esc(pth)}">
        ${PICK.on ? `<span class="pickbox ${on ? "on" : ""}" data-act="pick" data-path="${esc(pth)}"></span>` : ""}
        <span class="fico">📁</span>
        <span class="fmain"><span class="fname">${esc(f.name)}</span></span>
        <button class="btn sm" data-act="row-menu" data-name="${esc(f.name)}"
          data-path="${esc(pth)}" data-dir="1">⋯</button>
        <span class="fsize">›</span></div>`;
      }).join("")}
    </div>` : ""}
    ${imgs.length ? `<div class="card">
      <div class="card-h">🖼️ 图片<span class="hint">${imgs.length} 张</span></div>
      <div class="phgrid">
        ${imgs.map((f) => {
          const pth = base + f.name;
          const on = PICK.set.has(pth);
          return `<div class="ph ${on ? "picked" : ""}" data-act="file-open"
            data-url="${esc(f.thumbUrl || "")}" data-name="${esc(f.name)}">
          ${PICK.on ? `<span class="pickbox ${on ? "on" : ""}" data-act="pick" data-path="${esc(pth)}"></span>` : ""}
          ${f.thumbUrl ? `<img data-src="${esc(f.thumbUrl)}" alt="" style="opacity:0">`
                       : `<div class="sk"></div>`}
          <span class="cap">${esc(f.name)}</span>
          <button class="btn sm phmenu" data-act="row-menu" data-name="${esc(f.name)}"
            data-path="${esc(pth)}" data-dir="0">⋯</button></div>`;
        }).join("")}
      </div>
    </div>` : ""}
    ${plain.length ? `<div class="card">
      <div class="card-h">📄 其他文件<span class="hint">${plain.length} 个 · ${fmtSize(
        plain.reduce((s, f) => s + (f.size || 0), 0))}</span></div>
      ${plain.map((f) => {
        const pth = base + f.name;
        const on = PICK.set.has(pth);
        return `<div class="filerow ${on ? "picked" : ""}">
        ${PICK.on ? `<span class="pickbox ${on ? "on" : ""}" data-act="pick" data-path="${esc(pth)}"></span>` : ""}
        <span class="fico">📄</span>
        <span class="fmain"><span class="fname">${esc(f.name)}</span>
          <span class="fsub">${esc(fmtDate(f.mtime))}</span></span>
        <span class="fsize">${fmtSize(f.size)}</span>
        <button class="btn sm" data-act="row-dl" data-path="${esc(pth)}"
          data-name="${esc(f.name)}">下载</button>
        <button class="btn sm" data-act="row-menu" data-name="${esc(f.name)}"
          data-path="${esc(pth)}" data-dir="0">⋯</button></div>`;
      }).join("")}
    </div>` : ""}
    ${!dirs.length && !others.length ? `<div class="slot">此目录为空</div>` : ""}`;
}

function renderRecycle(res) {
  const items = res.items || [];
  if (!items.length) return `<div class="slot">最近删除是空的</div>`;
  return `<div class="card">
    <div class="card-h">最近删除<span class="hint">${res.count} 项</span></div>
    ${pickToggleBar()}
    ${items.map((it) => {
      const on = PICK.set.has(String(it.rid));
      return `<div class="filerow ${on ? "picked" : ""}">
      ${PICK.on ? `<span class="pickbox ${on ? "on" : ""}" data-act="pick" data-path="${esc(String(it.rid))}"></span>` : ""}
      <span class="fico">[bin]</span>
      <span class="fmain"><span class="fname">${esc(it.name)}</span>
        <span class="fsub">${esc(fmtDate(it.dtime || it.mtime))}${it.path ? " · " + esc(it.path) : ""}</span></span>
      <span class="fsize">${esc(String(it.path || "").split("/").filter(Boolean).slice(-2, -1)[0] || "")}</span>
      <button class="btn sm" data-act="recover" data-rid="${esc(String(it.rid))}"
        data-name="${esc(it.name)}">恢复</button>
    </div>`;
    }).join("")}
    <div class="actions" style="margin-top:14px">
      <button class="btn pri" data-act="recover-picked" ${pickCount() ? "" : "disabled"}>
        恢复选中（${pickCount()}）
      </button>
      <span class="spacer" style="flex:1"></span>
      <button class="btn danger" data-act="recycle-purge" ${pickCount() ? "" : "disabled"}>
        永久删除选中（${pickCount()}）
      </button>
      <button class="btn danger" data-act="recycle-empty">清空回收站</button>
    </div>
    <div class="note">恢复后文件回到原来的位置。
      <b>永久删除 / 清空</b>会真正抹掉数据，<b>没有撤销</b>。
      这两个功能是逆向设备 App 插件实现的，<b>尚未在真机上验证</b>——
      若返回错误码，请改用设备 App 的回收站操作。</div>
  </div>`;
}

/** 恢复回收站条目（rid 是设备侧主键，比按名字匹配可靠）。 */
async function recoverItems(rids, label) {
  if (!rids.length) { toast("请先选择要恢复的条目"); return; }
  if (!window.confirm("恢复" + label + "？\n\n文件会回到原来的位置。")) return;
  let ok = 0, fail = 0;
  for (const rid of rids) {
    try {
      await svc("recover_recycle", { rid: rid, category: RECY.space });
      ok++;
    } catch (e) { fail++; }
  }
  toast(fail ? "恢复完成：成功 " + ok + "，失败 " + fail : "已恢复 " + ok + " 项");
  PICK.on = false; PICK.set.clear();
  loadFiles();
}

/**
 * 永久删除回收站里选中的条目（**不可逆**）。
 *
 * ⚠️ 与「清空回收站」的区别：这个只删选中的，`rids` 必填；
 * `empty_recycle` 是整站清空，只需要任意一个 rid 当"有货"的凭据。
 */
async function purgeRecycleItems(rids) {
  if (!rids.length) { toast("请先选择要永久删除的条目"); return; }
  const ok = window.confirm(
    `永久删除选中的 ${rids.length} 项？\n\n` +
    `⚠️ 不可逆：数据会被真正抹掉，无法恢复（连回收站里也不再有）。\n\n` +
    `该功能逆向自设备 App 插件，尚未在真机验证。`
  );
  if (!ok) return;
  try {
    const res = await svc("permanent_delete_recycle_items", {
      rids: rids.map((r) => Number(r)),
      // ⚠️ 后端要求 confirm: "PERMANENT_DELETE"（schema 层就会拒）
      confirm: "PERMANENT_DELETE",
      category: RECY.space,
    });
    if (res && res.ok === false) {
      toast("永久删除失败：" + (res.error || "设备拒绝"));
      return;
    }
    toast(`已永久删除 ${rids.length} 项`);
    PICK.on = false; PICK.set.clear();
    loadFiles();
  } catch (e) {
    toast("永久删除失败：" + String(e.message || e));
  }
}

/**
 * 清空整个回收站（**不可逆**）。
 *
 * ⚠️ 设备侧要求 ``action=clear`` 时也要带至少一个 rid（App UI 上是取列表
 * 第一条就 break），后端会自己解析，所以这里不用传 rid。
 */
async function emptyRecycle() {
  const ok = window.confirm(
    "清空整个回收站？\n\n" +
    "⚠️ 不可逆：回收站里**所有**条目都会永久消失，无法恢复。\n" +
    "只想删几项的话，请改用「永久删除选中」。\n\n" +
    "该功能逆向自设备 App 插件，尚未在真机验证。"
  );
  if (!ok) return;
  try {
    const res = await svc("empty_recycle", {
      // ⚠️ 后端要求 confirm: "EMPTY_RECYCLE"
      confirm: "EMPTY_RECYCLE",
      category: RECY.space,
    });
    if (res && res.ok === false) {
      toast("清空失败：" + (res.error || "设备拒绝"));
      return;
    }
    toast("回收站已清空");
    PICK.on = false; PICK.set.clear();
    loadFiles();
  } catch (e) {
    toast("清空失败：" + String(e.message || e));
  }
}


/* ===================== 文件操作 ===================== */

/** 调集成服务并取返回值（写操作都返回 {ok,...}）。
 *
 * ⚠️ 必须走 WebSocket 的 ``call_service`` + ``return_response: true``：
 * 本集成的写服务都声明为 ``SupportsResponse.ONLY``，用前端
 * ``hass.callService(..., true)`` 会报
 * "The action requires responses and must be called with return_response=True"
 * （实测 2026-10-08）。
 */
async function svc(service, data) {
  const h = hassOf();
  const conn = h && h.connection;
  if (!conn) throw new Error("未连接到 Home Assistant");
  const res = await conn.sendMessagePromise({
    type: "call_service",
    domain: "huawei_home_storage",
    service,
    service_data: Object.assign({ entry_id: window.__hs_entry_id || "" }, data || {}),
    return_response: true,
  });
  return (res && res.response) || res;
}

const curSpace = () => (PH.space === "public" ? "public" : "user");

/**
 * 给**相册类服务**附上 account 参数（没有选中账号时返回空对象）。
 *
 * ⚠️ 为什么相册服务需要而别的不用（2026-10-29）：
 * 服务层一直是"只操作主账号"的（``runtime.client`` 固定主账号），多账号只做
 * 在视图里。而「上传照片到相册」是**视图写 + 服务读**的组合：
 *
 *   1. 上传走视图 → 按 account 正确进了账号 B
 *   2. copy_to_album 走服务 → 主账号 → 找不到刚传进 B 的文件
 *
 * 所以这几个相册服务补了 ``account`` 字段（见后端 ``ACCOUNT_FIELD``）。
 * 其余服务（move_paths / delete_paths / rename_path 等）**仍然只支持主账号**，
 * 这是已知限制，不要以为这里加了就全都支持了。
 */
const accArg = () => (SEL.account ? { account: SEL.account } : {});

/** 通用输入弹窗（新建文件夹 / 重命名 / 移动到）。 */
function openPrompt({ title, label, value = "", hint = "", okText = "确定", onOk }) {
  const panel = window.__hs_panel;
  const host = (panel && panel.shadowRoot) || document.body;
  const m = document.createElement("div");
  m.className = "modal";
  m.innerHTML = `
    <div class="mbox">
      <h3>${esc(title)}</h3>
      ${hint ? `<p class="sub">${esc(hint)}</p>` : '<p class="sub"></p>'}
      <div id="mBody">
        <div class="field"><label>${esc(label)}</label>
          <input id="pmInput" type="text" value="${esc(value)}"></div>
        <div class="mactions">
          <button class="btn" data-close>取消</button>
          <button class="btn pri" id="pmOk">${esc(okText)}</button>
        </div>
      </div>
    </div>`;
  host.appendChild(m);
  const input = m.querySelector("#pmInput");
  const close = () => m.remove();
  const submit = async () => {
    const v = input.value.trim();
    if (!v) { mErr(m, "不能为空"); return; }
    mBusy(m, "处理中…");
    try { await onOk(v); close(); } catch (e) { mErr(m, String(e.message || e)); }
  };
  m.querySelector("#pmOk").addEventListener("click", submit);
  input.addEventListener("keydown", (e) => { if (e.key === "Enter") submit(); });
  m.addEventListener("click", (e) => { if (e.target === m || e.target.closest("[data-close]")) close(); });
  setTimeout(() => input.focus(), 30);
}

/** 某一行的操作菜单。 */
function openRowMenu({ name, path, isDir }) {
  const panel = window.__hs_panel;
  const host = (panel && panel.shadowRoot) || document.body;
  const m = document.createElement("div");
  m.className = "modal";
  m.innerHTML = `
    <div class="mbox">
      <h3>${esc(name)}</h3>
      <p class="sub">${isDir ? "文件夹" : "文件"} · ${esc(path)}</p>
      <div class="menu">
        <button class="btn" data-op="rename">✏️ 重命名</button>
        <button class="btn" data-op="toalbum">🖼️ 加入相册</button>
        <button class="btn" data-op="copy">📄 复制到…</button>
        <button class="btn" data-op="move">📦 移动到…</button>
        <button class="btn danger" data-op="delete">🗑️ 删除（进回收站）</button>
      </div>
      <div class="mactions" style="margin-top:14px">
        <button class="btn" data-close>关闭</button>
      </div>
    </div>`;
  host.appendChild(m);
  const close = () => m.remove();
  m.addEventListener("click", (e) => {
    if (e.target === m || e.target.closest("[data-close]")) close();
  });
  const dir = fileDirOf(path);
  m.querySelectorAll("[data-op]").forEach((b) => {
    b.addEventListener("click", async () => {
      const op = b.dataset.op;
      close();
      if (op === "rename") {
        openPrompt({
          title: "重命名", label: "新名称", value: name,
          hint: "只改名称，位置不变。",
          onOk: async (newName) => {
            const target = dir + newName + (isDir ? "/" : "");
            await svc("rename_path", { old_path: path, new_path: target, category: curSpace() });
            toast("已重命名"); loadFiles();
          },
        });
      } else if (op === "toalbum") {
        // ✅ 2026-10-29 恢复：``copy_to_album`` 补上 addTime 后真机可用
        // （此前它"假成功"，入口被撤掉过）。把文件空间里的图收进相册。
        openAlbumTargetPicker(path, name);
      } else if (op === "move" || op === "copy") {
        openDestPicker(async (dest, destSpace) => {
          try {
            await svc(op === "move" ? "move_paths" : "copy_paths", {
              paths: [path],
              dest_dir: dest,
              category: curSpace(),
              // 跨空间目标（见 pickRun 里的同样说明）
              dest_category: destSpace || curSpace(),
            });
            toast(op === "move" ? "已移动" : "已复制");
            loadFiles();
          } catch (e) {
            toast((op === "move" ? "移动" : "复制") + "失败：" + String(e.message || e));
          }
        }, op);
      } else if (op === "delete") {
        if (!window.confirm(`删除「${name}」？\n\n会移入回收站，可从「最近删除」恢复。`)) return;
        try {
          await svc("delete_paths", { paths: [path], category: curSpace() });
          toast("已移入回收站"); loadFiles();
        } catch (e) { toast("失败：" + String(e.message || e)); }
      }
    });
  });
}

/** 取路径所在目录（带尾斜杠）。 */
function fileDirOf(path) {
  const p = String(path);
  const cut = p.endsWith("/") ? p.slice(0, -1) : p;
  const i = cut.lastIndexOf("/");
  return i <= 0 ? "/file/" : cut.slice(0, i + 1);
}

/** 选择并上传（浏览器 → 设备，带进度）。 */
function pickAndUpload() {
  const panel = window.__hs_panel;
  const input = panel && panel.shadowRoot.getElementById("fsFile");
  if (!input) return;
  input.value = "";
  input.onchange = () => {
    const fs = input.files || [];
    // 支持多选：逐个排队上传（并发受限，不会打爆设备会话）
    for (const f of fs) doUpload(f);
  };
  input.multiple = true;
  input.click();
}

/* ---- 拖拽上传：把文件拖到文件页即可 ---- */
function initDnd(panel) {
  const main = panel && panel.shadowRoot.querySelector(".main");
  if (!main || main.dataset.dnd) return;
  main.dataset.dnd = "1";
  const stop = (e) => { e.preventDefault(); e.stopPropagation(); };
  ["dragenter", "dragover"].forEach((ev) => main.addEventListener(ev, (e) => {
    stop(e);
    if (PH.space === "recycle") return;
    main.classList.add("dropping");
  }));
  ["dragleave", "dragend"].forEach((ev) => main.addEventListener(ev, (e) => {
    stop(e);
    if (!main.contains(e.relatedTarget)) main.classList.remove("dropping");
  }));
  main.addEventListener("drop", (e) => {
    stop(e);
    main.classList.remove("dropping");
    if (PH.space === "recycle") { toast("回收站不能上传"); return; }
    const fs = (e.dataTransfer && e.dataTransfer.files) || [];
    if (!fs.length) return;
    toast("上传 " + fs.length + " 个文件…");
    for (const f of fs) doUpload(f);
  });
}

/**
 * 把浏览器里的文件传到设备（底层，不关心传到哪、传完做什么）。
 *
 * 抽出来是因为有两条需求走同一条路：
 *   1. 文件页「上传文件」——传完就结束
 *   2. 相册页「上传照片」——传完还要 ``copy_to_album`` 把它收进相册
 * 两者只在"之后做什么"上不同，传输细节（鉴权头、账号参数、进度事件、
 * 错误提取）完全一样，复制一份必然有一天只改了一处。
 *
 * @param {File} file
 * @param {string} destPath 设备上的完整目标路径（含文件名）
 * @param {string} space "user" | "public"
 * @param {(pct:number, loaded:number)=>void} [onProgress]
 * @returns {Promise<{path:string,size:number}>}
 */
async function uploadRaw(file, destPath, space, onProgress) {
  const eid = window.__hs_entry_id || "";
  const h = hassOf();
  // ⚠️ 必须带 account（2026-10-29 修）：上传是**写操作**，后端
  // ``_gate_account`` 在缺省时会取「当前用户可见的第一个账号」。
  // 多账号用户若正在看第二个账号的目录，文件就会被塞进第一个账号 ——
  // 用户以为传到了 A，实际落在 B，且两个账号的目录树看起来一样，
  // 很难发现。files / albums / recycle 三个读接口都带了 account，唯独漏了这里。
  const acc = SEL.account ? `&account=${encodeURIComponent(SEL.account)}` : "";
  const url = `/api/huawei_home_storage/upload/${encodeURIComponent(eid)}`
    + `?path=${encodeURIComponent(destPath)}&space=${encodeURIComponent(space)}${acc}`;

  // 用 XHR 才能拿到上传进度（fetch 没有 progress 事件）
  const token = (h.auth && h.auth.data && h.auth.data.access_token) || null;
  if (!token) throw new Error("无法获取访问令牌，请刷新页面");

  await new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", url, true);
    xhr.setRequestHeader("Authorization", "Bearer " + token);
    xhr.setRequestHeader("Content-Type", "application/octet-stream");
    if (onProgress) {
      xhr.upload.onprogress = (ev) => {
        if (!ev.lengthComputable) return;
        onProgress(Math.round((ev.loaded / ev.total) * 100), ev.loaded);
      };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve();
      else {
        let msg = "HTTP " + xhr.status;
        try { msg = JSON.parse(xhr.responseText).error || msg; } catch (e) { /* 保持 */ }
        reject(new Error(msg));
      }
    };
    xhr.onerror = () => reject(new Error("网络中断"));
    xhr.send(file);
  });
  return { path: destPath, size: file.size };
}

async function doUpload(file) {
  const panel = window.__hs_panel;
  const dest = PH.path + file.name;
  // 多文件：每个文件一条记录（数组），整体进度由 uploadPct() 汇总
  const rec = { name: file.name, done: 0, total: file.size, pct: 0 };
  PH.uploads = PH.uploads || [];
  PH.uploads.push(rec);
  PH.upload = rec;   // 兼容旧引用
  if (panel) panel._draw();

  const finish = (ok, msg) => {
    // 只移除本条；全部结束才清空数组（避免多文件互相清掉进度）
    PH.uploads = (PH.uploads || []).filter((x) => x !== rec);
    PH.upload = PH.uploads.length ? PH.uploads[PH.uploads.length - 1] : null;
    if (panel) panel._draw();
    toast(msg);
    if (ok && !PH.uploads.length) loadFiles();
  };

  try {
    await uploadRaw(file, dest, curSpace(), (pct, loaded) => {
      if (!PH.upload) return;
      PH.upload.done = loaded;
      PH.upload.pct = pct;
      const bar = panel && panel.shadowRoot.querySelector(".main .bar > i");
      const txt = panel && panel.shadowRoot.querySelector(".main .card .bar")
        ? panel.shadowRoot.querySelectorAll(".main .card span")
        : null;
      if (bar) bar.style.width = PH.upload.pct + "%";
      if (txt && txt.length) {
        const el = [...txt].find((x) => /\d+%/.test(x.textContent));
        if (el) el.textContent = PH.upload.pct + "%";
      }
    });
    finish(true, "上传完成：" + file.name);
  } catch (e) {
    finish(false, "上传失败：" + String(e.message || e));
  }
}

/* ---------- 配置（只读总览 + 跳 HA 原生配置）---------- */
function renderConfig(d) {
  const e = d || {};
  const bdir = e.backup_dir || "/file/HomeAssistant/";
  const bspace = e.backup_space || "user";
  return `
    <div class="vhead"><h2>配置</h2>
      <span class="sub">当前生效的设置</span></div>

    <div class="card">
      <div class="card-h">💾 备份目标<span class="hint">由 backup.py 读取</span></div>
      <div class="row"><span class="k">备份目录</span><span class="v">${esc(bdir)}</span></div>
      <div class="row"><span class="k">所在空间</span><span class="v">${bspace === "public" ? "共享" : "我的文件"}</span></div>
      <div class="note">
        备份会存到这里，每个备份由 <code>.tar</code> 本体与
        <code>.ha-backup.json</code> 边车元数据组成。删除走设备回收站（可逆）。
      </div>
      <div class="actions" style="margin-top:14px">
        <button class="btn" data-act="open-ha-config">在 HA 中修改</button>
      </div>
    </div>

    <div class="card">
      <div class="card-h">🔐 账号<span class="hint">${(d.accounts || []).length} 个</span></div>
      ${(d.accounts || []).map((a) => `<div class="row">
        <span class="k">${esc(a.label || "账号")}${a.is_primary ? "（主）" : ""}</span>
        <span class="v">${a.counts && a.counts.photos != null ? a.counts.photos + " 张照片" : ""}</span>
      </div>`).join("") || '<div class="slot sm">无账号信息</div>'}
      <div class="actions" style="margin-top:14px">
        <button class="btn" data-act="open-ha-config">管理账号 / 重新登录</button>
      </div>
    </div>

    <div class="card">
      <div class="card-h">🧭 面板设置</div>
      <div class="row"><span class="k">界面皮肤</span><span class="v">${esc(
        (SKINS.find((x) => x.key === CUR_SKIN) || {}).title || CUR_SKIN
      )}</span></div>
      <div class="note">皮肤用右上角切换器改，会记住选择。</div>
    </div>`;
}

/**
 * 重试失败任务（``POST /{business}/retryTask``）。
 *
 * ⚠️ 需要 ``taskId`` + ``taskType`` 两个都传（设备按 taskType 分派）。任务列表里
 * ``taskType`` 可能缺失，缺了就传 0 让设备自己判；失败会如实提示。
 */
async function retryTask(taskId, taskType) {
  if (!taskId) return;
  try {
    const res = await svc("retry_task", {
      task_id: Number(taskId),
      task_type: Number(taskType) || 0,
      business: TASK.src || "filesvc",
    });
    if (res && res.ok === false) {
      toast("重试失败：" + (res.error || "设备拒绝"));
      return;
    }
    toast("已提交重试");
    setTimeout(() => loadTasks(), 1500);
  } catch (e) {
    toast("重试失败：" + String(e.message || e));
  }
}

/* ---------- 任务（文件 / 跨服务 / 相册）---------- */const TASK_SOURCES = [
  { key: "filesvc", title: "文件空间" },
  { key: "trans",   title: "跨服务传输" },
  { key: "gallery", title: "相册" },
];

function renderTasks() {
  return `
    <div class="vhead"><h2>任务</h2>
      <span class="sub">${TASK.data ? "共 " + (TASK.data.tasks || []).length + " 条" : ""}</span>
      <span class="spacer" style="flex:1"></span>
      <button class="btn sm" data-act="task-reload">刷新</button>
    </div>
    <div class="segs" style="margin-bottom:16px">
      ${TASK_SOURCES.map((x) => `<span class="seg ${x.key === TASK.src ? "on" : ""}"
        data-act="task-src" data-src="${x.key}">${esc(x.title)}
        ${TASK.counts[x.key] != null ? `<span class="n">${TASK.counts[x.key]}</span>` : ""}
      </span>`).join("")}
    </div>
    ${renderTaskBody()}`;
}

function renderTaskBody() {
  if (TASK.err) return `<div class="err">${esc(TASK.err)}</div>`;
  if (!TASK.data) return `<div class="slot sm">载入中…</div>`;
  const list = TASK.data.tasks || [];
  if (!list.length) return `<div class="slot">该来源当前没有任务</div>`;
  const title = (TASK_SOURCES.find((x) => x.key === TASK.src) || {}).title || "任务";
  return `<div class="card">
    <div class="card-h">${esc(title)}<span class="hint">${list.length} 条</span></div>
    ${list.map((t) => {
      const pct = taskPct(t);
      const failed = taskFailed(t);
      return `<div class="filerow" style="align-items:flex-start">
        <span class="fico">${failed ? "!" : pct >= 100 ? "OK" : "..."}</span>
        <span class="fmain">
          <span class="fname">${esc(t.originObjectName || t.transId || "任务")}</span>
          <span class="fsub">${esc(fmtDate(t.taskBeginTime))}${t.destination ? " -> " + esc(t.destination) : ""}</span>
          <div class="bar ${failed ? "danger" : ""}"><i style="width:${pct}%"></i></div>
        </span>
        <span class="fsize">${pct}%</span>
        ${failed ? `<button class="btn sm pri" data-act="task-retry"
          data-id="${esc(t.taskId)}" data-type="${esc(t.taskType != null ? t.taskType : 0)}">重试</button>` : ""}
        <button class="btn sm" data-act="task-clean" data-id="${esc(t.taskId)}">清除</button>
      </div>`;
    }).join("")}
    <div class="actions" style="margin-top:14px">
      <button class="btn danger" data-act="task-clean-all">清除本来源全部记录</button>
    </div>
  </div>`;
}

function taskPct(t) {
  const raw = Number(t.progress);
  if (t.progress !== "" && t.progress != null && !isNaN(raw)) {
    return Math.max(0, Math.min(100, Math.round(raw)));
  }
  const sum = Number(t.sumNum || t.sumSize || 0);
  const fin = Number(t.finishedNum || t.finishedSize || 0);
  if (!sum) return 0;
  return Math.max(0, Math.min(100, Math.round((fin / sum) * 100)));
}

function taskFailed(t) {
  const info = String(t.errorInfo || "");
  return info.includes("'err'") && !info.includes("'err': 0");
}

async function loadTasks() {
  const panel = window.__hs_panel;
  TASK.err = "";
  if (!TASK.data && panel) panel._draw();
  try {
    const res = await svc("task_status", { service: TASK.src });
    TASK.data = res || { tasks: [] };
    TASK.counts[TASK.src] = (TASK.data.tasks || []).length;
  } catch (e) {
    TASK.err = String(e.message || e);
  }
  if (panel && panel._view === "tasks") panel._draw();
}

async function cleanTasks(ids, label) {
  if (!ids.length) return;
  if (!window.confirm("清除" + label + "？\n\n这只删除设备的任务历史记录，不影响已传输的文件。")) return;
  try {
    const res = await svc("clean_task_records", { task_ids: ids });
    const failed = (res && res.failed_ids) || [];
    toast(failed.length ? "清除完成，" + failed.length + " 条失败" : "已清除 " + ids.length + " 条记录");
    TASK.data = null;
    await loadTasks();
  } catch (e) {
    toast("清除失败：" + String(e.message || e));
  }
}

/* ---------- 目录选择器（替代手输路径）---------- */
const DEST = { open: false, dirs: [], busy: false, err: "", cur: "/file/", cb: null,
               op: "move",
               /**
                * 目标空间：``user``（我的文件）| ``public``（共享）。
                *
                * ⚠️ 2026-10-29 之前选择器只能在本空间内浏览，于是
                * 「把文件放进共享」这个需求在 UI 上根本做不到 —— 虽然后端
                * ``move_paths`` / ``copy_paths`` 一直支持 ``dest_category``
                * （yaml 里也有声明），但面板从来不传它。用户只能干看着。
                */
               space: "user" };

async function openDestPicker(cb, op) {
  const panel = window.__hs_panel;
  DEST.open = true; DEST.cb = cb; DEST.err = "";
  DEST.op = op || "move";           // 仅用于提示"会跨空间复制/移动"
  DEST.space = curSpace();          // 默认从当前所在空间开始浏览
  DEST.cur = PH.path || "/file/";
  await loadDestDirs(DEST.cur);
  if (panel) panel._draw();
}

async function loadDestDirs(path) {
  const panel = window.__hs_panel;
  DEST.busy = true; DEST.err = "";
  if (panel) panel._draw();
  try {
    const eid = window.__hs_entry_id || "";
    // ⚠️ 用 DEST.space 而不是 curSpace()：允许浏览到**另一个**空间
    const q = `path=${encodeURIComponent(path)}&space=${encodeURIComponent(DEST.space)}`;
    const acc = SEL.account ? `&account=${encodeURIComponent(SEL.account)}` : "";
    const res = await apiGet(`/api/huawei_home_storage/files/${encodeURIComponent(eid)}?${q}${acc}`);
    DEST.dirs = (res.files || []).filter((f) => f.type !== 8).map((f) => ({
      name: f.name, path: path + f.name + "/",
    }));
    DEST.cur = path;
  } catch (e) { DEST.err = String(e.message || e); DEST.dirs = []; }
  DEST.busy = false;
  if (panel) panel._draw();
}

function renderDestPicker() {
  if (!DEST.open) return "";
  const parent = DEST.cur.replace(/[^/]+\/$/, "") || "/file/";
  const cross = DEST.space !== curSpace();
  return `<div class="modal">
    <div class="mbox">
      <h3>选择目标文件夹</h3>
      <div class="segs" style="margin:10px 0">
        <span class="seg ${DEST.space === "user" ? "on" : ""}"
          data-act="dest-space" data-space="user">我的文件</span>
        <span class="seg ${DEST.space === "public" ? "on" : ""}"
          data-act="dest-space" data-space="public">共享</span>
      </div>
      <p class="sub">当前：${esc(DEST.cur)}（点文件夹进入，点「选这里」确认）</p>
      ${cross ? `<div class="note" style="color:var(--warn)">
        目标在「${DEST.space === "public" ? "共享" : "我的文件"}」，与源不在同一空间 ——
        会跨空间${DEST.op === "copy" ? "复制" : "移动"}。</div>` : ""}
      ${DEST.err ? `<div class="err">${esc(DEST.err)}</div>` : ""}
      ${DEST.busy ? '<div class="slot sm">载入中…</div>' : `
        ${DEST.cur !== "/file/" ? `<div class="filerow dir" data-act="dest-go" data-path="${esc(parent)}">
          <span class="fico">[..]</span>
          <span class="fmain"><span class="fname">上一级</span></span></div>` : ""}
        ${DEST.dirs.length ? DEST.dirs.map((d) => `<div class="filerow dir" data-act="dest-go" data-path="${esc(d.path)}">
          <span class="fico">[D]</span>
          <span class="fmain"><span class="fname">${esc(d.name)}</span></span></div>`).join("")
          : '<div class="slot sm">该目录下没有子文件夹</div>'}
      `}
      <div class="mactions">
        <button class="btn" data-act="dest-cancel">取消</button>
        <button class="btn pri" data-act="dest-ok">选这里</button>
      </div>
    </div>
  </div>`;
}


/* ---------- 加入相册 / 共享给家人（相册域 fileId）---------- */
let MORE_OPEN = false;   /* 移动端「更多」抽屉是否展开 */
const ALBOP = { open: false, mode: "", files: [], albums: [], busy: false, err: "" };

/** 当前选中的照片（相册域 fileId）。 */
function pickedPhotoIds() {
  const out = [];
  for (const key of PICK.set) {
    if (!key.startsWith("photo:")) continue;
    const idx = Number(key.slice(6));
    const p = (ALB.photos || [])[idx];
    if (p && (p.fileId || p.id)) out.push(p.fileId || p.id);
  }
  return out;
}

/**
 * 把选中的照片**移出当前相册**（``/gallery/delAlbumMemb``）。
 *
 * 语义：解除照片与相册的关联，**不删原图** —— 照片仍在「照片」总相册和
 * 文件空间里。所以这里只做一次 confirm，不要套 delete_media 那套数据丢失警告。
 */
async function removePickedFromAlbum() {
  const a = ALB.album;
  const ids = pickedPhotoIds();
  if (!a || !ids.length) { toast("请先选择照片"); return; }
  const yes = window.confirm(
    `把选中的 ${ids.length} 张从相册「${a.name}」移出？\n\n` +
    "照片本身不会被删除，只是不再属于这个相册。"
  );
  if (!yes) return;
  try {
    const res = await svc("remove_album_members", {
      album_id: Number(a.id),
      album_type: Number(a.type) || 6,
      album_name: a.name,
      file_ids: ids,
      ...accArg(),
    });
    if (res && res.ok === false) {
      toast("移出失败：" + (res.error || "设备拒绝"));
      return;
    }
    toast(`已移出 ${ids.length} 张`);
    PICK.set.clear(); PICK.on = false;
    loadAlbumPage(false);
  } catch (e) {
    toast("移出失败：" + String(e.message || e));
  }
}

/**
 * 把选中的那一张设为相册封面（``POST /gallery/albumCfg`` + ``coverId``）。
 *
 * ⚠️ 报文里**不能带 albumName** —— 改名和设封面是同一端点的两套 body，
 * 混着传会被设备拒（30111）。2026-10-30 抓包 + 真机确认。
 */
async function setPickedAsCover() {
  const a = ALB.album;
  const ids = pickedPhotoIds();
  if (!a || ids.length !== 1) { toast("请只选一张照片"); return; }
  try {
    const res = await svc("album_set_cover", {
      album_id: Number(a.id),
      album_type: Number(a.type) || 6,
      cover_id: ids[0],
      ...accArg(),
    });
    if (res && res.ok === false) {
      toast("设封面失败：" + (res.error || "设备拒绝"));
      return;
    }
    toast("已设为相册封面");
    ALB.data = null;          // 封面变了，相册列表缓存作废
  } catch (e) {
    toast("设封面失败：" + String(e.message || e));
  }
}

async function openAlbumOp(mode) {
  const panel = window.__hs_panel;
  const ids = pickedPhotoIds();
  if (!ids.length) { toast("请先选择照片"); return; }
  // 目标相册：用户自建相册(type=6)才是能"加入"的
  const groups = (ALB.data && ALB.data.groups) || [];
  const userGroup = groups.find((g) => g.key === "user");
  ALBOP.open = true; ALBOP.mode = mode; ALBOP.files = ids;
  ALBOP.albums = (userGroup && userGroup.albums) || [];
  ALBOP.err = "";
  if (panel) panel._draw();
}

function renderAlbumOp() {
  if (!ALBOP.open) return "";
  const isAdd = ALBOP.mode === "add";
  return `<div class="modal"><div class="mbox">
    <h3>${isAdd ? "加入相册" : "共享给家人"}</h3>
    <p class="sub">已选 ${ALBOP.files.length} 张 · 选择目标相册</p>
    ${ALBOP.err ? `<div class="err">${esc(ALBOP.err)}</div>` : ""}
    ${!ALBOP.albums.length
      ? `<div class="slot sm">还没有可加入的相册。<br>
          只有「共享相册」（设备上 albumType=6 的自建相册）能收照片，<br>
          智能分类/人物/地点这些是设备自动生成的，塞不进去。<br><br>
          先回相册页点「＋ 新建相册」建一个，再回来加。</div>`
      : `<div>${ALBOP.albums.map((x) => `<div class="filerow dir" data-act="albop-ok"
          data-id="${x.id}" data-name="${esc(x.name)}">
          <span class="fico">[]</span>
          <span class="fmain"><span class="fname">${esc(x.name)}</span>
            <span class="fsub">${x.count} 张 · 归属 ${esc(String(x.ownerId || (x.userIds || [])[0] || "-"))}</span></span></div>`).join("")}</div>`}
    <div class="mactions"><button class="btn" data-act="albop-cancel">取消</button></div>
  </div></div>`;
}

/** 执行加入/共享。fileId 必须是**相册域**的，不是文件空间 fid。 */
async function runAlbumOp(albumId, albumName) {
  const panel = window.__hs_panel;
  const ids = ALBOP.files;
  const isAdd = ALBOP.mode === "add";
  if (!ids.length || !albumId) return;
  try {
    // ⚠️ 目标相册的 type 从数据里取，不要硬编码：
    // ``ALBOP.albums`` 来自「共享相册」分组（type=6），但硬编码会让将来
    // 支持别的分组时悄悄错位（``albumShareToPerson`` 就曾硬编码 23）
    const target = (ALBOP.albums || []).find((x) => String(x.id) === String(albumId));
    const albumType = Number((target && target.type) || 6);
    if (isAdd) {
      await albumAddTo(albumId, albumType, ids, albumName);
    } else {
      // 共享需要 ownerId（设备家庭成员 id）。
      // ⚠️ 不能从 device_users 取 —— 后端为隐私把它脱敏成空 dict。
      // 相册数据自带 ownerId（实测 10001/10002），用目标相册的归属人。
      const ownerId = target && (target.ownerId || (target.userIds || [])[0]);
      if (!ownerId) {
        ALBOP.err = "该相册没有归属人信息，无法共享";
        if (panel) panel._draw();
        return;
      }
      await albumShareToPerson(albumId, ownerId, ids, albumName, albumType);
    }
    ALBOP.open = false;
    PICK.set.clear(); PICK.on = false;
    if (panel) { panel._draw(); loadAlbumPage(false); }
  } catch (e) {
    ALBOP.err = String(e.message || e);
    if (panel) panel._draw();
  }
}

/* ---------- 文件下载 ---------- */
async function downloadFile(path, name) {
  // ⚠️ <a download> 直链不带 HA 鉴权头，设备会拒绝。
  // 先 fetchWithAuth 拿到 blob，再转临时 URL 触发下载。
  try {
    const h = hassOf();
    const eid = window.__hs_entry_id || "";
    // 多账号下必须走 /acct/ 子路由（2026-10-29 修）：不同账号的隧道端口不同，
    // 走单账号路由只会拿主账号的会话，下载第二个账号的文件必然失败。
    // 格式见 views.build_image_url：<entry>/acct/<account>/<name>/<path>
    const accSeg = SEL.account ? `acct/${encodeURIComponent(SEL.account)}/` : "";
    const url = `/api/huawei_home_storage/image/${encodeURIComponent(eid)}/${accSeg}raw${path}`;
    toast("准备下载…");
    const r = await h.fetchWithAuth(url);
    if (!r.ok) throw new Error("HTTP " + r.status);
    const blob = await r.blob();
    const u = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = u;
    a.download = name || "download";
    (document.body || document.documentElement).appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(u), 30000);
    toast("已开始下载 " + (name || ""));
  } catch (err) {
    toast("下载失败：" + String(err.message || err));
  }
}

/* ---------- 搜索（文件空间）---------- */
function renderSearch() {
  return `
    <div class="vhead"><h2>搜索</h2>
      <span class="sub">按关键字查找文件空间</span></div>
    <div class="searchbar">
      <input id="kwInput" type="text" placeholder="输入关键字后按回车"
        value="${esc(SRC.kw)}" autocomplete="off">
      <button class="btn pri" data-act="search-go">搜索</button>
      ${SRC.kw ? `<button class="btn sm" data-act="search-clear">清空</button>` : ""}
    </div>
    ${renderSearchBody()}`;
}

function renderSearchBody() {
  if (SRC.err) return `<div class="err">${esc(SRC.err)}</div>`;
  if (SRC.busy) return `<div class="slot sm">搜索中…</div>`;
  if (!SRC.res) return `<div class="slot">输入关键字开始搜索</div>`;
  const list = SRC.res.files || SRC.res.items || [];
  if (!list.length) return `<div class="slot">没有匹配「${esc(SRC.kw)}」的文件</div>`;
  const base = "/file/";
  return `<div class="card">
    <div class="card-h">结果<span class="hint">${list.length} 项</span></div>
    ${list.map((f) => `<div class="filerow">
      <span class="fico">${f.type === 8 ? "#" : "D"}</span>
      <span class="fmain">
        <span class="fname">${esc(f.name || f.fileName || "")}</span>
        <span class="fsub">${esc(f.path || f.dirPath || "")}</span>
      </span>
      <span class="fsize">${f.size ? fmtSize(f.size) : ""}</span>
    </div>`).join("")}
  </div>`;
}

async function doSearch() {
  const panel = window.__hs_panel;
  const box = panel && panel.shadowRoot.getElementById("kwInput");
  if (!box) return;
  SRC.kw = box.value.trim();
  if (!SRC.kw) { toast("请输入关键字"); return; }
  SRC.busy = true; SRC.err = ""; SRC.res = null;
  if (panel) panel._draw();
  try {
    SRC.res = await svc("search_files", { keyword: SRC.kw, limit: 100 });
  } catch (e) {
    SRC.err = String(e.message || e);
  }
  SRC.busy = false;
  if (panel && panel._view === "search") panel._draw();
}

/* ---------- 设备 ----------
 * ⚠️ 字段名必须与后端 views.py 的 _hardware/_network/_samba/_auto_upgrade 一致，
 *    写错会静默少显示整行（曾因此只显示 2 行硬件信息）。 */
function renderDevice(d) {
  const hw = d.hardware || {};
  const net = d.network || {};
  const dk = d.disk || {};
  const samba = d.samba || {};
  const au = d.auto_upgrade || {};
  const pct = dk.usage != null ? dk.usage : (dk.total ? Math.round(dk.used / dk.total * 100) : 0);
  const yesno = (v) => (v ? "已开启" : "未开启");
  const rows = (pairs) => {
    const html = pairs.filter(([, v]) => v != null && v !== "")
      .map(([k, v]) => `<div class="row"><span class="k">${esc(k)}</span>
        <span class="v">${esc(String(v))}</span></div>`).join("");
    return html || '<div class="slot sm">暂无数据</div>';
  };

  return `
    <h2 class="view-title">设备</h2>
    <div class="card">
      <div class="card-h">🖥️ 硬件<span class="hint">${esc(d.device_model || "")}</span></div>
      ${rows([
        ["型号", d.device_model],
        ["序列号", d.device_sn ? maskSn(d.device_sn) : ""],
        ["固件", hw.firmware],
        ["CPU", hw.cpu_model],
        ["核心数", hw.cpu_cores],
        ["CPU 占用", hw.cpu_usage != null ? hw.cpu_usage + " %" : ""],
        ["温度", hw.cpu_temperature != null ? hw.cpu_temperature + " °C" : ""],
        ["内存", hw.memory_total
          ? `${fmtSize(hw.memory_used)} / ${fmtSize(hw.memory_total)}` : ""],
        ["升级状态", hw.upgrade_state],
      ])}
    </div>

    <div class="card">
      <div class="card-h">💾 存储<span class="hint">${dk.slots ? dk.slots + " 个盘位" : ""}</span></div>
      <div style="font-family:var(--font-display);font-size:26px;font-weight:700">
        ${pct}%<span style="font-size:13px;font-weight:500;color:var(--text2);margin-left:8px">
        已使用</span></div>
      <div class="bar ${pct >= 90 ? "danger" : pct >= 75 ? "warn" : ""}"><i style="width:${pct}%"></i></div>
      ${rows([
        ["总容量", fmtSize(dk.total)],
        ["已使用", fmtSize(dk.used)],
        ["可用", fmtSize(dk.free)],
      ])}
    </div>

    <div class="card">
      <div class="card-h">🌐 网络与共享</div>
      ${rows([
        ["局域网地址", d.host],
        ["IPv4", net.ipv4],
        ["IPv6", net.ipv6],
        ["SMB 匿名共享", samba.public != null ? yesno(samba.public) : ""],
        ["SMB 账号共享", samba.user != null ? yesno(samba.user) : ""],
        ["自动升级", au.enabled != null
          ? yesno(au.enabled) + (au.window ? "（" + au.window + "）" : "") : ""],
      ])}
    </div>

    ${renderDiag()}
    <div class="card">
      <div class="card-h">设备操作</div>
      <div class="actions">
        <button class="btn" data-act="btn" data-which="sleep">😴 硬盘休眠</button>
        <button class="btn" data-act="diag">读取诊断</button>
        <button class="btn" data-act="btn" data-which="eject">⏏️ 弹出 USB</button>
        <button class="btn danger" data-act="btn" data-which="reboot">🔄 重启设备</button>
      </div>
      <div class="note">重启会中断所有连接，媒体与文件访问将短暂不可用。</div>
    </div>`;
}

/* ---------- 用户 ---------- */
function renderUsers(d) {
  const accs = d.accounts || [];
  const cur = d.current_account;
  let members = "";
  for (let i = 0; i < (d.device_users || []).length; i++) {
    const admin = i === 0;
    members += `<div class="ucard ${admin ? "admin" : ""}">
      <span class="uav">${admin ? "管" : String(i + 1)}</span>
      <div><div class="un">${admin ? "管理员" : "成员 " + (i + 1)}</div>
        <div class="ur">${admin ? "设备管理权限" : "普通成员"}</div></div>
      <span class="utag">${admin ? "管理员" : "成员"}</span></div>`;
  }
  return `
    <h2 class="view-title">用户</h2>
    <div class="card">
      <div class="card-h">👥 设备成员<span class="hint">共 ${(d.device_users || []).length} 位</span></div>
      ${members ? `<div class="users">${members}</div>` : '<div class="slot sm">暂无成员数据</div>'}
      <div class="note">出于隐私，面板不显示成员的真实姓名与 ID。</div>
    </div>
    <div class="card">
      <div class="card-h">🔐 登录账号<span class="hint">共 ${accs.length} 个</span></div>
      ${accs.map((a) => {
        const c = a.counts || {};
        const on = cur && (a.key === cur.key || a.account === cur.account);
        return `<div class="row">
          <span class="k">${esc(a.label || "账号")}
            ${a.is_primary ? '<span class="utag" style="margin-left:6px">主</span>' : ""}</span>
          <span class="v">${on ? "当前查看" : ""}${c.photos != null ? " · 照片 " + c.photos : ""}</span>
        </div>`;
      }).join("") || '<div class="slot sm">暂无账号</div>'}
      <div class="actions" style="margin-top:14px">
        <button class="btn pri" data-act="add-account">＋ 添加华为账号</button>
      </div>
      <div class="note">多账号各自独立隧道与相册视角 —— 顶部可切换。</div>
    </div>`;
}

/* ===================== 大图查看器 ===================== */
function openViewer(list, index) {
  const panel = window.__hs_panel;
  const host = (panel && panel.shadowRoot) || document.body;
  let i = index;

  const v = document.createElement("div");
  v.className = "viewer";
  v.tabIndex = 0;
  v.innerHTML = `
    <div class="vbar">
      <button class="btn" data-close>✕ 关闭</button>
      <span style="flex:1"></span>
      <span class="vtitle" style="color:#fff;font-weight:600"></span>
      <span style="flex:1"></span>
      <a class="btn" data-dl>⬇️ 原图</a>
    </div>
    ${list.length > 1 ? '<button class="nav prev" data-prev>‹</button>' : ""}
    <img alt="">
    ${list.length > 1 ? '<button class="nav next" data-next>›</button>' : ""}
    <div class="vmeta"></div>`;
  host.appendChild(v);

  const img = v.querySelector("img");
  const title = v.querySelector(".vtitle");
  const meta = v.querySelector(".vmeta");
  const dl = v.querySelector("[data-dl]");
  let objectUrl = null;

  async function show() {
    const p = list[i] || {};
    title.textContent = list.length > 1 ? `${i + 1} / ${list.length}` : "";
    meta.textContent = [fmtDate(p.mtime), p.size ? fmtSize(p.size) : ""].filter(Boolean).join(" · ");
    // 用 photo_info 补齐元数据（含 hdcFilePath 原图路径）—— 失败就保持基础信息
    if ((p.fileId || p.id) && !p._metaDone) {
      p._metaDone = true;
      svc("photo_info", { file_ids: [p.fileId || p.id] }).then((info) => {
        const one = (info && (info.photos || info.items || [])[0]) || info || {};
        const extra = [one.hdcFilePath ? "原图" : "", one.width && one.height ? one.width + "x" + one.height : "",
                       one.mime || ""].filter(Boolean).join(" · ");
        if (extra) meta.textContent = [meta.textContent, extra].filter(Boolean).join(" · ");
      }).catch(() => { /* 元数据取不到就只显示基础信息 */ });
    }
    if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
    img.removeAttribute("src");
    img.alt = "载入中…";
    const url = p.viewUrl || p.thumbUrl || "";
    dl.setAttribute("href", p.downloadUrl || url || "#");
    dl.setAttribute("download", p.downloadName || p.name || "photo");
    if (!url) { img.alt = "此照片没有可浏览的地址"; return; }
    try {
      const h = hassOf();
      const r = await h.fetchWithAuth(url);
      if (!r.ok) throw new Error("HTTP " + r.status);
      objectUrl = URL.createObjectURL(await r.blob());
      img.src = objectUrl;
      img.alt = "";
    } catch (e) {
      img.alt = "载入失败：" + String(e.message || e);
    }
  }

  v.addEventListener("click", (e) => {
    if (e.target === v || e.target.closest("[data-close]")) {
      // ⚠️ 关闭时必须释放当前这张的 blob（切图只释放上一张，最后一张会漏）
      releaseImageBlob(img);
      if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; }
      v.remove(); return;
    }
    if (e.target.closest("[data-prev]")) { i = (i - 1 + list.length) % list.length; show(); return; }
    if (e.target.closest("[data-next]")) { i = (i + 1) % list.length; show(); return; }
  });
  v.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { releaseImageBlob(img); if (objectUrl) { URL.revokeObjectURL(objectUrl); objectUrl = null; } v.remove(); }
    else if (e.key === "ArrowLeft") { i = (i - 1 + list.length) % list.length; show(); }
    else if (e.key === "ArrowRight") { i = (i + 1) % list.length; show(); }
  });
  v.focus();
  show();
}

/* ===================== 登录（面板内添加账号） ===================== */
function wsCmd(cmd, payload) {
  return new Promise((resolve, reject) => {
    const h = hassOf();
    const conn = h && h.connection;
    if (!conn) { reject(new Error("未连接到 Home Assistant")); return; }
    conn.sendMessagePromise({ type: cmd, ...payload }).then(resolve).catch(reject);
  });
}

function openLogin() {
  const panel = window.__hs_panel;
  const host = (panel && panel.shadowRoot) || document.body;
  const m = document.createElement("div");
  m.className = "modal";
  m.innerHTML = `
    <div class="mbox">
      <h3>添加华为账号</h3>
      <p class="sub">登录后可在此设备查看该账号的相册与文件。密码仅用于本次登录。</p>
      <div class="steps"><i class="on"></i><i></i><i></i></div>
      <div id="mBody">
        <div class="field"><label>华为账号</label>
          <input id="lgAcct" type="text" placeholder="手机号 / 邮箱" autocomplete="username"></div>
        <div class="field"><label>密码</label>
          <input id="lgPwd" type="password" placeholder="登录密码" autocomplete="current-password"></div>
        <div class="mactions">
          <button class="btn" data-close>取消</button>
          <button class="btn pri" id="lgNext">下一步</button>
        </div>
      </div>
    </div>`;
  host.appendChild(m);
  const close = () => m.remove();
  m.addEventListener("click", (e) => {
    if (e.target === m || e.target.closest("[data-close]")) close();
  });

  m.querySelector("#lgNext").addEventListener("click", async () => {
    const acct = m.querySelector("#lgAcct").value.trim();
    const pwd = m.querySelector("#lgPwd").value;
    if (!acct || !pwd) { mErr(m, "请填写账号与密码"); return; }
    mBusy(m, "正在登录…");
    try {
      const r = await wsCmd("huawei_home_storage/login_start", {
        entry_id: window.__hs_entry_id || "", account: acct, password: pwd,
      });
      if (r.done) { close(); toast("账号已添加"); if (panel) panel._load(); return; }
      stepChannels(m, r, r.flow_id, close);
    } catch (err) { mErr(m, String(err.message || err)); }
  });
}

function stepChannels(m, r, flowId, close) {
  const chans = r.channels || [];
  m.querySelector(".steps").innerHTML = '<i class="on"></i><i class="on"></i><i></i>';
  m.querySelector("#mBody").innerHTML = `
    ${r.prompt ? `<div class="mnote">${esc(r.prompt)}</div>` : ""}
    ${chans.length ? `<div class="field"><label>接收方式</label>
      <select id="lgCh">${chans.map((c, i) =>
        `<option value="${esc(c.key)}">${esc(c.label || "方式 " + (i + 1))}</option>`).join("")}
      </select></div>` : ""}
    <div class="mactions">
      <button class="btn" data-close>取消</button>
      <button class="btn pri" id="lgSend">获取验证码</button>
    </div>`;
  m.querySelector("#lgSend").addEventListener("click", async () => {
    const sel = m.querySelector("#lgCh");
    mBusy(m, "正在发送…");
    try {
      const r2 = await wsCmd("huawei_home_storage/login_channel", {
        flow_id: flowId, channel: sel ? sel.value : null,
      });
      stepCode(m, r2, flowId, close);
    } catch (err) { mErr(m, String(err.message || err)); }
  });
}

function stepCode(m, r, flowId, close) {
  m.querySelector(".steps").innerHTML = '<i class="on"></i><i class="on"></i><i class="on"></i>';
  m.querySelector("#mBody").innerHTML = `
    ${r.prompt ? `<div class="mnote">${esc(r.prompt)}</div>` : ""}
    <div class="field"><label>验证码</label>
      <input id="lgCode" type="text" placeholder="请输入验证码" autocomplete="one-time-code"></div>
    <div class="mactions">
      <button class="btn" data-close>取消</button>
      <button class="btn pri" id="lgDone">完成登录</button>
    </div>`;
  m.querySelector("#lgDone").addEventListener("click", async () => {
    const code = m.querySelector("#lgCode").value.trim();
    if (!code) { mErr(m, "请输入验证码"); return; }
    mBusy(m, "正在验证…");
    try {
      await wsCmd("huawei_home_storage/login_code", { flow_id: flowId, code });
      close();
      toast("账号已添加");
      const panel = window.__hs_panel;
      if (panel) panel._load();
    } catch (err) { mErr(m, String(err.message || err)); }
  });
}

function mErr(m, msg) {
  let box = m.querySelector(".merr");
  if (!box) {
    box = document.createElement("div");
    box.className = "merr";
    m.querySelector("#mBody").prepend(box);
  }
  box.textContent = msg;
}

function mBusy(m, msg) {
  const b = m.querySelector("#mBody .btn.pri");
  if (b) { b.disabled = true; b.textContent = msg; }
}

function toast(msg) {
  const panel = window.__hs_panel;
  const host = (panel && panel.shadowRoot) || document.body;
  // 同一时间只保留一条：连续操作时旧提示不会在底部堆成一列
  host.querySelectorAll(".toast").forEach(function (old) { old.remove(); });
  const t = document.createElement("div");
  t.className = "toast";
  t.textContent = msg;
  host.appendChild(t);
  setTimeout(() => t.remove(), 2600);
}

/* ===================== 视图注册表 ===================== */
const VIEWS = {
  overview: { icon: "📊", title: "概览", render: renderOverview, group: "浏览" },
  albums: { icon: "🖼️", title: "相册", render: renderAlbums, group: "浏览" },
  files: { icon: "📁", title: "文件", render: renderFiles, group: "浏览" },
  search: { icon: "🔍", title: "搜索", render: renderSearch, group: "浏览" },
  tasks: { icon: "📋", title: "任务", render: renderTasks, group: "管理" },
  device: { icon: "⚙️", title: "设备", render: renderDevice, group: "管理" },
  users: { icon: "👥", title: "用户", render: renderUsers, group: "管理" },
  config: { icon: "\U0001F527", title: "配置", render: renderConfig, group: "管理" },
};

/* ===================== 组件 ===================== */
class HuaweiStoragePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._view = "overview";
    this._status = null;
    this._error = "";
    this._timer = null;
  }

  set hass(h) {
    const first = !this._hass;
    this._hass = h;
    window.__hs_panel = this;   // 尽早暴露，供模块级函数取 hass
    if (first) this._load();
  }
  get hass() { return this._hass; }

  connectedCallback() {
    window.__hs_panel = this;
    this.shadowRoot.innerHTML = `
      <style>${STYLES}</style>
      <div class="app">
        <header class="topbar">
          <div class="brand"><span class="logo">🗄️</span>
            <span>家庭存储<span class="sub" id="brandSub"></span></span></div>
          <div class="spacer"></div>
          <div class="accts" id="accts"></div>
          ${renderSkinner()}
          <span class="pill" id="onlinePill"><i class="dot"></i><span>—</span></span>
        </header>
        <div class="body">
          <nav class="nav" id="nav"></nav>
          <main class="main" id="main"><div class="slot">载入中…</div></main>
        </div>
      </div>`;
    this._renderNav();
    applySkin(CUR_SKIN);
    this._initKeys();
    if (this._hass) this._load();
  }

  /** 全局快捷键：Esc 关闭弹层，Ctrl/Cmd+K 跳搜索。 */
  _initKeys() {
    if (this._keys) return;
    this._keys = true;
    const sr = this.shadowRoot;
    this._onKey = (e) => {
      if (e.key === "Escape") {
        const v = sr.querySelector(".viewer");
        if (v) { const c = v.querySelector("[data-close]"); if (c) c.click(); return; }
        const m = sr.querySelector(".modal");
        if (m) { const c = m.querySelector("[data-close]"); if (c) c.click(); }
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        this._view = "search";
        this._renderNav();
        this._draw();
        setTimeout(() => { const i = sr.getElementById("kwInput"); if (i) i.focus(); }, 80);
      }
    };
    document.addEventListener("keydown", this._onKey);  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
    cleanupImages();
    // ⚠️ 全局 keydown 若不解绑：闭包持有 shadowRoot，面板反复进出会累积监听。
    if (this._onKey) {
      try { document.removeEventListener("keydown", this._onKey); } catch (e) { /* 已移除 */ }
      this._onKey = null;
    }   // observer 与图片队列随组件一起释放
  }

  _nav() { return this.shadowRoot.getElementById("nav"); }
  _main() { return this.shadowRoot.getElementById("main"); }

  _entry() {
    const all = (this._status && this._status.entries) || [];
    if (!all.length) return null;
    if (SEL.entry) return all.find((e) => e.entry_id === SEL.entry) || all[0];
    return all[0];
  }

  _account() {
    const d = this._entry() || {};
    const accs = d.accounts || [];
    if (!accs.length) return null;
    if (SEL.account) {
      const hit = accs.find((a) => a.key === SEL.account);
      if (hit) return hit;
      // 存的选择已不在列表里（账号被移除 / 权限被收回）→ 清掉，
      // 别把过期标识发给后端（后端会 403，界面看起来像坏掉了）。
      SEL.account = null;
    }
    return accs[0];
  }

  _counts() {
    const a = this._account();
    if (a && a.counts) return a.counts;
    return (this._entry() || {}).counts || {};
  }

  _data() {
    const d = Object.assign({}, this._entry() || {});
    d.counts = this._counts();
    d.current_account = this._account();
    // 配置视图要展示备份目标：与 backend backup.py 的 _opts 读法保持一致
    // （data 与 options 合并，options 优先）。
    const ent = this._rawEntry();
    if (ent) {
      const merged = Object.assign({}, ent.data || {}, ent.options || {});
      d.backup_dir = merged.backup_dir || "/file/HomeAssistant/";
      d.backup_space = merged.backup_space || "user";
    }
    return d;
  }

  /** 取原始 config entry（含 data/options）。 */
  _rawEntry() {
    const all = (this._status && this._status.entries) || [];
    if (!all.length) return null;
    const eid = SEL.entry || all[0].entry_id;
    // 面板拿不到 hass.config_entries，改为从后端 status 携带（若后端未下发则降级）
    return (all.find((e) => e.entry_id === eid) || all[0]) || null;
  }

  /** silent=true 时只刷新顶栏状态，不重绘主视图。
   * 定时轮询若整屏重绘，会把已加载的缩略图全部清空重新拉取
   * （图会「闪」一下并重新走一遍设备请求），因此轮询必须静默。 */
  async _load(silent) {
    if (!this._hass) return;
    try {
      const r = await this._hass.fetchWithAuth("/api/huawei_home_storage/status");
      if (!r.ok) throw new Error("HTTP " + r.status);
      this._status = await r.json();
      this._error = "";
    } catch (e) {
      this._error = String(e.message || e);
      if (silent) return;
    }
    if (silent && this._status) {
      this._paintTop(this._data());
      return;
    }
    this._draw();
    if (!this._timer) this._timer = setInterval(() => this._load(true), 60000);
  }

  /** 只更新顶栏（品牌副标题 + 在线状态 + 账号胶囊）。 */
  _paintTop(d) {
    this._renderAccts(d);
    const sub = this.shadowRoot.getElementById("brandSub");
    if (sub) sub.textContent = d.device_model ? " · " + d.device_model : "";
    const pill = this.shadowRoot.getElementById("onlinePill");
    if (pill) {
      pill.className = "pill" + (d.online ? "" : " off");
      pill.innerHTML = `<i class="dot ${d.online ? "live" : ""}"></i>
        <span>${d.online ? "在线" : "离线"}</span>`;
    }
  }

  _renderNav() {
    const groups = {};
    for (const [k, v] of Object.entries(VIEWS)) {
      (groups[v.group] = groups[v.group] || []).push([k, v]);
    }
    // 桌面：按分组的侧栏（浏览 / 管理）
    const deskHtml = Object.entries(groups).map(([group, items]) =>
      `<div class="sec">${esc(group)}</div>` + items.map(([k, v]) =>
        `<button data-view="${k}" class="${k === this._view ? "active" : ""}">
          <span class="ico">${v.icon}</span><span>${esc(v.title)}</span></button>`).join("")
    ).join("");

    // 移动端：8 项放不下（≈509px > 414px 屏宽）→ 5 个主入口 + 「更多」抽屉
    const PRIMARY = ["overview", "albums", "files", "search"];
    const primHtml = PRIMARY.map((k) => {
      const v = VIEWS[k];
      if (!v) return "";
      return `<button data-view="${k}" class="${k === this._view ? "active" : ""}">
        <span class="ico">${v.icon}</span><span>${esc(v.title)}</span></button>`;
    }).join("") + `<button data-act="more" class="${MORE_OPEN ? "active" : ""}">
      <span class="ico">☰</span><span>更多</span></button>`;

    // 「更多」抽屉内容：任务 / 设备 / 用户 / 配置
    const moreHtml = MORE_OPEN ? `<div class="morebar">` +
      ["tasks", "device", "users", "config"].map((k) => {
        const v = VIEWS[k];
        if (!v) return "";
        return `<button class="btn sm ${k === this._view ? "pri" : ""}" data-view="${k}">
          <span class="ico">${v.icon}</span> ${esc(v.title)}</button>`;
      }).join("") + `</div>` : "";

    this._nav().innerHTML = `<div class="nav-desk">${deskHtml}</div>`
      + `<div class="nav-mob">${primHtml}${moreHtml}</div>`;

    this._nav().querySelectorAll("[data-view]").forEach((b) => {
      b.addEventListener("click", () => {
        this._view = b.dataset.view;
        if (this._view !== "albums") ALB.album = null;
        if (this._view !== "tasks") TASK.data = null;
        MORE_OPEN = false;
        this._renderNav();
        this._draw();
      });
    });
    const moreBtn = this._nav().querySelector('[data-act="more"]');
    if (moreBtn) {
      moreBtn.addEventListener("click", () => {
        MORE_OPEN = !MORE_OPEN;
        this._renderNav();
      });
    }
  }


  _renderAccts(d) {
    const box = this.shadowRoot.getElementById("accts");
    if (!box) return;
    const accs = d.accounts || [];
    if (accs.length < 2) {
      const one = accs[0];
      box.innerHTML = one
        ? `<span class="acct on" title="当前账号">
             <span class="av">${esc((one.label || "?").slice(0, 2))}</span>
             <span>${esc(one.label || "账号")}</span></span>`
        : "";
      return;
    }
    const cur = this._account();
    box.innerHTML = accs.map((a) => {
      const on = cur && (a.key === cur.key || a.account === cur.account);
      return `<span class="acct ${on ? "on" : ""}" data-acct="${esc(a.key || a.account || "")}">
        <span class="av">${esc((a.label || "?").slice(0, 2))}</span>
        <span>${esc(a.label || "账号")}</span>
        ${a.is_primary ? '<span class="badge">主</span>' : ""}</span>`;
    }).join("");
    box.querySelectorAll("[data-acct]").forEach((x) => {
      x.addEventListener("click", () => {
        SEL.account = x.dataset.acct;
        ALB.data = null;
        ALB.album = null;
        this._draw();
        if (this._view === "files") { loadFiles(); initDnd(this); }
        if (this._view === "tasks") loadTasks();
        if (this._view === "search") {}
      });
    });
  }

  _draw() {
    const d = this._data();
    window.__hs_entry_id = d.entry_id || window.__hs_entry_id || "";
    window.__hs_panel = this;
    this._paintTop(d);

    const v = VIEWS[this._view] || VIEWS.overview;
    releaseImagesIn(this._main());   // ← 重绘前释放上一屏的缩略图 blob
    this._main().innerHTML =
      (this._error ? `<div class="err">加载失败：${esc(this._error)}</div>` : "")
      + v.render(d);

    this._wire();
    // 搜索框：回车即搜索（placeholder 承诺了"回车"，之前没绑，是 bug）
    const kwEl = this.shadowRoot.getElementById("kwInput");
    if (kwEl && !kwEl.dataset.enterBound) {
      kwEl.dataset.enterBound = "1";
      kwEl.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter") { ev.preventDefault(); doSearch(); }
      });
    }
    queueImages(this._main());
    // 拖拽上传必须在这里初始化。此前只在账号胶囊的点击回调里调（且单账号用户
    // 根本不会绑定该回调）→ 首次进文件页拖拽无反应（静默失败）。initDnd 幂等，重复调用安全。
    if (this._view === "files") { loadFiles(); initDnd(this); }
    if (this._view === "tasks") loadTasks();
    if (this._view === "search") {}
  }

  _wire(root) {
    // ⚠️ 此前只扫 .main → 顶栏里的皮肤切换器（data-act="skin"）永远拿不到 handler，
    // 5 个皮肤按钮全部点不动。改为：无 root 时同时扫描顶栏与主体。
    const scope = root || [this.shadowRoot.querySelector(".topbar"), this._main()];
    const nodes = [];
    (Array.isArray(scope) ? scope : [scope]).forEach((r) => {
      if (r) r.querySelectorAll("[data-act]").forEach((el) => nodes.push(el));
    });
    nodes.forEach((el) => {
      if (el.dataset.bound) return;
      el.dataset.bound = "1";
      const act = el.dataset.act;
      el.addEventListener("click", async (e) => {
        if (act === "go-albums") {
          this._view = "albums"; this._renderNav(); this._draw();
        } else if (act === "go-files") {
          this._view = "files"; this._renderNav(); this._draw();
        } else if (act === "refresh") {
          await this._call("huawei_home_storage", "refresh_credentials");
        } else if (act === "dup") {
          dupStart();
        } else if (act === "alb-group") {
          ALB.group = el.dataset.key; this._draw();
        } else if (act === "alb-create") {
          openPrompt({
            title: "新建相册",
            label: "相册名称",
            value: "",
            hint: "会在「共享相册」里创建，家庭成员都能看到。",
            okText: "创建",
            onOk: (name) => createAlbum(name),
          });
        } else if (act === "alb-del") {
          deleteAlbum();
        } else if (act === "alb-rename") {
          renameAlbum();
        } else if (act === "alb-upload") {
          pickAndUploadToAlbum();
        } else if (act === "alb-open") {
          openAlbum(Number(el.dataset.type), Number(el.dataset.id), el.dataset.name);
        } else if (act === "alb-back") {
          ALB.album = null; this._draw();
        } else if (act === "alb-more") {
          loadAlbumPage(true);
        } else if (act === "skin") {
          e.stopPropagation();
          applySkin(el.dataset.skin);
          this.shadowRoot.querySelector(".skinner")?.remove();
          const bar = this.shadowRoot.querySelector(".topbar");
          if (bar) bar.insertAdjacentHTML("beforeend", "");
          this._draw();
        } else if (act === "task-src") {
          TASK.src = el.dataset.src; TASK.data = null;
          this._draw(); loadTasks();
        } else if (act === "task-reload") {
          TASK.data = null; this._draw(); loadTasks();
        } else if (act === "task-retry") {
          retryTask(el.dataset.id, el.dataset.type);
        } else if (act === "task-clean") {
          cleanTasks([el.dataset.id], "这条任务记录");
        } else if (act === "task-clean-all") {
          const ids = ((TASK.data && TASK.data.tasks) || []).map((t) => t.taskId);
          cleanTasks(ids, "本来源全部 " + ids.length + " 条记录");
        } else if (act === "search-clear") {
          SRC.kw = ""; SRC.res = null; SRC.err = "";
          this._draw();
          setTimeout(() => { const i = this.shadowRoot.getElementById("kwInput"); if (i) i.focus(); }, 60);
        } else if (act === "search-go") {
          doSearch();
        } else if (act === "pick-on") {
          PICK.on = true; PICK.set.clear(); PICK.base = PH.path;
          this._draw();
        } else if (act === "pick-off") {
          PICK.on = false; PICK.set.clear();
          this._draw();
        } else if (act === "pick") {
          e.stopPropagation();
          // Shift 点击：从上一次勾选到当前，批量区间选择
          if (e.shiftKey && PICK.last != null) {
            const all = pickAllPaths();
            const a = all.indexOf(PICK.last), b = all.indexOf(el.dataset.path);
            if (a >= 0 && b >= 0) {
              const [lo, hi] = a < b ? [a, b] : [b, a];
              for (let i = lo; i <= hi; i++) PICK.set.add(all[i]);
            } else { togglePick(el.dataset.path); }
          } else {
            togglePick(el.dataset.path);
          }
          PICK.last = el.dataset.path;
          this._draw();
        } else if (act === "pick-all") {
          const all = [...(PH.data && PH.data.files || [])].map((f) =>
            PH.path + f.name + (f.type === 8 ? "" : "/"));
          PICK.set = new Set(all); PICK.last = null;
          this._draw();
        } else if (act === "pick-none") {
          PICK.set.clear(); PICK.last = null;
          this._draw();
        } else if (act === "pick-move") { pickRun("move");
        } else if (act === "pick-copy") { pickRun("copy");
        } else if (act === "pick-del") { pickRun("delete");
        } else if (act === "open-ha-config") {
          // 跳到 HA 的集成配置页（options flow 在其中）
          const eid = window.__hs_entry_id || "";
          if (!eid) { toast("未获取到配置条目"); return; }
          try {
            const nav = document.querySelector("home-assistant");
            const ha = nav && nav.hass;
            if (ha && ha.auth && ha.auth.data) {
              history.pushState({}, "", "/config/integrations/integration/huawei_home_storage");
              window.dispatchEvent(new Event("location-changed"));
            } else {
              toast("请在 HA 界面中打开");
            }
          } catch (err) { toast("跳转失败：" + String(err.message || err)); }
        } else if (act === "recover") {
          recoverItems([el.dataset.rid], "「" + el.dataset.name + "」");
        } else if (act === "recover-picked") {
          recoverItems([...PICK.set], "选中的 " + pickCount() + " 项");
        } else if (act === "recycle-purge") {
          purgeRecycleItems([...PICK.set]);
        } else if (act === "recycle-empty") {
          emptyRecycle();
        } else if (act === "dup") {
          dupStart();
        } else if (act === "dup-res") {
          dupResult();
        } else if (act === "diag") {
          diagLoad();
        } else if (act === "dest-go") {
          loadDestDirs(el.dataset.path);
        } else if (act === "dest-space") {
          // 切到另一个空间时回到该空间根目录：两个空间的目录树是各自独立的，
          // 保留原来那条路径会指向一个在该空间不存在的位置（必然报"目录不可用"）
          DEST.space = el.dataset.space === "public" ? "public" : "user";
          loadDestDirs("/file/");
        } else if (act === "dest-cancel") {
          DEST.open = false; DEST.cb = null;
          this._draw();
        } else if (act === "dest-ok") {
          const cb = DEST.cb, d = DEST.cur, sp = DEST.space;
          DEST.open = false; DEST.cb = null;
          this._draw();
          if (cb) cb(d, sp);
        } else if (act === "album-add-picked") {
          openAlbumOp("add");
        } else if (act === "album-remove-picked") {
          removePickedFromAlbum();
        } else if (act === "album-cover-picked") {
          setPickedAsCover();
        } else if (act === "album-share-picked") {
          openAlbumOp("share");
        } else if (act === "albop-cancel") {
          ALBOP.open = false; this._draw();
        } else if (act === "albop-ok") {
          runAlbumOp(el.dataset.id, el.dataset.name);
        } else if (act === "pick-all-photos") {
          PICK.set = new Set((ALB.photos || []).map((_, i) => "photo:" + i));
          PICK.last = null; this._draw();
        } else if (act === "row-dl") {
          e.stopPropagation();
          downloadFile(el.dataset.path, el.dataset.name);
        } else if (act === "nav") {
          const to = el.dataset.view;
          if (to && VIEWS[to]) {
            this._view = to;
            this._renderNav();
            this._draw();
          }
        } else if (act === "photo-open") {
          openViewer(ALB.photos, Number(el.dataset.idx));
        } else if (act === "file-open") {
          openViewer([{
            thumbUrl: el.dataset.url, viewUrl: el.dataset.url,
            downloadUrl: el.dataset.url, downloadName: el.dataset.name,
          }], 0);
        } else if (act === "fs-space") {
          // 切到/离开回收站时，回收站的空间默认跟随用户刚看的那个空间，
          // 这样"在共享空间删了东西 → 点最近删除"能直接看到它
          if (el.dataset.space === "recycle") {
            RECY.space = PH.space === "public" ? "public" : "user";
            PICK.on = false; PICK.set.clear();
          }
          PH.space = el.dataset.space;
          PH.path = "/file/";
          this._draw();
        } else if (act === "recy-space") {
          // 回收站空间切换：列表与恢复/删除/清空必须看同一个空间，
          // 否则会出现"条目都在、每条恢复都失败"（见 RECY 的注释）
          RECY.space = el.dataset.space === "public" ? "public" : "user";
          PICK.on = false; PICK.set.clear();
          this._draw();
        } else if (act === "fs-go") {
          // 点在行内的 ⋯ 上时不要跟着进目录
          if (e.target.closest('[data-act="row-menu"]')) return;
          // 多选模式下点行即勾选（不必精准点小复选框）
          if (PICK.on) {
            e.stopPropagation();
            togglePick(el.dataset.path);
            PICK.last = el.dataset.path;
            this._draw();
            return;
          }
          PH.path = el.dataset.path;
          if (PICK.on) { PICK.set.clear(); }
          loadFiles();
        } else if (act === "fs-mkdir") {
          openPrompt({
            title: "新建文件夹", label: "文件夹名称", value: "",
            hint: "建在当前目录：" + PH.path,
            onOk: async (name) => {
              const target = PH.path + name.replace(/\/+$/, "") + "/";
              await svc("create_folder", { path: target, category: curSpace() });
              toast("已创建 " + name);
              loadFiles();
            },
          });
        } else if (act === "fs-upload") {
          pickAndUpload();
        } else if (act === "row-menu") {
          e.stopPropagation();
          openRowMenu({
            name: el.dataset.name,
            path: el.dataset.path,
            isDir: el.dataset.dir === "1",
          });
        } else if (act === "add-account") {
          openLogin();
        } else if (act === "btn") {
          const map = { sleep: "休眠硬盘", eject: "弹出 USB", reboot: "重启设备" };
          const w = el.dataset.which;
          if (!window.confirm(`确定要${map[w] || w}吗？`)) return;
          await this._press(w);
        }
      });
    });
  }

  async _call(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data || {});
      toast("已执行");
      this._load();
    } catch (e) {
      toast("失败：" + String(e.message || e));
    }
  }

  async _press(which) {
    const d = this._data();
    const id = (d.buttons || {})[which];
    if (!id) { toast("未找到该按钮实体"); return; }
    await this._call("button", "press", { entity_id: id });
  }
}

if (!customElements.get("huawei-storage-panel")) {
  customElements.define("huawei-storage-panel", HuaweiStoragePanel);
}
