/**
 * 华为家庭存储 - 侧边栏面板
 * 纯 Web Component（无外部依赖），使用 HA 的 CSS 变量以适配深浅主题。
 *
 * 文案全部走 HA 官方翻译体系：panel_custom 会把 localize 回调注入
 * panel.config，本组件用它取词；取不到时回退到内置中文。
 */
const STATUS_API = "huawei_home_storage/status";
const SERVICE_DOMAIN = "huawei_home_storage";
const SERVICE_REFRESH = "refresh_credentials";
const DOMAIN = "huawei_home_storage";

const MB = 1024 * 1024;

/** 内置回退文案（翻译资源缺失时使用） */
const FALLBACK = {
  title: "家庭存储",
  empty: "尚未配置任何设备。",
  refresh: "刷新凭据",
  refreshing: "刷新中…",
  openMedia: "打开媒体浏览",
  photos: "照片",
  videos: "视频",
  userAlbums: "用户相册",
  faceAlbums: "人物",
  sceneAlbums: "场景",
  placeAlbums: "地点",
  trash: "最近删除",
  diskTotal: "磁盘总容量",
  diskUsed: "磁盘已用",
  diskFree: "磁盘可用",
  usage: "使用率",
  model: "型号",
  serial: "序列号",
  mac: "MAC",
  lan: "局域网地址",
  tunnel: "设备会话通道",
  accountLogin: "华为账号 {account}（账号密码登录）",
  deviceCodeLogin: "设备码授权",
  sessionAt: "设备会话取得时间",
  usb: "USB",
  users: "设备用户",
};

function fmtSize(mb) {
  if (mb === null || mb === undefined) return "—";
  const bytes = mb * MB;
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let i = 0;
  while (value >= 1024 && i < units.length - 1) {
    value /= 1024;
    i += 1;
  }
  return `${value.toFixed(value >= 10 || i < 2 ? 0 : 1)} ${units[i]}`;
}

function maskAccount(account) {
  if (!account) return "—";
  if (account.length <= 6) return account;
  return `${account.slice(0, 3)}****${account.slice(-4)}`;
}

class HuaweiStoragePanel extends HTMLElement {
  constructor() {
    super();
    this._status = null;
    this._loading = false;
    this._busy = false;
    this._error = null;
    this._localize = null;
    this.attachShadow({ mode: "open" });
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this._load();
  }

  connectedCallback() {
    this._render();
    this._timer = window.setInterval(() => this._load(), 30000);
  }

  disconnectedCallback() {
    window.clearInterval(this._timer);
  }

  /** 取词：优先用 HA 注入的 localize，回退到内置文案 */
  _t(key, fallbackKey, placeholders) {
    if (this._localize) {
      try {
        const value = this._localize(`component.${DOMAIN}.common.${key}`);
        if (value) return value;
      } catch (e) {
        /* 未注册翻译资源时忽略 */
      }
    }
    let text = FALLBACK[fallbackKey || key] ?? key;
    if (placeholders) {
      for (const [k, v] of Object.entries(placeholders)) {
        text = text.replace(`{${k}}`, v);
      }
    }
    return text;
  }

  async _load() {
    if (!this._hass || this._loading) return;
    this._loading = true;
    try {
      this._status = await this._hass.callApi("GET", STATUS_API);
      this._error = null;
    } catch (err) {
      this._error = err && err.message ? err.message : String(err);
    } finally {
      this._loading = false;
      this._render();
    }
  }

  async _refreshCredentials() {
    if (this._busy) return;
    this._busy = true;
    this._render();
    try {
      await this._hass.callService(SERVICE_DOMAIN, SERVICE_REFRESH, {});
      await this._load();
    } catch (err) {
      this._error = err && err.message ? err.message : String(err);
    } finally {
      this._busy = false;
      this._render();
    }
  }

  _openMediaBrowser() {
    history.pushState(null, "", "/media-browser");
    window.dispatchEvent(new Event("location-changed"));
  }

