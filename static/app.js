/* DataPilot front-end: vanilla JS, no build step. */
const $ = (s, el = document) => el.querySelector(s);
const PALETTE = ["#0e8f86", "#e07a1f", "#3b6fd4", "#b93838", "#7a5bc7", "#2f9e44", "#c2a100", "#6b7c8c"];
const STARTERS = [
  "Summarise the uploaded data.", "What are the most important patterns?",
  "Show the key trends over time.", "Which categories have the highest values?",
  "What data-quality issues should I know about?", "Generate SQL for this analysis.",
];
const state = { sid: null, tables: [], selectedTables: new Set(), busy: false };

/* ---------- tiny DOM helper ---------- */
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(kid));
  return el;
}
const fmt = (v) => (typeof v === "number" ? (Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 2 })) : v ?? "");
const md = (text) => { const d = h("div", { class: "prose" }); d.innerHTML = DOMPurify.sanitize(marked.parse(text || "")); return d; };

async function api(path, opts = {}) {
  const res = await fetch("/api" + path, opts);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (_) {}
    const err = new Error(detail); err.status = res.status; throw err;
  }
  return res;
}
const json = async (path, opts) => (await api(path, opts)).json();
const post = (path, body) => json(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

/* ---------- session bootstrap ---------- */
async function init() {
  try {
    const health = await json("/health");
    $("#health").textContent = `${health.provider} · ${health.model}`;
    if (!health.llm_configured) showBanner("No LLM API key is configured, so questions can't be answered yet. Copy .env.example to .env, add a key and restart. Uploads, dashboard and data-quality checks still work.");
  } catch (_) { showBanner("Cannot reach the server."); }

  state.sid = localStorage.getItem("dp_sid");
  let data = null;
  if (state.sid) { try { data = await json(`/sessions/${state.sid}`); } catch (_) { state.sid = null; } }
  if (!state.sid) {
    state.sid = (await post("/sessions")).session_id;
    localStorage.setItem("dp_sid", state.sid);
    data = await json(`/sessions/${state.sid}`);
  }
  state.tables = data.tables;
  renderTables(); renderStarters(); renderEmptyState(); renderChips([]);
  data.turns.forEach((t) => { addUser(t.question); addAnswer(t); });
  $("#btn-export").href = `/api/sessions/${state.sid}/export.md`;
}
function showBanner(msg) { const b = $("#banner"); b.textContent = msg; b.hidden = false; }

/* ---------- sidebar ---------- */
function renderTables() {
  const box = $("#tables"); box.replaceChildren();
  const available = new Set(state.tables.map((t) => t.name));
  state.selectedTables = new Set([...state.selectedTables].filter((name) => available.has(name)));
  state.tables.forEach((t) => {
    const cols = t.profile.columns.map((c) => h("li", {}, h("span", {}, c.name), h("i", {}, c.kind)));
    box.append(h("details", { class: "tbl" },
      h("summary", {},
        h("input", { class: "table-check", type: "checkbox", checked: state.selectedTables.has(t.name),
          title: `Select ${t.name}`, onclick: (e) => e.stopPropagation(), onchange: (e) => toggleTable(t.name, e.target.checked) }),
        h("b", { title: t.name }, t.name), h("small", {}, `${t.rows.toLocaleString()} × ${t.profile.columns.length}`)),
      h("ul", {}, cols),
      h("button", { class: "rm", onclick: () => removeTable(t.name) }, "remove")));
  });
  renderDatasetControls();
}
function toggleTable(name, selected) {
  selected ? state.selectedTables.add(name) : state.selectedTables.delete(name);
  renderDatasetControls();
}
function renderDatasetControls() {
  const box = $("#dataset-controls");
  const total = state.tables.length, chosen = state.selectedTables.size;
  box.hidden = !total; box.replaceChildren();
  if (!total) return;
  const allSelected = chosen === total;
  box.append(
    h("button", { class: "mini control", type: "button", onclick: () => {
      state.selectedTables = allSelected ? new Set() : new Set(state.tables.map((t) => t.name)); renderTables();
    } }, allSelected ? "Clear selection" : "Select all"),
    h("button", { class: "mini control danger", type: "button", disabled: !chosen, onclick: deleteSelected }, `Delete selected${chosen ? ` (${chosen})` : ""}`),
  );
}
function renderEmptyState() {
  const hasData = state.tables.length > 0;
  $("#empty-eyebrow").textContent = hasData ? "DATA READY" : "CONVERSATIONAL ANALYTICS";
  $("#empty-title").innerHTML = hasData ? "Ask your data<br><i>anything.</i>" : "Turn rows into<br><i>real answers.</i>";
  $("#empty-copy").textContent = hasData
    ? `${state.tables.length} dataset${state.tables.length === 1 ? " is" : "s are"} ready. Start with a question below or choose a suggestion.`
    : "Upload CSV files, ask in plain English, and inspect the SQL behind every answer.";
}
function renderStarters() {
  const box = $("#starters"); box.replaceChildren();
  STARTERS.forEach((q) => box.append(h("button", { onclick: () => ask(q) }, q)));
}
function renderChips(list) {
  const box = $("#chips"); box.replaceChildren();
  list.forEach((q) => box.append(h("button", { type: "button", onclick: () => ask(q) }, q)));
}
async function removeTable(name) { await api(`/sessions/${state.sid}/files/${name}`, { method: "DELETE" }); await refreshTables(); }
async function deleteSelected() {
  const names = [...state.selectedTables];
  if (!names.length || !confirm(`Delete ${names.length} selected dataset${names.length === 1 ? "" : "s"}?`)) return;
  try {
    await Promise.all(names.map((name) => api(`/sessions/${state.sid}/files/${encodeURIComponent(name)}`, { method: "DELETE" })));
    state.selectedTables.clear(); await refreshTables();
  } catch (e) { showBanner(e.message); }
}
async function refreshTables() { state.tables = (await json(`/sessions/${state.sid}`)).tables; renderTables(); renderEmptyState(); }

function showUploadResults(results) {
  const box = $("#upload-notes"); box.replaceChildren();
  results.forEach((r) => {
    if (r.status === "loaded") {
      box.append(h("div", { class: "good" }, `✓ ${r.filename} → table “${r.name}”`));
      (r.warnings || []).forEach((w) => box.append(h("div", {}, "• " + w)));
    } else box.append(h("div", {}, `✗ ${r.error}`));
  });
}
async function upload(files) {
  if (!files.length) return;
  const fd = new FormData(); [...files].forEach((f) => fd.append("files", f));
  try { showUploadResults((await json(`/sessions/${state.sid}/files`, { method: "POST", body: fd })).results); }
  catch (e) { showUploadResults([{ status: "rejected", error: e.message }]); }
  await refreshTables();
}
$("#file").addEventListener("change", (e) => { upload(e.target.files); e.target.value = ""; });
const drop = $("#drop");
["dragover", "dragenter"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.add("over"); }));
["dragleave", "drop"].forEach((ev) => drop.addEventListener(ev, (e) => { e.preventDefault(); drop.classList.remove("over"); }));
drop.addEventListener("drop", (e) => upload(e.dataTransfer.files));
$("#btn-samples").addEventListener("click", async () => {
  showUploadResults((await json(`/sessions/${state.sid}/load-samples`, { method: "POST" })).results); await refreshTables();
});
$("#btn-clear").addEventListener("click", async () => {
  await post(`/sessions/${state.sid}/reset-chat`);
  [...$("#feed").children].forEach((c) => c.id !== "empty" && c.remove());
  $("#empty").style.display = ""; renderChips([]);
});
$("#btn-clear-data").addEventListener("click", async () => {
  if (!state.tables.length || !confirm("Remove all uploaded datasets and this session's conversation?")) return;
  try {
    await api(`/sessions/${state.sid}/files`, { method: "DELETE" });
    $("#upload-notes").replaceChildren();
    [...$("#feed").children].forEach((c) => c.id !== "empty" && c.remove());
    $("#empty").style.display = ""; renderChips([]); await refreshTables();
  } catch (e) { showBanner(e.message); }
});

