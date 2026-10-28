// Knowledge Gateway UI Controller

let eventSource = null;
let isTailingActive = true;
let activityEntries = [];
let currentFilterDebounce = null;

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
  if (window.lucide) {
    window.lucide.createIcons();
  }
  initSSE();
  fetchActivityLogs();
  fetchTopologyStatus();
  updateCacheHeader();
});

// Cache Header Stats
async function updateCacheHeader() {
  try {
    const res = await fetch("/api/v1/cache/stats");
    const data = await res.json();
    const pill = document.getElementById("cacheBackendPill");
    if (pill) {
      if (data.enabled) {
        pill.innerText = `${data.backend.toUpperCase()} (${data.hit_ratio_percent || 0}% hit rate)`;
      } else {
        pill.innerText = "Disabled";
      }
    }
  } catch (e) {
    console.debug("Cache stats check failed:", e);
  }
}

async function clearCacheFromUI() {
  try {
    await fetch("/api/v1/cache/clear", { method: "POST" });
    await updateCacheHeader();
    await fetchActivityLogs();
  } catch (e) {
    console.error("Failed to clear cache:", e);
  }
}

// Tab Switching
function switchTab(tabName) {
  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.classList.remove("active-tab", "border-indigo-500", "text-indigo-400");
    btn.classList.add("border-transparent", "text-slate-400");
  });
  document.querySelectorAll(".tab-content").forEach((c) => c.classList.add("hidden"));

  const activeBtn = document.getElementById(`tabBtn-${tabName}`);
  const activeContent = document.getElementById(`tab-${tabName}`);

  if (activeBtn && activeContent) {
    activeBtn.classList.add("active-tab", "border-indigo-500", "text-indigo-400");
    activeBtn.classList.remove("border-transparent", "text-slate-400");
    activeContent.classList.remove("hidden");
  }

  if (window.lucide) {
    window.lucide.createIcons();
  }

  if (tabName === "topology") {
    fetchTopologyStatus();
  }
}

// Live Server-Sent Events (SSE) Tailing
function initSSE() {
  if (eventSource) {
    eventSource.close();
  }

  try {
    eventSource = new EventSource("/api/v1/tail/stream");

    eventSource.onmessage = (event) => {
      if (!isTailingActive) return;
      try {
        const data = JSON.parse(event.data);
        handleLiveTailEvent(data);
      } catch (e) {
        // Heartbeat or ping event
      }
    };

    eventSource.onerror = () => {
      setTimeout(() => {
        if (isTailingActive) initSSE();
      }, 4000);
    };
  } catch (err) {
    console.error("SSE connection error:", err);
  }
}

function toggleTailing() {
  isTailingActive = !isTailingActive;
  const dot = document.getElementById("tailingDot");
  const text = document.getElementById("tailingText");
  const btn = document.getElementById("tailingToggleBtn");

  if (isTailingActive) {
    dot.className = "w-2 h-2 rounded-full bg-emerald-400 animate-ping";
    text.innerText = "Live Tailing: ON";
    btn.className = "flex items-center space-x-2 text-xs font-medium px-3.5 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 transition-all cursor-pointer";
    if (!eventSource || eventSource.readyState === EventSource.CLOSED) {
      initSSE();
    }
  } else {
    dot.className = "w-2 h-2 rounded-full bg-slate-500";
    text.innerText = "Live Tailing: PAUSED";
    btn.className = "flex items-center space-x-2 text-xs font-medium px-3.5 py-1.5 rounded-lg bg-slate-800 text-slate-400 border border-slate-700 hover:bg-slate-700 transition-all cursor-pointer";
  }
}

function handleLiveTailEvent(entry) {
  activityEntries.unshift(entry);
  updateActivityBadge();
  updateCacheHeader();

  const tbody = document.getElementById("activityTableBody");
  if (tbody.querySelector("td[colspan]")) {
    tbody.innerHTML = "";
  }

  const row = createActivityRow(entry, true);
  tbody.insertBefore(row, tbody.firstChild);

  while (tbody.children.length > 50) {
    tbody.removeChild(tbody.lastChild);
  }

  if (window.lucide) {
    window.lucide.createIcons();
  }
}

