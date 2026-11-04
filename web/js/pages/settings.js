// Settings: Profile, Firm, Members, Plugins (personal tokens), Billing.
import { act, ago, app, clear, confirm, copy, del, empty, field, formData, get, h, loadError, patch, post, put, showErrors, skeleton, toast, upgradePrompt } from "../lib.js";
import { navigate, refreshMe, renderBanners } from "../main.js";

const SECTIONS = [["profile", "Profile"], ["firm", "Firm"], ["members", "Members"], ["plugins", "Plugins"], ["billing", "Billing"]];
let panel = null;

export const key = () => "settings";
export const title = ([s]) => `Settings · ${(SECTIONS.find(([k]) => k === (s || "profile")) || SECTIONS[0])[1]}`;

export async function render(root, [section]) {
  const nav = h("nav", { class: "subnav", "aria-label": "Settings" });
  panel = h("div", { class: "panel" });
  root.append(h("div", { class: "page" }, h("div", { class: "page-head" }, h("h1", null, "Settings")), h("div", { class: "settings" }, nav, panel)));
  panel.nav = nav;
  await show(section || "profile");
}

export function update([section]) { show(section || "profile"); }

async function show(section) {
  clear(panel.nav, SECTIONS.map(([k, label]) => h("a", { href: `/app/settings/${k}`, "data-link": "", class: k === section && "active", "aria-current": k === section ? "page" : null }, label)));
  document.title = `${title([section])} · Lintel`;
  clear(panel, skeleton(1, "skel-list"));
  try { await ({ profile, firm, members, plugins, billing })[section](panel); }
  catch (e) { clear(panel, loadError(e, () => show(section))); }
}

const input = (name, val, extra = {}) => h("input", { class: "input", name, value: val ?? "", ...extra });

function onSubmit(form, fn) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    btn.classList.add("loading"); btn.disabled = true;
    try { showErrors(form, null); await fn(formData(form)); }
    catch (err) { err.code === "plan_limit" ? upgradePrompt(err) : showErrors(form, err); }
    finally { btn.classList.remove("loading"); btn.disabled = false; }
  });
}

// ---- profile ---------------------------------------------------------------
async function profile(p) {
  const me = app.me.user;
  const f1 = h("form", { novalidate: true }, field("Name", input("name", me.name, { maxlength: 100 })),
    h("div", { class: "field" }, h("span", { class: "flabel" }, "Email"), h("span", { class: "data" }, me.email)),
    h("button", { class: "btn primary", type: "submit" }, "Save"));
  onSubmit(f1, async (d) => { await patch("/api/me", { name: d.name }); await refreshMe(); toast("Profile saved."); });
  const f2 = h("form", { novalidate: true },
    field("Current password", input("current", "", { type: "password", autocomplete: "current-password" })),
    field("New password", input("password", "", { type: "password", autocomplete: "new-password" }), "At least 10 characters"),
    h("button", { class: "btn", type: "submit" }, "Change password"));
  onSubmit(f2, async (d) => { await post("/api/me/password", d); f2.reset(); toast("Password changed. Your other sessions were signed out."); });
  clear(p, h("section", null, h("h3", null, "Profile"), f1), h("section", null, h("h3", null, "Password"), f2));
}

