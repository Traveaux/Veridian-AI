# VERIDIAN AI — MASTER PLAN AGENT v2.1
> Document optimisé pour agent de code IA. Chaque tâche est autonome et exécutable.
> Date: 2026-04 | Priorité: P0 (critique) > P1 (important) > P2 (amélioration)

---

## RÈGLES GÉNÉRALES POUR L'AGENT

- Toujours utiliser `bot/utils/i18n.py` pour les textes du bot
- Toujours utiliser `bot/utils/embed_style.py` `style_embed()` pour les embeds
- Les couleurs d'embed suivent la hiérarchie: `COLOR_SUCCESS(0x2DFF8F) > COLOR_NOTICE(0x00E676) > COLOR_WARNING(0x008037) > COLOR_CRITICAL(0x004D40)`
- Tout texte du bot doit être traduit via `i18n.get(key, locale)` — la locale vient de `interaction.locale` ou `ticket.user_language`
- Le bot n'envoie **que** des embeds, jamais de texte brut
- Stripe est **interdit** — uniquement OxaPay + PayPal + cartes cadeaux

---

## SECTION 1 — CORRECTIONS IMMÉDIATES (P0)

### TÂCHE 1.1 — Supprimer la ligne verte animée du site web

**Fichier:** `web/index.html`

**Problème:** Le `<canvas id="grid-trace">` avec animation JS est distrayant et non professionnel.

**Action:**
```html
<!-- SUPPRIMER ces lignes dans web/index.html -->
<canvas id="grid-trace" style="position:fixed;inset:0;pointer-events:none;z-index:0;"></canvas>

<!-- SUPPRIMER dans web/js/main.js le bloc entier : -->
// ── GRID TRACE ──
(function () {
  const canvas = document.getElementById('grid-trace');
  // ... tout le bloc jusqu'à })();
```

**Résultat attendu:** Page web propre sans animation distrayante.

---

### TÂCHE 1.2 — Changer les boîtes bleues du dashboard en vert

**Fichier:** `web/css/dashboard.css`

**Problème:** Variables `--blue` et `--blue-dim` créent une incohérence visuelle (le reste est vert).

**Action — remplacer dans dashboard.css:**
```css
/* AVANT */
.billing-modal-tab.active {
  color: var(--text);
  border-color: rgba(77, 166, 255, 0.4);
  background: rgba(77, 166, 255, 0.12);
}
.billing-choice.active {
  border-color: rgba(77, 166, 255, 0.45);
  background: rgba(77, 166, 255, 0.1);
}

/* APRÈS */
.billing-modal-tab.active {
  color: var(--accent);
  border-color: rgba(45, 255, 143, 0.35);
  background: var(--accent-dim);
}
.billing-choice.active {
  border-color: rgba(45, 255, 143, 0.35);
  background: var(--accent-dim);
  box-shadow: 0 0 0 1px rgba(45,255,143,0.1) inset;
}
```

**Aussi remplacer toutes les occurrences `rgba(77, 166, 255` par `rgba(45, 255, 143`** dans dashboard.css.

---

### TÂCHE 1.3 — Messages du bot dans la langue de l'utilisateur

**Fichier:** `bot/utils/embed_style.py`, tous les cogs

**Problème:** Les embeds du bot ne s'adaptent pas à la langue Discord de l'utilisateur.

**Action — modifier `send_localized_embed` dans embed_style.py:**
```python
async def send_localized_embed(
    ctx_or_interaction,
    key: str,
    description_key: str = None,
    locale: str = None,
    color: discord.Color = None,
    ephemeral: bool = False,
    view = None,
    **kwargs
) -> discord.Message | None:
    from bot.utils.i18n import i18n
    
    # Priorité: locale forcée > locale Discord de l'utilisateur > fallback
    if not locale:
        if isinstance(ctx_or_interaction, discord.Interaction):
            # Récupérer la locale Discord de l'utilisateur
            user_locale = str(getattr(ctx_or_interaction, 'locale', '') or '')
            guild_locale = str(getattr(ctx_or_interaction.guild, 'preferred_locale', '') or '') if ctx_or_interaction.guild else ''
            locale = _normalize_lang(user_locale or guild_locale, 'fr')
        else:
            locale = 'fr'
    
    title = i18n.get(key, locale, **kwargs)
    desc = i18n.get(description_key, locale, **kwargs) if description_key else None
    
    if title == key:
        title = None
        desc = i18n.get(key, locale, **kwargs)
    
    embed = discord.Embed(title=title, description=desc)
    if color:
        embed.color = color
    style_embed(embed)
    # ... suite inchangée
```

**Dans chaque cog, récupérer la locale avant usage:**
```python
# Pattern à appliquer partout
locale = _normalize_lang(str(interaction.locale or ''), 'fr')
embed = discord.Embed(
    title=i18n.get("tickets.welcome_title", locale),
    description=i18n.get("tickets.welcome_desc", locale),
)
```

---

### TÂCHE 1.4 — Tous les embeds du bot en vert gradué

**Fichier:** `bot/config.py`, `bot/utils/embed_style.py`

**Problème:** Les embeds utilisent des couleurs incohérentes.

**Hiérarchie de couleurs (du plus clair au plus sombre = moins important à plus urgent):**
```python
# bot/config.py — remplacer les couleurs
COLOR_SUCCESS  = 0x2DFF8F  # Vert vif — succès, confirmation
COLOR_NOTICE   = 0x00E676  # Vert moyen — information
COLOR_WARNING  = 0x00A652  # Vert foncé — avertissement important
COLOR_CRITICAL = 0x004D40  # Vert très foncé — critique, erreur grave
```

**Dans `style_embed()`, forcer la couleur par défaut:**
```python
def style_embed(embed: discord.Embed) -> discord.Embed:
    # ... nettoyage existant ...
    if not embed.color or embed.color.value == 0:
        embed.color = discord.Color(COLOR_SUCCESS)
    return embed
```

---

### TÂCHE 1.5 — Le bot n'envoie QUE des embeds

**Fichier:** Tous les cogs (`bot/cogs/*.py`)

**Règle:** Remplacer TOUT `await channel.send("texte brut")` par un embed.

**Pattern à appliquer:**
```python
# INTERDIT
await interaction.response.send_message("Ticket créé !", ephemeral=True)

# OBLIGATOIRE
embed = discord.Embed(
    title=i18n.get("tickets.created_title", locale),
    description=i18n.get("tickets.created_desc", locale, channel=ticket_channel.mention),
    color=discord.Color(COLOR_SUCCESS)
)
style_embed(embed)
await interaction.response.send_message(embed=embed, ephemeral=True)
```

