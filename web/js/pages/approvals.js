// Approvals across every project: full change-set cards, approve all behind a confirm.
import { act, app, clear, confirm, empty, get, h, loadError, post, skeleton, toast } from "../lib.js";
import { changesetCard } from "../changeset.js";
import { refreshBadge } from "../main.js";

export const title = () => "Approvals";

export async function render(root) {
  const page = h("div", { class: "page" });
  root.append(page);
  const timer = setInterval(() => document.visibilityState === "visible" && load(page, true), 5000);
  await load(page);
  return () => clearInterval(timer);
}

let lastSig = "";

async function load(page, quiet) {
  if (!quiet) clear(page, head(0), skeleton(3, "skel-list"));
  let d;
  try { d = await get("/api/approvals"); }
  catch (e) { if (!quiet) clear(page, head(0), loadError(e, () => load(page))); return; }
  const sig = JSON.stringify(d.changesets.map((c) => [c.id, c.approval_count, c.comment_count]));
  if (quiet && sig === lastSig) return;
  if (quiet && page.contains(document.activeElement) && /textarea|input/i.test(document.activeElement.tagName)) return;
  lastSig = sig;
  const reload = () => { load(page, false); refreshBadge(); };
  const list = d.changesets;
  const all = app.can("approver") && list.length > 1 && h("button", { class: "btn", onclick: (e) => approveAll(e.currentTarget, list, reload) }, "Approve all ▾");
  clear(page, head(list.length, all),
    !app.can("approver") && list.length > 0 && h("div", { class: "notice", style: { marginBottom: "16px" } }, "You can comment on these. An approver decides."),
    list.length ? list.map((cs) => changesetCard(cs, { showProject: true, needed: d.needed_approvals, onChange: reload }))
      : empty("Nothing waiting", "When someone proposes a fix, or the assistant drafts a change, it waits here for an approver."));
}

function head(n, extra) {
  return h("div", { class: "page-head" }, h("h1", null, `Awaiting your approval (${n})`), h("span", { class: "spacer", style: { flex: 1 } }), extra,
    h("p", { class: "sub small muted", style: { margin: 0 } }, "Nothing changes in a model until a person approves it. Every decision is logged."));
}

async function approveAll(btn, list, reload) {
  const ok = await confirm({
    title: `Approve ${list.length} change sets`,
    message: [h("p", null, "You're approving all of these:"),
      h("ul", { class: "small", style: { paddingLeft: "18px" } }, list.map((c) => h("li", null, `${c.title} · ${c.project_name}`)))],
    confirmLabel: `Approve ${list.length}`,
  });
  if (!ok) return;
  await act(btn, async () => {
    let done = 0;
    for (const cs of list) {
      try { await post(`/api/changesets/${cs.id}/approve`); done++; }
      catch (e) { if (e.code === "plan_limit") throw e; toast(`${cs.title}: ${e.message}`, { error: true }); }
    }
    toast(`You approved ${done} change set${done === 1 ? "" : "s"}.`);
  });
  reload();
}