// ---- firm ------------------------------------------------------------------
async function firm(p) {
  const f = app.me.firm;
  const admin = app.can("admin");
  const nameForm = h("form", { novalidate: true }, field("Firm name", input("name", f.name, { maxlength: 120, disabled: !admin })),
    admin && h("button", { class: "btn primary", type: "submit" }, "Save"));
  onSubmit(nameForm, async (d) => { await patch("/api/firm", { name: d.name }); await refreshMe(); toast("Firm renamed."); show("firm"); });
  const toggle = (label, hint, keyName, value) => {
    const cb = h("input", { type: "checkbox", checked: value, disabled: !admin, "aria-label": label });
    cb.onchange = async () => {
      try { await patch("/api/firm", { [keyName]: cb.checked }); await refreshMe(); toast(`${label}: ${cb.checked ? "on" : "off"}.`); }
      catch (e) { cb.checked = !cb.checked; e.code === "plan_limit" ? upgradePrompt(e) : toast(e.message, { error: true }); }
    };
    return h("div", { class: "toggle" }, h("div", null, h("div", null, label), h("div", { class: "small muted" }, hint)), h("label", { class: "check" }, cb));
  };
  clear(p,
    h("section", null, h("h3", null, "Firm"), nameForm),
    h("section", null, h("h3", null, "Approvals and assistant"),
      toggle("Two approvals", "A change set needs two different approvers before it reaches the model. Firm plan.", "two_approvals", f.two_approvals),
      toggle("Assistant chat", "Chat sends your message plus the relevant model data and rules to Anthropic's API. API data isn't used for training.", "chat_enabled", f.chat_enabled)),
    h("section", null, h("h3", null, "Data region"),
      h("p", { class: "small" }, f.region ? `This firm's projects, rules and history are stored in ${f.region}.`
        : "This firm is stored in the default region of this Lintel server. Enterprise firms can choose a region or host Lintel themselves."),
      h("p", { class: "micro muted" }, "Firm ID ", h("code", { style: { textTransform: "none" } }, f.id))),
    app.can("owner") && ssoSection(f),
    app.can("owner") && h("section", null, h("h3", { class: "accent" }, "Danger zone"),
      h("p", { class: "small" }, "Deleting the firm signs everyone out and removes its projects, rules and history after 30 days."),
      h("button", { class: "btn danger", onclick: async () => {
        const ok = await confirm({ title: "Delete firm", message: `This deletes ${f.name} for every member.`, confirmLabel: "Delete firm", danger: true, typeToConfirm: f.name });
        if (!ok) return;
        await act(null, () => del("/api/firm", { confirm: f.name }));
        app.me = null;
        navigate("/login");
      } }, "Delete firm")));
}

function ssoSection(f) {
  const head = h("h3", null, "Single sign-on");
  if (!f.limits.sso) {
    return h("section", null, head, h("p", { class: "small" }, "Sign in through your identity provider (Okta, Microsoft Entra ID, Google Workspace or any OpenID Connect provider). Part of the Enterprise plan. ",
      h("a", { href: "/contact.html" }, "Talk to us →")));
  }
  const s = f.sso || {};
  const form = h("form", { novalidate: true },
    field("Issuer URL", input("issuer", s.issuer, { placeholder: "https://login.example.com" }), "From your identity provider's OpenID Connect app"),
    field("Client ID", input("client_id", s.client_id)),
    field("Client secret", input("client_secret", "", { type: "password", autocomplete: "off", placeholder: f.sso ? "Saved. Leave blank to keep it." : "" })),
    field("Email domains", input("domains", (s.domains || []).join(", "), { placeholder: "studio.com, studio.co.uk" }), "People with these addresses can sign in with SSO"),
    field("New people join as", h("select", { class: "input", name: "default_role" },
      [["member", "Member"], ["approver", "Approver"], ["viewer", "Viewer"]].map(([v, l]) => h("option", { value: v, selected: (s.default_role || "member") === v }, l)))),
    h("label", { class: "check", style: { margin: "8px 0 16px" } }, h("input", { type: "checkbox", name: "required", checked: !!s.required }),
      " Require SSO. Members can't use a password; owners still can, so a provider outage can't lock you out."),
    h("p", { class: "small muted" }, "Redirect URL for your provider: ", h("code", null, `${location.origin}/api/auth/sso/callback`)),
    h("div", { class: "btn-row" }, h("button", { class: "btn primary", type: "submit" }, f.sso ? "Save SSO" : "Turn on SSO"),
      f.sso && h("button", { class: "btn ghost", type: "button", onclick: async (e) => {
        if (!await confirm({ title: "Turn off SSO", message: "Members will sign in with their passwords again (or reset them).", confirmLabel: "Turn off", danger: true })) return;
        await act(e.currentTarget, () => del("/api/firm/sso"), "Single sign-on is off."); await refreshMe(); show("firm");
      } }, "Turn off")));
  onSubmit(form, async (d) => {
    await put("/api/firm/sso", { ...d, required: form.querySelector("[name=required]").checked });
    await refreshMe(); toast("Single sign-on saved."); show("firm");
  });
  return h("section", null, head, form);
}

// ---- members ---------------------------------------------------------------
const ROLES =[["owner", "Owner"], ["admin", "Admin"], ["approver", "Approver"], ["member", "Member"], ["viewer", "Viewer"]];
const ROLE_HELP = "Viewer: read only · Member: propose, chat, comment · Approver: approve, reject, revert · Admin: members, rules, tokens · Owner: billing, delete firm";

