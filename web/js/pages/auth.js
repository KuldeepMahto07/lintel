// Sign in, sign up, password reset and invite acceptance: a ruled drawing sheet beside the form.
import { app, field, formData, get, h, post, showErrors } from "../lib.js";
import { navigate, refreshMe } from "../main.js";
import { elevation, logoMark } from "../art.js";

function sheet(title, kicker, ...content) {
  return h("main", { class: "auth split" },
    h("section", { class: "auth-art", "aria-hidden": "true" },
      h("div", { class: "art-frame" },
        h("div", { class: "ruler top" }), h("div", { class: "ruler bottom" }), h("div", { class: "ruler left" }), h("div", { class: "ruler right" }),
        ["tl", "tr", "bl", "br"].map((c) => h("span", { class: ["corner", c] }, "+")),
        elevation({ seed: 11 })),
      h("div", { class: "caption" },
        h("span", { class: "label muted" }, "Rule checks · approval-gated edits · audit log"),
        h("span", { class: "h2" }, "Your standards, checked inside the model."))),
    h("div", { class: "auth-form" },
      h("div", { class: "auth-box" },
        h("a", { class: "logo", href: "/app", "data-link": "" }, logoMark(34), "LINTEL"),
        kicker && h("span", { class: "label muted" }, kicker),
        h("h1", null, title),
        ...content)));
}

const input = (name, type = "text", extra = {}) => h("input", { class: "input", name, type, ...extra });

function submitter(form, fn) {
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = form.querySelector("button[type=submit]");
    btn.classList.add("loading"); btn.disabled = true;
    try { await fn(formData(form)); }
    catch (err) { showErrors(form, err); }
    finally { if (btn.isConnected) { btn.classList.remove("loading"); btn.disabled = false; } }
  });
}

async function enter(next) {
  await refreshMe();
  navigate(next || "/app", { replace: true });
}

const nextParam = () => new URLSearchParams(location.search).get("next");

export const login = {
  title: () => "Sign in",
  render(root) {
    const form = h("form", { class: "auth-card", novalidate: true },
      field("Work email", input("email", "email", { autocomplete: "email", required: true, autofocus: true })),
      field("Password", input("password", "password", { autocomplete: "current-password", required: true })),
      h("div", { class: "btn-row", style: { justifyContent: "space-between" } },
        h("a", { class: "btn ghost", href: "/reset", "data-link": "" }, "Forgot password"),
        h("button", { class: "btn primary", type: "submit" }, "Sign in →")));
    submitter(form, async (d) => {
      await post("/api/auth/login", { email: d.email, password: d.password }, { allow401: true });
      await enter(nextParam());
    });
    const ssoError = new URLSearchParams(location.search).get("sso_error");
    const ssoBtn = h("button", { class: "btn", type: "button", style: { width: "100%", marginTop: "12px" } }, "Sign in with SSO");
    ssoBtn.onclick = async () => {
      const mail = form.querySelector("[name=email]").value.trim();
      if (!mail) { showErrors(form, { message: "Enter your work email first.", fields: { email: "Enter your work email." } }); return; }
      ssoBtn.classList.add("loading"); ssoBtn.disabled = true;
      try { const out = await post("/api/auth/sso/start", { email: mail }); location.href = out.url; }
      catch (err) { showErrors(form, err); ssoBtn.classList.remove("loading"); ssoBtn.disabled = false; }
    };
    form.append(ssoBtn);
    if (ssoError) form.prepend(h("div", { class: "notice", role: "alert", style: { marginBottom: "12px" } }, ssoError));
    root.append(sheet("Sign in", "Welcome back", form,
      h("p", { class: "alt" }, "New to Lintel? ", h("a", { href: "/signup", "data-link": "" }, "Create your firm"))));
  },
};

