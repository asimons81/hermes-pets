// Constants and Elements
const yearEl = document.querySelector('[data-year]');
const toast = document.querySelector('.toast');
const tabs = [...document.querySelectorAll('.tab-button')];
const panels = [...document.querySelectorAll('[data-panel]')];
const copyButtons = [...document.querySelectorAll('[data-copy-target]')];
const tabGlider = document.getElementById('tab-glider');
const sandbox = document.getElementById('desktop-sandbox');
const draggablePets = [...document.querySelectorAll('.draggable-pet')];
const revealElements = [...document.querySelectorAll('.reveal')];

// 1. Toast Notifications
function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('is-visible');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove('is-visible'), 2000);
}

// 2. Scroll-Triggered Reveal Animations
if ('IntersectionObserver' in window && revealElements.length) {
  const revealObserver = new IntersectionObserver((entries) => {
    entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add('revealed');
        revealObserver.unobserve(entry.target); // Reveal only once
      }
    });
  }, {
    root: null,
    rootMargin: '0px 0px -10% 0px',
    threshold: 0.05,
  });

  revealElements.forEach((el) => revealObserver.observe(el));
}

// 3. Tab Navigation & Glider Animation
function updateTabGlider(activeTab) {
  if (!tabGlider || !activeTab) return;
  tabGlider.style.left = `${activeTab.offsetLeft}px`;
  tabGlider.style.width = `${activeTab.offsetWidth}px`;
}

function activateTab(tabName) {
  const activeTab = tabs.find((tab) => tab.dataset.tab === tabName);
  if (!activeTab) return;

  tabs.forEach((tab) => {
    const active = tab === activeTab;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.tabIndex = active ? 0 : -1;
  });

  panels.forEach((panel) => {
    const active = panel.dataset.panel === tabName;
    panel.classList.toggle('is-active', active);
    panel.hidden = !active;
  });

  updateTabGlider(activeTab);
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => activateTab(tab.dataset.tab));
});

// Resize listener to keep tab glider aligned
window.addEventListener('resize', () => {
  const activeTab = tabs.find((tab) => tab.classList.contains('is-active'));
  if (activeTab) updateTabGlider(activeTab);
});