---

## SECTION 2 — SYSTÈME DE TICKETS MODERNISÉ (P0)

### TÂCHE 2.1 — Welcome embed dans la langue du client

**Fichier:** `bot/cogs/tickets.py` — méthode `_build_ticket_welcome_embed`

**Problème:** L'embed de bienvenue est en français/anglais, pas dans la langue détectée de l'utilisateur.

**Action:**
```python
def _build_ticket_welcome_embed(self, *, ticket_id, user_id, user_language, staff_language, guild_config=None, ...):
    # Langue pour le message utilisateur = langue détectée de l'utilisateur
    user_locale = _normalize_lang(user_language, 'en')
    # Langue pour le message staff = langue du staff
    staff_locale = _normalize_lang(staff_language, 'en')
    cfg = guild_config or {}
    
    # Message utilisateur dans SA langue
    user_msg = (cfg.get("ticket_welcome_message_user") or "").strip()
    if not user_msg:
        user_msg = i18n.get("tickets.default_welcome_user", user_locale)
    
    # Message staff dans la langue staff
    staff_msg = (cfg.get("ticket_welcome_message_staff") or "").strip()
    if not staff_msg:
        staff_msg = i18n.get("tickets.default_welcome_staff", staff_locale)
    
    # L'embed principal utilise la langue de l'UTILISATEUR
    embed = discord.Embed(
        title=i18n.get("tickets.welcome_title", user_locale),
        color=discord.Color(COLOR_NOTICE),
    )
    # ... reste inchangé
```

**Ajouter dans `bot/locales/en.json` et `fr.json`:**
```json
{
  "tickets": {
    "default_welcome_user": "Hello {user_mention}! Describe your issue and we will help you.",
    "default_welcome_staff": "New ticket from {user_mention}. User language: {user_language}."
  }
}
```

---

### TÂCHE 2.2 — Notification dans les logs à l'ouverture d'un ticket

**Fichier:** `bot/cogs/tickets.py` — méthode `open_ticket`

**Action — ajouter après création du ticket:**
```python
# Notification dans le channel de logs
log_channel_id = guild_config.get("log_channel_id")
if log_channel_id:
    log_channel = interaction.guild.get_channel(int(log_channel_id))
    if log_channel:
        staff_locale = _normalize_lang(staff_language, 'fr')
        log_embed = discord.Embed(
            title=i18n.get("tickets.log_opened_title", staff_locale),
            color=discord.Color(COLOR_NOTICE),
        )
        log_embed.add_field(
            name=i18n.get("tickets.log_user", staff_locale),
            value=f"{interaction.user.mention} (`{interaction.user.id}`)",
            inline=True
        )
        log_embed.add_field(
            name=i18n.get("tickets.log_channel", staff_locale),
            value=ticket_channel.mention,
            inline=True
        )
        log_embed.add_field(
            name=i18n.get("tickets.log_language", staff_locale),
            value=f"`{user_language or 'auto'}`",
            inline=True
        )
        # Motif IA (si disponible après analyse)
        if topic and topic.strip():
            log_embed.add_field(
                name=i18n.get("tickets.log_topic", staff_locale),
                value=topic[:200],
                inline=False
            )
        log_embed.timestamp = discord.utils.utcnow()
        style_embed(log_embed)
        await log_channel.send(embed=log_embed)
```

**Clés i18n à ajouter:**
```json
{
  "tickets": {
    "log_opened_title": "New ticket opened",
    "log_user": "User",
    "log_channel": "Channel",
    "log_language": "Language",
    "log_topic": "AI-detected reason"
  }
}
```

---

### TÂCHE 2.3 — Satisfaction rating à la fermeture du ticket

**Fichier:** `bot/cogs/tickets.py`, `database/schema.sql`

**DB — table déjà présente `vai_ticket_satisfaction`. Si manquante:**
```sql
CREATE TABLE IF NOT EXISTS vai_ticket_satisfaction (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id   INT NOT NULL,
    user_id     BIGINT NOT NULL,
    rating      TINYINT NOT NULL COMMENT '1-5',
    comment     TEXT,
    responded_at TIMESTAMP NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ticket (ticket_id),
    KEY idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Bot — envoyer DM avec boutons de notation après fermeture:**
```python
# Dans _post_close_outputs, après envoi du résumé à l'utilisateur:
async def _send_satisfaction_dm(self, ticket: dict, user: discord.abc.User):
    user_locale = _normalize_lang(ticket.get("user_language"), "en")
    embed = discord.Embed(
        title=i18n.get("tickets.rating_title", user_locale),
        description=i18n.get("tickets.rating_desc", user_locale),
        color=discord.Color(COLOR_NOTICE)
    )
    style_embed(embed)
    view = SatisfactionView(ticket["id"], self.bot, user_locale)
    try:
        await user.send(embed=embed, view=view)
    except discord.Forbidden:
        pass

class SatisfactionView(discord.ui.View):
    def __init__(self, ticket_id: int, bot, locale: str = "en"):
        super().__init__(timeout=86400)  # 24h
        self.ticket_id = ticket_id
        self.bot = bot
        self.locale = locale
        # Boutons 1-5 étoiles
        for i in range(1, 6):
            self.add_item(SatisfactionButton(i, ticket_id, bot, locale))

class SatisfactionButton(discord.ui.Button):
    def __init__(self, rating: int, ticket_id: int, bot, locale: str):
        stars = "⭐" * rating
        super().__init__(label=stars, style=discord.ButtonStyle.secondary, custom_id=f"sat:{ticket_id}:{rating}")
        self.rating = rating
        self.ticket_id = ticket_id
        self.bot = bot
        self.locale = locale
    
    async def callback(self, interaction: discord.Interaction):
        # Sauvegarder en DB
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vai_ticket_satisfaction (ticket_id, user_id, rating, responded_at) "
                "VALUES (%s, %s, %s, NOW()) ON DUPLICATE KEY UPDATE rating=%s, responded_at=NOW()",
                (self.ticket_id, interaction.user.id, self.rating, self.rating)
            )
        embed = discord.Embed(
            title=i18n.get("tickets.rating_thanks", self.locale),
            description=i18n.get("tickets.rating_saved", self.locale),
            color=discord.Color(COLOR_SUCCESS)
        )
        style_embed(embed)
        await interaction.response.edit_message(embed=embed, view=None)
