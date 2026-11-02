// Firm rules: table, add/edit drawer, CSV/JSON import with a preview of row errors, export.
import { act, api, app, chip, clear, confirm, download, drawer, empty, field, get, h, loadError, measure, post, showErrors, skeleton, toast, upgradePrompt, del } from "../lib.js";

export const title = () => "Rules";

const CSV_TEMPLATE = "name,kind,applies_to,where,prop,value,unit,ref,severity,fixable\n" +
  "Firm door width,min,door,,clear_width_mm,900,mm,Firm standard,error,true\n" +
  "Office area,min,room,use=office,area_m2,9,m²,Firm standard,warning,false\n";

export async function render(root) {
  localStorage[`lintelRulesSeen:${app.me.firm.id}`] = "1";
  const page = h("div", { class: "page" });
  root.append(page);
  await load(page);
}

async function load(page) {
  clear(page, head(page), skeleton(1, "skel-list"));
  let rules;
  try { rules = await get("/api/rules"); }
  catch (e) { clear(page, head(page), loadError(e, () => load(page))); return; }
  const reload = () => load(page);
  const focus = new URLSearchParams(location.search).get("rule");
  const admin = app.can("admin");
  const proposed = rules.filter((r) => r.status === "proposed");
  const table = h("div", { class: "table-wrap" }, h("table", { class: "t" },
    h("thead", null, h("tr", null, ["Name", "Applies to", "Check", "Ref", "Status", ""].map((c) => h("th", null, c)))),
    h("tbody", null, [...proposed, ...rules.filter((r) => r.status !== "proposed")].map((r) => row(r, admin, reload, focus === r.id)))));
  clear(page, head(page, rules.length, reload),
    h("p", { class: "small muted", style: { maxWidth: "760px" } }, "A rule is a number plus where it comes from. Lintel never stores building-code text. Starter values are examples: verify each against your adopted edition and local amendments."),
    !app.plan("custom_rules") && h("div", { class: "notice accent", style: { marginBottom: "16px" } }, "You're on the Free plan: starter rules only. Custom rules are kept but stay off until you upgrade."),
    rules.length ? table : empty("No rules", "Add your firm's first rule, or import the CSV template.", admin && h("button", { class: "btn primary", onclick: () => edit(null, reload) }, "+ Add rule")));
  if (focus) document.querySelector("tr.selected")?.scrollIntoView({ block: "center" });
}

function head(page, n = "", reload) {
  return h("div", { class: "page-head" }, h("h1", null, `Firm rules${n !== "" ? ` (${n})` : ""}`), h("span", { class: "spacer", style: { flex: 1 } }),
    reload && app.can("admin") && h("button", { class: "btn primary", onclick: () => edit(null, reload) }, "+ Add rule"),
    reload && app.can("admin") && h("button", { class: "btn", onclick: () => importDrawer(reload) }, "Import CSV/JSON"),
    reload && h("button", { class: "btn", onclick: (e) => act(e.currentTarget, () => download("/api/rules/export", "lintel-rules.json"), "Rules exported.") }, "Export"));
}

function checkText(r) {
  if (r.kind === "egress") return `travel ≤ ${measure(r.value / 1000, "m")}`;
  return `${r.prop || ""} ${r.kind === "min" ? "≥" : "≤"} ${measure(r.value, r.unit)}`;
}