// Fetch Activity Logs via REST
async function fetchActivityLogs() {
  const query = document.getElementById("logSearchInput")?.value || "";
  const source = document.getElementById("logSourceFilter")?.value || "";

  let url = `/api/v1/activity?limit=30`;
  if (query) url += `&query=${encodeURIComponent(query)}`;
  if (source) url += `&source=${encodeURIComponent(source)}`;

  try {
    const res = await fetch(url);
    const data = await res.json();
    activityEntries = data.entries || [];
    updateActivityBadge();
    renderActivityTable(activityEntries);
    updateCacheHeader();
  } catch (err) {
    console.error("Failed to fetch activity logs:", err);
  }
}

function debounceFilterLogs() {
  clearTimeout(currentFilterDebounce);
  currentFilterDebounce = setTimeout(fetchActivityLogs, 250);
}

function updateActivityBadge() {
  const badge = document.getElementById("activityCountBadge");
  if (badge) {
    badge.innerText = activityEntries.length;
  }
}

function renderActivityTable(entries) {
  const tbody = document.getElementById("activityTableBody");
  if (!entries || entries.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="8" class="text-center py-12 text-slate-500 font-sans">
          <i data-lucide="inbox" class="w-8 h-8 mx-auto mb-2 opacity-40"></i>
          No activity logs match the current filter.
        </td>
      </tr>
    `;
    if (window.lucide) window.lucide.createIcons();
    return;
  }

  tbody.innerHTML = "";
  entries.forEach((entry) => {
    tbody.appendChild(createActivityRow(entry, false));
  });

  if (window.lucide) {
    window.lucide.createIcons();
  }
}

function createActivityRow(entry, isNew) {
  const tr = document.createElement("tr");
  tr.className = `hover:bg-slate-800/40 transition-colors cursor-pointer ${isNew ? "flash-row" : ""}`;
  tr.onclick = (e) => {
    if (!e.target.closest("button")) {
      openInspector(entry.request_id);
    }
  };

  const timeStr = entry.timestamp ? entry.timestamp.split("T")[1]?.substring(0, 8) || "recent" : "recent";
  const scoreClass = entry.top_score >= 0.8 ? "score-high" : entry.top_score >= 0.4 ? "score-med" : "score-low";

  // Build sources chips
  let sourcesHtml = '<div class="flex flex-wrap gap-1 items-center">';
  if (entry.cached) {
    sourcesHtml += `
      <span class="px-1.5 py-0.5 rounded text-3xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center space-x-1">
        <span>⚡ CACHE HIT</span>
      </span>
    `;
  }

  const breakdown = entry.source_breakdown || {};
  const attempted = entry.sources_attempted || Object.keys(breakdown);

  attempted.forEach((src) => {
    if (src === "cache") return;
    const info = breakdown[src] || {};
    const count = info.count ?? 0;
    const badgeColor = getSourceBadgeStyle(src);
    sourcesHtml += `
      <span class="px-1.5 py-0.5 rounded text-3xs font-mono font-medium ${badgeColor}">
        ${src.toUpperCase()}: ${count}
      </span>
    `;
  });
  sourcesHtml += "</div>";

  tr.innerHTML = `
    <td class="py-3 px-4 text-slate-400 whitespace-nowrap">${timeStr}</td>
    <td class="py-3 px-4 font-mono text-indigo-400 font-medium whitespace-nowrap">${entry.request_id}</td>
    <td class="py-3 px-4 max-w-xs truncate text-slate-200 font-sans" title="${escapeHtml(entry.query)}">
      ${escapeHtml(entry.query)}
    </td>
    <td class="py-3 px-4">${sourcesHtml}</td>
    <td class="py-3 px-4 text-center text-slate-300">
      <span class="text-white font-bold">${entry.items_returned_count ?? 0}</span>
      <span class="text-slate-500">/ ${entry.total_consolidated_items ?? 0}</span>
    </td>
    <td class="py-3 px-4 text-center">
      <span class="score-pill ${scoreClass}">${(entry.top_score ?? 0).toFixed(3)}</span>
    </td>
    <td class="py-3 px-4 text-center ${entry.cached ? 'text-amber-400 font-bold' : 'text-emerald-400'}">${(entry.latency_ms ?? 0).toFixed(1)}ms</td>
    <td class="py-3 px-4 text-right">
      <button onclick="openInspector('${entry.request_id}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-indigo-600 text-slate-300 hover:text-white transition text-xs font-sans">
        Inspect
      </button>
    </td>
  `;

  return tr;
}

function getSourceBadgeStyle(source) {
  switch (source.toLowerCase()) {
    case "rag":
      return "bg-purple-950/70 text-purple-300 border border-purple-800/50";
    case "okf":
      return "bg-blue-950/70 text-blue-300 border border-blue-800/50";
    case "filesystem":
      return "bg-amber-950/70 text-amber-300 border border-amber-800/50";
    case "git":
      return "bg-rose-950/70 text-rose-300 border border-rose-800/50";
    case "sql":
      return "bg-emerald-950/70 text-emerald-300 border border-emerald-800/50";
    default:
      return "bg-slate-800 text-slate-300";
  }
}

// Request Inspector Drawer
async function openInspector(requestId) {
  const drawer = document.getElementById("inspectorDrawer");
  const backdrop = document.getElementById("inspectorBackdrop");

  drawer.classList.remove("translate-x-full");
  backdrop.classList.remove("hidden");

  document.getElementById("inspectReqId").innerText = requestId;
  document.getElementById("inspectTimestamp").innerText = "Loading audit trace...";

  try {
    const res = await fetch(`/api/v1/activity/${requestId}`);
    if (!res.ok) throw new Error("Activity not found");
    const detail = await res.json();

    const cacheLabel = detail.cached ? `⚡ CACHED (${detail.cache_backend || 'cache'})` : 'FRESH RETRIEVAL';
    document.getElementById("inspectTimestamp").innerText = `${detail.timestamp} • ${detail.latency_ms.toFixed(2)}ms latency • ${cacheLabel}`;
    document.getElementById("inspectQueryText").innerText = detail.query;

    // Tags
    const tagsContainer = document.getElementById("inspectTagsContainer");
    tagsContainer.innerHTML = "";
    (detail.tags || []).forEach((t) => {
      tagsContainer.innerHTML += `<span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-2xs">#${escapeHtml(t)}</span>`;
    });

    // Multi-Source Retrieval Breakdown Grid
    const sourcesGrid = document.getElementById("inspectSourcesGrid");
    sourcesGrid.innerHTML = "";

    // Add Cache Card if cached
    if (detail.cached) {
      sourcesGrid.innerHTML += `
        <div class="p-3.5 rounded-xl bg-amber-950/30 border border-amber-500/40 col-span-full space-y-1">
          <div class="flex items-center justify-between">
            <span class="font-bold text-xs text-amber-300 flex items-center space-x-1.5">
              <i data-lucide="zap" class="w-4 h-4 text-amber-400"></i>
              <span>ACCELERATED CACHE HIT (${(detail.cache_backend || 'cache').toUpperCase()})</span>
            </span>
            <span class="font-mono text-2xs text-amber-400">${detail.latency_ms.toFixed(2)}ms (Instant)</span>
          </div>
          <p class="text-2xs text-slate-300">Data returned directly from high-speed cache. Multi-source fan-out and ONNX re-ranking was bypassed to eliminate compute latency.</p>
        </div>
      `;
    }

    const breakdown = detail.source_breakdown || {};
    const allKnownSources = ["rag", "okf", "filesystem", "git", "sql"];

    allKnownSources.forEach((srcKey) => {
      const srcInfo = breakdown[srcKey] || { status: "not_queried", count: 0, latency_ms: 0 };
      const isQueried = detail.sources_attempted?.includes(srcKey);
      const isSuccess = srcInfo.status === "ok" || (srcInfo.count && srcInfo.count > 0);

      const statusBadge = detail.cached
        ? `<span class="text-2xs text-amber-400/80 font-mono">Cached from previous retrieval</span>`
        : !isQueried
        ? `<span class="text-2xs text-slate-500 font-mono">Not Selected</span>`
        : isSuccess
        ? `<span class="text-2xs text-emerald-400 font-mono flex items-center space-x-1"><span class="w-1.5 h-1.5 rounded-full bg-emerald-400"></span><span>Retrieved ${srcInfo.count} items</span></span>`
        : `<span class="text-2xs text-amber-400 font-mono">0 hits (${srcInfo.latency_ms?.toFixed(1) || 0}ms)</span>`;

      sourcesGrid.innerHTML += `
        <div class="p-3.5 rounded-xl bg-slate-950 border ${isSuccess ? "border-indigo-500/40 bg-indigo-950/10" : "border-slate-800"} space-y-2">
          <div class="flex items-center justify-between">
            <span class="font-bold uppercase tracking-wider font-mono text-xs ${getSourceTextColor(srcKey)}">${getSourceTitle(srcKey)}</span>
            <span class="font-mono text-slate-400 text-2xs">${srcInfo.latency_ms ? srcInfo.latency_ms.toFixed(1) + "ms" : "-"}</span>
          </div>
          <div>${statusBadge}</div>
          <div class="text-slate-400 text-2xs">${getSourceDescription(srcKey)}</div>
        </div>
      `;
    });

    // Rerank candidates table
    const rerankTbody = document.getElementById("inspectRerankTableBody");
    rerankTbody.innerHTML = "";
    (detail.candidates_reranking || []).forEach((c) => {
      const scoreClass = c.onnx_score >= 0.8 ? "score-high" : c.onnx_score >= 0.4 ? "score-med" : "score-low";
      rerankTbody.innerHTML += `
        <tr class="hover:bg-slate-900/60">
          <td class="p-2.5 text-slate-200 max-w-xs truncate" title="${escapeHtml(c.title)}">${escapeHtml(c.title)}</td>
          <td class="p-2.5">
            <span class="px-1.5 py-0.5 rounded text-3xs font-mono font-medium ${getSourceBadgeStyle(c.source_type)}">${c.source_type.toUpperCase()}</span>
          </td>
          <td class="p-2.5 text-center text-slate-400 font-mono">${c.raw_score.toFixed(3)}</td>
          <td class="p-2.5 text-center font-mono font-bold">
            <span class="score-pill ${scoreClass}">${c.onnx_score.toFixed(3)}</span>
          </td>
          <td class="p-2.5 text-right font-mono">
            ${c.accepted ? '<span class="text-emerald-400">Accepted</span>' : '<span class="text-slate-500">Pruned</span>'}
          </td>
        </tr>
      `;
    });

    // Response Payload
    document.getElementById("inspectRawPayload").innerText = JSON.stringify(detail.response_payload || {}, null, 2);

    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    console.error("Inspector fetch error:", err);
  }
}

