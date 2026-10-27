const $ = (selector) => document.querySelector(selector);
const state = { jobId: null, result: null, sources: null, exportUrl: null, files: [], fileLinks: [], selected: null, busy: false };
const browserMode = document.documentElement.dataset.mode === "browser";
const emptyInspector = $("#inspector").innerHTML;
const FULL_VIEW = 1000;
const view = { x: -500, y: -500, size: FULL_VIEW };
const pan = { active: false, moved: false, startX: 0, startY: 0, viewX: 0, viewY: 0 };

const escapeHtml = (text) => String(text ?? "").replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[char]);

function toast(message) {
  const element = $("#toast");
  element.textContent = message;
  element.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => (element.hidden = true), 4000);
}

async function api(url, options) {
  const response = await fetch(url, options);
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.detail || `Request failed (${response.status})`);
  return body;
}

$("#theme").addEventListener("click", () => {
  const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
  document.documentElement.dataset.theme = next;
  localStorage.setItem("pyarch-lite-theme", next);
});

if (browserMode) {
  $("#path").placeholder = "Public GitHub repository URL";
  $("#path").setAttribute("aria-label", "Public GitHub repository URL");
  $("#choose-folder").hidden = false;
  $("#mode-note").textContent = "Runs in your browser. Choose a folder (files stay on this device), paste a public GitHub URL, or explore the demo. First scan downloads Python; browser limits: 2,000 files / 30 MB.";
}

function setBusy(busy) {
  state.busy = busy;
  document.querySelectorAll('#scan-form button, #demo').forEach((button) => (button.disabled = busy));
  $("#cancel-scan").hidden = !busy || !browserMode;
}

function showProgress(percent, message) {
  $("#progress").firstElementChild.style.width = `${percent}%`;
  $("#scan-status").textContent = message;
}

$("#choose-folder").addEventListener("click", () => $("#folder-input").click());
$("#cancel-scan").addEventListener("click", () => window.BrowserAnalysis.cancel());
$("#folder-input").addEventListener("change", async (event) => {
  const files = Array.from(event.target.files);
  if (files.length) await scan(files);
  event.target.value = "";
});

$("#scan-form").addEventListener("submit", (event) => {
  event.preventDefault();
  scan();
});

async function scan(files = null) {
  if (state.busy) return;
  setBusy(true);
  const exclusions = $("#exclude").value.split(",").map((item) => item.trim()).filter(Boolean);
  const bar = $("#progress");
  clearTimeout(bar.hideTimer);
  showProgress(0, "Starting analysis");
  bar.hidden = false;
  try {
    if (browserMode) {
      const analysis = await window.BrowserAnalysis.analyze({ path: $("#path").value.trim(), files, exclusions }, showProgress);
      state.jobId = null;
      state.sources = analysis.sources;
      load(analysis.result);
      return;
    }
    const { job_id } = await api("/api/analyses", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ path: $("#path").value.trim(), exclusions }),
    });
    let job;
    do {
      await new Promise((resolve) => setTimeout(resolve, 400));
      job = await api(`/api/analyses/${job_id}`);
      showProgress(job.progress, job.message);
    } while (job.status === "queued" || job.status === "running");
    if (job.status === "error") throw new Error(job.message);
    state.jobId = job_id;
    state.sources = null;
    load(job.result);
  } catch (error) {
    $("#scan-status").textContent = error.message;
    toast(error.message);
  } finally {
    setBusy(false);
    bar.hideTimer = setTimeout(() => (bar.hidden = true), 500);
  }
}

$("#demo").addEventListener("click", async () => {
  if (state.busy) return;
  if (!browserMode) {
    $("#path").value = "demo_project";
    await scan();
    return;
  }
  setBusy(true);
  $("#cancel-scan").hidden = true;
  try {
    const analysis = await api(new URL("demo.json", document.baseURI));
    state.jobId = null;
    state.sources = analysis.sources;
    load(analysis.result);
    $("#scan-status").textContent = "Demo loaded. Select a file to explore its connections.";
  } catch (error) {
    toast(error.message);
  } finally {
    setBusy(false);
  }
});

