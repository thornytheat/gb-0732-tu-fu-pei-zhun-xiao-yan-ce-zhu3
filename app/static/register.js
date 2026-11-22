import {badge, el, fmt, reason, renderLedger} from './ledgers.js';
import {drawAtlas, drawEdge} from './plots.js';

const byId = id => document.getElementById(id);
const form = byId('run-form');
const sign = byId('signature-form');
const links = [...document.querySelectorAll('[data-section]')];
const state = {snapshot: null, catalog: null, preview: null, section: null, selected: null, edgeId: null,
  busy: false, signing: false, previewToken: 0, reused: false};
const formatTime = new Intl.DateTimeFormat('zh-CN', {timeZone: 'Asia/Shanghai', dateStyle: 'medium', timeStyle: 'medium'});
const sides = {N: '北', E: '东', S: '南', W: '西'};

function parameters() {
  const fields = new FormData(form);
  return {dataset: fields.get('dataset'), control_limit_m: Number(fields.get('control_limit_m')),
    seam_limit_m: Number(fields.get('seam_limit_m'))};
}

async function request(url, options) {
  let response;
  try {
    response = await fetch(url, options);
  } catch {
    throw new Error('服务暂不可达，请重试。');
  }
  if (!response.ok) {
    const error = await response.json().catch(() => null);
    throw new Error(error?.detail?.message || `请求失败，请重试。${response.status}`);
  }
  return response.json();
}

const post = (url, payload) => request(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});

function feedback(id, message) {
  const node = byId(id);
  node.textContent = message || '';
  node.hidden = !message;
}

function activeEdge() {
  return state.snapshot?.seams.edges.find(item => item.code === state.edgeId);
}

function plot() {
  const snapshot = state.snapshot;
  const blocked = state.selected && snapshot?.refit.sheets[state.selected].status !== 'FIT';
  byId('atlas-unit').textContent = blocked ? '原始像素 / px' : '局部平面 / m';
  byId('atlas-legend').hidden = Boolean(blocked);
  drawAtlas(byId('atlas-plot'), snapshot, state.selected, state.edgeId);
  drawEdge(byId('edge-plot'), activeEdge());
}

function renderSheetIndex() {
  const root = byId('sheet-index');
  const signed = new Set(state.snapshot?.signatures.map(item => item.sheet) || []);
  root.replaceChildren();
  for (const sheet of state.catalog?.sheets || []) {
    const button = el('button', null, 'sheet-item');
    button.type = 'button';
    button.dataset.sheet = sheet.code;
    button.setAttribute('aria-pressed', String(sheet.code === state.selected));
    button.disabled = !state.snapshot;
    button.append(el('span', sheet.code, 'num'), el('span', sheet.title));
    const decision = state.snapshot?.reviews.find(item => item.code === sheet.code);
    if (decision) button.append(badge(signed.has(sheet.code) ? 'SIGNED' : decision.status));
    root.append(button);
  }
  byId('all-sheets').disabled = !state.selected;
  const catalog = state.catalog;
  byId('origin').textContent = catalog ? `${catalog.longitude_deg.toFixed(4)}°E / ${catalog.latitude_deg.toFixed(4)}°N` : '—';
  byId('data-version').textContent = catalog?.version || '—';
}

function renderSeamIndex() {
  const root = byId('seam-index');
  root.replaceChildren();
  const results = state.snapshot?.seams.edges || state.catalog?.edges || [];
  for (const edge of results) {
    const button = el('button', null, 'seam-item');
    button.type = 'button';
    button.dataset.edge = edge.code;
    button.disabled = !state.snapshot;
    button.setAttribute('aria-pressed', String(edge.code === state.edgeId));
    const key = el('span');
    key.append(el('strong', edge.code, 'num'), el('small', `${edge.a} ${sides[edge.a_side]} · ${edge.b} ${sides[edge.b_side]}`));
    const value = el('span');
    if (edge.status) value.append(badge(edge.status), el('small', edge.max_m == null ? '—' : `${fmt(edge.max_m)} m`, 'num'));
    button.append(key, value);
    root.append(button);
  }
  const edge = activeEdge();
  byId('edge-caption').textContent = edge ? (edge.max_m == null ? reason(edge.reason) : `沿甲边位置 % · 法向偏移 m`) : '';
}

