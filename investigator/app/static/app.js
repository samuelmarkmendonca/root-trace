// RootTrace Incident Investigator Console Client
document.addEventListener('DOMContentLoaded', () => {
  // Elements
  const activeModelNameEl = document.getElementById('active-model-name');
  const selectServiceEl = document.getElementById('select-service');
  const selectWindowEl = document.getElementById('select-window');
  const queryTextInputEl = document.getElementById('query-text-input');
  const btnStartInvEl = document.getElementById('btn-start-investigation');
  const btnHeaderNewInvEl = document.getElementById('btn-header-new-inv');
  const invStatusLabelEl = document.getElementById('inv-status-label');
  const invIdLabelEl = document.getElementById('inv-id-label');
  const themeToggleBtn = document.getElementById('theme-toggle');
  const quickSearchTrigger = document.getElementById('quick-search-trigger');

  // Navigation Items
  const navBtnTimeline = document.getElementById('nav-btn-timeline');
  const navBtnServices = document.getElementById('nav-btn-services');
  const navBtnTopology = document.getElementById('nav-btn-topology');
  const navBtnInvestigations = document.getElementById('nav-btn-investigations');

  // Chaos Modal
  const btnToggleChaosEl = document.getElementById('btn-toggle-chaos');
  const btnSidebarChaosEl = document.getElementById('btn-sidebar-chaos');
  const btnCloseChaosEl = document.getElementById('btn-close-chaos');
  const chaosModalOverlayEl = document.getElementById('chaos-modal-overlay');
  const chaosFeedbackEl = document.getElementById('chaos-feedback');
  const faultActionBtns = document.querySelectorAll('.btn-fault-action');
  const quickChips = document.querySelectorAll('.quick-chip');

  // KPI Overview
  const kpiIncidentsCountEl = document.getElementById('kpi-incidents-count');
  const kpiIncidentsSubEl = document.getElementById('kpi-incidents-sub');
  const kpiErrorRateEl = document.getElementById('kpi-error-rate');
  const kpiErrorSubEl = document.getElementById('kpi-error-sub');
  const kpiAvgLatencyEl = document.getElementById('kpi-avg-latency');

  // Service Health
  const latFrontendEl = document.getElementById('lat-frontend');
  const errFrontendEl = document.getElementById('err-frontend');
  const healthPillFrontendEl = document.getElementById('health-pill-frontend');

  const latCheckoutEl = document.getElementById('lat-checkout');
  const errCheckoutEl = document.getElementById('err-checkout');
  const healthPillCheckoutEl = document.getElementById('health-pill-checkout');

  const latDbEl = document.getElementById('lat-db');
  const errDbEl = document.getElementById('err-db');
  const healthPillDbEl = document.getElementById('health-pill-db');

  // Topology
  const btnToggleTopologyEl = document.getElementById('btn-toggle-topology');
  const embeddedTopologyWrapEl = document.getElementById('embedded-topology-wrap');
  const networkGraphContainerEl = document.getElementById('network-graph-container');
  const graphPlaceholderEl = document.getElementById('graph-placeholder');

  // Live Stream Feed
  const liveStreamBadgeEl = document.getElementById('live-stream-badge');
  const emptyFeedHintEl = document.getElementById('empty-feed-hint');
  const stepsStreamEl = document.getElementById('steps-stream');
  const liveEventsFeedEl = document.getElementById('live-events-feed');

  // Causes
  const candidatesBadgeEl = document.getElementById('candidates-badge');
  const causesEmptyHintEl = document.getElementById('causes-empty-hint');
  const rootCausesListEl = document.getElementById('root-causes-list');

  // Timeline
  const timelineTabs = document.querySelectorAll('.t-tab');
  const timelineEmptyHintEl = document.getElementById('timeline-empty-hint');
  const timelineListEl = document.getElementById('timeline-list');

  // State
  let activeEventSource = null;
  let visNetworkInstance = null;
  let cachedTimelineEvents = [];
  let cachedGraphData = null;
  let cachedCandidateNames = [];

  // =============================================================
  // Theme Manager (Dark / Light Mode)
  // =============================================================
  function initThemeManager() {
    if (!themeToggleBtn) return;

    function getPreferredTheme() {
      const stored = localStorage.getItem('root_trace_theme');
      if (stored === 'dark' || stored === 'light') return stored;
      return (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) ? 'dark' : 'dark';
    }

    function applyTheme(theme, save = true) {
      document.documentElement.setAttribute('data-theme', theme);
      const isDark = theme === 'dark';
      themeToggleBtn.setAttribute('aria-pressed', isDark ? 'true' : 'false');
      themeToggleBtn.setAttribute('title', isDark ? 'Switch to light mode' : 'Switch to dark mode');
      themeToggleBtn.setAttribute('aria-label', isDark ? 'Switch to light mode' : 'Switch to dark mode');

      if (save) {
        try {
          localStorage.setItem('root_trace_theme', theme);
        } catch (e) {
          console.warn('Could not save theme to localStorage:', e);
        }
      }

      // Re-render graph if active so node background/font colors match theme
      if (cachedGraphData) {
        renderVisGraph(cachedGraphData, cachedCandidateNames);
      }
    }

    // Initialize with current applied or preferred theme
    const activeTheme = document.documentElement.getAttribute('data-theme') || getPreferredTheme();
    applyTheme(activeTheme, false);

    themeToggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next, true);
    });

    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (!localStorage.getItem('root_trace_theme')) {
          applyTheme(e.matches ? 'dark' : 'light', false);
        }
      });
    }
  }
  initThemeManager();

  // =============================================================
  // Smooth Medium-Paced Falling Scroll Handler
  // =============================================================
  function smoothScrollTo(element) {
    if (!element) return;

    setTimeout(() => {
      element.scrollIntoView({
        behavior: 'smooth',
        block: 'start'
      });

      element.classList.remove('section-falling-target');
      void element.offsetWidth; // Force reflow
      element.classList.add('section-falling-target');
    }, 40);
  }

  if (navBtnTimeline) {
    navBtnTimeline.addEventListener('click', (e) => {
      e.preventDefault();
      const target = document.getElementById('timeline-section');
      smoothScrollTo(target);
    });
  }

  if (navBtnServices) {
    navBtnServices.addEventListener('click', (e) => {
      e.preventDefault();
      const target = document.getElementById('service-health-section');
      smoothScrollTo(target);
    });
  }

  if (navBtnTopology) {
    navBtnTopology.addEventListener('click', (e) => {
      e.preventDefault();
      embeddedTopologyWrapEl.classList.remove('hidden');
      topologyVisible = true;
      const target = document.getElementById('service-health-section');
      smoothScrollTo(target);
    });
  }

  if (navBtnInvestigations) {
    navBtnInvestigations.addEventListener('click', (e) => {
      e.preventDefault();
      const target = document.getElementById('query-section');
      smoothScrollTo(target);
    });
  }

  // Quick Search Shortcut (Ctrl+K or Cmd+K)
  if (quickSearchTrigger) {
    quickSearchTrigger.addEventListener('click', () => {
      queryTextInputEl.focus();
      smoothScrollTo(document.getElementById('query-section'));
    });
  }

  window.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault();
      queryTextInputEl.focus();
      smoothScrollTo(document.getElementById('query-section'));
    }
  });

  // Generic internal anchor smooth scrolling
  document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
      const targetId = this.getAttribute('href');
      if (targetId && targetId !== '#') {
        const el = document.querySelector(targetId);
        if (el) {
          e.preventDefault();
          smoothScrollTo(el);
        }
      }
    });
  });

  // =============================================================
  // 1. Fetch System Info & Initial State
  // =============================================================
  async function loadSystemInfo() {
    try {
      const res = await fetch('/info');
      if (res.ok) {
        const data = await res.json();
        activeModelNameEl.textContent = data.active_model || 'qwen2.5:7b-8k';
      }
    } catch (e) {
      console.warn('Could not fetch /info:', e);
    }
  }
  loadSystemInfo();

  async function loadInitialState() {
    try {
      const res = await fetch('/investigations');
      if (res.ok) {
        const list = await res.json();
        if (Array.isArray(list) && list.length > 0) {
          const latest = list[list.length - 1];
          if (latest && latest.id) {
            fetchFinalReport(latest.id);
          }
        }
      }
    } catch (e) {
      console.warn('Could not load initial investigation state:', e);
    }
  }
  loadInitialState();

  // =============================================================
  // 2. Chaos Modal Toggle
  // =============================================================
  function openChaosModal() {
    chaosModalOverlayEl.classList.remove('hidden');
  }
  function closeChaosModal() {
    chaosModalOverlayEl.classList.add('hidden');
  }

  btnToggleChaosEl.addEventListener('click', openChaosModal);
  if (btnSidebarChaosEl) btnSidebarChaosEl.addEventListener('click', (e) => { e.preventDefault(); openChaosModal(); });
  btnCloseChaosEl.addEventListener('click', closeChaosModal);
  chaosModalOverlayEl.addEventListener('click', (e) => {
    if (e.target === chaosModalOverlayEl) closeChaosModal();
  });

  async function triggerFault(faultId) {
    chaosFeedbackEl.textContent = `Triggering fault '${faultId}' on stack...`;
    try {
      const res = await fetch(`/api/faults/${faultId}`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        chaosFeedbackEl.innerHTML = `✓ <strong>${faultId}</strong> applied: ${data.message || 'success'}. Wait ~45s for Prometheus scrape window before investigating.`;
      } else {
        chaosFeedbackEl.innerHTML = `⚠️ Error: ${data.detail || 'Failed to inject fault'}`;
      }
    } catch (err) {
      chaosFeedbackEl.innerHTML = `⚠️ Network error: ${err.message}`;
    }
  }

  faultActionBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const f = btn.getAttribute('data-fault');
      if (f) triggerFault(f);
    });
  });

  quickChips.forEach(chip => {
    chip.addEventListener('click', () => {
      const f = chip.getAttribute('data-fault');
      if (f) triggerFault(f);
    });
  });

  // =============================================================
  // 3. Topology Toggle
  // =============================================================
  let topologyVisible = true;
  function toggleTopology() {
    topologyVisible = !topologyVisible;
    if (topologyVisible) {
      embeddedTopologyWrapEl.classList.remove('hidden');
    } else {
      embeddedTopologyWrapEl.classList.add('hidden');
    }
  }
  btnToggleTopologyEl.addEventListener('click', toggleTopology);

  // =============================================================
  // 4. Start Investigation
  // =============================================================
  btnStartInvEl.addEventListener('click', runInvestigation);
  btnHeaderNewInvEl.addEventListener('click', () => {
    queryTextInputEl.focus();
    runInvestigation();
  });

  async function runInvestigation() {
    const service = selectServiceEl.value;
    const windowMinutes = parseInt(selectWindowEl.value, 10) || 15;

    // Reset UI
    btnStartInvEl.disabled = true;
    invStatusLabelEl.textContent = 'Running';
    invStatusLabelEl.className = 'status-badge running';
    invIdLabelEl.textContent = '';

    if (activeEventSource) {
      activeEventSource.close();
      activeEventSource = null;
    }

    // Reset Stream
    emptyFeedHintEl.style.display = 'none';
    stepsStreamEl.innerHTML = '';
    liveStreamBadgeEl.textContent = 'Live SSE';
    liveStreamBadgeEl.className = 'status-badge running';

    // Reset Causes & Timeline
    causesEmptyHintEl.style.display = 'block';
    rootCausesListEl.classList.add('hidden');
    rootCausesListEl.innerHTML = '';
    candidatesBadgeEl.textContent = 'Candidates: ...';

    timelineEmptyHintEl.style.display = 'block';
    timelineListEl.classList.add('hidden');
    timelineListEl.innerHTML = '';
    cachedTimelineEvents = [];

    // Append Initial Event
    appendStreamEvent({
      step: 0,
      kind: 'thought',
      content: `Collecting telemetry across architecture for '${service}' over past ${windowMinutes}m...`
    });

    try {
      const res = await fetch('/investigations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          service: service,
          window_minutes: windowMinutes,
          async_mode: true
        })
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `Server error ${res.status}`);
      }

      const launch = await res.json();
      const invId = launch.id;
      invIdLabelEl.textContent = `[${invId}]`;

      // Listen via SSE
      connectSse(invId);
    } catch (err) {
      console.error('Launch failed:', err);
      invStatusLabelEl.textContent = 'Failed';
      invStatusLabelEl.className = 'status-badge failed';
      btnStartInvEl.disabled = false;
      appendStreamEvent({
        step: 0,
        kind: 'thought',
        content: `Error initiating run: ${err.message}`
      });
    }
  }

  // =============================================================
  // 5. SSE Listener
  // =============================================================
  function connectSse(invId) {
    activeEventSource = new EventSource(`/investigations/${invId}/stream`);

    activeEventSource.onmessage = (e) => {
      try {
        const payload = JSON.parse(e.data);
        if (payload.type === 'ping') return; // Keepalive

        if (payload.step !== undefined || payload.type || payload.kind) {
          appendStreamEvent(payload);
        }

        if (payload.type === 'done' || payload.kind === 'finish') {
          if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
          }
          fetchFinalReport(invId);
        } else if (payload.type === 'error' && payload.error) {
          if (activeEventSource) {
            activeEventSource.close();
            activeEventSource = null;
          }
          invStatusLabelEl.textContent = 'Failed';
          invStatusLabelEl.className = 'status-badge failed';
          liveStreamBadgeEl.textContent = 'Failed';
          liveStreamBadgeEl.className = 'status-badge failed';
          btnStartInvEl.disabled = false;
        }
      } catch (err) {
        console.warn('SSE parse error:', e.data, err);
      }
    };

    activeEventSource.onerror = () => {
      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
      }
      fetchFinalReport(invId);
    };
  }

  function appendStreamEvent(evt) {
    if (!evt || evt.type === 'ping') return;
    const row = document.createElement('div');
    row.className = 'event-feed-row';

    const time = evt.timestamp ? new Date(evt.timestamp * 1000).toLocaleTimeString() : new Date().toLocaleTimeString();
    const eventType = evt.type || evt.kind || 'thought';

    let details = escapeHtml(evt.content || '');
    const toolName = evt.tool_name || evt.tool;
    const toolArgs = evt.tool_args || evt.input;
    const toolResult = evt.tool_result !== undefined ? evt.tool_result : evt.result_preview;

    if (toolName) {
      details += ` <br><div style="margin-top:4px;"><strong>Tool:</strong> <code>${escapeHtml(toolName)}</code>(${escapeHtml(JSON.stringify(toolArgs || {}))})</div>`;
    }
    if (toolResult !== undefined) {
      let preview = typeof toolResult === 'object' ? JSON.stringify(toolResult) : String(toolResult);
      if (preview.length > 250) preview = preview.slice(0, 250) + '...';
      details += ` <br><div style="margin-top:2px;"><strong>Result:</strong> <code>${escapeHtml(preview)}</code></div>`;
    }

    row.innerHTML = `
      <span class="evt-time">${time}</span>
      <span class="evt-type-tag ${escapeHtml(eventType)}">${escapeHtml(eventType)}</span>
      <div class="evt-content">${details}</div>
    `;

    stepsStreamEl.appendChild(row);
    liveEventsFeedEl.scrollTop = liveEventsFeedEl.scrollHeight;
  }

  // =============================================================
  // 6. Final Report
  // =============================================================
  async function fetchFinalReport(invId) {
    try {
      const res = await fetch(`/investigations/${invId}`);
      if (!res.ok) return;
      const data = await res.json();

      invStatusLabelEl.textContent = 'Completed';
      invStatusLabelEl.className = 'status-badge completed';
      liveStreamBadgeEl.textContent = 'Finished';
      liveStreamBadgeEl.className = 'status-badge completed';
      btnStartInvEl.disabled = false;
      invIdLabelEl.textContent = `[${invId}]`;

      // Extract Candidate Service Names
      const candidateList = data.candidates || [];
      const candidateNames = candidateList.map(c => typeof c === 'object' ? c.service : String(c));

      // Update Service Metrics & KPIs with candidate awareness
      updateMetricsOverview(data, candidateNames);

      // Render Topology Graph with root cause candidate highlighting
      if (data.graph) {
        renderVisGraph(data.graph, candidateNames);
      }

      // Render Candidates Badge
      if (candidateNames.length > 0) {
        candidatesBadgeEl.textContent = `Candidates: ${candidateNames.join(', ')}`;
        candidatesBadgeEl.className = 'status-badge running';
      } else {
        candidatesBadgeEl.textContent = `Candidates: None`;
        candidatesBadgeEl.className = 'status-badge completed';
      }

      // Render Causes from report or ranked_causes
      const causes = (data.report && data.report.root_causes) ? data.report.root_causes : (data.ranked_causes || []);
      if (causes && causes.length > 0) {
        renderCauses(causes);
      } else {
        causesEmptyHintEl.style.display = 'block';
        causesEmptyHintEl.textContent = 'Investigation complete. No unhealthy service or root causes identified.';
      }

      // Render Timeline
      if (data.timeline && data.timeline.length > 0) {
        cachedTimelineEvents = data.timeline;
        renderTimeline(cachedTimelineEvents);
      }
    } catch (e) {
      console.error('Final report error:', e);
      btnStartInvEl.disabled = false;
    }
  }

  // =============================================================
  // 7. Update KPIs & Monitored Services
  // =============================================================
  function updateMetricsOverview(data, candidateNames = []) {
    if (!data.graph || !data.graph.nodes) return;

    if (!candidateNames || candidateNames.length === 0) {
      const candidateList = data.candidates || [];
      candidateNames = candidateList.map(c => typeof c === 'object' ? c.service : String(c));
    }

    let unhealthyCount = 0;
    let totalLatency = 0;
    let countLatency = 0;
    let maxErrorRatio = 0;

    data.graph.nodes.forEach(node => {
      const id = node.id;
      const isCandidate = candidateNames.includes(id);
      const isUnhealthy = node.health === 'unhealthy';

      let err = 0;
      let lat = 0;

      if (node.error_ratio !== undefined) {
        err = node.error_ratio;
      } else if (data.all_metrics && data.all_metrics[id] && data.all_metrics[id].error_ratio) {
        const er = data.all_metrics[id].error_ratio;
        err = er.max !== undefined ? er.max : (er.last !== undefined ? er.last : 0);
      } else if (id === data.service && data.metrics && data.metrics.error_ratio) {
        const er = data.metrics.error_ratio;
        err = er.max !== undefined ? er.max : (er.last !== undefined ? er.last : 0);
      }

      if (node.latency_p95_seconds !== undefined) {
        lat = node.latency_p95_seconds;
      } else if (data.all_metrics && data.all_metrics[id] && data.all_metrics[id].latency_p95_seconds) {
        const lp = data.all_metrics[id].latency_p95_seconds;
        lat = lp.max !== undefined ? lp.max : (lp.last !== undefined ? lp.last : 0);
      } else if (id === data.service && data.metrics && data.metrics.latency_p95_seconds) {
        const lp = data.metrics.latency_p95_seconds;
        lat = lp.max !== undefined ? lp.max : (lp.last !== undefined ? lp.last : 0);
      }

      if (isUnhealthy) unhealthyCount++;
      if (lat > 0) { totalLatency += lat; countLatency++; }
      if (err > maxErrorRatio) maxErrorRatio = err;

      const latStr = lat > 0 ? (lat * 1000).toFixed(0) + ' ms' : '-- ms';
      const errStr = (err * 100).toFixed(1) + '%';

      let pillClass = 'svc-health-pill';
      let pillHtml = '<span class="dot"></span> Healthy';

      if (isCandidate) {
        pillClass = 'svc-health-pill candidate';
        pillHtml = '<span class="dot"></span> Root Cause Candidate';
      } else if (isUnhealthy) {
        pillClass = 'svc-health-pill cascaded';
        pillHtml = '<span class="dot"></span> Cascaded Impact';
      }

      if (id === 'frontend') {
        latFrontendEl.textContent = latStr;
        errFrontendEl.textContent = errStr;
        healthPillFrontendEl.className = pillClass;
        healthPillFrontendEl.innerHTML = pillHtml;
      } else if (id === 'checkout') {
        latCheckoutEl.textContent = latStr;
        errCheckoutEl.textContent = errStr;
        healthPillCheckoutEl.className = pillClass;
        healthPillCheckoutEl.innerHTML = pillHtml;
      } else if (id === 'db') {
        latDbEl.textContent = latStr;
        errDbEl.textContent = errStr;
        healthPillDbEl.className = pillClass;
        healthPillDbEl.innerHTML = pillHtml;
      }
    });

    // Overview KPIs
    kpiIncidentsCountEl.textContent = String(unhealthyCount).padStart(2, '0');
    kpiIncidentsSubEl.textContent = `${unhealthyCount} critical`;
    kpiIncidentsSubEl.className = `kpi-subtext ${unhealthyCount > 0 ? 'critical' : ''}`;

    kpiErrorRateEl.textContent = (maxErrorRatio * 100).toFixed(1) + '%';
    kpiErrorSubEl.textContent = maxErrorRatio > 0.05 ? 'elevated errors' : 'baseline (threshold 0.05)';

    const avgLat = countLatency > 0 ? (totalLatency / countLatency * 1000).toFixed(0) + ' ms' : '-- ms';
    kpiAvgLatencyEl.textContent = avgLat;
  }

  // =============================================================
  // 8. Render vis-network Topology
  // =============================================================
  function renderVisGraph(graphData, candidateNames = []) {
    graphPlaceholderEl.style.display = 'none';

    cachedGraphData = graphData;
    cachedCandidateNames = candidateNames;

    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';

    const nodes = (graphData.nodes || []).map(n => {
      const isCandidate = candidateNames.includes(n.id);
      const isUnhealthy = n.health === 'unhealthy';

      let labelText = `${n.id}\n(Healthy)`;
      let bg = isDark ? '#064e3b' : '#ecfdf5';
      let border = '#10b981';

      if (isCandidate) {
        labelText = `${n.id}\n(Root Cause Candidate)`;
        bg = isDark ? '#4c0519' : '#fff1f2';
        border = '#f43f5e';
      } else if (isUnhealthy) {
        labelText = `${n.id}\n(Cascaded Impact)`;
        bg = isDark ? '#451a03' : '#fffbeb';
        border = '#f59e0b';
      }

      return {
        id: n.id,
        label: labelText,
        shape: 'box',
        color: {
          background: bg,
          border: border,
          highlight: {
            background: bg,
            border: '#38bdf8'
          }
        },
        font: {
          color: isDark ? '#f8fafc' : '#0f172a',
          face: 'Plus Jakarta Sans, Inter, sans-serif',
          size: 13,
          bold: true
        },
        margin: 12,
        borderWidth: isCandidate ? 3 : 2,
        shadow: {
          enabled: true,
          color: isCandidate ? 'rgba(244, 63, 94, 0.35)' : 'rgba(0,0,0,0.25)',
          size: 8,
          x: 0,
          y: 4
        }
      };
    });

    const edges = (graphData.edges || []).map(e => ({
      from: e.from,
      to: e.to,
      arrows: 'to',
      color: {
        color: isDark ? '#334155' : '#cbd5e1',
        highlight: '#38bdf8'
      },
      width: 2,
      smooth: { type: 'cubicBezier', roundness: 0.2 }
    }));

    const networkData = {
      nodes: new vis.DataSet(nodes),
      edges: new vis.DataSet(edges)
    };

    const options = {
      layout: {
        hierarchical: {
          direction: 'LR',
          sortMethod: 'directed',
          levelSeparation: 140,
          nodeSpacing: 80
        }
      },
      physics: false,
      interaction: { hover: true, dragView: true, zoomView: true }
    };

    if (visNetworkInstance) visNetworkInstance.destroy();
    visNetworkInstance = new vis.Network(networkGraphContainerEl, networkData, options);
  }

  // =============================================================
  // 9. Render Causes
  // =============================================================
  function renderCauses(causes) {
    causesEmptyHintEl.style.display = 'none';
    rootCausesListEl.classList.remove('hidden');
    rootCausesListEl.innerHTML = '';

    causes.forEach((c, idx) => {
      const item = document.createElement('div');
      item.className = 'cause-item';

      const confPct = Math.round((c.confidence || 0.8) * 100);

      let evidenceLines = '';
      if (c.evidence && c.evidence.length > 0) {
        evidenceLines = `
          <div class="evidence-block">
            <div class="evidence-header">Verified Diagnostic Evidence</div>
            ${c.evidence.map(ev => `
              <div class="evidence-line">
                <span class="tool-tag">${escapeHtml(ev.tool || 'check')}</span>
                <span class="evidence-desc">${escapeHtml(ev.finding || '')}</span>
              </div>
            `).join('')}
          </div>
        `;
      }

      item.innerHTML = `
        <div class="cause-item-header">
          <div class="cause-target">
            <span class="rank-pill">#${c.rank || (idx + 1)}</span>
            <span>${escapeHtml(c.service || 'unknown')}</span>
          </div>
          <div class="confidence-meter">
            <div class="meter-bar"><div class="meter-fill" style="width: ${confPct}%"></div></div>
            <span>${confPct}%</span>
          </div>
        </div>
        <p class="cause-summary">${escapeHtml(c.summary || c.root_cause || c.rationale || '')}</p>
        ${evidenceLines}
      `;

      rootCausesListEl.appendChild(item);
    });
  }

  // =============================================================
  // 10. Render Timeline
  // =============================================================
  function renderTimeline(events, filter = 'all') {
    timelineEmptyHintEl.style.display = 'none';
    timelineListEl.classList.remove('hidden');
    timelineListEl.innerHTML = '';

    const list = filter === 'all' ? events : events.filter(e => e.type === filter);
    if (list.length === 0) {
      timelineListEl.innerHTML = `<div class="empty-hint">No events for filter '${escapeHtml(filter)}'.</div>`;
      return;
    }

    list.forEach(evt => {
      const row = document.createElement('div');
      row.className = 't-row';

      let clock = '--:--:--';
      if (evt.time) {
        const d = new Date(typeof evt.time === 'number' ? evt.time * 1000 : evt.time);
        clock = !isNaN(d.getTime()) ? d.toLocaleTimeString() : String(evt.time);
      }

      row.innerHTML = `
        <span class="t-clock">${escapeHtml(clock)}</span>
        <span class="t-svc">${escapeHtml(evt.service || 'infra')}</span>
        <span class="t-badge ${escapeHtml(evt.type || '')}">${escapeHtml(evt.type || 'event')}</span>
        <span class="t-msg">${escapeHtml(evt.description || evt.summary || '')}</span>
      `;

      timelineListEl.appendChild(row);
    });
  }

  timelineTabs.forEach(tab => {
    tab.addEventListener('click', () => {
      timelineTabs.forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      renderTimeline(cachedTimelineEvents, tab.getAttribute('data-type'));
    });
  });

  function escapeHtml(str) {
    if (!str) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }
});