function load(result) {
  state.result = result;
  state.selected = null;
  $("#ring").classList.remove("focused");
  state.files = result.nodes.filter((node) => node.kind === "file").sort((a, b) => a.path.localeCompare(b.path));
  const fileIds = new Set(state.files.map((file) => file.id));
  state.fileLinks = result.file_edges.filter((edge) => fileIds.has(edge.source) && fileIds.has(edge.target));
  const values = [result.stats.indexed_files ?? result.stats.files, result.stats.symbols, result.stats.edges];
  document.querySelectorAll("#stats b").forEach((element, index) => (element.textContent = values[index]));
  $("#hint").hidden = state.files.length > 0;
  const exportLink = $("#export");
  if (state.exportUrl) URL.revokeObjectURL(state.exportUrl);
  state.exportUrl = URL.createObjectURL(new Blob([JSON.stringify(result, null, 2)], { type: "application/json" }));
  exportLink.href = state.exportUrl;
  exportLink.download = "pyarch-analysis.json";
  exportLink.hidden = false;
  if (result.warnings.length) toast(`${result.warnings.length} warning(s): ${result.warnings[0].message}`);
  renderList();
  renderRing();
  fitView();
  $("#inspector").innerHTML = emptyInspector;
}

$("#filter").addEventListener("input", renderList);

function renderList() {
  const query = $("#filter").value.toLowerCase();
  const matches = state.files.filter((file) => file.path.toLowerCase().includes(query));
  $("#files").innerHTML = matches.map((file) =>
    `<li data-id="${file.id}" class="${file.id === state.selected ? "active" : ""}" title="${escapeHtml(file.path)}">${escapeHtml(file.path)}<small>${file.loc}</small></li>`
  ).join("") || '<li class="muted">No files.</li>';
}

$("#files").addEventListener("click", (event) => {
  const item = event.target.closest("li[data-id]");
  if (item) select(item.dataset.id);
});

function renderRing() {
  const count = state.files.length;
  const radius = 340;
  const position = new Map();
  state.files.forEach((file, index) => {
    const angle = (index / count) * Math.PI * 2 - Math.PI / 2;
    position.set(file.id, { angle, x: Math.cos(angle) * radius, y: Math.sin(angle) * radius });
  });
  const chords = state.fileLinks.map((edge) => {
    const from = position.get(edge.source);
    const to = position.get(edge.target);
    return `<path class="chord" data-source="${edge.source}" data-target="${edge.target}" d="M${from.x},${from.y} Q0,0 ${to.x},${to.y}"><title>${edge.type} ×${edge.count}</title></path>`;
  }).join("");
  const showLabels = count <= 80;
  const beads = state.files.map((file) => {
    const point = position.get(file.id);
    const size = 5 + Math.min(10, Math.sqrt(file.loc) / 3);
    const degrees = ((point.angle * 180) / Math.PI + 360) % 360;
    const flip = degrees > 90 && degrees < 270;
    const label = showLabels
      ? `<text class="label" data-id="${file.id}" transform="rotate(${flip ? degrees + 180 : degrees}) translate(${flip ? -radius - 22 : radius + 22},4)" text-anchor="${flip ? "end" : "start"}">${escapeHtml(file.path.split("/").pop())}</text>`
      : "";
    return `<circle class="bead" data-id="${file.id}" cx="${point.x}" cy="${point.y}" r="${size}"><title>${escapeHtml(file.path)}</title></circle>${label}`;
  }).join("");
  $("#ring").innerHTML = `<circle r="${radius}" fill="none" stroke="var(--line)" stroke-dasharray="2 6"/>${chords}${beads}`;
}

$("#ring").addEventListener("click", (event) => {
  if (pan.moved) return;
  const bead = event.target.closest(".bead");
  if (bead) select(bead.dataset.id);
  else if (state.selected) select(null);
});

function applyView() {
  $("#ring").setAttribute("viewBox", `${view.x} ${view.y} ${view.size} ${view.size}`);
  $("#zoom-level").textContent = `${Math.round((FULL_VIEW / view.size) * 100)}%`;
}

function svgPoint(clientX, clientY) {
  const svg = $("#ring");
  const point = svg.createSVGPoint();
  point.x = clientX;
  point.y = clientY;
  return point.matrixTransform(svg.getScreenCTM().inverse());
}

function zoom(factor, center = { x: view.x + view.size / 2, y: view.y + view.size / 2 }) {
  const size = Math.min(FULL_VIEW * 2, Math.max(FULL_VIEW / 12, view.size * factor));
  const scale = size / view.size;
  view.x = center.x - (center.x - view.x) * scale;
  view.y = center.y - (center.y - view.y) * scale;
  view.size = size;
  applyView();
}

function fitView() {
  Object.assign(view, { x: -500, y: -500, size: FULL_VIEW });
  applyView();
}

$("#ring").addEventListener("wheel", (event) => {
  event.preventDefault();
  zoom(Math.exp(event.deltaY * 0.0015), svgPoint(event.clientX, event.clientY));
}, { passive: false });

$("#ring").addEventListener("pointerdown", (event) => {
  if (event.button !== 0) return;
  Object.assign(pan, { active: true, moved: false, startX: event.clientX, startY: event.clientY, viewX: view.x, viewY: view.y });
});

