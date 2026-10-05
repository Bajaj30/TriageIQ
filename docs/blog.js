/* "Finding the two percent" — interactive figures. Plain JavaScript, no libraries.
   Real data comes from data.js (generated from the project's files); the timeline in Figure 5 is a labelled illustration. */
"use strict";

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const SVGNS = "http://www.w3.org/2000/svg";
function el(tag, attrs = {}, parent) {
  const n = document.createElementNS(SVGNS, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (parent) parent.appendChild(n);
  return n;
}
function rng(seed) { let s = seed >>> 0; return () => ((s = (s * 1664525 + 1013904223) >>> 0) / 4294967296); }
function pressed(group, btn) { $$("button", group).forEach((b) => b.setAttribute("aria-pressed", String(b === btn))); }

/* ---------------------------------------------------------------- reading progress + contents */
function chrome() {
  const bar = $("#progress"), toc = $("#toc"), hero = $(".hero");
  const links = $$("#toc a"), sections = links.map((a) => $(a.getAttribute("href")));
  const onScroll = () => {
    const h = document.documentElement;
    bar.style.width = (100 * h.scrollTop / Math.max(1, h.scrollHeight - h.clientHeight)) + "%";
    toc.classList.toggle("show", hero.getBoundingClientRect().bottom < 0);
    let current = 0;
    sections.forEach((s, i) => { if (s && s.getBoundingClientRect().top < window.innerHeight * 0.35) current = i; });
    links.forEach((a, i) => a.classList.toggle("active", i === current));
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();
}

/* ---------------------------------------------------------------- Figure 1: 2 in 100 */
function waffle() {
  const box = $("#waffle"), read = $("#waffle-readout");
  const N = 400, cells = [];
  for (let i = 0; i < N; i++) cells.push(box.appendChild(document.createElement("span")));
  const r = rng(7), order = cells.map((_, i) => i).sort(() => r() - 0.5);
  const modes = {
    story: { hits: 9, text: "<b>9 of 400</b> complaints with a written story ended in a payout — 2.16%, about 1 in 46." },
    all: { hits: 5, text: "<b>5 of 400</b> of all complaints ended in a payout — 1.26%, about 1 in 80." },
  };
  const show = (m) => {
    const hit = new Set(order.slice(0, modes[m].hits));
    cells.forEach((c, i) => c.classList.toggle("hit", hit.has(i)));
    read.innerHTML = modes[m].text;
  };
  $$("[data-waffle]").forEach((b) => b.addEventListener("click", () => { pressed(b.parentElement, b); show(b.dataset.waffle); }));
  show("story");
}

/* ---------------------------------------------------------------- Figure 4: the snowflake */
const TABLES = {
  fact:    { x: 450, y: 260, w: 196, label: "fact_complaint", title: "Complaints — the main table", rows: "4,826,564",
             what: "One row per complaint: which company, product, problem type and state, and the day it arrived. Ids, not names.",
             why: "It never holds the outcome. That lives in the timeline, so the answer can't slip into the model's clues by accident." },
  company: { x: 130, y: 175, w: 150, label: "dim_company", title: "Companies", rows: "4,946",
             what: "Every company complained about: a name and an id number — nothing that changes over time.",
             why: "Four companies appeared twice with different capital letters (“ATM OPS Inc” / “ATM OPS INC”) and were merged." },
  state:   { x: 130, y: 345, w: 150, label: "dim_state", title: "States", rows: "62",
             what: "US states and territories, plus “(not specified)”.",
             why: "A blank becomes an explicit “(not specified)” entry, so no complaint silently vanishes when tables are joined." },
  product: { x: 450, y: 70, w: 150, label: "dim_product", title: "Products", rows: "11",
             what: "Credit card, mortgage, debt collection… 14 names in the raw data become 11 after the August 2023 renames.",
             why: "A renamed product must keep its history, or every company's track record would restart from zero." },
  subprod: { x: 715, y: 70, w: 176, label: "dim_sub_product", title: "Sub-products", rows: "62",
             what: "Finer product types — the snowflake's arm branching off products.",
             why: "The same name sits under several products (“Credit reporting” under three), so a sub-product is identified by its name and its parent." },
  issue:   { x: 450, y: 450, w: 150, label: "dim_issue", title: "Problem types", rows: "93",
             what: "What the complaint is about — “Managing an account”, “Incorrect information on your report”…",
             why: "Not a child of product: 51 of the 93 problem types appear under several products." },
  subiss:  { x: 715, y: 450, w: 176, label: "dim_sub_issue", title: "Sub-problems", rows: "293",
             what: "Finer problem types — the second arm.",
             why: "122,207 complaints have none; each gets an explicit “(not specified)” instead of a blank." },
  story:   { x: 770, y: 205, w: 196, label: "complaint_narrative", title: "Written stories", rows: "1,639,068",
             what: "The customer's own words — only for the 1 in 3 who chose to publish them. What the AI reads.",
             why: "A side table, not a lookup list: each story belongs to exactly one complaint." },
  events:  { x: 770, y: 315, w: 196, label: "complaint_events", title: "Timelines", rows: "14,479,692",
             what: "Three rows per complaint: received → sent to the company → answered. The answer (“Closed with monetary relief”) lives here.",
             why: "Kept apart from the main table on purpose. Built in one pass: 14.5 million rows in under 2 minutes." },
  pxwalk:  { x: 200, y: 70, w: 176, label: "product_crosswalk", title: "Product translation table", rows: "12 rules",
             what: "Old product name → today's name, for the August 2023 form change.", cross: true,
             why: "Re-labels 1,334,958 complaints so their history carries over. Rules kept as data anyone can read, not buried in code." },
  ixwalk:  { x: 200, y: 450, w: 176, label: "issue_crosswalk", title: "Problem-type translation table", rows: "1 rule",
             what: "One renamed problem type: “…a credit reporting company's investigation…” → “…a company's investigation…”.", cross: true,
             why: "Re-labels 337,252 complaints. Not a leak — both names are known on arrival — but a history reset, fixed at the source." },
};
const EDGES = [["company", "fact"], ["state", "fact"], ["product", "fact"], ["subprod", "fact"], ["issue", "fact"], ["subiss", "fact"],
  ["product", "subprod"], ["issue", "subiss"], ["fact", "story"], ["fact", "events"], ["pxwalk", "product", true], ["ixwalk", "issue", true]];

function snowflake() {
  // Lines are drawn in SVG; the tables are ordinary buttons on top. Buttons keep their text and background
  // together, so they stay readable in dark mode, with keyboard access and big tap targets for free.
  const map = $("#snowmap");
  const svg = el("svg", { viewBox: "0 0 900 520", preserveAspectRatio: "none", "aria-hidden": "true" }, map);
  const edges = EDGES.map(([a, b, dash]) => {
    const A = TABLES[a], B = TABLES[b];
    return { a, b, line: el("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "edge" + (dash ? " dash" : "") }, svg) };
  });
  const nodes = {};
  for (const [key, t] of Object.entries(TABLES)) {
    const kind = key === "fact" ? " fact" : (key === "story" || key === "events") ? " side" : t.cross ? " cross" : "";
    const b = document.createElement("button");
    b.type = "button";
    b.className = "tnode" + kind;
    b.setAttribute("aria-label", t.title);
    Object.assign(b.style, { left: (t.x - t.w / 2) / 9 + "%", top: (t.y - 27) / 5.2 + "%",
                             width: t.w / 9 + "%", height: 54 / 5.2 + "%" });
    b.innerHTML = `<span class="nm">${t.label}</span><span class="rw">${t.rows}${t.cross ? "" : " rows"}</span>`;
    for (const ev of ["click", "mouseenter", "focus"]) b.addEventListener(ev, () => select(key));
    map.appendChild(b);
    nodes[key] = b;
  }
  const chips = $("#snow-chips");
  for (const [key, t] of Object.entries(TABLES)) {
    const b = document.createElement("button");
    b.type = "button"; b.textContent = t.title; b.dataset.key = key;
    b.addEventListener("click", () => select(key));
    chips.appendChild(b);
  }
  function select(key) {
    const t = TABLES[key];
    $$("button", chips).forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.key === key)));
    Object.entries(nodes).forEach(([k, n]) => n.classList.toggle("on", k === key));
    edges.forEach((e) => e.line.classList.toggle("on", e.a === key || e.b === key));
    $("#snow-panel").innerHTML = `<p class="t">${t.title}</p><p class="code">${t.label}</p>
      <div class="rows">${t.rows}</div><div class="rows-l">${t.cross ? "translation rules" : "rows, 2022–24"}</div>
      <p>${t.what}</p><p class="why">${t.why}</p>`;
  }
  select("fact");
}

/* ---------------------------------------------------------------- Figure 5: no peeking (illustration) */
function timeline() {
  const W = 900, H = 170, X0 = 30, X1 = 870, DAYS = 730;
  const host = $("#timeline");
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Past complaints of a made-up company on a timeline" }, host);
  const defs = el("defs", {}, svg);
  const pat = el("pattern", { id: "hatch", width: 6, height: 6, patternUnits: "userSpaceOnUse", patternTransform: "rotate(45)" }, defs);
  el("rect", { width: 6, height: 6, class: "hatch-a" }, pat);
  el("line", { x1: 0, y1: 0, x2: 0, y2: 6, class: "hatch-b", "stroke-width": 3 }, pat);
  const xs = (d) => X0 + (X1 - X0) * d / DAYS;
  const pend = el("rect", { y: 26, height: 96, class: "zone-pending" }, svg);
  const fut = el("rect", { y: 26, height: 96, class: "zone-future" }, svg);
  el("line", { x1: X0, x2: X1, y1: 122, y2: 122, class: "baseline" }, svg);
  ["Jan 2022", "Jul 2022", "Jan 2023", "Jul 2023", "Dec 2023"].forEach((lab, i) => {
    const t = el("text", { x: xs([0, 181, 365, 546, 729][i]), y: 142, class: "axis", "text-anchor": i === 0 ? "start" : i === 4 ? "end" : "middle" }, svg);
    t.textContent = lab;
  });
  const r = rng(42), dots = [];
  for (let i = 0; i < 64; i++) {
    const day = Math.floor(r() * DAYS), paid = r() < 0.16;
    dots.push({ day, paid, c: el("circle", { cx: xs(day), cy: 40 + r() * 72, r: 5.2 }, svg) });
  }
  const mk = el("line", { y1: 14, y2: 124, class: "marker" }, svg);
  const mkLab = el("text", { y: 12, class: "marker-label", "text-anchor": "middle" }, svg);
  mkLab.textContent = "complaint arrives";
  const lagLab = el("text", { y: 162, class: "axis", "text-anchor": "middle" }, svg);
  lagLab.textContent = "← 60 days →";
  const slider = $("#tl-day"), read = $("#tl-readout");
  const draw = () => {
    const d = +slider.value, cut = d - 60;
    pend.setAttribute("x", xs(cut)); pend.setAttribute("width", xs(d) - xs(cut));
    fut.setAttribute("x", xs(d)); fut.setAttribute("width", X1 - xs(d));
    mk.setAttribute("x1", xs(d)); mk.setAttribute("x2", xs(d)); mkLab.setAttribute("x", Math.min(Math.max(xs(d), 70), 830));
    lagLab.setAttribute("x", (xs(cut) + xs(d)) / 2);
    let known = 0, paid = 0, pending = 0;
    for (const p of dots) {
      const cls = p.day <= cut ? "dot-known" : p.day < d ? "dot-pending" : "dot-future";
      p.c.setAttribute("class", cls + (p.paid ? " paid" : ""));
      if (p.day <= cut) { known++; if (p.paid) paid++; } else if (p.day < d) pending++;
    }
    const date = new Date(2022, 0, 1 + d).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
    read.innerHTML = `A complaint arriving on <b>${date}</b> may use <b>${known}</b> past complaints (<b>${paid}</b> paid). ` +
      `<b>${pending}</b> more arrived in the last 60 days — their answers aren't in yet, so they don't count.`;
  };
  slider.addEventListener("input", draw);
  draw();
}

/* ---------------------------------------------------------------- Figure 6: smoothing */
function smoothing() {
  const KS = [0, 1, 2, 3, 5, 7, 10, 25, 50, 100, 200, 500], PRIOR = 0.15;
  const COS = { small: { n: 3, paid: 1 }, big: { n: 3000, paid: 1000 } };
  let co = "small";
  const slider = $("#k-slider"), gauge = $("#gauge"), out = $("#smooth-out"), read = $("#smooth-read");
  const pos = (v) => Math.min(Math.max((v - 0.1) / 0.3 * 100, 0), 100);          // the gauge spans 10% … 40%
  gauge.innerHTML = `<div class="ref" style="left:${pos(PRIOR)}%"><span>product's usual 15%</span></div>
                     <div class="ref" style="left:${pos(1 / 3)}%"><span>its own record 33.3%</span></div>
                     <div class="mark" id="g-mark"><span></span></div>`;
  const draw = () => {
    const K = KS[+slider.value], c = COS[co], s = (c.paid + K * PRIOR) / (c.n + K);
    $("#k-value").textContent = K;
    out.textContent = (s * 100).toFixed(1) + "%";
    const m = $("#g-mark"); m.style.left = pos(s) + "%"; m.querySelector("span").textContent = "smoothed";
    read.innerHTML = co === "small"
      ? `With ${c.n} real complaints and <b>K = ${K}</b>, the estimate is ${K === 0 ? "the raw 33.3% — three complaints taken literally" : "pulled toward the product's usual rate"}.`
      : `With ${c.n.toLocaleString("en-US")} real complaints, even <b>K = ${K}</b> barely moves it: real evidence drowns the imaginary complaints.`;
  };
  slider.addEventListener("input", draw);
  $$("[data-co]").forEach((b) => b.addEventListener("click", () => { pressed(b.parentElement, b); co = b.dataset.co; draw(); }));
  draw();
  const measured = [["K = 0", 86.9], ["K = 5", 89.0, true], ["K = 50", 87.5], ["K = 500", 85.0]];
  $("#kbars").innerHTML = measured.map(([k, v, best]) =>
    `<div class="kbar${best ? " best" : ""}"><span>${k}</span><div class="b" style="width:${(v - 80) / 10 * 100}%"></div><span>${v.toFixed(1)}</span></div>`).join("");
}

/* ---------------------------------------------------------------- Figure 7: word-pieces */
function tokens() {
  const T = window.TRIAGE_DATA.tokens, box = $("#tokens");
  const isBlank = (t) => /^(##)?x+$/.test(t) || t === "/";
  const draw = (mode) => {
    const list = T[mode];
    let blanks = 0;
    box.innerHTML = list.map((t) => {
      const esc = t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
      if (t === "[REDACTED]" || t === "[DATE]") { blanks++; return `<span class="marker">${t.slice(1, -1)}</span>`; }
      if (mode === "raw" && isBlank(t)) { blanks++; return `<span class="blank">${esc}</span>`; }
      return `<span>${esc}</span>`;
    }).join("");
    $("#tok-n").textContent = list.length;
    $("#tok-blank").textContent = blanks;
  };
  $$("[data-tok]").forEach((b) => b.addEventListener("click", () => { pressed(b.parentElement, b); draw(b.dataset.tok); }));
  draw("raw");
}

/* ---------------------------------------------------------------- Figure 10: read X%, catch Y% */
function curve() {
  const R = window.TRIAGE_DATA.recall;               // R[i] = % of payouts caught after reading i × 0.5 % of complaints
  const W = 900, H = 330, L = 56, Rt = 20, T = 18, B = 40, XMAX = 50;
  const svg = el("svg", { viewBox: `0 0 ${W} ${H}`, role: "img", "aria-label": "Share of payouts caught against share of complaints read" }, $("#curve"));
  const xs = (k) => L + (W - L - Rt) * k / XMAX, ys = (v) => T + (H - T - B) * (1 - v / 100);
  const grid = el("g", { class: "grid" }, svg);
  [0, 25, 50, 75, 100].forEach((v) => {
    el("line", { x1: L, x2: W - Rt, y1: ys(v), y2: ys(v) }, grid);
    const t = el("text", { x: L - 10, y: ys(v) + 4, class: "axis", "text-anchor": "end" }, svg); t.textContent = v + "%";
  });
  [0, 10, 20, 30, 40, 50].forEach((k) => {
    const t = el("text", { x: xs(k), y: H - 16, class: "axis", "text-anchor": "middle" }, svg); t.textContent = k + "%";
  });
  const xl = el("text", { x: W - Rt, y: H - 2, class: "axis", "text-anchor": "end" }, svg); xl.textContent = "share of complaints read →";
  const pts = [];
  for (let i = 0; i <= XMAX * 2; i++) pts.push([xs(i / 2), ys(R[i])]);
  el("path", { d: `M${xs(0)},${ys(0)} ` + pts.map((p) => `L${p[0]},${p[1]}`).join(" ") + ` L${xs(XMAX)},${ys(0)} Z`, class: "area" }, svg);
  el("path", { d: `M${xs(0)},${ys(0)} L${xs(XMAX)},${ys(XMAX)}`, class: "random" }, svg);
  el("path", { d: "M" + pts.map((p) => p.join(",")).join(" L"), class: "model" }, svg);
  const cur = el("line", { y1: T, y2: H - B, class: "cursor" }, svg);
  const dot = el("circle", { r: 6, class: "pt" }, svg);
  const slider = $("#curve-slider"), read = $("#curve-read");
  const draw = () => {
    const i = +slider.value, k = i / 2, v = R[i];
    cur.setAttribute("x1", xs(k)); cur.setAttribute("x2", xs(k));
    dot.setAttribute("cx", xs(k)); dot.setAttribute("cy", ys(v));
    $("#curve-k").textContent = (k % 1 ? k.toFixed(1) : k) + "%";
    read.innerHTML = `They read <b>${Math.round(150000 * k / 100).toLocaleString("en-US")}</b> of 150,000 complaints and find ` +
      `<b>${v.toFixed(1)}%</b> of the payouts (${Math.round(3471 * v / 100).toLocaleString("en-US")} of 3,471). ` +
      `Reading in random order would find about ${k % 1 ? k.toFixed(1) : k}%.`;
  };
  slider.addEventListener("input", draw);
  draw();
}

/* ---------------------------------------------------------------- dark / light toggle */
function themeToggle() {
  const btn = $("#theme-btn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const isDark = document.documentElement.classList.toggle("dark");
    localStorage.setItem("theme", isDark ? "dark" : "light");
  });
  // If the OS preference changes and the user hasn't explicitly chosen, follow the OS
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", (e) => {
    if (!localStorage.getItem("theme")) {
      document.documentElement.classList.toggle("dark", e.matches);
    }
  });
}

/* ---------------------------------------------------------------- start */
document.addEventListener("DOMContentLoaded", () => {
  chrome();
  themeToggle();
  waffle();
  snowflake();
  timeline();
  smoothing();
  tokens();
  curve();
});