```

**i18n à ajouter:**
```json
{
  "tickets": {
    "rating_title": "How was your support experience?",
    "rating_desc": "Rate your experience from 1 to 5 stars.",
    "rating_thanks": "Thank you for your feedback!",
    "rating_saved": "Your rating has been saved."
  }
}
```

---

### TÂCHE 2.4 — Fermer un ticket depuis le dashboard = fermer + supprimer sur Discord

**Fichier:** `api/routes/internal.py` — endpoint `POST /ticket/{ticket_id}/close`

**Action — modifier pour émettre une commande vers le bot:**
```python
@router.post("/ticket/{ticket_id}/close")
async def close_ticket_dashboard(ticket_id: int, request: Request):
    # ... vérifications existantes ...
    
    # Fermer en DB
    TicketModel.close(ticket_id, close_reason="Closed from dashboard")
    
    # Émettre un ordre de suppression du channel Discord
    # Via la table vai_pending_notifications avec type spécial
    # OU via une table vai_pending_actions
    ticket = TicketModel.get(ticket_id)
    if ticket and ticket.get("channel_id"):
        PendingNotificationModel.add_action(
            action_type="delete_channel",
            payload={"channel_id": ticket["channel_id"], "guild_id": ticket["guild_id"]}
        )
    
    return {"status": "success", "ticket_id": ticket_id, "ticket_status": "closed"}
```

**Ajouter table `vai_pending_actions`:**
```sql
CREATE TABLE IF NOT EXISTS vai_pending_actions (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    action_type VARCHAR(50) NOT NULL,
    payload_json JSON NOT NULL,
    attempts    INT DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_type (action_type),
    KEY idx_attempts (attempts)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Dans `bot/main.py` — boucle de traitement des actions:**
```python
@tasks.loop(seconds=15)
async def pending_actions_loop():
    """Traite les actions pendantes depuis l'API/dashboard."""
    try:
        from bot.db.models import PendingActionModel
        actions = PendingActionModel.list_pending(limit=10)
        for action in actions:
            if action["action_type"] == "delete_channel":
                payload = action["payload_json"]
                channel_id = payload.get("channel_id")
                if channel_id:
                    channel = bot.get_channel(int(channel_id))
                    if channel:
                        try:
                            await channel.delete(reason="Ticket closed from dashboard")
                        except Exception:
                            pass
                PendingActionModel.delete(action["id"])
    except Exception as e:
        logger.error(f"pending_actions_loop: {e}")
```

---

### TÂCHE 2.5 — Supprimer le salon après fermeture réussie d'un ticket

**Fichier:** `bot/cogs/tickets.py` — méthode `_finalize_ticket_close`

**Action — à la fin de `_finalize_ticket_close`:**
```python
async def _finalize_ticket_close(self, *, channel, ticket, closer, reason):
    # ... code existant ...
    
    # Après envoi des outputs: supprimer le channel après délai
    await asyncio.sleep(10)  # 10 secondes pour lire le résumé
    try:
        await channel.delete(reason=f"Ticket #{ticket['id']} closed — {reason[:50]}")
        logger.info(f"Channel ticket {ticket['id']} supprimé")
    except discord.NotFound:
        pass  # Déjà supprimé
    except discord.Forbidden:
        logger.warning(f"Permission manquante pour supprimer le channel du ticket {ticket['id']}")
    except Exception as e:
        logger.error(f"Erreur suppression channel ticket {ticket['id']}: {e}")
```

---

## SECTION 3 — SYSTÈME D'AVIS CLIENTS (P1)

### TÂCHE 3.1 — Table des avis en DB

```sql
CREATE TABLE IF NOT EXISTS vai_reviews (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         BIGINT NOT NULL,
    user_username   VARCHAR(100),
    guild_id        BIGINT,
    guild_name      VARCHAR(100),
    rating          TINYINT NOT NULL COMMENT '1-5',
    content         TEXT NOT NULL,
    is_approved     TINYINT(1) DEFAULT 0 COMMENT 'Approuvé par admin avant affichage',
    is_visible      TINYINT(1) DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_visible (is_visible),
    KEY idx_approved (is_approved),
    KEY idx_user (user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### TÂCHE 3.2 — API endpoint pour les avis

**Fichier:** `api/routes/internal.py`

```python
class ReviewCreateBody(BaseModel):
    rating: int  # 1-5
    content: str
    guild_id: Optional[int] = None

@router.post("/reviews", dependencies=[Depends(verify_internal_auth)])
async def create_review(body: ReviewCreateBody, request: Request):
    actor_id = getattr(request.state, 'user_id', None)
    if not actor_id:
        raise HTTPException(status_code=401, detail="Non authentifié")
    if body.rating < 1 or body.rating > 5:
        raise HTTPException(status_code=400, detail="Note entre 1 et 5")
    if len(body.content.strip()) < 20:
        raise HTTPException(status_code=400, detail="Avis trop court (min 20 chars)")
    
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO vai_reviews (user_id, user_username, guild_id, rating, content, is_approved) "
            "VALUES (%s, %s, %s, %s, %s, 0)",
            (actor_id, getattr(request.state, 'username', None), body.guild_id, body.rating, body.content.strip())
        )
    return {"status": "success", "message": "Review submitted for approval"}

@router.get("/reviews/public")
async def get_public_reviews(limit: int = 20):
    """Endpoint public pour le site web — pas d'auth requise."""
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id, user_username, guild_name, rating, content, created_at "
            "FROM vai_reviews WHERE is_approved=1 AND is_visible=1 "
            "ORDER BY created_at DESC LIMIT %s",
            (min(int(limit), 50),)
        )
        reviews = cursor.fetchall()
    return {"reviews": reviews, "total": len(reviews)}
```

---

### TÂCHE 3.3 — Formulaire d'avis dans le dashboard

**Fichier:** `web/dashboard.html` — ajouter dans la page KB ou une nouvelle page "Avis"

```html
<!-- Dans la sidebar, ajouter un item -->
<div class="nav-item" data-page="review">
  <svg class="nav-icon" viewBox="0 0 14 14" fill="none">
    <path d="M7 1l1.3 2.7L11 4.3l-2 2 .5 2.8L7 7.7 4.5 9.1 5 6.3 3 4.3l2.7-.6z" fill="currentColor" opacity=".7"/>
  </svg>
  <span data-i18n="dash_review">Laisser un avis</span>
</div>