// 4. Draggable Companion Pet Physics & Interaction
draggablePets.forEach((pet) => {
  let isDragging = false;
  let startX = 0, startY = 0;
  let currentX = 0, currentY = 0;
  let velocityY = 0;
  let gravityTimer = null;
  const bubble = pet.querySelector('.pet-bubble');
  const sprite = pet.querySelector('.pet-sprite');

  // Parse initial inline styles (percents or pixels)
  const rect = pet.getBoundingClientRect();
  const sandboxRect = sandbox.getBoundingClientRect();
  currentX = rect.left - sandboxRect.left;
  currentY = rect.top - sandboxRect.top;

  // Toggle Speech Bubble
  function showBubble() {
    if (!bubble) return;
    bubble.classList.add('is-active');
    window.clearTimeout(showBubble.timer);
    showBubble.timer = window.setTimeout(() => bubble.classList.remove('is-active'), 4000);
  }

  // Double click or tap wakes up the pet
  pet.addEventListener('dblclick', (e) => {
    e.stopPropagation();
    showBubble();
  });

  // Drag Event Handlers
  function onDragStart(clientX, clientY) {
    isDragging = true;
    pet.classList.add('is-dragging');
    window.cancelAnimationFrame(gravityTimer);

    const sRect = sandbox.getBoundingClientRect();
    startX = clientX - (pet.offsetLeft);
    startY = clientY - (pet.offsetTop);

    showBubble();
  }

  function onDragMove(clientX, clientY) {
    if (!isDragging) return;

    const sRect = sandbox.getBoundingClientRect();
    let newX = clientX - startX;
    let newY = clientY - startY;

    // Bounds checking
    const petW = pet.offsetWidth;
    const petH = pet.offsetHeight;
    if (newX < 0) newX = 0;
    if (newX > sRect.width - petW) newX = sRect.width - petW;
    if (newY < 0) newY = 0;
    if (newY > sRect.height - petH) newY = sRect.height - petH;

    currentX = newX;
    currentY = newY;

    pet.style.left = `${newX}px`;
    pet.style.top = `${newY}px`;
  }

  function onDragEnd() {
    if (!isDragging) return;
    isDragging = false;
    pet.classList.remove('is-dragging');

    // Run gravity fall simulation
    applyPhysics();
  }

  // Physics Gravity Fall & Spring Bounce
  function applyPhysics() {
    const sRect = sandbox.getBoundingClientRect();
    const floorY = sRect.height - pet.offsetHeight - 16; // 16px padding from taskbar bottom
    const bounceStrength = 0.45; // Energy retained on bounce
    const gravity = 0.8; // Acceleration

    velocityY = 0;

    function frame() {
      if (isDragging) return;

      velocityY += gravity;
      currentY += velocityY;

      // Check collision with floor
      if (currentY >= floorY) {
        currentY = floorY;
        velocityY = -velocityY * bounceStrength;

        // Stop updates when bounce velocity is negligible
        if (Math.abs(velocityY) < 1.5) {
          currentY = floorY;
          pet.style.top = `${currentY}px`;
          return;
        }
      }

      pet.style.top = `${currentY}px`;
      gravityTimer = window.requestAnimationFrame(frame);
    }

    gravityTimer = window.requestAnimationFrame(frame);
  }

  // Mouse Listeners
  pet.addEventListener('mousedown', (e) => {
    if (e.button !== 0) return; // Left click only
    e.preventDefault();
    onDragStart(e.clientX, e.clientY);

    const onMouseMove = (moveEvent) => onDragMove(moveEvent.clientX, moveEvent.clientY);
    const onMouseUp = () => {
      onDragEnd();
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
    };

    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
  });

  // Touch Listeners (Mobile Friendly)
  pet.addEventListener('touchstart', (e) => {
    if (e.touches.length !== 1) return;
    onDragStart(e.touches[0].clientX, e.touches[0].clientY);

    const onTouchMove = (moveEvent) => {
      if (moveEvent.touches.length !== 1) return;
      onDragMove(moveEvent.touches[0].clientX, moveEvent.touches[0].clientY);
    };

    const onTouchEnd = () => {
      onDragEnd();
      document.removeEventListener('touchmove', onTouchMove);
      document.removeEventListener('touchend', onTouchEnd);
    };

    document.addEventListener('touchmove', onTouchMove, { passive: true });
    document.addEventListener('touchend', onTouchEnd);
  });

  // Set up initial gravity fall to place them on taskbar
  applyPhysics();
});

// 5. Secure Command Copy to Clipboard
copyButtons.forEach((button) => {
  button.addEventListener('click', async () => {
    const targetId = button.dataset.copyTarget;
    const codeEl = document.getElementById(targetId);
    if (!codeEl) return;
    
    // Read code safely as textContent to avoid HTML tags
    const codeText = codeEl.textContent.trim();
    if (!codeText) return;

    try {
      await navigator.clipboard.writeText(codeText);
      showToast('Commands copied to clipboard');
      
      // Visual button feedback
      const originalText = button.textContent;
      button.textContent = 'Copied!';
      button.style.borderColor = 'var(--accent-blue)';
      button.style.color = 'var(--accent-blue)';
      
      window.setTimeout(() => {
        button.textContent = originalText;
        button.style.borderColor = '';
        button.style.color = '';
      }, 1500);
    } catch (err) {
      showToast('Copy failed, select manually');
    }
  });
});

// 6. Init Active Tab & Current Year
activateTab('users');

if (yearEl) {
  yearEl.textContent = String(new Date().getFullYear());
}

window.addEventListener('load', () => {
  document.documentElement.classList.add('ready');
});