  _render() {
    const entries = (this._status && this._status.entries) || [];
    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
          padding: 16px;
          color: var(--primary-text-color);
          background: var(--primary-background-color);
        }
        h1 {
          font-size: 22px;
          font-weight: 500;
          margin: 0 0 16px;
        }
        .card {
          background: var(--card-background-color, var(--ha-card-background));
          color: var(--primary-text-color);
          border-radius: var(--ha-card-border-radius, 12px);
          box-shadow: var(--ha-card-box-shadow, 0 2px 4px rgba(0,0,0,.15));
          padding: 16px;
          margin-bottom: 16px;
        }
        .card-header {
          display: flex;
          align-items: center;
          gap: 8px;
          margin-bottom: 12px;
          font-size: 18px;
          font-weight: 500;
        }
        .dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: var(--disabled-text-color);
        }
        .dot.on { background: var(--success-color, #4caf50); }
        .dot.off { background: var(--error-color, #f44336); }
        .grid {
          display: grid;
          grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
          gap: 12px;
        }
        .metric {
          background: var(--secondary-background-color);
          border-radius: 8px;
          padding: 10px 12px;
        }
        .metric .label {
          font-size: 12px;
          color: var(--secondary-text-color);
          margin-bottom: 4px;
        }
        .metric .value {
          font-size: 18px;
          font-weight: 500;
        }
        .bar {
          height: 8px;
          border-radius: 4px;
          background: var(--divider-color);
          overflow: hidden;
          margin-top: 8px;
        }
        .bar > span {
          display: block;
          height: 100%;
          background: var(--primary-color);
        }
        .actions {
          display: flex;
          flex-wrap: wrap;
          gap: 12px;
          margin-top: 16px;
        }
        button {
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 15px;
          padding: 10px 18px;
          border-radius: 8px;
          border: 1px solid var(--divider-color);
          background: var(--secondary-background-color);
          color: var(--primary-text-color);
          cursor: pointer;
        }
        button:hover { background: var(--divider-color); }
        button[disabled] { opacity: .5; cursor: default; }
        button.primary {
          background: var(--primary-color);
          border-color: var(--primary-color);
          color: var(--text-primary-color, #fff);
        }
        .meta {
          margin-top: 12px;
          font-size: 12px;
          color: var(--secondary-text-color);
          line-height: 1.6;
          word-break: break-all;
        }
        .error {
          color: var(--error-color);
          margin-bottom: 12px;
        }
        .empty { color: var(--secondary-text-color); }
      </style>
      <h1>${this._t("title")}</h1>
      ${this._error ? `<div class="error">${this._error}</div>` : ""}
      ${entries.length ? entries.map((e) => this._card(e)).join("") : `<div class="empty">${this._t("empty")}</div>`}
    `;
    const button = this.shadowRoot.querySelector("#refresh");
    if (button) button.addEventListener("click", () => this._refreshCredentials());
    const media = this.shadowRoot.querySelector("#media");
    if (media) media.addEventListener("click", () => this._openMediaBrowser());
  }

  _card(entry) {
    const c = entry.counts || {};
    const disk = entry.disk || {};
    const slots = disk.diskChangeInfo || [];
    const total = slots.reduce((sum, s) => sum + (s.totalSize || 0), 0);
    const used = slots.reduce((sum, s) => sum + (s.usedSize || 0), 0);
    const usage = total ? Math.round((used / total) * 1000) / 10 : null;
    const cred = entry.credentials || {};
    const obtained = cred.obtained_at
      ? new Date(cred.obtained_at * 1000).toLocaleString()
      : "—";
    const usb = entry.usb || {};
    const users = entry.device_users || [];

    return `
      <div class="card">
        <div class="card-header">
          <span class="dot ${entry.online ? "on" : "off"}"></span>
          <ha-icon icon="mdi:nas"></ha-icon>
          <span>${entry.title}</span>
        </div>
        <div class="grid">
          ${this._metric(this._t("photos"), c.photos)}
          ${this._metric(this._t("videos"), c.videos)}
          ${this._metric(this._t("user_albums"), c.user_albums)}
          ${this._metric(this._t("face_albums"), c.face_albums)}
          ${this._metric(this._t("scene_albums"), c.scene_albums)}
          ${this._metric(this._t("place_albums"), c.place_albums)}
          ${this._metric(this._t("trash"), c.trash)}
          ${this._metric(this._t("disk_total"), fmtSize(total || null))}
          ${this._metric(this._t("disk_used"), fmtSize(used || null))}
          ${this._metric(this._t("disk_free"), total ? fmtSize(total - used) : "—")}
          ${this._metric(this._t("disk_usage"), usage === null ? "—" : `${usage}%`)}
          ${this._metric(this._t("usb"), usb.status ? (usb.info || []).length || "已接入" : "—")}
          ${this._metric(this._t("users"), users.length || "—")}
        </div>
        ${usage === null ? "" : `<div class="bar"><span style="width:${usage}%"></span></div>`}
        <div class="meta">
          ${this._t("model")} ${entry.device_model || "—"} · ${this._t("serial")} ${entry.device_sn || "—"} · ${this._t("mac")} ${entry.device_mac || "—"}<br />
          ${this._t("lan")} ${entry.host || cred.https_url || "—"}<br />
          ${this._t("tunnel")} ${cred.https_url || "—"}${cred.data_https_url ? ` / ${cred.data_https_url}` : ""}<br />
          ${
            entry.login_method === "account"
              ? this._t("account_login", "accountLogin", { account: maskAccount(entry.account) })
              : this._t("device_code_login", "deviceCodeLogin")
          }<br />
          ${this._t("session_at", "sessionAt")}：${obtained}
        </div>
        <div class="actions">
          <button id="refresh" class="primary" ${this._busy ? "disabled" : ""}>
            <ha-icon icon="mdi:refresh"></ha-icon>
            ${this._busy ? this._t("refreshing") : this._t("refresh")}
          </button>
          <button id="media">
            <ha-icon icon="mdi:image-multiple"></ha-icon>
            ${this._t("open_media", "openMedia")}
          </button>
        </div>
      </div>
    `;
  }

  _metric(label, value) {
    const text = value === null || value === undefined ? "—" : value;
    return `<div class="metric"><div class="label">${label}</div><div class="value">${text}</div></div>`;
  }
}

customElements.define("huawei-storage-panel", HuaweiStoragePanel);
