// Lintel web app: router, app shell (header of cells), command bar, offline banner, global keys.
import { $, ApiError, app, clear, closeTop, dialog, get, h, initials, onNet, post, toast } from "./lib.js";
import { logoMark } from "./art.js";
import * as auth from "./pages/auth.js";
import * as projects from "./pages/projects.js";
import * as workspace from "./pages/workspace.js";
import * as approvals from "./pages/approvals.js";
import * as rules from "./pages/rules.js";
import * as audit from "./pages/audit.js";
import * as settings from "./pages/settings.js";

const ROUTES = [
  [/^\/login\/?$/, auth.login, false],
  [/^\/signup\/?$/, auth.signup, false],
  [/^\/reset\/?$/, auth.reset, false],
  [/^\/invite\/([^/]+)\/?$/, auth.invite, false],
  [/^\/app\/?$/, projects, true, "projects"],
  [/^\/app\/p\/([^/]+)(?:\/(issues|approvals|history|model|chat))?\/?$/, workspace, true, "projects"],
  [/^\/app\/approvals\/?$/, approvals, true, "approvals"],
  [/^\/app\/rules\/?$/, rules, true, "rules"],
  [/^\/app\/audit\/?$/, audit, true, "audit"],
  [/^\/app\/settings(?:\/(profile|firm|members|plugins|billing))?\/?$/, settings, true, "settings"],
];

const root = $("#app");
const panelMode = new URLSearchParams(location.search).get("panel") === "1";
if (panelMode) document.body.classList.add("panel-mode");
let current = null; // {page, key, cleanup}
let shell = null; // {frame, main, header, banners}

export function navigate(path, { replace = false } = {}) {
  if (panelMode && !path.includes("panel=1") && path.startsWith("/app/p/")) path += (path.includes("?") ? "&" : "?") + "panel=1";
  if (replace) history.replaceState(null, "", path); else history.pushState(null, "", path);
  route();
}
window.lintelNavigate = navigate;

async function loadMe() {
  try {
    app.me = await get("/api/me", { allow401: true });
  } catch (e) {
    if (e.status === 401) app.me = null; else throw e;
  }
  return app.me;
}
export const refreshMe = loadMe;

async function route() {
  const path = location.pathname;
  const match = ROUTES.map(([re, page, needsAuth, nav]) => ({ m: path.match(re), page, needsAuth, nav })).find((r) => r.m);
  if (!match) {
    if (path === "/" || path === "") return navigate("/app", { replace: true });
    return renderNotFound();
  }
  if (match.needsAuth) {
    if (!app.me) {
      try { await loadMe(); } catch (e) { return renderBootError(e); }
    }
    if (!app.me) return navigate(`/login?next=${encodeURIComponent(path + location.search)}`, { replace: true });
  } else if (match.page !== auth.invite && match.page !== auth.reset) {
    if (app.me === null) await loadMe().catch(() => null);
    if (app.me) return navigate(new URLSearchParams(location.search).get("next") || "/app", { replace: true });
  }
  const params = match.m.slice(1);
  const key = match.page.key ? match.page.key(params) : null;
  if (current && current.page === match.page && key !== null && current.key === key && match.page.update) {
    match.page.update(params);
    if (shell) markNav(match.nav);
    return;
  }
  current?.cleanup?.();
  current = null;
  let target;
  if (match.needsAuth) {
    ensureShell();
    markNav(match.nav);
    target = shell.main;
    clear(target);
    target.style.overflow = "";
    target.scrollTop = 0;
  } else {
    shell = null;
    target = root;
    clear(target);
  }
  const cleanup = await match.page.render(target, params);
  current = { page: match.page, key, cleanup };
  document.title = (match.page.title ? match.page.title(params) + " · " : "") + "Lintel";
}

function renderNotFound() {
  shell = null;
  clear(root, h("main", { class: "auth" }, h("div", { class: "auth-box" },
    h("span", { class: "label muted" }, "404"), h("h1", null, "Not on this sheet"),
    h("p", null, "That page doesn't exist."), h("a", { class: "btn", href: "/app", "data-link": "" }, "Go to projects →"))));
}

