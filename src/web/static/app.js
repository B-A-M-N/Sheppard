/* ═══════════════════════════════════════════════════════════
   Sheppard Web UI — app.js
   ═══════════════════════════════════════════════════════════ */

'use strict';

// ── State ──────────────────────────────────────────────────
const state = {
  activeTab: 'chat',
  chatMode: 'chat',           // 'chat' | 'analyze'
  chatHistory: [],            // [{role, content}]
  selectedMissionFilter: null,
  knowledge: {
    view: 'graph',
    selectedConcept: null,
    missionFilter: null,
    atomsOffset: 0,
    atomsTotal: 0,
    atomsLimit: 50,
    minConfidence: 0.3,
    sort: 'importance',
  },
  logs: {
    levels: new Set(['INFO', 'WARNING', 'ERROR']),
    filter: '',
    paused: false,
  },
  stats: {},
  missions: [],
};

// ── WebSocket connections ──────────────────────────────────
let chatWs = null;
let analyzeWs = null;
let logsWs = null;
let logsReconnectTimer = null;

// ── Tab switching ──────────────────────────────────────────
function switchTab(name) {
  state.activeTab = name;
  document.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t.dataset.tab === name));
  document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `${name}-pane`));
  if (name === 'missions') loadMissions();
  if (name === 'knowledge') loadKnowledge();
}

// ── API helpers ────────────────────────────────────────────
async function api(path, opts = {}) {
  const res = await fetch(`/api${path}`, {
    headers: { 'Content-Type': 'application/json', ...opts.headers },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// ── Status bar ─────────────────────────────────────────────
async function refreshStatus() {
  try {
    const [missionsData, stats] = await Promise.all([
      api('/missions'),
      api('/knowledge/stats'),
    ]);

    state.missions = missionsData.missions || [];
    state.stats = stats;

    const active = state.missions.filter(m => m.crawling).length;
    const dot = document.getElementById('status-dot');
    const statusText = document.getElementById('status-text');

    if (active > 0) {
      dot.className = 'stat-dot active';
      statusText.textContent = `${active} active`;
    } else {
      dot.className = 'stat-dot idle';
      statusText.textContent = 'idle';
    }

    document.getElementById('status-atoms').textContent = `${stats.total_atoms.toLocaleString()} atoms`;
    document.getElementById('status-missions').textContent = `${stats.total_missions.toLocaleString()} missions`;

    renderMissionFilters();
  } catch (e) {
    console.error('Status refresh failed:', e);
  }
}

// ── CHAT TAB ───────────────────────────────────────────────
function initChat() {
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');

  // Auto-resize textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });

  sendBtn.addEventListener('click', sendMessage);

  // Mode buttons
  document.querySelectorAll('.mode-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      state.chatMode = btn.dataset.mode;
      document.querySelectorAll('.mode-btn').forEach(b => b.classList.toggle('active', b.dataset.mode === state.chatMode));
      const placeholder = state.chatMode === 'analyze'
        ? 'Describe a problem to analyze...'
        : 'Ask Sheppard anything...';
      input.placeholder = placeholder;
    });
  });

  connectChatWs();
  connectAnalyzeWs();
}

function connectChatWs() {
  if (chatWs && chatWs.readyState <= 1) return;
  chatWs = new WebSocket(`ws://${location.host}/api/ws/chat`);
  chatWs.onclose = () => setTimeout(connectChatWs, 2000);
  chatWs.onerror = () => chatWs.close();
}

function connectAnalyzeWs() {
  if (analyzeWs && analyzeWs.readyState <= 1) return;
  analyzeWs = new WebSocket(`ws://${location.host}/api/ws/analyze`);
  analyzeWs.onclose = () => setTimeout(connectAnalyzeWs, 2000);
  analyzeWs.onerror = () => analyzeWs.close();
}

/**
 * Shared streaming helper. Sends messages over chatWs and streams tokens
 * into bubble. Updates state.chatHistory with the final assistant response.
 */
function _streamChat(messages, bubble) {
  const ws = chatWs;
  if (!ws || ws.readyState !== 1) {
    bubble.textContent = '[Not connected — retrying...]';
    bubble.classList.remove('streaming');
    document.getElementById('send-btn').disabled = false;
    return;
  }
  ws.send(JSON.stringify({ messages }));
  let buffer = '';
  const handler = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'token') {
      buffer += msg.text;
      bubble.textContent = buffer;
      scrollChatToBottom();
    } else if (msg.type === 'done') {
      bubble.classList.remove('streaming');
      state.chatHistory.push({ role: 'assistant', content: buffer });
      document.getElementById('send-btn').disabled = false;
      ws.removeEventListener('message', handler);
    } else if (msg.type === 'error') {
      bubble.textContent = `Error: ${msg.text}`;
      bubble.classList.remove('streaming');
      document.getElementById('send-btn').disabled = false;
      ws.removeEventListener('message', handler);
    }
  };
  ws.addEventListener('message', handler);
}

