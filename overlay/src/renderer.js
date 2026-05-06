/**
 * Hermes Pets Overlay Renderer
 * Receives events from the Electron bridge and updates the sprite + UI.
 */

// DOM refs
const spriteEl = document.getElementById('pet-sprite');
const nameEl = document.getElementById('pet-name');
const levelEl = document.getElementById('pet-level');
const xpFillEl = document.getElementById('xp-fill');
const statsEl = document.getElementById('pet-stats');
const bubbleEl = document.getElementById('pet-bubble');
const bubbleTextEl = document.getElementById('bubble-text');
const minBtn = document.getElementById('minimize-btn');
const connectionStatusEl = document.getElementById('connection-status');
const eventTrayEl = document.getElementById('event-tray');
const eventListEl = document.getElementById('event-list');
const currentStatusEl = document.getElementById('current-status');
const eventSummaryEl = document.getElementById('event-summary');
const DEBUG_EVENTS = new URLSearchParams(window.location.search).get('debugEvents') === '1';

function debugEvent(message, ...args) {
  if (DEBUG_EVENTS) console.log(`[pet-renderer/events] ${message}`, ...args);
}

// ---- Animation state machine ----
const DEBUG_ANIM = new URLSearchParams(window.location.search).get('debugAnimation') === '1';

var _petDragging = false;

