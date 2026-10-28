const $ = (id) => document.getElementById(id);
const state = { project: null, segments: [], captions: [], jobs: new Map(), sourceJob: null, exportJob: null,
  capabilities: {}, features: [], saveTimer: null, restoring: false, selectedSegment: 0,
  assetJob: null, assetBusy: false, assetUpload: null };

function node(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = value;
    else if (key.startsWith('on')) el.addEventListener(key.slice(2).toLowerCase(), value);
    else if (key === 'disabled') el.disabled = value;
    else el.setAttribute(key, value);
  }
  for (const child of children) if (child !== null && child !== undefined) el.append(child);
  return el;
}
function icon(name) {
  const el = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  el.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', `#i-${name}`); el.append(use); return el;
}
function notify(message) { $('notice-text').textContent = message; $('notice').hidden = false; }
function errorText(detail) {
  if (Array.isArray(detail)) return detail.map(x => x.msg || String(x)).join('; ');
  return typeof detail === 'string' ? detail : 'The request could not be completed. Please retry.';
}
async function request(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body && !(options.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const response = await fetch(path, { ...options, headers, credentials: 'same-origin' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401) showLogin();
    throw new Error(errorText(data.detail || data.error || data.message));
  }
  return data;
}
const post = (path, data) => request(path, { method: 'POST', body: JSON.stringify(data || {}) });
const patch = (path, data) => request(path, { method: 'PATCH', body: JSON.stringify(data) });
function safely(fn) { return async (event) => { try { await fn(event); } catch (error) { notify(error.message); } }; }
function seconds(value) { const n = Number(value); return Number.isFinite(n) ? n : 0; }
function duration() { return state.segments.reduce((sum, segment) => sum + Math.max(0, segment.end - segment.start), 0) / (Number($('speed').value) || 1); }
function timeLabel(value) { const sec = Math.max(0, Math.floor(seconds(value))); return `${Math.floor(sec / 60).toString().padStart(2, '0')}:${(sec % 60).toString().padStart(2, '0')}`; }
function dateLabel(value) {
  if (!value) return '';
  const date = typeof value === 'number' ? new Date(value * 1000) : new Date(value);
  return Number.isNaN(date.valueOf()) ? '' : date.toLocaleString();
}
function setBusy(button, busy, label) { button.disabled = busy; if (label) button.textContent = label; }
function showLogin() { $('login').hidden = false; $('app').hidden = true; }
function showView(view) {
  for (const name of ['workspace', 'history', 'features', 'settings']) $(`${name}-view`).hidden = name !== view;
  document.querySelectorAll('[data-view]').forEach(button => {
    button.classList.toggle('selected', button.dataset.view === view);
    if (button.dataset.view === view) button.setAttribute('aria-current', 'page'); else button.removeAttribute('aria-current');
  });
  $('view-label').textContent = { workspace: 'Workspace', history: 'URL history', features: 'Feature coverage', settings: 'Settings' }[view];
  if (view === 'history') loadHistory().catch(error => notify(error.message));
  if (view === 'features') loadFeatures().catch(error => notify(error.message));
}

function themePreference() { try { return JSON.parse(localStorage.getItem('studio-theme') || '{}'); } catch { return {}; } }
function applyTheme() {
  const preference = themePreference();
  const mode = preference.mode || 'light';
  const dark = mode === 'dark' || (mode === 'system' && matchMedia('(prefers-color-scheme: dark)').matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  if (preference.accent && /^#[0-9a-f]{6}$/i.test(preference.accent)) document.documentElement.style.setProperty('--accent', preference.accent);
  else document.documentElement.style.removeProperty('--accent');
  $('appearance').value = mode;
  $('accent').value = preference.accent || (dark ? '#79bea2' : '#246a57');
}
function saveTheme() {
  localStorage.setItem('studio-theme', JSON.stringify({ mode: $('appearance').value, accent: $('accent').value }));
  applyTheme();
}

async function enterStudio() {
  $('login').hidden = true; $('app').hidden = false;
  const [capabilities, health, projects] = await Promise.all([
    request('/api/capabilities'), request('/api/health'), request('/api/projects')
  ]);
  state.capabilities = capabilities;
  $('connection').lastChild.textContent = health.status === 'ok' || health.status === 'ready' ? 'Studio online' : 'Studio connected';
  $('runtime-info').textContent = capabilities.ffmpeg ? 'Video rendering is available. Heavy jobs run in the background.' : 'FFmpeg is not available on this server. Rendering needs server setup.';
  $('transcribe').disabled = !capabilities.transcription;
  $('suggest').disabled = !capabilities.transcription;
  $('ai-status').textContent = capabilities.transcription ? 'Speech tools are ready. Review suggestions before applying them.' : (capabilities.ai_reason || 'Speech tools need a local transcription model before they can run. Manual editing and captions are available.');
  const list = Array.isArray(projects) ? projects : projects.projects || [];
  const remembered = sessionStorage.getItem('studio-project');
  const project = list.find(p => !p.media && p.active_job) || list.find(p => p.id === remembered) || list[0];
  if (project) await loadProject(project.id);
}

function collectOptions() {
  return { segments: state.segments.map(({ start, end }) => ({ start, end })), aspect: $('aspect').value,
    resolution: Number($('resolution').value), fit: $('fit').value, mute: $('mute').checked,
    enhance_audio: $('enhance-audio').checked, volume: Number($('volume').value), speed: Number($('speed').value), text: $('overlay-text').value,
    captions: state.captions.map(c => ({ start: c.start, end: c.end, text: c.text })), caption_style: $('caption-style').value,
    transition: $('transition').value, caption_color: $('caption-color').value,
    caption_background: $('caption-background').value, text_color: $('text-color').value,
    logo_asset_id: $('logo-asset').value || null, music_asset_id: $('music-asset').value || null,
    font_asset_id: $('font-asset').value || null, logo_position: $('logo-position').value,
    music_volume: Number($('music-volume').value) };
}
function queueSave() {
  if (!state.project || state.restoring) return;
  if (state.segments.some(s => !Number.isFinite(s.start) || !Number.isFinite(s.end) || s.start < 0 || s.end <= s.start || s.end > state.project.media.duration + .01) ||
      state.captions.some(c => !Number.isFinite(c.start) || !Number.isFinite(c.end) || c.start < 0 || c.end <= c.start || c.end > duration() + .01)) {
    clearTimeout(state.saveTimer); $('save-status').textContent = 'Check timings'; return;
  }
  $('save-status').textContent = 'Saving…';
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(async () => {
    const id = state.project?.id;
    if (!id) return;
    try {
      await patch(`/api/projects/${id}`, { name: $('project-name').value || 'Untitled clip', edits: collectOptions() });
      if (state.project?.id === id) $('save-status').textContent = 'Session saved';
    } catch (error) { $('save-status').textContent = 'Save failed'; notify(error.message); }
  }, 450);
}
function updateDuration() { $('total-duration').textContent = `${duration().toFixed(1)}s`; }
function segmentInput(segment, index, key) {
  const label = node('label', {}, key === 'start' ? 'In (seconds)' : 'Out (seconds)');
  const input = node('input', { type: 'number', min: '0', max: state.project.media.duration, step: '.1',
    value: segment[key], required: '', 'aria-label': `Clip ${key} ${index + 1}` });
  input.addEventListener('focus', () => { state.selectedSegment = index; });
  input.addEventListener('input', () => { segment[key] = Number(input.value); updateDuration(); queueSave(); });
  label.append(input); return label;
}
function renderSegments() {
  const list = $('segments'); list.replaceChildren();
  state.segments.forEach((segment, index) => {
    const actions = node('div', { class: 'segment-actions' });
    for (const [label, symbol, delta] of [['Move segment up', '↑', -1], ['Move segment down', '↓', 1]]) {
      actions.append(node('button', { class: 'icon-button', type: 'button', 'aria-label': `${label} ${index + 1}`,
        disabled: index + delta < 0 || index + delta >= state.segments.length,
        onclick: () => { const other = index + delta; [state.segments[index], state.segments[other]] = [state.segments[other], state.segments[index]]; renderSegments(); queueSave(); } }, symbol));
    }
    actions.append(node('button', { class: 'icon-button', type: 'button', 'aria-label': `Remove segment ${index + 1}`, disabled: state.segments.length < 2,
      onclick: () => { state.segments.splice(index, 1); state.selectedSegment = Math.min(state.selectedSegment, state.segments.length - 1); renderSegments(); queueSave(); } }, '×'));
    list.append(node('div', { class: 'segment-row' }, node('span', { class: 'segment-number' }, String(index + 1).padStart(2, '0')),
      segmentInput(segment, index, 'start'), segmentInput(segment, index, 'end'), actions));
  });
  updateDuration();
}
function renderCaptions() {
  const list = $('captions'); list.replaceChildren();
  state.captions.forEach((caption, index) => {
    const times = node('div', { class: 'caption-times' });
    for (const key of ['start', 'end']) {
      const input = node('input', { type: 'number', min: '0', step: '.1', value: caption[key], required: '', 'aria-label': `Caption ${key} ${index + 1}` });
      input.addEventListener('input', () => { caption[key] = Number(input.value); queueSave(); });
      times.append(node('label', {}, key === 'start' ? 'Start (seconds)' : 'End (seconds)', input));
    }
    times.append(node('button', { class: 'text-button danger-text', type: 'button', 'aria-label': `Remove caption ${index + 1}`,
      onclick: () => { state.captions.splice(index, 1); renderCaptions(); queueSave(); } }, 'Remove'));
    const text = node('input', { type: 'text', value: caption.text, maxlength: '500', 'aria-label': `Caption text ${index + 1}`, placeholder: 'Caption text', required: '' });
    text.addEventListener('input', () => { caption.text = text.value; queueSave(); });
    list.append(node('div', { class: 'caption-row' }, times, node('label', {}, 'Text', text)));
  });
}
function applyOptions(options = {}) {
  state.segments = options.segments?.length ? structuredClone(options.segments) : [{ start: 0, end: Math.min(30, state.project.media.duration) }];
  state.captions = structuredClone(options.captions || []);
  for (const [id, key, fallback] of [['aspect', 'aspect', 'original'], ['resolution', 'resolution', '720'], ['fit', 'fit', 'contain'],
    ['caption-style', 'caption_style', 'clean'], ['overlay-text', 'text', ''], ['volume', 'volume', '1'], ['speed', 'speed', '1'],
    ['transition', 'transition', 'none'], ['caption-color', 'caption_color', '#ffffff'], ['caption-background', 'caption_background', '#000000'],
    ['text-color', 'text_color', '#ffffff'], ['logo-position', 'logo_position', 'top-right'], ['music-volume', 'music_volume', '.2'],
    ['logo-asset', 'logo_asset_id', ''], ['music-asset', 'music_asset_id', ''], ['font-asset', 'font_asset_id', '']]) $(id).value = options[key] ?? fallback;
  $('mute').checked = options.mute || false; $('enhance-audio').checked = options.enhance_audio || false;
  $('volume-value').value = `${Math.round(Number($('volume').value) * 100)}%`;
  $('music-volume-value').value = `${Math.round(Number($('music-volume').value) * 100)}%`;
  renderSegments(); renderCaptions();
}
function renderAssets(assets = []) {
  for (const kind of ['logo', 'music', 'font']) {
    const select = $(`${kind}-asset`); const selected = select.value;
    select.replaceChildren(node('option', { value: '' }, kind === 'font' ? 'Default studio font' : 'None'));
    for (const asset of assets.filter(item => item.kind === kind)) select.append(node('option', { value: asset.id }, asset.name));
    select.value = assets.some(asset => asset.id === selected) ? selected : '';
  }
  $('asset-count').textContent = `${assets.length} of 10 temporary assets`;
}
function setAssetBusy(busy) {
  state.assetBusy = busy;
  for (const type of ['logo', 'music', 'font']) $(`${type}-file`).disabled = busy;
}
async function trackAssetJob(id, projectId, name = 'Temporary asset') {
  state.assetJob = id; setAssetBusy(true); $('asset-job').hidden = false;
  sessionStorage.setItem('studio-asset-job', JSON.stringify({ id, projectId }));
  try {
    await watchJob(id, async () => {
      if (state.project?.id !== projectId) return;
      const updated = await request(`/api/projects/${projectId}`); state.project.assets = updated.assets;
      renderAssets(updated.assets || []); $('asset-job-message').textContent = `${name} is ready. Choose it above to apply it.`;
    });
  } finally {
    if (state.assetJob === id) {
      state.assetJob = null; setAssetBusy(false); $('asset-cancel').hidden = true;
      sessionStorage.removeItem('studio-asset-job');
    }
  }
}
function resumeAssetJob(project) {
  if (state.assetBusy) return;
  let previous;
  try { previous = JSON.parse(sessionStorage.getItem('studio-asset-job') || 'null'); } catch { sessionStorage.removeItem('studio-asset-job'); }
  const job = previous?.projectId === project.id ? previous : project.active_job?.kind === 'asset-upload' ? project.active_job : null;
  if (job?.id) trackAssetJob(job.id, project.id).catch(error => notify(error.message));
}
async function loadProject(id) {
  const project = await request(`/api/projects/${id}`);
  sessionStorage.setItem('studio-project', id);
  if (!project.media) {
    const job = project.active_job;
    if (job?.id) {
      state.sourceJob = job.id; $('import-button').disabled = true; $('video-file').disabled = true;
      state.jobs.set(job.id, job); jobDisplay(job);
      watchJob(job.id, async completed => { await loadProject(completed.project_id || id); });
    } else notify('This source is not ready yet. Open Activity to inspect its processing status.');
    return;
  }
  state.restoring = true; state.project = project; sessionStorage.setItem('studio-project', id);
  $('preview-empty').hidden = true; $('video-player').hidden = false;
  const previewURL = `/api/projects/${id}/preview`;
  if ($('video-player').getAttribute('src') !== previewURL) $('video-player').src = previewURL;
  $('source-name').textContent = project.name || 'Imported video';
  $('source-resolution').textContent = `${project.media.width} × ${project.media.height}`;
  $('project-name').value = project.name || 'Untitled clip';
  $('project-details').hidden = false; $('edit-empty').hidden = true; $('editor-form').hidden = false;
  $('expiry-info').textContent = project.expires_at ? `Temporary session expires ${dateLabel(project.expires_at)}. Download finished clips before then.` : 'This editing session and its video files are temporary.';
  $('playhead').textContent = `00:00 / ${timeLabel(project.media.duration)}`;
  renderAssets(project.assets || []); applyOptions(project.edits || {}); renderOutputs(project.clips || []); renderTranscript(project.transcript || []); renderDetections(project);
  state.restoring = false;
  resumeAssetJob(project);
  if (project.active_job?.kind === 'export' && state.exportJob !== project.active_job.id) {
    const job = project.active_job; state.exportJob = job.id; $('export-button').disabled = true;
    watchJob(job.id, async () => {
      if (state.project?.id !== id) return;
      const updated = await request(`/api/projects/${id}`); state.project.clips = updated.clips;
      renderOutputs(updated.clips || []); $('export-job-message').textContent = 'Clip ready. Download it below.';
    });
  }
}
function clearProject() {
  clearTimeout(state.saveTimer); state.project = null; state.segments = []; state.captions = [];
  sessionStorage.removeItem('studio-project'); $('video-player').pause(); $('video-player').removeAttribute('src'); $('video-player').load();
  $('video-player').hidden = true; $('preview-empty').hidden = false; $('project-details').hidden = true;
  $('editor-form').hidden = true; $('edit-empty').hidden = false; $('source-name').textContent = 'No video imported';
  $('source-resolution').textContent = 'NO SOURCE'; $('playhead').textContent = '00:00 / 00:00'; renderOutputs([]);
}
function renderOutputs(clips) {
  $('clip-count').textContent = `${clips.length} clip${clips.length === 1 ? '' : 's'}`;
  $('download-all').hidden = !clips.length;
  if (state.project) $('download-all').href = `/api/projects/${state.project.id}/download-all`;
  $('outputs').replaceChildren();
  if (!clips.length) {
    $('outputs').append(node('div', { class: 'output-empty' }, icon('video'), node('p', {}, 'Your exported clips will appear here.'),
      node('span', { class: 'fine muted' }, 'Nothing saved permanently. Download the clips you want to keep.'))); return;
  }
  for (const clip of clips) {
    const name = node('input', { value: clip.name || 'Untitled clip', maxlength: '100', 'aria-label': `Clip name ${clip.id}` });
    name.addEventListener('change', safely(async () => { await patch(`/api/clips/${clip.id}`, { name: name.value }); }));
    $('outputs').append(node('article', { class: 'clip-card panel' },
      node('video', { src: `/api/clips/${clip.id}/preview`, controls: '', preload: 'metadata', playsinline: '', 'aria-label': clip.name || 'Rendered clip preview' }),
      node('div', { class: 'clip-card-body' }, name, node('p', { class: 'clip-meta' }, `${seconds(clip.duration).toFixed(1)}s · MP4 · H.264`),
        node('a', { class: 'button quiet', href: `/api/clips/${clip.id}`, download: `${clip.name || 'clip'}.mp4` }, icon('download'), 'Download MP4'))));
  }
}
function renderTranscript(transcript) {
  $('transcript').replaceChildren();
  for (const line of transcript) {
    const jump = node('button', { type: 'button', 'aria-label': `Jump to ${timeLabel(line.start)}`, onclick: () => { $('video-player').currentTime = line.start; } }, timeLabel(line.start));
    const use = node('button', { class: 'text-button', type: 'button', 'aria-label': `Use transcript segment at ${timeLabel(line.start)}`,
      onclick: () => { state.segments.push({ start: line.start, end: line.end }); renderSegments(); queueSave(); } }, 'Use');
    $('transcript').append(node('div', { class: 'transcript-line' }, jump, node('p', {}, line.text), use));
  }
}
function jobDisplay(job) {
  const kind = job.id === state.assetJob ? 'asset' : job.kind === 'export' ? 'export' : ['import', 'upload', 'inspect'].includes(job.kind) ? 'source' : null;
  if (kind) {
    $(`${kind}-job`).hidden = false;
    $(`${kind}-job-message`).textContent = job.error || job.message || `${job.kind}: ${job.status}`;
    $(`${kind}-progress`).value = seconds(job.progress);
    $(`${kind}-cancel`).hidden = !['queued', 'running'].includes(job.status);
  }
  renderActivity();
}
function renderDetections(project) {
  $('detections').replaceChildren();
  const segments = project.detected_segments;
  if (!segments?.length) return;
  const label = project.detection_kind === 'non_silent' ? 'Non-silent sections' : 'Detected scenes';
  const selected = structuredClone(segments);
  $('detections').append(node('div', { class: 'suggestion-card' }, node('h4', {}, `${label} · ${selected.length}`),
    node('p', {}, selected.slice(0, 8).map(s => `${timeLabel(s.start)}–${timeLabel(s.end)}`).join(' / ') + (selected.length > 8 ? ' …' : '')),
    node('button', { class: 'button quiet small', type: 'button', onclick: () => {
      if (selected.length > 50) { notify('This source has more than 50 detected sections. Select a smaller set manually.'); return; }
      state.segments = structuredClone(selected); state.selectedSegment = 0; renderSegments(); queueSave();
    } }, 'Use detected sections')));
}
async function watchJob(id, onComplete) {
  let current;
  try {
    while (true) {
      current = await request(`/api/jobs/${id}`);
      state.jobs.set(id, current); jobDisplay(current);
      if (!['queued', 'running'].includes(current.status)) break;
      await new Promise(resolve => setTimeout(resolve, 650));
    }
    if (current.status === 'failed') throw new Error(current.error || current.message || 'Processing failed. Please try again.');
    if (current.status === 'completed') await onComplete(current);
  } catch (error) { notify(error.message); }
  finally {
    if (state.sourceJob === id) { state.sourceJob = null; $('import-button').disabled = false; $('video-file').disabled = false; }
    if (state.exportJob === id) { state.exportJob = null; $('export-button').disabled = false; }
    if (current?.kind === 'transcribe') $('transcribe').disabled = !state.capabilities.transcription;
  }
}
function renderActivity() {
  $('activity-list').replaceChildren();
  if (!state.jobs.size) $('activity-list').append(node('p', { class: 'muted fine' }, 'No processing jobs in this session.'));
  for (const job of [...state.jobs.values()].reverse()) {
    const row = node('div', { class: 'activity-item' }, node('p', {}, `${job.kind || 'Job'} · ${job.status}`),
      node('span', { class: 'fine muted' }, `${Math.round(seconds(job.progress) * 100)}%`),
      node('p', { class: 'fine muted' }, job.error || job.message || ''),
      node('progress', { max: '1', value: seconds(job.progress), 'aria-label': `${job.kind} progress` }));
    if (['queued', 'running'].includes(job.status)) row.append(node('button', { class: 'text-button', onclick: safely(async () => { await post(`/api/jobs/${job.id}/cancel`); }) }, 'Cancel'));
    $('activity-list').append(row);
  }
}
async function startImport(url) {
  if (state.sourceJob) { notify('A video is already being imported. Wait for it to finish or cancel it first.'); return; }
  $('import-button').disabled = true; $('video-file').disabled = true;
  try {
    const result = await post('/api/projects/import', { url }); state.sourceJob = result.job_id;
    watchJob(result.job_id, async job => { await loadProject(job.project_id); });
  } catch (error) { $('import-button').disabled = false; $('video-file').disabled = false; throw error; }
}
async function loadHistory() {
  const history = await request('/api/history'); $('history-list').replaceChildren();
  if (!history.length) $('history-list').append(node('p', { class: 'muted' }, 'No source URLs yet. Successfully imported links will appear here.'));
  for (const entry of history) {
    const url = typeof entry === 'string' ? entry : entry.url;
    $('history-list').append(node('div', { class: 'history-row' },
      node('div', {}, node('p', { class: 'history-url' }, url), node('time', {}, dateLabel(entry.used_at))),
      node('button', { class: 'button quiet small', onclick: safely(async () => { $('video-url').value = url; showView('workspace'); await startImport(url); }) }, 'Import again')));
  }
}
async function loadFeatures() {
  state.features = await request('/api/features');
  if (!Array.isArray(state.features)) state.features = state.features.features || [];
  renderFeatures();
}
function renderFeatures() {
  const search = $('feature-search').value.toLowerCase().trim();
  const features = state.features.filter(f => `${f.id} ${f.name} ${f.group}`.toLowerCase().includes(search));
  $('feature-summary').textContent = `${state.features.filter(f => f.status === 'implemented').length} implemented · ${state.features.length} requested · ${features.length} shown. Partial or pending work is not counted as complete.`;
  $('feature-list').replaceChildren();
  for (const feature of features) {
    $('feature-list').append(node('article', { class: 'feature-row' },
      node('div', { class: 'feature-title' }, node('h3', {}, `${feature.id}. ${feature.name}`), node('span', { class: `feature-status ${feature.status === 'implemented' ? 'implemented' : ''}` }, String(feature.status).replaceAll('-', ' '))),
      node('p', {}, typeof feature.group === 'string' ? feature.group : ''),
      node('p', {}, feature.notes || ''),
      feature.dependency ? node('p', {}, `Requires: ${Array.isArray(feature.dependency) ? feature.dependency.join(', ') : feature.dependency}`) : null));
  }
  if (!features.length) $('feature-list').append(node('p', { class: 'muted' }, 'No features match your search.'));
}

$('login-form').addEventListener('submit', async (event) => {
  event.preventDefault(); const button = event.submitter; setBusy(button, true, 'Opening…'); $('login-error').textContent = '';
  try { await post('/api/session', { password: $('password').value }); $('password').value = ''; await enterStudio(); }
  catch (error) { $('login-error').textContent = error.message; }
  finally { setBusy(button, false, 'Open studio'); }
});
$('signout').addEventListener('click', safely(async () => { await request('/api/session', { method: 'DELETE' }); clearProject(); showLogin(); }));
$('settings-signout').addEventListener('click', () => $('signout').click());
document.querySelectorAll('[data-view]').forEach(button => button.addEventListener('click', () => showView(button.dataset.view)));
document.querySelector('.brand').addEventListener('click', event => { event.preventDefault(); showView('workspace'); });
$('notice-close').addEventListener('click', () => { $('notice').hidden = true; });
$('jobs-toggle').addEventListener('click', () => { $('activity-panel').hidden = !$('activity-panel').hidden; renderActivity(); });
$('activity-close').addEventListener('click', () => { $('activity-panel').hidden = true; });
$('appearance').addEventListener('change', saveTheme); $('accent').addEventListener('input', saveTheme);
$('reset-theme').addEventListener('click', () => { localStorage.removeItem('studio-theme'); applyTheme(); });
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
$('import-form').addEventListener('submit', safely(async (event) => { event.preventDefault(); await startImport($('video-url').value.trim()); }));
$('video-file').addEventListener('change', safely(async () => {
  const file = $('video-file').files[0]; if (!file) return;
  if (state.sourceJob) { notify('Wait for the current import or cancel it first.'); return; }
  if (file.size > 1024 ** 3) { notify('This file exceeds the 1 GB upload limit. Choose a smaller file.'); $('video-file').value = ''; return; }
  $('import-button').disabled = true; $('video-file').disabled = true;
  const data = new FormData(); data.append('file', file);
  $('source-job').hidden = false; $('source-job-message').textContent = 'Uploading video…'; $('source-progress').removeAttribute('value'); $('source-cancel').hidden = true;
  try {
    const result = await request('/api/projects/upload', { method: 'POST', body: data }); state.sourceJob = result.job_id;
    watchJob(result.job_id, async job => { await loadProject(job.project_id); });
  } catch (error) { $('import-button').disabled = false; $('video-file').disabled = false; $('source-job').hidden = true; throw error; }
  finally { $('video-file').value = ''; }
}));
for (const kind of ['source', 'export']) $(`${kind}-cancel`).addEventListener('click', safely(async () => {
  const id = state[`${kind}Job`]; if (id) await post(`/api/jobs/${id}/cancel`);
}));
$('video-player').addEventListener('timeupdate', () => { $('playhead').textContent = `${timeLabel($('video-player').currentTime)} / ${timeLabel(state.project?.media.duration || 0)}`; });
$('video-player').addEventListener('error', () => {
  if ($('video-player').getAttribute('src')) notify('Your browser could not preview this video. Rendering may still work; an H.264 MP4 source gives the broadest preview compatibility.');
});
$('project-name').addEventListener('input', queueSave);
$('remove-project').addEventListener('click', safely(async () => {
  if (!state.project) return;
  const id = state.project.id; await request(`/api/projects/${id}`, { method: 'DELETE' }); clearProject();
}));
$('add-segment').addEventListener('click', () => {
  const start = Math.min($('video-player').currentTime, Math.max(0, state.project.media.duration - .1));
  state.segments.push({ start: Math.round(start * 10) / 10, end: Math.min(state.project.media.duration, start + 15) });
  state.selectedSegment = state.segments.length - 1; renderSegments(); queueSave();
});
for (const [id, key] of [['mark-in', 'start'], ['mark-out', 'end']]) $(id).addEventListener('click', () => {
  const segment = state.segments[state.selectedSegment] || state.segments[0]; if (!segment) return;
  segment[key] = Math.round($('video-player').currentTime * 10) / 10; renderSegments(); queueSave();
});
$('add-caption').addEventListener('click', () => { state.captions.push({ start: 0, end: Math.min(3, duration()), text: '' }); renderCaptions(); queueSave(); });
$('volume').addEventListener('input', () => { $('volume-value').value = `${Math.round(Number($('volume').value) * 100)}%`; });
for (const id of ['aspect', 'resolution', 'fit', 'caption-style', 'overlay-text', 'mute', 'enhance-audio', 'volume', 'speed']) $(id).addEventListener('input', queueSave);
for (const id of ['transition', 'caption-color', 'caption-background', 'text-color', 'logo-asset', 'music-asset', 'font-asset', 'logo-position', 'music-volume']) $(id).addEventListener('input', queueSave);
$('music-volume').addEventListener('input', () => { $('music-volume-value').value = `${Math.round(Number($('music-volume').value) * 100)}%`; });
$('speed').addEventListener('input', updateDuration);
$('editor-form').addEventListener('submit', safely(async (event) => {
  event.preventDefault(); if (!state.project || state.exportJob) return;
  if (state.segments.some(s => !Number.isFinite(s.start) || !Number.isFinite(s.end) || s.start < 0 || s.end <= s.start || s.end > state.project.media.duration + .01)) { notify('Each segment needs a start before its end, within the source duration.'); return; }
  if (state.captions.some(c => c.start < 0 || c.end <= c.start || c.end > duration() + .01 || !c.text.trim())) { notify('Each caption needs text and valid start/end times within the exported clip.'); return; }
  $('export-button').disabled = true; $('notice').hidden = true;
  try {
    const projectId = state.project.id;
    const result = await post(`/api/projects/${projectId}/export`, collectOptions()); state.exportJob = result.job_id;
    watchJob(result.job_id, async () => {
      if (state.project?.id !== projectId) return;
      const updated = await request(`/api/projects/${projectId}`); state.project.clips = updated.clips;
      renderOutputs(updated.clips || []); $('export-job-message').textContent = 'Clip ready. Download it below.';
    });
  } catch (error) { $('export-button').disabled = false; throw error; }
}));
$('transcribe').addEventListener('click', safely(async () => {
  $('transcribe').disabled = true;
  try {
    const result = await post(`/api/projects/${state.project.id}/transcribe`);
    watchJob(result.job_id, async () => { const p = await request(`/api/projects/${state.project.id}`); state.project.transcript = p.transcript; renderTranscript(p.transcript || []); $('ai-status').textContent = 'Transcript ready. Review its text and select moments to use.'; });
  } catch (error) { $('transcribe').disabled = false; throw error; }
}));
$('suggest').addEventListener('click', safely(async () => {
  $('suggest').disabled = true;
  try {
    const result = await post(`/api/projects/${state.project.id}/suggest`, { duration: 30, keywords: '' });
    const suggestions = Array.isArray(result) ? result : result.suggestions || [];
    $('suggestions').replaceChildren();
    if (!suggestions.length) $('suggestions').append(node('p', { class: 'fine muted' }, 'No suggestions found. Transcribe the source first or select a segment manually.'));
    for (const suggestion of suggestions) {
      $('suggestions').append(node('div', { class: 'suggestion-card' }, node('h4', {}, suggestion.title || 'Suggested moment'),
        node('p', {}, `${timeLabel(suggestion.start)}–${timeLabel(suggestion.end)} · ${suggestion.reason || suggestion.text || 'Review this selection before exporting.'}`),
        node('button', { type: 'button', class: 'button quiet small', onclick: () => { state.segments = [{ start: suggestion.start, end: suggestion.end }]; renderSegments(); queueSave(); } }, 'Use this selection')));
    }
  } finally { $('suggest').disabled = !state.capabilities.transcription; }
}));
for (const endpoint of ['detect-scenes', 'remove-silence']) $(endpoint).addEventListener('click', safely(async () => {
  const projectId = state.project?.id; if (!projectId) return;
  $('detect-scenes').disabled = true; $('remove-silence').disabled = true;
  $('detection-status').textContent = endpoint === 'detect-scenes' ? 'Looking for scene changes…' : 'Looking for non-silent sections…';
  try {
    const result = await post(`/api/projects/${projectId}/${endpoint}`);
    await watchJob(result.job_id, async () => {
      if (state.project?.id !== projectId) return;
      const updated = await request(`/api/projects/${projectId}`); renderDetections(updated);
      $('detection-status').textContent = updated.detected_segments?.length ? 'Review the detected sections before applying them.' : 'No matching sections found.';
    });
  } catch (error) { $('detection-status').textContent = 'Detection could not be completed.'; throw error; }
  finally { $('detect-scenes').disabled = false; $('remove-silence').disabled = false; }
}));
$('clear-history').addEventListener('click', safely(async () => { await request('/api/history', { method: 'DELETE' }); await loadHistory(); }));
for (const kind of ['logo', 'music', 'font']) $(`${kind}-file`).addEventListener('change', safely(async () => {
  const input = $(`${kind}-file`); const file = input.files[0]; const projectId = state.project?.id;
  if (!file || !projectId) return;
  if (state.assetBusy) { input.value = ''; notify('Wait for the current asset to finish or cancel it first.'); return; }
  const limit = (kind === 'font' ? 5 : 25) * 1024 ** 2;
  if (file.size > limit) { input.value = ''; notify(`${kind === 'font' ? 'Fonts' : 'Images and music'} must be no larger than ${limit / 1024 ** 2} MB.`); return; }
  setAssetBusy(true); state.assetUpload = new AbortController();
  $('asset-job').hidden = false; $('asset-job-message').textContent = `Uploading ${file.name}…`; $('asset-progress').removeAttribute('value'); $('asset-cancel').hidden = false;
  try {
    const data = new FormData(); data.append('file', file);
    const result = await request(`/api/projects/${projectId}/assets/${kind}`, { method: 'POST', body: data, signal: state.assetUpload.signal });
    state.assetUpload = null;
    await trackAssetJob(result.job_id, projectId, file.name);
  } catch (error) { if (error.name === 'AbortError') $('asset-job-message').textContent = 'Asset upload cancelled.'; else throw error; }
  finally {
    setAssetBusy(false); state.assetJob = null; state.assetUpload = null; input.value = ''; $('asset-cancel').hidden = true;
  }
}));
$('asset-cancel').addEventListener('click', safely(async () => {
  if (state.assetUpload) state.assetUpload.abort();
  if (state.assetJob) await post(`/api/jobs/${state.assetJob}/cancel`);
}));
$('feature-search').addEventListener('input', renderFeatures);
applyTheme();
request('/api/session').then(session => session.authenticated ? enterStudio() : showLogin()).catch(error => { showLogin(); $('login-error').textContent = error.message; });