function sendMessage() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;

  input.value = '';
  input.style.height = 'auto';

  appendMessage('user', text);

  if (text.startsWith('/')) {
    runCommand(text);
    return;
  }

  if (state.chatMode === 'analyze') {
    runAnalyze(text);
  } else {
    runChat(text);
  }
}

function runChat(text) {
  state.chatHistory.push({ role: 'user', content: text });
  const bubble = appendMessage('assistant', '');
  bubble.classList.add('streaming');
  document.getElementById('send-btn').disabled = true;
  _streamChat(state.chatHistory, bubble);
}

function runAnalyze(text) {
  const bubble = appendMessage('assistant', 'Analyzing...\n');
  bubble.classList.add('streaming');
  document.getElementById('send-btn').disabled = true;

  const ws = analyzeWs;
  if (!ws || ws.readyState !== 1) {
    bubble.textContent = '[Not connected — retrying...]';
    bubble.classList.remove('streaming');
    document.getElementById('send-btn').disabled = false;
    return;
  }

  ws.send(JSON.stringify({
    problem: text,
    mission_filter: state.selectedMissionFilter,
  }));

  let buffer = '';
  const handler = (evt) => {
    const msg = JSON.parse(evt.data);
    if (msg.type === 'chunk') {
      buffer += msg.text;
      bubble.textContent = buffer;
      scrollChatToBottom();
    } else if (msg.type === 'done') {
      bubble.classList.remove('streaming');
      document.getElementById('send-btn').disabled = false;
      ws.removeEventListener('message', handler);
    } else if (msg.type === 'error') {
      bubble.textContent = `Analysis error: ${msg.text}`;
      bubble.classList.remove('streaming');
      document.getElementById('send-btn').disabled = false;
      ws.removeEventListener('message', handler);
    }
  };
  ws.addEventListener('message', handler);
}

async function runCommand(text) {
  const parts = text.trim().split(/\s+/);
  const cmd = parts[0].toLowerCase();
  const args = parts.slice(1);

  switch (cmd) {
    case '/help': case '/h':
      showHelp();
      break;

    case '/learn':
      if (!args.length) { appendMessage('system', 'Usage: /learn <topic>'); break; }
      await cmdLearn(args.join(' '));
      break;

    case '/stop':
      if (!args.length) { appendMessage('system', 'Usage: /stop <mission_id>'); break; }
      await cmdStop(args[0]);
      break;

    case '/missions':
      switchTab('missions');
      break;

    case '/knowledge': case '/kb':
      switchTab('knowledge');
      break;

    case '/analyze': case '/a':
      // Route through the analyze WebSocket
      if (!args.length) { appendMessage('system', 'Usage: /analyze <problem statement>'); break; }
      runAnalyze(args.join(' '));
      break;

    case '/status':
      await cmdStatus();
      break;

    case '/query':
      if (!args.length) { appendMessage('system', 'Usage: /query <text>'); break; }
      await cmdQuery(args.join(' '));
      break;

    default:
      appendMessage('system', `Unknown command: ${cmd}. Type /help for available commands.`);
  }
}

function showHelp() {
  const bubble = appendMessage('system', '');
  bubble.innerHTML = `
    <table style="border-collapse:collapse; width:100%; font-family:var(--font); font-size:12px;">
      <thead>
        <tr style="border-bottom:1px solid var(--border)">
          <th style="text-align:left; padding:4px 12px 4px 0; color:var(--crimson)">Command</th>
          <th style="text-align:left; padding:4px 0; color:var(--crimson)">Usage</th>
        </tr>
      </thead>
      <tbody>
        ${[
          ['/learn &lt;topic&gt;',      'Start a background knowledge mission'],
          ['/stop &lt;mission_id&gt;',  'Cancel an active mission'],
          ['/analyze &lt;problem&gt;',  'Reason from knowledge toward a recommendation'],
          ['/query &lt;text&gt;',       'Search the knowledge base'],
          ['/missions',                 'Switch to missions tab'],
          ['/knowledge',                'Switch to knowledge tab'],
          ['/status',                   'Show system status'],
          ['/help',                     'Show this help'],
        ].map(([c, d]) => `
          <tr style="border-bottom:1px solid #1a1a1a">
            <td style="padding:5px 12px 5px 0; color:var(--crimson); white-space:nowrap">${c}</td>
            <td style="padding:5px 0; color:var(--white)">${d}</td>
          </tr>
        `).join('')}
      </tbody>
    </table>
  `;
}