function row(r, admin, reload, selected) {
  const where = r.where ? Object.entries(r.where).map(([k, v]) => `${k}=${v}`).join("; ") : "";
  let actions = null;
  if (admin) {
    if (r.status === "proposed") {
      const b = h("button", { class: "btn primary compact" }, "Activate");
      b.onclick = () => act(b, () => post(`/api/rules/${encodeURIComponent(r.id)}/status`, { status: "active" }), "Rule activated. The next check uses it.").then(reload);
      actions = [b, h("button", { class: "btn ghost compact", onclick: () => remove(r, reload) }, "Discard")];
    } else {
      const toggle = h("button", { class: "btn compact" }, r.status === "active" ? "Disable" : "Enable");
      toggle.onclick = async () => {
        const to = r.status === "active" ? "disabled" : "active";
        try {
          await post(`/api/rules/${encodeURIComponent(r.id)}/status`, { status: to });
          toast(to === "disabled" ? `"${r.name}" disabled. Its flags are gone.` : `"${r.name}" is active again.`, {
            undo: to === "disabled" ? async () => { await post(`/api/rules/${encodeURIComponent(r.id)}/status`, { status: "active" }); reload(); } : undefined,
          });
          reload();
        } catch (e) { e.code === "plan_limit" ? upgradePrompt(e) : toast(e.message, { error: true }); }
      };
      actions = [h("button", { class: "btn ghost compact", onclick: () => edit(r, reload) }, "Edit"), toggle,
        h("button", { class: "btn ghost compact", onclick: () => remove(r, reload), "aria-label": `Delete ${r.name}` }, "Delete")];
    }
  }
  return h("tr", { class: selected && "selected" },
    h("td", null, h("strong", null, r.name), h("div", { class: "micro muted" }, `${r.source || "firm"}${r.severity === "warning" ? " · warning" : ""}${r.fixable ? " · one-click fix" : ""}`)),
    h("td", { class: "mono" }, r.applies_to, where && h("div", { class: "micro muted" }, where)),
    h("td", { class: "mono" }, checkText(r)),
    h("td", { class: "ref", style: { maxWidth: "280px" } }, r.ref || "—"),
    h("td", null, chip(r.status === "proposed" ? "proposed" : r.status, r.status === "proposed" ? "▣ proposed" : r.status)),
    h("td", null, h("div", { class: "btn-row", style: { justifyContent: "flex-end" } }, actions)));
}

async function remove(r, reload) {
  const ok = await confirm({ title: "Delete rule", message: `Delete "${r.name}"? Projects stop checking it. This can't be undone; export your rules first if you might want it back.`, confirmLabel: "Delete", danger: true });
  if (!ok) return;
  await act(null, () => del(`/api/rules/${encodeURIComponent(r.id)}`), "Rule deleted.");
  reload();
}

function edit(r, reload) {
  const v = r || { kind: "min", applies_to: "door", severity: "error", fixable: false, unit: "mm" };
  const sel = (name, opts, cur) => h("select", { class: "select", name }, opts.map(([val, label]) => h("option", { value: val, selected: cur === val }, label)));
  const inp = (name, val, extra = {}) => h("input", { class: "input", name, value: val ?? "", ...extra });
  const where = v.where ? Object.entries(v.where).map(([k, x]) => `${k}=${x}`).join("; ") : "";
  const fixable = h("input", { type: "checkbox", name: "fixable", checked: !!v.fixable });
  const form = h("form", { class: "form-grid", novalidate: true },
    h("div", { class: "full" }, field("Name", inp("name", v.name, { maxlength: 120, autofocus: true }))),
    field("Check type", sel("kind", [["min", "Minimum"], ["max", "Maximum"], ["egress", "Travel distance"]], v.kind)),
    field("Applies to", sel("applies_to", [["door", "Doors"], ["room", "Rooms"], ["stair", "Stairs"]], v.applies_to)),
    field("Only where", inp("where", where, { placeholder: "use=exam" }), "key=value; separate with ;"),
    field("Property", inp("prop", v.prop, { placeholder: "clear_width_mm" }), "Not needed for travel distance"),
    field("Value", inp("value", v.kind === "egress" && v.value ? v.value : v.value, { inputmode: "decimal" }), "Travel distance in mm"),
    field("Unit", inp("unit", v.unit, { placeholder: "mm" })),
    h("div", { class: "full" }, field("Reference", inp("ref", v.ref, { placeholder: "IBC §1010.1.1 (verify against your adopted edition)" }), "A section number, never code text")),
    field("Severity", sel("severity", [["error", "Error"], ["warning", "Warning"]], v.severity)),
    h("div", { class: "field" }, h("span", { class: "flabel" }, "One-click fix"), h("label", { class: "check" }, fixable, "Lintel may propose the new value")));
  const d = drawer({
    title: r ? `Edit rule · ${r.name}` : "Add rule", body: form,
    foot: (close) => [h("button", { class: "btn", onclick: close }, "Cancel"), h("button", { class: "btn primary", onclick: () => form.requestSubmit() }, r ? "Save" : "Add rule →")],
  });
  form.onsubmit = async (e) => {
    e.preventDefault();
    const data = Object.fromEntries(new FormData(form).entries());
    data.fixable = fixable.checked;
    if (r) data.id = r.id;
    try {
      await post("/api/rules", data);
      d.close();
      toast(r ? "Rule saved. Checks use it on the next load." : "Rule added.");
      reload();
    } catch (err) {
      if (err.code === "plan_limit") { d.close(); upgradePrompt(err); } else showErrors(form, err);
    }
  };
}

