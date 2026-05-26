const token = new URLSearchParams(window.location.search).get('token') || readCookie('hermes_pet_dashboard_token');
const state = { snapshot: null, prefs: null, voice: null, species: [], speciesCurrent: null, speciesLoaded: false };

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
  if (!response.ok) {
    const error = new Error(payload.error || response.statusText);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function $(id) {
  return document.getElementById(id);
}

function showAlert(message, tone = 'info') {
  const el = $('alert');
  el.textContent = message;
  el.dataset.tone = tone;
  el.setAttribute('role', tone === 'error' ? 'alert' : 'status');
  el.classList.remove('hidden');
  window.clearTimeout(showAlert.timer);
  if (tone === 'error') return;
  showAlert.timer = window.setTimeout(() => el.classList.add('hidden'), 4800);
}

function empty(text) {
  return `<div class="empty">${escapeHtml(text)}</div>`;
}

function stateCard(tone, title, body) {
  return `
    <div class="state-card" data-tone="${escapeHtml(tone)}">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(body)}</span>
    </div>
  `;
}

function renderLoadingState() {
  $('petCard').className = 'pet-card pet-empty-card';
  $('petCard').innerHTML = stateCard('loading', 'Loading local pet state', 'Reading the token-protected dashboard snapshot from this machine.');
  $('speciesCount').textContent = '';
  $('speciesList').innerHTML = stateCard('loading', 'Loading built-in species', 'Reading the local pet catalog.');
  $('jobSummary').innerHTML = '';
  $('jobsList').innerHTML = stateCard('loading', 'Loading recent jobs', 'Wrapped command history will appear here when the state snapshot arrives.');
  $('eventsList').innerHTML = stateCard('loading', 'Loading event log', 'Recent local companion signals will appear here shortly.');
  $('achievementPreview').innerHTML = stateCard('loading', 'Loading achievements', 'Checking the compact local unlock ledger.');
  $('achievementProgress').innerHTML = achievementProgressHeader(0, 0, 0);
  $('achievementGrid').innerHTML = stateCard('loading', 'Loading achievement ledger', 'Badge groups will appear when the state snapshot arrives.');
}

function renderApiError(error) {
  const auth = error.status === 401;
  const title = auth ? 'Dashboard token required' : 'Dashboard API unavailable';
  const body = auth
    ? 'Open the private token URL printed by hermes-pet dashboard, or refresh this page from that same local session.'
    : 'The local server did not return a usable state snapshot. Check the dashboard process, then refresh.';
  $('petCard').className = 'pet-card pet-empty-card';
  $('petCard').innerHTML = stateCard('error', title, body);
  $('speciesCount').textContent = '';
  $('speciesList').innerHTML = stateCard('error', 'Species catalog paused', body);
  $('jobSummary').innerHTML = '';
  $('jobsList').innerHTML = stateCard('error', 'Signal feed paused', body);
  $('eventsList').innerHTML = stateCard('error', 'Event log paused', body);
  $('achievementPreview').innerHTML = stateCard('error', 'Achievement ledger paused', body);
  $('achievementProgress').innerHTML = achievementProgressHeader(0, 0, 0);
  $('achievementGrid').innerHTML = stateCard('error', 'Achievement ledger paused', body);
}

function formatTimestamp(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function formatDate(value) {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' });
}

function jobTone(job) {
  const status = String(job.status || '').toLowerCase();
  if (status === 'succeeded' || job.exit_code === 0) return 'success';
  if (status === 'failed' || (job.exit_code !== undefined && job.exit_code !== null && job.exit_code !== 0)) return 'danger';
  return 'neutral';
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
    const active = button.dataset.view === name;
    button.classList.toggle('active', active);
    if (active) {
      button.setAttribute('aria-current', 'page');
      const indicator = $('nav-indicator');
      if (indicator) {
        indicator.style.transform = `translateY(${button.offsetTop}px)`;
        indicator.style.height = `${button.offsetHeight}px`;
      }
    } else {
      button.removeAttribute('aria-current');
    }
  });
  document.querySelectorAll('.view').forEach((view) => {
    view.classList.toggle('active', view.id === name);
  });
  const viewMeta = {
    overview: ['Overview', 'Your active pet, recent signals, and local console health.'],
    change: ['Change Pet', 'Choose a built-in companion or hatch a fresh random pet.'],
    custom: ['Custom Pets', 'Installed custom pet packages and typed-path package import.'],
    prefs: ['Preferences', 'Notification posture, quiet mode, and local bubble behavior.'],
    voice: ['Voice Preview', 'Opt-in adapter plumbing for one explicit local test.'],
    achievements: ['Achievements', 'A compact local ledger of foundational unlocks.'],
  };
  const [title, subtitle] = viewMeta[name] || viewMeta.overview;
  $('viewTitle').textContent = title;
  $('viewSubtitle').textContent = subtitle;
}