/* ---------- tabs ---------- */
document.querySelectorAll(".tab").forEach((tab) => tab.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("on", t === tab));
  document.querySelectorAll(".view").forEach((v) => v.classList.toggle("on", v.id === "view-" + tab.dataset.tab));
  if (tab.dataset.tab === "dashboard") loadDashboard();
  if (tab.dataset.tab === "quality") loadQuality();
}));

/* ---------- chat ---------- */
function addUser(text) { $("#empty").style.display = "none"; $("#feed").append(h("div", { class: "u" }, text)); scrollDown(); }
function scrollDown() { const f = $("#feed"); f.scrollTop = f.scrollHeight; }

async function ask(question) {
  question = (question || "").trim();
  if (!question || state.busy) return;
  state.busy = true; $("#send").disabled = true; $("#input").value = ""; autosize();
  document.querySelector('[data-tab="chat"]').click();
  addUser(question); renderChips([]);
  const wrap = h("div", { class: "a" });
  const status = h("div", { class: "status" }, h("span", { class: "dots" }, h("i"), h("i"), h("i")), h("span", { id: "status-text" }, "Thinking…"));
  wrap.append(status); $("#feed").append(wrap); scrollDown();

  try {
    const res = await api(`/sessions/${state.sid}/chat/stream`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: question }) });
    const reader = res.body.getReader(), dec = new TextDecoder(); let buf = "";
    for (;;) {
      const { value, done } = await reader.read(); if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).trim(); buf = buf.slice(i + 2);
        if (line.startsWith("data:")) handleEvent(JSON.parse(line.slice(5)), wrap, status);
      }
    }
  } catch (e) {
    status.remove(); wrap.append(h("div", { class: "banner" }, e.message));
  } finally {
    state.busy = false; $("#send").disabled = false; $("#input").focus();
  }
}

