/**
 * Veridian AI — Dashboard JS
 * Auth: JWT Bearer uniquement pour les appels /internal/*
 * CDC 2026: utilisateur lambda = Tickets + Settings uniquement
 *           Super Admin = tout (Dashboard, Orders, KB, Super Admin, clés Groq)
 */

// ─────────────────────────────────────────────────────────────
// CONFIG
// ─────────────────────────────────────────────────────────────
const API_BASE = "https://api.veridiancloud.xyz";

const DISCORD_REDIRECT_URI = "https://api.veridiancloud.xyz/auth/callback";

// ─────────────────────────────────────────────────────────────
// STATE
// ─────────────────────────────────────────────────────────────
let state = {
  token: null,
  user: null,
  guilds: [],
  currentGuild: null,
  guildMeta: {}, // { [guildId]: { plan?: string } }
  currentPage: "dashboard",
};

function normalizeSnowflake(raw) {
  const s = String(raw || "").trim();
  if (!s) return null;
  const m = s.match(/\d{5,}/);
  return m ? m[0] : null;
}

// ─────────────────────────────────────────────────────────────
// INIT
// ─────────────────────────────────────────────────────────────
// Intervalle auto-refresh du statut bot (60s)
let _botStatusInterval = null;

document.addEventListener("DOMContentLoaded", () => {
  bindStaticActions();
  initApp();
  initNav();
  initKB();
  initToggleSwitches();
  initProgressBars();
  initBarChart();
  initServerSelector();
  initSettingsTabs();
  initSettingsSave();
  initTicketSearch();
  updateTopbarDate();
});

function bindStaticActions() {
  // Non-inline event handlers (required for strict CSP).
  const loginBtn = document.getElementById("login-discord-btn");
  if (loginBtn) loginBtn.addEventListener("click", loginWithDiscord);

  document.addEventListener("click", (e) => {
    const nav = e.target.closest("[data-nav]");
    if (nav) {
      navigateTo(nav.dataset.nav);
      return;
    }

    const actionEl = e.target.closest("[data-action]");
    if (actionEl) {
      const action = actionEl.dataset.action;
      if (action === "logout") return void logout();
      if (action === "close-transcript") return void closeTranscriptModal();
      if (action === "export-transcript-pdf") return void exportTranscriptPdf();
      if (action === "refresh-dashboard") return void loadDashboardStats();
      if (action === "refresh-tickets") return void loadTickets();
      if (action === "refresh-orders") return void loadOrders();
      if (action === "refresh-superadmin") return void loadSuperAdminData();
      if (action === "kb-cancel") {
        const form = document.getElementById("kb-form");
        if (form) form.style.display = "none";
        return;
      }
      if (action === "admin-activate-sub") return void adminActivateSub();
      if (action === "admin-revoke-sub") return void adminRevokeSub();
    }

    const ticketBtn = e.target.closest("[data-ticket-action]");
    if (ticketBtn) {
      const ticketId = parseInt(ticketBtn.dataset.ticketId, 10);
      const ticketStatus = ticketBtn.dataset.ticketStatus || "";
      if (!Number.isFinite(ticketId)) return;
      if (ticketBtn.dataset.ticketAction === "view") return void viewTicketTranscript(ticketId);
      if (ticketBtn.dataset.ticketAction === "close") return void closeTicket(ticketId, ticketStatus);
      if (ticketBtn.dataset.ticketAction === "reopen") return void reopenTicket(ticketId);
    }

    const orderBtn = e.target.closest("[data-order-action]");
    if (orderBtn) {
      const orderId = orderBtn.dataset.orderId;
      const status = orderBtn.dataset.status;
      if (!orderId || !status) return;
      if (orderBtn.dataset.orderAction === "set-status") return void validateOrder(orderBtn, orderId, status);
    }

    const kbBtn = e.target.closest("[data-kb-action]");
    if (kbBtn) {
      const id = parseInt(kbBtn.dataset.kbId, 10);
      if (!Number.isFinite(id)) return;
      if (kbBtn.dataset.kbAction === "edit") return void editKBEntry(id);
      if (kbBtn.dataset.kbAction === "delete") return void deleteKBEntry(id);
    }
  });

  // Escape closes the transcript modal (if open).
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeTranscriptModal();
  });

  // Changement de priorité de ticket (delegation change)
  document.addEventListener("change", (e) => {
    const sel = e.target.closest("[data-ticket-priority-select]");
    if (!sel) return;
    const ticketId = parseInt(sel.dataset.ticketId, 10);
    const value = sel.value;
    if (!Number.isFinite(ticketId) || !value) return;
    updateTicketPriority(ticketId, value, sel);
  });
}

async function initApp() {
  const urlParams = new URLSearchParams(window.location.search);
  const authCode  = urlParams.get("auth");   // temp_code apres OAuth (60s, usage unique)
  const urlError  = urlParams.get("error");

  if (urlError) {
    showLoginScreen();
    showToast("Erreur OAuth: " + urlError, "error");
    return;
  }

  // 1. Temp code dans l'URL → l'echanger contre le vrai JWT
  if (authCode) {
    // NE PAS effacer l'URL avant l'echange — si echec on peut reessayer
    await exchangeTempCode(authCode);
    return;
  }

  // 2. JWT deja en localStorage (session existante)
  const stored = localStorage.getItem("vai_token");
  if (stored) {
    state.token = stored;
    await loadUserFromToken();
    return;
  }

  // 3. Rien → ecran de login
  showLoginScreen();
}

async function exchangeTempCode(tempCode) {
  console.log("[auth] Echange temp_code...");
  try {
    const res = await fetch(API_BASE + "/auth/exchange", {
      method:  "POST",
      headers: { "Content-Type": "application/json" },
      body:    JSON.stringify({ code: tempCode }),
    });

    console.log("[auth] /auth/exchange status:", res.status);

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      const msg = err.detail || "Echange de code echoue (" + res.status + ")";
      console.error("[auth] Erreur exchange:", msg);
      throw new Error(msg);
    }

    const data = await res.json();
    console.log("[auth] Exchange OK, user:", data.user && data.user.username);

    state.token  = data.token;
    state.user   = data.user;
    state.guilds = data.guilds || [];
    localStorage.setItem("vai_token", data.token);

    // Nettoyer l'URL seulement apres succes
    window.history.replaceState({}, "", window.location.pathname);
    renderDashboard();

  } catch (e) {
    console.error("[auth] exchangeTempCode erreur:", e);
    showLoginScreen();
    showToast("Erreur de connexion: " + e.message, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// AUTH
// ─────────────────────────────────────────────────────────────

function loginWithDiscord() {
  // Redirect vers le backend qui gère le flux OAuth Discord
  window.location.href = API_BASE + "/auth/discord/login";
}

async function handleOAuthCode(code) {
  showToast("Connexion en cours…", "info");
  try {
    const res = await apiPost("/auth/discord", { code });
    state.token = res.token;
    state.user = res.user;
    state.guilds = res.guilds || [];
    localStorage.setItem("vai_token", res.token);
    window.history.replaceState({}, "", window.location.pathname);
    renderDashboard();
  } catch (e) {
    showLoginScreen();
    showToast("Erreur d'authentification: " + e.message, "error");
  }
}

async function loadUserFromToken() {
  try {
    const data = await apiFetch(`/auth/user/me`, { auth: true });
    state.user = {
      id: String(data.user_id),
      username: data.username,
      is_super_admin: data.is_super_admin,
    };
    // Charger les guilds depuis l'API (le token ne les contient pas)
    await loadGuilds();
    renderDashboard();
  } catch (e) {
    // Token invalide ou expiré
    localStorage.removeItem("vai_token");
    state.token = null;
    showLoginScreen();
    if (e.status !== 401) showToast("Session expirée, veuillez vous reconnecter", "warn");
  }
}

async function loadGuilds() {
  try {
    // On récupère les guilds via un appel auth/discord avec le token actuel
    // Alternative : endpoint dédié /auth/guilds
    const data = await apiFetch("/auth/user/guilds", { auth: true });
    state.guilds = data.guilds || [];
  } catch (e) {
    // Endpoint optionnel — pas bloquant
    logger?.warn?.("Guilds non chargées:", e);
  }
}

async function logout() {
  try {
    await apiPost("/auth/logout", { token: state.token });
  } catch (_) {}
  localStorage.removeItem("vai_token");
  state.token = null;
  state.user = null;
  state.guilds = [];
  state.currentGuild = null;
  // Arrêter l'auto-refresh du statut bot
  if (_botStatusInterval) {
    clearInterval(_botStatusInterval);
    _botStatusInterval = null;
  }
  showLoginScreen();
}

// ─────────────────────────────────────────────────────────────
// RENDER
// ─────────────────────────────────────────────────────────────

function showLoginScreen() {
  document.getElementById("login-screen").style.display = "flex";
  document.getElementById("app").style.display = "none";
}

function renderDashboard() {
  document.getElementById("login-screen").style.display = "none";
  document.getElementById("app").style.display = "flex";

  const isSuper = !!state.user?.is_super_admin;

  // User card
  const u = state.user;
  if (u) {
    document.querySelector(".user-name").textContent = u.username || "—";
    document.querySelector(".user-role").innerHTML = isSuper ? 'Super Admin <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="var(--yellow)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:-2px;margin-left:2px"><path d="M2 4l3 12h14l3-12-6 7-4-7-4 7-6-7z"></path></svg>' : "Admin Serveur";
    const avatarImg = document.querySelector(".user-avatar-img");
    if (avatarImg && u.avatar) avatarImg.src = u.avatar;
  }

  // Server selector
  populateServerSelector();
  // Fetch real plan/meta for the selected guild
  if (state.currentGuild?.id) ensureGuildMeta(state.currentGuild.id);

  // CDC: navigation et pages réservées au Super Admin
  toggleSuperAdminNav(isSuper);

  // CDC: masquer les pages réservées au Super Admin pour les utilisateurs lambda
  // Utilisateur lambda : uniquement Tickets + Settings
  const superOnlyPages = ["page-dashboard", "page-orders", "page-kb"];
  superOnlyPages.forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.style.display = isSuper ? "" : "none";
  });

  // CDC: masquer le bouton Upgrader (redirige vers Orders, réservé Super Admin)
  const upgradeBtnLegacy = document.querySelector(".btn[onclick*=\"orders\"]");
  if (upgradeBtnLegacy) upgradeBtnLegacy.style.display = isSuper ? "" : "none";
  const upgradeBtn = document.getElementById("settings-upgrade-btn");
  if (upgradeBtn) upgradeBtn.style.display = isSuper ? "" : "none";

  // Charger la page par défaut selon le rôle
  const defaultPage = isSuper ? "dashboard" : "tickets";
  navigateTo(state.currentPage || defaultPage);

  // Charger le statut du bot immédiatement et démarrer l'auto-refresh
  loadBotStatus();
  if (_botStatusInterval) clearInterval(_botStatusInterval);
  _botStatusInterval = setInterval(loadBotStatus, 60000);
}