function renderSign() {
  const eligible = state.snapshot?.reviews.filter(row => row.status === 'READY' &&
    !state.snapshot.signatures.some(signature => signature.sheet === row.code)) || [];
  sign.hidden = state.section !== 'review' || !eligible.length;
  const options = byId('signature-sheet');
  const selected = options.value;
  options.replaceChildren(...eligible.map(row => new Option(`${row.code} ${row.title}`, row.code)));
  if (eligible.some(row => row.code === selected)) options.value = selected;
  else if (eligible.some(row => row.code === state.selected)) options.value = state.selected;
}

function renderDetail() {
  if (!state.section) return;
  byId('section-detail').hidden = false;
  for (const link of links) {
    if (link.dataset.section === state.section) link.setAttribute('aria-current', 'location');
    else link.removeAttribute('aria-current');
  }
  byId('detail-title').textContent = links.find(link => link.dataset.section === state.section).textContent.trim().replace(/^\d+/, '');
  byId('detail-meta').textContent = state.snapshot ? (state.selected ? `图版 ${state.selected}` : '全册') : '档件预检';
  const limit = state.snapshot?.manifest.parameters.control_limit_m || parameters().control_limit_m;
  renderLedger(byId('detail-content'), state.section, {...state, limit});
  renderSign();
}

function showSnapshot(snapshot) {
  state.previewToken++;
  state.snapshot = snapshot;
  state.catalog = snapshot.catalog;
  state.preview = null;
  if (state.selected && !snapshot.refit.sheets[state.selected]) state.selected = null;
  if (!snapshot.seams.edges.some(edge => edge.code === state.edgeId)) state.edgeId = snapshot.seams.edges[0]?.code;
  const ledger = snapshot.ledger.controls;
  const values = {input: ledger.input, accepted: ledger.accepted, outlier: ledger.outlier, isolated: ledger.isolated,
    edges: snapshot.seams.edges.filter(edge => edge.status === 'PASS').length,
    ready: snapshot.reviews.filter(row => row.status === 'READY').length};
  for (const [key, value] of Object.entries(values)) byId(`k-${key}`).textContent = value;
  const manifest = snapshot.manifest;
  byId('edition').textContent = snapshot.catalog.title;
  byId('batch-id').textContent = manifest.run_id.slice(0, 12);
  byId('batch-id').title = manifest.run_id;
  byId('generated').textContent = `${formatTime.format(new Date(manifest.created_at))} · UTC+08:00 · ${manifest.rule_version}`;
  byId('run-state').textContent = state.reused ? '已复用同一批次 · 三表对账通过' : '校验完成 · 三表对账通过';
  const download = byId('download');
  download.href = `/api/review/runs/${manifest.run_id}/export`;
  download.removeAttribute('aria-disabled');
  byId('print').disabled = false;
  state.section ||= 'refit';
  renderSheetIndex();
  renderSeamIndex();
  plot();
  renderDetail();
}

async function readIndex() {
  const dataset = form.elements.dataset.value;
  try {
    const result = await request(`/api/intake?dataset=${encodeURIComponent(dataset)}`);
    if (!state.snapshot && dataset === form.elements.dataset.value) {
      state.catalog = result.catalog;
      renderSheetIndex();
      renderSeamIndex();
    }
  } catch (error) {
    if (!state.snapshot) feedback('run-error', error.message);
  }
}

