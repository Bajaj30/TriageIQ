/* TriageIQ site — plain JavaScript, no framework.
   Every API call goes to the SAME address as the page (e.g. "/predict"). On Vercel, vercel.json forwards those
   paths to the AWS server (a rewrite), so the browser never calls the server directly. Locally, web/dev_server.py
   does the same forwarding. */

"use strict";

// ---------------------------------------------------------------- talking to the API
async function api(path, options = {}, timeoutMs = 20000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);        // a score never takes 20 s; give up cleanly
  try {
    const res = await fetch(path, { ...options, signal: ctrl.signal,
      headers: { "Content-Type": "application/json", ...(options.headers || {}) } });
    let body = null;
    try { body = await res.json(); } catch (_) { /* not JSON (e.g. an HTML error page) */ }
    if (!res.ok) throw Object.assign(new Error("http " + res.status), { status: res.status, body });
    return body;
  } catch (err) {
    if (err.name === "AbortError") throw Object.assign(new Error("timeout"), { status: 0 });
    if (err.status === undefined) err.status = 0;                // network failure
    throw err;
  } finally {
    clearTimeout(timer);
  }
}

function problemText(err) {
  if (err.status === 429) return "Too many requests in a short time — wait a few seconds and try again.";
  if (err.status === 422) return null;                            // handled field by field
  if (err.status === 404) return (err.body && err.body.detail) || "Not found.";
  return "The service is having trouble right now — please try again in a minute.";
}

// ---------------------------------------------------------------- formatting
const $ = (sel, root = document) => root.querySelector(sel);
const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function pct(p) {
  const v = p * 100;
  if (v >= 10) return v.toFixed(1) + "%";
  if (v >= 1) return v.toFixed(1) + "%";
  if (v >= 0.1) return v.toFixed(2) + "%";
  if (v >= 0.01) return v.toFixed(2) + "%";
  return "< 0.01%";
}
function rate(p) { return p < 0.001 ? "under 0.1%" : (p * 100).toFixed(1) + "%"; }
function trend(v) {
  const x = Math.exp(v);
  if (Math.abs(x - 1) < 0.05) return "about the same";
  return x > 1 ? x.toFixed(1) + "× more" : x.toFixed(1) + "× (fewer)";
}
function dateLong(iso) {
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" });
}

// the risk scale: log-spaced from 0.01% to 100%, so 0.1% and 30% are both visible
function scalePos(p) {
  const lo = -4, hi = 0;
  const x = (Math.log10(Math.max(p, 1e-4)) - lo) / (hi - lo);
  return Math.min(Math.max(x, 0), 1) * 100;
}
function scaleHTML(p, threshold) {
  return `
    <div class="scale" aria-hidden="true">
      <div class="scale-track">
        <div class="scale-fill" style="width:${scalePos(p)}%"></div>
        <div class="scale-line" style="left:${scalePos(threshold)}%"><span>senior line ${pct(threshold)}</span></div>
        <div class="scale-dot" style="left:${scalePos(p)}%"></div>
      </div>
      <div class="scale-ticks"><span>0.01%</span><span>0.1%</span><span>1%</span><span>10%</span><span>100%</span></div>
    </div>`;
}

const LABELS = [   // frontend.md, Part B — what the model saw, in plain words
  ["company_issue_rate_s", "This company's payout rate on this kind of problem", rate],
  ["company_rate_s", "This company's payout rate overall", rate],
  ["issue_rate_s", "Payout rate for this kind of problem, all companies", rate],
  ["product_rate_s", "Payout rate for this product", rate],
  ["company_no_history", "Company has no track record yet", (v) => (v ? "yes" : "no")],
  ["company_issue_no_history", "No track record on this kind of problem", (v) => (v ? "yes" : "no")],
  ["company_untimely_rate", "Complaints this company never answered", rate],
  ["company_share_90d", "Its share of all complaints, last 90 days", rate],
  ["company_trend_90d", "Its complaint volume vs the 90 days before", trend],
  ["company_quiet_days", "Days since its previous complaint", (v) => Math.round(v).toLocaleString("en-US")],
];
function ledgerHTML(inputs) {
  return `<dl class="ledger">${LABELS.map(([k, label, f]) =>
    `<div><dt>${label}</dt><dd>${esc(f(inputs[k]))}</dd></div>`).join("")}</dl>`;
}

