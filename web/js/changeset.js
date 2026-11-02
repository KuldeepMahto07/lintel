// The change-set card: accent header strip, before (struck) → after (bold) diff, decisions, comments.
import { act, ago, app, chip, clear, clock, confirm, get, h, num, post, titleCase, toast } from "./lib.js";

const PROP_UNITS = { clear_width_mm: "mm", riser_mm: "mm", tread_mm: "mm", width_mm: "mm", area_m2: "m²" };

export function fmtValue(prop, v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number" || (typeof v === "string" && v.trim() !== "" && !isNaN(v))) {
    const unit = PROP_UNITS[prop];
    return num(v, Number.isInteger(Number(v)) ? 0 : 1) + (unit ? (unit === "m²" ? " M²" : " MM") : "");
  }
  return String(v);
}

function sourceLabel(cs) {
  return { rule: "rule fix", agent: "the assistant", revert: "revert", manual: "manual" }[cs.source] || cs.source;
}

export async function approve(cs, onChange) {
  const out = await post(`/api/changesets/${cs.id}/approve`);
  if (out.status === "proposed") toast(`Your approval is recorded: ${out.approvals} of ${out.needed}. Waiting for a second approver.`);
  else if (out.status === "applied") toast("You approved it. Applied to the model.");
  else toast("You approved it. The plugin applies it on its next sync.");
  onChange?.(out);
  return out;
}

export async function reject(cs, onChange) {
  await post(`/api/changesets/${cs.id}/reject`);
  toast("Rejected. It won't reach the model.", {
    kind: "Rejected",
    undo: async () => {
      try { await post(`/api/changesets/${cs.id}/undo-reject`); toast("Restored to the approval queue."); onChange?.(); }
      catch (e) { toast(e.message, { error: true }); }
    },
  });
  onChange?.();
}

export async function revert(cs, onChange) {
  const ok = await confirm({
    title: "Revert this change",
    message: [h("p", null, `An inverse change set for "${cs.title}" will be sent to the model, approved by you.`),
      h("p", { class: "small muted" }, "The original is marked reverted once the plugin applies it.")],
    confirmLabel: "Revert",
    danger: true,
  });
  if (!ok) return;
  await post(`/api/changesets/${cs.id}/revert`);
  toast("Revert sent to the model.");
  onChange?.();
}

/**
 * opts: {onChange, showProject, needed, compact, open}
 */
