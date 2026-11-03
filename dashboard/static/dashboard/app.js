(() => {
  const root = document.documentElement;
  const sidebarToggle = document.getElementById('sidebar-toggle');
  const profileTrigger = document.getElementById('profile-trigger');
  const profileMenu = document.getElementById('profile-menu');
  const themeButtons = document.querySelectorAll('[data-theme-choice]');

  function save(key, value) {
    try { localStorage.setItem(key, value); } catch (error) { /* Keep this session usable. */ }
  }

  function updateSidebarLabel() {
    const collapsed = root.classList.contains('sidebar-collapsed');
    const label = collapsed ? 'Развернуть меню' : 'Свернуть меню';
    sidebarToggle.setAttribute('aria-expanded', String(!collapsed));
    sidebarToggle.setAttribute('aria-label', label);
    sidebarToggle.title = label;
  }
  updateSidebarLabel();
  sidebarToggle.addEventListener('click', () => {
    root.classList.toggle('sidebar-collapsed');
    save('finstat-sidebar', root.classList.contains('sidebar-collapsed') ? 'collapsed' : 'expanded');
    updateSidebarLabel();
  });

  function closeProfileMenu() {
    profileMenu.hidden = true;
    profileTrigger.setAttribute('aria-expanded', 'false');
  }
  profileTrigger.addEventListener('click', () => {
    const opening = profileMenu.hidden;
    profileMenu.hidden = !opening;
    profileTrigger.setAttribute('aria-expanded', String(opening));
    if (opening) profileMenu.querySelector('a').focus();
  });
  document.addEventListener('click', (event) => {
    if (!profileTrigger.contains(event.target) && !profileMenu.contains(event.target)) closeProfileMenu();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !profileMenu.hidden) {
      closeProfileMenu();
      profileTrigger.focus();
    }
  });

  function syncThemeButtons() {
    themeButtons.forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.themeChoice === root.dataset.theme));
    });
  }
  syncThemeButtons();
  themeButtons.forEach(button => button.addEventListener('click', () => {
    root.dataset.theme = button.dataset.themeChoice;
    save('finstat-theme', root.dataset.theme);
    syncThemeButtons();
  }));

  const deductionTriggers = document.querySelectorAll('.deduction-trigger');
  let activeDeduction = null;

  function closeDeduction(restoreFocus = false) {
    if (!activeDeduction) return;
    const { button, panel, cell } = activeDeduction;
    panel.hidden = true;
    panel.removeAttribute('style');
    cell.appendChild(panel);
    button.setAttribute('aria-expanded', 'false');
    activeDeduction = null;
    if (restoreFocus) button.focus();
  }

  function placeDeduction() {
    if (!activeDeduction) return;
    const { button, panel } = activeDeduction;
    const rect = button.getBoundingClientRect();
    const margin = 12;
    const gap = 8;
    if (rect.bottom < 0 || rect.top > window.innerHeight || rect.right < 0 || rect.left > window.innerWidth) {
      closeDeduction();
      return;
    }
    const width = Math.min(390, window.innerWidth - margin * 2);
    panel.style.width = `${width}px`;
    const height = panel.getBoundingClientRect().height;
    const left = Math.max(margin, Math.min(rect.left, window.innerWidth - width - margin));
    const below = rect.bottom + gap;
    const above = rect.top - height - gap;
    const top = below + height <= window.innerHeight - margin
      ? below
      : above >= margin ? above : Math.max(margin, window.innerHeight - height - margin);
    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
  }

  deductionTriggers.forEach(button => button.addEventListener('click', () => {
    if (activeDeduction?.button === button) {
      closeDeduction();
      return;
    }
    closeDeduction();
    const panel = document.getElementById(button.getAttribute('aria-controls'));
    const cell = panel.parentElement;
    document.body.appendChild(panel);
    panel.hidden = false;
    button.setAttribute('aria-expanded', 'true');
    activeDeduction = { button, panel, cell };
    placeDeduction();
  }));
  document.addEventListener('click', event => {
    if (activeDeduction && !activeDeduction.button.contains(event.target) && !activeDeduction.panel.contains(event.target)) {
      closeDeduction();
    }
  });
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape' && activeDeduction) closeDeduction(true);
  });
  window.addEventListener('scroll', placeDeduction, true);
  window.addEventListener('resize', placeDeduction);

  const detailStatus = document.querySelector('[data-status-url]');
  if (detailStatus) {
    const checkStatus = async () => {
      try {
        const response = await fetch(detailStatus.dataset.statusUrl);
        if (!response.ok) return;
        const status = await response.json();
        if (status.complete || status.error) window.location.reload();
      } catch (error) { /* Try again on the next poll. */ }
    };
    window.setInterval(checkStatus, 10000);
  }
})();
