// Lintel site behaviour. Works without GSAP (content just appears); GSAP adds the motion.
(() => {
  const root = document.documentElement;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  root.classList.add("js");

  // ---- loader: once per visit --------------------------------------------
  const loader = document.querySelector(".loader");
  if (sessionStorage.lintelSeen || reduce) root.classList.add("seen");
  else setTimeout(() => { loader.classList.add("done"); sessionStorage.lintelSeen = 1; }, 1300);

  // ---- mobile menu -------------------------------------------------------
  const top = document.querySelector(".top"), menu = document.querySelector(".menu");
  menu?.addEventListener("click", () => {
    const open = top.classList.toggle("open");
    menu.setAttribute("aria-expanded", open);
  });

  window.addEventListener("load", () => {
    motion();
    demo();
    loop();
    pricing();
    form();
  });

  // ---- scroll motion -----------------------------------------------------
  function motion() {
    const items = document.querySelectorAll(".reveal");
    if (!window.gsap || reduce) { items.forEach((el) => (el.style.opacity = 1, el.style.transform = "none")); return; }
    gsap.registerPlugin(ScrollTrigger);
    const delay = root.classList.contains("seen") ? 0 : 1.2;
    // Failsafe: if animation frames aren't running (background tab, power saving, embedded
    // previews), show everything in its final state instead of leaving it invisible.
    const startFrame = gsap.ticker.frame;
    setTimeout(() => {
      if (gsap.ticker.frame - startFrame > 5) return;
      gsap.globalTimeline.progress(1);
      items.forEach((el) => { el.style.opacity = 1; el.style.transform = "none"; });
      document.querySelectorAll(".plan .wall").forEach((p) => { p.style.strokeDashoffset = 0; });
      document.querySelectorAll(".step").forEach((s) => s.classList.add("on"));
    }, 2600);
    items.forEach((el) => {
      const inHero = el.closest(".hero, .page-hero");
      gsap.to(el, {
        opacity: 1, y: 0, duration: .9, ease: "power3.out",
        delay: inHero ? delay + (+el.dataset.d || 0) : 0,
        scrollTrigger: inHero ? null : { trigger: el, start: "top 86%" },
      });
    });
    // plan walls draw themselves like a pen plotter
    document.querySelectorAll(".plan .wall").forEach((p, i) => {
      const len = p.getTotalLength ? p.getTotalLength() : 600;
      gsap.fromTo(p, { strokeDasharray: len, strokeDashoffset: len }, { strokeDashoffset: 0, duration: 1.4, delay: delay + .2 + i * .08, ease: "power2.inOut" });
    });
    document.querySelectorAll("[data-parallax]").forEach((el) =>
      gsap.to(el, { yPercent: -(+el.dataset.parallax), ease: "none", scrollTrigger: { trigger: el, scrub: true } }));
  }

  // ---- the loop: steps light up as they cross the middle of the screen --------
  function loop() {
    const steps = document.querySelectorAll(".step");
    if (!steps.length) return;
    const io = new IntersectionObserver((es) => es.forEach((e) => e.isIntersecting && e.target.classList.add("on")),
      { rootMargin: "-45% 0px -45% 0px" });
    steps.forEach((s) => io.observe(s));
    if (reduce) steps.forEach((s) => s.classList.add("on"));
  }

  // ---- interactive demo: issue -> revision cloud -> diff -> approval stamp -------
  function demo() {
    const svg = document.querySelector("#demo-plan");
    if (!svg) return;
    const NS = "http://www.w3.org/2000/svg";
    const el = (tag, attrs, parent = svg) => {
      const n = document.createElementNS(NS, tag);
      for (const k in attrs) n.setAttribute(k, attrs[k]);
      parent.appendChild(n);
      return n;
    };
    // doors on the corridor's north wall (y = 190), hinge at x, leaf length w (plan units, ~1 unit = 27 mm)
    const doorLayer = el("g", {});
    const doors = { exam1: { x: 172, w: 28 }, exam2: { x: 302, w: 34 }, wc: { x: 398, w: 26 }, office: { x: 498, w: 32 } };
    function drawDoors() {
      doorLayer.innerHTML = "";
      for (const [id, d] of Object.entries(doors)) {
        const g = el("g", { "data-door": id, class: d.fixed ? "fixed" : "" }, doorLayer);
        el("line", { class: "door-gap", x1: d.x, y1: 190, x2: d.x + d.w, y2: 190 }, g);
        el("line", { class: "door-leaf" + (d.fixed ? " fixed" : ""), x1: d.x, y1: 190, x2: d.x, y2: 190 - d.w }, g);
        el("path", { class: "door-swing", d: `M${d.x + d.w} 190 A${d.w} ${d.w} 0 0 0 ${d.x} ${190 - d.w}` }, g);
      }
    }
    drawDoors();
    const cloudPath = el("path", { class: "cloud" });
    const tag = el("text", { class: "tag" });

    // revision cloud: scalloped outline around a rectangle
    function cloud(x, y, w, h, r = 9) {
      const pts = [];
      const side = (x0, y0, x1, y1) => {
        const n = Math.max(2, Math.round(Math.hypot(x1 - x0, y1 - y0) / (r * 1.6)));
        for (let i = 0; i < n; i++) pts.push([x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n]);
      };
      side(x, y, x + w, y); side(x + w, y, x + w, y + h); side(x + w, y + h, x, y + h); side(x, y + h, x, y);
      let d = `M${pts[0][0]} ${pts[0][1]}`;
      for (let i = 1; i <= pts.length; i++) { const p = pts[i % pts.length]; d += ` A${r} ${r} 0 0 1 ${p[0]} ${p[1]}`; }
      return d;
    }

    const issues = [
      { id: "exam1", title: "Door clear width", where: "Exam 1", ref: "IBC §1010.1.1 per your rule set", val: "760 mm", box: [160, 150, 56, 50], tagAt: [150, 142], door: "exam1", fix: { from: "760 mm", to: "813 mm", w: 31 } },
      { id: "wc", title: "Door clear width", where: "Accessible WC", ref: "IBC §1010.1.1 per your rule set", val: "711 mm", box: [388, 156, 46, 44], tagAt: [372, 148], door: "wc", fix: { from: "711 mm", to: "813 mm", w: 30 } },
      { id: "corr", title: "Corridor clear width", where: "Main corridor", ref: "IBC §1020 per your rule set", val: "1000 mm", box: [140, 186, 300, 48], tagAt: [150, 252], warn: true, advice: "Needs a design decision: move the south wall 118 mm, or reduce the occupant load." },
      { id: "stair", title: "Stair riser height", where: "Stair 1", ref: "IBC §1011.5.2 per your rule set", val: "190 mm", box: [426, 236, 148, 98], tagAt: [430, 352], fix: { from: "18 × 190 mm", to: "20 × 171 mm" } },
    ];
    const list = document.querySelector("#demo-issues"), bar = document.querySelector("#demo-diff"),
      stamp = document.querySelector("#demo-stamp"), log = document.querySelector("#demo-log");
    let current = null;
    const time = () => new Date().toTimeString().slice(0, 5);

    function render() {
      list.innerHTML = issues.map((i) => `
        <button class="issue ${i.done ? "ok" : i.warn ? "warn" : ""}" data-id="${i.id}" aria-pressed="${current === i.id}">
          <span class="sev"></span>
          <span><b>${i.done ? "Fixed" : i.title}</b> · ${i.where}<small>${i.done ? "approved by you · undoable" : i.ref}</small></span>
          <span class="val">${i.done ? i.fix.to : i.val}</span>
        </button>`).join("");
      list.querySelectorAll(".issue").forEach((b) => b.onclick = () => select(b.dataset.id));
    }
    function select(id) {
      const i = issues.find((x) => x.id === id);
      current = id;
      stamp.classList.remove("on");
      cloudPath.setAttribute("d", cloud(...i.box));
      cloudPath.classList.toggle("on", !i.done);
      tag.textContent = i.done ? "" : `${i.val}${i.fix ? " → " + i.fix.to : ""}`;
      tag.setAttribute("x", i.tagAt[0]); tag.setAttribute("y", i.tagAt[1]);
      tag.classList.toggle("on", !i.done);
      if (i.done) bar.classList.remove("on");
      else {
        bar.classList.add("on");
        bar.innerHTML = i.fix
          ? `<span class="mono">${i.where}</span><span class="from">${i.fix.from}</span><span>→</span><span class="to">${i.fix.to}</span><span class="spacer"></span>
             <button class="btn btn-go" data-a="ok">Approve</button><button class="btn btn-chalk" data-a="no">Reject</button>`
          : `<span class="small muted">${i.advice}</span>`;
        bar.querySelectorAll("button").forEach((b) => b.onclick = () => decide(i, b.dataset.a === "ok"));
      }
      render();
    }
    function decide(i, ok) {
      cloudPath.classList.remove("on"); tag.classList.remove("on"); bar.classList.remove("on");
      if (ok) {
        i.done = true;
        if (i.door) { doors[i.door].w = i.fix.w; doors[i.door].fixed = true; drawDoors(); }
        stamp.classList.remove("on"); void stamp.offsetWidth; stamp.classList.add("on");
        log.textContent = `${time()}  you approved "${i.title}, ${i.where}" · applied in one undo step · logged`;
      } else {
        log.textContent = `${time()}  you rejected "${i.title}, ${i.where}" · model unchanged · logged`;
      }
      current = null;
      render();
    }
    render();
    setTimeout(() => current || select("wc"), root.classList.contains("seen") ? 1600 : 2800);
  }

  // ---- pricing toggle ----------------------------------------------------
  function pricing() {
    const btns = document.querySelectorAll(".toggle button");
    btns.forEach((b) => b.onclick = () => {
      btns.forEach((x) => x.setAttribute("aria-pressed", x === b));
      const yearly = b.dataset.cycle === "yearly";
      document.querySelectorAll("[data-month]").forEach((p) => {
        p.firstChild.textContent = "$" + (yearly ? p.dataset.year : p.dataset.month);
        p.nextElementSibling.textContent = yearly ? "billed yearly" : "billed monthly";
      });
    });
  }

  // ---- pilot form --------------------------------------------------------
  function form() {
    const f = document.querySelector("#pilot");
    if (!f) return;
    const msg = f.querySelector(".form-msg");
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      msg.className = "form-msg"; msg.textContent = "Sending…";
      try {
        const r = await fetch("/api/waitlist", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(Object.fromEntries(new FormData(f))) });
        const body = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(body.detail || "Couldn't send. Try again in a minute.");
        f.reset();
        msg.className = "form-msg ok"; msg.textContent = "Thanks. You're on the pilot list; we'll email you when your host tool is ready.";
      } catch (err) {
        msg.className = "form-msg err"; msg.textContent = err.message === "Failed to fetch" ? "Couldn't reach Lintel. Try again in a minute." : err.message;
      }
    });
  }
})();
