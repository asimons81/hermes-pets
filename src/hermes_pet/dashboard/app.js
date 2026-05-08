const token = new URLSearchParams(window.location.search).get('token') || readCookie('hermes_pet_dashboard_token');
const state = { snapshot: null, prefs: null, voice: null };

function readCookie(name) {
  return document.cookie
    .split(';')
    .map((part) => part.trim())
    .find((part) => part.startsWith(name + '='))
    ?.split('=')
    .slice(1)
    .join('=') || '';
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-Hermes-Pet-Token': token,
      ...(options.headers || {}),
    },
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.error || response.statusText);
  return payload;
}

function $(id) {
  return document.getElementById(id);
}

function showAlert(message, tone = 'info') {
  const el = $('alert');
  el.textContent = message;
  el.dataset.tone = tone;
  el.classList.remove('hidden');
  window.clearTimeout(showAlert.timer);
  showAlert.timer = window.setTimeout(() => el.classList.add('hidden'), 4800);
}

function empty(text) {
  return `<div class="empty">${escapeHtml(text)}</div>`;
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, (char) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  })[char]);
}

function setView(name) {
  document.querySelectorAll('.nav-item').forEach((button) => {
    button.classList.toggle('active', button.dataset.view === name);
  });
  document.querySelectorAll('.view').forEach((view) => {
    view.classList.toggle('active', view.id === name);
  });
  $('viewTitle').textContent = {
    overview: 'Overview',
    custom: 'Custom Pets',
    prefs: 'Preferences',
    voice: 'Voice Preview',
    achievements: 'Achievements',
  }[name] || 'Overview';
}

function renderSnapshot(snapshot) {
  state.snapshot = snapshot;
  $('stateDir').textContent = snapshot.state_dir || '';
  const dot = $('bridgeDot');
  dot.classList.toggle('ok', !!snapshot.bridge?.available);
  $('bridgeText').textContent = snapshot.bridge?.available ? 'Bridge online' : 'Bridge offline';
  renderPet(snapshot);
  renderJobs(snapshot);
  renderEvents(snapshot);
  renderAchievements(snapshot);
  renderCustomPets(snapshot);
  hydratePrefs(snapshot.prefs || {});
  hydrateVoice(snapshot.voice || {});
}

function renderPet(snapshot) {
  const pet = snapshot.pet;
  const custom = snapshot.custom_pet;
  if (!pet) {
    $('petCard').innerHTML = empty('No pet has hatched in this state directory yet. Hatch from the CLI, then refresh this console.');
    return;
  }
  $('petCard').innerHTML = `
    <div class="sprite-tile"><img alt="${escapeHtml(pet.species || 'pet')} sprite" src="/overlay/assets/sprites/${encodeURIComponent(pet.species || 'cat')}.png"></div>
    <div>
      <h2 class="pet-name">${escapeHtml(pet.name)} <span class="muted">Lv.${escapeHtml(pet.level)}</span></h2>
      <div class="muted">${escapeHtml(pet.species)} / ${escapeHtml(pet.variant)} / ${escapeHtml(custom?.name || 'built-in sprite')}</div>
      <div class="metric-row pet-stats">
        <div class="metric"><strong>${escapeHtml(pet.xp)}</strong><span>XP</span></div>
        <div class="metric"><strong>${escapeHtml(pet.xp_next)}</strong><span>next level</span></div>
        <div class="metric"><strong>${escapeHtml(pet.total_interactions || 0)}</strong><span>interactions</span></div>
        <div class="metric"><strong>${escapeHtml((pet.milestones || []).length)}</strong><span>milestones</span></div>
      </div>
    </div>
  `;
}