async function cmdLearn(topic) {
  const bubble = appendMessage('system', `Starting mission: ${topic}...`);
  try {
    const res = await api('/missions', {
      method: 'POST',
      body: JSON.stringify({ topic, ceiling_gb: 5.0 }),
    });
    bubble.innerHTML = `Mission started: <span class="crimson">${esc(topic)}</span><br>
      <span style="color:var(--grey); font-size:11px">ID: ${res.mission_id}</span>`;
    refreshStatus();
  } catch (e) {
    bubble.textContent = `Failed to start mission: ${e.message}`;
  }
}

async function cmdStop(id) {
  const bubble = appendMessage('system', `Stopping mission ${id}...`);
  try {
    await api(`/missions/${id}`, { method: 'DELETE' });
    bubble.textContent = `Mission ${id} cancelled.`;
    refreshStatus();
  } catch (e) {
    bubble.textContent = `Failed: ${e.message}`;
  }
}

async function cmdStatus() {
  const bubble = appendMessage('system', '');
  try {
    const [missions, stats] = await Promise.all([
      api('/missions'),
      api('/knowledge/stats'),
    ]);
    const active = missions.missions.filter(m => m.crawling);
    bubble.innerHTML = `
      <div style="font-family:var(--font); font-size:12px; line-height:1.8">
        <div><span class="grey">Atoms:</span> <span class="crimson">${stats.total_atoms.toLocaleString()}</span></div>
        <div><span class="grey">Missions:</span> ${stats.total_missions} total, ${stats.active_missions} active</div>
        <div><span class="grey">Concepts:</span> ${stats.total_concepts.toLocaleString()}</div>
        <div><span class="grey">Sources:</span> ${stats.total_sources.toLocaleString()}</div>
        ${active.length ? `<div style="margin-top:6px"><span class="grey">Running:</span> ${active.map(m => `<span class="crimson">${esc(m.title)}</span>`).join(', ')}</div>` : ''}
      </div>
    `;
  } catch (e) {
    bubble.textContent = `Status error: ${e.message}`;
  }
}

function cmdQuery(text) {
  state.chatHistory.push({ role: 'user', content: `Tell me what you know about: ${text}` });
  const bubble = appendMessage('assistant', '');
  bubble.classList.add('streaming');
  document.getElementById('send-btn').disabled = true;
  _streamChat(state.chatHistory, bubble);
}

function appendMessage(role, content) {
  const history = document.getElementById('chat-history');
  const div = document.createElement('div');
  div.className = `message ${role}`;

  const label = document.createElement('div');
  label.className = 'message-label';
  label.textContent = role === 'user' ? 'You' : role === 'assistant' ? 'Sheppard' : '';
  if (label.textContent) div.appendChild(label);

  const bubble = document.createElement('div');
  bubble.className = 'message-bubble';
  bubble.textContent = content;
  div.appendChild(bubble);

  history.appendChild(div);
  scrollChatToBottom();
  return bubble;
}

function scrollChatToBottom() {
  const h = document.getElementById('chat-history');
  h.scrollTop = h.scrollHeight;
}

function renderMissionFilters() {
  const list = document.getElementById('mission-filter-list');
  list.innerHTML = '';

  const all = document.createElement('div');
  all.className = 'mission-filter-item all-item' + (state.selectedMissionFilter === null ? ' selected' : '');
  all.textContent = 'All knowledge';
  all.addEventListener('click', () => {
    state.selectedMissionFilter = null;
    renderMissionFilters();
  });
  list.appendChild(all);

  // Only show missions that actually have atoms
  state.missions.filter(m => m.atom_count > 0).forEach(m => {
    const item = document.createElement('div');
    item.className = 'mission-filter-item' + (state.selectedMissionFilter === m.mission_id ? ' selected' : '');
    item.innerHTML = `<span>${esc(m.title)}</span><span style="font-size:10px;color:var(--grey2)">${m.atom_count}</span>`;
    item.title = m.title;
    item.addEventListener('click', () => {
      state.selectedMissionFilter = m.mission_id;
      renderMissionFilters();
    });
    list.appendChild(item);
  });
}

// ── MISSIONS TAB ───────────────────────────────────────────
let missionsShowAll = false;

async function loadMissions() {
  // refreshStatus runs every 5s and keeps state.missions + state.stats current.
  // Re-render from state immediately so the tab feels instant, then refresh in background.
  renderStats();
  renderMissionCards();
  try {
    const [missionsData, statsData] = await Promise.all([
      api('/missions'),
      api('/knowledge/stats'),
    ]);
    state.missions = missionsData.missions || [];
    state.stats = statsData;
    renderStats();
    renderMissionCards();
  } catch (e) {
    console.error('loadMissions failed:', e);
  }
}