async function ensureGuildMeta(guildId) {
  if (!state.token || !guildId) return;
  try {
    const stats = await apiFetch(`/internal/guild/${guildId}/stats`, { auth: true });
    if (stats && stats.current_plan) {
      state.guildMeta[guildId] = { ...(state.guildMeta[guildId] || {}), plan: stats.current_plan };
      updateServerPlanDisplay();
    }
  } catch (_) {}
}

function populateServerSelector() {
  const display = document.getElementById("server-selector-display");
  if (!display) return;

  const guilds = state.guilds;
  if (!guilds || guilds.length === 0) {
    display.querySelector(".server-name").textContent = "Aucun serveur";
    display.querySelector(".server-plan").textContent = "—";
    return;
  }

  // Sélectionner le premier par défaut
  if (!state.currentGuild) {
    state.currentGuild = guilds.find((x) => x && x.bot_present !== false) || guilds[0];
  }
  const g = state.currentGuild;

  display.querySelector(".server-name").textContent = g.name || "Serveur";
  updateServerPlanDisplay();

  // Avatar serveur
  const avatar = display.querySelector(".server-avatar");
  if (avatar) {
    if (g.icon) {
      // Avoid innerHTML injection: build the element.
      avatar.textContent = "";
      const iconUrl = String(g.icon || "");
      if (iconUrl.startsWith("https://")) {
        const img = document.createElement("img");
        img.src = iconUrl;
        img.alt = "";
        img.style.width = "28px";
        img.style.height = "28px";
        img.style.borderRadius = "6px";
        img.style.objectFit = "cover";
        avatar.appendChild(img);
      } else {
        avatar.textContent = g.name?.[0]?.toUpperCase() || "?";
      }
    } else {
      avatar.textContent = g.name?.[0]?.toUpperCase() || "?";
    }
  }

  // Peupler le dropdown
  const dropdown = document.getElementById("server-dropdown");
  if (dropdown && guilds.length > 0) {
    dropdown.innerHTML = "";
    guilds.forEach((guild) => {
      const item = document.createElement("div");
      item.style.cssText = "padding:8px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:12px;color:var(--text);transition:background .15s";
      item.addEventListener("mouseenter", () => item.style.background = "var(--surface)");
      item.addEventListener("mouseleave", () => item.style.background = "transparent");

      const iconSpan = document.createElement("span");
      iconSpan.style.cssText = "width:24px;height:24px;border-radius:6px;background:var(--surface2);display:flex;align-items:center;justify-content:center;font-size:11px;flex-shrink:0";
      if (guild.icon && String(guild.icon).startsWith("https://")) {
        const img = document.createElement("img");
        img.src = guild.icon;
        img.alt = "";
        img.style.cssText = "width:24px;height:24px;border-radius:6px;object-fit:cover";
        iconSpan.appendChild(img);
      } else {
        iconSpan.textContent = guild.name?.[0]?.toUpperCase() || "?";
      }

      const nameSpan = document.createElement("span");
      nameSpan.textContent = guild.name || "Serveur";
      nameSpan.style.cssText = "flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap";

      item.appendChild(iconSpan);
      item.appendChild(nameSpan);

      // Bot presence badge
      const badge = document.createElement("span");
      const present = guild.bot_present !== false; // default true if missing
      badge.textContent = present ? "BOT" : "INVITER";
      badge.style.cssText =
        "font-size:9px;padding:2px 6px;border-radius:999px;letter-spacing:.4px;font-family:'Space Mono',monospace;flex-shrink:0;" +
        (present
          ? "background:rgba(0,255,170,0.10);border:1px solid rgba(0,255,170,0.18);color:var(--accent)"
          : "background:rgba(255,184,77,0.10);border:1px solid rgba(255,184,77,0.20);color:var(--yellow)");
      item.appendChild(badge);

      if (guild.id === state.currentGuild?.id) {
        const check = document.createElement("span");
        check.textContent = "✓";
        check.style.cssText = "color:var(--accent);font-size:14px;flex-shrink:0";
        item.appendChild(check);
      }

      item.addEventListener("click", () => selectGuild(guild.id));
      dropdown.appendChild(item);
    });
  }
}

function formatPlanLabel(plan) {
  const p = String(plan || "").toLowerCase();
  if (p === "pro") return "Pro";
  if (p === "premium") return "Premium";
  if (p === "free") return "Free";
  return p ? p.toUpperCase() : "—";
}

function updateServerPlanDisplay() {
  const display = document.getElementById("server-selector-display");
  if (!display) return;
  const planEl = display.querySelector(".server-plan");
  if (!planEl) return;
  const g = state.currentGuild;
  if (!g) { planEl.textContent = "—"; return; }

  if (g.bot_present === false) {
    planEl.textContent = "Bot non installé";
    return;
  }
  const meta = state.guildMeta?.[g.id] || {};
  planEl.textContent = formatPlanLabel(meta.plan || "—");
}

function toggleSuperAdminNav(isSuperAdmin) {
  // Tous les éléments marqués [data-super-admin] sont réservés au Super Admin :
  // nav items Dashboard, Orders, KB + groupe Super Admin dans la sidebar
  // CDC 2026 : utilisateur lambda = Tickets + Settings uniquement
  document.querySelectorAll("[data-super-admin]").forEach((el) => {
    el.style.display = isSuperAdmin ? "" : "none";
  });
}

// ─────────────────────────────────────────────────────────────
// NAVIGATION
// ─────────────────────────────────────────────────────────────

function initNav() {
  document.querySelectorAll(".nav-item[data-page]").forEach((item) => {
    item.addEventListener("click", () => {
      const page = item.dataset.page;
      navigateTo(page);
    });
  });
}

function navigateTo(page) {
  // CDC: utilisateur lambda = non super-admin
  // Pages réservées au Super Admin : dashboard (global), orders, kb, superadmin
  const isSuper = !!state.user?.is_super_admin;
  if (!isSuper && ["dashboard", "orders", "kb", "superadmin"].includes(page)) page = "tickets";

  state.currentPage = page;

  // Nav items
  document.querySelectorAll(".nav-item").forEach((el) => el.classList.remove("active"));
  const target = document.querySelector(`.nav-item[data-page="${page}"]`);
  if (target) target.classList.add("active");

  // Pages
  document.querySelectorAll(".page-content").forEach((el) => el.classList.remove("active"));
  const pageEl = document.getElementById(`page-${page}`);
  if (pageEl) pageEl.classList.add("active");

  // Breadcrumb
  const names = {
    dashboard: "Dashboard",
    tickets: "Tickets",
    orders: "Orders",
    settings: "Settings",
    kb: "Knowledge Base",
    superadmin: "Super Admin",
  };
  const breadcrumb = document.getElementById("breadcrumb-page");
  if (breadcrumb) breadcrumb.textContent = names[page] || page;

  // Charger les données de la page
  if (state.token && state.currentGuild) {
    if (page === "tickets") loadTickets();
    if (page === "orders" && state.user?.is_super_admin) loadOrders();
    if (page === "settings") loadSettings();
    if (page === "kb") loadKB();
    if (page === "dashboard") loadDashboardStats();
    if (page === "superadmin") loadSuperAdminData();
  }
}

// ─────────────────────────────────────────────────────────────
// API HELPERS
// ─────────────────────────────────────────────────────────────

