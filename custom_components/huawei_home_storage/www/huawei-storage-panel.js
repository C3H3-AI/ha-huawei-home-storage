/* 家庭存储面板
 * 结构：侧栏/底栏按「浏览」「管理」分组
 *   浏览 → 概览 · 相册(真实相册) · 文件(我的文件/共享/最近删除)
 *   管理 → 设备(硬件+存储+网络+操作) · 用户(成员+账号+登录)
 * 视觉：温润数据中心风（青蓝品牌 + 柔和纵深 + 毛玻璃）
 */
const STYLES = String.raw`
:host{
  /* —— 跟随 HA 主题（深浅色都成立） —— */
  --bg:var(--primary-background-color,#f4f6fa);
  --card:var(--card-background-color,var(--ha-card-background,#ffffff));
  --text:var(--primary-text-color,#17202a);
  --text2:var(--secondary-text-color,#64748b);
  --divider:var(--divider-color,#e6eaf0);

  /* —— 品牌：青蓝 + 暖调点缀 —— */
  --brand:#0e8fc4;
  --brand-2:#12b3e8;
  --brand-soft:rgba(14,143,196,.10);
  --brand-line:rgba(14,143,196,.24);

  --ok:#2fa563;
  --warn:#e0902a;
  --danger:#d94f45;
  --ok-soft:rgba(47,165,99,.12);
  --warn-soft:rgba(224,144,42,.14);
  --danger-soft:rgba(217,79,69,.12);

  --radius:18px;
  --radius-s:12px;
  --gap:20px;
  --topbar:62px;

  --sh-1:0 1px 2px rgba(15,23,42,.04),0 2px 6px rgba(15,23,42,.05);
  --sh-2:0 6px 18px -4px rgba(15,23,42,.12),0 2px 6px -2px rgba(15,23,42,.06);
  --ring:0 0 0 1px rgba(15,23,42,.045);

  --font-display:'Baloo 2','HarmonyOS Sans SC','PingFang SC','Hiragino Sans GB','Microsoft YaHei',system-ui,sans-serif;
  --font-body:'IBM Plex Sans','HarmonyOS Sans SC','PingFang SC','Microsoft YaHei',system-ui,sans-serif;
}
*{box-sizing:border-box}
:host{
  display:block;
  background:
    radial-gradient(1100px 460px at 12% -8%,rgba(14,143,196,.07),transparent 62%),
    radial-gradient(900px 420px at 96% 4%,rgba(224,144,42,.05),transparent 60%),
    var(--bg);
  color:var(--text);
  font:400 14px/1.55 var(--font-body);
  -webkit-font-smoothing:antialiased;
}
.app{display:flex;flex-direction:column;min-height:100%}

/* ========== 顶栏 ========== */
.topbar{
  position:sticky;top:0;z-index:20;height:var(--topbar);
  display:flex;align-items:center;gap:12px;padding:0 20px;
  background:color-mix(in srgb,var(--card) 84%,transparent);
  backdrop-filter:blur(16px) saturate(1.5);
  -webkit-backdrop-filter:blur(16px) saturate(1.5);
  border-bottom:1px solid var(--divider);
}
.brand{display:flex;align-items:center;gap:11px;font-family:var(--font-display);
  font-weight:700;font-size:17px;letter-spacing:.2px;flex:none}
.brand .logo{
  width:36px;height:36px;border-radius:12px;display:grid;place-items:center;
  background:linear-gradient(140deg,var(--brand-2),var(--brand));color:#fff;font-size:18px;
  box-shadow:0 4px 12px rgba(14,143,196,.38),inset 0 1px 0 rgba(255,255,255,.28);
}
.brand .sub{font-family:var(--font-body);font-weight:500;font-size:12px;color:var(--text2)}
.spacer{flex:1}
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
  border:1px solid var(--divider);background:var(--card);color:var(--text2);
  transition:background .16s,color .16s,border-color .16s;white-space:nowrap}
.acct:hover{background:var(--brand-soft);color:var(--text)}
.acct.on{background:var(--brand-soft);color:var(--brand);border-color:var(--brand-line)}
.acct .av{width:22px;height:22px;border-radius:50%;display:grid;place-items:center;
  background:linear-gradient(140deg,var(--brand-2),var(--brand));color:#fff;
  font-size:10.5px;font-weight:700;flex:none}
.acct .badge{font-size:10px;font-weight:700;padding:1px 6px;border-radius:99px;
  background:var(--brand);color:#fff}

/* ========== 主体 ========== */
.body{flex:1;display:flex;align-items:flex-start}
.nav{width:224px;flex:none;position:sticky;top:var(--topbar);
  height:calc(100vh - var(--topbar));overflow:auto;
  padding:16px 11px;background:var(--card);border-right:1px solid var(--divider)}
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

.main{flex:1;min-width:0;padding:var(--gap);max-width:1240px;margin:0 auto;width:100%;
  animation:fadeUp .45s cubic-bezier(.22,1,.36,1) both}
@keyframes fadeUp{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
h2.view-title{margin:2px 0 16px;font-family:var(--font-display);font-size:20px;font-weight:700}
.vhead{display:flex;align-items:center;gap:12px;margin-bottom:16px;flex-wrap:wrap}
.vhead h2{margin:0;font-family:var(--font-display);font-size:20px;font-weight:700}
.vhead .sub{font-size:12px;color:var(--text2)}

/* ========== 卡片 ========== */
.card{background:var(--card);border-radius:var(--radius);box-shadow:var(--sh-1),var(--ring);
  padding:20px;margin-bottom:var(--gap);transition:box-shadow .2s}
.card:hover{box-shadow:var(--sh-2),var(--ring)}
.card-h{display:flex;align-items:center;gap:10px;margin:0 0 15px;
  font-family:var(--font-display);font-size:14.5px;font-weight:700}
.card-h::before{content:"";width:3px;height:15px;border-radius:2px;flex:none;
  background:linear-gradient(180deg,var(--brand-2),var(--brand))}
.card-h .hint{margin-left:auto;font-family:var(--font-body);font-size:12px;
  font-weight:500;color:var(--text2)}

.grid{display:grid;gap:13px;grid-template-columns:repeat(auto-fill,minmax(158px,1fr))}
.grid.kpi{grid-template-columns:repeat(auto-fill,minmax(196px,1fr))}

/* ========== KPI ========== */
.tile{position:relative;overflow:hidden;background:var(--card);border-radius:15px;
  box-shadow:var(--sh-1),var(--ring);padding:16px;display:flex;gap:14px;align-items:center;
  transition:transform .18s cubic-bezier(.22,1,.36,1),box-shadow .18s}
.tile::before{content:"";position:absolute;inset:0 auto 0 0;width:3px;background:var(--brand);opacity:.85}
.tile:hover{transform:translateY(-3px);box-shadow:var(--sh-2),var(--ring)}
.tile .ico{width:44px;height:44px;flex:none;border-radius:13px;display:grid;place-items:center;
  background:var(--brand-soft);color:var(--brand);font-size:20px}
.tile .lab{font-size:11.5px;color:var(--text2);margin-bottom:4px;font-weight:500}
.tile .val{font-family:var(--font-display);font-size:21px;font-weight:700;line-height:1.1;
  letter-spacing:-.3px;font-variant-numeric:tabular-nums}
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
  padding:10px 17px;min-height:42px;border-radius:12px;cursor:pointer;
  border:1px solid var(--divider);background:var(--card);color:var(--text);
  font-family:var(--font-body);font-size:13.5px;font-weight:600;
  transition:background .16s,box-shadow .16s,transform .1s;text-decoration:none}
.btn:hover{background:var(--bg);box-shadow:var(--sh-1)}
.btn:active{transform:scale(.97)}
.btn.pri{background:linear-gradient(140deg,var(--brand-2),var(--brand));
  border-color:transparent;color:#fff;box-shadow:0 4px 12px rgba(14,143,196,.32)}
.btn.pri:hover{filter:brightness(1.07)}
.btn.danger{background:var(--danger);border-color:var(--danger);color:#fff}
.btn.danger:hover{filter:brightness(1.06)}
.btn.sm{min-height:34px;padding:6px 12px;font-size:12.5px;border-radius:10px}
.btn[disabled]{opacity:.55;cursor:not-allowed;transform:none}
.actions{display:flex;flex-wrap:wrap;gap:11px}

/* 分段控件 */
.segs{display:flex;gap:6px;flex-wrap:wrap}
.seg{padding:8px 14px;border-radius:999px;font-size:13px;font-weight:600;cursor:pointer;
  border:1px solid var(--divider);background:var(--card);color:var(--text2);
  transition:background .16s,color .16s,border-color .16s}
.seg:hover{background:var(--brand-soft);color:var(--text)}
.seg.on{background:var(--brand-soft);color:var(--brand);border-color:var(--brand-line)}
.seg .n{font-size:11px;opacity:.75;margin-left:5px}

/* ========== 相册网格 ========== */
.albums{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(148px,1fr))}
.alb{position:relative;border-radius:15px;overflow:hidden;cursor:pointer;
  background:var(--card);box-shadow:var(--sh-1),var(--ring);
  transition:transform .18s cubic-bezier(.22,1,.36,1),box-shadow .18s}
.alb:hover{transform:translateY(-3px);box-shadow:var(--sh-2),var(--ring)}
.alb .cov{position:relative;aspect-ratio:1;background:var(--divider);overflow:hidden}
.alb .cov img{width:100%;height:100%;object-fit:cover;display:block}
.alb .cov .ph{width:100%;height:100%;display:grid;place-items:center;font-size:30px;
  background:linear-gradient(140deg,rgba(14,143,196,.14),rgba(14,143,196,.05));color:var(--brand)}
.alb .meta{padding:9px 11px 11px}
.alb .nm{font-size:13px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.alb .ct{font-size:11.5px;color:var(--text2);margin-top:2px}

/* ========== 照片网格 ========== */
.phgrid{display:grid;gap:8px;grid-template-columns:repeat(auto-fill,minmax(132px,1fr))}
.ph{position:relative;aspect-ratio:1;border-radius:12px;overflow:hidden;cursor:pointer;
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
@keyframes shimmer{from{background-position:120% 0}to{background-position:-120% 0}}

/* 文件行 */
.filerow{display:flex;align-items:center;gap:12px;padding:11px 4px;border-bottom:1px solid var(--divider)}
.filerow.dir{cursor:pointer}
.filerow.dir:hover{background:var(--brand-soft);border-radius:10px}
.filerow:last-child{border-bottom:0}
.filerow .fico{width:34px;height:34px;flex:none;border-radius:10px;display:grid;place-items:center;
  background:var(--brand-soft);color:var(--brand);font-size:16px}
.filerow .fmain{flex:1;min-width:0}
.filerow .fname{font-size:13.5px;font-weight:500;word-break:break-all}
.filerow .fsub{font-size:11.5px;color:var(--text2);margin-top:1px}
.filerow .fsize{font-size:12px;color:var(--text2);flex:none;font-variant-numeric:tabular-nums}

/* 文件操作：磁贴上的 ⋯ 与操作菜单 */
.phmenu{position:absolute;top:6px;right:6px;min-height:30px;padding:2px 9px;font-size:15px;
  border-radius:9px;background:rgba(0,0,0,.55);color:#fff;border:0;opacity:0;
  transition:opacity .15s;backdrop-filter:blur(4px)}
.ph:hover .phmenu{opacity:1}
.menu{display:flex;flex-direction:column;gap:6px;margin-top:4px}
.menu button{width:100%;text-align:left;justify-content:flex-start;gap:9px}
.menu button.danger{color:var(--danger);border-color:var(--danger-soft)}
.crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:3px;font-size:13px;margin-bottom:14px}
.crumbs a{color:var(--brand);cursor:pointer;text-decoration:none;padding:3px 7px;border-radius:7px}
.crumbs a:hover{background:var(--brand-soft)}
.crumbs .sep{color:var(--text2)}

/* ========== 大图查看器 ========== */
.viewer{position:fixed;inset:0;z-index:999;background:rgba(10,14,20,.94);
  backdrop-filter:blur(8px);-webkit-backdrop-filter:blur(8px);
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  animation:vfade .2s ease both;outline:none}
@keyframes vfade{from{opacity:0}to{opacity:1}}
.viewer img{max-width:94vw;max-height:78vh;object-fit:contain;border-radius:12px;
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
.mbox{width:100%;max-width:420px;max-height:88vh;overflow:auto;background:var(--card);
  border-radius:20px;box-shadow:0 24px 60px rgba(10,14,20,.35);padding:24px;
  animation:mup .26s cubic-bezier(.22,1,.36,1) both}
@keyframes mup{from{opacity:0;transform:translateY(14px) scale(.98)}to{opacity:1;transform:none}}
.mbox h3{margin:0 0 6px;font-family:var(--font-display);font-size:17px;font-weight:700}
.mbox p.sub{margin:0 0 18px;font-size:12.5px;color:var(--text2);line-height:1.5}
.field{margin-bottom:14px}
.field label{display:block;font-size:12px;font-weight:600;color:var(--text2);margin-bottom:6px}
.field input,.field select{width:100%;padding:11px 13px;border-radius:11px;font-size:14px;
  border:1px solid var(--divider);background:var(--bg);color:var(--text);font-family:var(--font-body)}
.field input:focus,.field select:focus{outline:none;border-color:var(--brand);
  box-shadow:0 0 0 3px var(--brand-soft)}
.merr{background:var(--danger-soft);color:var(--danger);font-size:12.5px;font-weight:500;
  padding:9px 12px;border-radius:10px;margin-bottom:14px}
.mnote{background:var(--brand-soft);color:var(--brand);font-size:12px;padding:9px 12px;
  border-radius:10px;margin-bottom:14px;line-height:1.5}
.mactions{display:flex;gap:10px;margin-top:6px}
.mactions .btn{flex:1}
.steps{display:flex;gap:6px;margin-bottom:18px}
.steps i{flex:1;height:3px;border-radius:2px;background:var(--divider)}
.steps i.on{background:var(--brand)}

/* ========== 用户 ========== */
.users{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}
.ucard{background:var(--card);border-radius:14px;box-shadow:var(--sh-1),var(--ring);
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
.slot{border:1.5px dashed var(--divider);border-radius:15px;padding:28px 18px;text-align:center;
  color:var(--text2);font-size:13px}
.slot.sm{padding:18px 14px}
.note{font-size:12px;color:var(--text2);margin-top:12px;line-height:1.6}
.err{background:var(--danger-soft);color:var(--danger);border-radius:12px;padding:12px 14px;
  font-size:13px;margin-bottom:14px}
.toast{position:fixed;left:50%;bottom:26px;transform:translateX(-50%);z-index:2000;
  background:var(--brand);color:#fff;padding:10px 18px;border-radius:999px;font-size:13px;
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
  .nav button{flex:1;min-width:60px;flex-direction:column;gap:3px;padding:7px 4px;
    font-size:10.5px;text-align:center;margin:0;border-radius:11px}
  .nav button:hover{transform:none}
  .nav button.active{box-shadow:none}
  .nav button .ico{font-size:19px}
  .main{padding:14px 13px calc(88px + env(safe-area-inset-bottom))}
  h2.view-title,.vhead h2{font-size:18px}
  .grid{grid-template-columns:repeat(auto-fill,minmax(132px,1fr));gap:10px}
  .grid.kpi{grid-template-columns:repeat(2,1fr);gap:10px}
  .tile{padding:13px;border-radius:14px}
  .tile .val{font-size:19px}
  .card{padding:15px;border-radius:16px;margin-bottom:14px}
  .row .k{min-width:88px;font-size:12px}
  .row .v{font-size:12.5px}
  .btn{flex:1;min-width:calc(50% - 6px)}
  .albums{grid-template-columns:repeat(3,1fr);gap:8px}
  .alb .meta{padding:7px 8px 9px}
  .alb .nm{font-size:12px}
  .phgrid{grid-template-columns:repeat(3,1fr);gap:6px}
  .users{grid-template-columns:repeat(2,1fr);gap:10px}
  .ucard{padding:12px}
  .modal{align-items:flex-end;padding:0}
  .mbox{max-width:none;border-radius:20px 20px 0 0;max-height:92vh;
    padding-bottom:calc(24px + env(safe-area-inset-bottom))}
  .viewer .nav{width:40px;height:40px}
}
`;

