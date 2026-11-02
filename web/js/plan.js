// Plan canvas: SVG drawn from the snapshot (mm, CAD y-up). Pan with space+drag or the middle button,
// zoom with the wheel or pinch, F fits, drag a box to select. Crosshair + X/Y readout inside the canvas only.
import { clear, h, num, reducedMotion, s } from "./lib.js";

const PAD = 0.06;

export function createPlan({ onSelectElement, onSelectIssue, onBoxSelect }) {
  const svg = s("svg", { class: "plan", role: "img", "aria-label": "Floor plan. Every flagged element is also in the issue list.", preserveAspectRatio: "xMidYMid meet" });
  const gWalls = s("g"), gRooms = s("g"), gDoors = s("g"), gStairs = s("g"), gLabels = s("g"), gMarks = s("g"), gSel = s("g");
  svg.append(gRooms, gWalls, gStairs, gDoors, gLabels, gMarks, gSel);
  const chH = h("div", { class: "crosshair h" }), chV = h("div", { class: "crosshair v" });
  const readout = h("div", { class: "readout" });
  const label = h("div", { class: "plan-label micro muted" }, "Plan");
  const tools = h("div", { class: "plan-tools" },
    h("button", { title: "Zoom in (+)", "aria-label": "Zoom in", onclick: () => zoomBy(0.75) }, "+"),
    h("button", { title: "Zoom out (−)", "aria-label": "Zoom out", onclick: () => zoomBy(1 / 0.75) }, "−"),
    h("button", { title: "Fit (F)", "aria-label": "Fit plan", onclick: () => fit(true) }, "F"));
  const emptyEl = h("div", { class: "plan-empty", hidden: true });
  const wrap = h("div", { class: "plan-wrap col" },
    h("div", { class: "ruler top" }), h("div", { class: "ruler bottom" }), h("div", { class: "ruler left" }), h("div", { class: "ruler right" }),
    ["tl", "tr", "bl", "br"].map((c) => h("span", { class: ["corner", c], "aria-hidden": "true" }, "+")),
    label, svg, chH, chV, readout, tools, emptyEl);

  let view = { x: 0, y: 0, w: 1000, h: 1000 };
  let bounds = null;
  let elements = [], byId = {}, issues = [];
  let selected = { element: null, issue: null };
  let seenIssues = null;
  let anim = null;

  // ---- drawing -------------------------------------------------------------
  const Y = (y) => -y;
  const pts = (outline) => outline.map(([x, y]) => `${x},${Y(y)}`).join(" ");
  const centroid = (o) => [o.reduce((a, p) => a + p[0], 0) / o.length, o.reduce((a, p) => a + p[1], 0) / o.length];

  function anchor(el) {
    if (!el) return null;
    if (el.geom?.location) return el.geom.location;
    if (el.geom?.outline?.length) return centroid(el.geom.outline);
    if (el.geom?.start && el.geom?.end) return [(el.geom.start[0] + el.geom.end[0]) / 2, (el.geom.start[1] + el.geom.end[1]) / 2];
    return null;
  }

  function doorFrame(door) {
    // orient the door along the nearest edge of the first room it opens into, swinging into that room
    const [px, py] = door.geom.location;
    const room = (door.props.rooms || []).map((r) => byId[r]).find((r) => r?.geom?.outline?.length);
    let d = [1, 0], n = [0, 1];
    if (room) {
      const o = room.geom.outline;
      let best = Infinity;
      for (let i = 0; i < o.length; i++) {
        const a = o[i], b = o[(i + 1) % o.length];
        const vx = b[0] - a[0], vy = b[1] - a[1], len = Math.hypot(vx, vy) || 1;
        const t = Math.max(0, Math.min(1, ((px - a[0]) * vx + (py - a[1]) * vy) / (len * len)));
        const dist = Math.hypot(a[0] + t * vx - px, a[1] + t * vy - py);
        if (dist < best) { best = dist; d = [vx / len, vy / len]; }
      }
      const [cx, cy] = centroid(o);
      n = [-d[1], d[0]];
      if ((cx - px) * n[0] + (cy - py) * n[1] < 0) n = [-n[0], -n[1]];
    }
    return { p: [px, py], d, n };
  }

  function draw() {
    const flagged = new Map();
    issues.forEach((i) => { if (!flagged.has(i.element)) flagged.set(i.element, i.severity); });
    clear(gWalls); clear(gRooms); clear(gDoors); clear(gStairs); clear(gLabels); clear(gMarks);
    for (const el of elements) {
      const cls = (base) => [base, flagged.has(el.id) && "flag", selected.element === el.id && "sel"];
      if (el.type === "wall" && el.geom?.start && el.geom?.end) {
        gWalls.append(s("line", { class: "wall", x1: el.geom.start[0], y1: Y(el.geom.start[1]), x2: el.geom.end[0], y2: Y(el.geom.end[1]),
          "stroke-width": el.props.thickness_mm || 150 }));
      } else if (el.type === "room" && el.geom?.outline?.length) {
        const poly = s("polygon", { class: cls("room"), points: pts(el.geom.outline), dataset: { id: el.id } }, s("title", null, el.props.name || el.id));
        gRooms.append(poly);
        const [cx, cy] = centroid(el.geom.outline);
        gLabels.append(s("text", { class: "room-name", x: cx, y: Y(cy), "text-anchor": "middle", "dominant-baseline": "central" }, el.props.name || el.id));
      } else if (el.type === "door" && el.geom?.location) {
        const { p, d, n } = doorFrame(el);
        const w = Number(el.props.clear_width_mm) || 900;
        const hinge = [p[0] - d[0] * w / 2, p[1] - d[1] * w / 2];
        const end = [p[0] + d[0] * w / 2, p[1] + d[1] * w / 2];
        const leafEnd = [hinge[0] + n[0] * w, hinge[1] + n[1] * w];
        const sweep = (d[0] * n[1] - d[1] * n[0]) > 0 ? 0 : 1;
        const g = s("g", { class: cls("door"), dataset: { id: el.id } },
          s("title", null, `${el.props.name || el.id} · ${num(w)} mm`),
          s("circle", { class: "hit", cx: p[0], cy: Y(p[1]), r: w * 0.7 }),
          s("line", { class: "leaf", x1: hinge[0], y1: Y(hinge[1]), x2: leafEnd[0], y2: Y(leafEnd[1]) }),
          s("path", { class: "swing", d: `M ${leafEnd[0]} ${Y(leafEnd[1])} A ${w} ${w} 0 0 ${sweep} ${end[0]} ${Y(end[1])}` }));
        gDoors.append(g);
        if (el.props.exit) {
          gLabels.append(s("text", { class: "exit-tag", x: p[0] - n[0] * w * 0.9, y: Y(p[1] - n[1] * w * 0.9), "text-anchor": "middle", "dominant-baseline": "central" }, "EXIT"));
        }
      } else if (el.type === "stair" && el.geom?.location) {
        const [x, y] = el.geom.location;
        const width = Number(el.props.width_mm) || 1200;
        const tread = Number(el.props.tread_mm) || 280;
        const n = Math.max(2, Math.min(40, (Number(el.props.risers) || 12) - 1));
        const len = tread * n;
        const g = s("g", { class: cls("stair"), dataset: { id: el.id } }, s("title", null, el.props.name || el.id),
          s("rect", { x: x - width / 2, y: Y(y) - len / 2, width, height: len }));
        for (let i = 1; i < n; i++) g.append(s("line", { x1: x - width / 2, x2: x + width / 2, y1: Y(y) - len / 2 + i * tread, y2: Y(y) - len / 2 + i * tread }));
        gStairs.append(g);
      }
    }
    const countAt = {};
    issues.forEach((i, n) => {
      const a = anchor(byId[i.element]);
      if (!a) return;
      const k = countAt[i.element] = (countAt[i.element] || 0) + 1;
      const isNew = seenIssues && !seenIssues.has(i.id) && !reducedMotion();
      const g = s("g", { class: ["mk", i.severity, selected.issue === i.id && "sel", isNew && "new"], dataset: { issue: i.id, x: a[0], y: a[1], k: k - 1 } },
        s("title", null, `${n + 1}. ${i.rule_name}: ${i.element_name}`),
        s("rect", { x: -7, y: -7, width: 14, height: 14 }),
        s("rect", { class: "ring", x: -11, y: -11, width: 22, height: 22 }),
        s("text", { x: 0, y: 0.5, "font-size": 9 }, String(n + 1)));
      gMarks.append(g);
    });
    seenIssues = new Set(issues.map((i) => i.id));
    applyView();
  }

  // ---- view ----------------------------------------------------------------
  function pxRatio() {
    const r = svg.getBoundingClientRect();
    if (!r.width || !r.height) return view.w / 1000;
    return Math.max(view.w / r.width, view.h / r.height);
  }

  function applyView() {
    svg.setAttribute("viewBox", `${view.x} ${view.y} ${view.w} ${view.h}`);
    const k = pxRatio();
    gLabels.setAttribute("font-size", 11 * k);
    for (const g of gMarks.children) {
      const x = Number(g.dataset.x), y = Number(g.dataset.y), i = Number(g.dataset.k);
      g.setAttribute("transform", `translate(${x + i * 18 * k} ${Y(y) - 16 * k}) scale(${k})`);
    }
  }

  function computeBounds() {
    const xs = [], ys = [];
    for (const el of elements) {
      const g = el.geom || {};
      for (const p of [...(g.outline || []), g.location, g.start, g.end].filter(Boolean)) { xs.push(p[0]); ys.push(p[1]); }
    }
    if (!xs.length) return null;
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    const w = Math.max(x1 - x0, 1000), hh = Math.max(y1 - y0, 1000);
    return { x: x0 - w * PAD, y: Y(y1) - hh * PAD, w: w * (1 + 2 * PAD), h: hh * (1 + 2 * PAD) };
  }

  function animateTo(target, ms = 300) {
    cancelAnimationFrame(anim);
    if (reducedMotion() || ms === 0) { view = target; applyView(); return; }
    const from = { ...view }, t0 = performance.now();
    const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
    const step = (now) => {
      const t = Math.min(1, (now - t0) / ms), e = ease(t);
      view = { x: from.x + (target.x - from.x) * e, y: from.y + (target.y - from.y) * e, w: from.w + (target.w - from.w) * e, h: from.h + (target.h - from.h) * e };
      applyView();
      if (t < 1) anim = requestAnimationFrame(step);
    };
    anim = requestAnimationFrame(step);
  }

  function fit(animated) {
    if (!bounds) return;
    animated ? animateTo({ ...bounds }) : (view = { ...bounds }, applyView());
  }

  function zoomBy(f, cx, cy) {
    const px = cx ?? view.x + view.w / 2, py = cy ?? view.y + view.h / 2;
    const w = Math.min(Math.max(view.w * f, 300), (bounds?.w || 1e5) * 8);
    const real = w / view.w;
    view = { x: px - (px - view.x) * real, y: py - (py - view.y) * real, w, h: view.h * real };
    applyView();
  }

  function zoomTo(elementId) {
    const el = byId[elementId];
    const a = anchor(el);
    if (!a) return;
    let w = 12000;
    if (el.geom?.outline) {
      const xs = el.geom.outline.map((p) => p[0]), ys = el.geom.outline.map((p) => p[1]);
      w = Math.max(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) * 1.8 + 4000;
    }
    const r = svg.getBoundingClientRect();
    const hh = r.width ? w * (r.height / r.width) : w;
    animateTo({ x: a[0] - w / 2, y: Y(a[1]) - hh / 2, w, h: hh });
  }

  function toSvg(evt) {
    const pt = svg.createSVGPoint();
    pt.x = evt.clientX; pt.y = evt.clientY;
    const m = svg.getScreenCTM();
    return m ? pt.matrixTransform(m.inverse()) : { x: 0, y: 0 };
  }

  // ---- interaction ---------------------------------------------------------
  let space = false, drag = null;
  const onKey = (e) => {
    if (e.code !== "Space" || /input|textarea|select/i.test(document.activeElement?.tagName || "")) return;
    if (e.type === "keydown" && wrap.matches(":hover")) { space = true; wrap.classList.add("space"); e.preventDefault(); }
    if (e.type === "keyup") { space = false; wrap.classList.remove("space"); }
  };
  window.addEventListener("keydown", onKey);
  window.addEventListener("keyup", onKey);
  const onResize = () => applyView();
  window.addEventListener("resize", onResize);

  svg.addEventListener("wheel", (e) => {
    e.preventDefault();
    const p = toSvg(e);
    const f = Math.exp((e.ctrlKey ? e.deltaY * 3 : e.deltaY) * 0.0015);
    zoomBy(f, p.x, p.y);
  }, { passive: false });

  svg.addEventListener("pointerdown", (e) => {
    if (e.button === 1 || (e.button === 0 && space)) {
      drag = { mode: "pan", sx: e.clientX, sy: e.clientY, view: { ...view }, k: pxRatio() };
      wrap.classList.add("panning");
    } else if (e.button === 0) {
      const p = toSvg(e);
      drag = { mode: "box", sx: e.clientX, sy: e.clientY, p0: p, target: e.target };
    } else return;
    svg.setPointerCapture(e.pointerId);
    e.preventDefault();
  });
  svg.addEventListener("pointermove", (e) => {
    const r = wrap.getBoundingClientRect();
    const p = toSvg(e);
    wrap.classList.add("hovering");
    chH.style.top = `${e.clientY - r.top}px`;
    chV.style.left = `${e.clientX - r.left}px`;
    readout.textContent = `X ${num(p.x)} MM · Y ${num(-p.y)} MM`;
    const flip = e.clientX - r.left > r.width - 190;
    readout.style.left = `${e.clientX - r.left + (flip ? -180 : 14)}px`;
    readout.style.top = `${e.clientY - r.top + 14}px`;
    if (!drag) return;
    if (drag.mode === "pan") {
      view = { ...drag.view, x: drag.view.x - (e.clientX - drag.sx) * drag.k, y: drag.view.y - (e.clientY - drag.sy) * drag.k };
      applyView();
    } else if (Math.hypot(e.clientX - drag.sx, e.clientY - drag.sy) > 4) {
      const x = Math.min(drag.p0.x, p.x), y = Math.min(drag.p0.y, p.y);
      clear(gSel, s("rect", { class: "selbox", x, y, width: Math.abs(p.x - drag.p0.x), height: Math.abs(p.y - drag.p0.y) }));
      drag.p1 = p;
    }
  });
  svg.addEventListener("pointerleave", () => wrap.classList.remove("hovering"));
  svg.addEventListener("pointerup", (e) => {
    if (!drag) return;
    const d = drag;
    drag = null;
    wrap.classList.remove("panning");
    clear(gSel);
    if (d.mode !== "box") return;
    if (d.p1) {
      const x0 = Math.min(d.p0.x, d.p1.x), x1 = Math.max(d.p0.x, d.p1.x), y0 = Math.min(d.p0.y, d.p1.y), y1 = Math.max(d.p0.y, d.p1.y);
      const inside = elements.filter((el) => { const a = anchor(el); return a && a[0] >= x0 && a[0] <= x1 && Y(a[1]) >= y0 && Y(a[1]) <= y1; });
      onBoxSelect?.(inside.map((el) => el.id));
      return;
    }
    const mk = d.target.closest?.(".mk");
    if (mk) return onSelectIssue?.(mk.dataset.issue);
    const hit = d.target.closest?.("[data-id]");
    onSelectElement?.(hit ? hit.dataset.id : null);
  });

  return {
    el: wrap,
    setData(els, iss, { refit = false } = {}) {
      elements = els || [];
      byId = Object.fromEntries(elements.map((e) => [e.id, e]));
      issues = iss || [];
      const first = !bounds;
      bounds = computeBounds();
      emptyEl.hidden = !!bounds;
      svg.style.visibility = bounds ? "visible" : "hidden";
      if (!bounds) clear(emptyEl, h("div", null, h("p", { class: "label" }, "No model yet"),
        h("p", { class: "small muted" }, "The plan appears after the first sync from your CAD plugin.")));
      draw();
      if ((first || refit) && bounds) requestAnimationFrame(() => fit(false));
    },
    select(elementId, issueId) {
      selected = { element: elementId || null, issue: issueId || null };
      for (const n of svg.querySelectorAll("[data-id]")) n.classList.toggle("sel", n.dataset.id === selected.element);
      for (const n of gMarks.children) n.classList.toggle("sel", n.dataset.issue === selected.issue);
    },
    zoomTo, fit, zoomBy,
    setLabel(text) { label.textContent = text; },
    destroy() {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("keyup", onKey);
      window.removeEventListener("resize", onResize);
      cancelAnimationFrame(anim);
    },
  };
}