async function apiFetch(path, { auth = false, method = "GET", body = null } = {}) {
  const headers = { "Content-Type": "application/json" };

  // Toutes les routes /internal/* et /auth/* nécessitent le JWT Bearer.
  // Le secret interne (INTERNAL_API_SECRET) reste côté serveur uniquement
  // et n'est jamais exposé dans le navigateur.
  if ((auth || path.startsWith("/internal/")) && state.token) {
    headers["Authorization"] = `Bearer ${state.token}`;
    // Fallback for some infrastructures that may strip Authorization.
    headers["X-VAI-Authorization"] = `Bearer ${state.token}`;
  }

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(API_BASE + path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const e = new Error(err.detail || `HTTP ${res.status}`);
    e.status = res.status;
    throw e;
  }
  return res.json();
}

async function apiPost(path, data) {
  return apiFetch(path, { method: "POST", body: data, auth: true });
}

async function apiPut(path, data) {
  return apiFetch(path, { method: "PUT", body: data, auth: true });
}

// ─────────────────────────────────────────────────────────────
// DASHBOARD STATS
// ─────────────────────────────────────────────────────────────

async function loadDashboardStats() {
  if (!state.currentGuild) return;
  const guildId = state.currentGuild.id;

  try {
    const stats = await apiFetch(`/internal/guild/${guildId}/stats`, { auth: true });

    setStatValue("stat-tickets-actifs", stats.open_tickets ?? "—");
    setStatValue("stat-tickets-mois", stats.tickets_month ?? "—");

    // Plan (valeur réelle, basée sur l'abonnement)
    if (stats.current_plan) {
      state.guildMeta[guildId] = { ...(state.guildMeta[guildId] || {}), plan: stats.current_plan };
      updateServerPlanDisplay();
    }

    // Bar chart (7 derniers jours)
    try {
      const chart = document.getElementById("bar-chart");
      if (chart) {
        const series = buildLast7DaysSeries(stats.daily_counts || []);
        renderBarChart(chart, series);
      }
    } catch (_) {}

    // Langues
    if (stats.languages && Array.isArray(stats.languages)) {
      renderLanguageStats(stats.languages);
      setStatValue("stat-languages-count", stats.languages.length);
    }

    // Badge tickets actifs sidebar
    const badge = document.querySelector('[data-badge="tickets"]');
    if (badge && stats.open_tickets != null) badge.textContent = stats.open_tickets;
  } catch (e) {
    console.warn("Dashboard stats:", e.message);
  }

  // Les commandes (orders) sont réservées au Super Admin
  if (state.user?.is_super_admin) {
    try {
      const orders = await apiFetch(`/internal/orders/pending`, { auth: true });
      const badge = document.querySelector('[data-badge="orders"]');
      if (badge && orders.total != null) badge.textContent = orders.total;
      setStatValue("stat-orders-attente", orders.total ?? "—");
    } catch (_) {}
  } else {
    const badge = document.querySelector('[data-badge="orders"]');
    if (badge) badge.textContent = "—";
    setStatValue("stat-orders-attente", "—");
  }
}

function buildLast7DaysSeries(dailyCounts) {
  // dailyCounts: [{day: 'YYYY-MM-DD', count: N}] from API
  const byDay = new Map();
  (dailyCounts || []).forEach((d) => {
    if (!d) return;
    const key = String(d.day || "");
    const val = Number(d.count || 0);
    if (key) byDay.set(key.slice(0, 10), val);
  });

  const labels = ["Dim", "Lun", "Mar", "Mer", "Jeu", "Ven", "Sam"];
  const out = [];
  const now = new Date();
  // Normalize to local midnight.
  now.setHours(0, 0, 0, 0);
  for (let i = 6; i >= 0; i--) {
    const dt = new Date(now);
    dt.setDate(now.getDate() - i);
    const yyyy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, "0");
    const dd = String(dt.getDate()).padStart(2, "0");
    const key = `${yyyy}-${mm}-${dd}`;
    out.push({ day: labels[dt.getDay()], val: byDay.get(key) || 0 });
  }
  return out;
}

function setStatValue(id, value) {
  const el = document.getElementById(id);
  if (el) {
    if (String(value).includes("<svg")) el.innerHTML = value;
    else el.textContent = value;
  }
}

// ─────────────────────────────────────────────────────────────────
// BOT STATUS (accessible à tous les utilisateurs authentifiés)
// ─────────────────────────────────────────────────────────────────

function formatUptime(seconds) {
  if (!seconds || seconds <= 0) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  let text = "";
  if (d > 0) text += `${d}j `;
  text += `${h}h ${m}m`;
  return text.trim();
}

async function loadBotStatus() {
  if (!state.token) return;

  try {
    const b = await apiFetch("/internal/bot/status", { auth: true });

    // ── Topbar indicator (visible partout) ──
    const dot = document.getElementById("bot-status-dot");
    const txt = document.getElementById("bot-status-text");
    const indicator = document.getElementById("bot-status-indicator");

    if (indicator) indicator.classList.remove("offline", "unknown");
    if (b.is_online) {
      if (txt) txt.textContent = "BOT EN LIGNE";
      if (indicator) indicator.title = `Latence: ${b.latency_ms}ms · ${b.guild_count} serveurs`;
    } else {
      if (indicator) indicator.classList.add("offline");
      if (txt) txt.textContent = "BOT HORS LIGNE";
      if (indicator) indicator.title = "Le bot ne répond plus depuis >2 minutes";
    }

    // ── Dashboard page: bot status cards ──
    setStatValue("dash-bot-status", b.is_online ? '<span style="color:var(--accent);display:inline-flex;align-items:center;gap:4px"><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"></circle></svg> En ligne</span>' : '<span style="color:var(--red);display:inline-flex;align-items:center;gap:4px"><svg width="10" height="10" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="12" r="10"></circle></svg> Hors ligne</span>');
    // We need to update setStatValue to support HTML

    setStatValue("dash-bot-latency", `Latence: ${b.latency_ms}ms`);
    setStatValue("dash-bot-guilds", b.guild_count ?? "—");
    setStatValue("dash-bot-users", `${b.user_count ?? 0} utilisateurs`);
    setStatValue("dash-bot-uptime", formatUptime(b.uptime_sec));
    setStatValue("dash-bot-version", b.version || "—");
    setStatValue("dash-bot-shards", `${b.shard_count ?? 1} shard${(b.shard_count ?? 1) > 1 ? "s" : ""}`);

    if (b.started_at) {
      try {
        const startDate = new Date(b.started_at);
        setStatValue("dash-bot-started", `Depuis: ${startDate.toLocaleString("fr-FR")}`);
      } catch (_) {
        setStatValue("dash-bot-started", `Depuis: ${b.started_at}`);
      }
    }

  } catch (e) {
    // Si l'appel échoue, marquer comme statut inconnu
    const indicator = document.getElementById("bot-status-indicator");
    const txt = document.getElementById("bot-status-text");
    if (indicator) { indicator.classList.remove("offline"); indicator.classList.add("unknown"); }
    if (txt) txt.textContent = "STATUT INCONNU";
    setStatValue("dash-bot-status", '<span style="color:var(--yellow);display:inline-flex;align-items:center;gap:4px"><svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg> Inconnu</span>');
    console.warn("Bot status:", e.message);
  }
}

const LANG_SVG = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="opacity:0.8"><circle cx="12" cy="12" r="10"></circle><line x1="2" y1="12" x2="22" y2="12"></line><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"></path></svg>`;
const LANG_FLAGS = { en: LANG_SVG, fr: LANG_SVG, de: LANG_SVG, es: LANG_SVG, ru: LANG_SVG, ja: LANG_SVG, zh: LANG_SVG, pt: LANG_SVG, it: LANG_SVG };
const LANG_NAMES = { en: "Anglais", fr: "Français", de: "Allemand", es: "Espagnol", ru: "Russe", ja: "Japonais", zh: "Chinois", pt: "Portugais", it: "Italien" };

function renderLanguageStats(languages) {
  const container = document.getElementById("lang-stats");
  if (!container) return;

  const total = languages.reduce((s, l) => s + (l.count || 0), 0);
  if (total === 0) return;

  container.innerHTML = languages
    .sort((a, b) => b.count - a.count)
    .slice(0, 5)
    .map((l) => {
      const code = l.user_language || l.lang || "?";
      const pctRaw = Math.round(((l.count || 0) / total) * 100);
      const pct = Math.max(0, Math.min(100, pctRaw));
      const name = LANG_NAMES[code] || code.toUpperCase();
      return `
      <div class="progress-item">
        <div class="progress-header">
          <div class="progress-label">${escHtml(name)}</div>
          <div class="progress-pct">${pct}%</div>
        </div>
        <div class="progress-track">
          <div class="progress-fill" data-width="${pct}%" style="width:0"></div>
        </div>
      </div>`;
    })
    .join("");

  // Réanimer les nouvelles barres
  setTimeout(() => animateProgressBars(container), 50);
}

// ─────────────────────────────────────────────────────────────
// TICKETS
// ─────────────────────────────────────────────────────────────

let allTickets = [];
let ticketFilter = "all";