/* ===================== 工具 ===================== */
const esc = (s) => String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
}[c]));

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
const PH = { path: "/file/", space: "user", data: null, upload: null };
const SEL = { entry: null, account: null };
const ALB = { data: null, group: null, album: null, photos: [], next: null, loading: false, err: "" };

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
    img.src = URL.createObjectURL(await r.blob());
    img.style.opacity = "1";
  } catch (e) {
    img.style.opacity = ".25";
  }
}

function queueImages(root) {
  const imgs = [...root.querySelectorAll("img[data-src]")];
  if (!imgs.length) return;
  const io = new IntersectionObserver((entries) => {
    entries.forEach((en) => {
      if (!en.isIntersecting) return;
      const img = en.target;
      io.unobserve(img);
      IMG_QUEUE.push({ img, url: img.dataset.src });
      pumpImages();
    });
  }, { rootMargin: "300px" });
  imgs.forEach((im) => io.observe(im));
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

  return `
    <h2 class="view-title">概览</h2>
    <div class="card">
      <div class="card-h">💾 存储容量
        <span class="hint">${fmtSize(dk.used || 0)} / ${fmtSize(dk.total || 0)}</span></div>
      <div style="font-family:var(--font-display);font-size:30px;font-weight:700">
        ${pct}%<span style="font-size:14px;font-weight:500;color:var(--text2);margin-left:8px">
        已使用</span></div>
      <div class="bar ${cls}"><i style="width:${pct}%"></i></div>
      <div style="display:flex;gap:18px;margin-top:12px;font-size:12.5px;color:var(--text2)">
        <span>已用 <b style="color:var(--text)">${fmtSize(dk.used || 0)}</b></span>
        <span>可用 <b style="color:var(--text)">${fmtSize(dk.free || 0)}</b></span>
      </div>
    </div>

    <div class="grid kpi">
      <div class="tile"><div class="ico">🖼️</div><div>
        <div class="lab">照片</div><div class="val">${c.photos ?? "—"}</div></div></div>
      <div class="tile"><div class="ico">🎬</div><div>
        <div class="lab">视频</div><div class="val">${c.videos ?? "—"}</div></div></div>
      <div class="tile"><div class="ico">📄</div><div>
        <div class="lab">文件</div><div class="val">${c.all_files ?? "—"}</div></div></div>
      <div class="tile ${online ? "good" : "danger"}"><div class="ico">📶</div><div>
        <div class="lab">设备状态</div><div class="val">${online ? "在线" : "离线"}</div></div></div>
      <div class="tile"><div class="ico">👥</div><div>
        <div class="lab">设备用户</div><div class="val">${(d.device_users || []).length}</div></div></div>
      <div class="tile"><div class="ico">🗂️</div><div>
        <div class="lab">智能相册</div><div class="val">${albums || "—"}</div></div></div>
    </div>

    <div class="card" style="margin-top:var(--gap)">
      <div class="card-h">⚡ 快捷操作</div>
      <div class="actions">
        <button class="btn pri" data-act="go-albums">🖼️ 浏览相册</button>
        <button class="btn" data-act="go-files">📁 浏览文件</button>
        <button class="btn" data-act="refresh">🔄 刷新凭据</button>
        <button class="btn" data-act="dup">🔍 扫描重复照片</button>
      </div>
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
      ${cur ? `<span class="acct on"><span class="av">${esc((cur.label || "?").slice(0, 2))}</span>
        ${esc(cur.label || "")}</span>` : ""}
    </div>
    <div class="segs" style="margin-bottom:16px">
      ${groups.map((x) => `<span class="seg ${x.key === g.key ? "on" : ""}"
        data-act="alb-group" data-key="${esc(x.key)}">${esc(x.title)}
        <span class="n">${x.albums.length}</span></span>`).join("")}
    </div>
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

function renderAlbumDetail() {
  const a = ALB.album;
  const photos = ALB.photos || [];
  return `
    <div class="vhead">
      <button class="btn sm" data-act="alb-back">← 返回相册</button>
      <h2>${esc(a.name)}</h2>
      <span class="sub">已载入 ${photos.length} 张</span>
    </div>
    ${ALB.err ? `<div class="err">${esc(ALB.err)}</div>` : ""}
    ${photos.length ? `<div class="phgrid">
      ${photos.map((p, i) => `
        <div class="ph" data-act="photo-open" data-idx="${i}">
          ${p.thumbUrl ? `<img data-src="${esc(p.thumbUrl)}" alt="" style="opacity:0">`
                       : `<div class="sk"></div>`}
          ${p.mtime ? `<span class="cap">${esc(fmtDate(p.mtime).slice(5, 16))}</span>` : ""}
        </div>`).join("")}
    </div>` : `<div class="slot">正在载入照片…</div>`}
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
  ALB.album = { type, id, name };
  ALB.photos = [];
  ALB.next = null;
  ALB.err = "";
  const panel = window.__hs_panel;
  if (panel) panel._draw();
  await loadAlbumPage(false);
}