function closeInspector() {
  document.getElementById("inspectorDrawer").classList.add("translate-x-full");
  document.getElementById("inspectorBackdrop").classList.add("hidden");
}

function getSourceTitle(key) {
  switch (key) {
    case "rag": return "RAG Vector DB";
    case "okf": return "OKF Knowledge Point";
    case "filesystem": return "Filesystem Docs";
    case "git": return "Git Repository";
    case "sql": return "Relational SQL (Postgres / MySQL)";
    default: return key.toUpperCase();
  }
}

function getSourceTextColor(key) {
  switch (key) {
    case "rag": return "text-purple-400";
    case "okf": return "text-blue-400";
    case "filesystem": return "text-amber-400";
    case "git": return "text-rose-400";
    case "sql": return "text-emerald-400";
    default: return "text-slate-300";
  }
}

function getSourceDescription(key) {
  switch (key) {
    case "rag": return "Dense vector ANN semantic search via Qdrant";
    case "okf": return "Deterministic entity and relation graph traversal";
    case "filesystem": return "Full-text file search across docs & specifications";
    case "git": return "Commit history, branches, and tracked repository files";
    case "sql": return "Relational tables with parameterized text matching";
    default: return "";
  }
}

// Playground Execution & Pagination
let currentPlaygroundPage = 1;

