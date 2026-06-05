const { app } = require('electron');
const childProcess = require('child_process');
const fs = require('fs');
const net = require('net');
const os = require('os');
const path = require('path');

const port = Number.parseInt(process.env.HERMES_PET_PORT || '17473', 10);
const resourcesPath = process.resourcesPath || __dirname;
const overlayDir = process.env.HERMES_PET_INSTALLED_OVERLAY_DIR
  || path.join(resourcesPath, 'overlay');
const nodeModulesDir = path.join(resourcesPath, 'app', 'node_modules');

let bridgeProcess = null;

function localAppDataPath(...parts) {
  return path.join(
    process.env.LOCALAPPDATA || path.join(os.homedir(), 'AppData', 'Local'),
    ...parts,
  );
}

function bridgeExecutable() {
  const candidates = [
    process.env.HERMES_PET_BRIDGE_EXE,
    path.join(resourcesPath, 'bin', 'hermes-pet-bridge.exe'),
    path.join(path.dirname(process.execPath), 'bin', 'hermes-pet-bridge.exe'),
    path.join(__dirname, 'staging', 'bin', 'hermes-pet-bridge.exe'),
  ].filter(Boolean);
  return candidates.find((candidate) => fs.existsSync(candidate)) || '';
}

function bridgeAvailable() {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: '127.0.0.1', port });
    const done = (available) => {
      socket.removeAllListeners();
      socket.destroy();
      resolve(available);
    };
    socket.setTimeout(500);
    socket.once('connect', () => done(true));
    socket.once('timeout', () => done(false));
    socket.once('error', () => done(false));
  });
}

async function startBridgeIfNeeded() {
  if (await bridgeAvailable()) return;

  const exe = bridgeExecutable();
  if (!exe) {
    console.warn('[hermes-pets] bundled bridge executable not found; overlay will retry bridge connection');
    return;
  }

  bridgeProcess = childProcess.spawn(exe, ['--serve', '--port', String(port)], {
    detached: false,
    stdio: 'ignore',
    windowsHide: true,
    env: {
      ...process.env,
      HERMES_PET_PORT: String(port),
      HERMES_PET_HOST: '127.0.0.1',
    },
  });
}

async function boot() {
  process.env.HERMES_PET_PORT = String(port);
  process.env.HERMES_PET_WS_URL = process.env.HERMES_PET_WS_URL || `ws://127.0.0.1:${port}`;
  process.env.HERMES_PET_INSTALLED_OVERLAY_DIR = overlayDir;
  process.env.HERMES_PET_WINDOWS_APP_EXE = process.execPath;
  process.env.HERMES_PET_WINDOWS_NODE_MODULES = nodeModulesDir;
  process.env.HERMES_PET_POSITION_FILE = process.env.HERMES_PET_POSITION_FILE
    || localAppDataPath('HermesAgent', 'pet-overlay-electron', 'overlay-position.json');

  await startBridgeIfNeeded();
  require(path.join(overlayDir, 'src', 'main.windows.js'));
}

app.on('before-quit', () => {
  if (bridgeProcess && !bridgeProcess.killed) {
    bridgeProcess.kill();
  }
});

boot().catch((error) => {
  console.error('[hermes-pets] failed to boot desktop app:', error);
  app.exit(1);
});
