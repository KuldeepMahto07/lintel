// Lintel dashboard. Hash routes: #/projects, #/project/<id>/<tab>, #/rules, #/audit.
// ?panel=<project> renders the compact column shown inside the CAD app.
const $ = (s, el = document) => el.querySelector(s);
const view = $("#view");
const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const when = (t) => (t ? new Date(t * 1000).toLocaleString() : "never");
const fmt = (v) => (typeof v === "number" ? +v.toFixed(1) : v);
const actorInput = $("#actor");
actorInput.value = localStorage.lintelActor || "you";
actorInput.onchange = () => (localStorage.lintelActor = actorInput.value.trim() || "you");
const actor = () => localStorage.lintelActor || "you";
const panelProject = new URLSearchParams(location.search).get("panel");
if (panelProject) document.body.classList.add("panel");

async function api(path, opts = {}) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json", "X-Actor": actor() }, ...opts });
  const body = r.headers.get("content-type")?.includes("json") ? await r.json() : await r.text();
  if (!r.ok) throw new Error(body.detail || body || r.statusText);
  return body;
}
const post = (path, data = {}) => api(path, { method: "POST", body: JSON.stringify({ actor: actor(), ...data }) });

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast.h);
  toast.h = setTimeout(() => t.classList.remove("show"), 3500);
}
async function act(fn, ok) {
  try { await fn(); if (ok) toast(ok); route(); } catch (e) { toast(e.message); }
}

// ---- routing ---------------------------------------------------------------
async function route() {
  const [, page = "projects", id, tab = "issues"] = (location.hash || "#/projects").split("/");
  document.querySelectorAll("#nav a").forEach((a) => a.classList.toggle("on", a.dataset.nav === (page === "project" ? "projects" : page)));
  try {
    if (panelProject) return await renderPanel(panelProject);
    if (page === "project") return await renderProject(decodeURIComponent(id), tab);
    if (page === "rules") return await renderRules();
    if (page === "audit") return await renderAudit();
    return await renderProjects();
  } catch (e) {
    view.innerHTML = `<div class="card">Couldn't load: ${esc(e.message)}</div>`;
  }
}
window.addEventListener("hashchange", route);

// ---- projects --------------------------------------------------------------
async function renderProjects() {
  const ps = await api("/api/projects");
  view.innerHTML = `<h1>Projects</h1><div class="sub">Every model a Lintel plugin has sent. Open one to see issues, approvals and history.</div>
  ${ps.length ? `<div class="grid">${ps.map((p) => `
    <a class="card" href="#/project/${encodeURIComponent(p.id)}">
      <strong>${esc(p.name)}</strong> ${p.pending ? `<span class="pill proposed">${p.pending} awaiting approval</span>` : ""}
      <div class="muted">${esc(p.host || "no host")} · ${p.element_count} elements · synced ${when(p.snapshot_at)}</div>
    </a>`).join("")}</div>`
    : `<div class="card empty">No projects yet. Open a model in Rhino and run <code>Lintel</code>, or run the fixture host:<br><code>python hosts/fixture_host.py samples/clinic.json</code></div>`}`;
}

async function renderProject(pid, tab) {
  const d = await api(`/api/projects/${encodeURIComponent(pid)}`);
  const pending = d.changesets.filter((c) => c.status === "proposed");
  const tabs = [["issues", `Issues (${d.issues.length})`], ["approvals", `Approvals (${pending.length})`], ["history", "History"], ["model", "Model"], ["chat", "Chat"]];
  view.innerHTML = `<h1>${esc(d.project.name)}</h1>
    <div class="sub">${esc(d.host || "no host")} · ${d.elements.length} elements · last sync ${when(d.snapshot_at)}</div>
    <nav class="tabs">${tabs.map(([k, l]) => `<a href="#/project/${encodeURIComponent(pid)}/${k}" class="${k === tab ? "on" : ""}">${l}</a>`).join("")}</nav>
    <div id="tab"></div>`;
  const el = $("#tab");
  if (tab === "issues") renderIssues(el, d);
  else if (tab === "approvals") renderChangesets(el, pending, "Nothing waiting. Fixes you request, and edits the assistant proposes, appear here for approval.");
  else if (tab === "history") renderChangesets(el, d.changesets.filter((c) => c.status !== "proposed"), "No decisions yet.");
  else if (tab === "model") renderModel(el, d);
  else renderChat(el, pid);
}