async function members(p) {
  const d = await get("/api/members");
  const admin = app.can("admin"), owner = app.can("owner");
  const f = app.me.firm;
  const rows = d.members.map((m) => {
    const self = m.id === app.me.user.id;
    const roleCell = admin && !(m.role === "owner" && !owner)
      ? h("select", { class: "select", style: { height: "32px", width: "140px" }, "aria-label": `Role for ${m.name}`, onchange: async (e) => {
        const prev = m.role;
        try { await patch(`/api/members/${m.id}`, { role: e.target.value }); m.role = e.target.value; toast(`${m.name} is now ${e.target.value}.`); await refreshMe(); }
        catch (err) { e.target.value = prev; err.code === "plan_limit" ? upgradePrompt(err) : toast(err.message, { error: true }); }
      } }, ROLES.filter(([r]) => owner || r !== "owner").map(([r, l]) => h("option", { value: r, selected: m.role === r }, l)))
      : h("span", { class: "chip" }, m.role);
    const remove = admin && !self && !(m.role === "owner" && !owner) && h("button", { class: "btn ghost compact", onclick: async () => {
      const ok = await confirm({ title: "Remove member", message: `Remove ${m.name} from ${f.name}? Their sessions and plugin tokens stop working now.`, confirmLabel: "Remove", danger: true });
      if (ok && await act(null, () => del(`/api/members/${m.id}`), `${m.name} removed.`) !== undefined) show("members");
    } }, "Remove");
    return h("tr", null, h("td", null, m.name, self && h("span", { class: "micro muted" }, " (you)")), h("td", { class: "mono" }, m.email), h("td", null, roleCell),
      h("td", { class: "micro muted" }, m.last_login_at ? `Seen ${ago(m.last_login_at)}` : "—"), h("td", null, remove));
  });
  const linkBox = h("div");
  const inviteForm = admin && h("form", { class: "form-grid", novalidate: true },
    field("Email", input("email", "", { type: "email", placeholder: "name@firm.com" })),
    field("Role", h("select", { class: "select", name: "role" }, ROLES.filter(([r]) => r !== "owner").map(([r, l]) => h("option", { value: r, selected: r === "member" }, l)))),
    h("div", { class: "full btn-row" }, h("button", { class: "btn primary", type: "submit" }, "Send invite →"), h("span", { class: "micro muted" }, `${f.seats_used} of ${f.seat_cap} seats used · viewers are free`)),
    h("div", { class: "full" }, linkBox));
  if (inviteForm) onSubmit(inviteForm, async (data) => {
    const out = await post("/api/invites", data);
    toast(`Invite sent to ${data.email}.`);
    await show("members");
    if (out.link) showLink(out.link);
  });
  const showLink = (link) => {
    const box = panel.querySelector("#invite-link");
    if (box) clear(box, h("p", { class: "small muted" }, "Email isn't configured on this server, so copy the link and send it yourself. It works once and expires in 7 days."),
      h("div", { class: "secret" }, h("code", null, link), h("button", { class: "btn compact", onclick: () => copy(link, "Invite link copied") }, "Copy")));
  };
  clear(p,
    h("section", null, h("h3", null, `Members (${d.members.length})`), h("div", { class: "table-wrap" }, h("table", { class: "t" },
      h("thead", null, h("tr", null, ["Name", "Email", "Role", "Last seen", ""].map((c) => h("th", null, c)))), h("tbody", null, rows))),
    h("p", { class: "micro muted", style: { marginTop: "10px" } }, ROLE_HELP)),
    admin && h("section", null, h("h3", null, "Invite"), inviteForm, h("div", { id: "invite-link", style: { marginTop: "12px" } })),
    admin && h("section", null, h("h3", null, `Pending invites (${(d.invites || []).length})`),
      (d.invites || []).length ? h("div", { class: "table-wrap" }, h("table", { class: "t" }, h("tbody", null, d.invites.map((i) => h("tr", null,
        h("td", { class: "mono" }, i.email), h("td", null, h("span", { class: "chip" }, i.role)),
        h("td", { class: "micro muted" }, i.expires_at < Date.now() / 1000 ? "Expired" : `Expires in ${Math.ceil((i.expires_at - Date.now() / 1000) / 86400)} days`),
        h("td", null, h("div", { class: "btn-row", style: { justifyContent: "flex-end" } },
          h("button", { class: "btn ghost compact", onclick: async (e) => { const out = await act(e.currentTarget, () => post(`/api/invites/${i.id}/resend`), "Invite resent with a fresh link."); if (out?.link) showLink(out.link); } }, "Resend"),
          h("button", { class: "btn ghost compact", onclick: async () => { if (await act(null, () => del(`/api/invites/${i.id}`), "Invite cancelled.") !== undefined) show("members"); } }, "Cancel"))))))))
        : h("p", { class: "small muted" }, "No pending invites.")));
}

