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
})();