function customPetSpriteSrc(custom, preferredState = 'idle') {
  if (!custom?.name || !custom?.manifest?.states) return '';
  const states = custom.manifest.states;
  const stateName = states[preferredState] ? preferredState : (states.idle ? 'idle' : Object.keys(states)[0]);
  const frames = states[stateName]?.frames || [];
  const frame = frames[0];
  if (!stateName || !frame) return '';
  return `/api/custom-pets/${encodeURIComponent(custom.name)}/sprite/${encodeURIComponent(stateName)}/${encodeURIComponent(frame)}`;
}

function renderSnapshot(snapshot) {
  state.snapshot = snapshot;
  document.body.dataset.stale = 'false';
  $('stateDir').textContent = snapshot.state_dir || '';
  $('lastRefresh').textContent = snapshot.generated_at ? `Snapshot refreshed ${formatTimestamp(snapshot.generated_at)}` : 'Snapshot refreshed.';
  const dot = $('bridgeDot');
  dot.classList.toggle('ok', !!snapshot.bridge?.available);
  $('bridgeText').textContent = snapshot.bridge?.available ? 'Bridge online' : 'Bridge offline - local state still available';
  renderPet(snapshot);
  renderSpecies();
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
  const card = $('petCard');
  if (!pet && !custom) {
    card.className = 'pet-card pet-empty-card';
    card.innerHTML = `
      <div class="pet-empty">
        <strong>No active companion yet</strong>
        <span>No built-in or custom pet is active. Choose a built-in species from Change Pet, hatch a random pet, or select an installed custom pet.</span>
      </div>
    `;
    return;
  }
  const xp = Number(pet?.xp || 0);
  const xpNext = Number(pet?.xp_next || 0);
  const progress = xpNext > 0 ? Math.max(0, Math.min(100, Math.round((xp / xpNext) * 100))) : 0;
  const species = pet?.species || 'custom';
  const spriteSrc = custom?.name ? customPetSpriteSrc(custom, 'idle') : `/overlay/assets/sprites/${encodeURIComponent(species || 'cat')}.png`;
  const spriteAlt = custom?.name ? `${custom.name} custom pet sprite` : `${species} sprite`;
  const displayName = custom?.name || pet?.name || 'Custom pet';
  const levelLabel = pet?.level ? `Lv.${pet.level}` : 'Custom';
  const visualState = custom?.name ? 'Active custom pet' : 'Built-in visual active';
  const customLabel = custom?.name ? `Active custom pet package: ${custom.name}` : 'Built-in pet';
  const baseVariant = pet ? [pet.species, pet.variant, pet.hat && pet.hat !== 'none' ? `${pet.hat} hat` : ''].filter(Boolean).join(' / ') : 'custom pet only';
  const variantLabel = custom?.name && pet?.species === 'custom'
    ? `Custom pet package: ${custom.name}`
    : custom?.name && pet
      ? `Custom pet package: ${custom.name} / previous pet state: ${pet.name}`
      : baseVariant;
  card.className = 'pet-card pet-hero-card';
  card.innerHTML = `
    <div class="sprite-stage" aria-label="${escapeHtml(displayName)} sprite">
      <img alt="${escapeHtml(spriteAlt)}" src="${escapeHtml(spriteSrc)}">
    </div>
    <div class="pet-hero-copy">
      <p class="pet-kicker">${escapeHtml(visualState)}</p>
      <h2 class="pet-name">${escapeHtml(displayName)} <span>${escapeHtml(levelLabel)}</span></h2>
      <div class="pet-meta">
        <span>${escapeHtml(variantLabel || 'local pet')}</span>
        <span>${escapeHtml(customLabel)}</span>
      </div>
      <div class="xp-block">
        <div class="xp-row">
          <span>${escapeHtml(xp)} XP</span>
          <span>${escapeHtml(xpNext)} next level</span>
        </div>
        <div class="xp-progress" role="progressbar" aria-label="XP progress toward next level" aria-valuemin="0" aria-valuemax="${escapeHtml(xpNext)}" aria-valuenow="${escapeHtml(Math.min(xp, xpNext))}">
          <span style="width:${escapeHtml(progress)}%"></span>
        </div>
      </div>
      <div class="pet-stat-grid">
        <div><strong>${escapeHtml(pet?.total_interactions || 0)}</strong><span>Interactions</span></div>
        <div><strong>${escapeHtml((pet?.milestones || []).length)}</strong><span>Milestones</span></div>
        <div><strong>${escapeHtml(custom?.name ? 'custom' : (pet?.variant || 'normal'))}</strong><span>Visual</span></div>
      </div>
    </div>
  `;
}