const TOOL_LABEL = { run_sql: "Running SQL", create_chart: "Building chart", detect_anomalies: "Scanning for anomalies",
  data_quality_report: "Checking data quality", forecast: "Forecasting", describe_table: "Inspecting table" };

function handleEvent(ev, wrap, status) {
  const label = $("#status-text", status);
  if (ev.type === "tool_call" && label) label.textContent = (TOOL_LABEL[ev.name] || ev.name) + (ev.args?.purpose ? `: ${ev.args.purpose}` : "…");
  else if (ev.type === "artifact") { status.before(renderArtifact(ev.artifact)); scrollDown(); }
  else if (ev.type === "error") { status.remove(); wrap.append(h("div", { class: "banner" }, ev.message)); }
  else if (ev.type === "final") {
    status.remove();
    wrap.append(...buildAnswer(ev.turn, false)); // streamed artifact cards stay in place
    renderChips(ev.turn.followups || []); scrollDown();
  }
}

function addAnswer(turn) { const w = h("div", { class: "a" }, ...buildAnswer(turn, true)); $("#feed").append(w); }

/* Answer block order: artifacts first (evidence), then the written answer, then trace. */
function buildAnswer(turn, includeArtifacts) {
  const parts = [];
  if (includeArtifacts) turn.artifacts.forEach((a) => parts.push(renderArtifact(a)));
  parts.push(md(turn.answer));
  if (turn.steps?.length) {
    const ol = h("ol", {}, turn.steps.map((s) => h("li", {}, h("span", { class: s.ok ? "ok" : "fail" }, s.ok ? "✓ " : "✗ "), `${TOOL_LABEL[s.tool] || s.tool}`, s.args?.purpose ? ` – ${s.args.purpose}` : "", ` (${s.summary}, ${s.ms} ms)`)));
    parts.push(h("details", { class: "trace" }, h("summary", {}, `Reasoning trace · ${turn.steps.length} step(s) · ${(turn.elapsed_ms / 1000).toFixed(1)}s`), ol));
  }
  return parts;
}

/* ---------- artifacts ---------- */
function renderArtifact(a) {
  if (a.type === "sql") return sqlCard(a);
  if (a.type === "chart" || a.type === "forecast") return chartCard(a);
  if (a.type === "anomalies") return anomalyCard(a);
  if (a.type === "quality") return h("div", { class: "card" }, qualityBlocks(a.reports));
  return h("div");
}