async function loadTickets() {
  if (!state.currentGuild) return;
  const guildId = state.currentGuild.id;

  const tbody = document.getElementById("tickets-tbody");
  if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:24px">Chargement…</td></tr>`;

  try {
    const data = await apiFetch(`/internal/guild/${guildId}/tickets`, { auth: true });
    allTickets = data.tickets || [];
    renderTickets(allTickets);
  } catch (e) {
    if (tbody) tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--red);padding:24px">Erreur: ${escHtml(e.message || String(e))}</td></tr>`;
  }
}

function renderTickets(tickets) {
  const tbody = document.getElementById("tickets-tbody");
  if (!tbody) return;

  if (!tickets.length) {
    tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text3);padding:24px">Aucun ticket trouvé</td></tr>`;
    return;
  }

  tbody.innerHTML = tickets.map((t) => {
    const statusClass = { open: "pill pending", closed: "pill paid", "in_progress": "pill premium", "pending_close": "pill rejected" }[t.status] || "pill";
    const statusLabel = { open: "Ouvert", closed: "Fermé", in_progress: "En cours", "pending_close": "En attente clôture" }[t.status] || t.status;
    const ts = new Date(t.opened_at).getTime();
    const date = !isNaN(ts) ? new Date(ts).toLocaleString("fr-FR") : (t.opened_at || "—");
    const priorityRaw = (t.priority || "medium").toLowerCase();
    const priorityLabelMap = {
      low: "Bas",
      medium: "Moyen",
      high: "Haut",
      urgent: "Prioritaire",
    };
    const priorityLabel = priorityLabelMap[priorityRaw] || priorityRaw;
    const priorityClassMap = {
      low: "priority-dot low",
      medium: "priority-dot mid",
      high: "priority-dot high",
      urgent: "priority-dot high",
    };
    const priorityClass = priorityClassMap[priorityRaw] || "priority-dot mid";
    const tid = parseInt(String(t.id), 10);
    return `
    <tr>
      <td><span class="mono-id">#${Number.isFinite(tid) ? tid : escHtml(t.id)}</span></td>
      <td>${escHtml(t.user_username || String(t.user_id))}</td>
      <td><span class="${statusClass}">${escHtml(statusLabel)}</span></td>
      <td>
        <div style="display:flex;align-items:center;gap:6px">
          <span class="${priorityClass}">${escHtml(priorityLabel)}</span>
          ${Number.isFinite(tid) ? `
          <select data-ticket-priority-select data-ticket-id="${tid}" style="background:var(--surface);border:1px solid var(--border2);color:var(--text3);font-size:10px;border-radius:999px;padding:2px 6px;">
            <option value="low" ${priorityRaw === "low" ? "selected" : ""}>Bas</option>
            <option value="medium" ${priorityRaw === "medium" ? "selected" : ""}>Moyen</option>
            <option value="high" ${priorityRaw === "high" ? "selected" : ""}>Haut</option>
            <option value="urgent" ${priorityRaw === "urgent" ? "selected" : ""}>Prioritaire</option>
          </select>` : ""}
        </div>
      </td>
      <td>${escHtml(LANG_NAMES[t.user_language] || (t.user_language || "").toUpperCase())}</td>
      <td>${escHtml(t.assigned_staff_name || "—")}</td>
      <td class="mono-grey">${date}</td>
      <td>
        <button class="btn btn-ghost btn-sm btn-xs" data-ticket-action="view" data-ticket-id="${Number.isFinite(tid) ? tid : ""}" type="button" style="display:inline-flex;align-items:center;gap:4px">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path><polyline points="14 2 14 8 20 8"></polyline><line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line><polyline points="10 9 9 9 8 9"></polyline></svg>
          <span data-i18n="dash_view">Voir</span>
        </button>
        ${["open", "in_progress", "pending_close"].includes(t.status) && Number.isFinite(tid) ? `<button class="btn btn-red btn-sm btn-xs" data-ticket-action="close" data-ticket-id="${tid}" data-ticket-status="${escHtml(t.status || "")}" type="button" style="margin-left:4px">${t.status === "pending_close" ? "Confirmer" : "Demander fermeture"}</button>` : ""}
        ${["pending_close", "closed"].includes(t.status) && Number.isFinite(tid) ? `<button class="btn btn-ghost btn-sm btn-xs" data-ticket-action="reopen" data-ticket-id="${tid}" type="button" style="margin-left:4px">Réouvrir</button>` : ""}
      </td>
    </tr>`;
  }).join("");
}

function initTicketSearch() {
  const input = document.getElementById("ticket-search");
  if (!input) return;
  input.addEventListener("input", () => {
    const q = input.value.toLowerCase();
    const filtered = allTickets.filter(
      (t) =>
        String(t.id).includes(q) ||
        (t.user_username || "").toLowerCase().includes(q) ||
        (t.status || "").includes(q)
    );
    renderTickets(filtered);
  });

  // Filtres statut
  document.querySelectorAll("[data-ticket-filter]").forEach((btn) => {
    btn.addEventListener("click", () => {
      ticketFilter = btn.dataset.ticketFilter;
      document.querySelectorAll("[data-ticket-filter]").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");

      const filtered = ticketFilter === "all"
        ? allTickets
        : allTickets.filter((t) => ticketFilter === "open" ? ["open", "pending_close"].includes(t.status) : t.status === ticketFilter);
      renderTickets(filtered);
    });
  });
}

async function viewTicketTranscript(ticketId) {
  const modal = document.getElementById("transcript-modal");
  const content = document.getElementById("transcript-content");
  if (!modal || !content) return;

  content.textContent = "Chargement…";
  content.dataset.rawText = "";
  modal.style.display = "flex";

  try {
    const data = await apiFetch(`/internal/ticket/${ticketId}/transcript`, { auth: true });
    const titleEl = document.getElementById("transcript-title");
    if (titleEl) titleEl.textContent = `Ticket #${ticketId}`;

    const lines = [];

    // Résumé IA (si présent)
    if ((data.transcript || "").trim()) {
      lines.push("Résumé automatique du ticket");
      lines.push("-----------------------------");
      lines.push(String(data.transcript || "").trim());
      lines.push("");
      lines.push("");
    }

    // Messages détaillés : original + traduction éventuelle
    const msgs = Array.isArray(data.messages) ? data.messages : [];
    for (const m of msgs) {
      const author = m.author_username || String(m.author_id || "?");
      let ts = "";
      if (m.sent_at) {
        try {
          const d = new Date(m.sent_at);
          ts = d.toLocaleString("fr-FR");
        } catch (_) {
          ts = String(m.sent_at);
        }
      }
      const origLang = (m.original_language || "").toUpperCase();
      const tgtLang = (m.target_language || "").toUpperCase();
      const headerParts = [];
      if (ts) headerParts.push(ts);
      headerParts.push(author);
      if (origLang) {
        if (tgtLang && tgtLang !== origLang) {
          headerParts.push(`${origLang} → ${tgtLang}`);
        } else {
          headerParts.push(origLang);
        }
      }
      lines.push(headerParts.join(" · "));
      lines.push("");

      const original = (m.original_content || "").trim();
      if (original) {
        lines.push("Message original :");
        lines.push(original);
        lines.push("");
      }

      const translated = (m.translated_content || "").trim();
      if (translated) {
        lines.push("Traduction :");
        lines.push(translated);
        lines.push("");
      }

      lines.push("────────────────────────────────────────");
      lines.push("");
    }

    const finalText = lines.length ? lines.join("\n") : "Aucune transcription disponible.";
    content.textContent = finalText;
    content.dataset.rawText = finalText;
  } catch (e) {
    content.textContent = "Erreur: " + e.message;
    content.dataset.rawText = "";
  }
}

function closeTranscriptModal() {
  const modal = document.getElementById("transcript-modal");
  if (modal) modal.style.display = "none";
}

function exportTranscriptPdf() {
  const content = document.getElementById("transcript-content");
  if (!content) return;
  const raw = content.dataset.rawText || content.textContent || "";
  const text = String(raw || "").trim();
  if (!text) {
    showToast("Aucune transcription à exporter", "warn");
    return;
  }

  const titleEl = document.getElementById("transcript-title");
  const title = titleEl ? titleEl.textContent || "Transcription" : "Transcription";

  const win = window.open("", "_blank", "width=900,height=1000");
  if (!win) {
    showToast("Impossible d'ouvrir la fenêtre d'export (popup bloquée)", "warn");
    return;
  }

  const safeTitle = escHtml(title);
  const safeBody = escHtml(text);

  win.document.write(`
    <html>
      <head>
        <meta charset="utf-8">
        <title>${safeTitle}</title>
        <style>
          body {
            font-family: system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
            font-size: 12px;
            line-height: 1.6;
            color: #111;
            background: #fff;
            padding: 24px;
            white-space: pre-wrap;
          }
          h1 {
            font-size: 18px;
            margin: 0 0 16px;
          }
          pre {
            font-family: "Space Mono",ui-monospace,Menlo,Monaco,Consolas,"Liberation Mono","Courier New",monospace;
            font-size: 11px;
          }
        </style>
      </head>
      <body>
        <h1>${safeTitle}</h1>
        <pre>${safeBody}</pre>
      </body>
    </html>
  `);
  win.document.close();
  win.focus();
  try {
    win.print();
  } catch (_) {
    // L'utilisateur pourra utiliser le menu du navigateur si nécessaire.
  }
}