function importDrawer(reload) {
  const ta = h("textarea", { class: "textarea", rows: 8, placeholder: "Paste CSV with a header row, or a JSON list", style: { fontFamily: "var(--font-mono)", fontSize: "12px" } });
  const file = h("input", { type: "file", accept: ".csv,.json,text/csv,application/json", class: "small" });
  const preview = h("div");
  const importBtn = h("button", { class: "btn primary", disabled: true }, "Import");
  file.onchange = async () => { if (file.files[0]) { ta.value = await file.files[0].text(); check(); } };
  let timer;
  ta.oninput = () => { clearTimeout(timer); timer = setTimeout(check, 350); };
  async function check() {
    importBtn.disabled = true;
    if (!ta.value.trim()) return clear(preview);
    try {
      const out = await api("/api/rules/import?dry_run=1", { method: "POST", raw: ta.value });
      clear(preview,
        h("p", { class: "micro", style: { margin: "16px 0 8px" } }, `${out.valid} ready · `, h("span", { class: out.invalid ? "accent" : "muted" }, `${out.invalid} with errors`)),
        h("div", { class: "table-wrap" }, h("table", { class: "t compact" },
          h("thead", null, h("tr", null, ["Row", "Name", "Check", "Errors"].map((c) => h("th", null, c)))),
          h("tbody", null, out.rows.map((r) => h("tr", { class: r.errors && "selected" },
            h("td", { class: "num" }, String(r.row)), h("td", null, r.rule.name || "—"),
            h("td", { class: "mono" }, `${r.rule.applies_to || "?"} ${r.rule.prop || ""} ${r.rule.kind || ""} ${r.rule.value ?? ""}`),
            h("td", { class: "micro accent" }, r.errors ? Object.entries(r.errors).map(([k, m]) => `${k}: ${m}`).join(" · ") : h("span", { class: "muted" }, "OK"))))))));
      importBtn.disabled = !(out.valid && !out.invalid);
    } catch (e) {
      clear(preview, h("div", { class: "notice accent", style: { marginTop: "16px" } }, e.message));
    }
  }
  const d = drawer({
    title: "Import rules",
    body: [h("p", { class: "small muted" }, "Columns: name, kind (min/max/egress), applies_to (door/room/stair), where, prop, value, unit, ref, severity, fixable. Every row must pass before anything is saved."),
      h("div", { class: "btn-row", style: { marginBottom: "12px" } }, file,
        h("button", { class: "btn ghost compact", onclick: () => { ta.value = CSV_TEMPLATE; check(); } }, "Use the template")),
      ta, preview],
    foot: (close) => [h("button", { class: "btn", onclick: close }, "Cancel"), importBtn],
  });
  importBtn.onclick = async () => {
    const out = await act(importBtn, () => api("/api/rules/import", { method: "POST", raw: ta.value }), (o) => `Imported ${o.imported} rule${o.imported === 1 ? "" : "s"}. They flag matching elements now.`);
    if (out) { d.close(); reload(); }
  };
}