function dataTable(columns, rows) {
  const head = h("tr", {}, columns.map((c) => h("th", {}, c)));
  const body = rows.map((r) => h("tr", {}, r.map((v) => h("td", { class: typeof v === "number" ? "n" : "" }, fmt(v)))));
  return h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, head), h("tbody", {}, body)));
}

function sqlCard(a) {
  const code = h("pre", {}, h("code", {}, a.query));
  const out = h("div");
  const card = h("div", { class: "card sql" });
  const copy = h("button", { class: "mini", onclick: () => { navigator.clipboard.writeText(a.query); copy.textContent = "Copied"; setTimeout(() => (copy.textContent = "Copy SQL"), 1200); } }, "Copy SQL");
  let editor = null;
  const edit = h("button", { class: "mini", onclick: async () => {
    if (!editor) { editor = h("textarea", {}); editor.value = a.query; code.replaceWith(editor); edit.textContent = "Run"; return; }
    try { const r = await post(`/sessions/${state.sid}/sql`, { query: editor.value }); out.replaceChildren(h("div", { class: "sub", style: "margin:8px 0" }, `${r.row_count} row(s)`), dataTable(r.columns, r.rows)); }
    catch (e) { out.replaceChildren(h("div", { class: "fail" }, e.message)); }
  } }, "Edit & run");
  card.append(h("div", { class: "bar" }, h("h4", {}, a.title || "Query"), h("span", {}, copy, edit)), code,
    h("div", { class: "sub", style: "margin:8px 0" }, `${a.row_count}${a.truncated ? "+" : ""} row(s)${a.cached ? " · cached" : ""}`),
    a.columns.length ? dataTable(a.columns, a.rows.slice(0, 100)) : "", out);
  return card;
}
function chartCard(a) {
  const canvas = h("canvas"); const card = h("div", { class: "card" }, h("h4", {}, a.chart.title), h("div", { class: "chartbox" }, canvas));
  if (a.chart.truncated) card.append(h("div", { class: "sub" }, "Showing a subset of the data for readability."));
  if (a.type === "forecast" && a.details) card.append(h("div", { class: "sub", style: "margin-top:8px" }, `${a.details.method} · trend ${a.details.direction} · ${a.details.caveat}`));
  requestAnimationFrame(() => drawChart(canvas, a.chart));
  return card;
}
function drawChart(canvas, s) {
  const t = s.type, isPie = t === "pie" || t === "doughnut";
  const datasets = s.datasets.map((d, i) => {
    const color = PALETTE[i % PALETTE.length];
    const base = { label: d.label, data: d.data };
    if (isPie) return { ...base, backgroundColor: s.labels.map((_, j) => PALETTE[j % PALETTE.length]) };
    if (t === "bar" || t === "horizontal_bar") return { ...base, backgroundColor: color, borderRadius: 3 };
    if (t === "scatter") return { ...base, backgroundColor: color + "99", pointRadius: 3 };
    const line = { ...base, borderColor: color, backgroundColor: color + "33", tension: 0.25, pointRadius: s.labels.length > 40 ? 0 : 3, fill: t === "area" };
    if (d.style === "dashed") return { ...line, borderDash: [6, 4], borderColor: "#e07a1f", backgroundColor: "#e07a1f" };
    if (d.style === "band") return { ...line, borderDash: [2, 3], borderColor: "#e07a1f55", pointRadius: 0, borderWidth: 1 };
    return line;
  });
  const type = { horizontal_bar: "bar", area: "line" }[t] || t;
  return new Chart(canvas, {
    type, data: { labels: s.labels, datasets },
    options: {
      responsive: true, maintainAspectRatio: false, indexAxis: t === "horizontal_bar" ? "y" : "x",
      plugins: { legend: { display: datasets.length > 1 || isPie, position: "bottom" } },
      scales: isPie ? {} : { x: { title: { display: true, text: s.x_label }, ticks: { maxTicksLimit: 14 } }, y: { title: { display: true, text: s.y_label }, beginAtZero: t.includes("bar") } },
    },
  });
}