$("#ring").addEventListener("pointermove", (event) => {
  if (!pan.active) return;
  const dx = event.clientX - pan.startX;
  const dy = event.clientY - pan.startY;
  if (!pan.moved && Math.hypot(dx, dy) < 4) return;
  if (!pan.moved) {
    pan.moved = true;
    event.currentTarget.setPointerCapture(event.pointerId);
    event.currentTarget.classList.add("panning");
  }
  const unitsPerPixel = 1 / event.currentTarget.getScreenCTM().a;
  view.x = pan.viewX - dx * unitsPerPixel;
  view.y = pan.viewY - dy * unitsPerPixel;
  applyView();
});

function endPan(event) {
  pan.active = false;
  $("#ring").classList.remove("panning");
  setTimeout(() => (pan.moved = false));
}
$("#ring").addEventListener("pointerup", endPan);
$("#ring").addEventListener("pointercancel", endPan);
window.addEventListener("pointerup", endPan);
window.addEventListener("blur", endPan);
$("#ring").addEventListener("dblclick", fitView);

document.querySelector(".zoom").addEventListener("click", (event) => {
  const action = event.target.closest("button")?.dataset.zoom;
  if (action === "in") zoom(1 / 1.3);
  if (action === "out") zoom(1.3);
  if (action === "fit") fitView();
});

document.addEventListener("keydown", (event) => {
  if (event.target.matches("input")) return;
  if (event.key === "+" || event.key === "=") zoom(1 / 1.3);
  if (event.key === "-") zoom(1.3);
  if (event.key === "0") fitView();
});

function select(id) {
  state.selected = id;
  const svg = $("#ring");
  svg.classList.toggle("focused", Boolean(id));
  svg.querySelectorAll(".chord").forEach((chord) => chord.classList.toggle("hot", chord.dataset.source === id || chord.dataset.target === id));
  svg.querySelectorAll(".bead, .label").forEach((element) => element.classList.toggle("active", element.dataset.id === id));
  renderList();
  if (!id) {
    $("#inspector").innerHTML = emptyInspector;
    return;
  }
  const node = state.result.nodes.find((item) => item.id === id);
  if (!node) return;
  const members = new Set([id, ...state.result.nodes.filter((item) => item.file_id === id).map((item) => item.id)]);
  const relationships = state.result.edges.filter((edge) => members.has(edge.source) || members.has(edge.target));
  renderInspector({ node, relationships });
}

function nodeLabel(id) {
  const node = state.result.nodes.find((item) => item.id === id);
  return node ? node.qualname || node.label : id;
}

function renderInspector({ node, relationships }) {
  const symbols = state.result.nodes.filter((item) => item.file_id === node.id);
  const outgoing = state.fileLinks.filter((edge) => edge.source === node.id);
  const incoming = state.fileLinks.filter((edge) => edge.target === node.id);
  const linkRow = (edge, other) => `<div class="rel"><b>${edge.type}</b> ${escapeHtml(nodeLabel(other))} <span class="muted">×${edge.count}</span></div>`;
  $("#inspector").innerHTML = `
    <h2>${escapeHtml(node.path)}</h2>
    <div><span class="tag">${escapeHtml(node.module || "module")}</span><span class="tag">${node.loc} lines</span><span class="tag">${relationships.length} relations</span></div>
    <h4>Uses (${outgoing.length})</h4>${outgoing.map((edge) => linkRow(edge, edge.target)).join("") || '<p class="muted">Nothing.</p>'}
    <h4>Used by (${incoming.length})</h4>${incoming.map((edge) => linkRow(edge, edge.source)).join("") || '<p class="muted">Nobody.</p>'}
    <h4>Symbols (${symbols.length})</h4>
    <div>${symbols.map((symbol) => `<span class="tag" title="line ${symbol.line}">${symbol.kind === "class" ? "◆" : "ƒ"} ${escapeHtml(symbol.qualname)}</span>`).join("") || '<p class="muted">None.</p>'}</div>
    <button class="pill" id="show-source" type="button">View source</button>
    <pre id="source" hidden></pre>`;
  $("#show-source").addEventListener("click", async () => {
    const pre = $("#source");
    if (!pre.hidden) return (pre.hidden = true);
    try {
      const { source } = state.sources
        ? { source: state.sources[node.path] }
        : await api(`/api/analyses/${state.jobId}/source?path=${encodeURIComponent(node.path)}`);
      if (typeof source !== "string") throw new Error("Source is not available for this file.");
      pre.textContent = source;
      pre.hidden = false;
    } catch (error) {
      toast(error.message);
    }
  });
}