<!-- Page review -->
<div class="page-content" id="page-review">
  <div class="page-header">
    <div>
      <div class="page-title">Laisser un avis</div>
      <div class="page-sub">Partagez votre expérience avec Veridian AI</div>
    </div>
  </div>
  <div class="card" style="max-width:600px">
    <div class="card-body">
      <div class="form-group">
        <label class="form-label">Note (1-5)</label>
        <div id="star-rating" style="display:flex;gap:8px;margin-bottom:8px">
          <!-- Généré par JS -->
        </div>
        <input type="hidden" id="review-rating" value="0">
      </div>
      <div class="form-group">
        <label class="form-label">Votre avis (min. 20 caractères)</label>
        <textarea class="form-input" id="review-content" rows="5" placeholder="Décrivez votre expérience avec Veridian AI..."></textarea>
      </div>
      <button class="btn btn-primary" data-action="submit-review" type="button">Envoyer l'avis</button>
      <div id="review-feedback" style="margin-top:12px;display:none"></div>
    </div>
  </div>
</div>
```

---

### TÂCHE 3.4 — Affichage des avis sur index.html avec fallback i18n

**Fichier:** `web/index.html` — remplacer la section "TÉMOIGNAGES" statique

```html
<section style="padding:80px 24px;background:var(--bg2);border-top:1px solid var(--border)">
  <div style="max-width:1100px;margin:0 auto">
    <div style="text-align:center;margin-bottom:48px" class="reveal">
      <div class="section-label" data-i18n="section_reviews">AVIS CLIENTS</div>
      <h2 class="section-title" data-i18n="section_reviews_title">Ce que disent nos utilisateurs</h2>
    </div>
    <div id="reviews-container" class="reveal">
      <!-- Chargé dynamiquement -->
      <div id="reviews-loading" style="text-align:center;color:var(--text3);padding:40px">
        <span data-i18n="reviews_loading">Chargement des avis...</span>
      </div>
    </div>
  </div>
</section>
```

**Script JS dans `web/js/main.js`:**
```javascript
async function loadReviews() {
  const container = document.getElementById("reviews-container");
  const loading = document.getElementById("reviews-loading");
  if (!container) return;
  
  try {
    const res = await fetch("https://api.veridiancloud.xyz/internal/reviews/public?limit=6");
    const data = await res.json();
    const reviews = data.reviews || [];
    
    if (!reviews.length) {
      const noReviewsKey = "reviews_empty";
      loading.innerHTML = `<div style="text-align:center;color:var(--text3);padding:40px;font-size:14px" data-i18n="${noReviewsKey}">Aucun avis disponible pour le moment.</div>`;
      // Appliquer i18n sur le nouvel élément
      if (typeof initI18n === 'function') initI18n();
      return;
    }
    
    const stars = (n) => "⭐".repeat(n);
    const timeAgo = (dateStr) => {
      const diff = Date.now() - new Date(dateStr).getTime();
      const d = Math.floor(diff / 86400000);
      return d < 1 ? "Aujourd'hui" : d < 30 ? `Il y a ${d} jours` : `Il y a ${Math.floor(d/30)} mois`;
    };
    
    loading.remove();
    const grid = document.createElement("div");
    grid.className = "social-proof-grid";
    grid.innerHTML = reviews.map(r => `
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:16px;padding:24px">
        <div style="display:flex;justify-content:space-between;margin-bottom:12px">
          <span style="font-size:16px">${stars(r.rating)}</span>
          <span style="font-size:11px;color:var(--text3);font-family:'Space Mono',monospace">${timeAgo(r.created_at)}</span>
        </div>
        <div style="font-size:13px;color:var(--text2);line-height:1.7;margin-bottom:16px">"${r.content}"</div>
        <div style="font-weight:700;font-size:13px">${r.user_username || "Utilisateur"}</div>
        ${r.guild_name ? `<div style="color:var(--text3);font-size:12px">${r.guild_name}</div>` : ""}
      </div>
    `).join("");
    container.appendChild(grid);
  } catch (e) {
    if (loading) loading.textContent = "—";
  }
}

// Appeler au chargement
document.addEventListener("DOMContentLoaded", loadReviews);
```

**Clés i18n à ajouter dans TOUS les fichiers locales:**
```json
{
  "section_reviews": "AVIS CLIENTS",
  "section_reviews_title": "Ce que disent nos utilisateurs",
  "reviews_loading": "Chargement des avis...",
  "reviews_empty": "Aucun avis disponible pour le moment. Soyez le premier à partager votre expérience !"
}
```

---

## SECTION 4 — MODÈLE ÉCONOMIQUE REVU (P0)

### TÂCHE 4.1 — Grille tarifaire finale

| Plan | Mensuel | Annuel | Cible |
|---|---:|---:|---|
| Free | 0€ | — | Découverte |
| Starter | 4€ | 36€ (-25%) | Petites communautés |
| Pro | 12€ | 108€ (-25%) | Équipes actives |
| Business | 29€ | 261€ (-25%) | Opérations avancées |

**Add-ons:**
| Add-on | Prix mensuel | Prix annuel |
|---|---:|---:|
| Serveur extra | 9€ | 81€ |
| White-label | 19€ | 171€ |
| Pack IA tokens | 10€ | 90€ |

**Seuil de rentabilité estimé:** ~200€ MRR (≈15 serveurs Starter ou 5 Pro)

**Action — `bot/billing.py` est déjà à jour. Vérifier que `PRICING` correspond à la grille.**

---

### TÂCHE 4.2 — Affichage billing annuel/mensuel toggle sur le site

**Fichier:** `web/index.html` — section pricing

```html
<!-- Ajouter avant la grille pricing -->
<div style="display:flex;align-items:center;justify-content:center;gap:12px;margin-bottom:32px" class="reveal">
  <span style="font-size:13px;color:var(--text2)" data-i18n="pricing_monthly">Mensuel</span>
  <div id="billing-toggle" style="width:48px;height:26px;background:var(--surface);border:1px solid var(--border2);border-radius:13px;cursor:pointer;position:relative;transition:background .2s">
    <div id="billing-toggle-dot" style="width:20px;height:20px;background:var(--accent);border-radius:50%;position:absolute;top:2px;left:2px;transition:left .2s"></div>
  </div>
  <span style="font-size:13px;color:var(--text2)" data-i18n="pricing_annual">Annuel</span>
  <span style="font-size:11px;font-family:'Space Mono',monospace;color:var(--accent);background:var(--accent-dim);padding:2px 8px;border-radius:4px" data-i18n="pricing_discount">-25%</span>