function renderJobs(snapshot) {
  const summary = snapshot.job_summary || {};
  $('jobSummary').innerHTML = ['total', 'succeeded', 'failed', 'retryable_failures'].map((key) => `
    <div class="metric"><strong>${escapeHtml(summary[key] || 0)}</strong><span>${escapeHtml(key.replaceAll('_', ' '))}</span></div>
  `).join('');
  const jobs = snapshot.jobs || [];
  $('jobsList').innerHTML = jobs.length ? jobs.map((job) => `
    <div class="activity">
      <strong>${escapeHtml(job.name || job.id || 'job')}</strong>
      <small>${escapeHtml(job.status || 'unknown')} / exit ${escapeHtml(job.exit_code ?? '-')} / ${escapeHtml(job.duration_text || '')}</small>
    </div>
  `).join('') : empty('No wrapped jobs recorded in this state directory.');
}

function renderEvents(snapshot) {
  const events = snapshot.events || [];
  $('eventsList').innerHTML = events.length ? events.map((event) => `
    <div class="activity">
      <strong>${escapeHtml(event.text || event.type)}</strong>
      <small>${escapeHtml(event.type)} ${event.sender ? '/ ' + escapeHtml(event.sender) : ''}</small>
    </div>
  `).join('') : empty('No local events recorded yet. The test event button can verify overlay delivery.');
}

function renderAchievements(snapshot) {
  const achievements = snapshot.achievements || { items: [] };
  $('achievementCount').textContent = `${achievements.unlocked_count || 0}/${achievements.total_count || 0} unlocked`;
  const preview = achievements.items.slice(0, 3);
  $('achievementPreview').innerHTML = preview.length ? preview.map(achievementCard).join('') : empty('Achievement ledger is ready.');
  $('achievementGrid').innerHTML = achievements.items.length ? achievements.items.map(achievementCard).join('') : empty('Achievement definitions are available once local state appears.');
}

function achievementCard(item) {
  return `
    <div class="achievement ${item.unlocked ? '' : 'locked'}">
      <strong>${item.unlocked ? 'Unlocked' : 'Locked'} / ${escapeHtml(item.title)}</strong>
      <small>${escapeHtml(item.description)}${item.unlocked_at ? ' / ' + escapeHtml(item.unlocked_at) : ''}</small>
    </div>
  `;
}

function renderCustomPets(snapshot) {
  const pets = snapshot.custom_pets || [];
  $('customDir').textContent = snapshot.state_dir ? `${snapshot.state_dir}/custom-pets` : '';
  $('customDir').title = $('customDir').textContent;
  $('customPetsList').innerHTML = pets.length ? pets.map((pet) => `
    <div class="pet-row">
      <div>
        <strong>${pet.current ? 'Current / ' : ''}${escapeHtml(pet.name)}</strong>
        <small>${pet.valid ? petSummary(pet) : `invalid / ${escapeHtml(pet.error || 'unknown error')}`}</small>
      </div>
      <div class="row-actions">
        <button class="tiny" type="button" data-use="${escapeHtml(pet.name)}" ${pet.valid ? '' : 'disabled'}>Use</button>
        <button class="tiny" type="button" data-remove="${escapeHtml(pet.name)}">Remove</button>
      </div>
    </div>
  `).join('') : empty('No custom pets installed. Import a validated local package by path.');
}

function petSummary(pet) {
  const frames = (pet.state_summary || []).map((item) => `${item.name}:${item.frame_count}`).join(', ');
  const missing = (pet.missing_optional_states || []).slice(0, 3).join(', ');
  return escapeHtml(`${frames || (pet.states || []).join(', ') || 'valid'}${missing ? ' / missing ' + missing : ''}`);
}

function hydratePrefs(prefs) {
  state.prefs = prefs;
  renderSegmented('profileControl', ['normal', 'focus', 'pairing', 'demo', 'silent'], prefs.notification_profile, (value) => {
    state.prefs.notification_profile = value;
    savePrefs();
  });
  renderSegmented('quietControl', ['off', 'important', 'silent'], prefs.quiet_mode, (value) => {
    state.prefs.quiet_mode = value;
    savePrefs();
  });
  $('trayToggle').checked = !!prefs.show_tray_on_urgent;
  $('idleToggle').checked = !!prefs.show_idle_bubbles;
  $('throttleInput').value = prefs.bubble_throttle_seconds ?? 2.5;
}

