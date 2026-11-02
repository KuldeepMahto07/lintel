// Project workspace: issues · plan canvas · inspector, with tabs for Approvals, History, Model and Chat.
import { $, $$, act, ago, api, app, chip, clear, copy, del, drawer, empty, get, h, loadError, measure, num, post, put, toast, titleCase } from "../lib.js";
import { approve, changesetCard, compactRow, fmtValue, reject } from "../changeset.js";
import { createPlan } from "../plan.js";
import { navigate, refreshBadge } from "../main.js";

const TABS = [["issues", "Issues"], ["approvals", "Approvals"], ["history", "History"], ["model", "Model"], ["chat", "Chat"]];
let ws = null; // the open workspace

export const key = ([id]) => id;
export const title = () => ws?.data?.project?.name || "Project";

export async function render(root, [id, tab = "issues"]) {
  ws = new Workspace(root, id);
  await ws.load(tab);
  return () => { ws?.destroy(); ws = null; };
}

export function update([, tab = "issues"]) {
  ws?.setTab(tab);
}

function issueMeasure(i) {
  const op = i.kind === "max" || i.kind === "egress" ? ">" : "<";
  if (i.kind === "egress") return [h("span", { class: "fail-val" }, `${num(i.actual / 1000, 1)} M`), ` ${op} ${num(i.required / 1000, 1)} M`];
  return [h("span", { class: "fail-val" }, measure(i.actual, i.unit)), ` ${op} ${measure(i.required, i.unit)}`];
}

const sig = (d) => JSON.stringify([d.snapshot_at, d.changesets.map((c) => [c.id, c.status, c.comment_count, c.approval_count]),
  d.issues.map((i) => i.id + (i.pending || "")), d.project.name, d.plugin_seen_at && Math.floor(d.plugin_seen_at / 60)]);

class Workspace {
  constructor(root, id) {
    this.root = root;
    this.id = id;
    this.tab = "issues";
    this.sel = null; // {type: issue|element|changeset|box, id|ids}
    this.filter = "";
    this.modelType = "room";
    this.chat = null;
    this.timer = null;
    this.onKey = (e) => this.key(e);
  }

  async load(tab) {
    clear(this.root, h("div", { class: "page" }, h("div", { class: "skel-grid" }, h("div", { class: "skeleton" }), h("div", { class: "skeleton" }), h("div", { class: "skeleton" }))));
    try {
      this.data = await get(`/api/projects/${encodeURIComponent(this.id)}`);
    } catch (e) {
      clear(this.root, h("div", { class: "page" }, loadError(e, () => this.load(tab))));
      return;
    }
    this.sigv = sig(this.data);
    document.title = `${this.data.project.name} · Lintel`;
    this.build();
    this.setTab(tab, true);
    window.addEventListener("keydown", this.onKey);
    this.timer = setInterval(() => this.poll(), 5000);
  }

  destroy() {
    clearInterval(this.timer);
    window.removeEventListener("keydown", this.onKey);
    this.plan?.destroy();
    this.chatAbort?.abort();
  }

  // ---- layout ----------------------------------------------------------------
  build() {
    this.head = h("div", { class: "ws-head" });
    this.notice = h("div", { style: { gridColumn: "1 / -1" } });
    this.left = h("section", { class: "col col-left", "aria-label": "List" });
    this.right = h("aside", { class: "col col-right", "aria-label": "Inspector" });
    this.plan = createPlan({
      onSelectElement: (eid) => this.select(eid ? { type: "element", id: eid } : null, { zoom: false }),
      onSelectIssue: (iid) => this.select({ type: "issue", id: iid }, { zoom: false }),
      onBoxSelect: (ids) => this.select(ids.length ? { type: "box", ids } : null, { zoom: false }),
    });
    this.wsEl = h("div", { class: "ws" }, this.head, this.notice, this.left, this.plan.el, this.right);
    this.wsEl.style.gridTemplateRows = "auto auto minmax(0, 1fr)";
    clear(this.root, this.wsEl);
    this.root.style.overflow = "hidden";
    this.renderHead();
    this.renderNotice();
    this.plan.setData(this.data.elements, this.data.issues);
    this.renderInspector();
  }

