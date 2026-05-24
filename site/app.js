const yearEl = document.querySelector('[data-year]');
const toast = document.querySelector('.toast');
const navLinks = [...document.querySelectorAll('.topnav a[href^="#"]')];
const sections = navLinks
  .map((link) => document.querySelector(link.getAttribute('href')))
  .filter(Boolean);
const tabs = [...document.querySelectorAll('.tab-button')];
const panels = [...document.querySelectorAll('[data-panel]')];
const copyButtons = [...document.querySelectorAll('[data-copy-target]')];

function showToast(message) {
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('is-visible');
  window.clearTimeout(showToast.timer);
  showToast.timer = window.setTimeout(() => toast.classList.remove('is-visible'), 1800);
}

function setActiveSection(id) {
  navLinks.forEach((link) => {
    const active = link.getAttribute('href') === `#${id}`;
    link.classList.toggle('is-active', active);
    if (active) {
      link.setAttribute('aria-current', 'page');
    } else {
      link.removeAttribute('aria-current');
    }
  });
}

if ('IntersectionObserver' in window && sections.length) {
  const observer = new IntersectionObserver((entries) => {
    const visible = entries
      .filter((entry) => entry.isIntersecting)
      .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];

    if (visible?.target?.id) {
      setActiveSection(visible.target.id);
    }
  }, {
    rootMargin: '-20% 0px -60% 0px',
    threshold: [0.12, 0.3, 0.5, 0.7],
  });

  sections.forEach((section) => observer.observe(section));
}

function activateTab(tabName) {
  tabs.forEach((tab) => {
    const active = tab.dataset.tab === tabName;
    tab.classList.toggle('is-active', active);
    tab.setAttribute('aria-selected', active ? 'true' : 'false');
    tab.tabIndex = active ? 0 : -1;
  });

  panels.forEach((panel) => {
    const active = panel.dataset.panel === tabName;
    panel.classList.toggle('is-active', active);
    panel.hidden = !active;
  });
}

tabs.forEach((tab) => {
  tab.addEventListener('click', () => activateTab(tab.dataset.tab));
});

copyButtons.forEach((button) => {
  button.addEventListener('click', async () => {
    const targetId = button.dataset.copyTarget;
    const code = document.getElementById(targetId)?.innerText?.trim();
    if (!code) return;

    try {
      await navigator.clipboard.writeText(code);
      showToast('Copied commands to clipboard');
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = code;
      textarea.setAttribute('readonly', 'true');
      textarea.style.position = 'fixed';
      textarea.style.left = '-9999px';
      document.body.appendChild(textarea);
      textarea.select();
      const success = document.execCommand('copy');
      document.body.removeChild(textarea);
      showToast(success ? 'Copied commands to clipboard' : 'Copy failed, select manually');
    }
  });
});

activateTab('users');

if (yearEl) {
  yearEl.textContent = String(new Date().getFullYear());
}

window.addEventListener('load', () => {
  document.documentElement.classList.add('ready');
});