async function executePlaygroundQuery() {
  const query = document.getElementById("playgroundQuery").value.trim();
  if (!query) return;

  const rawTags = document.getElementById("playgroundTags").value.trim();
  const tags = rawTags ? rawTags.split(",").map((t) => t.trim()).filter(Boolean) : [];

  const sources = [];
  if (document.getElementById("src-rag").checked) sources.push("rag");
  if (document.getElementById("src-okf").checked) sources.push("okf");
  if (document.getElementById("src-fs").checked) sources.push("filesystem");
  if (document.getElementById("src-git").checked) sources.push("git");
  if (document.getElementById("src-sql").checked) sources.push("sql");

  const page = parseInt(document.getElementById("playgroundPage").value, 10) || 1;
  const pageSize = parseInt(document.getElementById("playgroundPageSize").value, 10) || 3;
  currentPlaygroundPage = page;

  const execBtn = document.getElementById("executeBtn");
  execBtn.disabled = true;
  execBtn.innerHTML = `<i data-lucide="loader" class="w-4 h-4 animate-spin"></i><span>Consolidating Knowledge...</span>`;
  if (window.lucide) window.lucide.createIcons();

  try {
    const res = await fetch("/api/v1/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        query: query,
        tags: tags,
        sources: sources.length ? sources : null,
        page: page,
        page_size: pageSize,
      }),
    });

    const data = await res.json();
    renderPlaygroundResults(data);
    updateCacheHeader();
  } catch (err) {
    console.error("Playground query error:", err);
  } finally {
    execBtn.disabled = false;
    execBtn.innerHTML = `<i data-lucide="sparkles" class="w-4 h-4"></i><span>Execute Knowledge Query</span>`;
    if (window.lucide) window.lucide.createIcons();
  }
}