  renderHead() {
    const d = this.data;
    const awaiting = d.changesets.filter((c) => c.status === "proposed").length;
    const stale = d.snapshot_at && Date.now() / 1000 - d.snapshot_at > 86400;
    const tabs = h("nav", { class: "ws-tabs", "aria-label": "Project views" }, TABS.map(([k, label]) => h("a", {
      class: ["cell", k === this.tab && "active"], href: `/app/p/${d.project.id}${k === "issues" ? "" : "/" + k}`, "data-link": "", dataset: { tab: k },
      "aria-current": k === this.tab ? "page" : null,
    }, label, k === "approvals" && awaiting ? h("span", { class: "badge" }, String(awaiting)) : null, k === "issues" ? h("span", { class: "muted" }, `(${d.issues.length})`) : null)));
    clear(this.head,
      h("div", { class: "ws-title" },
        h("h2", { title: d.project.name }, d.project.name),
        h("span", { class: "chip" }, (d.host || d.project.host || "manual").toUpperCase()),
        h("span", { class: ["micro", stale ? "muted" : "ink2"] }, d.snapshot_at ? (stale ? `Model last synced ${ago(d.snapshot_at)}` : `Synced ${ago(d.snapshot_at)}`) : "Never synced"),
        app.can("admin") && h("button", { class: "btn ghost compact", onclick: () => this.overridesDrawer() }, "Project rules"),
        h("button", { class: "btn compact inspector-drawer-btn", onclick: () => this.right.classList.toggle("open") }, "Inspector"),
        h("button", { class: "btn compact show-plan-btn", style: { display: "none" }, onclick: () => this.wsEl.classList.toggle("show-plan") }, "Show plan")),
      tabs);
    if (matchMedia("(max-width: 760px)").matches) $(".show-plan-btn", this.head).style.display = "inline-flex";
  }

  renderNotice() {
    const d = this.data;
    const now = Date.now() / 1000;
    const waiting = d.changesets.some((c) => c.status === "approved" && now - c.updated_at > 120);
    const pluginQuiet = !d.plugin_seen_at || now - d.plugin_seen_at > 120;
    const sampleHost = (d.project.host || "") === "sample";
    clear(this.notice, waiting && pluginQuiet && !sampleHost
      ? h("div", { class: "banner accent", role: "status" }, h("span", { class: "grow" }, "No plugin connected. Approved changes will apply when Rhino reconnects."),
        h("a", { class: "btn ghost compact", href: "/app/settings/plugins", "data-link": "" }, "Plugin setup →"))
      : null);
  }

  setTab(tab, force) {
    if (!force && tab === this.tab) return;
    this.tab = tab;
    this.wsEl.classList.toggle("wide-left", tab === "chat" || tab === "model");
    $$(".ws-tabs .cell", this.head).forEach((c) => {
      c.classList.toggle("active", c.dataset.tab === tab);
      if (c.dataset.tab === tab) c.setAttribute("aria-current", "page"); else c.removeAttribute("aria-current");
    });
    if (this.sel?.type === "changeset" && tab === "issues") this.select(null);
    this.renderLeft();
    requestAnimationFrame(() => this.plan.zoomBy(1));
  }

  // ---- left column -----------------------------------------------------------
  renderLeft() {
    if (this.tab === "chat") return this.renderChat();
    this.chatAbort?.abort();
    const body = { issues: () => this.issuesList(), approvals: () => this.csList("proposed"), history: () => this.csList("history"), model: () => this.modelList() }[this.tab]();
    clear(this.left, body);
  }

  issuesList() {
    const d = this.data;
    const search = h("input", { class: "input", placeholder: "Filter issues  /", value: this.filter, "aria-label": "Filter issues", style: { height: "32px" },
      oninput: (e) => { this.filter = e.target.value; this.drawIssues(list); } });
    this.searchEl = search;
    const list = h("div", { class: "col-scroll" });
    this.drawIssues(list);
    return [h("div", { class: "col-head" }, h("span", { class: "label grow" }, `Issues (${d.issues.length})`)),
      h("div", { style: { padding: "8px 14px", borderBottom: "1px solid var(--line)" } }, search), list];
  }