function renderSpecies() {
  const list = $('speciesList');
  const species = state.species || [];
  const currentName = (state.snapshot?.pet?.species || state.speciesCurrent?.species || state.speciesCurrent?.name || '').toLowerCase();
  $('speciesCount').textContent = species.length ? `${species.length} species` : '';
  if (!state.speciesLoaded) {
    list.innerHTML = stateCard('loading', 'Loading built-in species', 'Reading the local pet catalog.');
    return;
  }
  if (!species.length) {
    list.innerHTML = empty('No built-in species were returned by the local catalog.');
    return;
  }
  list.innerHTML = species.map((item) => {
    const name = item.name || 'unknown';
    const isCurrent = currentName && String(name).toLowerCase() === currentName;
    return `
      <article class="species-option ${isCurrent ? 'current' : ''}">
        <div class="species-main">
          <strong>${escapeHtml(name)}${isCurrent ? ' / Current' : ''}</strong>
          <small>${escapeHtml(item.rarity || 'standard')} rarity / ${escapeHtml(item.personality || 'companion')} personality</small>
          <span>Favorite tool: ${escapeHtml(item.favorite_tool || 'any local command')}</span>
        </div>
        <button class="${isCurrent ? 'secondary' : 'primary'}" type="button" data-adopt-species="${escapeHtml(name)}">
          ${isCurrent ? 'Restart' : 'Adopt'}
        </button>
      </article>
    `;
  }).join('');
}

async function loadSpecies() {
  try {
    const result = await api('/api/species');
    state.species = result.species || [];
    state.speciesCurrent = result.current || null;
    state.speciesLoaded = true;
    renderSpecies();
  } catch (error) {
    state.speciesLoaded = true;
    $('speciesCount').textContent = '';
    $('speciesList').innerHTML = stateCard('error', 'Species catalog unavailable', error.message);
  }
}

function renderJobs(snapshot) {
  const summary = snapshot.job_summary || {};
  const metrics = [
    ['total', 'Total', 'Recorded jobs', 'neutral'],
    ['succeeded', 'Succeeded', 'Completed cleanly', 'success'],
    ['failed', 'Failed', 'Needs review', 'danger'],
    ['retryable_failures', 'Retryable', 'Safe to rerun', 'warning'],
  ];
  $('jobSummary').innerHTML = metrics.map(([key, label, note, tone]) => `
    <div class="status-metric" data-tone="${escapeHtml(tone)}">
      <span class="status-metric-label">${escapeHtml(label)}</span>
      <strong>${escapeHtml(summary[key] || 0)}</strong>
      <span class="status-metric-note">${escapeHtml(note)}</span>
    </div>
  `).join('');
  const jobs = snapshot.jobs || [];
  $('jobsList').innerHTML = jobs.length ? jobs.map((job) => {
    const tone = jobTone(job);
    const timestamp = formatTimestamp(job.finished_at || job.started_at || job.created_at);
    const retryableFailure = tone === 'danger' && job.retryable === true;
    return `
      <div class="job-feed-row" data-tone="${escapeHtml(tone)}">
        <div class="job-feed-main">
          <strong>${escapeHtml(job.name || job.id || 'job')}</strong>
          <div class="job-feed-meta">
            <span>Status: ${escapeHtml(job.status || 'unknown')}</span>
            <span>Exit: ${escapeHtml(job.exit_code ?? '-')}</span>
            <span>Duration: ${escapeHtml(job.duration_text || '-')}</span>
          </div>
        </div>
        <div class="job-feed-side">
          ${timestamp ? `<span class="feed-time">${escapeHtml(timestamp)}</span>` : ''}
          ${retryableFailure ? '<span class="retry-chip">Retryable</span>' : ''}
        </div>
      </div>
    `;
  }).join('') : empty('No wrapped jobs recorded yet. Run commands with hermes-pet wrap to build a local signal history.');
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
  const items = sortAchievements(achievements.items || []);
  const unlockedCount = Number(achievements.unlocked_count ?? items.filter((item) => item.unlocked).length);
  const totalCount = Number(achievements.total_count ?? items.length);
  const progress = totalCount > 0 ? Math.round((unlockedCount / totalCount) * 100) : 0;
  $('achievementCount').textContent = `${unlockedCount}/${totalCount} unlocked`;
  $('achievementProgress').innerHTML = achievementProgressHeader(unlockedCount, totalCount, progress);
  const preview = selectAchievementPreview(items);
  $('achievementPreview').innerHTML = preview.length ? preview.map(achievementCard).join('') : empty('Achievement ledger is ready.');
  $('achievementGrid').innerHTML = items.length ? achievementCategoryGroups(items) : empty('Achievement definitions are available once local state appears.');
}