// the complaint text as the model read it: CFPB blanks become redaction bars
function narrativeHTML(text) {
  return esc(text)
    .replace(/\[REDACTED\]/g, '<span class="redact" title="Hidden by the CFPB">REDACTED</span>')
    .replace(/\[DATE\]/g, '<span class="redact date" title="A date hidden by the CFPB">DATE</span>');
}

// ---------------------------------------------------------------- "Why this score?" — explanations (local only)
// The API explains a score with Shapley values (api/xai.py): a typical complaint's score, then how much each part
// of THIS complaint multiplies the odds. Only offered where the API says it can (/explain/status) — the deployed
// server doesn't carry the extra model files, and Vercel doesn't forward /explain, so the live site never shows it.
const XAI = api("/explain/status").then((r) => !!(r && r.available)).catch(() => false);

function oddsText(f) {
  if (Math.abs(Math.log(f)) < Math.log(1.05)) return "≈ ×1";
  const k = f >= 1 ? f : 1 / f;
  return (f >= 1 ? "×" : "÷") + (k >= 10 ? Math.round(k).toLocaleString("en-US") : k.toFixed(1));
}
const yes = (v) => (v >= 0.5 ? "yes" : "no");
const FACTOR_DETAIL = {   // the input that best describes each group, in plain words
  "The product": (i) => `pays out on ${rate(i.product_rate_s)} of complaints`,
  "The kind of problem": (i) => `pays out on ${rate(i.issue_rate_s)} of complaints`,
  "This company's record on this kind of problem": (i) =>
    i.company_issue_no_history >= 0.5 ? "no track record yet" : `paid on ${rate(i.company_issue_rate_s)}`,
  "This company's record overall": (i) =>
    i.company_no_history >= 0.5 ? "no track record yet" : `paid on ${rate(i.company_rate_s)}`,
  "Complaints this company never answered": (i) => rate(i.company_untimely_rate),
  "How busy this company has been lately": (i) => `volume ${trend(i.company_trend_90d)}`,
  "How common this kind of problem is lately": (i) => `volume ${trend(i.issue_trend_90d)}`,
  "Older American tag": (i) => yes(i.is_older_american),
  "Servicemember tag": (i) => yes(i.is_servicemember),
};