</div>
```

---

## SECTION 5 — FEATURES CONCURRENTIELLES (P1)

### TÂCHE 5.1 — Tags/Labels sur les tickets

**DB:**
```sql
CREATE TABLE IF NOT EXISTS vai_ticket_tags (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    label       VARCHAR(50) NOT NULL,
    color       VARCHAR(10) DEFAULT '#2DFF8F',
    emoji       VARCHAR(20),
    is_active   TINYINT(1) DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vai_ticket_tag_links (
    ticket_id   INT NOT NULL,
    tag_id      INT NOT NULL,
    added_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticket_id, tag_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Commande Discord `/tag add [nom]` et `/tag remove [nom]`:**
```python
@discord.app_commands.command(name="tag", description="Gérer les tags d'un ticket")
@discord.app_commands.describe(action="add ou remove", name="Nom du tag")
async def manage_tag(self, interaction: discord.Interaction, action: str, name: str):
    ticket = TicketModel.get_by_channel(interaction.channel.id)
    if not ticket:
        return await send_localized_embed(interaction, "common.error", ephemeral=True)
    
    locale = _normalize_lang(str(interaction.locale), 'fr')
    
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM vai_ticket_tags WHERE guild_id=%s AND label=%s AND is_active=1",
            (interaction.guild.id, name)
        )
        tag = cursor.fetchone()
    
    if not tag:
        # Créer le tag si inexistant
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vai_ticket_tags (guild_id, label) VALUES (%s, %s)",
                (interaction.guild.id, name)
            )
            tag_id = cursor.lastrowid
    else:
        tag_id = tag["id"]
    
    if action == "add":
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT IGNORE INTO vai_ticket_tag_links (ticket_id, tag_id) VALUES (%s, %s)",
                (ticket["id"], tag_id)
            )
        embed = discord.Embed(title=f"Tag `{name}` ajouté", color=discord.Color(COLOR_SUCCESS))
    else:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM vai_ticket_tag_links WHERE ticket_id=%s AND tag_id=%s",
                (ticket["id"], tag_id)
            )
        embed = discord.Embed(title=f"Tag `{name}` retiré", color=discord.Color(COLOR_NOTICE))
    
    style_embed(embed)
    await interaction.response.send_message(embed=embed, ephemeral=True)
```

---

### TÂCHE 5.2 — Notes internes sur les tickets (staff only)

**Commande `/note [texte]`:**
```python
@discord.app_commands.command(name="note", description="Ajouter une note interne (visible staff uniquement)")
@discord.app_commands.describe(content="Contenu de la note")
async def add_note(self, interaction: discord.Interaction, content: str):
    ticket = TicketModel.get_by_channel(interaction.channel.id)
    if not ticket:
        return
    
    is_staff = interaction.user.guild_permissions.manage_channels
    if not is_staff:
        return await send_localized_embed(interaction, "common.error", ephemeral=True)
    
    # Sauvegarder en DB
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO vai_ticket_notes (ticket_id, author_id, author_username, content) VALUES (%s,%s,%s,%s)",
            (ticket["id"], interaction.user.id, interaction.user.display_name, content)
        )
    
    # Envoyer un embed avec mention [NOTE INTERNE]
    embed = discord.Embed(
        title="📋 Note interne",
        description=content,
        color=discord.Color(COLOR_WARNING)
    )
    embed.set_footer(text=f"Ajoutée par {interaction.user.display_name} — Visible staff seulement")
    style_embed(embed)
    await interaction.channel.send(embed=embed)
    await interaction.response.send_message("Note ajoutée.", ephemeral=True)
```

**DB:**
```sql
CREATE TABLE IF NOT EXISTS vai_ticket_notes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id       INT NOT NULL,
    author_id       BIGINT NOT NULL,
    author_username VARCHAR(100),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ticket (ticket_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

---

### TÂCHE 5.3 — Canned Responses (réponses prédéfinies avec traduction auto)

**DB:**
```sql
CREATE TABLE IF NOT EXISTS vai_snippets (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    trigger     VARCHAR(50) NOT NULL COMMENT 'Mot-clé déclencheur ex: /bonjour',
    content     TEXT NOT NULL,
    language    VARCHAR(10) DEFAULT 'fr',
    auto_translate TINYINT(1) DEFAULT 1,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id),
    UNIQUE KEY uniq_guild_trigger (guild_id, trigger)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Commande `/snippet [trigger]` dans un ticket:**
```python
@discord.app_commands.command(name="snippet", description="Envoyer une réponse prédéfinie")
@discord.app_commands.describe(trigger="Déclencheur du snippet")
async def send_snippet(self, interaction: discord.Interaction, trigger: str):
    ticket = TicketModel.get_by_channel(interaction.channel.id)
    if not ticket:
        return
    
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM vai_snippets WHERE guild_id=%s AND trigger=%s",
            (interaction.guild.id, trigger)
        )
        snippet = cursor.fetchone()
    
    if not snippet:
        embed = discord.Embed(title="Snippet introuvable", color=discord.Color(COLOR_CRITICAL))
        style_embed(embed)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
    
    content = snippet["content"]
    
    # Traduction automatique si activée
    user_lang = ticket.get("user_language")
    if snippet["auto_translate"] and user_lang and user_lang != snippet["language"]:
        from bot.services.translator import TranslatorService
        translator = TranslatorService()
        content, _ = translator.translate(content, snippet["language"], user_lang)
    
    embed = discord.Embed(description=content, color=discord.Color(COLOR_SUCCESS))
    style_embed(embed)
    await interaction.response.send_message(embed=embed)
```

---

### TÂCHE 5.4 — Blacklist utilisateurs

**DB:**
```sql
CREATE TABLE IF NOT EXISTS vai_blacklist (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    user_id     BIGINT NOT NULL,
    reason      TEXT,
    added_by    BIGINT,
    expires_at  TIMESTAMP NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uniq_guild_user (guild_id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Dans `open_ticket` — vérification avant création:**
```python
# Vérifier blacklist avant de créer le ticket
with get_db_context() as conn:
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id FROM vai_blacklist WHERE guild_id=%s AND user_id=%s "
        "AND (expires_at IS NULL OR expires_at > NOW())",
        (interaction.guild.id, interaction.user.id)
    )
    if cursor.fetchone():
        embed = discord.Embed(
            title=i18n.get("tickets.blacklisted_title", locale),
            description=i18n.get("tickets.blacklisted_desc", locale),
            color=discord.Color(COLOR_CRITICAL)
        )
        style_embed(embed)
        return await interaction.response.send_message(embed=embed, ephemeral=True)
```

**Commande `/blacklist add|remove @user [raison] [durée]`:**
```python
@discord.app_commands.command(name="blacklist")
@discord.app_commands.checks.has_permissions(administrator=True)
@discord.app_commands.describe(action="add/remove", user="Utilisateur", reason="Raison")
async def blacklist(self, interaction, action: str, user: discord.Member, reason: str = ""):
    locale = _normalize_lang(str(interaction.locale), 'fr')
    if action == "add":
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vai_blacklist (guild_id, user_id, reason, added_by) "
                "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE reason=%s",
                (interaction.guild.id, user.id, reason, interaction.user.id, reason)
            )
        embed = discord.Embed(
            title=i18n.get("admin.blacklist_added", locale),
            description=f"{user.mention} — {reason or 'Aucune raison'}",
            color=discord.Color(COLOR_WARNING)
        )
    else:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "DELETE FROM vai_blacklist WHERE guild_id=%s AND user_id=%s",
                (interaction.guild.id, user.id)
            )
        embed = discord.Embed(title=i18n.get("admin.blacklist_removed", locale), color=discord.Color(COLOR_SUCCESS))
    style_embed(embed)
    await interaction.response.send_message(embed=embed, ephemeral=True)
