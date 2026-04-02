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

// ── BILLING TOGGLE ──
const billingToggle = document.getElementById('billingToggle');
if (billingToggle) {
  billingToggle.addEventListener('change', function() {
    const isAnnual = this.checked;
    const pricingCards = document.querySelectorAll('.pricing-card');
    const monthlyLabel = document.querySelector('.billing-label:first-of-type');
    const annualLabel = document.querySelector('.billing-label:nth-of-type(2)');
    
    pricingCards.forEach(card => {
      if (isAnnual) {
        card.classList.add('annual-mode');
      } else {
        card.classList.remove('annual-mode');
      }
    });
    
    // Update label colors
    if (monthlyLabel && annualLabel) {
      if (isAnnual) {
        monthlyLabel.style.color = 'var(--text3)';
        monthlyLabel.style.fontWeight = '400';
        annualLabel.style.color = 'var(--text)';
        annualLabel.style.fontWeight = '600';
      } else {
        monthlyLabel.style.color = 'var(--text)';
        monthlyLabel.style.fontWeight = '600';
        annualLabel.style.color = 'var(--text3)';
        annualLabel.style.fontWeight = '400';
      }
    }
  });
}

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