function whyHTML(r) {
  const shown = r.factors.filter((f) => Math.abs(Math.log(f.odds_factor)) >= Math.log(1.05)).slice(0, 7);
  const rest = r.factors.filter((f) => !shown.includes(f));
  const restOdds = rest.reduce((a, f) => a * f.odds_factor, 1);
  const rows = shown.map((f) => ({ name: f.name, f: f.odds_factor, detail: FACTOR_DETAIL[f.name] ? FACTOR_DETAIL[f.name](f.inputs) : "" }));
  if (rest.length) rows.push({ name: `Everything else (${rest.length} more)`, f: restOdds, detail: "" });
  // the zero line sits where the data needs it: at the left edge when every factor raises the odds,
  // further right only as far as the biggest "lowers" factor — so the bars use the whole width
  const up = Math.max(0, ...rows.map((x) => Math.log(x.f)));
  const down = Math.max(0, ...rows.map((x) => -Math.log(x.f)));
  const span = up + down || 1, zero = (down / span) * 100;
  const bar = (f) => {
    const w = (Math.abs(Math.log(f)) / span) * 100, rises = f >= 1;
    return `<span class="why-bar" style="--zero:${zero}%"><i class="${rises ? "up" : "down"}" style="${rises
      ? `left:${zero}%` : `right:${100 - zero}%`};width:${w}%"></i></span>`;
  };
  const row = (x) => `<div class="why-row">
      <div class="why-head"><span class="why-name">${esc(x.name)}${x.detail ? `<small>${esc(x.detail)}</small>` : ""}</span>
        <span class="why-val ${x.f >= 1 ? "up" : "down"}">${oddsText(x.f)}</span></div>
      ${bar(x.f)}</div>`;
  return `
    <section class="why">
      <p class="kicker">Why this score</p>
      <div class="why-grid">
        <div>
          <div class="why-path">
            <div class="why-row edge"><div class="why-head"><span class="why-name">A typical complaint</span><span class="why-val">${pct(r.typical_probability)}</span></div></div>
            ${rows.map(row).join("")}
            <div class="why-row edge"><div class="why-head"><span class="why-name">This complaint</span><span class="why-val">${pct(r.payout_probability)}</span></div></div>
          </div>
          <p class="small">Each line multiplies the odds of a payout. The starting point is the model's score for a typical
            complaint — most complaints are credit-report disputes that almost never pay, so it starts low.</p>
        </div>
        <div>
          <h3>Which sentences mattered</h3>
          <p class="narrative why-text">${highlightHTML(r)}</p>
          <p class="small">Darker red raised the chance, green lowered it (hover a sentence for its effect). Measured by hiding
            sentences and re-reading the rest — ${esc(r.sentence_method)}.${r.words_not_read ? ` The last ${r.words_not_read} words were past what the model reads.` : ""}</p>
        </div>
      </div>
      <p class="why-caveat">${esc(r.caveat)}</p>
      <p class="foot-meta">Explained in ${(r.latency_ms / 1000).toFixed(1)} s · Shapley values over the shipped model · every check passed</p>
    </section>`;
}

function highlightHTML(r) {
  const logs = r.sentences.map((x) => Math.log(x.odds_factor));
  const max = Math.max(...logs.map(Math.abs), 1e-9);
  let html = "", at = 0;
  r.sentences.forEach((x, k) => {
    const rel = logs[k] / max, level = Math.abs(rel) >= 0.6 ? 2 : Math.abs(rel) >= 0.25 ? 1 : 0;
    const cls = level ? `hl ${rel > 0 ? "up" : "down"}${level}` : "hl";
    html += esc(r.text.slice(at, x.start)) +
      `<span class="${cls}" title="${x.odds_factor >= 1 ? "raises" : "lowers"} the odds ${oddsText(x.odds_factor)}">${narrativeHTML(r.text.slice(x.start, x.end))}</span>`;
    at = x.end;
  });
  const tail = r.text.slice(at);
  return html + (r.words_not_read ? `<span class="unread" title="Past the 510 word-pieces the model reads">${narrativeHTML(tail)}</span>` : esc(tail));
}

async function addWhy(slot, request) {   // request: () => Promise of the explanation
  if (!(await XAI)) return;
  slot.innerHTML = `<button class="btn btn-quiet why-btn" type="button">Why this score?</button>`;
  const btn = $("button", slot);
  btn.addEventListener("click", async () => {
    btn.disabled = true; btn.textContent = "Re-reading the complaint…";
    try { slot.innerHTML = whyHTML(await request()); }
    catch (err) {
      btn.disabled = false; btn.textContent = "Why this score?";
      slot.insertAdjacentHTML("beforeend", `<p class="notes">${esc((err.body && err.body.detail) || problemText(err) || "Could not explain this score.")}</p>`);
    }
  });
}

// ---------------------------------------------------------------- shared: live numbers from /model-info
async function loadFacts() {
  const el = $("#facts");
  if (!el) return;
  try {
    const m = await api("/model-info");
    const t = m.tested_on_2024;
    el.innerHTML = `
      <li>Tested on ${t.complaints.toLocaleString("en-US")} complaints from 2024 it never saw</li>
      <li>Reading the riskiest 10% catches ${(t.riskiest_10pct_catches_share_of_payouts * 100).toFixed(1)}% of payouts</li>
      <li>Track records as of ${dateLong(m.features_as_of)}</li>`;
  } catch (_) { /* the facts line is decoration; the page works without it */ }
}