  drawIssues(list) {
    const d = this.data;
    if (!d.snapshot_at) {
      clear(list, h("div", { style: { padding: "16px" } }, empty("No model yet",
        "Sync a model from Rhino to run checks. Create a plugin token, then run the Lintel plugin with this project ID.",
        h("div", { class: "btn-row" }, h("a", { class: "btn primary compact", href: "/app/settings/plugins", "data-link": "" }, "Connect Rhino →"),
          h("button", { class: "btn compact", onclick: () => copy(d.project.ext_key || d.project.id, "Project ID copied") }, "Copy project ID")))));
      return;
    }
    if (!d.issues.length) {
      clear(list, h("div", { style: { padding: "16px" } }, empty("All clear", "No issues against your active rules. Lintel re-checks on every sync.")));
      return;
    }
    const q = this.filter.trim().toLowerCase();
    const numbered = d.issues.map((i, n) => ({ i, n: n + 1 }))
      .filter(({ i }) => !q || [i.rule_name, i.element_name, i.ref, i.element].join(" ").toLowerCase().includes(q));
    const groups = [["error", "Errors"], ["warning", "Warnings"]].map(([sev, label]) => [label, numbered.filter(({ i }) => (i.severity === "warning" ? "warning" : "error") === sev)]);
    clear(list, groups.filter(([, items]) => items.length).map(([label, items]) => [
      h("div", { class: "group-label micro" }, h("span", null, label), h("span", null, String(items.length))),
      items.map(({ i, n }) => this.issueRow(i, n)),
    ]), numbered.length ? null : h("p", { class: "micro muted", style: { padding: "14px" } }, "Nothing matches the filter."));
  }

  issueRow(i, n) {
    const selected = this.sel?.type === "issue" && this.sel.id === i.id;
    let action;
    if (i.pending) action = h("a", { class: "chip proposed", href: `/app/p/${this.data.project.id}/approvals`, "data-link": "", onclick: (e) => e.stopPropagation() }, "Fix awaiting approval");
    else if (i.fixable && app.can("member")) {
      const b = h("button", { class: "btn compact primary" }, "Propose fix →");
      b.onclick = (e) => { e.stopPropagation(); this.proposeFix(i, b); };
      action = b;
    } else action = h("span", { class: "micro muted" }, i.fixable ? "Fix available" : "Advice only");
    return h("div", {
      class: ["issue-row", selected && "selected"], tabindex: "0", role: "button", dataset: { issue: i.id },
      "aria-label": `${n}. ${i.rule_name}, ${i.element_name}`,
      onclick: () => this.select({ type: "issue", id: i.id }),
      onkeydown: (e) => { if (e.key === "Enter") this.select({ type: "issue", id: i.id }); },
    },
    h("span", { class: ["marker", i.severity === "warning" && "warn"] }, String(n)),
    h("div", { class: "body" },
      h("span", { class: "name" }, i.rule_name),
      h("span", { class: "el" }, i.element_name),
      h("span", { class: "data" }, issueMeasure(i)),
      h("span", { class: "ref" }, i.ref),
      h("div", { class: "act" }, action, h("span", { class: "micro muted" }, i.overridden ? "project value" : ""))));
  }

  async proposeFix(i, btn) {
    const out = await act(btn, () => post(`/api/projects/${this.data.project.id}/issues/${encodeURIComponent(i.id)}/fix`), "Fix proposed. It's waiting for approval.");
    if (out) {
      await this.refresh();
      refreshBadge();
      this.select({ type: "changeset", id: out.changeset }, { zoom: false });
    }
  }

  csList(which) {
    const d = this.data;
    const items = which === "proposed" ? d.changesets.filter((c) => c.status === "proposed") : d.changesets.filter((c) => c.status !== "proposed");
    const head = h("div", { class: "col-head" }, h("span", { class: "label grow" }, which === "proposed" ? `Awaiting approval (${items.length})` : `History (${items.length})`));
    const list = h("div", { class: "col-scroll" }, items.length
      ? items.map((c) => compactRow(c, { selected: this.sel?.type === "changeset" && this.sel.id === c.id, onSelect: (cs) => this.select({ type: "changeset", id: cs.id }) }))
      : h("div", { style: { padding: "16px" } }, which === "proposed"
        ? empty("Nothing waiting", "Fixes you propose, and edits the assistant drafts, wait here until an approver decides.")
        : empty("No decisions yet", "Approved, rejected, applied and reverted change sets appear here, newest first.")));
    if (which === "proposed" && items.length && !this.sel) setTimeout(() => this.select({ type: "changeset", id: items[0].id }, { zoom: true }), 0);
    return [head, list];
  }

