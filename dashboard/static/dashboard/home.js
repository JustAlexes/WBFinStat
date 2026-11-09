(() => {
  const glow = document.querySelector('[data-cursor-glow]');
  const surface = glow?.closest('.workspace-home');
  if (!surface) return;
  let frame = 0;
  let clientX = 0;
  let clientY = 0;

  function update() {
    frame = 0;
    const bounds = surface.getBoundingClientRect();
    surface.style.setProperty('--cursor-x', `${clientX - bounds.left}px`);
    surface.style.setProperty('--cursor-y', `${clientY - bounds.top}px`);
  }

  function hide() {
    surface.classList.remove('has-cursor');
    if (frame) cancelAnimationFrame(frame);
    frame = 0;
  }

  surface.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch') return;
    clientX = event.clientX;
    clientY = event.clientY;
    surface.classList.add('has-cursor');
    if (!frame) frame = requestAnimationFrame(update);
  });
  surface.addEventListener('pointerleave', hide);
  window.addEventListener('blur', hide);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) hide();
  });
})();