function renderBootError(e) {
  clear(root, h("main", { class: "auth" }, h("div", { class: "auth-box" },
    h("h1", null, "Can't reach Lintel"), h("p", null, e.message || "The server didn't answer."),
    h("button", { class: "btn", onclick: () => route() }, "Retry"))));
}

// ---- the app shell ---------------------------------------------------------
function ensureShell() {
  if (shell && root.contains(shell.frame)) { renderHeader(); renderBanners(); return; }
  const header = h("header", { class: "app-header" });
  const banners = h("div", { class: "banners" });
  const main = h("main", { class: "main", id: "main", tabindex: "-1" });
  const frame = h("div", { class: "frame" }, header, banners, main);
  clear(root, frame);
  shell = { frame, header, banners, main, nav: {} };
  renderHeader();
  renderBanners();
  refreshBadge();
}

function navCell(key, label, href, extra) {
  const a = h("a", { class: ["cell nav", key === "approvals" ? "" : "hide-narrow"], href, "data-link": "", dataset: { nav: key } }, label, extra);
  shell.nav[key] = a;
  return a;
}

function renderHeader() {
  const me = app.me;
  shell.nav = {};
  const firmCell = h("button", { class: "cell", "aria-haspopup": "true", "aria-expanded": "false" },
    me.firm.name, h("span", { "aria-hidden": "true" }, "▾"));
  const firmMenu = h("div", { class: "dropdown", role: "menu" },
    h("div", { class: "dd-title" }, "Switch firm"),
    me.firms.map((f) => h("button", {
      role: "menuitem", onclick: async (ev) => {
        ev.stopPropagation();
        if (f.id === me.firm.id) return closeMenus();
        try { await post("/api/me/firm", { firm_id: f.id }); await loadMe(); closeMenus(); shell = null; navigate("/app"); }
        catch (e) { toast(e.message, { error: true }); }
      },
    }, h("span", null, f.name), h("span", { class: "muted" }, f.id === me.firm.id ? "✓ " + f.role : f.role))));
  firmCell.append(firmMenu);
  const acctCell = h("button", { class: "cell", "aria-haspopup": "true", "aria-expanded": "false", "aria-label": "Account" },
    h("span", { class: "avatar" }, initials(me.user.name)));
  acctCell.append(h("div", { class: "dropdown", role: "menu" },
    h("div", { class: "dd-title" }, me.user.name + " · " + me.role),
    h("a", { href: "/app/settings/profile", "data-link": "", role: "menuitem" }, "Profile", h("span", null, "→")),
    h("a", { href: "/app/settings/plugins", "data-link": "", role: "menuitem" }, "Plugin tokens", h("span", null, "→")),
    h("button", { role: "menuitem", onclick: signOut }, "Sign out", h("span", null, "×"))));
  for (const cell of [firmCell, acctCell]) {
    cell.addEventListener("click", (ev) => {
      if (ev.target.closest(".dropdown")) return;
      const dd = cell.querySelector(".dropdown");
      const open = !dd.classList.contains("open");
      closeMenus();
      dd.classList.toggle("open", open);
      cell.setAttribute("aria-expanded", String(open));
    });
  }
  clear(shell.header,
    h("a", { class: "cell logo", href: "/app", "data-link": "", "aria-label": "Lintel home" }, logoMark(34), "LINTEL"),
    h("span", { class: "spacer" }),
    navCell("projects", "Projects", "/app"),
    navCell("approvals", "Approvals", "/app/approvals", h("span", { class: "badge", id: "approvals-badge" })),
    navCell("rules", "Rules", "/app/rules"),
    navCell("audit", "Audit", "/app/audit"),
    navCell("settings", "Settings", "/app/settings"),
    h("button", { class: "cell nav hide-narrow", onclick: openCommandBar, title: "Command bar (Ctrl K)", style: { width: "88px" } }, "⌘K"),
    firmCell, acctCell);
}

function closeMenus() {
  document.querySelectorAll(".dropdown.open").forEach((d) => {
    d.classList.remove("open");
    d.parentElement?.setAttribute("aria-expanded", "false");
  });
}
document.addEventListener("click", (e) => { if (!e.target.closest(".cell")) closeMenus(); });

function markNav(key) {
  for (const [k, a] of Object.entries(shell?.nav || {})) {
    a.classList.toggle("active", k === key);
    if (k === key) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
  }
}

