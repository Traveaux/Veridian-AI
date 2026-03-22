// ── SCROLL REVEAL ──
const revealEls = document.querySelectorAll('.reveal');
const observer = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      e.target.classList.add('visible');
      observer.unobserve(e.target);
    }
  });
}, { threshold: 0.12 });
revealEls.forEach(el => observer.observe(el));

// ── NAVBAR SCROLL ──
const navbar = document.querySelector('.navbar');
window.addEventListener('scroll', () => {
  if (window.scrollY > 40) {
    navbar.style.background = 'rgba(10,15,13,0.95)';
    navbar.style.borderBottomColor = 'rgba(45,255,143,0.12)';
  } else {
    navbar.style.background = 'rgba(10,15,13,0.7)';
    navbar.style.borderBottomColor = 'rgba(45,255,143,0.08)';
  }
});

// ── COUNTER ANIMATION ──
function animateCounter(el, target, suffix = '') {
  const duration = 1800;
  const start = performance.now();
  const startVal = 0;

  function update(now) {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    // Ease out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.floor(startVal + (target - startVal) * eased);
    el.textContent = current.toLocaleString() + suffix;
    if (progress < 1) requestAnimationFrame(update);
  }

  requestAnimationFrame(update);
}

const countersObserver = new IntersectionObserver((entries) => {
  entries.forEach(e => {
    if (e.isIntersecting) {
      const el = e.target;
      const target = parseInt(el.dataset.target);
      const suffix = el.dataset.suffix || '';
      animateCounter(el, target, suffix);
      countersObserver.unobserve(el);
    }
  });
}, { threshold: 0.5 });

document.querySelectorAll('[data-target]').forEach(el => countersObserver.observe(el));