async function updateTicketPriority(ticketId, priority, selectEl) {
  const prev = selectEl.value;
  selectEl.disabled = true;
  try {
    await apiFetch(`/internal/ticket/${ticketId}/priority`, {
      method: "PUT",
      auth: true,
      body: { priority },
    });
    showToast(`Priorité mise à jour`, "success");
  } catch (e) {
    selectEl.value = prev;
    showToast("Erreur mise à jour priorité: " + e.message, "error");
  } finally {
    selectEl.disabled = false;
  }
}

async function closeTicket(ticketId, currentStatus = "") {
  const normalizedStatus = String(currentStatus || "").toLowerCase();
  const confirmMessage = normalizedStatus === "pending_close"
    ? `Confirmer la clôture définitive du ticket #${ticketId} ?`
    : `Passer le ticket #${ticketId} en attente de confirmation de clôture ?`;
  if (!confirm(confirmMessage)) return;
  try {
    const data = await apiFetch(`/internal/ticket/${ticketId}/close`, { method: "POST", auth: true });
    if (data.ticket_status === "pending_close") {
      showToast(`Ticket #${ticketId} en attente de confirmation`, "info");
    } else if (data.ticket_status === "closed") {
      showToast(`Ticket #${ticketId} fermé`, "success");
    } else {
      showToast(`Action appliquée sur le ticket #${ticketId}`, "success");
    }
    loadTickets();
  } catch (e) {
    showToast("Erreur: " + e.message, "error");
  }
}