let offlineBanner = null;
export function renderBanners() {
  if (!shell) return;
  const me = app.me;
  const out = [];
  if (offlineBanner) out.push(offlineBanner);
  const f = me.firm;
  if (f.trial_days_left !== null && f.trial_days_left !== undefined) {
    out.push(h("div", { class: "banner" }, h("span", { class: "grow" },
      f.trial_days_left > 0 ? `Pro trial · ${f.trial_days_left} day${f.trial_days_left === 1 ? "" : "s"} left`
        : "Your trial has ended. You're on the Free plan; your projects and rules are kept."),
      app.can("owner") && h("a", { class: "btn ghost compact", href: "/app/settings/billing", "data-link": "" }, "See plans →")));
  }
  const used = me.usage?.chat_messages || 0, cap = me.usage?.chat_cap || 0;
  if (app.can("admin") && cap && used >= cap * (me.usage?.warn_at || 0.8)) {
    out.push(h("div", { class: "banner accent" }, h("span", { class: "grow" },
      used >= cap ? `Assistant messages used up for this month (${used} of ${cap}). Chat resumes next month, or add more.`
        : `Assistant messages: ${used} of ${cap} used this month.`),
      f.plan !== "free" && h("a", { class: "btn ghost compact", href: "/app/settings/billing", "data-link": "" }, "Add 500 messages →")));
  }
  clear(shell.banners, out);
}

onNet("offline", () => {
  offlineBanner = h("div", { class: "banner ink", role: "alert" }, h("span", { class: "grow" }, "Can't reach Lintel. Retrying…"));
  renderBanners();
  retryLoop(1000);
});
onNet("online", () => { offlineBanner = null; renderBanners(); });
let retrying = false;
async function retryLoop(wait) {
  if (retrying) return;
  retrying = true;
  while (offlineBanner) {
    await new Promise((r) => setTimeout(r, wait));
    try { await get("/api/health"); } catch { wait = Math.min(wait * 2, 30000); }
  }
  retrying = false;
}

export async function refreshBadge() {
  if (!app.me) return;
  try {
    const d = await get("/api/approvals");
    const b = document.getElementById("approvals-badge");
    if (b) b.textContent = d.changesets.length ? String(d.changesets.length) : "";
    shell?.nav.approvals?.classList.toggle("cta", d.changesets.length > 0);
  } catch { /* the banner covers network errors */ }
}
setInterval(() => { if (shell && document.visibilityState === "visible") refreshBadge(); }, 15000);

async function signOut() {
  try { await post("/api/auth/logout"); } catch { /* signed out either way */ }
  app.me = null;
  shell = null;
  navigate("/login");
}

window.addEventListener("lintel:signed-out", () => {
  if (!app.me) return;
  app.me = null;
  shell = null;
  toast("Your session ended. Please sign in again.", { kind: "Signed out" });
  navigate(`/login?next=${encodeURIComponent(location.pathname)}`, { replace: true });
});