function renderIssues(el, d, compact = false) {
  const bad = new Set(d.issues.map((i) => i.element));
  el.innerHTML = `<div class="split">
    <div>${d.issues.length ? d.issues.map((i) => `
      <div class="card issue" data-el="${esc(i.element)}">
        <span class="pill ${esc(i.severity)}">${esc(i.severity)}</span>
        <div class="body"><strong>${esc(i.rule_name)}</strong> · ${esc(i.element_name)}
          <div>${esc(i.message)}</div><div class="ref">${esc(i.ref)}</div></div>
        ${i.pending ? `<span class="pill proposed">fix awaiting approval</span>` : i.fixable ? `<button class="primary" data-fix="${esc(i.id)}">Propose fix</button>` : `<span class="muted" title="Needs a design decision">Advice only</span>`}
      </div>`).join("") : `<div class="card empty">No issues against the active rules.</div>`}</div>
    ${compact ? "" : `<div>${planSvg(d.elements, bad)}<div class="muted">Click an issue to highlight it. Red: elements with issues; green door: exit.</div></div>`}
  </div>`;
  el.querySelectorAll("[data-fix]").forEach((b) => b.onclick = (e) => {
    e.stopPropagation();
    act(() => post(`/api/projects/${encodeURIComponent(d.project.id)}/issues/${encodeURIComponent(b.dataset.fix)}/fix`),
      "Fix proposed: review it under Approvals");
  });
  el.querySelectorAll(".issue").forEach((c) => c.onclick = () => {
    el.querySelectorAll(".issue").forEach((x) => x.classList.toggle("sel", x === c));
    el.querySelectorAll(".plan [data-id]").forEach((s) => s.classList.toggle("hl", s.dataset.id === c.dataset.el));
  });
}

function renderChangesets(el, list, empty) {
  el.innerHTML = list.length ? list.map((c) => `
    <div class="card">
      <div><span class="pill ${esc(c.status)}">${esc(c.status)}</span> <strong>${esc(c.title)}</strong>
        <span class="muted">· ${esc(c.source)} · ${when(c.created)}</span></div>
      <div class="muted" style="margin:4px 0 8px">${esc(c.reason)}</div>
      <table class="diff"><tr><th>Element</th><th>Property</th><th>Now</th><th>After</th></tr>
        ${c.ops.map((o) => `<tr><td>${esc(o.element_name || o.element)}</td><td>${esc(o.prop)}</td>
          <td class="from">${esc(fmt(o.from))}</td><td class="to">${esc(fmt(o.to))}</td></tr>`).join("")}</table>
      ${c.error ? `<div class="pill failed" style="margin-top:8px">${esc(c.error)}</div>` : ""}
      <div style="margin-top:10px;display:flex;gap:6px">
        ${c.status === "proposed" ? `<button class="primary" data-a="approve" data-id="${c.id}">Approve</button><button class="danger" data-a="reject" data-id="${c.id}">Reject</button>` : ""}
        ${c.status === "applied" && c.source !== "revert" ? `<button data-a="revert" data-id="${c.id}">Revert</button>` : ""}
        ${c.status === "approved" ? `<span class="muted">Approved; the host plugin applies it on its next sync.</span>` : ""}
      </div>
    </div>`).join("") : `<div class="card empty">${empty}</div>`;
  el.querySelectorAll("[data-a]").forEach((b) => b.onclick = () => act(() => post(`/api/changesets/${b.dataset.id}/${b.dataset.a}`),
    { approve: "Approved: the plugin will apply it", reject: "Rejected", revert: "Revert sent to the plugin" }[b.dataset.a]));
}