async function reopenTicket(ticketId) {
  if (!confirm(`Réouvrir le ticket #${ticketId} ?`)) return;
  try {
    await apiFetch(`/internal/ticket/${ticketId}/reopen`, { method: "POST", auth: true });
    showToast(`Ticket #${ticketId} réouvert`, "success");
    loadTickets();
  } catch (e) {
    showToast("Erreur: " + e.message, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// ORDERS
// ─────────────────────────────────────────────────────────────

async function loadOrders() {
  try {
    const data = await apiFetch(`/dashboard/orders/pending`, { auth: true });
    renderOrders(data.orders || []);
  } catch (e) {
    console.warn("Orders:", e.message);
  }
}

function renderOrders(orders, containerId = "orders-list") {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!orders.length) {
    container.innerHTML = `<div style="text-align:center;color:var(--text3);padding:40px;font-size:13px">✅ Aucune commande en attente</div>`;
    return;
  }

  container.innerHTML = orders.map((o) => {
    const orderKey = o.order_id || o.order_ref || o.id;
    return `
    <div class="order-card" data-order-key="${escAttr(orderKey)}">
      <div class="order-method-icon ${o.method === 'paypal' ? 'paypal' : o.method === 'giftcard' ? 'giftcard' : 'oxapay'}">
        ${o.method === 'paypal' 
          ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect><line x1="1" y1="10" x2="23" y2="10"></line></svg>` 
          : o.method === 'giftcard' 
            ? `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px"><polyline points="20 12 20 22 4 22 4 12"></polyline><rect x="2" y="7" width="20" height="5"></rect><line x1="12" y1="22" x2="12" y2="7"></line><path d="M12 7H7.5a2.5 2.5 0 0 1 0-5C11 2 12 7 12 7z"></path><path d="M12 7h4.5a2.5 2.5 0 0 0 0-5C13 2 12 7 12 7z"></path></svg>` 
            : `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;margin-right:4px"><rect x="3" y="11" width="18" height="11" rx="2" ry="2"></rect><path d="M7 11V7a5 5 0 0 1 10 0v4"></path></svg>`}
      </div>
      <div class="order-info">
        <div class="order-id">${escHtml(orderKey)}</div>
        <div class="order-user">${escHtml(o.username || "—")} <span class="mono-grey">#${o.user_id}</span></div>
        <div class="order-meta">${escHtml(o.method)} · ${escHtml(o.plan)} · ${timeAgo(o.created_at)}</div>
      </div>
      <div style="margin-right:8px;text-align:right">
        <div class="order-amount">${parseFloat(o.amount || 0).toFixed(2)}€</div>
        <span class="pill pending" style="font-size:9px">EN ATTENTE</span>
      </div>
      <div class="order-actions">
        <button class="btn btn-primary btn-sm" data-order-action="set-status" data-order-id="${escAttr(orderKey)}" data-status="paid" type="button" title="Valider">✅</button>
        <button class="btn btn-yellow btn-sm" data-order-action="set-status" data-order-id="${escAttr(orderKey)}" data-status="partial" type="button" title="Montant incomplet">⚠️</button>
        <button class="btn btn-red btn-sm" data-order-action="set-status" data-order-id="${escAttr(orderKey)}" data-status="rejected" type="button" title="Rejeter">❌</button>
      </div>
    </div>`;
  }).join("");
}

async function validateOrder(btn, orderId, status) {
  const labels = { paid: "valider", partial: "marquer comme incomplet", rejected: "rejeter" };
  if (!confirm(`Voulez-vous ${labels[status] || status} la commande ${orderId} ?`)) return;

  btn.disabled = true;
  const siblings = btn.parentElement.querySelectorAll("button");
  siblings.forEach((b) => (b.disabled = true));

  try {
    const endpointMap = { paid: "validate", partial: "partial", rejected: "reject" };
    const endpoint = endpointMap[status] || "status";
    
    await apiFetch(`/dashboard/orders/${encodeURIComponent(orderId)}/${endpoint}`, {
      method: "POST",
      auth: true,
      body: status === "rejected" ? { reason: "Refusé par l'admin" } : {},
    });

    const card = btn.closest(".order-card");
    if (card) {
      const pillClass = { paid: "paid", partial: "yellow", rejected: "rejected" }[status] || "";
      const label = { paid: "Payé ✅", partial: "Incomplet ⚠️", rejected: "Rejeté ❌" }[status] || status;
      card.querySelector(".order-actions").innerHTML = `<span class="pill ${pillClass}">${label}</span>`;
    }

    showToast(`Commande ${orderId} : ${labels[status]}`, "success");

    // Mettre à jour le badge
    const badge = document.querySelector('[data-badge="orders"]');
    if (badge) {
      const count = parseInt(badge.textContent) || 0;
      badge.textContent = Math.max(0, count - 1);
    }
  } catch (e) {
    showToast("Erreur: " + e.message, "error");
    siblings.forEach((b) => (b.disabled = false));
  }
}

// ─────────────────────────────────────────────────────────────
// SETTINGS
// ─────────────────────────────────────────────────────────────

function initSettingsTabs() {
  // Sub-category tabs inside Settings page
  const tabs = Array.from(document.querySelectorAll(".settings-tab[data-settings-tab]"));
  const panels = Array.from(document.querySelectorAll(".settings-panel[data-settings-panel]"));
  if (!tabs.length || !panels.length) return;

  function activate(tabName) {
    tabs.forEach((t) => {
      const on = t.dataset.settingsTab === tabName;
      t.classList.toggle("active", on);
      t.setAttribute("aria-selected", on ? "true" : "false");
    });
    panels.forEach((p) => p.classList.toggle("active", p.dataset.settingsPanel === tabName));
  }

  tabs.forEach((t) => t.addEventListener("click", () => activate(t.dataset.settingsTab)));

  // Ticket open type: button vs select
  const openType = document.getElementById("settings-ticket-open-type");
  const syncOpenTypeVisibility = () => {
    const mode = openType?.value || "button";
    document.querySelectorAll("[data-open-type]").forEach((el) => {
      el.style.display = el.dataset.openType === mode ? "" : "none";
    });
  };
  if (openType) {
    openType.addEventListener("change", syncOpenTypeVisibility);
    syncOpenTypeVisibility();
  }

  // Preview / Deploy
  const previewBtn = document.getElementById("settings-ticket-preview-btn");
  const deployBtn = document.getElementById("settings-ticket-deploy-btn");
  const deleteBtn = document.getElementById("settings-ticket-delete-btn");

  const buildTicketOpenPayload = () => {
    const channelRaw = normalizeSnowflake(document.getElementById("settings-ticket-open-channel")?.value || "");
    const payload = {
      ticket_open_channel_id: channelRaw,
      ticket_open_message: (document.getElementById("settings-ticket-open-message")?.value || "").trim(),
      ticket_selector_enabled: (document.getElementById("settings-ticket-open-type")?.value || "button") === "select",
      ticket_button_label: (document.getElementById("settings-ticket-button-label")?.value || "").trim(),
      ticket_button_style: (document.getElementById("settings-ticket-button-style")?.value || "primary").trim(),
      ticket_button_emoji: (document.getElementById("settings-ticket-button-emoji")?.value || "").trim(),
      ticket_selector_placeholder: (document.getElementById("settings-ticket-selector-placeholder")?.value || "").trim(),
      ticket_selector_options: (document.getElementById("settings-ticket-selector-options")?.value || "").trim(),
    };
    return payload;
  };

  if (previewBtn) {
    previewBtn.addEventListener("click", () => {
      const p = buildTicketOpenPayload();
      let note = "";
      if (p.ticket_selector_enabled) {
        note = "Sélecteur activé. Options JSON: " + (p.ticket_selector_options ? "OK" : "VIDE");
      } else {
        note = "Bouton: " + (p.ticket_button_label || "(label vide)") + " · style=" + (p.ticket_button_style || "primary");
      }
      showToast("Prévisualisation: " + note, "info");
    });
  }

  if (deployBtn) {
    deployBtn.addEventListener("click", async () => {
      if (!state.currentGuild) return showToast("Aucun serveur sélectionné", "warn");
      const guildId = state.currentGuild.id;
      const payload = buildTicketOpenPayload();
      if (!payload.ticket_open_channel_id) return showToast("Channel d'ouverture manquant", "warn");
      deployBtn.disabled = true;
      deployBtn.textContent = "Déploiement…";
      try {
        await apiPost(`/internal/guild/${guildId}/tickets/open-message/deploy`, payload);
        showToast("Message d'ouverture déployé ✅", "success");
      } catch (e) {
        showToast("Erreur déploiement: " + e.message, "error");
      } finally {
        deployBtn.disabled = false;
        deployBtn.textContent = "Déployer dans le channel";
      }
    });
  }

  if (deleteBtn) {
    deleteBtn.addEventListener("click", async () => {
      if (!state.currentGuild) return showToast("Aucun serveur sélectionné", "warn");
      if (!confirm("Supprimer le message d'ouverture déjà déployé ?")) return;
      deleteBtn.disabled = true;
      deleteBtn.textContent = "Suppression…";
      try {
        await apiPost(`/internal/guild/${state.currentGuild.id}/tickets/open-message/delete`, {});
        showToast("Suppression demandée ✅", "success");
      } catch (e) {
        showToast("Erreur suppression: " + e.message, "error");
      } finally {
        deleteBtn.disabled = false;
        deleteBtn.textContent = "Supprimer le message";
      }
    });
  }

  const welcomeUserInput = document.getElementById("settings-ticket-welcome-message-user");
  const welcomeStaffInput = document.getElementById("settings-ticket-welcome-message-staff");
  const syncWelcomePreview = () => renderTicketWelcomePreview();
  [welcomeUserInput, welcomeStaffInput].forEach((el) => {
    if (el) el.addEventListener("input", syncWelcomePreview);
  });
  syncWelcomePreview();
}

function renderTemplatePreview(template, vars) {
  return String(template || "").replace(/\{([a-z_]+)\}/gi, (_, rawKey) => {
    const key = String(rawKey || "").toLowerCase();
    return Object.prototype.hasOwnProperty.call(vars, key) ? vars[key] : `{${rawKey}}`;
  });
}

function renderTicketWelcomePreview() {
  const userEl = document.getElementById("settings-ticket-welcome-preview-user");
  const staffEl = document.getElementById("settings-ticket-welcome-preview-staff");
  if (!userEl || !staffEl) return;

  const vars = {
    ticket_id: "#1842",
    user_mention: "@Jordan",
    user_language: "Français",
    staff_language: "Anglais",
    assigned_staff: "Non assigné",
    status: "Ouvert",
  };

  const userTemplate = (document.getElementById("settings-ticket-welcome-message-user")?.value || "").trim();
  const staffTemplate = (document.getElementById("settings-ticket-welcome-message-staff")?.value || "").trim();

  userEl.textContent = renderTemplatePreview(
    userTemplate || "Hello {user_mention}, tell us what happened and we will assist you shortly.",
    vars
  );
  staffEl.textContent = renderTemplatePreview(
    staffTemplate || "Staff note: reply in {staff_language}. Assigned: {assigned_staff}.",
    vars
  );
}

async function loadSettings() {
  if (!state.currentGuild) return;
  const guildId = state.currentGuild.id;

  try {
    const cfg = await apiFetch(`/internal/guild/${guildId}/config`, { auth: true });

    const fields = {
      "settings-support-channel": cfg.support_channel_id ? `#${cfg.support_channel_id}` : "",
      "settings-ticket-category": cfg.ticket_category_id ? cfg.ticket_category_id : "",
      "settings-staff-role": cfg.staff_role_id ? `@${cfg.staff_role_id}` : "",
      "settings-log-channel": cfg.log_channel_id ? `#${cfg.log_channel_id}` : "",

      // Ticket v0.4
      "settings-ticket-open-channel": cfg.ticket_open_channel_id ? `#${cfg.ticket_open_channel_id}` : "",
      "settings-ticket-open-message": cfg.ticket_open_message || "",
      "settings-ticket-button-label": cfg.ticket_button_label || "Ouvrir un ticket",
      "settings-ticket-button-style": cfg.ticket_button_style || "primary",
      "settings-ticket-button-emoji": cfg.ticket_button_emoji || "",
      "settings-ticket-selector-placeholder": cfg.ticket_selector_placeholder || "Sélectionnez le type de ticket",
      "settings-ticket-selector-options": typeof cfg.ticket_selector_options === "string" ? cfg.ticket_selector_options : (cfg.ticket_selector_options ? JSON.stringify(cfg.ticket_selector_options, null, 2) : "[]"),
      "settings-ticket-welcome-message-user": cfg.ticket_welcome_message_user || cfg.ticket_welcome_message || "",
      "settings-ticket-welcome-message-staff": cfg.ticket_welcome_message_staff || cfg.ticket_welcome_message || "",
      "settings-ticket-take-label": cfg.ticket_take_label || "S'approprier le ticket",
      "settings-ticket-close-label": cfg.ticket_close_label || "Fermer le ticket",
      "settings-ticket-reopen-label": cfg.ticket_reopen_label || "Réouvrir",
      "settings-ticket-transcript-label": cfg.ticket_transcript_label || "Transcript",
      "settings-ticket-welcome-color": cfg.ticket_welcome_color || "#4DA6FF",
      "settings-ticket-max-open": (cfg.ticket_max_open ?? 1),
      "settings-staff-languages": typeof cfg.staff_languages_json === "string" ? cfg.staff_languages_json : (cfg.staff_languages_json ? JSON.stringify(cfg.staff_languages_json, null, 2) : "[]"),

      // AI custom v0.4
      "settings-ai-custom-prompt": cfg.ai_custom_prompt || "",
    };

    for (const [id, val] of Object.entries(fields)) {
      const el = document.getElementById(id);
      if (el) el.value = val;
    }

    const langSelect = document.getElementById("settings-default-lang");
    if (langSelect && cfg.default_language) langSelect.value = cfg.default_language;

    // Toggles (valeurs réelles)
    setToggleState("auto_translate", !!cfg.auto_translate);
    setToggleState("public_support", !!cfg.public_support);
    setToggleState("auto_transcript", !!cfg.auto_transcript);
    setToggleState("ai_moderation", !!cfg.ai_moderation);
    setToggleState("staff_suggestions", !!cfg.staff_suggestions);

    // Ticket / AI v0.4 toggles
    setToggleState("ticket_mention_staff", !!cfg.ticket_mention_staff);
    setToggleState("ticket_close_on_leave", !!cfg.ticket_close_on_leave);
    setToggleState("ai_prompt_enabled", !!cfg.ai_prompt_enabled);

    // Open type selector
    const openType = document.getElementById("settings-ticket-open-type");
    if (openType) openType.value = cfg.ticket_selector_enabled ? "select" : "button";
    // ensure visibility refresh
    try { document.getElementById("settings-ticket-open-type")?.dispatchEvent(new Event("change")); } catch (_) {}
    renderTicketWelcomePreview();

    // Deploy error display
    const errBox = document.getElementById("settings-ticket-deploy-error");
    const errText = document.getElementById("settings-ticket-deploy-error-text");
    const lastErr = (cfg.ticket_open_last_deploy_error || "").trim();
    if (errBox && errText) {
      if (lastErr) {
        errText.textContent = lastErr;
        errBox.style.display = "block";
      } else {
        errText.textContent = "";
        errBox.style.display = "none";
      }
    }

    // Plan actuel (valeur réelle via /stats)
    const planEl = document.getElementById("settings-current-plan");
    const priceEl = document.getElementById("settings-current-plan-price");
    if (state.currentGuild?.bot_present === false) {
      if (planEl) planEl.textContent = "Bot non installé";
      if (priceEl) priceEl.textContent = "";
    } else {
      try {
        const stats = await apiFetch(`/internal/guild/${guildId}/stats`, { auth: true });
        const plan = stats.current_plan || "free";
        state.guildMeta[guildId] = { ...(state.guildMeta[guildId] || {}), plan };
        updateServerPlanDisplay();
        if (planEl) planEl.textContent = formatPlanLabel(plan);
        if (priceEl) {
          priceEl.textContent =
            String(plan).toLowerCase() === "premium" ? "— 2€/mois" :
            String(plan).toLowerCase() === "pro" ? "— 5€/mois" : "";
        }
      } catch (_) {
        if (planEl) planEl.textContent = "—";
        if (priceEl) priceEl.textContent = "";
      }
    }
  } catch (e) {
    showToast("Erreur chargement config: " + e.message, "error");
  }
}

function setToggleState(key, on) {
  const el = document.querySelector(`.toggle-switch[data-setting-key="${key}"]`);
  if (!el) return;
  el.classList.toggle("on", !!on);
}

function getToggleState(key) {
  const el = document.querySelector(`.toggle-switch[data-setting-key="${key}"]`);
  return !!(el && el.classList.contains("on"));
}

function initSettingsSave() {
  const saveBtn = document.getElementById("settings-save-btn");
  if (!saveBtn) return;

  saveBtn.addEventListener("click", async () => {
    if (!state.currentGuild) return showToast("Aucun serveur sélectionné", "warn");

    saveBtn.textContent = "Sauvegarde…";
    saveBtn.disabled = true;

    const cfg = {
      name: state.currentGuild.name || null,
      default_language: document.getElementById("settings-default-lang")?.value || "en",
      auto_translate: getToggleState("auto_translate"),
      public_support: getToggleState("public_support"),
      auto_transcript: getToggleState("auto_transcript"),
      ai_moderation: getToggleState("ai_moderation"),
      staff_suggestions: getToggleState("staff_suggestions"),

      // Ticket v0.4
      ticket_open_message: (document.getElementById("settings-ticket-open-message")?.value || "").trim(),
      ticket_button_label: (document.getElementById("settings-ticket-button-label")?.value || "").trim() || "Ouvrir un ticket",
      ticket_button_style: (document.getElementById("settings-ticket-button-style")?.value || "primary").trim(),
      ticket_button_emoji: (document.getElementById("settings-ticket-button-emoji")?.value || "").trim(),
      ticket_welcome_message: (document.getElementById("settings-ticket-welcome-message-user")?.value || "").trim(),
      ticket_welcome_message_user: (document.getElementById("settings-ticket-welcome-message-user")?.value || "").trim(),
      ticket_welcome_message_staff: (document.getElementById("settings-ticket-welcome-message-staff")?.value || "").trim(),
      ticket_take_label: (document.getElementById("settings-ticket-take-label")?.value || "").trim() || "S'approprier le ticket",
      ticket_close_label: (document.getElementById("settings-ticket-close-label")?.value || "").trim() || "Fermer le ticket",
      ticket_reopen_label: (document.getElementById("settings-ticket-reopen-label")?.value || "").trim() || "Réouvrir",
      ticket_transcript_label: (document.getElementById("settings-ticket-transcript-label")?.value || "").trim() || "Transcript",
      ticket_welcome_color: (document.getElementById("settings-ticket-welcome-color")?.value || "#4DA6FF").trim(),
      ticket_selector_enabled: (document.getElementById("settings-ticket-open-type")?.value || "button") === "select",
      ticket_selector_placeholder: (document.getElementById("settings-ticket-selector-placeholder")?.value || "").trim(),
      ticket_selector_options: (document.getElementById("settings-ticket-selector-options")?.value || "").trim(),
      ticket_mention_staff: getToggleState("ticket_mention_staff"),
      ticket_close_on_leave: getToggleState("ticket_close_on_leave"),
      ticket_max_open: parseInt(document.getElementById("settings-ticket-max-open")?.value || "1", 10),
      staff_languages_json: (document.getElementById("settings-staff-languages")?.value || "").trim(),

      // AI custom v0.4
      ai_custom_prompt: (document.getElementById("settings-ai-custom-prompt")?.value || "").trim(),
      ai_prompt_enabled: getToggleState("ai_prompt_enabled"),
    };

    // Ne pas utiliser parseInt sur les snowflakes Discord (> 2^53-1 en JS).
    cfg.support_channel_id = normalizeSnowflake(document.getElementById("settings-support-channel")?.value || "");
    cfg.ticket_category_id = normalizeSnowflake(document.getElementById("settings-ticket-category")?.value || "");
    cfg.staff_role_id = normalizeSnowflake(document.getElementById("settings-staff-role")?.value || "");
    cfg.log_channel_id = normalizeSnowflake(document.getElementById("settings-log-channel")?.value || "");
    cfg.ticket_open_channel_id = normalizeSnowflake(document.getElementById("settings-ticket-open-channel")?.value || "");

    try {
      await apiPut(`/internal/guild/${state.currentGuild.id}/config`, cfg);
      showToast("Configuration sauvegardée ✅", "success");
    } catch (e) {
      showToast("Erreur: " + e.message, "error");
    } finally {
      saveBtn.textContent = "Sauvegarder";
      saveBtn.disabled = false;
    }
  });
}

// ─────────────────────────────────────────────────────────────
// KNOWLEDGE BASE
// ─────────────────────────────────────────────────────────────

let kbEntries = [];
let kbLimit = 0;

async function loadKB() {
  if (!state.currentGuild) return;
  const guildId = state.currentGuild.id;

  try {
    const data = await apiFetch(`/internal/guild/${guildId}/kb`, { auth: true });
    kbEntries = data.entries || [];
    kbLimit = data.limit ?? 0;
    renderKBEntries();
    updateKBCounter();
  } catch (e) {
    console.warn("KB:", e.message);
  }
}

function renderKBEntries() {
  const container = document.getElementById("kb-entries");
  if (!container) return;

  if (!kbEntries.length) {
    container.innerHTML = `<div style="text-align:center;color:var(--text3);padding:24px;font-size:13px">Aucune entrée. Cliquez sur "+ Ajouter" pour commencer.</div>`;
    return;
  }

  container.innerHTML = kbEntries.map((e) => `
    <div class="kb-item" data-kb-id="${e.id}">
      <div class="kb-question">${escHtml(e.question)}</div>
      <div class="kb-answer">${escHtml(e.answer)}</div>
      <div class="kb-footer">
        <button class="btn btn-ghost btn-sm" data-kb-action="edit" data-kb-id="${escAttr(e.id)}" type="button">Modifier</button>
        <button class="btn btn-red btn-sm" data-kb-action="delete" data-kb-id="${escAttr(e.id)}" type="button">Supprimer</button>
      </div>
    </div>`).join("");
}

function updateKBCounter() {
  const count = kbEntries.length;
  const limit = kbLimit;
  const limitLabel = limit == null ? "Illimité" : String(limit);
  const el = document.querySelector(".card-meta[data-kb-counter]");
  if (el) el.textContent = `${count} / ${limitLabel} ENTRÉES`;
  document.querySelectorAll("[data-kb-counter]").forEach((node) => {
    node.textContent = `${count} / ${limitLabel}`;
  });
  const fill = document.querySelector(".progress-fill[data-kb-fill]");
  if (fill) {
    const pct = !limit ? 0 : Math.min(100, Math.round((count / limit) * 100));
    fill.style.width = pct + "%";
  }
}

function initKB() {
  const addBtn = document.getElementById("kb-add-btn");
  const form = document.getElementById("kb-form");
  if (addBtn && form) {
    addBtn.addEventListener("click", () => {
      form.style.display = form.style.display === "none" ? "block" : "none";
      document.getElementById("kb-form-id").value = "";
      document.getElementById("kb-form-q").value = "";
      document.getElementById("kb-form-a").value = "";
      document.getElementById("kb-form-title").textContent = "Nouvelle entrée";
    });
  }

  const saveBtn = document.getElementById("kb-save-btn");
  if (saveBtn) saveBtn.addEventListener("click", saveKBEntry);
}

async function saveKBEntry() {
  if (!state.currentGuild) return showToast("Aucun serveur sélectionné", "warn");

  const id = document.getElementById("kb-form-id")?.value;
  const question = document.getElementById("kb-form-q")?.value?.trim();
  const answer = document.getElementById("kb-form-a")?.value?.trim();

  if (!question || !answer) return showToast("Question et réponse requis", "warn");

  try {
    if (id) {
      await apiPut(`/internal/guild/${state.currentGuild.id}/kb/${id}`, { question, answer });
      showToast("Entrée mise à jour ✅", "success");
    } else {
      await apiPost(`/internal/guild/${state.currentGuild.id}/kb`, { question, answer });
      showToast("Entrée ajoutée ✅", "success");
    }
    document.getElementById("kb-form").style.display = "none";
    await loadKB();
  } catch (e) {
    showToast("Erreur: " + e.message, "error");
  }
}

function editKBEntry(id) {
  const entry = kbEntries.find((e) => e.id === id);
  if (!entry) return;

  document.getElementById("kb-form-id").value = id;
  document.getElementById("kb-form-q").value = entry.question;
  document.getElementById("kb-form-a").value = entry.answer;
  document.getElementById("kb-form-title").textContent = "Modifier l'entrée";
  document.getElementById("kb-form").style.display = "block";
  document.getElementById("kb-form").scrollIntoView({ behavior: "smooth" });
}

async function deleteKBEntry(id) {
  if (!confirm("Supprimer cette entrée ?")) return;
  try {
    await apiFetch(`/internal/guild/${state.currentGuild.id}/kb/${id}`, { method: "DELETE", auth: true });
    showToast("Entrée supprimée", "success");
    await loadKB();
  } catch (e) {
    showToast("Erreur: " + e.message, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// SUPER ADMIN
// ─────────────────────────────────────────────────────────────

async function loadSuperAdminData() {
  // Indicateur de chargement
  const ordersContainer = document.getElementById("admin-orders-list");
  if (ordersContainer) ordersContainer.innerHTML = `<div style="color:var(--text3);font-size:13px;text-align:center;padding:24px">Chargement…</div>`;

  const [globalStats, pendingOrders, botStatus] = await Promise.allSettled([
    apiFetch("/dashboard/stats", { auth: true }),
    apiFetch("/dashboard/orders/pending", { auth: true }),
    apiFetch("/internal/bot/status", { auth: true }),
  ]);

  // Stats globales
  if (globalStats.status === "fulfilled") {
    const s = globalStats.value;
    setStatValue("admin-stat-servers", s.total_guilds ?? "—");
    setStatValue("admin-stat-users", s.total_users ?? "—");
    setStatValue("admin-stat-tickets", s.tickets_today ?? "—");
    setStatValue(
      "admin-stat-revenue",
      s.revenue_month == null ? "—" : `${Number(s.revenue_month).toFixed(2)}€`
    );
    // Badge orders dans la sidebar
    const badge = document.querySelector('[data-badge="orders"]');
    if (badge && s.orders_pending != null) badge.textContent = s.orders_pending;
  } else {
    console.warn("SuperAdmin stats error:", globalStats.reason?.message);
  }

  // Commandes en attente
  if (pendingOrders.status === "fulfilled") {
    renderOrders(pendingOrders.value.orders || [], "admin-orders-list");
  } else {
    if (ordersContainer) ordersContainer.innerHTML = `<div style="color:var(--red);font-size:13px;text-align:center;padding:24px">❌ Erreur chargement commandes</div>`;
  }

  // Statut bot (uptime + version + latency + channels)
  if (botStatus.status === "fulfilled") {
    const b = botStatus.value;
    setStatValue("admin-bot-uptime", formatUptime(b.uptime_sec));
    setStatValue("admin-bot-version", b.version || "—");
    setStatValue("admin-bot-latency", b.latency_ms != null ? `${b.latency_ms}ms` : "—");
    setStatValue("admin-bot-channels", b.channel_count ?? "—");
    setStatValue("admin-bot-shards", `${b.shard_count ?? 1} shard${(b.shard_count ?? 1) > 1 ? "s" : ""}`);

    if (b.started_at) {
      try {
        const startDate = new Date(b.started_at);
        setStatValue("admin-bot-started", `Démarré: ${startDate.toLocaleString("fr-FR")}`);
      } catch (_) {
        setStatValue("admin-bot-started", `Démarré: ${b.started_at}`);
      }
    }
  }
}

async function adminActivateSub() {
  const guildId = normalizeSnowflake(document.getElementById("admin-guild-id")?.value?.trim());
  const plan = document.getElementById("admin-plan")?.value || "premium";
  if (!guildId) return showToast("Guild ID invalide", "warn");

  try {
    await apiPost("/internal/admin/activate-sub", { guild_id: guildId, plan, duration_days: 30 });
    showToast(`Abonnement ${plan} activé pour ${guildId}`, "success");
  } catch (e) {
    showToast("Erreur: " + e.message, "error");
  }
}

async function adminRevokeSub() {
  const guildId = normalizeSnowflake(document.getElementById("admin-guild-id")?.value?.trim());
  if (!guildId) return showToast("Guild ID invalide", "warn");

  try {
    await apiPost("/internal/revoke-sub", { guild_id: guildId });
    showToast(`Abonnement révoqué pour ${guildId}`, "success");
  } catch (e) {
    showToast("Erreur: " + e.message, "error");
  }
}

// ─────────────────────────────────────────────────────────────
// SERVER SELECTOR DROPDOWN
// ─────────────────────────────────────────────────────────────

function initServerSelector() {
  const display = document.getElementById("server-selector-display");
  const dropdown = document.getElementById("server-dropdown");
  if (!display) return;

  display.addEventListener("click", () => {
    if (!dropdown) return;
    dropdown.style.display = dropdown.style.display === "none" ? "block" : "none";
  });

  document.addEventListener("click", (e) => {
    if (dropdown && !display.contains(e.target) && !dropdown.contains(e.target)) {
      dropdown.style.display = "none";
    }
  });
}

function selectGuild(guildId) {
  const guild = state.guilds.find((g) => g.id === guildId);
  if (!guild) return;

  state.currentGuild = guild;
  populateServerSelector();
  ensureGuildMeta(guild.id);

  const dropdown = document.getElementById("server-dropdown");
  if (dropdown) dropdown.style.display = "none";

  // Recharger la page courante avec le nouveau serveur
  navigateTo(state.currentPage);
}

// ─────────────────────────────────────────────────────────────
// UI: PROGRESS BARS
// ─────────────────────────────────────────────────────────────

function initProgressBars() {
  animateProgressBars(document);
}

function animateProgressBars(root) {
  root.querySelectorAll(".progress-fill[data-width]").forEach((el) => {
    setTimeout(() => {
      el.style.width = el.dataset.width;
    }, 100);
  });
  root.querySelectorAll(".key-fill[data-width]").forEach((el) => {
    setTimeout(() => {
      el.style.width = el.dataset.width;
    }, 150);
  });
}

// ─────────────────────────────────────────────────────────────
// UI: BAR CHART (tickets 7 jours)
// ─────────────────────────────────────────────────────────────

function initBarChart() {
  const chart = document.getElementById("bar-chart");
  if (!chart) return;
  // Render an empty chart; real data comes from /internal/guild/{id}/stats.
  renderBarChart(chart, [
    { day: "—", val: 0 },
    { day: "—", val: 0 },
    { day: "—", val: 0 },
    { day: "—", val: 0 },
    { day: "—", val: 0 },
    { day: "—", val: 0 },
    { day: "—", val: 0 },
  ]);
}

function renderBarChart(container, data) {
  const max = Math.max(...data.map((d) => d.val), 1);
  container.innerHTML = data
    .map(
      (d) => `
    <div class="bar-group">
      <div class="bar-value">${Number(d.val)}</div>
      <div class="bar" style="height:0" data-height="${Math.round((d.val / max) * 100)}%"></div>
      <div class="bar-label">${escHtml(d.day)}</div>
    </div>`
    )
    .join("");

  setTimeout(() => {
    container.querySelectorAll(".bar[data-height]").forEach((bar) => {
      bar.style.height = bar.dataset.height;
    });
  }, 100);
}

// ─────────────────────────────────────────────────────────────
// UI: TOGGLE SWITCHES
// ─────────────────────────────────────────────────────────────

function initToggleSwitches() {
  document.querySelectorAll(".toggle-switch:not([style*='pointer-events:none'])").forEach((toggle) => {
    toggle.addEventListener("click", () => {
      toggle.classList.toggle("on");
    });
  });
}

// ─────────────────────────────────────────────────────────────
// UI: TOAST
// ─────────────────────────────────────────────────────────────

function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.style.cssText =
      "position:fixed;bottom:24px;right:24px;z-index:99999;display:flex;flex-direction:column;gap:8px;";
    document.body.appendChild(container);
  }

  const colors = {
    success: "var(--accent)",
    error: "var(--red)",
    warn: "var(--yellow)",
    info: "var(--blue)",
  };

  const toast = document.createElement("div");
  toast.style.cssText = `
    padding:10px 16px;border-radius:8px;font-size:13px;font-weight:500;
    background:var(--bg2);border:1px solid ${colors[type] || colors.info};
    color:var(--text);box-shadow:0 4px 20px rgba(0,0,0,0.4);
    display:flex;align-items:center;gap:8px;
    animation:slideIn .2s ease;max-width:320px;
  `;
  const icons = {
    success: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>`,
    error: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`,
    warn: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
    info: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`
  };

  toast.innerHTML = `<span style="color:${colors[type]};display:flex;align-items:center">
    ${icons[type] || icons.info}
  </span> <span>${escHtml(message)}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transition = "opacity .3s";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ─────────────────────────────────────────────────────────────
// HELPERS
// ─────────────────────────────────────────────────────────────

function escHtml(str) {
  if (str === null || str === undefined) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escAttr(str) {
  // Same escaping as HTML text, plus single-quote (handled in escHtml).
  return escHtml(str);
}

function timeAgo(dateStr) {
  if (!dateStr) return "—";
  const diff = Date.now() - new Date(dateStr).getTime();
  const m = Math.floor(diff / 60000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h}h`;
  return `il y a ${Math.floor(h / 24)}j`;
}

function updateTopbarDate() {
  const el = document.querySelector(".page-sub");
  if (!el) return;
  const now = new Date();
  const opts = { weekday: "long", year: "numeric", month: "long", day: "numeric" };
  el.textContent = now.toLocaleDateString("fr-FR", opts);
}

// Injecter l'animation CSS si absente
if (!document.getElementById("dashboard-anim-style")) {
  const style = document.createElement("style");
  style.id = "dashboard-anim-style";
  style.textContent = `
    @keyframes slideIn { from { transform: translateX(30px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
    .bar { transition: height 0.6s cubic-bezier(.34,1.56,.64,1); border-radius: 4px 4px 0 0; background: var(--accent); }
    .progress-fill { transition: width 0.8s cubic-bezier(.34,1.56,.64,1); }
    .key-fill { transition: width 0.7s ease; }
    .nav-item[data-ticket-filter].active { background: var(--accent-dim); color: var(--accent); }
  `;
  document.head.appendChild(style);
}