const animController = {
  manifest: null,
  currentState: null,
  currentFrame: 0,
  frameTimer: null,
  species: '',
  customPet: null,
  blinkTimer: null,
  hoverActive: false,
  _playingOneShot: false,

  // Preload cache: str key -> truthy (loaded OK)
  _preloaded: Object.create(null),
  // Set of keys that failed to load (avoid retrying)
  _unavailable: Object.create(null),
  // Last src assigned to backgroundImage to avoid redundant writes
  _lastBgSrc: '',

  debugLog(msg) {
    if (DEBUG_ANIM) console.log('[pet-anim] ' + msg);
  },

  normalizeStateName(stateName) {
    var aliases = {
      'running-left': 'run_left',
      'running-right': 'run_right',
      'walk-left': 'walk_left',
      'walk-right': 'walk_right',
      'message-received': 'message_react',
      'message': 'message_react',
      'bubble': 'bubble_react',
      'thinking': 'review',
      'busy': 'waiting',
      'happy': 'jumping',
      'sad': 'failed',
      'error': 'failed',
      'offline': 'waiting'
    };
    return aliases[stateName] || stateName;
  },

  _stateAssetDir(stateName, cfg) {
    var assetDir = cfg && cfg.assetDir ? cfg.assetDir : stateName;
    if (this.customPet && this.customPet.baseUrl) {
      return this.customPet.baseUrl + '/sprites/' + assetDir + '/';
    }
    return '../assets/sprites/' + this.species + '/' + assetDir + '/';
  },

  hasStateConfig(stateName) {
    if (!this.manifest || !this.manifest.states) return false;
    stateName = this.normalizeStateName(stateName);
    var speciesStates = this.manifest.species
      && this.species
      && this.manifest.species[this.species]
      && this.manifest.species[this.species].states;
    if (this.customPet && this.customPet.manifest && this.customPet.manifest.states) {
      return !!this.customPet.manifest.states[stateName];
    }
    return !!((speciesStates && speciesStates[stateName]) || this.manifest.states[stateName]);
  },

  _preloadKey(key, src) {
    if (this._preloaded[key]) return Promise.resolve(true);
    if (this._unavailable[key]) return Promise.resolve(false);
    return new Promise(function(resolve) {
      var img = new Image();
      img.onload = function() { resolve(true); };
      img.onerror = function() { resolve(false); };
      img.src = src;
    });
  },

  _preloadFrames(stateName, cfg) {
    var self = this;
    var frames = (cfg && cfg.frames && cfg.frames.length > 0) ? cfg.frames : null;
    if (!frames) return Promise.resolve();
    var basePath = this._stateAssetDir(stateName, cfg);
    var promises = frames.map(function(f) {
      var key = stateName + '|' + f;
      var src = basePath + f;
      return self._preloadKey(key, src).then(function(ok) {
        if (ok) {
          self._preloaded[key] = true;
        } else {
          self._unavailable[key] = true;
          self.debugLog('preload FAIL: ' + src + ' (marked unavailable)');
        }
        return ok;
      });
    });
    return Promise.all(promises).then(function() {
      self.debugLog('preload complete: ' + stateName + ' frames=' + frames.length);
    });
  },

  async loadManifest() {
    try {
      // Use IPC to bypass file:// fetch restrictions in Electron with context isolation
      if (window.hermesPetAPI && window.hermesPetAPI.loadManifest) {
        this.manifest = await window.hermesPetAPI.loadManifest();
        if (this.manifest) {
          this.debugLog('manifest loaded via IPC, species: ' +
            (this.manifest.species ? Object.keys(this.manifest.species).join(', ') : '(none)') +
            ', states: ' + Object.keys(this.manifest.states || {}).join(', '));
          return;
        }
      }
      // Fallback: try fetch (works in dev without context isolation)
      var resp = await fetch('../assets/manifest.json');
      if (!resp.ok) throw new Error('HTTP ' + resp.status);
      this.manifest = await resp.json();
      this.debugLog('manifest loaded via fetch, species: ' +
        (this.manifest.species ? Object.keys(this.manifest.species).join(', ') : '(none)') +
        ', states: ' + Object.keys(this.manifest.states || {}).join(', '));
    } catch (err) {
      this.debugLog('manifest load failed: ' + err.message + ' (using CSS fallback)');
      this.manifest = null;
    }
  },

  getStateConfig(stateName) {
    if (!this.manifest || !this.manifest.states) return null;
    stateName = this.normalizeStateName(stateName);
    var speciesStates = this.manifest.species
      && this.species
      && this.manifest.species[this.species]
      && this.manifest.species[this.species].states;
    if (this.customPet && this.customPet.manifest && this.customPet.manifest.states) {
      return this.customPet.manifest.states[stateName]
        || this.customPet.manifest.states.idle
        || this.manifest.states[stateName]
        || this.manifest.states.idle
        || null;
    }
    return (speciesStates && speciesStates[stateName])
      || this.manifest.states[stateName]
      || (speciesStates && speciesStates.idle)
      || this.manifest.states.idle
      || null;
  },

  resolveFrameSrc(stateName, frameIndex) {
    if (!this.species) return '';
    var cfg = this.getStateConfig(stateName);
    var frames = cfg && cfg.frames && cfg.frames.length > 0 ? cfg.frames : null;
    if (frames) {
      var idx = frameIndex % frames.length;
      var file = frames[idx];
      return this._stateAssetDir(stateName, cfg) + file;
    }
    if (this.customPet && this.customPet.baseUrl) return '';
    return '../assets/sprites/' + this.species + '.png';
  },

  mayTransiton(stateName) {
    if (stateName === 'drag') return true;
    if (_petDragging) {
      this.debugLog('BLOCKED transition to "' + stateName + '" (dragging)');
      return false;
    }
    if (this._playingOneShot) {
      this.debugLog('BLOCKED transition to "' + stateName + '" (one-shot ' + this.currentState + ' playing)');
      return false;
    }
    return true;
  },

  transition(stateName) {
    var self = this;
    if (!this.manifest || !this.species) return;
    stateName = this.normalizeStateName(stateName);

    if (!this.mayTransiton(stateName)) return;

    var cfg = this.hasStateConfig(stateName) ? this.getStateConfig(stateName) : null;
    if (!cfg) {
      this.debugLog('unknown state "' + stateName + '", falling back to idle');
      stateName = 'idle';
      cfg = this.getStateConfig('idle');
      if (!cfg) return;
    }

    if (this.currentState === stateName && cfg.loop !== false) {
      this.debugLog('SKIP transition: already ' + stateName + ' (looping)');
      return;
    }

    this.debugLog('transition: ' + (this.currentState || 'none') + ' -> ' + stateName +
      '  species=' + this.species + '  dragging=' + _petDragging +
      '  oneShot=' + this._playingOneShot + '  hover=' + this.hoverActive);

    this.stopLoop();
    var wasOneShot = this._playingOneShot;
    this._playingOneShot = cfg.loop === false;
    if (wasOneShot && !this._playingOneShot) {
      this.debugLog('one-shot cancelled (interrupted by ' + stateName + ')');
    }
    this.currentState = stateName;
    this.currentFrame = 0;

    this._preloadFrames(stateName, cfg).then(function() {
      if (self.currentState !== stateName) {
        self.debugLog('DISCARD stale preload for ' + stateName + ' (current=' + self.currentState + ')');
        return;
      }
      self._renderFrame(stateName, 0);
      self._startLoop(stateName, cfg);
    });
  },

  _renderFrame(stateName, frameIndex) {
    if (!this.species) return;
    var src = this.resolveFrameSrc(stateName, frameIndex);

    if (src === this._lastBgSrc) {
      this.debugLog('frame NOP ' + frameIndex + ' of "' + stateName + '" (same as last)');
      return;
    }

    var file = src.split('/').pop();
    var key = stateName + '|' + file;

    if (this._unavailable[key]) {
      var cfg = this.getStateConfig(stateName);
      var frames = cfg && cfg.frames;
      if (frames) {
        for (var i = 0; i < frames.length; i++) {
          var tryIdx = (frameIndex + i) % frames.length;
          var tryFile = frames[tryIdx];
          var tryKey = stateName + '|' + tryFile;
          if (!this._unavailable[tryKey]) {
            src = this._stateAssetDir(stateName, cfg) + tryFile;
            this.debugLog('frame FALLBACK ' + frameIndex + ' -> ' + tryIdx + ' of "' + stateName + '" (' + tryFile + ')');
            break;
          }
        }
      }
      if (src === this._lastBgSrc) return;
    }

    this._lastBgSrc = src;
    spriteEl.style.backgroundImage = 'url("' + src + '")';
    this.debugLog('frame ' + frameIndex + ' of "' + stateName + '"  src=' + src);
    if (DEBUG_ANIM) this._updateDebugOverlay(stateName, frameIndex, src);
  },

  _startLoop(stateName, cfg) {
    var self = this;
    var fps = cfg.fps || 1;
    var looper = cfg.loop !== false;
    var fallback = cfg.fallback || 'idle';
    var totalFrames = (cfg.frames && cfg.frames.length) || 1;

    this.debugLog('loop start: state=' + stateName + ' fps=' + fps + ' loop=' + looper +
      ' totalFrames=' + totalFrames + ' fallback=' + fallback);

    this.frameTimer = setInterval(function() {
      self.currentFrame++;

      if (looper && self.currentFrame >= totalFrames) {
        self.currentFrame = 0;
      }

      if (!looper && self.currentFrame >= totalFrames) {
        self.debugLog('one-shot "' + stateName + '" complete -> "' + fallback + '"');
        self.stopLoop();
        self._playingOneShot = false;
        self.transition(fallback);
        return;
      }

      self._renderFrame(stateName, self.currentFrame);
    }, 1000 / Math.max(fps, 1));
  },

  stopLoop() {
    if (this.frameTimer) {
      clearInterval(this.frameTimer);
      this.frameTimer = null;
    }
  },

  init(species, customPet) {
    this.customPet = customPet || null;
    this.species = species;
    if (!this.manifest) return;
    this.stopLoop();
    this.currentState = null;
    this.currentFrame = 0;
    this._playingOneShot = false;
    this._preloaded = Object.create(null);
    this._unavailable = Object.create(null);
    this._lastBgSrc = '';
    this.debugLog('init species=' + species + (this.customPet ? ' custom=' + this.customPet.name : ''));
    this.transition('idle');
    this._startBlinkTimer();
  },

  _updateDebugOverlay(stateName, frameIndex, src) {
    var el = document.getElementById('pet-anim-debug');
    if (!el) {
      el = document.createElement('div');
      el.id = 'pet-anim-debug';
      el.style.cssText =
        'position:absolute;top:0;left:0;' +
        'background:rgba(0,0,0,0.75);color:#0f0;' +
        'font:10px monospace;padding:4px 6px;' +
        'z-index:99;pointer-events:none;border-radius:0 0 6px 0;' +
        'max-width:280px;white-space:pre-wrap;word-break:break-all;';
      document.getElementById('pet-container').appendChild(el);
    }
    var file = src.split('/').pop() || src;
    el.textContent = 'state=' + stateName +
      ' frame=' + frameIndex +
      ' file=' + file +
      '\nspecies=' + this.species +
      '\ndrag=' + _petDragging +
      ' hover=' + this.hoverActive +
      ' oneshot=' + this._playingOneShot;
  },

  _removeDebugOverlay() {
    var el = document.getElementById('pet-anim-debug');
    if (el) el.remove();
  },

  _startBlinkTimer() {
    this._stopBlinkTimer();
    this._scheduleBlink();
  },

  _scheduleBlink() {
    var self = this;
    this.blinkTimer = setTimeout(function() {
      var canBlink = self.currentState === 'idle' &&
        !_petDragging &&
        !self.hoverActive &&
        !self._playingOneShot;
      if (!canBlink) {
        self.debugLog('BLOCKED blink (state=' + self.currentState +
          ' dragging=' + _petDragging +
          ' hover=' + self.hoverActive +
          ' oneshot=' + self._playingOneShot + ')');
        self._scheduleBlink();
        return;
      }
      if (Math.random() < 0.3) {
        self.transition('blink');
      }
      self._scheduleBlink();
    }, 4000 + Math.random() * 8000);
  },

  _stopBlinkTimer() {
    if (this.blinkTimer) {
      clearTimeout(this.blinkTimer);
      this.blinkTimer = null;
    }
  }
};