function renderStats() {
  const s = state.stats;
  document.getElementById('stat-atoms').textContent    = (s.total_atoms || 0).toLocaleString();
  document.getElementById('stat-missions').textContent = (s.total_missions || 0).toString();
  document.getElementById('stat-concepts').textContent = (s.total_concepts || 0).toLocaleString();
  document.getElementById('stat-sources').textContent  = (s.total_sources || 0).toLocaleString();
}

function missionStatusClass(m) {
  if (m.crawling) return 'active';
  if (m.status === 'completed') return 'completed';
  if (m.status === 'active') return 'queued';   // active in DB but not actually running = stalled
  if (m.status === 'queued') return 'queued';
  return 'failed';
}

function missionStatusLabel(m) {
  if (m.crawling) return 'running';
  if (m.status === 'active') return 'stalled';
  return m.status;
}

function renderMissionCards() {
  const list = document.getElementById('missions-list');
  list.innerHTML = '';

  // Default: only show missions that have atoms or are actively crawling
  let visible = missionsShowAll
    ? state.missions
    : state.missions.filter(m => m.atom_count > 0 || m.crawling);

  if (!visible.length && !state.missions.length) {
    list.innerHTML = '<div class="empty-state"><div class="empty-icon">📡</div><div>No missions yet. Start one above.</div></div>';
    return;
  }

  if (!visible.length) {
    list.innerHTML = `<div class="empty-state" style="height:80px">
      <div style="color:var(--grey)">No missions with data yet.</div>
      <button class="btn-ghost" onclick="missionsShowAll=true; renderMissionCards()">Show all ${state.missions.length}</button>
    </div>`;
    return;
  }

  // Toggle bar
  const toggle = document.createElement('div');
  toggle.style.cssText = 'display:flex; justify-content:flex-end; margin-bottom:10px; font-size:12px; font-family:var(--font);';
  toggle.innerHTML = missionsShowAll
    ? `<button class="btn-ghost" onclick="missionsShowAll=false; renderMissionCards()">Show with data only (${state.missions.filter(m=>m.atom_count>0||m.crawling).length})</button>`
    : `<button class="btn-ghost" onclick="missionsShowAll=true; renderMissionCards()">Show all ${state.missions.length}</button>`;
  list.appendChild(toggle);

  visible.forEach(m => {
    const card = document.createElement('div');
    card.className = 'mission-card';
    card.addEventListener('click', () => openMissionModal(m.mission_id));

    const dotClass = missionStatusClass(m);
    const label = missionStatusLabel(m);
    const bytes = m.bytes_ingested > 0 ? `${(m.bytes_ingested / 1024 / 1024).toFixed(1)} MB` : '—';
    const budget = m.budget_bytes > 0 ? `${(m.budget_bytes / 1024 / 1024 / 1024).toFixed(1)} GB` : '—';

    card.innerHTML = `
      <div class="mission-status-dot ${dotClass}"></div>
      <div class="mission-info">
        <div class="mission-title">${esc(m.title)}</div>
        <div class="mission-meta">${label} · ${m.created_at ? new Date(m.created_at).toLocaleDateString() : '—'}</div>
      </div>
      <div class="mission-stats">
        <div class="mission-stat">
          <div class="mission-stat-val">${m.atom_count.toLocaleString()}</div>
          <div class="mission-stat-lbl">atoms</div>
        </div>
        <div class="mission-stat">
          <div class="mission-stat-val">${m.source_count.toLocaleString()}</div>
          <div class="mission-stat-lbl">sources</div>
        </div>
        <div class="mission-stat">
          <div class="mission-stat-val">${bytes}</div>
          <div class="mission-stat-lbl">/ ${budget}</div>
        </div>
      </div>
      <div class="mission-actions">
        <button class="btn-ghost btn-delete" onclick="event.stopPropagation(); deleteMission('${m.mission_id}', '${esc(m.title)}')" title="Delete mission">✕</button>
      </div>
    `;
    list.appendChild(card);
  });
}

async function startMission() {
  const input = document.getElementById('new-mission-input');
  const topic = input.value.trim();
  if (!topic) return;

  input.disabled = true;
  try {
    await api('/missions', {
      method: 'POST',
      body: JSON.stringify({ topic, ceiling_gb: 5.0 }),
    });
    input.value = '';
    await loadMissions();
    await refreshStatus();
  } catch (e) {
    alert(`Failed to start mission: ${e.message}`);
  } finally {
    input.disabled = false;
  }
}

async function deleteMission(id, title) {
  if (!confirm(`Delete "${title}"?\n\nThis removes the mission and all its atoms permanently.`)) return;
  try {
    const res = await fetch(`/api/missions/${id}`, { method: 'DELETE' });
    if (!res.ok && res.status !== 404) {
      throw new Error(`${res.status} ${await res.text()}`);
    }
    await loadMissions();
    await refreshStatus();
  } catch (e) {
    alert(`Delete failed: ${e.message}`);
  }
}

