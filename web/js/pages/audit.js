// Audit log: when · project · who · action · target · detail, with filters, paging and CSV export.
import { act, app, clear, download, empty, get, h, loadError, skeleton, upgradePrompt, when } from "../lib.js";

export const title = () => "Audit";

const ACTIONS = [["", "All actions"], ["changeset", "Change sets"], ["changeset.approved", "Approvals"], ["changeset.applied", "Applied"],
  ["changeset.failed", "Failed"], ["model.snapshot", "Model syncs"], ["rule", "Rules"], ["member", "Members"], ["auth", "Sign-ins"],
  ["token", "Plugin tokens"], ["chat", "Chat"], ["project", "Projects"], ["firm", "Firm"]];

export async function render(root) {
  const page = h("div", { class: "page" });
  root.append(page);
  let projects = [], members = [];
  try { [projects, members] = await Promise.all([get("/api/projects"), get("/api/members").then((m) => m.members)]); }
  catch { /* filters fall back to free text */ }
  const f = { project: "", actor: "", action: "", since: "", until: "" };
  const sel = (key, opts, label) => h("div", { class: "field" }, h("label", { class: "flabel", for: `af-${key}` }, label),
    h("select", { class: "select", id: `af-${key}`, onchange: (e) => { f[key] = e.target.value; load(); } }, opts.map(([v, l]) => h("option", { value: v }, l))));
  const date = (key, label) => h("div", { class: "field" }, h("label", { class: "flabel", for: `af-${key}` }, label),
    h("input", { class: "input", type: "date", id: `af-${key}`, onchange: (e) => { f[key] = e.target.value; load(); } }));
  const exportBtn = app.can("admin") && h("button", { class: "btn", onclick: () => act(exportBtn, async () => {
    try { await download(`/api/audit.csv?${qs()}`, "lintel-audit.csv"); }
    catch (e) { if (e.code === "plan_limit") upgradePrompt(e); else throw e; }
  }) }, "Export CSV");
  const table = h("div");
  clear(page,
    h("div", { class: "page-head" }, h("h1", null, "Audit log"), h("span", { class: "spacer", style: { flex: 1 } }), exportBtn,
      h("p", { class: "sub small muted", style: { margin: 0 } }, "Every sync, proposal, decision, apply, revert, rule change, invite and sign-in. Kept for the life of the firm.")),
    h("div", { class: "filters" },
      sel("project", [["", "All projects"], ...projects.map((p) => [p.id, p.name])], "Project"),
      sel("actor", [["", "Everyone"], ...members.map((m) => [m.id, m.name]), ["agent", "The assistant"]], "Who"),
      sel("action", ACTIONS, "Action"),
      date("since", "From"), date("until", "To")),
    table);

  function qs(cursor) {
    const p = new URLSearchParams();
    if (f.project) p.set("project", f.project);
    if (f.actor) p.set("actor", f.actor);
    if (f.action) p.set("action", f.action);
    if (f.since) p.set("since", String(new Date(f.since + "T00:00").getTime() / 1000));
    if (f.until) p.set("until", String(new Date(f.until + "T00:00").getTime() / 1000 + 86400));
    if (cursor) p.set("cursor", cursor);
    return p.toString();
  }

  async function load() {
    clear(table, skeleton(1, "skel-list"));
    let d;
    try { d = await get(`/api/audit?${qs()}`); }
    catch (e) { clear(table, loadError(e, load)); return; }
    if (!d.entries.length) return clear(table, empty("Nothing logged", "No entries match these filters."));
    const tbody = h("tbody");
    const more = h("button", { class: "btn", style: { marginTop: "16px" } }, "Load more");
    const add = (rows) => tbody.append(...rows.map(row));
    add(d.entries);
    let next = d.next;
    more.hidden = !next;
    more.onclick = () => act(more, async () => {
      const n = await get(`/api/audit?${qs(next)}`);
      add(n.entries);
      next = n.next;
      more.hidden = !next;
    });
    clear(table, h("div", { class: "table-wrap" }, h("table", { class: "t" },
      h("thead", null, h("tr", null, ["When", "Project", "Who", "Action", "Target", "Detail"].map((c) => h("th", null, c)))), tbody)), more);
  }
  await load();
}

function row(a) {
  const detail = Object.entries(a.detail || {}).filter(([k]) => k !== "ops").map(([k, v]) => `${k}: ${typeof v === "object" ? JSON.stringify(v) : v}`).join(" · ");
  return h("tr", null,
    h("td", { class: "mono", style: { whiteSpace: "nowrap" } }, when(a.at)),
    h("td", null, a.project_name || h("span", { class: "muted" }, "—")),
    h("td", null, a.actor_name || a.actor),
    h("td", { class: "mono" }, a.action),
    h("td", { class: "mono micro" }, a.target || ""),
    h("td", { class: "small muted", style: { maxWidth: "420px", overflowWrap: "anywhere" } }, detail.slice(0, 300)));
}