// ---- plugins ---------------------------------------------------------------
async function plugins(p) {
  const tokens = await get("/api/tokens");
  const shown = h("div");
  const form = app.can("member") && h("form", { class: "btn-row", novalidate: true, style: { alignItems: "flex-end" } },
    h("div", { style: { flex: 1, minWidth: "240px" } }, field("Token name", input("name", "", { placeholder: "e.g. Ana's Rhino", maxlength: 80 }))),
    h("div", { class: "field" }, h("button", { class: "btn primary", type: "submit" }, "Create token →")));
  if (form) onSubmit(form, async (d) => {
    const out = await post("/api/tokens", d);
    await show("plugins");
    clear(panel.querySelector("#token-once"), h("div", { class: "notice accent" },
      h("p", { class: "label" }, `New token · ${out.name}`),
      h("p", { class: "small" }, "Copy it now. Lintel stores only a hash, so it can't show this again."),
      h("div", { class: "secret" }, h("code", null, out.token), h("button", { class: "btn primary compact", onclick: () => copy(out.token, "Token copied") }, "Copy"))));
  });
  const live = tokens.filter((t) => !t.revoked_at);
  clear(p,
    h("section", null, h("h3", null, "Plugin tokens"),
      h("p", { class: "small muted" }, "Each person creates their own token for the CAD plugin. It acts with your role in this firm. Revoke it if a laptop is lost."),
      form || h("p", { class: "small muted" }, "Viewers can't sync models, so they don't need a token."),
      h("div", { id: "token-once", style: { margin: "12px 0" } }, shown),
      live.length ? h("div", { class: "table-wrap" }, h("table", { class: "t" },
        h("thead", null, h("tr", null, ["Name", "Token", "Created", "Last used", ""].map((c) => h("th", null, c)))),
        h("tbody", null, live.map((t) => h("tr", null, h("td", null, t.name), h("td", { class: "mono" }, `${t.prefix}…`),
          h("td", { class: "micro muted" }, ago(t.created_at)), h("td", { class: "micro" }, t.last_used_at ? ago(t.last_used_at) : "never"),
          h("td", null, h("button", { class: "btn danger compact", onclick: async () => {
            const ok = await confirm({ title: "Revoke token", message: `Revoke "${t.name}"? The plugin using it stops syncing on its next request.`, confirmLabel: "Revoke", danger: true });
            if (ok && await act(null, () => del(`/api/tokens/${t.id}`), "Token revoked.") !== undefined) show("plugins");
          } }, "Revoke")))))))
        : empty("No tokens yet", "Create one to connect Rhino.")),
    h("section", null, h("h3", null, "Connect Rhino 8"),
      h("ol", { class: "steps" },
        h("li", null, "Create a token above and copy it."),
        h("li", null, ["Save it on your computer: set the ", h("code", null, "LINTEL_TOKEN"), " environment variable, or paste it into ", h("code", null, "data/plugin-token.txt"), " in the Lintel folder."]),
        h("li", null, ["Set ", h("code", null, "LINTEL_URL"), ` to ${location.origin} if Lintel isn't on this computer.`]),
        h("li", null, ["In Rhino 8 run ", h("code", null, "_-RunPythonScript \"…\\hosts\\rhino\\lintel_rhino.py\""), ". A Lintel panel opens beside the model; sign in there once."]),
        h("li", null, "Your model syncs every 2 seconds. Approved changes apply as one undo step, so Ctrl+Z undoes a Lintel edit.")),
      h("p", { class: "small muted", style: { marginTop: "12px" } }, "No Rhino? Run the fixture host to try the protocol: ", h("code", null, "python hosts/fixture_host.py samples/clinic.json --watch"))));
}