async function purgeEmptyMissions() {
  const empty = state.missions.filter(m => m.atom_count === 0 && !m.crawling);
  if (!empty.length) { alert('No empty missions to purge.'); return; }
  if (!confirm(`Delete ${empty.length} missions with zero atoms?`)) return;
  for (const m of empty) {
    try { await api(`/missions/${m.mission_id}`, { method: 'DELETE' }); } catch (_) {}
  }
  await loadMissions();
  await refreshStatus();
}

async function openMissionModal(id) {
  const overlay = document.getElementById('mission-modal-overlay');
  const titleEl = document.getElementById('mission-modal-title');
  const body = document.getElementById('mission-modal-body');
  body.innerHTML = '<div style="color:var(--grey)">Loading...</div>';
  overlay.classList.remove('hidden');

  try {
    const data = await api(`/missions/${id}`);
    const m = data.mission;
    titleEl.textContent = m.title;

    const bytes = (m.bytes_ingested / 1024 / 1024).toFixed(1);
    const budgetGb = (m.budget_bytes / 1024 / 1024 / 1024).toFixed(1);

    body.innerHTML = `
      <div style="display:grid; grid-template-columns:1fr 1fr; gap:8px 20px; margin-bottom:16px; color:var(--grey)">
        <div><span class="grey">Status:</span> <span class="crimson">${m.status}</span></div>
        <div><span class="grey">Atoms:</span> <span style="color:var(--white)">${m.atom_count}</span></div>
        <div><span class="grey">Sources:</span> <span style="color:var(--white)">${m.source_count}</span></div>
        <div><span class="grey">Data:</span> <span style="color:var(--white)">${bytes} MB / ${budgetGb} GB</span></div>
        <div style="grid-column:span 2"><span class="grey">Objective:</span> <span style="color:var(--white)">${esc(m.objective)}</span></div>
      </div>
      <div style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:var(--grey); margin-bottom:8px;">Recent Atoms</div>
      <div style="display:flex; flex-direction:column; gap:6px; margin-bottom:16px;">
        ${data.atoms.slice(0, 15).map(a => `
          <div style="padding:8px 10px; background:var(--bg3); border-radius:4px; font-size:12px; line-height:1.5; color:var(--white)">
            ${esc(a.statement)}
            <span style="float:right; color:var(--grey); font-size:10px">${(a.confidence * 100 || 0).toFixed(0)}%</span>
          </div>
        `).join('')}
        ${data.atoms.length === 0 ? '<div style="color:var(--grey)">No atoms yet.</div>' : ''}
      </div>
      <div style="font-size:11px; text-transform:uppercase; letter-spacing:1px; color:var(--grey); margin-bottom:8px;">Recent Events</div>
      <div style="display:flex; flex-direction:column; gap:3px;">
        ${data.events.slice(0, 10).map(e => `
          <div style="display:flex; gap:10px; font-size:11px; padding:4px 0; border-bottom:1px solid var(--border)">
            <span style="color:var(--grey2)">${e.created_at ? new Date(e.created_at).toLocaleTimeString() : ''}</span>
            <span style="color:var(--crimson)">${esc(e.event_type || '')}</span>
          </div>
        `).join('')}
        ${data.events.length === 0 ? '<div style="color:var(--grey)">No events.</div>' : ''}
      </div>
    `;
  } catch (e) {
    body.innerHTML = `<div style="color:var(--crimson)">Error: ${esc(e.message)}</div>`;
  }
}

function closeMissionModal() {
  document.getElementById('mission-modal-overlay').classList.add('hidden');
}

// ── KNOWLEDGE TAB ──────────────────────────────────────────
async function loadKnowledge() {
  loadConcepts();
  if (state.knowledge.view === 'graph') {
    renderGraph();
  } else {
    loadAtoms();
  }
}

async function loadConcepts() {
  try {
    const data = await api('/knowledge/concepts?limit=80');
    renderConceptList(data.concepts || []);
  } catch (e) {
    console.error('loadConcepts failed:', e);
  }
}

function renderConceptList(concepts) {
  const list = document.getElementById('concept-list');
  list.innerHTML = '';

  if (!concepts.length) {
    list.innerHTML = '<div class="empty-state" style="padding:20px; height:auto">No concepts yet</div>';
    return;
  }

  concepts.forEach(c => {
    const item = document.createElement('div');
    item.className = 'concept-item' + (state.knowledge.selectedConcept === c.name ? ' selected' : '');
    item.innerHTML = `<span>${esc(c.name)}</span><span class="concept-count">${c.count}</span>`;
    item.addEventListener('click', () => {
      state.knowledge.selectedConcept = c.name;
      state.knowledge.atomsOffset = 0;
      renderConceptList(concepts);
      if (state.knowledge.view === 'atoms') loadAtoms();
      else { setKnowledgeView('atoms'); }
    });
    list.appendChild(item);
  });
}