// ---------------------------------------------------------------- page: score a complaint
const EXAMPLES = {
  fee: {
    company: "JPMORGAN CHASE & CO.", product: "Checking or savings account", sub_product: "Checking account",
    issue: "Managing an account", state: "CA", older_american: false, servicemember: false,
    narrative: "On XX/XX/XXXX I noticed two overdraft fees of {$35.00} on my checking account. The deposit that covered the purchase had posted that same morning, so my balance was never negative. I called customer service twice and was told the fees were correct and would not be refunded. I am asking the bank to reverse both charges and explain why they were applied.",
  },
  report: {
    company: "EQUIFAX, INC.", product: "Credit reporting or other personal consumer reports", sub_product: "Credit reporting",
    issue: "Incorrect information on your report", state: "TX", older_american: false, servicemember: false,
    narrative: "There is an account on my credit report that does not belong to me. I have never opened an account with this creditor and I do not recognize the balance. I disputed this item with the credit bureau on XX/XX/XXXX but it is still showing on my report. Please investigate and remove the inaccurate information from my file as required by law.",
  },
};

async function initScore() {
  const form = $("#score-form");
  const productSel = $("#product"), subSel = $("#sub_product"), issueSel = $("#issue"), stateSel = $("#state");
  const company = $("#company"), list = $("#company-list"), text = $("#narrative"), count = $("#word-count");
  let products = [];

  function fillSubs(selected) {
    const p = products.find((x) => x.product === productSel.value);
    subSel.innerHTML = p ? p.sub_products.map((s) => `<option>${esc(s)}</option>`).join("") : "";
    subSel.disabled = !p;
    if (selected) subSel.value = selected;
  }
  function words() { return text.value.split(/\s+/).filter((w) => /^[A-Za-z]/.test(w) && !/^X{2,}/.test(w)).length; }
  function updateCount() {
    const n = words();
    count.textContent = n < 20 ? `${n} words — at least 20 needed` : `${n} words`;
    count.classList.toggle("ok", n >= 20);
  }

  try {
    const [ps, issues, states] = await Promise.all([api("/options/products"), api("/options/issues"), api("/options/states")]);
    products = ps;
    productSel.innerHTML = '<option value="" disabled selected>Choose a product</option>' +
      ps.map((p) => `<option>${esc(p.product)}</option>`).join("");
    issueSel.innerHTML = '<option value="" disabled selected>Choose an issue</option>' +
      issues.map((i) => `<option>${esc(i)}</option>`).join("");
    stateSel.innerHTML = '<option value="">Not given</option>' +
      states.filter((s) => /^[A-Z]{2}$/.test(s)).map((s) => `<option>${esc(s)}</option>`).join("");
  } catch (err) {
    showBanner(problemText(err) || "Could not load the form options.");
  }
  productSel.addEventListener("change", () => fillSubs());
  text.addEventListener("input", updateCount);

  // company suggestions: ask the API after the visitor pauses typing (keeps well under the rate limit)
  let timer = null;
  company.addEventListener("input", () => {
    clearTimeout(timer);
    const q = company.value.trim();
    if (q.length < 2) return;
    timer = setTimeout(async () => {
      try {
        const names = await api("/options/companies?search=" + encodeURIComponent(q));
        list.innerHTML = names.map((n) => `<option value="${esc(n)}"></option>`).join("");
      } catch (_) { /* suggestions are optional */ }
    }, 250);
  });

  document.querySelectorAll("[data-example]").forEach((b) => b.addEventListener("click", () => {
    const ex = EXAMPLES[b.dataset.example];
    company.value = ex.company; productSel.value = ex.product; fillSubs(ex.sub_product);
    issueSel.value = ex.issue; stateSel.value = ex.state;
    $("#older_american").checked = ex.older_american; $("#servicemember").checked = ex.servicemember;
    text.value = ex.narrative; updateCount(); clearErrors();
    form.scrollIntoView({ behavior: "smooth", block: "start" });
  }));

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    clearErrors();
    const body = {
      company: company.value.trim(), product: productSel.value, sub_product: subSel.value, issue: issueSel.value,
      state: stateSel.value || null, older_american: $("#older_american").checked,
      servicemember: $("#servicemember").checked, narrative: text.value,
    };
    const missing = ["company", "product", "sub_product", "issue"].filter((k) => !body[k]);
    if (missing.length) { missing.forEach((k) => fieldError(k, "Required.")); return; }
    if (words() < 20) { fieldError("narrative", "Write at least 20 words — the model was trained on complaints of 20 words or more."); return; }

    const btn = $("#score-btn"), out = $("#assessment");
    btn.disabled = true; btn.textContent = "Scoring…";
    out.innerHTML = '<p class="loading">Reading the complaint and the company’s track record</p>';
    try {
      const r = await api("/predict", { method: "POST", body: JSON.stringify(body) });
      out.innerHTML = assessmentHTML(r);
      addWhy($("#why-slot", out), () => api("/explain", { method: "POST", body: JSON.stringify(body) }, 90000));
    } catch (err) {
      out.innerHTML = emptyAssessment();
      if (err.status === 422) show422(err.body);
      else showBanner(problemText(err));
    } finally {
      btn.disabled = false; btn.textContent = "Score it";
    }
  });
  updateCount();
}