function renderSegmented(id, values, active, onClick) {
  $(id).innerHTML = values.map((value) => `
    <button type="button" class="${value === active ? 'active' : ''}" data-value="${escapeHtml(value)}">${escapeHtml(value)}</button>
  `).join('');
  $(id).querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => onClick(button.dataset.value));
  });
}

function hydrateVoice(voice) {
  state.voice = voice;
  $('voiceEnabled').checked = !!voice.enabled;
  $('voiceCommand').value = voice.command || '';
}

async function refresh() {
  try {
    renderSnapshot(await api('/api/state'));
  } catch (error) {
    showAlert(error.message, 'error');
  }
}

async function savePrefs() {
  try {
    const body = {
      ...(state.prefs || {}),
      show_tray_on_urgent: $('trayToggle').checked,
      show_idle_bubbles: $('idleToggle').checked,
      bubble_throttle_seconds: Number($('throttleInput').value || 0),
    };
    const result = await api('/api/prefs', { method: 'POST', body: JSON.stringify(body) });
    hydratePrefs(result.prefs);
    showAlert(result.bridge_notified ? 'Preferences saved and sent to the overlay.' : 'Preferences saved. Bridge is offline.');
    refresh();
  } catch (error) {
    showAlert(error.message, 'error');
  }
}

async function saveVoice() {
  try {
    const result = await api('/api/voice', {
      method: 'POST',
      body: JSON.stringify({ enabled: $('voiceEnabled').checked, command: $('voiceCommand').value }),
    });
    hydrateVoice(result.status);
    showAlert('Voice preview saved.');
  } catch (error) {
    showAlert(error.message, 'error');
  }
}

document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
$('refreshBtn').addEventListener('click', refresh);
$('savePrefsBtn').addEventListener('click', savePrefs);
$('saveVoiceBtn').addEventListener('click', saveVoice);
$('importBtn').addEventListener('click', async () => {
  try {
    await api('/api/custom-pets/import', {
      method: 'POST',
      body: JSON.stringify({ path: $('importPath').value, name: $('importName').value }),
    });
    $('importPath').value = '';
    $('importName').value = '';
    showAlert('Custom pet imported.');
    refresh();
  } catch (error) {
    showAlert(error.message, 'error');
  }
});
$('customPetsList').addEventListener('click', async (event) => {
  const use = event.target?.dataset?.use;
  const remove = event.target?.dataset?.remove;
  try {
    if (use) await api('/api/custom-pets/use', { method: 'POST', body: JSON.stringify({ name: use }) });
    if (remove) await api(`/api/custom-pets/${encodeURIComponent(remove)}`, { method: 'DELETE' });
    showAlert(use ? 'Custom pet selected.' : 'Custom pet removed.');
    refresh();
  } catch (error) {
    showAlert(error.message, 'error');
  }
});
$('testEventBtn').addEventListener('click', async () => {
  try {
    const result = await api('/api/events/test', { method: 'POST', body: '{}' });
    showAlert(result.bridge_notified ? 'Test event sent to overlay.' : 'Test event saved; bridge is offline.');
    refresh();
  } catch (error) {
    showAlert(error.message, 'error');
  }
});
$('testVoiceBtn').addEventListener('click', async () => {
  try {
    const result = await api('/api/voice/test', {
      method: 'POST',
      body: JSON.stringify({ text: $('voiceText').value }),
    });
    $('voiceResult').textContent = JSON.stringify(result.result, null, 2);
    showAlert(result.result.ok ? 'Voice test completed.' : 'Voice test reported a problem.');
  } catch (error) {
    showAlert(error.message, 'error');
  }
});

setView(new URLSearchParams(window.location.search).get('view') || 'overview');
refresh();