// State
let state = {
  species: '',
  name: '',
  level: 1,
  xp: 0,
  xpNext: 100,
  variant: 'normal',
  mood: 'idle',
  currentStatus: 'Idle',
  visible: true,
  shiny: false,
  hat: false,
};

let bubbleTimeout = null;
let bubblePulseTimeout = null;
let reactTimeout = null;
let eventTrayTimeout = null;
let lastMood = 'idle';
let dragPointerId = null;
let dragStart = null;
let dragMoved = false;

const RECENT_EVENT_LIMIT = 6;
const BUBBLE_THROTTLE_MS = 2500;
const STATUS_THROTTLE_MS = 5000;
const DEFAULT_NOTIFICATION_PREFS = {
  notification_profile: 'normal',
  muted_until: null,
  quiet_mode: 'off',
  bubble_throttle_seconds: BUBBLE_THROTTLE_MS / 1000,
  show_tray_on_urgent: true,
  show_idle_bubbles: true,
};
const recentEvents = [];
const lastBubbleByKey = Object.create(null);
const lastBubbleByChannel = Object.create(null);
let notificationPrefs = { ...DEFAULT_NOTIFICATION_PREFS };
let trayAttention = false;

// ---- Sprite setters ----
const ASSET_BASE = '../assets/sprites';