async function selectSection(section, focus = false) {
  state.section = section;
  state.preview = null;
  const token = ++state.previewToken;
  feedback('signature-error', null);
  renderDetail();
  if (focus) byId('detail-title').focus({preventScroll: true});
  if (focus) byId('section-detail').scrollIntoView({block: 'start'});
  if (state.snapshot || section === 'review' || !form.reportValidity()) return;
  byId('detail-content').replaceChildren(el('p', '正在校验该章节。'));
  try {
    const value = await request(`/api/${section}?${new URLSearchParams(parameters())}`);
    if (state.previewToken !== token) return;
    state.preview = value;
    renderDetail();
  } catch (error) {
    if (state.previewToken === token) byId('detail-content').replaceChildren(el('p', error.message, 'feedback'));
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  if (state.busy || state.signing) return;
  state.busy = true;
  const button = byId('run');
  button.disabled = true;
  feedback('run-error', null);
  feedback('signature-error', null);
  byId('run-state').textContent = '正在校验档件…';
  try {
    const snapshot = await post('/api/review/runs', parameters());
    state.reused = snapshot.reused;
    showSnapshot(snapshot);
    button.textContent = '重跑校验';
  } catch (error) {
    feedback('run-error', error.message);
    byId('run-state').textContent = '校验失败 · 可重试';
  } finally {
    state.busy = false;
    button.disabled = false;
  }
});

sign.addEventListener('submit', async event => {
  event.preventDefault();
  if (state.busy || state.signing) return;
  state.signing = true;
  const button = sign.querySelector('button');
  button.disabled = true;
  const runId = state.snapshot.manifest.run_id;
  feedback('signature-error', null);
  try {
    const sheet = byId('signature-sheet').value;
    const reviewer = byId('reviewer').value;
    await post(`/api/review/runs/${runId}/signatures`, {sheet, reviewer, expected_version: 0});
    showSnapshot(await request(`/api/review/runs/${runId}`));
    byId('run-state').textContent = `${sheet} 已签审入册`;
  } catch (error) {
    feedback('signature-error', error.message);
  } finally {
    state.signing = false;
    button.disabled = false;
  }
});

for (const link of links) link.addEventListener('click', event => {
  event.preventDefault();
  history.replaceState(null, '', link.hash);
  selectSection(link.dataset.section, true);
});

byId('sheet-index').addEventListener('click', event => {
  const item = event.target.closest('[data-sheet]');
  if (!item || !state.snapshot) return;
  state.selected = item.dataset.sheet;
  renderSheetIndex();
  byId('sheet-index').querySelector(`[data-sheet="${state.selected}"]`).focus({preventScroll: true});
  plot();
  renderDetail();
});
byId('all-sheets').addEventListener('click', () => {
  state.selected = null;
  renderSheetIndex();
  byId('sheet-index').querySelector('button')?.focus({preventScroll: true});
  plot();
  renderDetail();
});
byId('seam-index').addEventListener('click', event => {
  const item = event.target.closest('[data-edge]');
  if (!item || !state.snapshot) return;
  state.edgeId = item.dataset.edge;
  renderSeamIndex();
  byId('seam-index').querySelector(`[data-edge="${state.edgeId}"]`).focus({preventScroll: true});
  plot();
  selectSection('seams');
});
form.addEventListener('change', () => {
  if (!state.snapshot) {
    feedback('run-error', null);
    readIndex();
    if (state.section) selectSection(state.section);
  }
});
byId('print').addEventListener('click', () => window.print());
let frame;
const redraw = () => {
  cancelAnimationFrame(frame);
  frame = requestAnimationFrame(() => {
    plot();
    if (state.section === 'refit') renderDetail();
  });
};
window.addEventListener('resize', redraw);
window.addEventListener('beforeprint', plot);
window.addEventListener('afterprint', redraw);
plot();
readIndex();
const sectionFromHash = links.find(link => link.hash === location.hash);
if (sectionFromHash) selectSection(sectionFromHash.dataset.section);