function achievementSortOrder(item) {
  const order = Number(item?.sort_order);
  return Number.isFinite(order) ? order : 9999;
}

function sortAchievements(items) {
  return [...items].sort((left, right) => achievementSortOrder(left) - achievementSortOrder(right) || String(left.title || '').localeCompare(String(right.title || '')));
}

function selectAchievementPreview(items) {
  const withTime = (item) => {
    const time = new Date(item.unlocked_at || 0).getTime();
    return Number.isNaN(time) ? 0 : time;
  };
  const latestUnlocked = items
    .filter((item) => item.unlocked)
    .sort((left, right) => withTime(right) - withTime(left) || achievementSortOrder(right) - achievementSortOrder(left));
  const relevantLocked = items.filter((item) => !item.unlocked);
  const seen = new Set();
  return [...latestUnlocked, ...relevantLocked]
    .filter((item) => {
      const key = item.id || item.title;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    })
    .slice(0, 3);
}

function achievementProgressHeader(unlockedCount, totalCount, progress) {
  return `
    <div class="achievement-progress-copy">
      <span>Progress</span>
      <strong>${escapeHtml(unlockedCount)}/${escapeHtml(totalCount)}</strong>
    </div>
    <div class="achievement-progress-track" role="progressbar" aria-label="Achievement unlock progress" aria-valuemin="0" aria-valuemax="${escapeHtml(totalCount)}" aria-valuenow="${escapeHtml(unlockedCount)}">
      <span style="width:${escapeHtml(Math.max(0, Math.min(100, progress)))}%"></span>
    </div>
  `;
}

function achievementCategoryGroups(items) {
  const groups = new Map();
  items.forEach((item) => {
    const category = item.category || 'Achievements';
    if (!groups.has(category)) groups.set(category, []);
    groups.get(category).push(item);
  });
  return [...groups.entries()].map(([category, categoryItems]) => {
    const unlocked = categoryItems.filter((item) => item.unlocked).length;
    return `
      <section class="achievement-category">
        <div class="achievement-category-head">
          <h2>${escapeHtml(category)}</h2>
          <span>${escapeHtml(unlocked)}/${escapeHtml(categoryItems.length)} unlocked</span>
        </div>
        <div class="achievement-grid">
          ${categoryItems.map(achievementCard).join('')}
        </div>
      </section>
    `;
  }).join('');
}

function achievementCard(item) {
  const stateLabel = item.unlocked ? 'Unlocked' : 'Locked';
  const body = item.unlocked ? (item.description || item.locked_hint || '') : (item.locked_hint || item.description || '');
  const unlockedDate = item.unlocked_at ? formatDate(item.unlocked_at) : '';
  const meta = [item.category, item.tier].filter(Boolean).join(' / ');
  return `
    <article class="achievement-badge ${item.unlocked ? 'unlocked' : 'locked'}" data-accent="${escapeHtml(item.accent || 'primary')}">
      <div class="achievement-medallion" aria-hidden="true">${escapeHtml(item.icon || (item.unlocked ? '*' : '?'))}</div>
      <div class="achievement-body">
        <div class="achievement-title-row">
          <strong>${escapeHtml(item.title || 'Achievement')}</strong>
          <span>${escapeHtml(stateLabel)}</span>
        </div>
        <small>${escapeHtml(meta || 'Achievement')}</small>
        <p>${escapeHtml(body)}</p>
        ${unlockedDate ? `<time datetime="${escapeHtml(item.unlocked_at)}">Unlocked ${escapeHtml(unlockedDate)}</time>` : ''}
      </div>
    </article>
  `;
}