function renderModel(el, d) {
  const by = (t) => d.elements.filter((e) => e.type === t);
  const row = (e, cols) => `<tr><td>${esc(e.id)}</td>${cols.map((c) => `<td>${esc(fmt(e.props[c]))}</td>`).join("")}</tr>`;
  const table = (title, items, cols) => `<h2>${title} (${items.length})</h2><table><tr><th>id</th>${cols.map((c) => `<th>${c}</th>`).join("")}</tr>${items.map((e) => row(e, cols)).join("")}</table>`;
  const eg = d.egress || {};
  el.innerHTML = planSvg(d.elements, new Set(d.issues.map((i) => i.element))) +
    table("Rooms", by("room").map((r) => ({ ...r, props: { ...r.props, travel_m: eg[r.id] ? eg[r.id] / 1000 : "" } })), ["name", "use", "area_m2", "clear_width_mm", "travel_m"]) +
    table("Doors", by("door"), ["name", "clear_width_mm", "exit"]) +
    table("Stairs", by("stair"), ["name", "riser_mm", "tread_mm", "risers", "width_mm"]) +
    table("Walls", by("wall"), ["length_mm", "thickness_mm", "height_mm"]);
}

function planSvg(els, bad) {
  const pts = els.flatMap((e) => e.geom?.outline || (e.geom?.location ? [e.geom.location] : []));
  if (!pts.length) return "";
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const pad = 2000, x0 = Math.min(...xs) - pad, y0 = Math.min(...ys) - pad, w = Math.max(...xs) - x0 + pad, h = Math.max(...ys) - y0 + pad;
  const Y = (y) => y0 + h - (y - y0); // CAD y points up
  const rooms = els.filter((e) => e.type === "room" && e.geom?.outline).map((r) => {
    const o = r.geom.outline, cx = o.reduce((s, p) => s + p[0], 0) / o.length, cy = o.reduce((s, p) => s + p[1], 0) / o.length;
    return `<polygon data-id="${esc(r.id)}" class="room ${bad.has(r.id) ? "bad" : ""}" points="${o.map((p) => `${p[0]},${Y(p[1])}`).join(" ")}"><title>${esc(r.props.name)}</title></polygon>
      <text x="${cx}" y="${Y(cy)}" text-anchor="middle">${esc(r.props.name)}</text>`;
  }).join("");
  const marks = els.filter((e) => (e.type === "door" || e.type === "stair") && e.geom?.location).map((e) => {
    const [x, y] = e.geom.location, cls = `door ${bad.has(e.id) ? "bad" : ""} ${e.props.exit ? "exit" : ""}`;
    return e.type === "door" ? `<circle data-id="${esc(e.id)}" class="${cls}" cx="${x}" cy="${Y(y)}" r="450"><title>${esc(e.props.name)} ${esc(e.props.clear_width_mm)} mm</title></circle>`
      : `<rect data-id="${esc(e.id)}" class="${cls}" x="${x - 1200}" y="${Y(y) - 1200}" width="2400" height="2400"><title>${esc(e.props.name)}</title></rect>`;
  }).join("");
  return `<svg class="plan" viewBox="${x0} ${y0} ${w} ${h}" role="img" aria-label="Floor plan">${rooms}${marks}</svg>`;
}