// ── SMOOTH SCROLL FOR ANCHOR LINKS ──
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', e => {
    e.preventDefault();
    const target = document.querySelector(a.getAttribute('href'));
    if (target) {
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

// ── DISCORD INVITE BUTTON ──
document.querySelectorAll('[data-discord]').forEach(btn => {
  btn.addEventListener('click', () => {
    // Replace with real Discord invite link
    window.open('https://discord.com/oauth2/authorize?client_id=1475845849333498038', '_blank');
  });
});

// ── TYPING EFFECT for hero subtitle ──
const typingEl = document.getElementById('typing-text');
if (typingEl) {
  const texts = [
    'Support multilingue alimenté par l\'IA.',
    'Tickets traduits en temps réel.',
    'Votre communauté sans frontières.',
  ];
  let i = 0, j = 0, deleting = false;

  function type() {
    const current = texts[i];
    if (!deleting) {
      typingEl.textContent = current.slice(0, j + 1);
      j++;
      if (j === current.length) {
        deleting = true;
        setTimeout(type, 2200);
        return;
      }
    } else {
      typingEl.textContent = current.slice(0, j - 1);
      j--;
      if (j === 0) {
        deleting = false;
        i = (i + 1) % texts.length;
      }
    }
    setTimeout(type, deleting ? 35 : 55);
  }
  type();
}

// ── GRID TRACE ──
(function () {
  const canvas = document.getElementById('grid-trace');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const CELL = 60;
  let W, H, cols, rows;

  function resize() {
    W = canvas.width  = window.innerWidth;
    H = canvas.height = window.innerHeight;
    cols = Math.ceil(W / CELL) + 1;
    rows = Math.ceil(H / CELL) + 1;
  }
  resize();
  window.addEventListener('resize', resize);

  let prevScroll = window.scrollY, scrollVel = 0;

  // Position grille courante
  let gi = Math.floor(cols / 2);
  let gj = Math.floor(rows / 2);

  // Position lissée (px écran)
  let px = gi * CELL, py = gj * CELL;
  let targetX = px, targetY = py;

  // Segments : coords écran mises à jour à chaque frame avec le scroll
  const segs = [], MAX_SEG = 16;

  // Historique des positions récentes pour éviter de repasser au même endroit
  // On garde les N derniers (gi,gj) visités
  const visited = [];
  const MAX_VISITED = 8;

  // Direction précédente pour éviter de faire demi-tour
  let lastDi = 0, lastDj = 0;

  const STEP_MS = 480;
  let lastTime = 0, timeSinceStep = 0;

  function wasRecentlyVisited(ni, nj) {
    return visited.some(v => v.i === ni && v.j === nj);
  }

  function pickNext() {
    const dirs = [
      { di:  1, dj:  0 },
      { di: -1, dj:  0 },
      { di:  0, dj:  1 },
      { di:  0, dj: -1 },
    ];

    // Construire les poids
    const candidates = [];
    for (const d of dirs) {
      const ni = gi + d.di;
      const nj = gj + d.dj;

      // Rester dans l'écran (avec marge de 1 cellule)
      if (ni < 0 || ni >= cols || nj < 1 || nj >= rows - 1) continue;

      let w = 10;

      // Pénaliser le demi-tour
      if (d.di === -lastDi && d.dj === -lastDj) w *= 0.05;

      // Pénaliser les positions récemment visitées
      if (wasRecentlyVisited(ni, nj)) w *= 0.1;

      // Favoriser la direction du scroll
      if (scrollVel >  8 && d.dj ===  1) w *= 4;
      if (scrollVel < -8 && d.dj === -1) w *= 4;

      // Légère préférence pour changer de direction (évite les longues lignes droites)
      if (d.di === lastDi && d.dj === lastDj) w *= 0.6;

      if (w > 0) candidates.push({ ni, nj, di: d.di, dj: d.dj, w });
    }

    if (candidates.length === 0) return { ni: gi, nj: gj, di: 0, dj: 0 };

    const tot = candidates.reduce((a, c) => a + c.w, 0);
    let r = Math.random() * tot;
    for (const c of candidates) {
      r -= c.w;
      if (r <= 0) return c;
    }
    return candidates[candidates.length - 1];
  }

  function frame(now) {
    requestAnimationFrame(frame);
    const dt = Math.min(now - lastTime, 80);
    lastTime = now;

    const curScroll = window.scrollY;
    const delta     = curScroll - prevScroll;
    scrollVel       = delta / (dt / 16);
    prevScroll      = curScroll;

    // Décaler tout avec le scroll
    py      -= delta;
    targetY -= delta;
    for (const s of segs) { s.ay -= delta; s.by -= delta; }

    // Si la cible sort de l'écran, la ramener sans casser gj
    // On recalcule gj depuis targetY pour rester cohérent
    if (targetY < CELL)     targetY = CELL;
    if (targetY > H - CELL) targetY = H - CELL;
    py = Math.max(CELL, Math.min(H - CELL, py));

    // Resynchroniser gj avec targetY (après clamping)
    gj = Math.round(targetY / CELL);
    gj = Math.max(1, Math.min(rows - 2, gj));

    // Step
    const speed = 1 + Math.min(Math.abs(scrollVel) / 12, 3);
    timeSinceStep += dt * speed;
    if (timeSinceStep >= STEP_MS) {
      timeSinceStep = 0;
      const next = pickNext();

      segs.push({ ax: targetX, ay: targetY, bx: next.ni * CELL, by: next.nj * CELL });
      if (segs.length > MAX_SEG) segs.shift();

      // Mémoriser la position courante
      visited.push({ i: gi, j: gj });
      if (visited.length > MAX_VISITED) visited.shift();

      lastDi = next.di;
      lastDj = next.dj;
      gi = next.ni;
      gj = next.nj;
      targetX = gi * CELL;
      targetY = gj * CELL;
    }

    // Lissage
    px += (targetX - px) * 0.14;
    py += (targetY - py) * 0.14;

    // Dessin
    ctx.clearRect(0, 0, W, H);
    const n = segs.length;

    for (let i = 0; i < n; i++) {
      const s = segs[i];
      const t = (i + 1) / (n + 1);
      ctx.beginPath();
      ctx.moveTo(s.ax, s.ay);
      ctx.lineTo(s.bx, s.by);
      ctx.strokeStyle = `rgba(45,255,143,${t * 0.17})`;
      ctx.lineWidth   = 1.5;
      ctx.shadowColor = 'rgba(45,255,143,0.15)';
      ctx.shadowBlur  = 5;
      ctx.stroke();
    }

    if (n > 0) {
      const last = segs[n - 1];
      ctx.beginPath();
      ctx.moveTo(last.bx, last.by);
      ctx.lineTo(px, py);
      ctx.strokeStyle = 'rgba(45,255,143,0.17)';
      ctx.lineWidth   = 1.5;
      ctx.shadowColor = 'rgba(45,255,143,0.15)';
      ctx.shadowBlur  = 5;
      ctx.stroke();
    }

    // Point lumineux
    ctx.beginPath();
    ctx.arc(px, py, 3, 0, Math.PI * 2);
    ctx.fillStyle   = 'rgba(45,255,143,0.5)';
    ctx.shadowColor = 'rgba(45,255,143,0.8)';
    ctx.shadowBlur  = 10;
    ctx.fill();
    ctx.shadowBlur  = 0;
  }

  requestAnimationFrame(t => { lastTime = t; requestAnimationFrame(frame); });
})();