function renderCustomPets(snapshot) {
  const pets = snapshot.custom_pets || [];
  const codexPets = snapshot.codex_pets || [];
  const hasCurrentCustom = pets.some((pet) => pet.current);
  $('customDir').textContent = snapshot.state_dir ? `${snapshot.state_dir}/custom-pets` : '';
  $('customDir').title = $('customDir').textContent;
  renderCodexImportOptions(codexPets);
  $('customPetsList').innerHTML = `
    ${hasCurrentCustom ? `
      <div class="custom-current-note">
        <div>
          <strong>Custom pet active</strong>
          <span>This imported pet is the active companion. Clear it to remove the custom active pet without deleting the installed package.</span>
        </div>
        <button class="secondary" type="button" data-clear-current-custom="true">Use built-in pet</button>
      </div>
    ` : ''}
    ${pets.length ? pets.map((pet) => `
    <div class="pet-row ${pet.current ? 'current-custom' : ''}">
      <div>
        <strong>${pet.current ? 'Active custom pet / ' : ''}${escapeHtml(pet.name)}</strong>
        <small>${pet.valid ? petSummary(pet) : `invalid / ${escapeHtml(pet.error || 'unknown error')}`}</small>
      </div>
      <div class="row-actions">
        <button class="tiny" type="button" data-use="${escapeHtml(pet.name)}" ${pet.valid ? '' : 'disabled'}>Use custom</button>
        ${pet.current ? '<button class="tiny secondary" type="button" data-clear-current-custom="true">Clear</button>' : ''}
        <button class="tiny danger" type="button" data-remove="${escapeHtml(pet.name)}">Remove</button>
      </div>
    </div>
  `).join('') : empty('No custom pets installed. Import a validated local package by path. Built-in pets are available from Change Pet.')}
  `;
}

function petSummary(pet) {
  const frames = (pet.state_summary || []).map((item) => `${item.name}:${item.frame_count}`).join(', ');
  const missing = (pet.missing_optional_states || []).slice(0, 3).join(', ');
  return escapeHtml(`${frames || (pet.states || []).join(', ') || 'valid'}${missing ? ' / missing ' + missing : ''}`);
}