export const signup = {
  title: () => "Create your firm",
  render(root) {
    const form = h("form", { class: "auth-card", novalidate: true },
      field("Name", input("name", "text", { autocomplete: "name", required: true, autofocus: true })),
      field("Work email", input("email", "email", { autocomplete: "email", required: true })),
      field("Password", input("password", "password", { autocomplete: "new-password", required: true, minlength: 10 }), "At least 10 characters"),
      field("Firm name", input("firm_name", "text", { autocomplete: "organization", required: true })),
      h("button", { class: "btn primary", type: "submit", style: { width: "100%" } }, "Create account →"),
      h("p", { class: "hint", style: { marginTop: "12px" } }, "14 days of Pro, no card needed."));
    submitter(form, async (d) => {
      await post("/api/auth/signup", d);
      await enter("/app");
    });
    root.append(sheet("Create your firm", "Lintel", form,
      h("p", { class: "alt" }, "Already have an account? ", h("a", { href: "/login", "data-link": "" }, "Sign in"))));
  },
};

export const reset = {
  title: () => "Reset password",
  render(root) {
    const token = new URLSearchParams(location.search).get("token");
    if (token) {
      const form = h("form", { class: "auth-card", novalidate: true },
        field("New password", input("password", "password", { autocomplete: "new-password", autofocus: true }), "At least 10 characters"),
        h("button", { class: "btn primary", type: "submit" }, "Set password →"));
      submitter(form, async (d) => {
        await post("/api/auth/reset/confirm", { token, password: d.password });
        app.me = null;
        form.replaceWith(h("div", { class: "auth-card" }, h("p", null, "Your password is set. Every other session was signed out."),
          h("a", { class: "btn primary", href: "/login", "data-link": "" }, "Sign in →")));
      });
      root.append(sheet("Set a new password", "Reset", form));
      return;
    }
    const form = h("form", { class: "auth-card", novalidate: true },
      field("Work email", input("email", "email", { autocomplete: "email", autofocus: true })),
      h("button", { class: "btn primary", type: "submit" }, "Send reset link →"));
    submitter(form, async (d) => {
      await post("/api/auth/reset/request", { email: d.email });
      form.replaceWith(h("div", { class: "auth-card" },
        h("p", null, "If that email has a Lintel account, a reset link is on its way. It works once and expires in 30 minutes.")));
    });
    root.append(sheet("Reset password", "Forgot it?", form,
      h("p", { class: "alt" }, h("a", { href: "/login", "data-link": "" }, "Back to sign in"))));
  },
};

export const invite = {
  title: () => "Join your team",
  async render(root, [token]) {
    let info;
    try {
      info = await get(`/api/invites/${encodeURIComponent(token)}`, { allow401: true });
    } catch (e) {
      root.append(sheet("Invite unavailable", "Invite", h("div", { class: "auth-card" }, h("p", null, e.message),
        h("a", { class: "btn", href: "/login", "data-link": "" }, "Sign in →"))));
      return;
    }
    await refreshMe().catch(() => null);
    const me = app.me;
    const kicker = `${info.firm_name} · as ${info.role}`;
    const form = h("form", { class: "auth-card", novalidate: true });
    if (me && me.user.email.toLowerCase() === info.email.toLowerCase()) {
      form.append(h("p", null, `You're signed in as ${me.user.email}.`), h("button", { class: "btn primary", type: "submit" }, `Join ${info.firm_name} →`));
    } else if (me) {
      form.append(h("p", null, `This invite is for ${info.email}, but you're signed in as ${me.user.email}. Sign out, then open the link again.`));
    } else if (info.has_account) {
      form.append(h("p", { class: "small muted" }, `Sign in as ${info.email} to join.`),
        field("Password", input("password", "password", { autocomplete: "current-password", autofocus: true })),
        h("button", { class: "btn primary", type: "submit" }, "Sign in and join →"));
    } else {
      form.append(h("p", { class: "small muted" }, `You'll sign in with ${info.email}.`),
        field("Name", input("name", "text", { autocomplete: "name", autofocus: true })),
        field("Password", input("password", "password", { autocomplete: "new-password" }), "At least 10 characters"),
        h("button", { class: "btn primary", type: "submit" }, "Join →"));
    }
    submitter(form, async (d) => {
      await post(`/api/invites/${encodeURIComponent(token)}/accept`, d, { allow401: true });
      app.me = null;
      await enter("/app");
    });
    root.append(sheet(`Join ${info.firm_name}`, kicker, form));
  },
};