function paginatePlayground(delta) {
  const pageInput = document.getElementById("playgroundPage");
  let newPage = (parseInt(pageInput.value, 10) || 1) + delta;
  if (newPage < 1) newPage = 1;
  pageInput.value = newPage;
  executePlaygroundQuery();
}

function renderPlaygroundResults(data) {
  document.getElementById("resCount").innerText = (data.items || []).length;
  document.getElementById("resTotal").innerText = data.total_results || 0;
  document.getElementById("resLatency").innerText = `${data.latency_ms}ms`;
  document.getElementById("pageIndicator").innerText = `Page ${data.page} / ${data.total_pages || 1}`;

  document.getElementById("prevPageBtn").disabled = !data.has_previous;
  document.getElementById("nextPageBtn").disabled = !data.has_next;

  // Render sources pills
  const pillsContainer = document.getElementById("resSourcesPills");
  pillsContainer.innerHTML = "";
  if (data.cached) {
    pillsContainer.innerHTML += `
      <span class="px-2 py-0.5 rounded text-3xs font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 flex items-center space-x-1">
        <span>⚡ CACHE HIT (${(data.cache_backend || 'cache').toUpperCase()})</span>
      </span>
    `;
  }
  for (const [srcKey, stat] of Object.entries(data.sources_searched || {})) {
    pillsContainer.innerHTML += `
      <span class="px-2 py-0.5 rounded text-3xs font-mono ${getSourceBadgeStyle(srcKey)}">
        ${srcKey.toUpperCase()}: ${stat.count} (${stat.latency_ms.toFixed(1)}ms)
      </span>
    `;
  }

  // Render items
  const container = document.getElementById("playgroundResultsList");
  if (!data.items || data.items.length === 0) {
    container.innerHTML = `
      <div class="bg-slate-900/40 border border-slate-800/80 rounded-xl p-8 text-center text-slate-500">
        No results found for this page.
      </div>
    `;
    return;
  }

  container.innerHTML = "";
  data.items.forEach((item, idx) => {
    const scoreClass = item.score >= 0.8 ? "score-high" : item.score >= 0.4 ? "score-med" : "score-low";
    const provKeys = Object.entries(item.provenance || {})
      .map(([k, v]) => `<span class="px-2 py-0.5 rounded bg-slate-950 font-mono text-slate-400 text-3xs border border-slate-800">${k}: ${escapeHtml(String(v))}</span>`)
      .join(" ");

    container.innerHTML += `
      <div class="bg-slate-900/80 rounded-xl border border-slate-800 p-4 space-y-3 hover:border-slate-700 transition">
        <div class="flex items-start justify-between gap-3">
          <div class="flex items-center space-x-2">
            <span class="px-2 py-0.5 rounded text-3xs font-mono font-medium ${getSourceBadgeStyle(item.source_type)}">
              ${item.source_type.toUpperCase()}
            </span>
            <h3 class="text-sm font-bold text-white">${escapeHtml(item.title)}</h3>
          </div>
          <div class="flex items-center space-x-2">
            <span class="text-3xs font-mono text-slate-400">ONNX Score:</span>
            <span class="score-pill ${scoreClass}">${item.score.toFixed(3)}</span>
          </div>
        </div>

        <p class="text-xs text-slate-300 font-sans leading-relaxed bg-slate-950/60 p-3 rounded-lg border border-slate-800/60">
          ${escapeHtml(item.snippet || item.content.substring(0, 240))}
        </p>

        <div class="flex flex-wrap items-center gap-1.5 pt-1">
          <span class="text-3xs font-mono text-slate-500 mr-1">PROVENANCE:</span>
          ${provKeys}
        </div>
      </div>
    `;
  });

  if (window.lucide) window.lucide.createIcons();
}

