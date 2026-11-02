// Lintel's drawings, generated as SVG: the logo mark and an architectural elevation
// (stippled concrete, hatching, glazing, ink trees, the accent sun). Seeded, so a page
// draws the same picture every time.
import { s } from "./lib.js";

export function logoMark(size = 30) {
  // a lintel: one beam with depth, resting on two posts
  return s("svg", { viewBox: "0 0 40 40", width: size, height: size, fill: "none", stroke: "currentColor", "stroke-width": "1.7", "aria-hidden": "true", class: "logo-svg" },
    s("path", { d: "M3 13h28v6H3z" }),
    s("path", { d: "M3 13l6-6h28l-6 6M31 19l6-6v-6" }),
    s("path", { d: "M8 19v17h5V19M21 19v17h5V19" }),
    s("path", { d: "M3 36h28", stroke: "var(--accent)" }));
}

function rng(seed) {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let r = Math.imul(t ^ (t >>> 15), 1 | t);
    r ^= r + Math.imul(r ^ (r >>> 7), 61 | r);
    return ((r ^ (r >>> 14)) >>> 0) / 4294967296;
  };
}

let uid = 0;

function patterns(R, id) {
  const dots = (n, rmax) => Array.from({ length: n }, () => s("circle", { cx: (R() * 40).toFixed(1), cy: (R() * 40).toFixed(1), r: (0.35 + R() * rmax).toFixed(2), fill: "var(--ink)" }));
  return s("defs", null,
    s("pattern", { id: `${id}-stip`, width: 40, height: 40, patternUnits: "userSpaceOnUse" }, s("rect", { width: 40, height: 40, fill: "#efeee8" }), dots(46, 0.55)),
    s("pattern", { id: `${id}-dense`, width: 40, height: 40, patternUnits: "userSpaceOnUse" }, s("rect", { width: 40, height: 40, fill: "#7d7c78" }), dots(120, 0.7)),
    s("pattern", { id: `${id}-hatch`, width: 8, height: 8, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" },
      s("rect", { width: 8, height: 8, fill: "#ecebe5" }), s("line", { x1: 0, y1: 0, x2: 0, y2: 8, stroke: "var(--ink)", "stroke-width": "0.7", opacity: ".55" })),
    s("linearGradient", { id: `${id}-glass`, x1: 0, y1: 0, x2: 1, y2: 1 },
      s("stop", { offset: "0", "stop-color": "#f4f3ee" }), s("stop", { offset: "1", "stop-color": "#c9c8c2" })));
}

function tree(R, x, y, h, leafy) {
  const g = s("g", { class: "tree" });
  const branch = (x0, y0, len, ang, w, depth) => {
    const x1 = x0 + Math.cos(ang) * len, y1 = y0 - Math.sin(ang) * len;
    g.append(s("path", { d: `M${x0.toFixed(1)} ${y0.toFixed(1)}Q${((x0 + x1) / 2 + (R() - 0.5) * len * 0.3).toFixed(1)} ${((y0 + y1) / 2).toFixed(1)} ${x1.toFixed(1)} ${y1.toFixed(1)}`,
      stroke: "var(--ink)", "stroke-width": Math.max(0.5, w).toFixed(2), fill: "none", "stroke-linecap": "round" }));
    if (depth === 0 || len < 5) {
      if (leafy) for (let i = 0; i < 5; i++) {
        g.append(s("circle", { cx: (x1 + (R() - 0.5) * 18).toFixed(1), cy: (y1 + (R() - 0.5) * 12).toFixed(1), r: (2 + R() * 5).toFixed(1), fill: "var(--ink)", opacity: (0.75 + R() * 0.25).toFixed(2) }));
      }
      return;
    }
    const n = 2 + (R() < 0.35 ? 1 : 0);
    for (let i = 0; i < n; i++) {
      branch(x1, y1, len * (0.62 + R() * 0.18), ang + (i - (n - 1) / 2) * (0.42 + R() * 0.3) + (R() - 0.5) * 0.25, w * 0.66, depth - 1);
    }
  };
  branch(x, y, h * 0.36, Math.PI / 2 + (R() - 0.5) * 0.12, leafy ? 4.2 : 3.4, leafy ? 6 : 7);
  return g;
}

/** An original elevation: a low glazed pavilion, a stippled upper box, a dark stair core, a side wing, trees. */
export function elevation({ seed = 7, sun = true, markers = true, className = "" } = {}) {
  const R = rng(seed);
  const id = `art${++uid}`;
  const L = "var(--ink)";
  const line = (x1, y1, x2, y2, w = 1.2) => s("line", { x1, y1, x2, y2, stroke: L, "stroke-width": w });
  const rect = (x, y, w, h, fill, sw = 1.4) => s("rect", { x, y, width: w, height: h, fill, stroke: L, "stroke-width": sw });
  const svg = s("svg", { viewBox: "0 0 1200 520", class: ["art", className].join(" "), role: "img", "aria-label": "Line drawing of a building elevation", preserveAspectRatio: "xMidYMid meet" });
  svg.append(patterns(R, id));
  const g = s("g");
  if (sun) g.append(s("circle", { cx: 860, cy: 150, r: 92, fill: "var(--accent)" }));
  // upper stippled box with a ribbon window
  g.append(rect(300, 150, 520, 120, `url(#${id}-stip)`));
  g.append(rect(350, 182, 360, 52, `url(#${id}-glass)`, 1.6));
  for (let x = 410; x < 710; x += 60) g.append(line(x, 182, x, 234, 1.1));
  // glazed pavilion below with mullions and a hatched return
  g.append(rect(330, 270, 330, 170, `url(#${id}-glass)`));
  for (let x = 385; x < 660; x += 55) g.append(line(x, 270, x, 440, 1.2));
  g.append(rect(660, 270, 70, 170, `url(#${id}-hatch)`, 1.1));
  // dark stair core with small windows
  g.append(rect(730, 110, 64, 330, `url(#${id}-dense)`, 1.6));
  for (let y = 135; y < 420; y += 38) g.append(rect(752, y, 20, 22, "#f2f1eb", 1.1));
  // side wing
  g.append(rect(794, 190, 250, 250, `url(#${id}-stip)`));
  g.append(rect(794, 270, 250, 16, `url(#${id}-hatch)`, 0.9));
  for (const x of [830, 900, 970]) g.append(rect(x, 210, 40, 40, `url(#${id}-glass)`, 1.3));
  g.append(rect(905, 320, 82, 120, `url(#${id}-dense)`, 1.4));
  // plinth, steps and ground
  g.append(rect(240, 440, 820, 26, "#efeee8", 1.2));
  for (let i = 0; i < 5; i++) g.append(rect(170 + i * 12, 440 + i * 5.2, 70 - i * 12, 5.2, "#efeee8", 0.9));
  g.append(line(60, 466, 1150, 466, 1.6));
  // trees
  g.append(tree(R, 150, 466, 360, false));
  g.append(tree(R, 1105, 466, 290, true));
  g.append(tree(R, 1150, 466, 210, true));
  // issue marks on the drawing, as the app would flag them
  if (markers) {
    for (const [x, y] of [[540, 196], [395, 330], [760, 236], [940, 372]]) g.append(s("rect", { x: x - 7, y: y - 7, width: 14, height: 14, fill: "var(--accent)", opacity: ".42" }));
    g.append(s("circle", { cx: 260, cy: 236, r: 4, fill: "var(--accent)" }));
  }
  svg.append(g);
  return svg;
}

/** A small floor-plan thumbnail drawn from room outlines (mm, y up), for project cards. */
export function planThumb(outlines, flagged = []) {
  const svg = s("svg", { class: "thumb", viewBox: "0 0 100 60", preserveAspectRatio: "xMidYMid meet", "aria-hidden": "true" });
  const pts = outlines.flat();
  if (!pts.length) {
    svg.append(s("path", { d: "M20 12h38v14h22v22H20z", fill: "none", stroke: "var(--ghost)", "stroke-width": "2.2", "stroke-dasharray": "4 3" }));
    return svg;
  }
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
  const k = Math.min(84 / (x1 - x0 || 1), 44 / (y1 - y0 || 1));
  const ox = 50 - ((x1 - x0) * k) / 2, oy = 30 + ((y1 - y0) * k) / 2;
  const P = ([x, y]) => `${(ox + (x - x0) * k).toFixed(1)},${(oy - (y - y0) * k).toFixed(1)}`;
  outlines.forEach((o, i) => svg.append(s("polygon", { points: o.map(P).join(" "), fill: flagged.includes(i) ? "var(--accent-soft)" : "none", stroke: "var(--wall)", "stroke-width": "1.6", "stroke-linejoin": "miter" })));
  flagged.slice(0, 6).forEach((i) => {
    const o = outlines[i];
    const c = [o.reduce((a, p) => a + p[0], 0) / o.length, o.reduce((a, p) => a + p[1], 0) / o.length];
    const [cx, cy] = P(c).split(",").map(Number);
    svg.append(s("rect", { x: cx - 2.2, y: cy - 2.2, width: 4.4, height: 4.4, fill: "var(--accent)" }));
  });
  return svg;
}
