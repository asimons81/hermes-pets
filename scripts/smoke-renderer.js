#!/usr/bin/env node
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const repoRoot = path.resolve(__dirname, '..');
const overlayDir = path.resolve(process.argv[2] || path.join(repoRoot, 'src/hermes_pet/overlay'));
const rendererPath = path.join(overlayDir, 'src/renderer.js');
const manifestPath = path.join(overlayDir, 'assets/manifest.json');

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

class FakeClassList {
  constructor(initial = []) {
    this.values = new Set(initial);
  }

  add(...names) {
    names.forEach((name) => this.values.add(name));
  }

  remove(...names) {
    names.forEach((name) => this.values.delete(name));
  }

  contains(name) {
    return this.values.has(name);
  }

  toggle(name, force) {
    const next = force === undefined ? !this.values.has(name) : !!force;
    if (next) this.values.add(name);
    else this.values.delete(name);
    return next;
  }
}

function makeElement(id = '') {
  const initialClasses = [];
  if (['pet-bubble', 'event-tray', 'pet-stats', 'drop-zone', 'upload-hint'].includes(id)) {
    initialClasses.push('hidden');
  }
  if (id === 'pet-sprite') initialClasses.push('sprite', 'idle');
  return {
    id,
    style: {},
    children: [],
    classList: new FakeClassList(initialClasses),
    textContent: '',
    offsetWidth: 120,
    addEventListener() {},
    appendChild(child) {
      this.children.push(child);
      return child;
    },
    remove() {},
    setPointerCapture() {},
    releasePointerCapture() {},
    hasPointerCapture() {
      return true;
    },
    getBoundingClientRect() {
      return { left: 40, top: 40, width: 160, height: 160 };
    },
    set innerHTML(value) {
      this.textContent = String(value || '');
    },
    get innerHTML() {
      return this.textContent;
    },
  };
}

function makeDocument() {
  const elements = new Map();
  const document = {
    body: makeElement('body'),
    addEventListener() {},
    createElement(tag) {
      const el = makeElement(tag);
      el.tagName = tag.toUpperCase();
      return el;
    },
    getElementById(id) {
      if (!elements.has(id)) {
        elements.set(id, makeElement(id));
      }
      return elements.get(id);
    },
  };
  return document;
}

async function flush() {
  await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  await Promise.resolve();
}

async function main() {
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));
  const renderer = fs.readFileSync(rendererPath, 'utf8');
  const bridgeCallbacks = { events: null, connected: null };
  const document = makeDocument();
  const context = {
    console,
    document,
    Image: class {
      set src(value) {
        this._src = value;
        if (this.onload) queueMicrotask(() => this.onload());
      }
      get src() {
        return this._src;
      }
    },
    URL,
    URLSearchParams,
    setTimeout() {
      return 1;
    },
    clearTimeout() {},
    setInterval() {
      return 1;
    },
    clearInterval() {},
    fetch() {
      throw new Error('fetch should not be used when IPC manifest is present');
    },
    window: {
      location: { search: '?debugSmoke=1&species=cat' },
      addEventListener() {},
      hermesPetAPI: {
        loadManifest: () => manifest,
        onPetEvent: (callback) => {
          bridgeCallbacks.events = callback;
        },
        onBridgeConnected: (callback) => {
          bridgeCallbacks.connected = callback;
        },
        show() {},
        hide() {},
        minimize() {},
        restore() {},
        petDragStart() {},
        petDragMove() {},
        petDragEnd() {},
      },
    },
  };
  context.globalThis = context;

  vm.runInNewContext(renderer, context, { filename: rendererPath });
  await flush();

  const smoke = context.window.__hermesPetRendererSmoke;
  assert(smoke, 'renderer smoke API was not exposed');
  assert(typeof bridgeCallbacks.events === 'function', 'pet event listener was not registered');
  assert(typeof bridgeCallbacks.connected === 'function', 'bridge connection listener was not registered');
  assert(smoke.getCurrentAnimation() === 'idle', 'startup should render idle animation');

  smoke.handleEvent({ type: 'state', species: 'cat', name: 'Miso', level: 2, xp: 30, xp_next: 100 });
  await flush();
  assert(smoke.getState().name === 'Miso', 'state event should update pet name');
  assert(document.getElementById('pet-sprite').style.backgroundImage.includes('/cat/idle/'), 'built-in cat sprite should be visible');

  bridgeCallbacks.connected(false);
  await flush();
  assert(smoke.getCurrentAnimation() === 'waiting', 'disconnect should transition to waiting');
  bridgeCallbacks.connected(true);
  await flush();
  assert(smoke.getCurrentAnimation() === 'idle', 'reconnect should return waiting pet to idle');

  smoke.handleEvent({
    type: 'notification_prefs',
    prefs: { notification_profile: 'focus', quiet_mode: 'important', show_idle_bubbles: false },
  });
  assert(smoke.getNotificationPrefs().notification_profile === 'focus', 'profile should normalize through renderer prefs');
  assert(smoke.getNotificationPrefs().quiet_mode === 'important', 'quiet profile should be active');

  smoke.handleEvent({ type: 'job_started', text: 'Tests', id: 'job-1' });
  await flush();
  assert(smoke.getCurrentAnimation() === 'running', 'job_started should animate running');

  smoke.handleEvent({ type: 'job_failed', text: 'Tests failed', id: 'job-2', exit_code: 7 });
  await flush();
  assert(smoke.getCurrentAnimation() === 'failed', 'job_failed should animate failed');
  assert(smoke.isTrayVisible(), 'job_failed should open the activity tray');
  assert(smoke.isTrayAttention(), 'job_failed should mark the tray as attention state');
  assert(smoke.getBubbleText().includes('Failed:'), 'job_failed should show a critical bubble');

  smoke.handleEvent({ type: 'message_received', source: 'telegram', sender: 'Ada', text: 'Can you review?', urgent: true });
  await flush();
  assert(smoke.getRecentEvents()[0].group === 'messages', 'message events should be grouped for tray scanning');

  smoke.handleEvent({
    type: 'state',
    species: 'cat',
    name: 'Custom',
    custom_pet: {
      name: 'spark',
      path: '/tmp/hermes-pet-smoke',
      manifest: { states: { idle: { fps: 1, frames: ['idle_00.png'] } } },
    },
  });
  await flush();
  assert(
    document.getElementById('pet-sprite').style.backgroundImage.includes('/tmp/hermes-pet-smoke/sprites/idle/idle_00.png'),
    'selected custom pet should load its idle frame'
  );

  smoke.handleEvent({ type: 'state', species: 'cat', name: 'Fallback', custom_pet: { name: 'bad' } });
  await flush();
  assert(document.getElementById('pet-sprite').style.backgroundImage.includes('/cat/idle/'), 'invalid custom pet should fall back to built-in sprite');

  console.log('renderer smoke ok');
}

main().catch((error) => {
  console.error(error.stack || error.message);
  process.exit(1);
});