// ---- chat ------------------------------------------------------------------
async function renderChat(el, pid) {
  const msgs = await api(`/api/projects/${encodeURIComponent(pid)}/chat`);
  el.innerHTML = `<div class="card"><div class="chat" id="msgs">${msgs.length ? msgs.map((m) => `<div class="msg ${m.role}">${esc(m.text)}</div>`).join("")
    : `<div class="muted">Ask about this model or tell Lintel what to change. Try: "Check the doors and fix anything below our minimum", or "We always use 900 mm doors".</div>`}</div>
    <form class="chatbox" id="chatform"><textarea id="chatin" placeholder="Ask about the model, or tell Lintel what to change…" aria-label="Message"></textarea><button class="primary">Send</button></form>
    <div class="muted" style="margin-top:6px">Lintel only proposes edits. Each one waits for your approval under Approvals.</div></div>`;
  const box = $("#msgs");
  box.scrollTop = box.scrollHeight;
  $("#chatin").onkeydown = (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); $("#chatform").requestSubmit(); } };
  $("#chatform").onsubmit = async (e) => {
    e.preventDefault();
    const text = $("#chatin").value.trim();
    if (!text) return;
    box.insertAdjacentHTML("beforeend", `<div class="msg user">${esc(text)}</div><div class="msg assistant muted" id="thinking">Reading the model…</div>`);
    box.scrollTop = box.scrollHeight;
    $("#chatin").value = "";
    try {
      const r = await post(`/api/projects/${encodeURIComponent(pid)}/chat`, { message: text });
      if (r.changesets.length) toast(`${r.changesets.length} change set(s) waiting for your approval`);
      if (r.rules.length) toast(`Rule proposed: activate it on the Firm rules page`);
    } catch (err) { toast(err.message); }
    route();
  };
}

// ---- host panel ------------------------------------------------------------
async function renderPanel(pid) {
  const d = await api(`/api/projects/${encodeURIComponent(pid)}`);
  const pending = d.changesets.filter((c) => c.status === "proposed");
  view.innerHTML = `<h1>Lintel</h1><div class="sub">${esc(d.project.name)} · synced ${when(d.snapshot_at)}</div>
    <h2>Waiting for approval (${pending.length})</h2><div id="p-app"></div>
    <h2>Assistant</h2><div id="p-chat"></div>
    <h2>Issues (${d.issues.length})</h2><div id="p-iss"></div>`;
  renderChangesets($("#p-app"), pending, "Nothing waiting.");
  renderIssues($("#p-iss"), d, true);
  await renderChat($("#p-chat"), pid);
}