function renderCodexImportOptions(codexPets) {
  const select = $('codexPetSelect');
  const meta = $('codexImportMeta');
  if (!select || !meta) return;
  if (!codexPets.length) {
    select.innerHTML = '<option value="latest">No Codex pets found</option>';
    select.disabled = true;
    $('importCodexBtn').disabled = true;
    meta.textContent = 'No importable Codex desktop pets found under known Codex pet stores.';
    return;
  }
  select.disabled = false;
  $('importCodexBtn').disabled = false;
  select.innerHTML = codexPets.map((pet, index) => {
    const value = index === 0 ? 'latest' : (pet.path || pet.slug);
    const states = (pet.states || []).join(', ');
    const source = pet.source_label || pet.source_kind || 'codex';
    return `<option value="${escapeHtml(value)}">${escapeHtml(index === 0 ? 'latest / ' : '')}${escapeHtml(pet.slug)} (${escapeHtml(source)}, ${escapeHtml(states || 'valid')})</option>`;
  }).join('');
  meta.textContent = `${codexPets.length} Codex-created pet${codexPets.length === 1 ? '' : 's'} found. Latest defaults to ${codexPets[0].slug}.`;
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
    <button type="button" class="${value === active ? 'active' : ''}" data-value="${escapeHtml(value)}" aria-pressed="${value === active ? 'true' : 'false'}">${escapeHtml(value)}</button>
  `).join('');
  $(id).querySelectorAll('button').forEach((button) => {
    button.addEventListener('click', () => onClick(button.dataset.value));
  });
}

function voiceReasonMessage(reason) {
  const normalized = String(reason || '').toLowerCase();
  if (normalized.startsWith('invalid-command')) return 'The adapter command could not be parsed.';
  if (normalized.includes('no such file') || normalized.includes('not found')) return 'The adapter could not be started.';
  const messages = {
    'voice-command-missing': 'No adapter command is configured.',
    timeout: 'The adapter timed out before finishing.',
    'command-failed': 'The adapter exited with a non-zero status.',
    'voice-disabled': 'Voice preview is disabled.',
    'quiet-mode-silent': 'Silent mode suppressed voice output.',
    'event-not-allowlisted': 'This event is not enabled for voice preview.',
  };
  return messages[normalized] || 'The adapter did not complete.';
}

function voiceSourceLabel(voice) {
  if (voice?.command_source === 'env') return 'local environment';
  return 'saved preferences';
}

function hydrateVoice(voice) {
  state.voice = voice;
  const commandFromEnv = voice?.command_source === 'env';
  const hasCommand = !!String(voice?.command || '').trim();
  $('voiceEnabled').checked = !!voice?.enabled;
  $('voiceCommand').disabled = commandFromEnv;
  $('voiceCommand').value = commandFromEnv ? '' : (voice?.command || '');
  $('voiceCommand').placeholder = commandFromEnv ? 'Configured by local environment' : 'Local adapter command';
  const enabledText = voice?.enabled ? 'enabled' : 'disabled';
  const commandText = hasCommand ? `adapter configured through ${voiceSourceLabel(voice)}` : 'no adapter command configured';
  const bridgeText = state.snapshot?.bridge?.available === false ? ' Bridge is offline; explicit voice tests still run locally.' : '';
  $('voiceMeta').textContent = `Voice preview ${enabledText}; ${commandText}.${bridgeText}`;
}

function setVoiceBusy(isBusy) {
  $('testVoiceBtn').disabled = isBusy;
  $('testVoiceBtn').setAttribute('aria-busy', isBusy ? 'true' : 'false');
  $('voiceResult').setAttribute('aria-busy', isBusy ? 'true' : 'false');
}

function renderVoiceResult(result) {
  const ok = !!result?.ok;
  const skipped = !!result?.skipped;
  const tone = ok && !skipped ? 'success' : 'error';
  const title = ok && !skipped ? 'Voice test completed' : 'Voice test did not play';
  const detail = ok && !skipped ? 'The adapter accepted the test text.' : voiceReasonMessage(result?.reason);
  const exitRow = Number.isInteger(result?.exit_code)
    ? `<div class="result-row"><span>Exit code</span><strong>${escapeHtml(result.exit_code)}</strong></div>`
    : '';
  $('voiceResult').dataset.tone = tone;
  $('voiceResult').innerHTML = `
    <div class="result-summary">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(detail)}</span>
    </div>
    ${exitRow}
  `;
}

async function refresh() {
  try {
    if (!state.snapshot) renderLoadingState();
    renderSnapshot(await api('/api/state'));
    loadSpecies();
  } catch (error) {
    if (state.snapshot) {
      document.body.dataset.stale = 'true';
      $('lastRefresh').textContent = 'Refresh failed; showing the last successful local snapshot.';
      showAlert(`Refresh failed: ${error.message}. Showing the last successful snapshot.`, 'error');
    } else {
      renderApiError(error);
      $('lastRefresh').textContent = 'Local state could not be loaded.';
      showAlert(error.message, 'error');
    }
  }
}

function confirmFreshPet(actionLabel) {
  const pet = state.snapshot?.pet;
  if (!pet) return true;
  return window.confirm(
    `${actionLabel} will replace ${pet.name || 'the active pet'} with a fresh pet. ` +
    'XP, stats, and milestones will reset. Installed custom pet packages are kept, but the current custom pet selection will be cleared. Continue?'
  );
}

function snapshotFromResult(result) {
  return result.snapshot || result.state || result;
}

async function replacePet(path, body, successMessage) {
  try {
    const result = await api(path, {
      method: 'POST',
      body: JSON.stringify(body || {}),
    });
    const snapshot = snapshotFromResult(result);
    if (snapshot?.pet !== undefined) renderSnapshot(snapshot);
    await loadSpecies();
    showAlert(successMessage, 'success');
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
    const body = { enabled: $('voiceEnabled').checked };
    if (!$('voiceCommand').disabled) body.command = $('voiceCommand').value;
    const result = await api('/api/voice', {
      method: 'POST',
      body: JSON.stringify(body),
    });
    hydrateVoice(result.status);
    const hasCommand = !!String(result.status?.command || '').trim();
    showAlert(hasCommand ? 'Voice preview saved.' : 'Voice preview saved. Add an adapter command before running a test.', hasCommand ? 'success' : 'info');
  } catch (error) {
    showAlert('Voice settings could not be saved.', 'error');
  }
}

document.querySelectorAll('.nav-item').forEach((button) => button.addEventListener('click', () => setView(button.dataset.view)));
window.addEventListener('resize', () => {
  const activeBtn = document.querySelector('.nav-item.active');
  const indicator = $('nav-indicator');
  if (activeBtn && indicator) {
    indicator.style.transform = `translateY(${activeBtn.offsetTop}px)`;
    indicator.style.height = `${activeBtn.offsetHeight}px`;
  }
});
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
$('importCodexBtn').addEventListener('click', async () => {
  try {
    const result = await api('/api/custom-pets/import-codex', {
      method: 'POST',
      body: JSON.stringify({
        target: $('codexPetSelect').value || 'latest',
        name: $('codexImportName').value,
        use: $('codexUseAfterImport').checked,
        replace: $('codexReplaceImport').checked,
      }),
    });
    $('codexImportName').value = '';
    const snapshot = snapshotFromResult(result);
    if (snapshot?.custom_pets !== undefined) renderSnapshot(snapshot);
    const selectedMessage = result.bridge_notified === false
      ? 'Codex pet imported and selected. Bridge is offline.'
      : 'Codex pet imported and selected.';
    showAlert(result.current ? selectedMessage : 'Codex pet imported.', 'success');
    refresh();
  } catch (error) {
    showAlert(error.message, 'error');
  }
});
$('customPetsList').addEventListener('click', async (event) => {
  const use = event.target?.dataset?.use;
  const remove = event.target?.dataset?.remove;
  const clearCurrent = event.target?.dataset?.clearCurrentCustom;
  try {
    if (use) await api('/api/custom-pets/use', { method: 'POST', body: JSON.stringify({ name: use }) });
    if (clearCurrent) await api('/api/custom-pets/clear-current', { method: 'POST', body: '{}' });
    if (remove) await api(`/api/custom-pets/${encodeURIComponent(remove)}`, { method: 'DELETE' });
    showAlert(use ? 'Custom pet activated.' : clearCurrent ? 'Custom active pet cleared.' : 'Custom pet package removed.', clearCurrent ? 'success' : 'info');
    refresh();
  } catch (error) {
    showAlert(error.message, 'error');
  }
});
$('speciesList').addEventListener('click', async (event) => {
  const species = event.target?.dataset?.adoptSpecies;
  if (!species || !confirmFreshPet(`Adopting ${species}`)) return;
  await replacePet('/api/pets/adopt', { species }, `${species} adopted as a fresh built-in pet.`);
});
$('randomHatchBtn').addEventListener('click', async () => {
  if (!confirmFreshPet('Random hatch')) return;
  await replacePet('/api/pets/random-hatch', {}, 'Random built-in pet hatched.');
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
    setVoiceBusy(true);
    $('voiceResult').dataset.tone = 'info';
    $('voiceResult').textContent = 'Running explicit local voice test...';
    const result = await api('/api/voice/test', {
      method: 'POST',
      body: JSON.stringify({ text: $('voiceText').value }),
    });
    hydrateVoice(result.status);
    renderVoiceResult(result.result || {});
    showAlert(result.result?.ok ? 'Voice test completed.' : voiceReasonMessage(result.result?.reason), result.result?.ok ? 'success' : 'error');
  } catch (error) {
    $('voiceResult').dataset.tone = 'error';
    $('voiceResult').innerHTML = `
      <div class="result-summary">
        <strong>Voice test unavailable</strong>
        <span>The local dashboard API could not complete the explicit test.</span>
      </div>
    `;
    showAlert('Voice test could not be completed.', 'error');
  } finally {
    setVoiceBusy(false);
  }
});

setView(new URLSearchParams(window.location.search).get('view') || 'overview');
refresh();