function anomalyCard(a) {
  const r = a.report;
  const summary = h("table", {}, h("thead", {}, h("tr", {}, ["Column", "Flagged", "% of rows", "Expected range", "Median"].map((c) => h("th", {}, c)))),
    h("tbody", {}, r.columns.map((c) => h("tr", {}, h("td", {}, c.column), h("td", { class: "n" }, fmt(c.flagged)), h("td", { class: "n" }, c.pct_flagged + "%"),
      h("td", {}, c.expected_min == null ? "per group" : `${fmt(c.expected_min)} … ${fmt(c.expected_max)}`), h("td", { class: "n" }, fmt(c.median))))));
  const rows = r.anomalies.slice(0, 15).map((x) => h("tr", {}, h("td", { class: "n" }, x.row_index), h("td", {}, x.column), h("td", { class: "n" }, fmt(x.value)),
    h("td", {}, `${fmt(x.expected_min)} … ${fmt(x.expected_max)}`), h("td", { class: "n" }, x.severity), h("td", { style: "white-space:normal;min-width:320px" }, x.reason)));
  return h("div", { class: "card" },
    h("h4", {}, `Anomalies in “${a.table}” — ${r.total_flagged} flagged (${r.method.toUpperCase()} rule)`),
    h("div", { class: "tablewrap" }, summary),
    h("div", { class: "sub", style: "margin:10px 0 6px" }, `Top ${rows.length} by severity. ${r.note}`),
    h("div", { class: "tablewrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Row", "Column", "Value", "Expected", "Severity", "Why flagged"].map((c) => h("th", {}, c)))), h("tbody", {}, rows))));
}

function qualityBlocks(reports) {
  return reports.map((q) => h("div", { style: "margin-bottom:18px" },
    h("div", { style: "display:flex;align-items:baseline;gap:12px" }, h("h4", { style: "margin:0" }, `${q.table}`), h("span", { class: "score" }, `${q.score}/100`), h("span", { class: "sub" }, `${q.rows.toLocaleString()} rows`)),
    q.issues.length ? h("div", { class: "tablewrap", style: "margin-top:8px" }, h("table", {}, h("tbody", {}, q.issues.map((i) =>
      h("tr", {}, h("td", {}, h("span", { class: "chip " + i.severity }, i.severity)), h("td", {}, i.column || "(table)"), h("td", {}, i.issue), h("td", { style: "white-space:normal" }, i.detail)))))) : h("div", { class: "sub" }, "No issues found.")));
}

/* ---------- dashboard & quality tabs ---------- */
async function loadDashboard() {
  const box = $("#dash");
  if (!state.tables.length) return box.replaceChildren(h("p", { class: "sub" }, "Load a dataset to see an auto-generated dashboard."));
  try {
    const d = await json(`/sessions/${state.sid}/dashboard`);
    box.replaceChildren(...d.sections.flatMap((s) => [
      h("h2", {}, s.table),
      h("div", { class: "kpis" }, s.kpis.map((k) => h("div", { class: "kpi" }, h("b", {}, fmt(k.value)), h("span", {}, k.label)))),
      h("div", { class: "grid" }, s.charts.map((c) => chartCard({ type: "chart", chart: c }))),
    ]));
  } catch (e) { box.replaceChildren(h("p", { class: "fail" }, e.message)); }
}
async function loadQuality() {
  const box = $("#qual");
  if (!state.tables.length) return box.replaceChildren(h("p", { class: "sub" }, "Load a dataset to run data-quality checks."));
  try { box.replaceChildren(...qualityBlocks((await json(`/sessions/${state.sid}/quality`)).reports).map((el) => h("div", { class: "card", style: "margin-bottom:14px" }, el))); }
  catch (e) { box.replaceChildren(h("p", { class: "fail" }, e.message)); }
}

/* ---------- composer ---------- */
const input = $("#input");
function autosize() { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 160) + "px"; }
input.addEventListener("input", autosize);
input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(input.value); } });
$("#composer").addEventListener("submit", (e) => { e.preventDefault(); ask(input.value); });

init();