export function changesetCard(cs, opts = {}) {
  const settled = cs.status !== "proposed";
  const card = h("article", { class: ["cs-card", settled && "settled"], tabindex: "0", dataset: { cs: cs.id }, "aria-label": cs.title });
  const needed = opts.needed || 1;
  const head = h("div", { class: "cs-head" },
    h("span", { class: "title" }, cs.title),
    settled ? chip(cs.status) : h("span", { class: "micro" }, clock(cs.created_at)));
  const meta = h("div", { class: "cs-meta micro muted" },
    opts.showProject && cs.project_name && h("a", { href: `/app/p/${cs.project_id}/approvals`, "data-link": "" }, cs.project_name),
    h("span", null, `Proposed by ${cs.source === "agent" ? "the assistant" : (cs.created_by_name || "someone")}`),
    h("span", null, sourceLabel(cs)),
    h("span", null, ago(cs.created_at)));
  const rows = cs.ops.map((o) => h("tr", null,
    h("td", null, o.element_name || o.element, h("div", { class: "micro muted" }, o.element)),
    h("td", { class: "mono" }, titleCase(o.prop)),
    h("td", { class: "before" }, fmtValue(o.prop, o.from)),
    h("td", { class: "arrow", "aria-hidden": "true" }, "→"),
    h("td", { class: "after" }, fmtValue(o.prop, o.to))));
  const diff = h("table", { class: "diff" },
    h("thead", null, h("tr", null, h("th", null, "Element"), h("th", null, "Property"), h("th", null, "Before"), h("th", null, ""), h("th", null, "After"))),
    h("tbody", null, rows));
  const body = h("div", { class: "cs-body" }, diff,
    cs.reason && h("p", { class: "cs-reason" }, cs.reason),
    cs.error && h("div", { class: "cs-error", role: "alert" }, cs.error),
    cs.status === "proposed" && needed > 1 && h("p", { class: "micro" }, `${cs.approval_count || 0} of ${needed} approvals`));
  const foot = h("div", { class: "cs-foot" });
  const commentsBox = h("div", { class: "comments", hidden: true });

  if (cs.status === "proposed") {
    if (app.can("approver")) {
      const a = h("button", { class: "btn primary compact", "data-action": "approve" }, "Approve →");
      const r = h("button", { class: "btn danger compact", "data-action": "reject" }, "Reject");
      a.onclick = () => act(a, () => approve(cs, opts.onChange));
      r.onclick = () => act(r, () => reject(cs, opts.onChange));
      foot.append(a, r);
    } else {
      foot.append(h("span", { class: "micro muted" }, "Waiting for an approver"));
    }
  } else if (cs.status === "approved") {
    foot.append(h("span", { class: "micro" }, "Approved. Applies when the plugin next syncs."));
  } else if (cs.status === "applied" && cs.source !== "revert" && app.can("approver")) {
    const rv = h("button", { class: "btn compact" }, "↺ Revert");
    rv.onclick = () => act(rv, () => revert(cs, opts.onChange));
    foot.append(rv);
  }
  const cbtn = h("button", { class: "btn ghost compact", "aria-expanded": "false" },
    cs.comment_count ? `${cs.comment_count} comment${cs.comment_count === 1 ? "" : "s"} ▸` : "Comment");
  cbtn.onclick = async () => {
    const open = commentsBox.hidden;
    commentsBox.hidden = !open;
    cbtn.setAttribute("aria-expanded", String(open));
    if (open) await loadComments(cs, commentsBox, cbtn);
  };
  foot.append(h("span", { class: "spacer" }), cbtn);
  body.append(foot, commentsBox);
  card.append(head, meta, body);
  if (opts.open) cbtn.click();
  return card;
}

async function loadComments(cs, box, cbtn) {
  clear(box, h("span", { class: "micro muted" }, "Loading comments…"));
  let list;
  try { list = await get(`/api/changesets/${cs.id}/comments`); }
  catch (e) { clear(box, h("span", { class: "micro accent" }, e.message)); return; }
  const draw = () => {
    const ta = h("textarea", { class: "textarea", rows: 2, maxlength: 4000, placeholder: "Add a comment…", "aria-label": "Comment" });
    const send = h("button", { class: "btn compact", type: "submit" }, "Post");
    const form = h("form", { class: "btn-row", style: { alignItems: "flex-end" } }, h("div", { style: { flex: 1 } }, ta), send);
    form.onsubmit = (e) => {
      e.preventDefault();
      if (!ta.value.trim()) return;
      act(send, async () => {
        const out = await post(`/api/changesets/${cs.id}/comments`, { body: ta.value });
        list = out.comments;
        cbtn.textContent = `${list.length} comment${list.length === 1 ? "" : "s"} ▸`;
        draw();
      });
    };
    clear(box,
      list.length ? list.map((c) => h("div", { class: "comment" },
        h("div", { class: "who micro muted" }, `${c.name} · ${ago(c.created_at)}`), h("p", null, c.body)))
        : h("span", { class: "micro muted" }, "No comments yet."),
      app.can("member") && form);
  };
  draw();
}

export function compactRow(cs, { selected, onSelect }) {
  return h("div", {
    class: ["issue-row", selected && "selected"], tabindex: "0", role: "button", dataset: { cs: cs.id },
    onclick: () => onSelect(cs), onkeydown: (e) => { if (e.key === "Enter") onSelect(cs); },
  },
  h("span", { class: ["marker", cs.status !== "proposed" && "done"] }, cs.status === "proposed" ? "▣" : cs.status === "applied" ? "✓" : "·"),
  h("div", { class: "body" },
    h("span", { class: "name" }, cs.title),
    h("span", { class: "micro muted" }, `${cs.source === "agent" ? "the assistant" : cs.created_by_name || ""} · ${ago(cs.created_at)}`),
    h("div", { class: "act" }, chip(cs.status), cs.ops.length > 1 ? h("span", { class: "micro muted" }, `${cs.ops.length} edits`) : null)));
}