```

---

### TÂCHE 5.5 — Round-robin auto-assignment

**Fichier:** `bot/cogs/tickets.py`

**Principe:** Assigner automatiquement le prochain staff disponible en rotation.

```python
def _get_next_staff_round_robin(guild_id: int, guild_config: dict) -> tuple[int | None, str | None]:
    """Retourne (user_id, username) du prochain staff selon round-robin."""
    import json
    staff_json = guild_config.get("staff_languages_json")
    if not staff_json:
        return None, None
    
    try:
        staff_list = json.loads(staff_json) if isinstance(staff_json, str) else staff_json
        if not staff_list:
            return None, None
        
        # Récupérer le dernier assigné
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT assigned_staff_id FROM vai_tickets WHERE guild_id=%s AND assigned_staff_id IS NOT NULL "
                "ORDER BY opened_at DESC LIMIT 1",
                (guild_id,)
            )
            row = cursor.fetchone()
            last_id = row[0] if row else None
        
        # Trouver le suivant dans la liste
        ids = [int(s.get("user_id", 0)) for s in staff_list if s.get("user_id")]
        if not ids:
            return None, None
        
        if last_id and last_id in ids:
            idx = (ids.index(last_id) + 1) % len(ids)
        else:
            idx = 0
        
        next_id = ids[idx]
        next_name = next((s.get("username", "Staff") for s in staff_list if int(s.get("user_id", 0)) == next_id), "Staff")
        return next_id, next_name
    except Exception:
        return None, None
```

---

### TÂCHE 5.6 — SLA (Service Level Agreement) avec breach alerts

**DB:**
```sql
ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS sla_response_minutes INT DEFAULT 60 
    COMMENT 'Délai max de première réponse en minutes';
ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS sla_resolution_hours INT DEFAULT 24 
    COMMENT 'Délai max de résolution en heures';
```

**Boucle de monitoring dans `bot/main.py`:**
```python
@tasks.loop(minutes=15)
async def sla_monitor_loop():
    """Vérifie les violations SLA et alerte."""
    try:
        guilds = GuildModel.get_all()
        for guild_cfg in guilds:
            sla_response = int(guild_cfg.get("sla_response_minutes") or 60)
            log_channel_id = guild_cfg.get("log_channel_id")
            if not log_channel_id:
                continue
            
            # Tickets ouverts sans réponse staff depuis trop longtemps
            with get_db_context() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    """SELECT t.id, t.channel_id, t.user_username, t.opened_at
                    FROM vai_tickets t
                    WHERE t.guild_id=%s AND t.status='open'
                    AND NOT EXISTS (
                        SELECT 1 FROM vai_ticket_messages m 
                        WHERE m.ticket_id=t.id AND m.author_id != t.user_id
                    )
                    AND t.opened_at < DATE_SUB(NOW(), INTERVAL %s MINUTE)""",
                    (guild_cfg["id"], sla_response)
                )
                breaches = cursor.fetchall()
            
            for breach in breaches:
                log_channel = bot.get_channel(int(log_channel_id))
                if log_channel:
                    embed = discord.Embed(
                        title="⏰ SLA Breach Alert",
                        description=f"Ticket #{breach['id']} ({breach['user_username']}) sans réponse depuis >{sla_response}min",
                        color=discord.Color(COLOR_CRITICAL)
                    )
                    embed.add_field(name="Channel", value=f"<#{breach['channel_id']}>", inline=True)
                    style_embed(embed)
                    await log_channel.send(embed=embed)
    except Exception as e:
        logger.error(f"SLA monitor: {e}")