function assessmentHTML(r) {
  const senior = r.route === "senior analyst";
  const notes = (r.notes || []).map((n) => `<p class="notes">${esc(n)}</p>`).join("");
  const cut = r.text_cut_at_512 ? `<p class="notes">This complaint is longer than the model reads; it read the first 510 word-pieces.</p>` : "";
  return `
    <p class="kicker">Assessment</p>
    <p class="big">${pct(r.payout_probability)}</p>
    <p class="big-cap">chance the company pays money to resolve it</p>
    <span class="route ${senior ? "senior" : "template"}">${senior ? "Send to a senior analyst" : "Template response"}</span>
    <p class="route-note">Seniors read the riskiest 10% — complaints at ${pct(r.senior_threshold)} or more.</p>
    ${scaleHTML(r.payout_probability, r.senior_threshold)}
    <h3>What the model saw besides the text</h3>
    ${ledgerHTML(r.inputs)}
    ${notes}${cut}
    <div id="why-slot"></div>
    <p class="foot-meta">Track records as of ${dateLong(r.features_as_of)} · scored in ${Math.round(r.latency_ms)} ms · ${esc(r.model_version)}</p>`;
}
function emptyAssessment() {
  return `<div class="assess-empty"><p>The assessment appears here.</p>
          <p>Fill in a complaint, or start from an example.</p></div>`;
}

const FIELD = { company: "company", product: "product", sub_product: "sub_product", issue: "issue", state: "state", narrative: "narrative" };
function fieldError(name, msg) {
  const input = document.getElementById(FIELD[name] || name);
  if (!input) { showBanner(msg); return; }
  const field = input.closest(".field");
  field.classList.add("has-error");
  const p = document.createElement("p");
  p.className = "field-error"; p.textContent = msg;
  field.appendChild(p);
}
function show422(body) {
  const d = body && body.detail;
  if (Array.isArray(d)) {                                          // Pydantic: [{loc: [..., field], msg}]
    d.forEach((e) => fieldError(e.loc[e.loc.length - 1], e.msg.replace(/^Value error, /, "")));
  } else if (typeof d === "string") {                              // our lookups: "unknown sub_product …"
    const m = d.match(/^unknown (\w+)/);
    if (m && FIELD[m[1]]) fieldError(m[1], d.replace(/^unknown \w+ /, "Not recognised: "));
    else showBanner(d);
  }
}
function clearErrors() {
  document.querySelectorAll(".field-error").forEach((e) => e.remove());
  document.querySelectorAll(".has-error").forEach((e) => e.classList.remove("has-error"));
  const b = $("#banner"); if (b) b.hidden = true;
}
function showBanner(msg) { const b = $("#banner"); if (b) { b.textContent = msg; b.hidden = false; } }