function setKnowledgeView(view) {
  state.knowledge.view = view;
  document.querySelectorAll('.view-btn').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  document.getElementById('graph-container').classList.toggle('hidden', view !== 'graph');
  document.getElementById('atoms-container').classList.toggle('hidden', view !== 'atoms');
  document.getElementById('atoms-pagination').classList.toggle('hidden', view !== 'atoms');
  const controls = document.getElementById('atoms-controls');
  if (controls) controls.classList.toggle('hidden', view !== 'atoms');
  if (view === 'graph') renderGraph();
  else loadAtoms();
}

// ── D3 Force Graph ─────────────────────────────────────────
async function renderGraph() {
  const container = document.getElementById('graph-container');
  const tooltip = document.getElementById('graph-tooltip');
  container.innerHTML = '';
  container.appendChild(tooltip);

  let graphData;
  try {
    graphData = await api('/knowledge/graph');
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">🔗</div><div>Failed to load graph: ${esc(e.message)}</div></div>`;
    return;
  }

  if (!graphData.nodes.length) {
    container.innerHTML = '<div class="empty-state"><div class="empty-icon">🔗</div><div>No knowledge graph yet. Run a /learn mission first.</div></div>';
    return;
  }

  const W = container.clientWidth;
  const H = container.clientHeight;

  const svg = d3.select(container)
    .append('svg')
    .attr('width', W)
    .attr('height', H)
    .style('background', '#0a0a0a');

  const g = svg.append('g');

  // Zoom + pan
  svg.call(d3.zoom()
    .scaleExtent([0.1, 5])
    .on('zoom', e => g.attr('transform', e.transform))
  );

  // Color and size
  const color = d => d.type === 'mission' ? '#dc143c' : '#444488';
  const maxWeight = Math.max(...graphData.nodes.map(d => d.weight || 1), 1);
  const radius = d => {
    const w = d.weight || 1;
    if (d.type === 'mission') return Math.max(10, Math.min(28, 10 + (w / maxWeight) * 18));
    return Math.max(4, Math.min(14, 4 + (w / maxWeight) * 10));
  };

  const simulation = d3.forceSimulation(graphData.nodes)
    .force('link', d3.forceLink(graphData.links).id(d => d.id).distance(80).strength(0.5))
    .force('charge', d3.forceManyBody().strength(-120))
    .force('center', d3.forceCenter(W / 2, H / 2))
    .force('collision', d3.forceCollide().radius(d => radius(d) + 4));

  const link = g.append('g')
    .selectAll('line')
    .data(graphData.links)
    .join('line')
    .attr('stroke', '#2a2a2a')
    .attr('stroke-width', d => Math.max(1, Math.min(3, d.value * 0.2)));

  const node = g.append('g')
    .selectAll('g')
    .data(graphData.nodes)
    .join('g')
    .attr('cursor', 'pointer')
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
      .on('drag',  (e, d) => { d.fx = e.x; d.fy = e.y; })
      .on('end',   (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; })
    );

  node.append('circle')
    .attr('r', radius)
    .attr('fill', color)
    .attr('stroke', d => d.type === 'mission' ? '#ff2a52' : '#666688')
    .attr('stroke-width', 1.5);

  node.append('text')
    .attr('dy', d => radius(d) + 12)
    .attr('text-anchor', 'middle')
    .attr('font-size', d => d.type === 'mission' ? 11 : 9)
    .attr('font-family', 'monospace')
    .attr('fill', d => d.type === 'mission' ? '#ffffff' : '#888888')
    .text(d => d.label.length > 18 ? d.label.slice(0, 17) + '…' : d.label);

  // Tooltip
  node
    .on('mouseenter', (e, d) => {
      const lines = [`<strong>${esc(d.label)}</strong>`];
      if (d.type === 'mission') {
        lines.push(`${(d.weight || 0).toLocaleString()} atoms`);
        if (d.avg_conf) lines.push(`avg confidence: ${(d.avg_conf * 100).toFixed(0)}%`);
        if (d.run_count > 1) lines.push(`${d.run_count} runs`);
        lines.push(`status: ${d.status}`);
      } else {
        lines.push(`${(d.weight || 0)} atoms`);
      }
      tooltip.innerHTML = lines.join('<br>');
      tooltip.style.opacity = '1';
    })
    .on('mousemove', e => {
      const rect = container.getBoundingClientRect();
      tooltip.style.left = (e.clientX - rect.left + 12) + 'px';
      tooltip.style.top  = (e.clientY - rect.top  + 12) + 'px';
    })
    .on('mouseleave', () => {
      tooltip.style.opacity = '0';
    })
    .on('click', (e, d) => {
      if (d.type === 'concept') {
        state.knowledge.selectedConcept = d.label;
        state.knowledge.atomsOffset = 0;
        setKnowledgeView('atoms');
      } else if (d.type === 'mission') {
        state.knowledge.selectedConcept = null;
        state.knowledge.atomsOffset = 0;
        // Concept graph: d.id is a real mission UUID
        // Fallback graph: d.id is "topic:..." — find a matching mission by title
        if (d.id.startsWith('topic:')) {
          const match = state.missions.find(m => m.title.toLowerCase() === d.label.toLowerCase() && m.atom_count > 0);
          state.knowledge.missionFilter = match ? match.mission_id : null;
        } else {
          state.knowledge.missionFilter = d.id;
        }
        setKnowledgeView('atoms');
      }
    });

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    node.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