async function loadAlbumPage(append) {
  const eid = window.__hs_entry_id || "";
  if (!eid || !ALB.album) return;
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
      ${space !== "recycle" ? `<span class="spacer" style="flex:1"></span>
        <button class="btn sm" data-act="fs-mkdir">＋ 新建文件夹</button>
        <button class="btn sm pri" data-act="fs-upload">⬆ 上传文件</button>
        <input type="file" id="fsFile" style="display:none">` : ""}
    </div>
    ${PH.upload ? `<div class="card" style="padding:12px 16px">
      <div style="display:flex;align-items:center;gap:10px;font-size:12.5px">
        <b>${esc(PH.upload.name)}</b>
        <span style="color:var(--text2)">${fmtSize(PH.upload.done)} / ${fmtSize(PH.upload.total)}</span>
        <span style="flex:1"></span>
        <span style="color:var(--brand);font-weight:600">${PH.upload.pct}%</span>
      </div>
      <div class="bar"><i style="width:${PH.upload.pct}%"></i></div>
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
      const q = SEL.account ? `?account=${encodeURIComponent(SEL.account)}` : "";
      const res = await apiGet(`/api/huawei_home_storage/recycle/${encodeURIComponent(eid)}${q}`);
      box.innerHTML = renderRecycle(res);
      if (panel) panel._wire(box);
      return;
    }
    const q = new URLSearchParams({ path: PH.path, space: PH.space });
    if (SEL.account) q.set("account", SEL.account);
    const res = await apiGet(`/api/huawei_home_storage/files/${encodeURIComponent(eid)}?${q}`);
    PH.data = res;
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
      ${dirs.map((f) => `<div class="filerow dir" data-act="fs-go"
          data-path="${esc(base + f.name)}/">
        <span class="fico">📁</span>
        <span class="fmain"><span class="fname">${esc(f.name)}</span></span>
        <button class="btn sm" data-act="row-menu" data-name="${esc(f.name)}"
          data-path="${esc(base + f.name)}/" data-dir="1">⋯</button>
        <span class="fsize">›</span></div>`).join("")}
    </div>` : ""}
    ${imgs.length ? `<div class="card">
      <div class="card-h">🖼️ 图片<span class="hint">${imgs.length} 张</span></div>
      <div class="phgrid">
        ${imgs.map((f) => `<div class="ph" data-act="file-open"
            data-url="${esc(f.thumbUrl || "")}" data-name="${esc(f.name)}">
          ${f.thumbUrl ? `<img data-src="${esc(f.thumbUrl)}" alt="" style="opacity:0">`
                       : `<div class="sk"></div>`}
          <span class="cap">${esc(f.name)}</span>
          <button class="btn sm phmenu" data-act="row-menu" data-name="${esc(f.name)}"
            data-path="${esc(base + f.name)}" data-dir="0">⋯</button></div>`).join("")}
      </div>
    </div>` : ""}
    ${plain.length ? `<div class="card">
      <div class="card-h">📄 其他文件<span class="hint">${plain.length} 个 · ${fmtSize(
        plain.reduce((s, f) => s + (f.size || 0), 0))}</span></div>
      ${plain.map((f) => `<div class="filerow">
        <span class="fico">📄</span>
        <span class="fmain"><span class="fname">${esc(f.name)}</span>
          <span class="fsub">${esc(fmtDate(f.mtime))}</span></span>
        <span class="fsize">${fmtSize(f.size)}</span>
        <button class="btn sm" data-act="row-menu" data-name="${esc(f.name)}"
          data-path="${esc(base + f.name)}" data-dir="0">⋯</button></div>`).join("")}
    </div>` : ""}
    ${!dirs.length && !others.length ? `<div class="slot">此目录为空</div>` : ""}`;
}

function renderRecycle(res) {
  const items = res.items || [];
  if (!items.length) return `<div class="slot">最近删除是空的</div>`;
  return `<div class="card">
    <div class="card-h">🗑️ 最近删除<span class="hint">${res.count} 项</span></div>
    ${items.map((it) => `<div class="filerow">
      <span class="fico">🗑️</span>
      <span class="fmain"><span class="fname">${esc(it.name)}</span>
        <span class="fsub">${esc(fmtDate(it.mtime))}</span></span>
      <span class="fsize">${esc(String(it.path || "").split("/").filter(Boolean).slice(-2, -1)[0] || "")}</span>
    </div>`).join("")}
    <div class="note">恢复或彻底删除请到「媒体 → 华为家庭存储 → 最近删除」操作。</div>
  </div>`;
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
      } else if (op === "move" || op === "copy") {
        openPrompt({
          title: op === "move" ? "移动到" : "复制到",
          label: "目标文件夹", value: dir,
          hint: "目标目录必须已存在（目录需带尾斜杠）。",
          onOk: async (dest) => {
            const d = dest.endsWith("/") ? dest : dest + "/";
            await svc(op === "move" ? "move_paths" : "copy_paths",
                      { paths: [path], dest_dir: d, category: curSpace() });
            toast(op === "move" ? "已移动" : "已复制"); loadFiles();
          },
        });
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
    const f = input.files && input.files[0];
    if (f) doUpload(f);
  };
  input.click();
}

async function doUpload(file) {
  const panel = window.__hs_panel;
  const eid = window.__hs_entry_id || "";
  const h = hassOf();
  const dest = PH.path + file.name;
  const url = `/api/huawei_home_storage/upload/${encodeURIComponent(eid)}`
    + `?path=${encodeURIComponent(dest)}&space=${encodeURIComponent(curSpace())}`;
  PH.upload = { name: file.name, done: 0, total: file.size, pct: 0 };
  if (panel) panel._draw();

  const finish = (ok, msg) => {
    PH.upload = null;
    if (panel) panel._draw();
    toast(msg);
    if (ok) loadFiles();
  };

  // 用 XHR 才能拿到上传进度（fetch 没有 progress 事件）
  const token = (h.auth && h.auth.data && h.auth.data.access_token) || null;
  if (!token) { finish(false, "无法获取访问令牌，请刷新页面"); return; }
  try {
    await new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url, true);
      xhr.setRequestHeader("Authorization", "Bearer " + token);
      xhr.setRequestHeader("Content-Type", "application/octet-stream");
      xhr.upload.onprogress = (ev) => {
        if (!PH.upload || !ev.lengthComputable) return;
        PH.upload.done = ev.loaded;
        PH.upload.pct = Math.round((ev.loaded / ev.total) * 100);
        const bar = panel && panel.shadowRoot.querySelector(".main .bar > i");
        const txt = panel && panel.shadowRoot.querySelector(".main .card .bar")
          ? panel.shadowRoot.querySelectorAll(".main .card span")
          : null;
        if (bar) bar.style.width = PH.upload.pct + "%";
        if (txt && txt.length) {
          const el = [...txt].find((x) => /\d+%/.test(x.textContent));
          if (el) el.textContent = PH.upload.pct + "%";
        }
      };
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
    finish(true, "上传完成：" + file.name);
  } catch (e) {
    finish(false, "上传失败：" + String(e.message || e));
  }
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

    <div class="card">
      <div class="card-h">⚙️ 设备操作</div>
      <div class="actions">
        <button class="btn" data-act="btn" data-which="sleep">😴 硬盘休眠</button>
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
    if (e.target === v || e.target.closest("[data-close]")) { v.remove(); return; }
    if (e.target.closest("[data-prev]")) { i = (i - 1 + list.length) % list.length; show(); return; }
    if (e.target.closest("[data-next]")) { i = (i + 1) % list.length; show(); return; }
  });
  v.addEventListener("keydown", (e) => {
    if (e.key === "Escape") v.remove();
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
  device: { icon: "⚙️", title: "设备", render: renderDevice, group: "管理" },
  users: { icon: "👥", title: "用户", render: renderUsers, group: "管理" },
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
          <span class="pill" id="onlinePill"><i class="dot"></i><span>—</span></span>
        </header>
        <div class="body">
          <nav class="nav" id="nav"></nav>
          <main class="main" id="main"><div class="slot">载入中…</div></main>
        </div>
      </div>`;
    this._renderNav();
    if (this._hass) this._load();
  }

  disconnectedCallback() {
    if (this._timer) clearInterval(this._timer);
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
      return accs.find((a) => a.key === SEL.account || a.account === SEL.account) || accs[0];
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
    return d;
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
    this._nav().innerHTML = Object.entries(groups).map(([group, items]) =>
      `<div class="sec">${esc(group)}</div>` + items.map(([k, v]) =>
        `<button data-view="${k}" class="${k === this._view ? "active" : ""}">
          <span class="ico">${v.icon}</span><span>${esc(v.title)}</span></button>`).join("")
    ).join("");
    this._nav().querySelectorAll("[data-view]").forEach((b) => {
      b.addEventListener("click", () => {
        this._view = b.dataset.view;
        if (this._view !== "albums") ALB.album = null;
        this._renderNav();
        this._draw();
      });
    });
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
        if (this._view === "files") loadFiles();
      });
    });
  }

  _draw() {
    const d = this._data();
    window.__hs_entry_id = d.entry_id || window.__hs_entry_id || "";
    window.__hs_panel = this;
    this._paintTop(d);

    const v = VIEWS[this._view] || VIEWS.overview;
    this._main().innerHTML =
      (this._error ? `<div class="err">加载失败：${esc(this._error)}</div>` : "")
      + v.render(d);

    this._wire();
    queueImages(this._main());
    if (this._view === "files") loadFiles();
  }

  _wire(root) {
    (root || this._main()).querySelectorAll("[data-act]").forEach((el) => {
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
          await this._call("huawei_home_storage", "duplicate_scan", { act: "start" });
        } else if (act === "alb-group") {
          ALB.group = el.dataset.key; this._draw();
        } else if (act === "alb-open") {
          openAlbum(Number(el.dataset.type), Number(el.dataset.id), el.dataset.name);
        } else if (act === "alb-back") {
          ALB.album = null; this._draw();
        } else if (act === "alb-more") {
          loadAlbumPage(true);
        } else if (act === "photo-open") {
          openViewer(ALB.photos, Number(el.dataset.idx));
        } else if (act === "file-open") {
          openViewer([{
            thumbUrl: el.dataset.url, viewUrl: el.dataset.url,
            downloadUrl: el.dataset.url, downloadName: el.dataset.name,
          }], 0);
        } else if (act === "fs-space") {
          PH.space = el.dataset.space;
          PH.path = "/file/";
          this._draw();
        } else if (act === "fs-go") {
          // 点在行内的 ⋯ 上时不要跟着进目录
          if (e.target.closest('[data-act="row-menu"]')) return;
          PH.path = el.dataset.path;
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
