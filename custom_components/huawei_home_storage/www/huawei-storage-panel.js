/* 家庭存储面板（响应式 · 可扩展）
 * 一套 CSS，820px 断点自动切换「桌面侧栏 ↔ 手机底栏」
 * 视图注册表 VIEWS：新增功能只需加一项，导航自动生成
 */
const STYLES = String.raw`" + 
/* ===================== 设计令牌（对齐 HA 主题变量） ===================== */
:root{
  --bg:var(--primary-background-color,#f5f5f5);            /* --primary-background-color */
  --card:var(--card-background-color,var(--ha-card-background,#fff));             /* --card-background-color */
  --text:var(--primary-text-color,#212121);          /* --primary-text-color */
  --text2:var(--secondary-text-color,#727272);         /* --secondary-text-color */
  --divider:var(--divider-color,#e0e0e0);       /* --divider-color */
  --primary:var(--primary-color,#03a9f4);       /* --primary-color */
  --success:var(--success-color,#4caf50);       /* --success-color */
  --warn:#ff9800;
  --danger:var(--error-color,#f44336);
  --radius:14px;
  --shadow:0 1px 3px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.08);
  --gap:16px;
  --topbar:56px;
  --nav-w:220px;
}

*{box-sizing:border-box}
html,body{margin:0;padding:0;height:100%}
body{
  background:var(--bg);color:var(--text);
  font:400 15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",
       "PingFang SC","Microsoft YaHei",sans-serif;
  -webkit-font-smoothing:antialiased;
}

/* ===================== 骨架：顶部 + 侧栏 + 主区 ===================== */
.app{display:flex;flex-direction:column;min-height:100%}

/* 顶栏 */
.topbar{
  position:sticky;top:0;z-index:20;height:var(--topbar);
  display:flex;align-items:center;gap:12px;padding:0 16px;
  background:var(--card);border-bottom:1px solid var(--divider);
}
.brand{display:flex;align-items:center;gap:10px;font-weight:600;font-size:17px}
.brand .logo{
  width:30px;height:30px;border-radius:9px;display:grid;place-items:center;
  background:var(--primary);color:#fff;font-size:17px;
}
.brand .sub{font-weight:400;font-size:12px;color:var(--text2)}
.spacer{flex:1}
.pill{
  display:inline-flex;align-items:center;gap:6px;font-size:12px;font-weight:500;
  padding:5px 11px;border-radius:999px;background:rgba(76,175,80,.12);color:var(--success);
}
.pill.off{background:rgba(244,67,54,.12);color:var(--danger)}
.dot{width:8px;height:8px;border-radius:50%;background:currentColor}

/* 主体 */
.body{flex:1;display:flex;align-items:flex-start}

/* 侧栏（桌面） */
.nav{
  width:var(--nav-w);flex:none;position:sticky;top:var(--topbar);
  height:calc(100vh - var(--topbar));overflow:auto;
  padding:12px 10px;background:var(--card);border-right:1px solid var(--divider);
}
.nav button{
  width:100%;display:flex;align-items:center;gap:10px;
  padding:10px 12px;margin-bottom:4px;border:0;border-radius:10px;
  background:transparent;color:var(--text2);font-size:14px;cursor:pointer;text-align:left;
}
.nav button:hover{background:rgba(3,169,244,.08);color:var(--text)}
.nav button.active{background:rgba(3,169,244,.14);color:var(--primary);font-weight:600}
.nav .ico{width:20px;text-align:center;font-size:16px}
.nav .sec{
  margin:14px 12px 6px;font-size:11px;font-weight:700;letter-spacing:.6px;
  color:var(--text2);text-transform:uppercase;
}

/* 主内容 */
.main{flex:1;min-width:0;padding:var(--gap);max-width:1400px;margin:0 auto;width:100%}
h2.view-title{margin:0 0 14px;font-size:20px;font-weight:600}

/* 卡片 */
.card{
  background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);
  padding:16px;margin-bottom:var(--gap);
}
.card-h{
  display:flex;align-items:center;gap:8px;margin:0 0 12px;
  font-size:15px;font-weight:600;
}
.card-h .hint{margin-left:auto;font-size:12px;font-weight:400;color:var(--text2)}

/* 网格（自适应） */
.grid{display:grid;gap:12px;grid-template-columns:repeat(auto-fill,minmax(160px,1fr))}
.grid.kpi{grid-template-columns:repeat(auto-fill,minmax(200px,1fr))}

/* KPI 磁贴 */
.tile{
  background:var(--card);border-radius:var(--radius);box-shadow:var(--shadow);
  padding:14px;display:flex;gap:12px;align-items:flex-start;
}
.tile .ico{
  width:38px;height:38px;flex:none;border-radius:11px;display:grid;place-items:center;
  background:rgba(3,169,244,.12);color:var(--primary);font-size:18px;
}
.tile .lab{font-size:12px;color:var(--text2);margin-bottom:3px}
.tile .val{font-size:19px;font-weight:600;line-height:1.2}
.tile .val small{font-size:12px;font-weight:400;color:var(--text2);margin-left:4px}
.tile.warn .ico{background:rgba(255,152,0,.14);color:var(--warn)}
.tile.good .ico{background:rgba(76,175,80,.14);color:var(--success)}

/* 进度条 */
.bar{height:8px;border-radius:99px;background:var(--divider);overflow:hidden;margin-top:10px}
.bar > i{display:block;height:100%;background:var(--primary);border-radius:99px}
.bar.warn > i{background:var(--warn)}
.bar.danger > i{background:var(--danger)}

/* 列表行 */
.row{
  display:flex;align-items:center;gap:12px;padding:11px 0;
  border-bottom:1px solid var(--divider);
}
.row:last-child{border-bottom:0}
.row .k{color:var(--text2);font-size:13px;min-width:120px}
.row .v{margin-left:auto;font-weight:500;font-size:14px;text-align:right;word-break:break-all}

/* 按钮 */
.btn{
  display:inline-flex;align-items:center;justify-content:center;gap:7px;
  padding:10px 16px;min-height:44px;border-radius:10px;cursor:pointer;
  border:1px solid var(--divider);background:var(--bg);color:var(--text);font-size:14px;
}
.btn:hover{background:var(--divider)}
.btn.pri{background:var(--primary);border-color:var(--primary);color:#fff}
.btn.danger{background:var(--danger);border-color:var(--danger);color:#fff}
.btn[disabled]{opacity:.5;cursor:not-allowed}
.actions{display:flex;flex-wrap:wrap;gap:10px}

/* 扩展位：预留给未来功能 */
.slot{
  border:1.5px dashed var(--divider);border-radius:12px;padding:18px;text-align:center;
  color:var(--text2);font-size:13px;background:transparent;
}

/* ===================== 手机：底栏导航 ===================== */
@media (max-width:820px){
  .nav{
    position:fixed;bottom:0;left:0;right:0;top:auto;width:auto;height:auto;
    display:flex;overflow-x:auto;border-right:0;border-top:1px solid var(--divider);
    padding:6px;gap:4px;z-index:30;
  }
  .nav .sec{display:none}
  .nav button{
    flex:1;min-width:72px;flex-direction:column;gap:3px;padding:7px 4px;
    font-size:11px;text-align:center;margin:0;border-radius:9px;
  }
  .nav button .ico{font-size:18px}
  .main{padding:12px 12px calc(76px + env(safe-area-inset-bottom))}
  .grid{grid-template-columns:repeat(auto-fill,minmax(140px,1fr))}
  .grid.kpi{grid-template-columns:repeat(2,1fr)}
  .row .k{min-width:96px;font-size:12px}
  .row .v{font-size:13px}
  .btn{flex:1;min-width:calc(50% - 5px)}
  h2.view-title{font-size:18px}
}
/* ---- 照片/文件浏览器 ---- */
.crumbs{display:flex;flex-wrap:wrap;align-items:center;gap:4px;font-size:13px;margin-bottom:12px}
.crumbs a{color:var(--primary);cursor:pointer;text-decoration:none;padding:2px 4px;border-radius:6px}
.crumbs a:hover{background:rgba(3,169,244,.1)}
.crumbs .sep{color:var(--text2)}
.phgrid{display:grid;gap:10px;grid-template-columns:repeat(auto-fill,minmax(120px,1fr))}
.ph{position:relative;aspect-ratio:1;border-radius:10px;overflow:hidden;background:var(--divider);cursor:pointer}
.ph img{width:100%;height:100%;object-fit:cover;display:block}
.ph .cap{position:absolute;left:0;right:0;bottom:0;padding:4px 6px;font-size:11px;color:#fff;
  background:linear-gradient(transparent,rgba(0,0,0,.65));white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dir{aspect-ratio:auto;display:flex;flex-direction:column;align-items:center;justify-content:center;
  gap:6px;padding:14px 8px;text-align:center}
.dir .dico{font-size:30px}
.dir .dname{font-size:12px;color:var(--text2);word-break:break-all;max-height:2.6em;overflow:hidden}
.viewer{position:fixed;inset:0;z-index:999;background:rgba(0,0,0,.9);
  display:flex;flex-direction:column;align-items:center;justify-content:center}
.viewer img{max-width:96vw;max-height:84vh;object-fit:contain;border-radius:6px}
.viewer .vbar{position:absolute;top:0;left:0;right:0;display:flex;align-items:center;gap:10px;
  padding:12px 16px;color:#fff;font-size:13px}
.viewer .vbar .btn{min-height:36px;padding:6px 14px}
.viewer .vmeta{color:#ddd;font-size:12px;margin-top:10px;text-align:center;padding:0 16px}
.filerow{display:flex;align-items:center;gap:10px;padding:9px 0;border-bottom:1px solid var(--divider)}
.filerow:last-child{border-bottom:0}
.filerow .fico{font-size:18px;width:24px;text-align:center}
.filerow .fname{flex:1;font-size:13px;word-break:break-all}
.filerow .fsize{font-size:12px;color:var(--text2);flex:none}
@media (max-width:820px){
  .phgrid{grid-template-columns:repeat(3,1fr);gap:6px}
}

 + "`;