  modelList() {
    const d = this.data;
    const COLS = {
      room: [["name", "Name"], ["use", "Use"], ["area_m2", "Area m²"], ["travel", "Travel m"]],
      door: [["name", "Name"], ["clear_width_mm", "Width mm"], ["exit", "Exit"]],
      stair: [["name", "Name"], ["riser_mm", "Riser"], ["tread_mm", "Tread"], ["risers", "Risers"]],
      wall: [["length_mm", "Length mm"], ["thickness_mm", "Thick mm"]],
    };
    const flagged = new Set(d.issues.map((i) => i.element));
    const search = h("input", { class: "input", placeholder: "Search elements  /", "aria-label": "Search elements", style: { height: "32px" } });
    this.searchEl = search;
    const tableBox = h("div", { class: "col-scroll" });
    const counts = (t) => d.elements.filter((e) => e.type === t).length;
    const seg = h("div", { class: "seg" }, Object.keys(COLS).map((t) => h("button", {
      class: t === this.modelType && "on", onclick: () => { this.modelType = t; this.renderLeft(); },
    }, `${t}s ${counts(t)}`)));
    const sortState = { col: null, dir: 1 };
    const draw = () => {
      const q = search.value.trim().toLowerCase();
      let rows = d.elements.filter((e) => e.type === this.modelType)
        .map((e) => ({ e, v: { ...e.props, travel: d.egress[e.id] !== undefined ? d.egress[e.id] / 1000 : undefined } }))
        .filter(({ e }) => !q || JSON.stringify([e.id, e.props]).toLowerCase().includes(q));
      if (sortState.col) rows.sort((a, b) => (a.v[sortState.col] > b.v[sortState.col] ? 1 : -1) * sortState.dir);
      const cols = COLS[this.modelType];
      clear(tableBox, rows.length ? h("table", { class: "t compact" },
        h("thead", null, h("tr", null, h("th", null, "ID"), cols.map(([k, label]) => h("th", {
          class: !["name", "use"].includes(k) && "num", style: { cursor: "pointer" }, "aria-sort": sortState.col === k ? (sortState.dir > 0 ? "ascending" : "descending") : null,
          onclick: () => { sortState.dir = sortState.col === k ? -sortState.dir : 1; sortState.col = k; draw(); },
        }, label)))),
        h("tbody", null, rows.map(({ e, v }) => h("tr", {
          class: ["clickable", this.sel?.type === "element" && this.sel.id === e.id && "selected"],
          onclick: () => this.select({ type: "element", id: e.id }),
        }, h("td", { class: "mono" }, flagged.has(e.id) ? h("span", { class: "accent" }, "▣ ") : null, e.id),
        cols.map(([k]) => h("td", { class: !["name", "use"].includes(k) && "num" },
          typeof v[k] === "boolean" ? (v[k] ? "Yes" : "—") : typeof v[k] === "number" ? num(v[k], k === "travel" || k === "area_m2" ? 1 : 0) : (v[k] ?? "—")))))))
        : h("p", { class: "micro muted", style: { padding: "14px" } }, d.elements.length ? "Nothing matches." : "No model yet."));
    };
    search.addEventListener("input", draw);
    draw();
    return [h("div", { class: "col-head" }, h("span", { class: "label grow" }, `Model · ${d.elements.length} elements`)),
      h("div", { style: { padding: "8px 14px", borderBottom: "1px solid var(--line)", display: "grid", gap: "8px" } }, seg, search), tableBox];
  }

