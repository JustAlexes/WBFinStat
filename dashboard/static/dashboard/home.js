(() => {
  const stage = document.querySelector('[data-kinetic-stage]');
  if (!stage) return;
  const canvas = stage.querySelector('canvas');
  const context = canvas.getContext('2d');
  if (!context) return;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const pointer = { x: 0, y: 0, active: false, down: false };
  const impulse = stage.querySelector('.kinetic-impulse');
  let width = 0;
  let height = 0;
  let particles = [];
  let frame = 0;
  let previousTime = 0;
  let visible = true;
  const ambient = Array.from({ length: 42 }, () => ({
    x: Math.random(), y: Math.random(), phase: Math.random() * Math.PI * 2,
  }));

  function paint(time = 0) {
    const step = Math.min((time - previousTime) / 16.67 || 1, 2);
    previousTime = time;
    context.clearRect(0, 0, width, height);
    const glowX = pointer.active ? pointer.x : width * .5;
    const glowY = pointer.active ? pointer.y : height * .47;
    const glow = context.createRadialGradient(glowX, glowY, 0, glowX, glowY, width * .42);
    glow.addColorStop(0, 'rgba(112, 87, 255, .16)');
    glow.addColorStop(1, 'rgba(112, 87, 255, 0)');
    context.fillStyle = glow;
    context.fillRect(0, 0, width, height);
    context.lineWidth = 1;
    ambient.forEach((point, index) => {
      const drift = motion.matches ? 0 : Math.sin(time * .00025 + point.phase) * 14;
      const x = point.x * width + drift;
      const y = 68 + point.y * (height - 136);
      context.fillStyle = 'rgba(179, 172, 255, .32)';
      context.fillRect(x, y, 1.5, 1.5);
      const other = ambient[index + 1];
      if (other && Math.hypot(x - other.x * width, y - (68 + other.y * (height - 136))) < 115) {
        context.strokeStyle = 'rgba(164, 150, 255, .07)';
        context.beginPath();
        context.moveTo(x, y);
        context.lineTo(other.x * width, 68 + other.y * (height - 136));
        context.stroke();
      }
    });
    context.font = '9px monospace';
    particles.forEach((particle, index) => {
      if (!motion.matches) {
        particle.vx += (particle.homeX - particle.x) * .025 * step;
        particle.vy += (particle.homeY - particle.y) * .025 * step;
        if (pointer.active) {
          const dx = particle.x - pointer.x;
          const dy = particle.y - pointer.y;
          const distance = Math.hypot(dx, dy) || 1;
          const radius = Math.min(150, width * .25);
          if (distance < radius) {
            const force = (1 - distance / radius) * (pointer.down ? -1.4 : 3.8) * step;
            particle.vx += dx / distance * force;
            particle.vy += dy / distance * force;
          }
        }
        particle.vx *= Math.pow(.87, step);
        particle.vy *= Math.pow(.87, step);
        particle.x += particle.vx * step;
        particle.y += particle.vy * step;
      }
      const displaced = Math.hypot(particle.x - particle.homeX, particle.y - particle.homeY);
      context.fillStyle = displaced > 16 ? '#67e4e0' : particle.color;
      if (displaced > 12 && index % 7 === 0) {
        context.fillText(String(index % 10), particle.x, particle.y);
      } else {
        context.fillRect(particle.x, particle.y, particle.size, particle.size);
      }
    });
  }

  function animate(time) {
    frame = 0;
    paint(time);
    if (!motion.matches && visible && !document.hidden) frame = requestAnimationFrame(animate);
  }

  function start() {
    if (!frame && !document.hidden && visible) {
      previousTime = performance.now();
      frame = requestAnimationFrame(animate);
    }
  }

  function resize() {
    const bounds = stage.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    width = bounds.width;
    height = bounds.height;
    const ratio = Math.min(window.devicePixelRatio || 1, 2);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    const sample = document.createElement('canvas');
    sample.width = Math.ceil(width);
    sample.height = Math.ceil(height);
    const ink = sample.getContext('2d', { willReadFrequently: true });
    if (!ink) return;
    const fontSize = Math.min(178, width * .22);
    ink.font = `800 ${fontSize}px Arial, sans-serif`;
    ink.textAlign = 'center';
    ink.textBaseline = 'middle';
    ink.fillStyle = '#fff';
    ink.fillText('FinStat', width / 2, height * .47);
    const data = ink.getImageData(0, 0, sample.width, sample.height).data;
    const spacing = width < 500 ? 4 : 5;
    const points = [];
    for (let y = 0; y < sample.height; y += spacing) {
      for (let x = 0; x < sample.width; x += spacing) {
        if (data[(y * sample.width + x) * 4 + 3] > 110) {
          points.push({ homeX: x, homeY: y,
            x: motion.matches ? x : x + (Math.random() - .5) * 150,
            y: motion.matches ? y : y + (Math.random() - .5) * 150,
            vx: 0, vy: 0, size: width < 500 ? 1.8 : 2.4,
            color: `hsl(${248 - x / width * 32}, ${65 + x / width * 20}%, ${85 - x / width * 10}%)`,
          });
        }
      }
    }
    particles = points;
    stage.classList.add('is-ready');
    paint();
    start();
  }

  stage.addEventListener('pointermove', event => {
    if (event.pointerType === 'touch' || motion.matches) return;
    const bounds = stage.getBoundingClientRect();
    pointer.x = event.clientX - bounds.left;
    pointer.y = event.clientY - bounds.top;
    pointer.active = true;
  });
  stage.addEventListener('pointerdown', event => {
    if (!event.target.closest('button')) pointer.down = true;
  });
  stage.addEventListener('pointerleave', () => { pointer.active = pointer.down = false; });
  window.addEventListener('pointerup', () => { pointer.down = false; });
  impulse.addEventListener('click', () => {
    if (motion.matches) return;
    pointer.active = false;
    particles.forEach(particle => {
      const angle = Math.atan2(particle.homeY - height * .47, particle.homeX - width * .5);
      const speed = 9 + Math.random() * 15;
      particle.vx += Math.cos(angle) * speed;
      particle.vy += Math.sin(angle) * speed;
    });
    start();
  });
  function motionChanged() {
    if (motion.matches) {
      particles.forEach(p => { p.x = p.homeX; p.y = p.homeY; p.vx = p.vy = 0; });
    }
    impulse.disabled = motion.matches;
    impulse.title = motion.matches ? 'Уменьшение движения включено в настройках системы' : '';
    start();
  }
  motion.addEventListener('change', motionChanged);
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
    else start();
  });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      if (visible) start();
      else if (frame) { cancelAnimationFrame(frame); frame = 0; }
    }).observe(stage);
  }
  if ('ResizeObserver' in window) new ResizeObserver(resize).observe(stage);
  else window.addEventListener('resize', resize);
  try { resize(); motionChanged(); } catch (error) {
    stage.classList.remove('is-ready');
    if (frame) cancelAnimationFrame(frame);
  }
})();