// ---------------------------------------------------------------- page: real 2024 complaints
async function initReal() {
  const buttons = document.querySelectorAll("[data-paid]");
  const out = $("#case-file");
  let current = "";
  async function draw(paid) {
    current = paid;
    buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.paid === paid)));
    out.innerHTML = '<p class="loading">Pulling a complaint from the 2024 files</p>';
    try {
      const r = await api("/complaint/random" + (paid ? "?paid=" + paid : ""));
      out.innerHTML = caseHTML(r);
      addWhy($("#why-slot", out), () => api(`/complaint/${r.complaint_id}/explain`, {}, 90000));
    } catch (err) {
      out.innerHTML = `<p class="banner">${esc(problemText(err) || "Could not load a complaint.")}</p>`;
    }
  }
  buttons.forEach((b) => b.addEventListener("click", () => draw(b.dataset.paid)));
  $("#draw-again").addEventListener("click", () => draw(current));
  draw("");
}

function caseHTML(r) {
  const senior = r.route === "senior analyst";
  let stamp, why, good;
  if (senior && r.actually_paid) { stamp = "Caught"; good = true; why = "Sent to a senior — and the company did pay."; }
  else if (!senior && !r.actually_paid) { stamp = "Right call"; good = true; why = "Left to a template — and the company paid nothing."; }
  else if (!senior && r.actually_paid) { stamp = "Missed"; good = false; why = "Looked low-risk, but the company paid. Often a goodwill decision the text doesn't show."; }
  else { stamp = "False alarm"; good = false; why = "Looked like a payout case, but the company paid nothing."; }
  return `
    <article class="file">
      <p class="file-meta"><strong>${esc(r.company)}</strong> · ${esc(r.product)} · ${esc(r.issue)}<br>
        Received ${dateLong(r.date_received)} · ${esc(r.state)} · CFPB complaint ${r.complaint_id}</p>
      <div class="file-body">
        <p class="narrative">${narrativeHTML(r.narrative)}</p>
        <aside class="verdict">
          <div class="row"><h3>The model said</h3>
            <div class="val">${pct(r.payout_probability)}</div>
            <div class="sub">${senior ? "Send to a senior analyst" : "Template response"}</div></div>
          <div class="row"><h3>What the company did</h3>
            <div class="val" style="font-size:20px">${esc(r.what_actually_happened || "Unknown")}</div>
            <div class="sub">${r.actually_paid ? "Money was paid" : "No money paid"}</div></div>
          <span class="stamp ${good ? "good" : "bad"}">${stamp}</span>
          <p class="stamp-why">${why}</p>
        </aside>
      </div>
      <div id="why-slot"></div>
    </article>`;
}

// ---------------------------------------------------------------- page: how it works
async function initHow() {
  try {
    const m = await api("/model-info");
    const t = m.tested_on_2024;
    $("#stat-wc").textContent = t.within_company_auc.toFixed(2);
    $("#stat-wc-range").textContent = t.within_company_auc_95pct_range.map((x) => Number(x).toFixed(3)).join("–");
    $("#stat-top").textContent = (t.riskiest_10pct_catches_share_of_payouts * 100).toFixed(1) + "%";
    $("#stat-n").textContent = t.complaints.toLocaleString("en-US");
    $("#stat-payouts").textContent = t.payouts.toLocaleString("en-US");
    $("#limits").innerHTML = m.limits.map((l) => `<li>${esc(l)}</li>`).join("");
  } catch (_) { /* static fallbacks stay in place */ }
}

// ---------------------------------------------------------------- start
document.addEventListener("DOMContentLoaded", () => {
  loadFacts();
  const page = document.body.dataset.page;
  if (page === "score") initScore();
  if (page === "real") initReal();
  if (page === "how") initHow();
});