// ── Atom table ─────────────────────────────────────────────
async function loadAtoms() {
  const container = document.getElementById('atoms-container');
  container.innerHTML = '<div class="empty-state" style="height:80px"><div style="color:var(--grey)">Loading atoms...</div></div>';

  try {
    const params = new URLSearchParams({
      limit: state.knowledge.atomsLimit,
      offset: state.knowledge.atomsOffset,
      min_confidence: state.knowledge.minConfidence,
      sort: state.knowledge.sort,
    });
    if (state.knowledge.selectedConcept) params.set('concept', state.knowledge.selectedConcept);
    if (state.knowledge.missionFilter) params.set('mission_id', state.knowledge.missionFilter);

    const data = await api(`/knowledge/atoms?${params}`);
    state.knowledge.atomsTotal = data.total;
    renderAtomTable(data.atoms);
    renderAtomPagination();
  } catch (e) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon">⚠️</div><div>Failed: ${esc(e.message)}</div></div>`;
  }
}

function renderAtomTable(atoms) {
  const container = document.getElementById('atoms-container');
  container.innerHTML = '';

  // Filter breadcrumb
  const filters = [];
  if (state.knowledge.selectedConcept) filters.push(`concept: <span class="crimson">${esc(state.knowledge.selectedConcept)}</span>`);
  if (state.knowledge.missionFilter) {
    const m = state.missions.find(x => x.mission_id === state.knowledge.missionFilter);
    if (m) filters.push(`mission: <span class="crimson">${esc(m.title)}</span>`);
  }
  if (filters.length) {
    const crumb = document.createElement('div');
    crumb.style.cssText = 'padding:8px 14px; font-size:11px; font-family:var(--font); color:var(--grey); border-bottom:1px solid var(--border); display:flex; align-items:center; gap:12px;';
    crumb.innerHTML = `Filtered by ${filters.join(' · ')} <button class="btn-ghost" style="padding:2px 8px; font-size:11px" onclick="clearAtomFilters()">✕ clear</button>`;
    container.appendChild(crumb);
  }

  if (!atoms.length) {
    const empty = document.createElement('div');
    empty.className = 'empty-state';
    empty.style.height = '200px';
    empty.innerHTML = '<div class="empty-icon">🔬</div><div>No atoms found.</div>';
    container.appendChild(empty);
    return;
  }

  atoms.forEach(a => {
    const row = document.createElement('div');
    row.className = 'atom-row';
    const conf = a.confidence != null ? `${(a.confidence * 100).toFixed(0)}%` : '—';
    row.innerHTML = `
      <span class="atom-type-badge ${a.atom_type || 'claim'}">${a.atom_type || 'claim'}</span>
      <span class="atom-text">${esc(a.statement || '')}</span>
      <div class="atom-meta">
        <span class="atom-conf">conf ${conf}</span>
        <span class="atom-mission">${esc(a.mission_title || '')}</span>
      </div>
    `;
    container.appendChild(row);
  });
}

function renderAtomPagination() {
  const pg = document.getElementById('atoms-pagination');
  const total = state.knowledge.atomsTotal;
  const offset = state.knowledge.atomsOffset;
  const limit = state.knowledge.atomsLimit;
  const page = Math.floor(offset / limit) + 1;
  const totalPages = Math.ceil(total / limit) || 1;

  pg.innerHTML = `
    <button class="btn-ghost" ${offset === 0 ? 'disabled' : ''} onclick="atomsPage(-1)">← Prev</button>
    <span>Page ${page} of ${totalPages} &nbsp;·&nbsp; ${total.toLocaleString()} atoms</span>
    <button class="btn-ghost" ${offset + limit >= total ? 'disabled' : ''} onclick="atomsPage(1)">Next →</button>
  `;
}

function atomsPage(dir) {
  state.knowledge.atomsOffset = Math.max(0,
    state.knowledge.atomsOffset + dir * state.knowledge.atomsLimit
  );
  loadAtoms();
}