  // ---- chat ----------------------------------------------------------------
  async renderChat() {
    const log = h("div", { class: "chat-log", "aria-live": "polite" });
    const ta = h("textarea", { class: "textarea", rows: 1, placeholder: "Ask about your drawing…", "aria-label": "Message the assistant", maxlength: 4000 });
    const send = h("button", { class: "btn primary compact", type: "submit" }, "Send →");
    const form = h("form", { class: "chat-form" }, h("div", { style: { flex: 1 } }, ta), send);
    clear(this.left, h("div", { class: "col-head" }, h("span", { class: "label grow" }, "Assistant"), h("span", { class: "micro muted" }, "Proposes only. You approve.")),
      h("div", { class: "chat", style: { minHeight: 0, flex: 1 } }, log, app.can("member") ? form : h("p", { class: "micro muted", style: { padding: "12px 14px" } }, "Viewers can read the conversation but not chat.")));
    let state;
    try { state = await get(`/api/projects/${this.data.project.id}/chat`); }
    catch (e) { clear(log, loadError(e, () => this.renderChat())); return; }
    if (this.tab !== "chat") return;
    if (!state.configured) {
      clear(log, empty(state.chat_enabled ? "Chat isn't set up" : "Chat is off",
        state.chat_enabled ? "The assistant needs an Anthropic API key on the server (ANTHROPIC_API_KEY). Checks, fixes and approvals work without it."
          : "An admin switched chat off for this firm.",
        app.can("admin") && h("a", { class: "btn compact", href: "/app/settings/firm", "data-link": "" }, "Settings →")));
      form.remove();
      return;
    }
    const addMsg = (role, text) => {
      const m = h("div", { class: ["msg", role] }, h("span", { class: "who micro" }, role === "user" ? "You" : "The assistant"), renderText(text));
      log.append(m);
      log.scrollTop = log.scrollHeight;
      return m;
    };
    const addCs = (cs) => {
      if (!cs) return;
      const card = h("div", { class: "cs-card", style: { margin: 0 } },
        h("div", { class: "cs-head" }, h("span", { class: "title" }, cs.title), chip(cs.status)),
        h("div", { class: "cs-body" }, h("table", { class: "diff" }, h("tbody", null, cs.ops.map((o) => h("tr", null,
          h("td", null, o.element_name || o.element), h("td", { class: "before" }, fmtValue(o.prop, o.from)), h("td", { class: "arrow" }, "→"), h("td", { class: "after" }, fmtValue(o.prop, o.to)))))),
        h("button", { class: "btn compact", onclick: () => this.select({ type: "changeset", id: cs.id }) }, "Review →")));
      log.append(card);
      log.scrollTop = log.scrollHeight;
    };
    const addRule = (r) => {
      if (!r) return;
      log.append(h("div", { class: "notice" }, h("span", { class: "label" }, "Rule proposed · "), `${r.name}: ${r.kind === "max" ? "≤" : "≥"} ${measure(r.value, r.unit)}. `,
        h("a", { href: `/app/rules?rule=${encodeURIComponent(r.id)}`, "data-link": "" }, app.can("admin") ? "Review on the Rules page →" : "An admin can activate it on the Rules page.")));
    };
    for (const m of state.messages) {
      if (m.role === "changeset") addCs(m.changeset);
      else if (m.role === "rule") addRule(m.rule);
      else addMsg(m.role, m.text);
    }
    if (!state.messages.length) {
      log.append(h("div", { class: "suggest" }, h("span", { class: "label muted" }, "Try"),
        ["Which doors are under our minimum?", "Is stair 1 OK?", "Summarise open issues"].map((q) => h("button", { type: "button", onclick: () => { ta.value = q; form.requestSubmit(); } }, q))));
    }
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } });
    form.onsubmit = async (e) => {
      e.preventDefault();
      const text = ta.value.trim();
      if (!text || send.disabled) return;
      $(".suggest", log)?.remove();
      ta.value = "";
      addMsg("user", text);
      const typing = h("div", { class: "msg assistant" }, h("span", { class: "who micro" }, "The assistant"), h("span", { class: "typing micro muted" }, "Reading the model"));
      log.append(typing);
      send.disabled = true;
      this.chatAbort = new AbortController();
      try {
        const r = await fetch(`/api/projects/${this.data.project.id}/chat`, {
          method: "POST", credentials: "same-origin", signal: this.chatAbort.signal,
          headers: { "Content-Type": "application/json", "X-CSRF-Token": app.me.csrf }, body: JSON.stringify({ message: text }),
        });
        if (!r.ok) {
          const err = (await r.json().catch(() => ({}))).error || {};
          typing.remove();
          log.append(h("div", { class: "msg assistant error" }, err.message || "The assistant is unavailable."));
          return;
        }
        const reader = r.body.getReader(), dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let cut;
          while ((cut = buf.indexOf("\n\n")) >= 0) {
            const line = buf.slice(0, cut).trim();
            buf = buf.slice(cut + 2);
            if (!line.startsWith("data: ")) continue;
            const ev = JSON.parse(line.slice(6));
            if (ev.type === "text") { log.insertBefore(addMsg("assistant", ev.text), typing); }
            else if (ev.type === "changeset") { addCs(ev.changeset); log.append(typing); }
            else if (ev.type === "rule") { addRule(ev.rule); log.append(typing); }
            else if (ev.type === "error") log.append(h("div", { class: "msg assistant error" }, ev.message));
          }
        }
        typing.remove();
        await this.refresh();
        refreshBadge();
      } catch (err) {
        typing.remove();
        if (err.name !== "AbortError") log.append(h("div", { class: "msg assistant error" }, "Couldn't reach the assistant."));
      } finally {
        send.disabled = false;
        log.scrollTop = log.scrollHeight;
      }
    };
    ta.focus();
  }

  // ---- inspector -------------------------------------------------------------
  select(sel, { zoom = true } = {}) {
    this.sel = sel;
    const d = this.data;
    let elementId = null, issueId = null;
    if (sel?.type === "issue") { issueId = sel.id; elementId = d.issues.find((i) => i.id === sel.id)?.element; }
    if (sel?.type === "element") elementId = sel.id;
    if (sel?.type === "changeset") elementId = d.changesets.find((c) => c.id === sel.id)?.ops[0]?.element;
    this.plan.select(elementId, issueId);
    if (zoom && elementId) this.plan.zoomTo(elementId);
    $$("[data-issue].issue-row", this.left).forEach((r) => r.classList.toggle("selected", r.dataset.issue === issueId));
    $$("[data-cs].issue-row", this.left).forEach((r) => r.classList.toggle("selected", sel?.type === "changeset" && r.dataset.cs === sel.id));
    $$("tr.clickable", this.left).forEach((r) => r.classList.toggle("selected", sel?.type === "element" && r.firstChild?.textContent.replace("▣ ", "") === sel.id));
    $(`[data-issue="${CSS.escape(issueId || "")}"].issue-row`, this.left)?.scrollIntoView({ block: "nearest" });
    this.renderInspector();
    if (sel && matchMedia("(max-width: 1100px)").matches) this.right.classList.add("open");
  }

  renderInspector() {
    const d = this.data, sel = this.sel;
    const close = h("button", { class: "icon-btn", "aria-label": "Clear selection", onclick: () => { this.right.classList.remove("open"); this.select(null); } }, "×");
    const head = (label) => h("div", { class: "col-head" }, h("span", { class: "label grow" }, label), sel && close);
    if (!sel) {
      const awaiting = d.changesets.filter((c) => c.status === "proposed").length;
      const counts = ["room", "door", "stair", "wall"].map((t) => [t, d.elements.filter((e) => e.type === t).length]);
      clear(this.right, head("Inspector"), h("div", { class: "inspector" },
        h("div", { class: "sect" }, h("dl", { class: "kv" },
          h("dt", null, "Issues"), h("dd", null, String(d.issues.length)),
          h("dt", null, "Awaiting approval"), h("dd", null, String(awaiting)),
          counts.map(([t, n]) => [h("dt", null, t + "s"), h("dd", null, String(n))]),
          h("dt", null, "Project ID"), h("dd", null, h("button", { class: "btn ghost compact", onclick: () => copy(d.project.ext_key || d.project.id, "Project ID copied") }, d.project.ext_key || d.project.id)))),
        h("p", { class: "small muted" }, "Select an issue, an element on the plan, or a change set."),
        h("p", { class: "micro muted" }, "J / K next issue · F fit · drag to select · space+drag to pan · A approve · R reject")));
      return;
    }
    if (sel.type === "changeset") {
      const cs = d.changesets.find((c) => c.id === sel.id);
      if (!cs) { this.sel = null; return this.renderInspector(); }
      clear(this.right, head("Change set"), h("div", { class: "inspector" },
        changesetCard(cs, { needed: d.needed_approvals, onChange: () => this.refresh().then(refreshBadge) })));
      return;
    }
    if (sel.type === "box") {
      const ids = new Set(sel.ids);
      const inside = d.issues.map((i, n) => ({ i, n: n + 1 })).filter(({ i }) => ids.has(i.element));
      clear(this.right, head(`${sel.ids.length} elements selected`), h("div", { class: "inspector" },
        h("p", { class: "micro" }, `${inside.length} issue${inside.length === 1 ? "" : "s"} inside the box`),
        inside.length ? inside.map(({ i, n }) => this.issueRow(i, n)) : h("p", { class: "small muted" }, "No issues on these elements."),
        h("h3", { class: "h4", style: { margin: "20px 0 8px" } }, "Elements"),
        h("dl", { class: "kv" }, sel.ids.slice(0, 60).map((id) => {
          const e = d.elements.find((x) => x.id === id);
          return [h("dt", null, e?.type || ""), h("dd", null, h("button", { class: "btn ghost compact", onclick: () => this.select({ type: "element", id }) }, e?.props.name || id))];
        }))));
      return;
    }
    const issue = sel.type === "issue" ? d.issues.find((i) => i.id === sel.id) : null;
    const elId = issue ? issue.element : sel.id;
    const el = d.elements.find((e) => e.id === elId);
    if (!el) { this.sel = null; return this.renderInspector(); }
    const elIssues = d.issues.map((i, n) => ({ i, n: n + 1 })).filter(({ i }) => i.element === el.id);
    const props = Object.entries(el.props).filter(([k]) => k !== "rooms");
    clear(this.right, head(`${el.id} · ${el.props.name || el.type}`), h("div", { class: "inspector" },
      issue && h("div", { class: "sect" },
        h("h3", { style: { marginBottom: "8px" } }, issue.rule_name),
        h("dl", { class: "kv" },
          h("dt", null, "Measured"), h("dd", { class: "accent" }, issue.kind === "egress" ? `${num(issue.actual / 1000, 1)} M` : measure(issue.actual, issue.unit)),
          h("dt", null, issue.kind === "min" ? "Required" : "Allowed"), h("dd", null, `${issue.kind === "min" ? "≥" : "≤"} ${issue.kind === "egress" ? num(issue.required / 1000, 1) + " M" : measure(issue.required, issue.unit)}`),
          h("dt", null, "Rule"), h("dd", null, issue.rule_name),
          h("dt", null, "Ref"), h("dd", null, issue.ref || "—")),
        h("p", { class: "ref", style: { marginTop: "8px" } }, "Verify against your adopted edition and local amendments."),
        h("p", { class: "small" }, issue.message),
        issue.pending ? h("button", { class: "btn compact", onclick: () => this.select({ type: "changeset", id: issue.pending }) }, "View the open fix →")
          : issue.fixable && app.can("member") ? (() => { const b = h("button", { class: "btn primary" }, "Propose fix →"); b.onclick = () => this.proposeFix(issue, b); return b; })()
            : h("p", { class: "micro muted" }, issue.fixable ? "Members can propose this fix." : "Advice only: this needs a design decision, so Lintel won't guess a geometry change.")),
      h("div", { class: "sect" },
        h("span", { class: "label muted" }, el.type),
        h("dl", { class: "kv" }, h("dt", null, "ID"), h("dd", null, el.id),
          props.map(([k, v]) => [h("dt", null, titleCase(k)), h("dd", null, typeof v === "boolean" ? (v ? "Yes" : "No") : fmtValue(k, v))]),
          d.egress[el.id] !== undefined && [h("dt", null, "Travel to exit"), h("dd", null, `${num(d.egress[el.id] / 1000, 1)} M`)])),
      !issue && elIssues.length > 0 && h("div", { class: "sect" }, h("span", { class: "label muted" }, `Issues (${elIssues.length})`),
        elIssues.map(({ i, n }) => this.issueRow(i, n)))));
  }

  // ---- project rule overrides ---------------------------------------------------
  async overridesDrawer() {
    const d = this.data;
    const dr = drawer({ title: `Rules for ${d.project.name}`, body: h("p", { class: "micro muted" }, "Loading…") });
    let rules;
    try { rules = (await get("/api/rules")).filter((r) => r.status === "active"); }
    catch (e) { clear(dr.body, loadError(e, () => { dr.close(); this.overridesDrawer(); })); return; }
    const ov = () => this.data.overrides || {};
    const draw = () => clear(dr.body,
      h("p", { class: "small muted" }, "Change a value for this project only (e.g. a sprinklered building allows a longer travel distance), or switch a rule off here. Firm rules stay as they are."),
      !app.plan("overrides") && h("div", { class: "notice accent" }, "Per-project overrides need the Pro plan."),
      h("table", { class: "t compact" }, h("thead", null, h("tr", null, h("th", null, "Rule"), h("th", { class: "num" }, "Firm"), h("th", null, "This project"), h("th", null, "On"), h("th", null, ""))),
        h("tbody", null, rules.map((r) => {
          const o = ov()[r.id];
          const shown = r.kind === "egress" ? 1000 : 1;
          const val = h("input", { class: "input", style: { height: "32px", width: "90px" }, inputmode: "decimal", value: o?.value != null ? o.value / shown : "", placeholder: num(r.value / shown, r.kind === "egress" ? 1 : 0), "aria-label": `Override for ${r.name}` });
          const on = h("input", { type: "checkbox", checked: o ? o.enabled : true, "aria-label": `${r.name} on for this project` });
          const save = h("button", { class: "btn compact" }, "Save");
          save.onclick = () => act(save, async () => {
            const out = await put(`/api/projects/${d.project.id}/rules/${encodeURIComponent(r.id)}`, { value: val.value === "" ? null : Number(val.value) * shown, enabled: on.checked });
            this.data.overrides = out.overrides;
            await this.refresh(); draw();
          }, "Override saved. Checks updated.");
          const reset = o && h("button", { class: "btn ghost compact", onclick: async () => {
            await act(null, async () => { const out = await del(`/api/projects/${d.project.id}/rules/${encodeURIComponent(r.id)}`); this.data.overrides = out.overrides; await this.refresh(); draw(); }, "Back to the firm value.");
          } }, "Reset");
          return h("tr", null, h("td", null, r.name, h("div", { class: "micro muted" }, r.kind === "egress" ? "metres" : r.unit)),
            h("td", { class: "num" }, num(r.value / shown, r.kind === "egress" ? 1 : 0)), h("td", null, val), h("td", null, h("label", { class: "check" }, on)), h("td", null, h("div", { class: "btn-row" }, save, reset)));
        }))));
    draw();
  }

  // ---- data refresh and keys -----------------------------------------------------
  async refresh() {
    try {
      const d = await get(`/api/projects/${encodeURIComponent(this.id)}`);
      this.apply(d, true);
    } catch { /* the offline banner covers it */ }
  }

  async poll() {
    if (document.visibilityState !== "visible") return;
    try {
      const d = await get(`/api/projects/${encodeURIComponent(this.id)}`);
      this.apply(d, false);
    } catch { /* keep the last good data */ }
  }

  apply(d, force) {
    const s = sig(d);
    if (!force && s === this.sigv) return;
    const changed = s !== this.sigv;
    this.sigv = s;
    this.data = d;
    this.renderHead();
    this.renderNotice();
    this.plan.setData(d.elements, d.issues);
    if (this.sel?.type === "issue" && !d.issues.find((i) => i.id === this.sel.id)) this.sel = null;
    this.plan.select(...this.selectedIds());
    if (this.tab !== "chat") {
      const scroll = $(".col-scroll", this.left)?.scrollTop;
      this.renderLeft();
      const sc = $(".col-scroll", this.left);
      if (sc && scroll) sc.scrollTop = scroll;
    }
    const typing = this.right.contains(document.activeElement) && /textarea|input/i.test(document.activeElement.tagName);
    if (!typing) this.renderInspector();
    if (changed && !force) refreshBadge();
  }

  selectedIds() {
    const s = this.sel, d = this.data;
    if (s?.type === "issue") return [d.issues.find((i) => i.id === s.id)?.element, s.id];
    if (s?.type === "element") return [s.id, null];
    return [null, null];
  }

  key(e) {
    if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".drawer.open, .dialog.open")) return;
    const typing = /input|textarea|select/i.test(e.target.tagName);
    if (e.key === "Escape" && !typing && this.sel) { this.select(null); return; }
    if (typing) return;
    const k = e.key.toLowerCase();
    if (k === "j" || k === "k") {
      e.preventDefault();
      const list = this.tab === "approvals" || this.tab === "history"
        ? this.data.changesets.filter((c) => (this.tab === "approvals") === (c.status === "proposed")).map((c) => ({ type: "changeset", id: c.id }))
        : this.data.issues.map((i) => ({ type: "issue", id: i.id }));
      if (!list.length) return;
      const at = list.findIndex((x) => x.type === this.sel?.type && x.id === this.sel?.id);
      const next = at < 0 ? 0 : (at + (k === "j" ? 1 : -1) + list.length) % list.length;
      this.select(list[next]);
      $(`[data-${list[next].type === "issue" ? "issue" : "cs"}="${CSS.escape(list[next].id)}"]`, this.left)?.focus();
    } else if (k === "f") { e.preventDefault(); this.plan.fit(true); }
    else if (e.key === "+" || e.key === "=") this.plan.zoomBy(0.75);
    else if (e.key === "-") this.plan.zoomBy(1 / 0.75);
    else if (e.key === "/") { e.preventDefault(); this.searchEl?.isConnected && this.searchEl.focus(); }
    else if ((k === "a" || k === "r") && this.sel?.type === "changeset" && app.can("approver")) {
      const cs = this.data.changesets.find((c) => c.id === this.sel.id);
      if (cs?.status !== "proposed") return;
      e.preventDefault();
      const after = () => this.refresh().then(refreshBadge);
      (k === "a" ? approve(cs, after) : reject(cs, after)).catch((err) => toast(err.message, { error: true }));
    }
  }
}

// assistant text with rule references shown as chips
function renderText(text) {
  const out = [];
  const re = /((?:IBC|IRC|IFC|ADA|NFPA|Firm standard)[^\n,.;)]{0,3}(?:Table\s)?§?\s?\d[\d.]*|§\s?\d[\d.]*)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    out.push(text.slice(last, m.index), h("span", { class: "chip ref-chip" }, m[0]));
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return h("span", null, out);
}