// ---- command bar (Ctrl/⌘ K) -------------------------------------------------
async function openCommandBar() {
  if (!app.me || document.querySelector(".cmdk")) return;
  const items = [
    { label: "Projects", hint: "page", go: "/app" },
    { label: "Approvals", hint: "page", go: "/app/approvals" },
    { label: "Rules", hint: "page", go: "/app/rules" },
    { label: "Audit log", hint: "page", go: "/app/audit" },
    ...["profile", "firm", "members", "plugins", "billing"].map((s) => ({ label: `Settings › ${s[0].toUpperCase() + s.slice(1)}`, hint: "setting", go: `/app/settings/${s}` })),
  ];
  const input = h("input", { class: "input", placeholder: "Jump to a project, rule or setting…", "aria-label": "Search" });
  const list = h("div", { class: "cmdk-list", role: "listbox" });
  let on = 0, shown = items;
  const d = dialog({ title: "Go to", className: "cmdk", body: [input, list] });
  d.body.style.padding = "0";
  const draw = () => {
    const q = input.value.trim().toLowerCase();
    shown = items.filter((i) => !q || i.label.toLowerCase().includes(q)).slice(0, 30);
    on = Math.min(on, Math.max(0, shown.length - 1));
    clear(list, shown.length ? shown.map((i, n) => h("div", {
      class: ["cmdk-item", n === on && "on"], role: "option", "aria-selected": String(n === on),
      onclick: () => { d.close(); navigate(i.go); }, onmousemove: () => { if (on !== n) { on = n; draw(); } },
    }, h("span", null, i.label), h("span", { class: "micro" }, i.hint))) : h("div", { class: "cmdk-item" }, h("span", { class: "muted" }, "Nothing matches")));
  };
  input.addEventListener("input", () => { on = 0; draw(); });
  input.addEventListener("keydown", (e) => {
    if (e.key === "ArrowDown") { on = Math.min(on + 1, shown.length - 1); draw(); e.preventDefault(); }
    if (e.key === "ArrowUp") { on = Math.max(on - 1, 0); draw(); e.preventDefault(); }
    if (e.key === "Enter" && shown[on]) { d.close(); navigate(shown[on].go); }
  });
  draw();
  try {
    const [ps, rs] = await Promise.all([get("/api/projects"), get("/api/rules")]);
    items.unshift(...ps.map((p) => ({ label: p.name, hint: `project · ${p.issues} issues`, go: `/app/p/${p.id}` })));
    items.push(...rs.map((r) => ({ label: r.name, hint: `rule · ${r.status}`, go: `/app/rules?rule=${encodeURIComponent(r.id)}` })));
    draw();
  } catch { /* pages stay listed */ }
}

// ---- global events ---------------------------------------------------------
document.addEventListener("click", (e) => {
  const a = e.target.closest("a[href]");
  if (!a || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || a.target || a.hasAttribute("download")) return;
  const url = new URL(a.href, location.href);
  if (url.origin !== location.origin || !/^\/(app|login|signup|reset|invite)(\/|$|\?)/.test(url.pathname + (url.search ? "?" : ""))) return;
  e.preventDefault();
  closeMenus();
  navigate(url.pathname + url.search);
});

window.addEventListener("popstate", route);

document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); openCommandBar(); return; }
  if (e.key === "Escape") { if (closeTop()) { e.preventDefault(); return; } closeMenus(); }
});

window.addEventListener("unhandledrejection", (e) => {
  if (e.reason instanceof ApiError) { e.preventDefault(); if (e.reason.status !== 401) toast(e.reason.message, { error: true }); }
});

// ---- drawing-sheet details -------------------------------------------------
// Buttons ending in "→" get the arrow in the accent colour, as on the Lintel site.
function arrows(root) {
  for (const btn of root.querySelectorAll ? root.querySelectorAll(".btn") : []) {
    for (const n of btn.childNodes) {
      if (n.nodeType === 3 && /\s→$/.test(n.nodeValue)) {
        n.nodeValue = n.nodeValue.replace(/→$/, "");
        n.after(h("span", { class: "arr", "aria-hidden": "true" }, "→"));
      }
    }
  }
}
new MutationObserver((muts) => {
  for (const m of muts) for (const n of m.addedNodes) if (n.nodeType === 1) arrows(n.matches?.(".btn") ? n.parentNode || n : n);
}).observe(document.body, { childList: true, subtree: true });

// a small accent dot trails the pointer; the real cursor is untouched
if (matchMedia("(pointer: fine)").matches && !matchMedia("(prefers-reduced-motion: reduce)").matches) {
  const dot = h("div", { class: "cursor-dot", "aria-hidden": "true" });
  document.body.append(dot);
  let tx = 0, ty = 0, x = 0, y = 0, raf = 0;
  const step = () => {
    x += (tx - x) * 0.22; y += (ty - y) * 0.22;
    dot.style.transform = `translate(${x + 14}px, ${y + 14}px)`;
    raf = Math.abs(tx - x) + Math.abs(ty - y) > 0.3 ? requestAnimationFrame(step) : 0;
  };
  window.addEventListener("pointermove", (e) => {
    tx = e.clientX; ty = e.clientY;
    dot.classList.toggle("on", !e.target.closest?.("svg.plan"));
    if (!raf) raf = requestAnimationFrame(step);
  });
  document.addEventListener("pointerleave", () => dot.classList.remove("on"));
}

route();