```

---

## SECTION 6 — DASHBOARD ERGONOMIE (P1)

### TÂCHE 6.1 — Onboarding wizard 4 étapes

**Fichier:** `web/dashboard.html` — ajouter modal d'onboarding

```html
<!-- Modal onboarding (affiché si guild non configurée) -->
<div id="onboarding-modal" style="display:none;position:fixed;inset:0;z-index:20000;background:rgba(0,0,0,.8);align-items:center;justify-content:center">
  <div style="background:var(--bg2);border:1px solid var(--border2);border-radius:16px;width:min(560px,90vw);padding:32px">
    <div style="display:flex;justify-content:space-between;margin-bottom:24px">
      <div style="font-family:'Space Mono',monospace;font-size:13px;font-weight:700;color:var(--accent)">
        Configuration initiale
      </div>
      <div style="font-size:11px;color:var(--text3);font-family:'Space Mono',monospace" id="onboarding-step-label">ÉTAPE 1/4</div>
    </div>
    
    <!-- Step 1: Catégorie tickets -->
    <div id="onboarding-step-1" class="onboarding-step">
      <h3 style="font-size:18px;margin-bottom:8px">Catégorie des tickets</h3>
      <p style="color:var(--text2);font-size:13px;margin-bottom:16px">Entrez l'ID de la catégorie Discord où les tickets seront créés.</p>
      <input class="form-input" id="onb-category" placeholder="ID de la catégorie Discord">
    </div>
    
    <!-- Step 2: Rôle staff -->
    <div id="onboarding-step-2" class="onboarding-step" style="display:none">
      <h3 style="font-size:18px;margin-bottom:8px">Rôle du staff</h3>
      <p style="color:var(--text2);font-size:13px;margin-bottom:16px">ID du rôle Discord de votre équipe de support.</p>
      <input class="form-input" id="onb-staff-role" placeholder="ID du rôle staff">
    </div>
    
    <!-- Step 3: Channel support public -->
    <div id="onboarding-step-3" class="onboarding-step" style="display:none">
      <h3 style="font-size:18px;margin-bottom:8px">Channel support public</h3>
      <p style="color:var(--text2);font-size:13px;margin-bottom:16px">Channel où le bot répondra automatiquement aux questions.</p>
      <input class="form-input" id="onb-support-channel" placeholder="ID ou #nom-du-channel">
    </div>
    
    <!-- Step 4: Langue par défaut -->
    <div id="onboarding-step-4" class="onboarding-step" style="display:none">
      <h3 style="font-size:18px;margin-bottom:8px">Langue du staff</h3>
      <p style="color:var(--text2);font-size:13px;margin-bottom:16px">Dans quelle langue votre staff répond-il ?</p>
      <select class="form-select" id="onb-lang">
        <option value="fr">Français</option>
        <option value="en">English</option>
        <option value="es">Español</option>
        <option value="de">Deutsch</option>
      </select>
    </div>
    
    <div style="display:flex;justify-content:space-between;margin-top:24px">
      <button class="btn btn-ghost btn-sm" id="onb-skip">Passer</button>
      <button class="btn btn-primary" id="onb-next">Suivant →</button>
    </div>
    
    <!-- Progress dots -->
    <div style="display:flex;justify-content:center;gap:8px;margin-top:20px">
      <div style="width:8px;height:8px;border-radius:50%;background:var(--accent)" id="onb-dot-1"></div>
      <div style="width:8px;height:8px;border-radius:50%;background:var(--surface2)" id="onb-dot-2"></div>
      <div style="width:8px;height:8px;border-radius:50%;background:var(--surface2)" id="onb-dot-3"></div>
      <div style="width:8px;height:8px;border-radius:50%;background:var(--surface2)" id="onb-dot-4"></div>
    </div>
  </div>
</div>
```

---

### TÂCHE 6.2 — Ctrl+K command palette

**Ajouter dans `web/js/dashboard.js`:**
```javascript
// Command palette
let cmdPaletteOpen = false;
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey || e.metaKey) && e.key === "k") {
    e.preventDefault();
    toggleCommandPalette();
  }
  if (e.key === "Escape" && cmdPaletteOpen) {
    closeCommandPalette();
  }
});

function toggleCommandPalette() {
  const el = document.getElementById("cmd-palette");
  if (!el) return;
  cmdPaletteOpen = !cmdPaletteOpen;
  el.style.display = cmdPaletteOpen ? "flex" : "none";
  if (cmdPaletteOpen) document.getElementById("cmd-input")?.focus();
}

function closeCommandPalette() {
  const el = document.getElementById("cmd-palette");
  if (el) el.style.display = "none";
  cmdPaletteOpen = false;
}
```

**HTML à ajouter dans `web/dashboard.html`:**
```html
<div id="cmd-palette" style="display:none;position:fixed;inset:0;z-index:30000;align-items:flex-start;justify-content:center;padding-top:15vh;background:rgba(0,0,0,.6);backdrop-filter:blur(4px)">
  <div style="background:var(--bg2);border:1px solid var(--border2);border-radius:12px;width:min(560px,90vw);overflow:hidden">
    <input id="cmd-input" type="text" placeholder="Rechercher une action... (Ctrl+K)" 
           style="width:100%;padding:14px 16px;background:transparent;border:none;outline:none;color:var(--text);font-size:14px">
    <div id="cmd-results" style="border-top:1px solid var(--border);max-height:300px;overflow-y:auto">
      <!-- Généré par JS -->
    </div>
  </div>
</div>
```

---

### TÂCHE 6.3 — Ticket detail drawer (sans navigation)

**Ajouter dans dashboard.html:**
```html
<div id="ticket-drawer" style="display:none;position:fixed;right:0;top:0;bottom:0;width:min(480px,90vw);background:var(--bg2);border-left:1px solid var(--border);z-index:5000;overflow-y:auto;padding:24px;transform:translateX(100%);transition:transform .3s">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:20px">
    <div style="font-family:'Space Mono',monospace;font-size:13px;font-weight:700;color:var(--text)" id="drawer-title">Ticket #—</div>
    <button onclick="closeTicketDrawer()" style="background:none;border:none;color:var(--text3);cursor:pointer;font-size:20px">×</button>
  </div>
  <div id="drawer-content">
    <!-- Chargé dynamiquement -->
  </div>
</div>
```

---

## SECTION 7 — ANALYTICS DASHBOARD (P1)

### TÂCHE 7.1 — Page analytics avec KPI cards

**Fichier:** `web/dashboard.html` — nouvelle page analytics

```html
<!-- Nav item -->
<div class="nav-item" data-page="analytics">
  <svg class="nav-icon" viewBox="0 0 14 14" fill="none">
    <path d="M2 10.5l3-4 3 2 3-5.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/>
  </svg>
  <span>Analytics</span>
</div>

<!-- Page analytics -->
<div class="page-content" id="page-analytics">
  <div class="page-header">
    <div><div class="page-title">Analytics</div></div>
  </div>
  
  <!-- KPI cards -->
  <div class="stats-row">
    <div class="stat-card c-green">
      <div class="stat-top">
        <div class="stat-label">TICKETS CE MOIS</div>
        <div class="stat-icon c-green">📊</div>
      </div>
      <div class="stat-value" id="kpi-tickets">—</div>
      <div class="stat-delta" id="kpi-tickets-delta">vs mois précédent</div>
    </div>
    <div class="stat-card c-yellow">
      <div class="stat-top">
        <div class="stat-label">TEMPS RÉPONSE MOYEN</div>
        <div class="stat-icon c-yellow">⏱️</div>
      </div>
      <div class="stat-value" id="kpi-response">—</div>
    </div>
    <div class="stat-card c-blue">
      <div class="stat-top">
        <div class="stat-label">SATISFACTION MOYENNE</div>
        <div class="stat-icon c-blue">⭐</div>
      </div>
      <div class="stat-value" id="kpi-csat">—</div>
    </div>
    <div class="stat-card c-red">
      <div class="stat-top">
        <div class="stat-label">SLA BREACH RATE</div>
        <div class="stat-icon c-red">🚨</div>
      </div>
      <div class="stat-value" id="kpi-sla">—</div>
    </div>
  </div>
  
  <!-- Agent leaderboard -->
  <div class="card">
    <div class="card-header">
      <div class="card-title"><div class="card-dot"></div><span>Leaderboard agents</span></div>
    </div>
    <div class="card-body no-pad">
      <table class="data-table" id="leaderboard-table">
        <thead><tr>
          <th>Agent</th><th>Tickets traités</th><th>Temps moyen</th><th>CSAT</th>
        </tr></thead>
        <tbody id="leaderboard-body">
          <tr><td colspan="4" style="text-align:center;color:var(--text3);padding:24px">Chargement...</td></tr>
        </tbody>
      </table>
    </div>
  </div>