const VIEWS = {
  overview:{icon:"📊", title:"概览", render:renderOverview},
  storage :{icon:"💾", title:"存储", render:renderStorage},
  photos  :{icon:"🖼️", title:"相册", render:renderPhotos},
  device  :{icon:"⚙️", title:"设备", render:renderDevice},
  network :{icon:"🌐", title:"网络", render:renderNetwork},
  backup  :{icon:"☁️", title:"备份", render:renderBackup},
};

/* ---------- 工具 ---------- */
const fmtSize=(b)=>{
  if(b==null||isNaN(b)) return "—";
  const u=["B","KB","MB","GB","TB","PB"]; let i=0;
  while(b>=1024&&i<u.length-1){b/=1024;i++;}
  return b.toFixed(i===0?0:(b<10?1:0))+" "+u[i];
};
const esc=(s)=>String(s??"").replace(/[&<>"]/g,(c)=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const tile=(icon,label,value,cls="")=>`<div class="tile ${cls}">
    <div class="ico">${icon}</div>
    <div><div class="lab">${esc(label)}</div><div class="val">${esc(value)}</div></div>
  </div>`;
const row=(k,v)=>`<div class="row"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`;
const dash=(v)=>v??"—";
/* 序列号默认打码（仓库隐私扫描会拦设备序列号），点按钮才显示 */
const maskSn=(v)=>{
  const s=String(v||"");
  return s.length>8?s.slice(0,2)+"****"+s.slice(-4):(s||"—");
};
/* 账号脱敏：手机号/邮箱只保留前 3 后 4，避免面板与截图泄漏 */
const maskAccount=(a)=>{
  const s=String(a||"");
  if(!s) return "账号";
  if(s.includes("@")){
    const [u,d2]=s.split("@");
    return (u.length>2?u.slice(0,2)+"***":u)+"@"+d2;
  }
  return s.length>7?s.slice(0,3)+"****"+s.slice(-4):s.slice(0,1)+"***";
};

/* ---------- 视图 ---------- */
function renderOverview(d){
  const c=d.counts||{}, hw=d.hardware||{}, dk=d.disk||{};
  const usage=dk.usage??0;
  const lvl=usage>=90?"danger":usage>=75?"warn":"";
  return `
    <h2 class="view-title">概览</h2>
    <div class="grid kpi">
      ${tile("🖼️","照片",dash(c.photos))}
      ${tile("🎬","视频",dash(c.videos))}
      ${tile("👥","人脸相册",dash(c.face_albums))}
      ${tile("🗑️","回收站",dash(c.trash))}
      ${tile("🧩","已装插件",dash(c.installed_plugins),"good")}
      ${tile("📄","最近文件",dash(c.recent_files))}
    </div>
    <div class="card" style="margin-top:var(--gap)">
      <div class="card-h">💾 容量<span class="hint">${fmtSize(dk.used||0)} / ${fmtSize(dk.total||0)}</span></div>
      <div class="bar ${lvl}"><i style="width:${Math.min(100,usage)}%"></i></div>
      <div style="margin-top:8px;font-size:13px;color:var(--text2)">
        已用 ${usage}% · 剩余 ${fmtSize(dk.free||0)} · ${dash(dk.slots)} 个盘位
      </div>
    </div>
    <div class="card">
      <div class="card-h">⚡ 运行状态</div>
      <div class="grid">
        ${tile("🔥","CPU",hw.cpu_usage!=null?hw.cpu_usage+"%":"—",hw.cpu_usage>=80?"warn":"")}
        ${tile("🌡️","温度",hw.cpu_temperature!=null?hw.cpu_temperature+"°C":"—",
               hw.cpu_temperature==null?"":hw.cpu_temperature>=70?"warn":"good")}
        ${tile("🧠","内存",hw.memory_total?Math.round((hw.memory_used||0)/hw.memory_total*100)+"%":"—")}
        ${tile("🔌","USB",d.usb&&d.usb.status?"已接入":"未接入")}
      </div>
    </div>`;
}

function renderStorage(d){
  const dk=d.disk||{};
  return `
    <h2 class="view-title">存储</h2>
    <div class="grid kpi">
      ${tile("💽","总容量",fmtSize(dk.total))}
      ${tile("📈","已用",fmtSize(dk.used))}
      ${tile("📉","剩余",fmtSize(dk.free))}
      ${tile("🔢","盘位",dash(dk.slots))}
    </div>
    <div class="card" style="margin-top:var(--gap)">
      <div class="card-h">👥 设备用户<span class="hint">${(d.device_users||[]).length} 个</span></div>
      <div class="row"><span class="k">用户数</span><span class="v">${(d.device_users||[]).length}</span></div>
      <div style="margin-top:8px;font-size:12px;color:var(--text2)">
        出于隐私，面板不展示具体用户名/ID。
      </div>
    </div>
    <div class="card">
      <div class="card-h">🗂️ 文件</div>
      <div class="grid">
        ${tile("📄","最近文件",dash(d.counts?.recent_files))}
        ${tile("📁","全部文件",dash(d.counts?.all_files))}
        ${tile("♻️","重复照片",dash(d.counts?.duplicate_photos),"good")}
      </div>
    </div>`;
}

/* 照片/文件浏览器：基于 /filesvc/files 目录 + thumb 图片代理 */
const PH_STATE = { path:"/file/", stack:[], data:null, loading:false };

function renderPhotos(d){
  // 异步加载目录；browsePhotos 会把内容写进 shadow 内的 #phWrap
  setTimeout(()=>browsePhotos(PH_STATE.root||window.__hs_entry_id, PH_STATE.path),0);
  return `
    <h2 class="view-title">照片与文件</h2>
    <div id="phWrap"><div class="slot">加载中…</div></div>`;
}

async function browsePhotos(_root, path){
  const panel=window.__hs_panel;
  const host=panel?panel.shadowRoot.getElementById("phWrap"):null;
  const entryId=window.__hs_entry_id||"";
  if(!entryId||!host){ return; }
  PH_STATE.loading=true;
  host.innerHTML='<div class="slot">加载中…</div>';
  try{
    const h=panel.hass||panel._hass;
    const resp=await h.fetchWithAuth(
      "/api/huawei_home_storage/files/"+encodeURIComponent(entryId)+"?path="+encodeURIComponent(path));
    if(!resp.ok) throw new Error("HTTP "+resp.status);
    const data=await resp.json();
    PH_STATE.path=path; PH_STATE.data=data;
    if(host) host.innerHTML=renderBrowser(data, path, entryId);
    // 绑定目录点击与图片点击
    if(host){
      /* 图片懒加载: fetchWithAuth -> blob URL（img 标签无法带认证头） */
      const h2=panel.hass||panel._hass;
      const lazy=[...host.querySelectorAll("img[data-src]")];
      const loadOne=async(im)=>{
        try{
          const r2=await h2.fetchWithAuth(im.dataset.src);
          if(!r2.ok) throw new Error("HTTP "+r2.status);
          im.src=URL.createObjectURL(await r2.blob());
        }catch(e){ im.style.opacity=".25"; }
      };
      for(const im of lazy.slice(0,60)) loadOne(im);   /* 首屏先加载 60 张 */
      lazy.slice(60).forEach((im,i)=>setTimeout(()=>loadOne(im), 3000+i*300));
      host.querySelectorAll("[data-dir]").forEach(x=>x.addEventListener("click",()=>{
        browsePhotos(null, x.dataset.dir);
      }));
      host.querySelectorAll(".ph[data-full]").forEach(x=>x.addEventListener("click",()=>{
        openViewer(x.dataset.full, x.dataset.name||"", x.dataset.meta||"");
      }));
      host.querySelectorAll("[data-crumb]").forEach(x=>x.addEventListener("click",()=>{
        browsePhotos(null, x.dataset.crumb);
      }));
      const up=host.querySelector("[data-up]");
      if(up) up.addEventListener("click",()=>browsePhotos(null, up.dataset.up));
    }
  }catch(err){
    if(host) host.innerHTML=`<div class="slot">加载失败：${esc(String(err&&err.message||err))}</div>`;
  }finally{ PH_STATE.loading=false; }
}

function crumbs(path, entryId){
  const parts=String(path).split("/").filter(Boolean);
  let acc="/file/";
  const out=[`<a data-crumb="/file/">/file</a>`];
  for(const p of parts.slice(1)){
    acc += p + "/";
    out.push(`<span class="sep">›</span><a data-crumb="${esc(acc)}">${esc(p)}</a>`);
  }
  return `<div class="crumbs">${out.join("")}</div>`;
}

function renderBrowser(data, path, entryId){
  const files=(data.files||[]);
  const dirs=files.filter(f=>f.type!==8);
  const imgs=files.filter(f=>f.type===8 && (f.mime||"").startsWith("image/"));
  const others=files.filter(f=>f.type===8 && !(f.mime||"").startsWith("image/"));
  // 面包屑
  let acc=""; const crumbs=[];
  for(const p of String(path).split("/").filter(Boolean)){
    acc+=p+"/";
    crumbs.push(`<a data-crumb="/${acc.replace(/^\//,"")}">${esc(p)}</a>`);
  }
  const parent = path.replace(/[^/]+\/$/,"") || "/file/";
  const upBtn = path!=="/file/"
    ? `<button class="btn" data-up="${esc(parent)}">⬆️ 上一级</button>` : "";
  return `
    <div class="crumbs">
      ${crumbs.map(c=>c).join('<span class="sep">›</span>')}
      ${upBtn?'<span style="margin-left:auto">'+upBtn+'</span>':''}
    </div>
    ${dirs.length?`<div class="grid" style="margin-bottom:14px">
      ${dirs.map(f=>{
        const full=path+(f.name||"")+"/";
        return `<div class="ph dir" data-dir="${esc(full)}">
          <span class="dico">📁</span><span class="dname">${esc(f.name||"")}</span>
        </div>`;}).join("")}
    </div>`:""}
    ${imgs.length?`<div class="phgrid">
      ${imgs.map(f=>`<div class="ph" data-full="${esc(fullOf(f,path))}"
            data-name="${esc(f.name||"")}" data-meta="${esc(fmtSize(f.size))}">
          ${f.thumbUrl?`<img data-src="${esc(f.thumbUrl)}" alt="">`:""}
          <span class="cap">${esc(f.name||"")}</span>
        </div>`).join("")}
    </div>`:""}
    ${others.length?`<div class="card" style="margin-top:14px">
      <div class="card-h">📄 其他文件（${others.length}）</div>
      ${others.map(f=>`<div class="filerow">
        <span class="fico">📄</span><span class="fname">${esc(f.name||"")}</span>
        <span class="fsize">${fmtSize(f.size)}</span></div>`).join("")}
    </div>`:""}
    ${!dirs.length&&!imgs.length&&!others.length?'<div class="slot">此目录为空</div>':""}
  `;
}

/* 原图路径 = 目录 + 文件名（实测直取原图 1.8MB JPEG 成功）*/
function fullOf(f, path){
  return path + (f.name||"");
}

function openViewer(full, name, meta){
  const v=document.createElement("div");
  v.className="viewer";
  const entryId=window.__hs_entry_id||"";
  const seg=String(full).replace(/^\//,"").split("/").map(encodeURIComponent).join("/");
  const url="/api/huawei_home_storage/image/"+encodeURIComponent(entryId)+"/raw/"+seg;
  v.innerHTML=`
    <div class="vbar">
      <button class="btn" data-close>✕ 关闭</button>
      <span>${esc(name)}</span>
    </div>
    <img alt="加载中…">
    <div class="vmeta">${esc(meta||"")}</div>`;
  /* 大图也要走认证: fetchWithAuth -> blob（img 无法带请求头） */
  const panel=window.__hs_panel;
  const h=panel&&(panel.hass||panel._hass);
  (async()=>{
    const img=v.querySelector("img");
    try{
      const rr=await h.fetchWithAuth(url);
      if(!rr.ok) throw new Error("HTTP "+rr.status);
      img.src=URL.createObjectURL(await rr.blob());
    }catch(e){ img.alt="加载失败: "+String((e&&e.message)||e); }
  })();
  v.addEventListener("click",(e)=>{
    if(e.target===v || e.target.closest("[data-close]")) v.remove();
  });
  /* 必须挂在面板 shadow 内：.viewer 的样式在 shadow 里，挂到 document.body 会丢样式
     （表现为大图不是全屏遮罩而是排在页面下方） */
  (window.__hs_panel&&window.__hs_panel.shadowRoot||document.body).appendChild(v);
}

function renderDevice(d){
  const hw=d.hardware||{}, h=d.health||{}, s=d.samba||{}, au=d.auto_upgrade||{};
  return `
    <h2 class="view-title">设备</h2>
    <div class="card">
      <div class="card-h">🖥️ 硬件</div>
      ${row("型号",dash(d.device_model))}
      ${row("固件",dash(hw.firmware))}
      ${row("CPU",`${dash(hw.cpu_model)} · ${dash(hw.cpu_cores)} 核`)}
      <div class="row"><span class="k">序列号</span><span class="v">
        <span id="snText">${esc(maskSn(d.device_sn))}</span>
        <button class="btn" style="padding:2px 8px;min-height:28px;font-size:12px"
                data-act="toggle-sn">显示</button>
      </span></div>
    </div>
    <div class="card">
      <div class="card-h">💚 健康</div>
      ${row("错误码",dash(h.error_code))}
      ${row("维修模式",dash(h.repair_mode))}
      ${row("访问设备数",dash(h.client_devices))}
      ${row("已装插件",dash(d.counts?.installed_plugins))}
    </div>
    <div class="card">
      <div class="card-h">🔧 服务与升级</div>
      ${row("公共 Samba",s.public?"开启":"关闭")}
      ${row("用户 Samba",s.user?"开启":"关闭")}
      ${row("自动升级",au.enabled?"开启":"关闭")}
      ${row("升级时段",au.window||"—")}
    </div>
    <div class="card">
      <div class="card-h">🎛️ 设备操作</div>
      <div class="actions">
        <button class="btn" data-act="sleep">😴 磁盘休眠</button>
        <button class="btn" data-act="eject">⏏️ 弹出 USB</button>
        <button class="btn danger" data-act="reboot">🔄 重启设备</button>
      </div>
      <div style="margin-top:10px;font-size:12px;color:var(--text2)">
        重启会中断服务约 1-2 分钟，仅在你点击时触发。
      </div>
    </div>`;
}

function renderNetwork(d){
  const n=d.network||{};
  return `
    <h2 class="view-title">网络</h2>
    <div class="card">
      <div class="card-h">🌐 地址</div>
      ${row("IPv4",n.ipv4||d.host||"—")}
      ${row("IPv6",n.ipv6||"—")}
    </div>
    <div class="card">
      <div class="card-h">🔐 连接</div>
      ${(d.accounts||[]).map((a)=>`
        <div class="row"><span class="k">${esc(maskAccount(a.account))}</span>
        <span class="v" style="font-size:12px">${esc(a.tunnel||"—")}</span></div>`).join("")
        || '<div class="slot">暂无账号信息</div>'}
    </div>
    <div class="card">
      <div class="card-h">🛠️ 操作</div>
      <div class="actions">
        <button class="btn pri" data-act="refresh">🔑 刷新凭据</button>
      </div>
    </div>`;
}

function renderBackup(){
  return `
    <h2 class="view-title">备份</h2>
    <div class="slot">☁️ HA 备份到家庭存储<br>
      <span style="font-size:12px">（上传通道打通后启用 · 已预留接口）</span>
    </div>`;
}

/* ---------- Web Component ---------- */
class HuaweiStoragePanel extends HTMLElement {
  constructor(){
    super();
    this.attachShadow({mode:"open"});
    this._status=null; this._error=""; this._view="overview"; this._busy=false; this._hass=null;
  }

  connectedCallback(){
    this.shadowRoot.innerHTML=`
      <style>${STYLES}</style>
      <div class="app">
        <header class="topbar">
          <div class="brand"><span class="logo">🗄️</span>
            <span>家庭存储<span class="sub" id="brandSub"></span></span></div>
          <div class="spacer"></div>
          <span class="pill" id="onlinePill"><i class="dot"></i><span>—</span></span>
        </header>
        <div class="body">
          <nav class="nav" id="nav"></nav>
          <main class="main" id="main"></main>
        </div>
      </div>`;
    this._nav().addEventListener("click",(e)=>{
      const b=e.target.closest("button[data-view]"); if(!b) return;
      this._nav().querySelectorAll("button").forEach((x)=>x.classList.remove("active"));
      b.classList.add("active"); this._view=b.dataset.view; this._draw();
      window.scrollTo({top:0,behavior:"smooth"});
    });
    this._main().addEventListener("click",(e)=>{
      const b=e.target.closest("button[data-act]"); if(b) this._act(b.dataset.act,b);
    });
    this._load();
  }

  /* HA 面板框架把 hass 作为 property 注入（认证请求与调用服务都靠它） */
  set hass(h){
    const was=this._hass;
    this._hass=h;
    if(h&&!was&&this.shadowRoot.getElementById("main")) this._load();
  }
  get hass(){ return this._hass; }

  _nav(){return this.shadowRoot.getElementById("nav");}
  _main(){return this.shadowRoot.getElementById("main");}

  _renderNav(){
    const keys=Object.keys(VIEWS);
    const main=keys.slice(0,5), ext=keys.slice(5);
    const btn=(k)=>{const v=VIEWS[k];return `<button data-view="${k}" class="${k===this._view?"active":""}">
      <span class="ico">${v.icon}</span>${v.title}</button>`;};
    this._nav().innerHTML=`<div class="sec">概览</div>${main.map(btn).join("")}`+
      (ext.length?`<div class="sec">扩展</div>${ext.map(btn).join("")}`:"");
  }

  /* HA 把 hass 作为 property 注入，时机可能晚于 connectedCallback，
     所以这里等它就绪再发请求；必须用 hass.fetchWithAuth（裸 fetch 会 401）。 */
  _hassReady(){
    const h=this.hass||this._hass;
    return (h&&typeof h.fetchWithAuth==="function")?h:null;
  }

  async _load(){
    let h=this._hassReady();
    if(!h){
      // 等待注入（最多约 3 秒）
      for(let i=0;i<15&&!h;i++){
        await new Promise((r)=>setTimeout(r,200));
        h=this._hassReady();
      }
    }
    if(!h){
      this._error="未获取到 Home Assistant 连接（hass）";
      this._draw();
      return;
    }
    try{
      const resp=await h.fetchWithAuth("/api/huawei_home_storage/status");
      if(!resp.ok) throw new Error("HTTP "+resp.status);
      this._status=await resp.json(); this._error="";
    }catch(err){ this._error=String((err&&err.message)||err); }
    this._draw();
  }

  _draw(){
    const d=(this._status&&this._status.entries&&this._status.entries[0])||{};
    // 照片浏览器需要 entry_id 与面板引用
    window.__hs_entry_id = d.entry_id || window.__hs_entry_id || "";
    window.__hs_panel = this;
    this._renderNav();
    const v=VIEWS[this._view]||VIEWS.overview;
    this._main().innerHTML=
      (this._error?`<div class="card" style="border-left:4px solid var(--danger)">
        加载失败：${esc(this._error)}</div>`:"")+v.render(d);
    const on=!!d.online;
    const p=this.shadowRoot.getElementById("onlinePill");
    p.className="pill"+(on?"":" off");
    p.innerHTML=`<i class="dot"></i><span>${on?"在线":"离线"}</span>`;
    this.shadowRoot.getElementById("brandSub").textContent=d.device_model?" · "+d.device_model:"";
  }

  async _act(act,btn){
    if(act==="toggle-sn"){
      const d=(this._status&&this._status.entries&&this._status.entries[0])||{};
      const t=this.shadowRoot.getElementById("snText");
      if(!t) return;
      const full=String(d.device_sn||"");
      const masked=t.dataset.masked||maskSn(full);
      if(!t.dataset.masked) t.dataset.masked=masked;
      const showing=t.textContent===full;
      t.textContent=showing?masked:full;
      btn.textContent=showing?"显示":"隐藏";
      return;
    }
    if(this._busy) return;
    const d=(this._status&&this._status.entries&&this._status.entries[0])||{};
    const confirms={
      reboot:"确认重启设备？服务会中断约 1-2 分钟。",
      sleep:"确认让磁盘休眠？",
      eject:"确认弹出 USB 设备？",
    };
    if(confirms[act]&&!window.confirm(confirms[act])) return;
    this._busy=true; const old=btn.textContent; btn.disabled=true; btn.textContent="处理中…";
    try{ await this._call(act,d); }
    catch(err){ window.alert("操作失败："+String((err&&err.message)||err)); }
    finally{ btn.disabled=false; btn.textContent=old; this._busy=false; await this._load(); }
  }

  async _call(act,d){
    const hass=this.hass||this._hass;
    if(act==="media"){
      window.history.pushState(null,"","/media-browser/browse/media-source");
      window.dispatchEvent(new CustomEvent("location-changed",{bubbles:true,composed:true}));
      return;
    }
    if(!hass) throw new Error("尚未连接到 Home Assistant");
    const services={
      refresh:["huawei_home_storage","refresh_credentials",{}],
      dup:["huawei_home_storage","duplicate_scan",{act:"start"}],
    };
    if(services[act]){
      const [dom,svc,data]=services[act];
      await hass.callService(dom,svc,data);
      return;
    }
    // 按钮实体：按状态里返回的实体 ID 调用
    const eid=(d.buttons||{})[act];
    if(!eid) throw new Error("未找到对应按钮实体（"+act+"）");
    await hass.callService("button","press",{entity_id:eid});
  }
}

customElements.define("huawei-storage-panel",HuaweiStoragePanel);