function clearAtomFilters() {
  state.knowledge.selectedConcept = null;
  state.knowledge.missionFilter = null;
  state.knowledge.atomsOffset = 0;
  // Deselect concept in sidebar
  document.querySelectorAll('.concept-item').forEach(i => i.classList.remove('selected'));
  loadAtoms();
}

// ── LOGS TAB ───────────────────────────────────────────────
function initLogs() {
  // Level filter buttons
  document.querySelectorAll('.level-btn').forEach(btn => {
    const lvl = btn.dataset.level;
    if (state.logs.levels.has(lvl)) btn.classList.add('active', lvl);
    btn.addEventListener('click', () => {
      if (state.logs.levels.has(lvl)) {
        state.logs.levels.delete(lvl);
        btn.classList.remove('active', lvl);
      } else {
        state.logs.levels.add(lvl);
        btn.classList.add('active', lvl);
      }
    });
  });

  // Search filter
  document.getElementById('logs-search').addEventListener('input', e => {
    state.logs.filter = e.target.value.toLowerCase();
  });

  connectLogsWs();
}

function connectLogsWs() {
  if (logsWs && logsWs.readyState <= 1) return;
  logsWs = new WebSocket(`ws://${location.host}/api/ws/logs`);

  logsWs.onopen = () => {
    updateLogsStatus('connected');
  };

  logsWs.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      if (msg.ping) return;
      appendLogLine(msg);
    } catch (_) {}
  };

  logsWs.onclose = () => {
    updateLogsStatus('reconnecting...');
    logsReconnectTimer = setTimeout(connectLogsWs, 3000);
  };

  logsWs.onerror = () => logsWs.close();
}

function updateLogsStatus(text) {
  const el = document.getElementById('logs-status');
  if (el) el.textContent = text;
}

const MAX_LOG_LINES = 1000;
let logLineCount = 0;

function appendLogLine(msg) {
  if (!state.logs.levels.has(msg.level)) return;
  if (state.logs.filter && !`${msg.name} ${msg.msg}`.toLowerCase().includes(state.logs.filter)) return;

  const container = document.getElementById('log-container');
  const atBottom = container.scrollHeight - container.clientHeight - container.scrollTop < 40;

  const line = document.createElement('div');
  line.className = `log-line ${msg.level}`;
  line.innerHTML = `
    <span class="log-ts">${esc(msg.ts)}</span>
    <span class="log-level">${msg.level}</span>
    <span class="log-name" title="${esc(msg.name)}">${esc(msg.name)}</span>
    <span class="log-msg">${esc(msg.msg)}</span>
  `;
  container.appendChild(line);
  logLineCount++;

  // Trim old lines
  while (logLineCount > MAX_LOG_LINES) {
    container.removeChild(container.firstChild);
    logLineCount--;
  }

  if (atBottom) container.scrollTop = container.scrollHeight;
}

// ── Concept search filter ──────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('concept-search').addEventListener('input', e => {
    const q = e.target.value.toLowerCase();
    document.querySelectorAll('.concept-item').forEach(item => {
      const name = item.querySelector('span:first-child').textContent.toLowerCase();
      item.style.display = name.includes(q) ? '' : 'none';
    });
  });
});

// ── Escape HTML helper ─────────────────────────────────────
function esc(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Boot ───────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  // Tab clicks
  document.querySelectorAll('.tab').forEach(t => {
    t.addEventListener('click', () => switchTab(t.dataset.tab));
  });

  // View toggle buttons in knowledge tab
  document.querySelectorAll('.view-btn').forEach(b => {
    b.addEventListener('click', () => setKnowledgeView(b.dataset.view));
  });

  // Mission modal close
  document.getElementById('mission-modal-close').addEventListener('click', closeMissionModal);
  document.getElementById('mission-modal-overlay').addEventListener('click', e => {
    if (e.target === e.currentTarget) closeMissionModal();
  });

  // New mission form
  document.getElementById('new-mission-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') startMission();
  });
  document.getElementById('start-mission-btn').addEventListener('click', startMission);

  // Confidence slider
  const slider = document.getElementById('conf-slider');
  const confLabel = document.getElementById('conf-label');
  if (slider) {
    slider.addEventListener('input', () => {
      const val = parseInt(slider.value);
      confLabel.textContent = val + '%';
      state.knowledge.minConfidence = val / 100;
    });
    slider.addEventListener('change', () => {
      state.knowledge.atomsOffset = 0;
      loadAtoms();
    });
  }

  // Sort select
  const sortSelect = document.getElementById('sort-select');
  if (sortSelect) {
    sortSelect.addEventListener('change', () => {
      state.knowledge.sort = sortSelect.value;
      state.knowledge.atomsOffset = 0;
      loadAtoms();
    });
  }

  initChat();
  initLogs();
  refreshStatus();

  // Refresh status every 5s
  setInterval(refreshStatus, 5000);
});
