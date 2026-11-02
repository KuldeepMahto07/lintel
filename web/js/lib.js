// Shared helpers: DOM building (text only, never innerHTML with data), the API client,
// toasts, drawers, dialogs, formatters. Everything the pages use comes from here.

// ---- DOM -------------------------------------------------------------------
export function h(tag, attrs, ...children) {
  const el = document.createElement(tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

const SVGNS = "http://www.w3.org/2000/svg";
export function s(tag, attrs, ...children) {
  const el = document.createElementNS(SVGNS, tag);
  setAttrs(el, attrs);
  append(el, children);
  return el;
}

function setAttrs(el, attrs) {
  if (!attrs) return;
  for (const [k, v] of Object.entries(attrs)) {
    if (v === null || v === undefined || v === false) continue;
    if (k === "class") el.setAttribute("class", Array.isArray(v) ? v.filter(Boolean).join(" ") : v);
    else if (k === "style" && typeof v === "object") Object.assign(el.style, v);
    else if (k === "dataset") Object.assign(el.dataset, v);
    else if (k.startsWith("on") && typeof v === "function") el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === "value" && "value" in el) el.value = v;
    else if (k === "checked" || k === "disabled" || k === "selected") el[k] = !!v;
    else el.setAttribute(k, v === true ? "" : String(v));
  }
}

export function append(el, children) {
  for (const c of children.flat(Infinity)) {
    if (c === null || c === undefined || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

export function clear(el, ...children) {
  el.replaceChildren();
  return append(el, children);
}

export const $ = (sel, root = document) => root.querySelector(sel);
export const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

// ---- state shared by the pages ---------------------------------------------
export const app = {
  me: null, // {user, firm, role, firms, csrf, usage}
  can(role) {
    const rank = ["viewer", "member", "approver", "admin", "owner"];
    return !!this.me && rank.indexOf(this.me.role) >= rank.indexOf(role);
  },
  plan(feature) { return !!this.me?.firm?.limits?.[feature]; },
};

// ---- API -------------------------------------------------------------------
export class ApiError extends Error {
  constructor(status, err) {
    super(err?.message || `Request failed (${status})`);
    this.status = status;
    this.code = err?.code;
    this.fields = err?.fields || {};
    this.data = err || {};
  }
}

const listeners = { offline: [], online: [] };
export const onNet = (ev, fn) => listeners[ev].push(fn);
let offline = false;

export async function api(path, opts = {}) {
  const { method = "GET", body, raw, signal } = opts;
  const headers = {};
  if (method !== "GET") headers["X-CSRF-Token"] = app.me?.csrf || "";
  let payload;
  if (raw !== undefined) { payload = raw; headers["Content-Type"] = "text/plain"; }
  else if (body !== undefined) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  let r;
  try {
    r = await fetch(path, { method, headers, body: payload, credentials: "same-origin", signal });
  } catch (e) {
    if (e.name === "AbortError") throw e;
    if (!offline) { offline = true; listeners.offline.forEach((f) => f()); }
    throw new ApiError(0, { code: "offline", message: "Can't reach Lintel." });
  }
  if (offline) { offline = false; listeners.online.forEach((f) => f()); }
  if (r.status === 204) return null;
  const type = r.headers.get("content-type") || "";
  const data = type.includes("json") ? await r.json() : await r.text();
  if (!r.ok) {
    const err = new ApiError(r.status, typeof data === "object" ? data.error : { message: data });
    if (r.status === 401 && !opts.allow401) {
      window.dispatchEvent(new CustomEvent("lintel:signed-out"));
    }
    throw err;
  }
  return data;
}
export const get = (p, o) => api(p, o);
export const post = (p, body, o = {}) => api(p, { ...o, method: "POST", body: body ?? {} });
export const patch = (p, body) => api(p, { method: "PATCH", body });
export const put = (p, body) => api(p, { method: "PUT", body });
export const del = (p, body) => api(p, { method: "DELETE", body });

// ---- formatting ------------------------------------------------------------
const THIN = " ";
export function num(v, digits = 0) {
  if (v === null || v === undefined || v === "") return "—";
  const n = Number(v);
  if (!Number.isFinite(n)) return String(v);
  const fixed = digits ? n.toFixed(digits) : String(Math.round(n));
  const [i, d] = fixed.split(".");
  const neg = i.startsWith("-");
  const grouped = (neg ? i.slice(1) : i).replace(/\B(?=(\d{3})+(?!\d))/g, THIN);
  return (neg ? "-" : "") + grouped + (d && Number(d) !== 0 ? "." + d : "");
}
export function measure(v, unit) {
  const u = (unit || "").toLowerCase();
  if (u === "m²" || u === "m2") return `${num(v, 1)} M²`;
  if (u === "mm" && Math.abs(Number(v)) >= 10000) return `${num(Number(v) / 1000, 1)} M`;
  if (u === "mm") return `${num(v)} MM`;
  return `${num(v, Number.isInteger(Number(v)) ? 0 : 1)}${unit ? " " + unit.toUpperCase() : ""}`;
}
export function ago(t) {
  if (!t) return "never";
  const d = Date.now() / 1000 - t;
  if (d < 45) return "just now";
  if (d < 90) return "1 min ago";
  if (d < 3600) return `${Math.round(d / 60)} min ago`;
  if (d < 5400) return "1 hour ago";
  if (d < 86400) return `${Math.round(d / 3600)} hours ago`;
  if (d < 172800) return "yesterday";
  return `${Math.round(d / 86400)} days ago`;
}
export const when = (t) => (t ? new Date(t * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" }) : "—");
export const clock = (t) => (t ? new Date(t * 1000).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" }) : "");
export const initials = (name) => (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join("").toUpperCase();
export const idx = (n) => `[${String(n).padStart(2, "0")}]`;
export const titleCase = (s) => String(s || "").replace(/_/g, " ");

// ---- toasts ----------------------------------------------------------------
export function toast(message, opts = {}) {
  const box = $("#toasts");
  const undo = opts.undo;
  const t = h("div", { class: ["toast", opts.error && "error"] },
    h("span", { class: "kind" }, opts.kind || (opts.error ? "Error" : "Done")),
    h("span", null, message),
    undo && h("button", { class: "undo", onclick: async () => { t.remove(); await undo(); } }, "Undo"));
  box.append(t);
  setTimeout(() => t.remove(), undo ? 6000 : 4000);
}
export const fail = (e) => toast(e?.message || "Something went wrong.", { error: true });

/** Run an action from a button: loading state, toast on error, button back to normal. */
export async function act(btn, fn, okMessage) {
  if (btn) { btn.classList.add("loading"); btn.disabled = true; }
  try {
    const out = await fn();
    if (okMessage) toast(typeof okMessage === "function" ? okMessage(out) : okMessage);
    return out;
  } catch (e) {
    if (e.code === "plan_limit") upgradePrompt(e);
    else fail(e);
    return undefined;
  } finally {
    if (btn && btn.isConnected) { btn.classList.remove("loading"); btn.disabled = false; }
  }
}

export function upgradePrompt(e) {
  dialog({
    title: "Upgrade needed",
    body: [h("p", null, e.message), h("p", { class: "small muted" }, `Current plan: ${String(e.data.plan || "free").toUpperCase()}.`)],
    actions: (close) => [
      h("button", { class: "btn", onclick: close }, "Not now"),
      app.can("owner") ? h("a", { class: "btn primary", href: "/app/settings/billing", "data-link": "", onclick: close }, "See plans →")
        : h("span", { class: "micro muted" }, "Ask your firm owner to upgrade"),
    ],
  });
}

// ---- drawers and dialogs ---------------------------------------------------
let openLayers = [];
export function closeTop() {
  const top = openLayers.pop();
  if (top) top();
  return !!top;
}

function layer(el) {
  const scrim = h("div", { class: "scrim" });
  document.body.append(scrim, el);
  const prevFocus = document.activeElement;
  requestAnimationFrame(() => { scrim.classList.add("open"); el.classList.add("open"); });
  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    openLayers = openLayers.filter((f) => f !== close);
    scrim.classList.remove("open"); el.classList.remove("open");
    setTimeout(() => { scrim.remove(); el.remove(); }, 220);
    prevFocus?.focus?.();
  };
  scrim.addEventListener("click", close);
  openLayers.push(close);
  setTimeout(() => (el.querySelector("[autofocus], input, select, textarea, button:not(.close)") || el).focus(), 60);
  return close;
}

export function drawer({ title, body, foot }) {
  const bodyEl = h("div", { class: "drawer-body" });
  const footEl = h("div", { class: "drawer-foot" });
  const el = h("aside", { class: "drawer", role: "dialog", "aria-modal": "true", "aria-label": title, tabindex: "-1" },
    h("div", { class: "drawer-head" }, h("span", { class: "title" }, title),
      h("button", { class: "close", "aria-label": "Close", onclick: () => close() }, "×")),
    bodyEl, footEl);
  const close = layer(el);
  append(bodyEl, [typeof body === "function" ? body(close) : body]);
  if (foot) append(footEl, [foot(close)]); else footEl.remove();
  return { close, body: bodyEl, el };
}

export function dialog({ title, body, actions, className }) {
  const bodyEl = h("div", { class: "drawer-body" });
  const footEl = h("div", { class: "drawer-foot" });
  const el = h("div", { class: ["dialog", className], role: "dialog", "aria-modal": "true", "aria-label": title, tabindex: "-1" },
    h("div", { class: "drawer-head" }, h("span", { class: "title" }, title),
      h("button", { class: "close", "aria-label": "Close", onclick: () => close() }, "×")),
    bodyEl, footEl);
  const close = layer(el);
  append(bodyEl, [typeof body === "function" ? body(close) : body]);
  if (actions) append(footEl, [actions(close)]); else footEl.remove();
  return { close, body: bodyEl, el };
}

/** Confirmation for destructive or bulk actions. Resolves true when confirmed. */
export function confirm({ title, message, confirmLabel = "Confirm", danger = false, typeToConfirm }) {
  return new Promise((resolve) => {
    let input;
    const d = dialog({
      title,
      body: [
        ...(Array.isArray(message) ? message : [h("p", null, message)]),
        typeToConfirm && field("Type " + typeToConfirm + " to confirm", input = h("input", { class: "input", autocomplete: "off" })),
      ],
      actions: (close) => {
        const ok = h("button", { class: ["btn", danger ? "danger" : "primary"], disabled: !!typeToConfirm,
          onclick: () => { resolve(true); close(); } }, confirmLabel);
        if (input) input.addEventListener("input", () => (ok.disabled = input.value.trim() !== typeToConfirm));
        return [h("button", { class: "btn", onclick: () => { resolve(false); close(); } }, "Cancel"), ok];
      },
    });
    d.el.querySelector(".close").addEventListener("click", () => resolve(false));
  });
}

// ---- form helpers ----------------------------------------------------------
export function field(label, control, hint) {
  const id = control.id || (control.id = "f" + Math.random().toString(36).slice(2, 8));
  return h("div", { class: "field", dataset: { name: control.name || "" } },
    h("label", { for: id }, label), control, hint && h("span", { class: "hint" }, hint));
}

export function showErrors(form, err) {
  $$(".field.error", form).forEach((f) => { f.classList.remove("error"); f.querySelector(".field-error")?.remove(); });
  $(".form-error", form)?.remove();
  const fields = err?.fields || {};
  let shown = false;
  for (const [name, msg] of Object.entries(fields)) {
    const f = $(`.field[data-name="${CSS.escape(name)}"]`, form);
    if (!f) continue;
    f.classList.add("error");
    f.append(h("span", { class: "field-error" }, msg));
    shown = true;
  }
  if (!shown && err) form.prepend(h("div", { class: "notice accent form-error" }, err.message));
}

export const formData = (form) => Object.fromEntries(new FormData(form).entries());

// ---- states ----------------------------------------------------------------
export const skeleton = (n = 6, cls = "skel-grid") => h("div", { class: cls, "aria-busy": "true", "aria-label": "Loading" },
  Array.from({ length: n }, () => h("div", { class: "skeleton" })));

export function loadError(e, retry) {
  if (e?.status === 404 || e?.status === 403) {
    return h("div", { class: "empty" }, h("span", { class: "label" }, "No access"),
      h("p", null, e.status === 404 ? "This doesn't exist, or you don't have access to it." : "You don't have access to this."),
      h("a", { class: "btn", href: "/app", "data-link": "" }, "Back to projects →"));
  }
  return h("div", { class: "load-error" }, h("span", null, `Couldn't load this: ${e?.message || "unknown error"}`),
    h("button", { class: "btn compact", onclick: retry }, "Retry"));
}

export function empty(label, text, action) {
  return h("div", { class: "empty" }, h("span", { class: "label" }, label), h("p", null, text), action);
}

export function chip(status, text) {
  return h("span", { class: ["chip", status] }, status === "applied" ? "✓ " : "", text || status);
}

export async function copy(text, what = "Copied") {
  try { await navigator.clipboard.writeText(text); toast(what); }
  catch { toast("Copy failed. Select the text and copy it by hand.", { error: true }); }
}

export async function download(path, filename) {
  const r = await fetch(path, { credentials: "same-origin" });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    throw new ApiError(r.status, data.error);
  }
  const url = URL.createObjectURL(await r.blob());
  const a = h("a", { href: url, download: filename });
  document.body.append(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export const reducedMotion = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
