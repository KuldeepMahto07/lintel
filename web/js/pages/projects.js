// Projects: grid of cells with sort/filter, a card menu, and the first-run onboarding checklist.
import { act, ago, app, clear, copy, drawer, empty, field, get, h, idx, loadError, patch, post, showErrors, skeleton } from "../lib.js";
import { navigate } from "../main.js";
import { elevation, planThumb } from "../art.js";

export const title = () => "Projects";
let state = { sort: localStorage.lintelSort || "synced", filter: "all" };

export async function render(root) {
  const page = h("div", { class: "page" });
  root.append(page);
  await load(page);
}

async function load(page) {
  clear(page, header(), skeleton(6));
  let projects, archived, extras;
  try {
    [projects, archived, extras] = await Promise.all([
      get("/api/projects"),
      get("/api/projects?archived=1"),
      checklistData(),
    ]);
  } catch (e) {
    clear(page, header(), loadError(e, () => load(page)));
    return;
  }
  const grid = h("div");
  const draw = () => {
    let list = state.filter === "archived" ? archived : projects;
    if (state.filter === "issues") list = list.filter((p) => p.issues > 0);
    if (state.filter === "awaiting") list = list.filter((p) => p.awaiting > 0);
    list = [...list].sort({
      synced: (a, b) => (b.snapshot_at || 0) - (a.snapshot_at || 0),
      name: (a, b) => a.name.localeCompare(b.name),
      issues: (a, b) => b.issues - a.issues,
    }[state.sort]);
    clear(grid, list.length ? h("div", { class: "grid-cells" }, list.map((p, n) => card(p, n + 1, () => load(page))))
      : (projects.length || state.filter === "archived")
        ? empty("Nothing here", state.filter === "archived" ? "No archived projects." : "No projects match this filter.")
        : h("div", { class: "art-band" }, elevation({ seed: 5 }), empty("No projects yet", "Connect Rhino or try the sample clinic.", h("div", { class: "btn-row" },
          app.can("member") && sampleButton(page), h("a", { class: "btn", href: "/app/settings/plugins", "data-link": "" }, "Connect Rhino →")))));
  };
  const controls = h("div", { class: "filters" },
    h("div", { class: "seg", role: "group", "aria-label": "Filter" }, [["all", "All"], ["issues", "Has issues"], ["awaiting", "Awaiting approval"], ["archived", `Archived ${archived.length || ""}`]]
      .map(([k, l]) => h("button", { class: state.filter === k && "on", "aria-pressed": String(state.filter === k), onclick: (e) => {
        state.filter = k;
        e.target.parentElement.querySelectorAll("button").forEach((b) => { b.classList.toggle("on", b === e.target); b.setAttribute("aria-pressed", String(b === e.target)); });
        draw();
      } }, l))),
    h("span", { class: "spacer", style: { flex: 1 } }),
    h("label", { class: "micro muted", for: "sort" }, "Sort"),
    h("select", { class: "select", id: "sort", style: { width: "180px", height: "32px" }, onchange: (e) => { state.sort = localStorage.lintelSort = e.target.value; draw(); } },
      [["synced", "Last synced"], ["name", "Name"], ["issues", "Most issues"]].map(([v, l]) => h("option", { value: v, selected: state.sort === v }, l))));
  clear(page, header(page), checklist(extras, projects, page), controls, grid);
  draw();
}

function header(page) {
  return h("div", { class: "page-head" },
    h("h1", null, "Projects"),
    h("span", { class: "spacer", style: { flex: 1 } }),
    page && app.can("member") && h("button", { class: "btn", onclick: () => newProject(page) }, "+ New project"),
    page && h("a", { class: "btn primary", href: "/app/settings/plugins", "data-link": "" }, "Connect Rhino →"));
}

function card(p, n, reload) {
  const menuBtn = h("button", { class: "icon-btn menu-btn", "aria-label": `Actions for ${p.name}`, "aria-haspopup": "true" }, "⋯");
  const menu = h("div", { class: "dropdown", role: "menu", style: { top: "44px", right: "8px" } },
    app.can("admin") && h("button", { role: "menuitem", onclick: (e) => { e.stopPropagation(); menu.classList.remove("open"); rename(p, reload); } }, "Rename"),
    app.can("admin") && h("button", { role: "menuitem", onclick: (e) => { e.stopPropagation(); menu.classList.remove("open");
      act(null, () => patch(`/api/projects/${p.id}`, { archived: !p.archived_at }), p.archived_at ? "Project restored." : "Project archived. Find it under Archived.").then(reload); } },
    p.archived_at ? "Restore" : "Archive"),
    h("button", { role: "menuitem", onclick: (e) => { e.stopPropagation(); menu.classList.remove("open"); copy(p.ext_key || p.id, "Project ID copied for the plugin"); } }, "Copy project ID"));
  menuBtn.onclick = (e) => {
    e.preventDefault(); e.stopPropagation();
    document.querySelectorAll(".dropdown.open").forEach((d) => d !== menu && d.classList.remove("open"));
    menu.classList.toggle("open");
  };
  const host = (p.host || "manual").toUpperCase();
  return h("div", { class: "card project-card" },
    h("a", { class: "card-link", href: `/app/p/${p.id}`, "data-link": "", style: { display: "contents" } },
      h("div", { class: "card-top" }, h("span", { class: "label" }, host), h("span", { class: "micro muted", style: { marginRight: "34px" } }, idx(n))),
      h("div", { class: "drawing" }, planThumb(p.thumb?.rooms || [], p.thumb?.flagged || [])),
      h("div", { class: "name-row" }, h("h3", null, p.name),
        h("span", { class: "sq", title: p.issues ? `${p.issues} issues` : "No issues" }, h("span", { class: p.issues && "hot" }))),
      h("div", { class: "meta" },
        h("span", { class: ["micro", p.issues ? "accent" : "muted"] }, p.issues ? `▣ ${p.issues} issue${p.issues === 1 ? "" : "s"}` : p.snapshot_at ? "0 issues" : "—"),
        h("span", { class: "micro" }, p.awaiting ? `${p.awaiting} awaiting` : "—"),
        h("span", { class: "micro muted full" }, p.snapshot_at ? `Synced ${ago(p.snapshot_at)}` : "Never synced"))),
    menuBtn, menu);
}

