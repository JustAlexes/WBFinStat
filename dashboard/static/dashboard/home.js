(() => {
  const canvas = document.querySelector('[data-landscape-canvas]');
  if (!canvas) return;
  const workspace = canvas.closest('.workspace-home');
  const context = canvas.getContext('2d');
  if (!context || !workspace) return;
  const motion = window.matchMedia('(prefers-reduced-motion: reduce)');
  const button = workspace.querySelector('.landscape-impulse');
  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0, strength: 0, active: false, down: false };
  const waves = [];
  let width = 0;
  let height = 0;
  let columns = 76;
  let rows = 44;
  let frame = 0;
  let lastPaint = -Infinity;
  let elapsed = 0;
  let previousTime = 0;
  let visible = true;
  const stars = Array.from({ length: 68 }, () => ({
    x: Math.random(), y: Math.random(), size: .4 + Math.random() * 1.3,
    phase: Math.random() * Math.PI * 2,
  }));

  function addWave(x, y) {
    if (motion.matches) return;
    waves.push({ x, y, born: elapsed });
    if (waves.length > 6) waves.shift();
    start();
  }

  function project(column, row, time) {
    const u = column / (columns - 1);
    const v = row / (rows - 1);
    const x = (u - .5) * 3.6;
    const depth = .44 + Math.pow(v, 1.4) * .78;
    const hill = Math.exp(-((x - .38) ** 2 * 2.7 + (v - .46) ** 2 * 15));
    const ridge = Math.exp(-((x + .9) ** 2 * 3.2 + (v - .7) ** 2 * 18));
    const elevation = Math.sin(x * 2.7 + v * 6.4 - time * .32) * .24
      + Math.cos(x * 3.5 - v * 5 + time * .23) * .13
      + hill * .95 + ridge * .5;
    let screenX = width * .5 + x * width * .43 * depth;
    let screenY = height * .24 + v * height * .63 - elevation * height * .23 * depth;
    const dx = screenX - pointer.x;
    const dy = screenY - pointer.y;
    const distance = Math.hypot(dx, dy);
    const radius = Math.max(130, Math.min(250, width * .2));
    const influence = Math.exp(-((distance / radius) ** 2) * 2) * pointer.strength;
    const twist = pointer.down ? .8 : .12;
    screenX += (dx * -.08 - dy * twist) * influence;
    screenY += (dy * -.08 + dx * twist * .4 - (pointer.down ? -80 : 52)) * influence;
    for (const wave of waves) {
      const age = time - wave.born;
      const radius = age * 240;
      const distance = Math.hypot(screenX - wave.x, screenY - wave.y);
      const front = (distance - radius) / 42;
      screenY -= Math.cos(front * 1.7) * Math.exp(-front * front * .55)
        * Math.exp(-age * .65) * 38;
    }
    const parallaxX = (pointer.x / Math.max(width, 1) - .5) * 20 * pointer.strength;
    const parallaxY = (pointer.y / Math.max(height, 1) - .5) * 12 * pointer.strength;
    return { x: screenX + parallaxX, y: screenY + parallaxY, elevation, depth, u, v };
  }

  function line(points, color, thickness = .7) {
    context.strokeStyle = color;
    context.lineWidth = thickness;
    context.beginPath();
    points.forEach((point, index) => {
      if (index === 0) context.moveTo(point.x, point.y);
      else context.lineTo(point.x, point.y);
    });
    context.stroke();
  }

  function paint() {
    const dark = document.documentElement.dataset.theme === 'dark';
    const time = motion.matches ? 2.4 : elapsed;
    context.clearRect(0, 0, width, height);
    const glow = context.createRadialGradient(width * .57, height * .49, 0, width * .57, height * .49, width * .55);
    glow.addColorStop(0, dark ? 'rgba(107, 72, 210, .16)' : 'rgba(126, 95, 222, .1)');
    glow.addColorStop(1, 'rgba(126, 95, 222, 0)');
    context.fillStyle = glow;
    context.fillRect(0, 0, width, height);
    if (pointer.strength > .01) {
      const light = context.createRadialGradient(pointer.x, pointer.y, 0, pointer.x, pointer.y, 220);
      light.addColorStop(0, `rgba(77, 196, 218, ${pointer.strength * (dark ? .1 : .07)})`);
      light.addColorStop(1, 'rgba(77, 196, 218, 0)');
      context.fillStyle = light;
      context.fillRect(0, 0, width, height);
    }
    stars.forEach(star => {
      const x = star.x * width + Math.sin(time * .12 + star.phase) * 8;
      const y = star.y * height;
      const shimmer = .25 + (Math.sin(time * .5 + star.phase) + 1) * .13;
      context.fillStyle = dark ? `rgba(173, 173, 220, ${shimmer})` : `rgba(111, 101, 163, ${shimmer})`;
      context.fillRect(x, y, star.size, star.size);
    });
    const mesh = [];
    for (let row = 0; row < rows; row += 1) {
      const points = [];
      for (let column = 0; column < columns; column += 1) points.push(project(column, row, time));
      mesh.push(points);
    }
    context.lineJoin = 'round';
    for (let row = 0; row < rows; row += 1) {
      const v = row / (rows - 1);
      const alpha = (dark ? .13 : .1) + Math.sin(v * Math.PI) * (dark ? .2 : .14);
      line(mesh[row], `rgba(${dark ? '151, 119, 230' : '113, 88, 182'}, ${alpha})`, .7);
    }
    for (let column = 0; column < columns; column += 2) {
      line(mesh.map(points => points[column]), dark ? 'rgba(107, 141, 198, .12)' : 'rgba(106, 113, 165, .1)', .6);
    }
    // Bright travelling contours give the mesh depth without blurring every line.
    for (const row of [12, 19, 27, 35]) {
      const gradient = context.createLinearGradient(width * .1, 0, width * .9, 0);
      gradient.addColorStop(0, 'rgba(154, 96, 247, 0)');
      gradient.addColorStop(.25, dark ? 'rgba(179, 131, 255, .58)' : 'rgba(125, 79, 207, .5)');
      gradient.addColorStop(.65, dark ? 'rgba(89, 215, 223, .65)' : 'rgba(31, 157, 175, .48)');
      gradient.addColorStop(1, 'rgba(89, 215, 223, 0)');
      const index = Math.min(rows - 1, Math.round(row / 44 * rows));
      context.shadowColor = dark ? '#8f72dc' : 'transparent';
      context.shadowBlur = dark ? 8 : 0;
      line(mesh[index], gradient, 1.3);
      context.shadowBlur = 0;
    }
    // Signals float above the surface and follow its actual geometry.
    for (let index = 0; index < 9; index += 1) {
      const column = Math.round((.15 + index * .087) * (columns - 1));
      const row = Math.round((.32 + (index % 3) * .17) * (rows - 1));
      const point = mesh[row][column];
      const lift = 24 + Math.sin(time * .6 + index) * 9;
      const x = point.x;
      const y = point.y - lift;
      line([{ x, y: point.y }, { x, y }], dark ? 'rgba(116, 210, 216, .22)' : 'rgba(65, 139, 156, .22)');
      const halo = context.createRadialGradient(x, y, 0, x, y, 14);
      halo.addColorStop(0, dark ? 'rgba(106, 233, 229, .35)' : 'rgba(75, 177, 190, .2)');
      halo.addColorStop(1, 'rgba(106, 233, 229, 0)');
      context.fillStyle = halo;
      context.fillRect(x - 14, y - 14, 28, 28);
      context.fillStyle = dark ? '#a9f0ed' : '#4a9aa4';
      context.beginPath();
      context.arc(x, y, 1.8, 0, Math.PI * 2);
      context.fill();
    }
    for (const wave of waves) {
      const age = time - wave.born;
      context.strokeStyle = `rgba(133, 210, 233, ${Math.max(0, .25 - age * .09)})`;
      context.lineWidth = 1;
      context.beginPath();
      context.ellipse(wave.x, wave.y, Math.max(1, age * 240), Math.max(1, age * 130), 0, 0, Math.PI * 2);
      context.stroke();
    }
  }

  function animate(timestamp) {
    frame = 0;
    if (timestamp - lastPaint >= 30 || motion.matches) {
      const delta = Math.min((timestamp - previousTime) / 1000 || .016, .05);
      if (!motion.matches) elapsed += delta;
      previousTime = timestamp;
      lastPaint = timestamp;
      pointer.x += (pointer.targetX - pointer.x) * .12;
      pointer.y += (pointer.targetY - pointer.y) * .12;
      pointer.strength += ((pointer.active ? 1 : 0) - pointer.strength) * .1;
      while (waves.length && elapsed - waves[0].born > 4) waves.shift();
      paint();
    }
    if (!motion.matches && visible && !document.hidden) frame = requestAnimationFrame(animate);
  }

  function start() {
    if (!frame && visible && !document.hidden) {
      previousTime = performance.now();
      lastPaint = -Infinity;
      frame = requestAnimationFrame(animate);
    }
  }

  function resize() {
    const bounds = workspace.getBoundingClientRect();
    if (!bounds.width || !bounds.height) return;
    width = bounds.width;
    height = bounds.height;
    columns = width < 700 ? 48 : 76;
    rows = width < 700 ? 30 : 44;
    const ratio = Math.min(window.devicePixelRatio || 1, 1.7);
    canvas.width = Math.round(width * ratio);
    canvas.height = Math.round(height * ratio);
    context.setTransform(ratio, 0, 0, ratio, 0, 0);
    pointer.x = pointer.targetX = width * .5;
    pointer.y = pointer.targetY = height * .5;
    paint();
    start();
  }

  workspace.addEventListener('pointermove', event => {
    if (motion.matches) return;
    const bounds = workspace.getBoundingClientRect();
    pointer.targetX = event.clientX - bounds.left;
    pointer.targetY = event.clientY - bounds.top;
    pointer.active = true;
  });
  workspace.addEventListener('pointerdown', event => {
    if (motion.matches || event.target.closest('a, button')) return;
    const bounds = workspace.getBoundingClientRect();
    pointer.targetX = event.clientX - bounds.left;
    pointer.targetY = event.clientY - bounds.top;
    pointer.active = pointer.down = true;
    addWave(pointer.targetX, pointer.targetY);
  });
  workspace.addEventListener('pointerleave', () => { pointer.active = pointer.down = false; });
  window.addEventListener('pointerup', () => { pointer.down = false; });
  window.addEventListener('pointercancel', () => { pointer.down = false; });
  button.addEventListener('click', () => addWave(width * .52, height * .5));
  function motionChanged() {
    button.disabled = motion.matches;
    button.title = motion.matches ? 'Уменьшение движения включено в настройках системы' : '';
    if (motion.matches) { waves.length = 0; pointer.active = false; pointer.strength = 0; }
    start();
  }
  motion.addEventListener('change', motionChanged);
  // A theme change also repaints the static reduced-motion composition.
  if ('MutationObserver' in window) {
    new MutationObserver(start).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  }
  document.addEventListener('visibilitychange', () => {
    if (document.hidden && frame) { cancelAnimationFrame(frame); frame = 0; }
    else start();
  });
  if ('IntersectionObserver' in window) {
    new IntersectionObserver(entries => {
      visible = entries[0].isIntersecting;
      if (visible) start();
      else if (frame) { cancelAnimationFrame(frame); frame = 0; }
    }).observe(workspace);
  }
  if ('ResizeObserver' in window) new ResizeObserver(resize).observe(workspace);
  else window.addEventListener('resize', resize);
  resize();
  motionChanged();
})();