// ---- billing ---------------------------------------------------------------
async function billing(p) {
  const d = await get("/api/billing");
  const f = d.firm, owner = app.can("owner");
  const usage = d.usage.chat_messages, cap = d.chat_cap, extra = d.usage.topup_messages || 0;
  const pct = cap ? Math.min(100, Math.round((usage / cap) * 100)) : 0;
  const qs = new URLSearchParams(location.search);
  const upgraded = qs.get("upgraded"), toppedUp = qs.get("topup");
  const planCard = (key, name, price, sub, items) => {
    const current = f.plan === key;
    const btn = owner && !current && key !== "free" && h("button", { class: "btn primary", onclick: async (e) => {
      const out = await act(e.currentTarget, () => post("/api/billing/checkout", { plan: key, interval: "month", seats: Math.max(f.seats_used, key === "firm" ? 3 : 1) }));
      if (out?.url) location.href = out.url;
    } }, `Upgrade to ${name} →`);
    return h("div", { class: ["card", current && "selected"] },
      h("div", { class: "card-top" }, h("span", { class: "label" }, name), current && h("span", { class: "chip applied" }, "✓ Current")),
      h("div", { class: "price" }, price), h("span", { class: "micro muted" }, sub),
      h("ul", null, items.map((i) => h("li", null, i))), btn);
  };
  clear(p,
    upgraded && h("div", { class: "notice", style: { marginBottom: "16px" } }, "Thanks. Your plan updates as soon as the payment provider confirms it."),
    toppedUp && h("div", { class: "notice", style: { marginBottom: "16px" } }, `Thanks. ${d.topup.messages} messages are added as soon as the payment provider confirms it.`),
    h("section", null, h("h3", null, "Your plan"),
      h("dl", { class: "kv", style: { maxWidth: "520px" } },
        h("dt", null, "Plan"), h("dd", null, f.plan.toUpperCase() + (f.trial_days_left !== null ? ` · trial, ${f.trial_days_left} days left` : "")),
        h("dt", null, "Seats"), h("dd", null, `${f.seats_used} of ${f.seat_cap} used`),
        h("dt", null, "Assistant this month"), h("dd", null, `${usage} of ${cap}` + (extra ? ` (includes ${extra} added)` : ""))),
      h("div", { class: ["meter", pct >= 80 && "hot"], style: { maxWidth: "520px", marginTop: "12px" }, role: "meter", "aria-valuenow": String(pct), "aria-valuemin": "0", "aria-valuemax": "100", "aria-label": "Assistant messages used" }, h("span", { style: { width: `${pct}%` } })),
      app.can("admin") && f.plan !== "free" && h("div", { style: { display: "flex", flexWrap: "wrap", marginTop: "16px", gap: "12px", alignItems: "center" } },
        h("button", { class: "btn", onclick: async (e) => {
          const out = await act(e.currentTarget, () => post("/api/billing/topup"));
          if (out?.url) location.href = out.url;
        } }, `Add ${d.topup.messages} messages · $${d.topup.price} →`),
        h("span", { class: "micro muted" }, "For this month only. Checks, fixes and approvals never use messages.")),
      owner && f.plan_raw !== "free" && !f.trial_days_left && h("button", { class: "btn", style: { marginTop: "16px" }, onclick: async (e) => {
        const out = await act(e.currentTarget, () => post("/api/billing/portal"));
        if (out?.url) location.href = out.url;
      } }, "Manage billing →")),
    h("section", null, h("h3", null, "Plans"),
      !d.configured && h("div", { class: "notice", style: { marginBottom: "16px" } }, "Online payments aren't set up on this server yet. Contact us to upgrade."),
      h("div", { class: "plans" },
        planCard("free", "Free", "$0", "1 member", ["1 project", "Checks, plan view, propose fixes", "Starter rules", "20 assistant messages / month"]),
        planCard("pro", "Pro", "$39", "per seat / month · $390 / year", ["Unlimited projects", "Apply approved changes in Rhino", "Custom rules and project overrides", "300 assistant messages per seat"]),
        planCard("firm", "Firm", "$99", "per seat / month · min 3 seats", ["Everything in Pro", "Two-approval mode", "Audit CSV export", "1 000 assistant messages per seat"])),
      !owner && h("p", { class: "micro muted", style: { marginTop: "12px" } }, "Only the firm owner can change the plan.")));
  renderBanners();
}