// ---- rules -----------------------------------------------------------------
async function renderRules() {
  const rules = await api("/api/rules");
  const val = (r) => r.kind === "egress" ? `${fmt(r.value / 1000)} m travel` : `${r.kind === "min" ? "≥" : "≤"} ${fmt(r.value)} ${esc(r.unit || "")}`;
  const where = (r) => Object.entries(r.where || {}).map(([k, v]) => `${k}=${v}`).join(";");
  view.innerHTML = `<h1>Firm rules</h1>
  <div class="sub">Your standards and the code requirements you check against: a number, a scope and the section it comes from. Lintel stores no code text, so confirm each value against the edition your jurisdiction adopted.</div>
  <table><tr><th>Rule</th><th>Applies to</th><th>Requirement</th><th>Reference</th><th>Source</th><th>Status</th><th></th></tr>
  ${rules.map((r) => `<tr><td><strong>${esc(r.name)}</strong></td><td>${esc(r.applies_to)} ${where(r) ? `<span class="muted">(${esc(where(r))})</span>` : ""}</td>
    <td>${r.prop ? `<code>${esc(r.prop)}</code> ` : ""}${val(r)}${r.fixable ? ' <span class="pill">auto-fix</span>' : ""}</td>
    <td class="ref">${esc(r.ref)}</td><td>${esc(r.source)}</td><td><span class="pill ${esc(r.status)}">${esc(r.status)}</span></td>
    <td style="white-space:nowrap"><button data-edit="${esc(r.id)}">Edit</button>
      <button data-st="${r.status === "active" ? "disabled" : "active"}" data-id="${esc(r.id)}">${r.status === "active" ? "Disable" : "Activate"}</button>
      <button class="danger" data-del="${esc(r.id)}">Delete</button></td></tr>`).join("")}</table>
  <h2 id="formtitle">Add a rule</h2>
  <form class="card form" id="ruleform">
    <input type="hidden" name="id">
    <label class="wide">Name<input name="name" required placeholder="Corridor width (firm)"></label>
    <label>Check<select name="kind"><option value="min">minimum</option><option value="max">maximum</option><option value="egress">travel distance</option></select></label>
    <label>Applies to<select name="applies_to"><option>door</option><option>room</option><option>stair</option></select></label>
    <label>Property<input name="prop" placeholder="clear_width_mm"></label>
    <label>Value<input name="value" required type="number" step="any"></label>
    <label>Unit<input name="unit" placeholder="mm"></label>
    <label>Only where<input name="where" placeholder="use=corridor"></label>
    <label class="wide">Reference<input name="ref" required placeholder="Firm standard, or e.g. IBC §1020 (verify)"></label>
    <label>Severity<select name="severity"><option>error</option><option>warning</option></select></label>
    <label>One-click fix<select name="fixable"><option value="false">no (advice)</option><option value="true">yes</option></select></label>
    <div><button class="primary">Save rule</button> <button type="button" id="clearform">Clear</button></div>
  </form>
  <h2>Import or export</h2>
  <div class="card">
    <div class="muted">Paste a JSON list, or CSV with a header row: name,kind,applies_to,prop,value,unit,where,ref,severity,fixable</div>
    <textarea id="imp" rows="5" style="width:100%;margin:6px 0"></textarea>
    <input type="file" id="impfile" accept=".json,.csv"> <button class="primary" id="impbtn">Import</button>
    <a class="btn" href="/api/rules/export">Export JSON</a>
  </div>`;
  const form = $("#ruleform");
  view.querySelectorAll("[data-st]").forEach((b) => b.onclick = () => act(() => post(`/api/rules/${b.dataset.id}/status`, { status: b.dataset.st }), "Rule updated"));
  view.querySelectorAll("[data-del]").forEach((b) => b.onclick = () => confirm("Delete this rule?") &&
    act(() => api(`/api/rules/${b.dataset.del}?actor=${encodeURIComponent(actor())}`, { method: "DELETE" }), "Rule deleted"));
  view.querySelectorAll("[data-edit]").forEach((b) => b.onclick = () => {
    const r = rules.find((x) => x.id === b.dataset.edit);
    for (const [k, v] of Object.entries({ ...r, where: where(r), fixable: String(!!r.fixable) })) if (form.elements[k]) form.elements[k].value = v ?? "";
    $("#formtitle").textContent = `Edit: ${r.name}`;
    form.scrollIntoView({ behavior: "smooth" });
  });
  $("#clearform").onclick = () => { form.reset(); form.elements.id.value = ""; $("#formtitle").textContent = "Add a rule"; };
  form.onsubmit = (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    const existing = rules.find((x) => x.id === data.id);
    act(() => post("/api/rules", { ...data, status: existing?.status === "disabled" ? "disabled" : "active", source: existing?.source }), "Rule saved");
  };
  $("#impfile").onchange = async (e) => ($("#imp").value = await e.target.files[0].text());
  $("#impbtn").onclick = () => act(async () => {
    const r = await api("/api/rules/import", { method: "POST", body: $("#imp").value });
    toast(`Imported ${r.imported} rule(s)`);
  });
}

// ---- audit -----------------------------------------------------------------
async function renderAudit() {
  const rows = await api("/api/audit");
  view.innerHTML = `<h1>Audit log</h1><div class="sub">Every snapshot, proposal, approval, rejection, applied edit, revert and rule change, newest first.</div>
  <table><tr><th>When</th><th>Project</th><th>Who</th><th>Action</th><th>Target</th><th>Detail</th></tr>
  ${rows.map((r) => `<tr><td style="white-space:nowrap">${when(r.ts)}</td><td>${esc(r.project || "firm")}</td><td>${esc(r.actor)}</td>
    <td><code>${esc(r.action)}</code></td><td>${esc(r.target)}</td>
    <td class="muted">${esc(r.detail.title || r.detail.error || r.detail.text || r.detail.name || (Object.keys(r.detail).length ? JSON.stringify(r.detail).slice(0, 140) : ""))}</td></tr>`).join("")}</table>`;
}

route();
if (panelProject) setInterval(() => { if (!document.activeElement || document.activeElement.tagName !== "TEXTAREA") route(); }, 5000);