</div>
```

---

## SECTION 8 — MODÈLE ÉCONOMIQUE DÉTAILLÉ (P0)

### Calcul de rentabilité

```
Coûts mensuels estimés:
- Hébergement VPS (2 cores, 4GB): ~10€/mois
- MySQL hébergé: ~5€/mois
- Groq API (free tier suffisant pour ~100 serveurs): 0-20€
- Domaine + SSL: ~5€/mois
- Total: ~20-40€/mois

Break-even:
- 10 Starter (4€) = 40€ → rentable
- 5 Pro (12€) = 60€ → très rentable
- Mix cible: 20 Starter + 5 Pro = 80+60 = 140€ MRR (mois 3)
- Cible 6 mois: 200€ MRR → ~30€ margin/mois

Projection 1 an (si 2% conversion gratuit → payant):
- 500 serveurs Free → 10 payants = 80€ MRR
- 1000 serveurs → 20 payants = 160€ MRR
```

### Stratégie d'acquisition

1. **Discord.bots.gg** listing gratuit → exposition organique
2. **top.gg** premium listing 20€/mois → ROI si 2 conversions
3. **Communautés gaming/SaaS Discord** → démo gratuite 30 jours Pro
4. **Appel annuel** → -25% = économie réelle, incite à s'engager

---

## SECTION 9 — WEBHOOK SORTANTS (P2)

### TÂCHE 9.1 — Table et endpoint

```sql
CREATE TABLE IF NOT EXISTS vai_outbound_webhooks (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    guild_id    BIGINT NOT NULL,
    url         VARCHAR(500) NOT NULL,
    secret      VARCHAR(100),
    events      JSON COMMENT '["ticket.open","ticket.close","ticket.message"]',
    is_active   TINYINT(1) DEFAULT 1,
    last_status INT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Service dans `bot/services/webhook_emitter.py`:**
```python
import aiohttp, hmac, hashlib, json, os

async def emit_webhook(guild_id: int, event: str, payload: dict):
    """Émet un événement vers tous les webhooks sortants configurés."""
    from bot.db.connection import get_db_context
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT * FROM vai_outbound_webhooks WHERE guild_id=%s AND is_active=1",
            (guild_id,)
        )
        webhooks = cursor.fetchall()
    
    for wh in webhooks:
        events = wh.get("events") or []
        if isinstance(events, str):
            events = json.loads(events)
        if event not in events:
            continue
        
        body = json.dumps({"event": event, "guild_id": guild_id, "data": payload})
        headers = {"Content-Type": "application/json", "X-Veridian-Event": event}
        
        if wh.get("secret"):
            sig = hmac.new(wh["secret"].encode(), body.encode(), hashlib.sha256).hexdigest()
            headers["X-Veridian-Signature"] = sig
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(wh["url"], data=body, headers=headers, timeout=10) as resp:
                    # Mettre à jour le status
                    with get_db_context() as conn:
                        cursor = conn.cursor()
                        cursor.execute(
                            "UPDATE vai_outbound_webhooks SET last_status=%s WHERE id=%s",
                            (resp.status, wh["id"])
                        )
        except Exception as e:
            logger.warning(f"Webhook sortant {wh['id']} échoué: {e}")
```

---

## SECTION 10 — ROADMAP SPRINTS

```
Sprint 1 (Semaines 1-2): CORRECTIONS CRITIQUES
├── Tâche 1.1 à 1.5 (embeds, langues, couleurs)
├── Tâche 2.4 + 2.5 (fermeture ticket = suppression Discord)
└── Tâche 2.1 (welcome embed en langue client)

Sprint 2 (Semaines 3-4): TICKETS MODERNES
├── Tâche 2.2 (logs à l'ouverture)
├── Tâche 2.3 (satisfaction rating)
├── Tâche 5.2 (notes internes)
└── Tâche 5.4 (blacklist)

Sprint 3 (Semaines 5-6): AVIS + BILLING
├── Tâche 3.1 à 3.4 (système d'avis complet)
├── Tâche 4.1 + 4.2 (billing toggle annuel/mensuel)
└── Tâche 5.3 (snippets)

Sprint 4 (Semaines 7-8): FEATURES AVANCÉES
├── Tâche 5.1 (tags/labels)
├── Tâche 5.5 (round-robin)
├── Tâche 5.6 (SLA)
└── Tâche 6.1 (onboarding wizard)

Sprint 5 (Semaines 9-10): ANALYTICS + UX
├── Tâche 6.2 (Ctrl+K)
├── Tâche 6.3 (ticket drawer)
├── Tâche 7.1 (analytics + leaderboard)
└── Tâche 9.1 (webhooks sortants)

Sprint 6 (Semaines 11-12): POLISH + MOBILE
├── Mobile responsive dashboard
├── Export CSV/PDF des tickets
├── Optimisations perf / cache
└── Documentation utilisateur finale
```

---

## CHECKLIST POUR L'AGENT

Avant chaque tâche:
- [ ] Vérifier les imports dans le fichier cible
- [ ] Ajouter les clés i18n dans `bot/locales/fr.json` ET `bot/locales/en.json`
- [ ] Vérifier la migration DB dans `api/db_migrate.py`
- [ ] S'assurer que `style_embed()` est appelé sur chaque embed
- [ ] Tester que la locale vient de `interaction.locale` ou `ticket.user_language`

Après chaque tâche:
- [ ] Pas de texte brut envoyé par le bot (uniquement embeds)
- [ ] Couleur d'embed cohérente avec l'hiérarchie d'importance
- [ ] Textes traduits via i18n avec bonne locale
- [ ] Nouvelle table DB ajoutée dans `api/db_migrate.py`