function rename(p, reload) {
  const input = h("input", { class: "input", name: "name", value: p.name, maxlength: 120 });
  const form = h("form", null, field("Project name", input));
  const d = drawer({
    title: "Rename project", body: form,
    foot: (close) => [h("button", { class: "btn", onclick: close }, "Cancel"), h("button", { class: "btn primary", onclick: () => form.requestSubmit() }, "Save")],
  });
  form.onsubmit = async (e) => {
    e.preventDefault();
    try { await patch(`/api/projects/${p.id}`, { name: input.value }); d.close(); reload(); }
    catch (err) { showErrors(form, err); }
  };
}

function newProject(page) {
  const input = h("input", { class: "input", name: "name", maxlength: 120, placeholder: "e.g. Clinic ground floor" });
  const form = h("form", null, field("Project name", input),
    h("p", { class: "small muted" }, "A manual project waits for its first model. The Rhino plugin also creates projects on its first sync."));
  const d = drawer({
    title: "New project", body: form,
    foot: (close) => [h("button", { class: "btn", onclick: close }, "Cancel"), h("button", { class: "btn primary", onclick: () => form.requestSubmit() }, "Create →")],
  });
  form.onsubmit = async (e) => {
    e.preventDefault();
    try {
      const out = await post("/api/projects", { name: input.value });
      d.close();
      navigate(`/app/p/${out.project.id}`);
    } catch (err) {
      if (err.code === "plan_limit") { d.close(); (await import("../lib.js")).upgradePrompt(err); }
      else showErrors(form, err);
    }
  };
}

function sampleButton(page, label = "Try the sample clinic →") {
  const b = h("button", { class: "btn primary" }, label);
  b.onclick = async () => {
    const out = await act(b, () => post("/api/projects/sample"));
    if (out) navigate(`/app/p/${out.project.id}`);
    else load(page);
  };
  return b;
}

// ---- onboarding checklist ---------------------------------------------------
async function checklistData() {
  const [tokens, members, approved] = await Promise.all([
    get("/api/tokens"),
    get("/api/members"),
    get("/api/audit?action=changeset.approved"),
  ]);
  return { tokens, members, approved: approved.entries.length > 0 };
}

function checklist(x, projects, page) {
  const key = `lintelChecklist:${app.me.firm.id}`;
  if (localStorage[key] === "dismissed") return null;
  const items = [
    { name: "Connect Rhino", done: x.tokens.some((t) => !t.revoked_at), go: h("a", { class: "btn ghost compact", href: "/app/settings/plugins", "data-link": "" }, "Create token →") },
    { name: "Or try the sample clinic", done: projects.some((p) => p.host === "sample"), go: app.can("member") && sampleButton(page, "Load sample →") },
    { name: "Review your rules", done: !!localStorage[`lintelRulesSeen:${app.me.firm.id}`], go: h("a", { class: "btn ghost compact", href: "/app/rules", "data-link": "" }, "Open rules →") },
    { name: "Invite a teammate", done: x.members.members.length > 1 || (x.members.invites || []).length > 0, go: app.can("admin") && h("a", { class: "btn ghost compact", href: "/app/settings/members", "data-link": "" }, "Invite →") },
    { name: "Approve your first fix", done: x.approved, go: h("span", { class: "micro muted" }, app.can("approver") ? "Propose one, then approve it" : "Approvers do this") },
  ];
  if (items.every((i) => i.done)) return null;
  const done = items.filter((i) => i.done).length;
  const box = h("section", { class: "checklist", "aria-label": "Getting started" },
    h("div", { class: "intro" },
      h("div", null, h("span", { class: "label muted" }, `Getting started · ${done} of ${items.length}`), elevation({ seed: 3, markers: false }), h("h3", null, "Set up your sheet")),
      h("button", { class: "btn ghost compact", onclick: () => { localStorage[key] = "dismissed"; box.remove(); } }, "Dismiss")),
    h("ol", null, items.map((i) => h("li", { class: i.done && "done" },
      h("span", { class: "step-name" }, i.name),
      i.done ? h("span", { class: "tick" }, "✓ Done") : i.go || h("span")))));
  return box;
}