function sendQuickSampleQuery(text) {
  switchTab("playground");
  document.getElementById("playgroundQuery").value = text;
  document.getElementById("playgroundPage").value = 1;
  executePlaygroundQuery();
}

// Topology & Connectors Health
async function fetchTopologyStatus() {
  const grid = document.getElementById("topologyGrid");
  if (!grid) return;

  grid.innerHTML = `<div class="col-span-full py-8 text-center text-slate-500 font-mono">Checking connector states...</div>`;

  try {
    const res = await fetch("/api/v1/sources/status");
    const data = await res.json();
    grid.innerHTML = "";

    for (const [key, info] of Object.entries(data)) {
      const isHealthy = info.status === "healthy" || info.status === "active" || info.enabled === true;
      grid.innerHTML += `
        <div class="bg-slate-900/70 p-5 rounded-xl border ${isHealthy ? "border-slate-800" : "border-amber-500/30"} space-y-3">
          <div class="flex items-center justify-between">
            <span class="font-bold text-sm text-white flex items-center space-x-2">
              <span class="w-2.5 h-2.5 rounded-full ${isHealthy ? "bg-emerald-400" : "bg-amber-400"}"></span>
              <span>${key.toUpperCase()}</span>
            </span>
            <span class="px-2 py-0.5 rounded text-3xs font-mono ${isHealthy ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20" : "bg-amber-500/10 text-amber-400 border border-amber-500/20"}">
              ${(info.status || (info.enabled ? 'ACTIVE' : 'INACTIVE')).toUpperCase()}
            </span>
          </div>

          <pre class="bg-slate-950 p-3 rounded-lg text-3xs font-mono text-slate-300 overflow-x-auto max-h-36">${JSON.stringify(info, null, 2)}</pre>
        </div>
      `;
    }
    if (window.lucide) window.lucide.createIcons();
  } catch (err) {
    grid.innerHTML = `<div class="col-span-full text-center text-rose-400">Error loading status: ${err.message}</div>`;
  }
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