function pathToFileUrl(filePath) {
  var text = String(filePath || '').replace(/\\/g, '/');
  if (!text) return '';
  if (/^file:\/\//i.test(text)) return text.replace(/\/+$/, '');
  if (text.startsWith('//')) return 'file:' + encodeURI(text).replace(/#/g, '%23').replace(/\?/g, '%3F');
  if (/^[A-Za-z]:\//.test(text)) return 'file:///' + encodeURI(text).replace(/#/g, '%23').replace(/\?/g, '%3F');
  return 'file://' + encodeURI(text).replace(/#/g, '%23').replace(/\?/g, '%3F');
}

function normalizeCustomPet(customPet) {
  if (!customPet || typeof customPet !== 'object') return null;
  var petPath = customPet.overlay_path || customPet.path;
  if (!petPath || !customPet.manifest || !customPet.manifest.states || !customPet.manifest.states.idle) {
    return null;
  }
  return {
    name: String(customPet.name || 'custom'),
    baseUrl: pathToFileUrl(petPath),
    manifest: customPet.manifest,
  };
}

function setSprite(species, variant) {
  if (variant === void 0) variant = 'normal';
  var nextCustomPet = normalizeCustomPet(state.custom_pet);
  var currentCustomName = animController.customPet && animController.customPet.name;
  var nextCustomName = nextCustomPet && nextCustomPet.name;
  if (animController.species !== species || currentCustomName !== nextCustomName) {
    if (_petDragging) {
      if (DEBUG_ANIM) console.log('[pet-anim] BLOCKED setSprite(' + species + ') while dragging');
      return;
    }
    animController.species = species;
    if (animController.manifest) animController.init(species, nextCustomPet);
    else spriteEl.style.backgroundImage = 'url("' + ASSET_BASE + '/' + species + '.png")';
  }
}

function setMood(mood) {
  spriteEl.classList.remove('idle', 'happy', 'thinking', 'busy');
  spriteEl.classList.add(mood || 'idle');
  spriteEl.classList.toggle('pet-idle', (mood || 'idle') === 'idle');
  transitionForMood(mood);
}

function transitionForMood(mood) {
  var stateForMood = {
    idle: 'idle',
    happy: 'jumping',
    thinking: 'review',
    busy: 'waiting',
    sad: 'failed',
    failed: 'failed',
    error: 'failed',
    waiting: 'waiting',
    running: 'running'
  };
  var nextState = stateForMood[mood || 'idle'];
  if (nextState) animController.transition(nextState);
}

function setShiny(on) {
  spriteEl.classList.toggle('shiny', on);
}

function triggerReaction(duration = 900) {
  if (reactTimeout) clearTimeout(reactTimeout);
  spriteEl.classList.remove('pet-react');
  void spriteEl.offsetWidth;
  spriteEl.classList.add('pet-react');
  reactTimeout = setTimeout(() => {
    spriteEl.classList.remove('pet-react');
    reactTimeout = null;
  }, duration);
}

// ---- Stats badge ----
function updateStats() {
  nameEl.textContent = state.name || '...';
  levelEl.textContent = `Lv.${state.level}`;
  const pct = Math.min(100, Math.round((state.xp / state.xpNext) * 100));
  xpFillEl.style.width = `${pct}%`;
}

// Show stats on hover over sprite
spriteEl.addEventListener('mouseenter', () => {
  if (_petDragging) return;
  statsEl.classList.add('visible');
  spriteEl.classList.add('pet-hover');
  animController.hoverActive = true;
  animController.transition('hover');
});
spriteEl.addEventListener('mouseleave', () => {
  statsEl.classList.remove('visible');
  spriteEl.classList.remove('pet-hover');
  animController.hoverActive = false;
  if (!_petDragging) animController.transition('idle');
});

// ---- Chat bubble ----
function showBubble(text, duration = 3500) {
  if (bubbleTimeout) clearTimeout(bubbleTimeout);
  bubbleTextEl.textContent = text;
  bubbleEl.className = 'bubble';
  bubbleEl.classList.remove('hidden');
  if (bubblePulseTimeout) clearTimeout(bubblePulseTimeout);
  bubbleEl.classList.remove('bubble-pulse');
  void bubbleEl.offsetWidth;
  bubbleEl.classList.add('bubble-pulse');
  bubblePulseTimeout = setTimeout(() => {
    bubbleEl.classList.remove('bubble-pulse');
    bubblePulseTimeout = null;
  }, 420);

  // Position: above the sprite, centered
  const rect = spriteEl.getBoundingClientRect();
  bubbleEl.style.bottom = `${rect.height + 12}px`;
  bubbleEl.style.left = `${rect.left + rect.width / 2 - bubbleEl.offsetWidth / 2}px`;

  bubbleTimeout = setTimeout(() => {
    bubbleEl.classList.add('fade-out');
    setTimeout(() => bubbleEl.classList.add('hidden'), 400);
  }, duration);
}

// ---- Recent event memory ----
function singleLineText(value, limit) {
  var text = String(value || '').replace(/\s+/g, ' ').trim();
  if (!limit || text.length <= limit) return text;
  return text.slice(0, Math.max(0, limit - 1)).trimEnd() + '...';
}

function titleCaseText(value) {
  return singleLineText(value, 40).replace(/(^|[\s_-])([a-z])/g, function(match) {
    return match.toUpperCase();
  });
}

function eventText(msg) {
  if (msg.type === 'message_received') {
    const source = titleCaseText(msg.source || 'message');
    const sender = singleLineText(msg.sender || 'someone', 60);
    const body = singleLineText(msg.text || '', 180);
    return body ? source + ' from ' + sender + ': ' + body : source + ' from ' + sender;
  }
  if (msg.text) return singleLineText(msg.text, 220);
  return String(msg.type || 'Event');
}

function eventSeverity(msg) {
  if (msg.severity) return String(msg.severity);
  var severityByType = {
    job_finished: 'success',
    job_failed: 'error',
    approval_needed: 'warning',
    message_received: msg.urgent ? 'warning' : 'info'
  };
  return severityByType[msg.type] || 'info';
}

function eventGroup(msg) {
  if (msg.type === 'job_failed' || msg.type === 'job_finished' || msg.type === 'job_started') return 'jobs';
  if (msg.type === 'message_received') return 'messages';
  if (msg.type === 'approval_needed') return 'approvals';
  if (msg.type === 'daily_brief') return 'briefs';
  return 'status';
}

function normalizeNotificationPrefs(prefs) {
  var next = { ...DEFAULT_NOTIFICATION_PREFS };
  if (prefs && typeof prefs === 'object') {
    Object.assign(next, prefs);
  }
  if (!['normal', 'focus', 'pairing', 'demo', 'silent'].includes(next.notification_profile)) {
    next.notification_profile = 'normal';
  }
  if (!['off', 'important', 'silent'].includes(next.quiet_mode)) {
    next.quiet_mode = 'off';
  }
  var throttle = Number(next.bubble_throttle_seconds);
  next.bubble_throttle_seconds = Number.isFinite(throttle) ? Math.max(0, throttle) : DEFAULT_NOTIFICATION_PREFS.bubble_throttle_seconds;
  next.show_tray_on_urgent = next.show_tray_on_urgent !== false;
  next.show_idle_bubbles = next.show_idle_bubbles !== false;
  if (next.muted_until) {
    var mutedUntilMs = Date.parse(String(next.muted_until));
    next.muted_until = Number.isFinite(mutedUntilMs) && mutedUntilMs > Date.now() ? String(next.muted_until) : null;
  }
  return next;
}

function updateNotificationPrefs(prefs) {
  notificationPrefs = normalizeNotificationPrefs(prefs);
  debugEvent('notification prefs updated', notificationPrefs);
}

function eventIcon(msg) {
  var iconByType = {
    status: 'S',
    job_started: '>',
    job_finished: 'OK',
    job_failed: '!',
    job_history: 'J',
    approval_needed: '?',
    message_received: '@',
    daily_brief: '#',
    bubble: '*'
  };
  return iconByType[msg.type] || '*';
}

function recordRecentEvent(msg) {
  if (!msg || !msg.type || msg.type === 'state') return;
  var item = {
    id: msg.id || String(Date.now()) + '-' + recentEvents.length,
    type: msg.type,
    group: eventGroup(msg),
    text: eventText(msg),
    severity: eventSeverity(msg),
    createdAt: msg.created_at || new Date().toISOString()
  };
  recentEvents.unshift(item);
  if (recentEvents.length > RECENT_EVENT_LIMIT) recentEvents.length = RECENT_EVENT_LIMIT;
  renderRecentEvents();
}

function jobDurationText(job) {
  if (job.duration_text) return String(job.duration_text);
  var seconds = Number(job.duration || 0);
  if (!Number.isFinite(seconds) || seconds < 0) return '-';
  var total = Math.round(seconds);
  if (total < 60) return total + 's';
  var minutes = Math.floor(total / 60);
  var rest = total % 60;
  if (minutes < 60) return minutes + 'm ' + String(rest).padStart(2, '0') + 's';
  var hours = Math.floor(minutes / 60);
  return hours + 'h ' + String(minutes % 60).padStart(2, '0') + 'm';
}

function jobHistoryText(job) {
  var status = job.status === 'failed' ? 'Failed' : 'Done';
  var name = job.name || 'command';
  var exit = job.exit_code == null ? '' : ', exit ' + job.exit_code;
  return status + ': ' + name + ' (' + jobDurationText(job) + exit + ')';
}

function recordJobHistory(msg) {
  var jobs = Array.isArray(msg.jobs) ? msg.jobs.slice(0, 4) : [];
  jobs.reverse().forEach(function(job) {
    var failed = job.status === 'failed' || (job.exit_code != null && job.exit_code !== 0);
    recentEvents.unshift({
      id: job.id || String(Date.now()) + '-job',
      type: failed ? 'job_failed' : 'job_finished',
      group: 'jobs',
      text: jobHistoryText(job),
      severity: failed ? 'error' : 'success',
      createdAt: job.finished_at || job.started_at || msg.created_at || new Date().toISOString()
    });
  });
  if (recentEvents.length > RECENT_EVENT_LIMIT) recentEvents.length = RECENT_EVENT_LIMIT;
  renderRecentEvents();
}

function renderRecentEvents() {
  if (!eventListEl) return;
  if (currentStatusEl) currentStatusEl.textContent = state.currentStatus || 'Idle';
  var summary = { jobs: 0, messages: 0, approvals: 0, briefs: 0, status: 0 };
  var attention = false;
  recentEvents.forEach(function(item) {
    var group = item.group || eventGroup(item);
    summary[group] = (summary[group] || 0) + 1;
    attention = attention || item.severity === 'error' || item.severity === 'warning';
  });
  trayAttention = attention;
  if (eventSummaryEl) {
    var parts = [];
    if (summary.jobs) parts.push(summary.jobs + ' job' + (summary.jobs === 1 ? '' : 's'));
    if (summary.messages) parts.push(summary.messages + ' msg' + (summary.messages === 1 ? '' : 's'));
    if (summary.approvals) parts.push(summary.approvals + ' approval' + (summary.approvals === 1 ? '' : 's'));
    if (summary.briefs) parts.push(summary.briefs + ' brief' + (summary.briefs === 1 ? '' : 's'));
    eventSummaryEl.textContent = parts.length ? parts.join(' / ') : '0 recent';
  }
  if (eventTrayEl) {
    eventTrayEl.classList.toggle('attention', trayAttention);
    eventTrayEl.classList.toggle('quiet-profile', notificationPrefs.quiet_mode !== 'off');
  }
  eventListEl.textContent = '';
  if (recentEvents.length === 0) {
    var empty = document.createElement('div');
    empty.className = 'event-row';
    empty.innerHTML = '<span class="event-icon">-</span><span class="event-text">No recent events</span>';
    eventListEl.appendChild(empty);
    return;
  }
  recentEvents.slice(0, 4).forEach(function(item) {
    var row = document.createElement('div');
    row.className = 'event-row ' + item.severity;
    var icon = document.createElement('span');
    icon.className = 'event-icon';
    icon.textContent = eventIcon(item);
    var text = document.createElement('span');
    text.className = 'event-text';
    var title = document.createElement('span');
    title.className = 'event-title';
    title.textContent = item.text;
    var meta = document.createElement('span');
    meta.className = 'event-meta';
    meta.textContent = titleCaseText(item.group || eventGroup(item));
    text.appendChild(title);
    text.appendChild(meta);
    row.appendChild(icon);
    row.appendChild(text);
    eventListEl.appendChild(row);
  });
}

function setEventTrayVisible(visible, autoHideMs) {
  if (!eventTrayEl) return;
  if (eventTrayTimeout) {
    clearTimeout(eventTrayTimeout);
    eventTrayTimeout = null;
  }
  renderRecentEvents();
  eventTrayEl.classList.toggle('hidden', !visible);
  if (visible && autoHideMs) {
    eventTrayTimeout = setTimeout(function() {
      eventTrayEl.classList.add('hidden');
      eventTrayTimeout = null;
    }, autoHideMs);
  }
}

function mutedNow() {
  if (!notificationPrefs.muted_until) return false;
  var mutedUntilMs = Date.parse(String(notificationPrefs.muted_until));
  if (!Number.isFinite(mutedUntilMs) || mutedUntilMs <= Date.now()) {
    notificationPrefs.muted_until = null;
    return false;
  }
  return true;
}

function isCriticalEvent(msg) {
  return msg.type === 'job_failed' ||
    msg.type === 'approval_needed' ||
    (msg.type === 'message_received' && !!msg.urgent);
}

function bubbleChannelForEvent(msg) {
  if (msg.type === 'status') return 'status';
  if (msg.type === 'job_started') return 'job_lifecycle';
  if (msg.type === 'job_finished') return 'job_success';
  if (msg.type === 'daily_brief') return 'brief';
  return msg.type || 'event';
}

function shouldShowEventBubble(msg) {
  var critical = isCriticalEvent(msg);
  if (mutedNow() && !critical) return false;
  if (notificationPrefs.quiet_mode !== 'off' && !critical) return false;
  if (critical) return true;
  var now = Date.now();
  var text = eventText(msg);
  var key = msg.type + '|' + text;
  var channel = bubbleChannelForEvent(msg);
  var prefThrottleMs = Math.round(Number(notificationPrefs.bubble_throttle_seconds) * 1000);
  var minDelay = msg.type === 'status' ? Math.max(STATUS_THROTTLE_MS, prefThrottleMs) : prefThrottleMs;
  var last = lastBubbleByKey[key] || 0;
  if (now - last < minDelay) return false;
  var lastChannel = lastBubbleByChannel[channel] || 0;
  if (now - lastChannel < minDelay) return false;
  lastBubbleByKey[key] = now;
  lastBubbleByChannel[channel] = now;
  return true;
}

function bubbleTextForEvent(msg) {
  var text = eventText(msg);
  var prefixByType = {
    status: 'Status: ',
    job_started: 'Started: ',
    job_finished: 'Finished: ',
    job_failed: 'Failed: ',
    approval_needed: 'Approval needed: ',
    message_received: msg.urgent || msg.severity === 'warning' ? 'Urgent message: ' : 'Message: ',
    daily_brief: 'Daily brief: '
  };
  return (prefixByType[msg.type] || '') + text;
}

function transitionForEvent(msg) {
  var next = eventReactionFor(msg).animation;
  if (next) {
    if (isCriticalEvent(msg) && animController._playingOneShot) {
      animController._playingOneShot = false;
    }
    animController.transition(next);
  }
}

function eventReactionFor(msg) {
  var severity = eventSeverity(msg);
  if (msg.type === 'job_failed' || severity === 'error') {
    return { animation: 'failed', reactionMs: 1100, trayMs: 9000 };
  }
  if (msg.type === 'approval_needed') {
    return { animation: 'review', reactionMs: 950, trayMs: 0 };
  }
  if (msg.type === 'job_started') {
    return { animation: 'running', reactionMs: 700, trayMs: 0 };
  }
  if (msg.type === 'job_finished') {
    return { animation: 'jumping', reactionMs: 900, trayMs: 5000 };
  }
  if (msg.type === 'message_received') {
    return { animation: msg.urgent ? 'waving' : 'message_react', reactionMs: 850, trayMs: msg.urgent ? 8000 : 0 };
  }
  if (msg.type === 'daily_brief') {
    return { animation: 'waving', reactionMs: 750, trayMs: 6000 };
  }
  if (msg.type === 'status') {
    return { animation: severity === 'warning' ? 'review' : 'waiting', reactionMs: 650, trayMs: 0 };
  }
  return { animation: 'bubble_react', reactionMs: 850, trayMs: 0 };
}

function rememberStatus(msg) {
  if (msg.type === 'status') {
    state.currentStatus = eventText(msg);
  } else if (msg.type === 'job_started') {
    state.currentStatus = 'Working: ' + eventText(msg);
  } else if (msg.type === 'job_finished') {
    state.currentStatus = 'Done: ' + eventText(msg);
  } else if (msg.type === 'job_failed') {
    state.currentStatus = 'Needs attention: ' + eventText(msg);
  } else if (msg.type === 'approval_needed') {
    state.currentStatus = 'Waiting for approval';
  }
}

function handleAmbientEvent(msg) {
  rememberStatus(msg);
  recordRecentEvent(msg);
  var reaction = eventReactionFor(msg);
  transitionForEvent(msg);
  triggerReaction(reaction.reactionMs || 850);
  if (shouldShowEventBubble(msg)) {
    showBubble(bubbleTextForEvent(msg), msg.duration || 3800);
  }
  if (shouldShowEventTray(msg)) {
    setEventTrayVisible(true, reaction.trayMs || 6000);
  } else {
    renderRecentEvents();
  }
}

function shouldShowEventTray(msg) {
  if (msg.type === 'approval_needed' || msg.type === 'job_failed') return true;
  if (notificationPrefs.quiet_mode === 'silent' && !isCriticalEvent(msg)) return false;
  if (msg.urgent) return notificationPrefs.show_tray_on_urgent;
  if (msg.severity === 'warning') return notificationPrefs.show_tray_on_urgent;
  return eventReactionFor(msg).trayMs > 0 && notificationPrefs.quiet_mode === 'off';
}

// ---- Bounce on click ----
spriteEl.addEventListener('click', () => {
  if (dragMoved) {
    dragMoved = false;
    return;
  }
  if (recentEvents.length > 0 || state.currentStatus !== 'Idle') {
    setEventTrayVisible(eventTrayEl ? eventTrayEl.classList.contains('hidden') : true, 0);
    return;
  }
  setMood('happy');
  setTimeout(() => setMood(state.mood), 1800);
});

spriteEl.addEventListener('contextmenu', (event) => {
  event.preventDefault();
  event.stopPropagation();
  setEventTrayVisible(eventTrayEl ? eventTrayEl.classList.contains('hidden') : true, 0);
});

// ---- Window drag ----
const DEBUG_DRAG = new URLSearchParams(window.location.search).get('debugDrag') === '1';

function debugDrag(msg) {
  if (DEBUG_DRAG) console.log('[pet-drag] ' + msg);
}

function dragPoint(event) {
  return { screenX: event.screenX, screenY: event.screenY };
}

function spriteClientRect() {
  const rect = spriteEl.getBoundingClientRect();
  return {
    left: rect.left,
    top: rect.top,
    width: rect.width,
    height: rect.height,
  };
}

function dragEnabled() {
  return document.body.classList.contains('overlay-mode') &&
    window.hermesPetAPI &&
    !document.body.classList.contains('click-through-mode');
}

function startPetDrag(event) {
  if (!dragEnabled() || event.button !== 0) return;
  if (dragPointerId != null) finishPetDrag('stale-start', event, { force: true });

  event.preventDefault();
  event.stopPropagation();
  dragPointerId = event.pointerId ?? 'mouse';
  dragStart = dragPoint(event);
  dragMoved = false;
  _petDragging = true;
  spriteEl.classList.add('dragging', 'pet-dragging');
  animController.transition('drag');
  try {
    if (typeof event.pointerId === 'number') {
      spriteEl.setPointerCapture(event.pointerId);
      debugDrag('pointerdown id=' + event.pointerId + ' capture=ok');
    } else {
      spriteEl.setPointerCapture(1);
      debugDrag('pointerdown id=' + event.pointerId + ' capture=forced(1)');
    }
  } catch (e) {
    debugDrag('pointerdown id=' + event.pointerId + ' capture=FAIL ' + e.message);
  }
  window.hermesPetAPI.petDragStart({ ...dragStart, spriteRect: spriteClientRect() });
}

function movePetDrag(event) {
  if (dragPointerId == null || !dragStart) return;
  if (event.pointerId != null && dragPointerId !== event.pointerId) return;
  if (typeof event.buttons === 'number' && (event.buttons & 1) === 0) {
    finishPetDrag('move-without-button', event, { force: true });
    return;
  }

  event.preventDefault();
  event.stopPropagation();
  const point = dragPoint(event);
  if (Math.abs(point.screenX - dragStart.screenX) > 2 || Math.abs(point.screenY - dragStart.screenY) > 2) {
    dragMoved = true;
  }
  window.hermesPetAPI.petDragMove(point);
}

function endPetDrag(event) {
  finishPetDrag('end', event);
}

function finishPetDrag(reason, event, options = {}) {
  if (dragPointerId == null) return;
  if (!options.force && event && event.pointerId != null && dragPointerId !== event.pointerId) return;

  if (event) {
    event.preventDefault();
    event.stopPropagation();
  }

  var pid = (event && typeof event.pointerId === 'number') ? event.pointerId : null;
  var savedPointerId = dragPointerId;
  dragPointerId = null;
  dragStart = null;
  spriteEl.classList.remove('dragging', 'pet-dragging');
  _petDragging = false;

  try {
    if (pid != null) {
      if (!spriteEl.hasPointerCapture || spriteEl.hasPointerCapture(pid)) {
        spriteEl.releasePointerCapture(pid);
      }
      debugDrag(reason + ' id=' + pid + ' release=ok');
    } else if (typeof savedPointerId === 'number') {
      if (!spriteEl.hasPointerCapture || spriteEl.hasPointerCapture(savedPointerId)) {
        spriteEl.releasePointerCapture(savedPointerId);
      }
      debugDrag(reason + ' savedId=' + savedPointerId + ' release=ok');
    }
  } catch (e) {
    debugDrag(reason + ' release=FAIL ' + e.message);
  }

  if (animController.hoverActive) {
    animController.transition('hover');
  } else {
    animController.transition('idle');
  }
  debugDrag(reason + ' cleanup=ok');
  window.hermesPetAPI?.petDragEnd?.();
}

function recoverLostPointerCapture(event) {
  if (dragPointerId == null) return;
  if (event && event.pointerId != null && dragPointerId !== event.pointerId) return;
  if (typeof event?.buttons === 'number' && (event.buttons & 1) === 0) {
    finishPetDrag('lostcapture-button-up', event, { force: true });
    return;
  }
  try {
    if (typeof event?.pointerId === 'number') {
      spriteEl.setPointerCapture(event.pointerId);
      debugDrag('lostpointercapture id=' + event.pointerId + ' recapture=ok');
      return;
    }
  } catch (e) {
    debugDrag('lostpointercapture recapture=FAIL ' + e.message);
  }
  finishPetDrag('lostcapture-unrecoverable', event, { force: true });
}

spriteEl.addEventListener('pointerdown', startPetDrag);
spriteEl.addEventListener('pointerup', endPetDrag);
spriteEl.addEventListener('pointercancel', endPetDrag);
spriteEl.addEventListener('lostpointercapture', recoverLostPointerCapture);
document.addEventListener('pointermove', movePetDrag, true);
window.addEventListener('pointermove', movePetDrag, true);
document.addEventListener('pointerup', endPetDrag, true);
document.addEventListener('pointercancel', endPetDrag, true);
window.addEventListener('pointerup', endPetDrag, true);
window.addEventListener('mouseup', endPetDrag, true);
window.addEventListener('blur', endPetDrag);

// ---- Minimize ----
let isMinimized = false;
minBtn.addEventListener('click', () => {
  if (isMinimized) {
    window.hermesPetAPI?.restore?.();
    document.body.classList.remove('bubble-mode');
    isMinimized = false;
    minBtn.textContent = '−';
  } else {
    window.hermesPetAPI?.minimize?.();
    document.body.classList.add('bubble-mode');
    isMinimized = true;
    minBtn.textContent = '+';
  }
});

// ---- Event parser ----
function handleEvent(msg) {
  // msg schema from Python bridge:
  // { type: 'state', species, name, level, xp, xp_next, variant, shiny }
  // { type: 'mood_change', mood: 'idle'|'happy'|'thinking'|'busy' }
  // { type: 'bubble', text, duration }
  // { type: 'xp_change', delta, new_xp, new_level }
  // { type: 'hatch', species, name, variant, shiny }
  // { type: 'toggle_visible', visible: bool }

  debugEvent(`handle type=${msg?.type || 'unknown'}`, msg);

  switch (msg.type) {
    case 'hatch':
      state.species = msg.species;
      state.name = msg.name;
      state.variant = msg.variant || 'normal';
      state.shiny = msg.shiny || false;
      state.custom_pet = msg.custom_pet || null;
      state.level = 1;
      state.xp = 0;
      state.xpNext = 100;
      setSprite(state.species, state.variant);
      setShiny(state.shiny);
      updateStats();
      showBubble(`You hatched ${msg.name}!`, 4000);
      break;

    case 'state':
      Object.assign(state, msg);
      state.custom_pet = msg.custom_pet || null;
      state.xpNext = msg.xp_next || state.xpNext;
      setSprite(state.species, state.variant);
      setShiny(state.shiny);
      updateStats();
      break;

    case 'custom_pet':
      state.custom_pet = msg.custom_pet || null;
      setSprite(state.species || 'cat', state.variant);
      if (state.custom_pet) showBubble('Using custom pet ' + state.custom_pet.name, 2500);
      break;

    case 'notification_prefs':
      updateNotificationPrefs(msg.prefs || msg);
      break;

    case 'mood_change':
      state.mood = msg.mood;
      setMood(msg.mood);
      break;

    case 'bubble':
    case 'status':
    case 'job_started':
    case 'job_finished':
    case 'job_failed':
    case 'job_history':
    case 'approval_needed':
    case 'daily_brief':
      if (msg.type === 'job_history') recordJobHistory(msg);
      else handleAmbientEvent(msg);
      break;

    case 'xp_change':
      state.xp = msg.new_xp ?? state.xp;
      if (msg.new_level != null) state.level = msg.new_level;
      updateStats();
      if (msg.delta > 0) showBubble(`+${msg.delta} XP`, 2000);
      if (msg.delta > 0) animController.transition('jumping');
      break;

    case 'toggle_visible':
      if (msg.visible) {
        window.hermesPetAPI?.show?.();
      } else {
        window.hermesPetAPI?.hide?.();
      }
      break;

    case 'message_received':
      handleAmbientEvent(msg);
      break;
  }
}

// ---- Bridge listeners ----
if (window.hermesPetAPI) {
  window.hermesPetAPI.onPetEvent(handleEvent);
  window.hermesPetAPI.onBridgeConnected((connected) => {
    debugEvent(`bridge connected state=${connected}`);
    if (connectionStatusEl) {
      connectionStatusEl.textContent = connected ? 'Connected' : 'Waiting for Hermes';
      connectionStatusEl.classList.toggle('connected', connected);
    }
    if (connected) {
      if (animController.currentState === 'waiting') animController.transition('idle');
    } else {
      showBubble('Waiting for Hermes...', 4000);
      animController.transition('waiting');
    }
  });
}

// Default state: show idle empty until first event
setMood('idle');
nameEl.textContent = 'Hermes Pets';

// =====================================================================
// FEATURE F1: Custom sprite upload (drag & drop + right-click file picker)
// =====================================================================

const dropZone = document.getElementById('drop-zone');
const uploadHint = document.getElementById('upload-hint');
const uploadEnabled = new URLSearchParams(window.location.search).get('showUpload') === '1';

document.body.classList.toggle('show-upload-ui', uploadEnabled);

function setCustomSprite(filePath) {
  spriteEl.style.backgroundImage = `url("${filePath}")`;
  state.species = 'custom';
  state.variant = 'normal';
  showBubble('New custom sprite uploaded!', 3000);
}

if (uploadEnabled) {
  document.addEventListener('dragenter', (e) => {
    e.preventDefault();
    if (dropZone) dropZone.classList.remove('hidden');
  });

  document.addEventListener('dragover', (e) => {
    e.preventDefault();
    if (dropZone) dropZone.classList.add('drag-over');
  });

  document.addEventListener('dragleave', (e) => {
    if (e.relatedTarget && !document.body.contains(e.relatedTarget)) {
      if (dropZone) { dropZone.classList.remove('drag-over'); dropZone.classList.add('hidden'); }
    }
  });

  document.addEventListener('drop', (e) => {
    e.preventDefault();
    if (dropZone) { dropZone.classList.remove('drag-over'); dropZone.classList.add('hidden'); }
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      const file = files[0];
      if (file.type.startsWith('image/')) {
        const url = URL.createObjectURL(file);
        setCustomSprite(url);
        window.hermesPetAPI?.saveCustomSprite?.(file.path || file.name);
      } else {
        showBubble('Only image files, please!', 2000);
      }
    }
  });

  if (uploadHint) {
    uploadHint.addEventListener('click', (e) => {
      e.stopPropagation();
      window.hermesPetAPI?.pickCustomSprite?.();
    });
  }
}

// =====================================================================
// FEATURE F2: Idle time-based chat lines
// =====================================================================

const IDLE_LINES = [
  "I'm bored... let's code something cool!",
  "*stretches* Ready when you are!",
  "Type something, I'm watching...",
  "Did you know I level up when you work?",
  "*yawns* This terminal is cozy.",
  "Waiting for wisdom...",
  "Pet me! Click me!",
  "I wonder what we'll build next...",
  "Your terminal history smells like ambition.",
  "*whispers* Use the tools...",
];

let idleTimer = null;
let idleInterval = 45000;

function resetIdleTimer() {
  if (idleTimer) clearTimeout(idleTimer);
  idleTimer = setTimeout(() => {
    if (notificationPrefs.show_idle_bubbles && notificationPrefs.quiet_mode === 'off' && !mutedNow()) {
      const line = IDLE_LINES[Math.floor(Math.random() * IDLE_LINES.length)];
      showBubble(line, 4000);
    }
    idleInterval = Math.min(idleInterval * 1.5, 300000);
    resetIdleTimer();
  }, idleInterval);
}

// Wrap existing handleEvent to also reset idle timer
const _origHandleEvent = handleEvent;
handleEvent = function(msg) {
  _origHandleEvent(msg);
  idleInterval = 45000;
  resetIdleTimer();
};

document.addEventListener('mousemove', () => {
  idleInterval = 45000;
  resetIdleTimer();
});

resetIdleTimer();

animController.loadManifest().then(function() {
  if (!DEBUG_ANIM) animController._removeDebugOverlay();
  if (!animController.manifest) return;

  // Bootstrap: if HERMES_PET_SPECIES was passed as a query param,
  // show the sprite immediately without waiting for bridge state.
  var qsSpecies = new URLSearchParams(window.location.search).get('species') || 'cat';
  if (qsSpecies && !animController.species) {
    setSprite(qsSpecies);
    return;
  }

  if (animController.species) {
    animController.init(animController.species);
  }
});

if (DEBUG_EVENTS || new URLSearchParams(window.location.search).get('debugSmoke') === '1') {
  window.__hermesPetRendererSmoke = {
    handleEvent: handleEvent,
    getState: function() { return { ...state }; },
    getRecentEvents: function() { return recentEvents.slice(); },
    getNotificationPrefs: function() { return { ...notificationPrefs }; },
    getCurrentAnimation: function() { return animController.currentState; },
    isTrayVisible: function() { return !!eventTrayEl && !eventTrayEl.classList.contains('hidden'); },
    isTrayAttention: function() { return !!eventTrayEl && eventTrayEl.classList.contains('attention'); },
    getBubbleText: function() { return bubbleTextEl ? bubbleTextEl.textContent : ''; }
  };
}
