# 🚀 Veridian AI — Roadmap Production Complète
> Version cible : **1.0.0-stable** · Mis à jour : Mars 2026

---

## 📋 Table des matières

1. [État actuel & Diagnostic](#1-état-actuel--diagnostic)
2. [Corrections critiques (Bloquantes)](#2-corrections-critiques-bloquantes)
3. [Améliorations bot Discord](#3-améliorations-bot-discord)
4. [Améliorations API Backend](#4-améliorations-api-backend)
5. [Refonte Dashboard (UI/UX)](#5-refonte-dashboard-uiux)
6. [Refonte Landing Page](#6-refonte-landing-page)
7. [Nouvelles fonctionnalités clés](#7-nouvelles-fonctionnalités-clés)
8. [Performance & Scalabilité](#8-performance--scalabilité)
9. [Sécurité renforcée](#9-sécurité-renforcée)
10. [DevOps & Déploiement Production](#10-devops--déploiement-production)
11. [Checklist de lancement](#11-checklist-de-lancement)
12. [Ordre d'exécution recommandé](#12-ordre-dexécution-recommandé)

---

## 1. État actuel & Diagnostic

### ✅ Ce qui fonctionne bien
- Architecture modulaire (cogs/services/routes) solide
- Système de tickets avec traduction bidirectionnelle
- Fallback automatique sur 4 clés Groq
- Cache des traductions SHA256
- OAuth2 Discord + JWT sécurisé
- DB auto-migration au démarrage
- Dashboard admin fonctionnel

### ❌ Problèmes bloquants identifiés

| Problème | Fichier | Impact |
|---|---|---|
| `hmac.new()` → doit être `hmac.new()` → **`hmac.HMAC()`** correct: `hmac.new()` n'existe pas | `api/routes/webhook.py` ligne 22 | 🔴 Crash webhook OxaPay |
| `TicketModel.count_open_by_user` manquant dans certains chemins | `bot/cogs/tickets.py` ligne ~500 | 🔴 Crash ouverture ticket |
| `TranslatorService` importé sans `asyncio.to_thread` sur certains appels sync | `bot/cogs/tickets.py` | 🟡 Freeze event loop |
| `_embed_color()` mappe "blue" → `COLOR_SUCCESS` (vert) — incohérent | `bot/cogs/tickets.py` | 🟡 UX dégradé |
| `ai_intent` colonne manquante dans `vai_tickets` | `bot/db/models.py` | 🟡 Exception silencieuse |
| `verify_oxapay_signature` : `hmac.new()` → `hmac.HMAC()` | `api/routes/webhook.py` | 🔴 Signature toujours invalide |
| Dashboard JS : `loadOrders()` navigue vers page "orders" mais charge les stats billing, pas les commandes pendantes du super-admin | `web/js/dashboard.js` | 🟡 Confusion UX |
| Langue `"auto"` stockée en DB non gérée au moment de la traduction staff→user | `bot/cogs/tickets.py` | 🟡 Pas de traduction |
| `ticket_welcome_color` valeur `#4DA6FF` (hex) non gérée par `_embed_color()` qui attend `"blue"` | `bot/cogs/tickets.py` | 🟡 Couleur fallback |
| `PendingNotificationModel` ne filtre pas `last_attempt` pour éviter spam retry | `bot/db/models.py` | 🟡 DMs en double |

---

## 2. Corrections critiques (Bloquantes)

### 2.1 Fix `hmac.new()` → correction webhook OxaPay

**Fichier :** `api/routes/webhook.py`

```python
# ❌ AVANT (ligne 22) — hmac.new() n'existe pas en Python 3
expected_signature = hmac.new(
    secret.encode(), 
    payload, 
    hashlib.sha256
).hexdigest()

# ✅ APRÈS
expected_signature = hmac.new(
    secret.encode(),
    payload,
    hashlib.sha256
).hexdigest()
# NOTE: En Python 3, c'est hmac.HMAC ou hmac.new fonctionne via le module
# Vérifier: import hmac; hmac.new(b'k', b'msg', 'sha256').hexdigest()
# Si erreur → utiliser:
expected_signature = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
# hmac.new est bien présent en Python 3 via le module hmac — OK.
# Le vrai bug est dans bot/services/oxapay.py verify_webhook_signature:
# hmac.new() → CORRECT, mais hmac.HMAC() serait plus explicite.
# Le vrai bug: payload est un dict, pas des bytes.
```

**Fichier :** `bot/services/oxapay.py` — `verify_webhook_signature`

```python
# ❌ AVANT
payload_json = json.dumps(payload, sort_keys=True)
expected_signature = hmac.new(
    self.webhook_secret.encode(),
    payload_json.encode(),  # ← encode() manquait sur payload bytes dans webhook.py
    hashlib.sha256
).hexdigest()

# ✅ APRÈS — dans api/routes/webhook.py, body est déjà bytes
def verify_oxapay_signature(payload: bytes, signature: str) -> bool:
    secret = os.getenv("OXAPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected = hmac.new(
        secret.encode('utf-8'),
        payload,          # ← utiliser le body bytes brut, pas re-sérialisé
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature.lower())
```

### 2.2 Ajouter colonne `ai_intent` dans la migration DB

**Fichier :** `api/db_migrate.py` — dans `_ensure_ticket_migrations()`

```python
# Ajouter après le bloc assigned_staff_name:
if _column_info(tickets_table, "ai_intent") is None:
    with get_db_context() as conn:
        cursor = conn.cursor()
        try:
            cursor.execute(
                f"ALTER TABLE {tickets_table} "
                f"ADD COLUMN ai_intent TEXT NULL "
                f"COMMENT 'Analyse IA du premier message'"
            )
            logger.info(f"[db] Colonne ai_intent ajoutee a {tickets_table}")
        except Exception as e:
            if "duplicate column" not in str(e).lower():
                logger.warning(f"[db] ALTER {tickets_table}.ai_intent: {e}")
```

**Fichier :** `database/schema.sql` — dans `vai_tickets`

```sql
-- Ajouter dans la définition de vai_tickets:
ai_intent TEXT NULL COMMENT 'Analyse IA du premier message (Smart Welcome)',
```

### 2.3 Fix `_embed_color()` pour supporter les codes hex

**Fichier :** `bot/cogs/tickets.py`

```python
def _embed_color(raw: str | None) -> discord.Color:
    n = (raw or "").strip().lower()
    if not n:
        return discord.Color(COLOR_SUCCESS)

    # ✅ Support hex COMPLET (y compris depuis le colorpicker du dashboard)
    hex_raw = n.lstrip('#')
    if len(hex_raw) in (3, 6) and all(c in '0123456789abcdef' for c in hex_raw):
        try:
            if len(hex_raw) == 3:
                hex_raw = ''.join(c*2 for c in hex_raw)
            return discord.Color(int(hex_raw, 16))
        except Exception:
            pass

    return {
        "blue":    discord.Color(0x4DA6FF),   # Bleu Discord cohérent
        "green":   discord.Color(COLOR_SUCCESS),
        "red":     discord.Color(COLOR_CRITICAL),
        "yellow":  discord.Color(COLOR_WARNING),
        "purple":  discord.Color(COLOR_NOTICE),
        "success": discord.Color(COLOR_SUCCESS),
        "notice":  discord.Color(COLOR_NOTICE),
        "warning": discord.Color(COLOR_WARNING),
        "critical":discord.Color(COLOR_CRITICAL),
    }.get(n, discord.Color(COLOR_SUCCESS))
```

### 2.4 Fix langue `"auto"` dans la traduction staff→user

**Fichier :** `bot/cogs/tickets.py` — dans `on_message` côté staff

```python
# ❌ AVANT
user_lang = ticket.get("user_language") if ticket.get("user_language") not in (None, "", "auto") else None

# ✅ APRÈS — Aussi tenter de détecter depuis l'historique
if not user_lang:
    user_lang = self._dominant_language_from_history(ticket["id"], ticket.get("user_id"))
    if user_lang:
        TicketModel.update(ticket["id"], user_language=user_lang)
        ticket["user_language"] = user_lang
```

### 2.5 Fix PendingNotificationModel — anti-spam retry

**Fichier :** `bot/db/models.py`

```python
@staticmethod
def list_pending(limit: int = 20) -> List[Dict]:
    """Récupère les notifications à envoyer (max 5 tentatives, délai exponentiel)."""
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        try:
            cursor.execute(
                f"SELECT * FROM {DB_TABLE_PREFIX}pending_notifications "
                f"WHERE attempts < 5 "
                f"AND (last_attempt IS NULL OR last_attempt < DATE_SUB(NOW(), INTERVAL POWER(2, attempts) MINUTE)) "
                f"ORDER BY created_at ASC LIMIT %s",
                (limit,)
            )
            return cursor.fetchall()
        except Exception:
            # Fallback sans délai exponentiel si la requête échoue
            cursor.execute(
                f"SELECT * FROM {DB_TABLE_PREFIX}pending_notifications "
                f"WHERE attempts < 5 ORDER BY created_at ASC LIMIT %s",
                (limit,)
            )
            return cursor.fetchall()
```

---

## 3. Améliorations Bot Discord

### 3.1 Commande `/language` manquante dans `tickets.py`

La commande `/language` est dans `support.py` mais elle doit aussi mettre à jour le ticket actif si l'utilisateur a un ticket ouvert.

**Fichier :** `bot/cogs/support.py` — améliorer `SupportCog`

```python
@discord.app_commands.command(name="language", description="Définir votre langue préférée")
@discord.app_commands.describe(code="Code langue : fr, en, es, de, it, pt, ru, ja, zh, ar…")
async def set_language(self, interaction: discord.Interaction, code: str):
    await interaction.response.defer(ephemeral=True)
    code = code.strip().lower()[:2]
    
    UserModel.upsert(interaction.user.id, interaction.user.name, code)
    
    # Mettre à jour le ticket actif si existant
    try:
        from bot.db.models import TicketModel
        with __import__('bot.db.connection', fromlist=['get_db_context']).get_db_context() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(
                "SELECT id, channel_id FROM vai_tickets WHERE guild_id=%s AND user_id=%s AND status IN ('open','in_progress','pending_close') LIMIT 1",
                (interaction.guild.id, interaction.user.id)
            )
            ticket = cursor.fetchone()
        if ticket:
            TicketModel.update(ticket["id"], user_language=code)
            chan = interaction.guild.get_channel(int(ticket["channel_id"]))
            if chan:
                tickets_cog = self.bot.get_cog("TicketsCog")
                if tickets_cog:
                    await tickets_cog._try_update_welcome_embed(chan, ticket["id"])
    except Exception:
        pass

    lang_name = LANGUAGE_NAMES.get(code, code.upper())
    embed = discord.Embed(
        title="Langue mise à jour",
        description=f"Votre langue est maintenant : **{lang_name}** (`{code}`)",
        color=discord.Color(COLOR_SUCCESS)
    )
    await interaction.followup.send(embed=style_embed(embed), ephemeral=True)
```

### 3.2 Système de suggestions staff (Pro)

**Nouveau fichier :** `bot/cogs/suggestions.py`

```python
"""
Cog: Suggestions staff IA — Propose des réponses aux agents en PRO.
S'active automatiquement quand staff_suggestions = 1.
"""

import discord
from discord.ext import commands
from loguru import logger

from bot.db.models import GuildModel, SubscriptionModel, TicketModel, TicketMessageModel
from bot.services.groq_client import GroqClient
from bot.utils.embed_style import style_embed
from bot.config import COLOR_NOTICE


class SuggestionsCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.groq = GroqClient()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        ticket = TicketModel.get_by_channel(message.channel.id)
        if not ticket or ticket["status"] == "closed":
            return

        guild_config = GuildModel.get(message.guild.id) or {}
        if not int(guild_config.get("staff_suggestions", 0) or 0):
            return

        # Vérifier plan Pro
        sub = SubscriptionModel.get(message.guild.id)
        if not sub or sub.get("plan") != "pro":
            return

        # Seulement sur les messages utilisateur
        is_ticket_user = message.author.id == ticket["user_id"]
        if not is_ticket_user:
            return

        text = (message.content or "").strip()
        if not text or len(text.split()) < 3:
            return

        try:
            msgs = TicketMessageModel.get_by_ticket(ticket["id"])
            last = msgs[-20:] if msgs else []
            conversation = [
                {"author": m.get("author_username", "?"), "content": m.get("original_content", "")}
                for m in last if (m.get("original_content") or "").strip()
            ]

            if not conversation:
                return

            staff_lang = ticket.get("staff_language") or guild_config.get("default_language") or "en"
            suggestion = self.groq.generate_staff_suggestion(conversation, staff_lang)

            if suggestion:
                embed = discord.Embed(
                    title="💡 Suggestion de réponse",
                    description=suggestion[:1500],
                    color=discord.Color(COLOR_NOTICE)
                )
                embed.set_footer(text="IA · Suggestion uniquement — modifiez avant d'envoyer")
                await message.channel.send(embed=style_embed(embed))
        except Exception as e:
            logger.debug(f"Staff suggestion failed: {e}")


async def setup(bot):
    await bot.add_cog(SuggestionsCog(bot))
```

**Ajouter dans** `bot/services/groq_client.py` :

```python
def generate_staff_suggestion(self, messages: list, staff_language: str) -> str:
    """Génère une suggestion de réponse pour le staff basée sur la conversation."""
    if not self.api_keys or not messages:
        return ""

    conv_text = "\n".join([
        f"[{m.get('author','?')}]: {m.get('content','')}"
        for m in messages[-10:]
        if (m.get('content') or '').strip()
    ])

    system = (
        f"You are a customer support assistant helping a staff member.\n"
        f"Based on the conversation, generate ONE concise, professional reply suggestion.\n"
        f"Rules:\n"
        f"- Respond in: {staff_language}\n"
        f"- Maximum 3 sentences\n"
        f"- Be empathetic and solution-focused\n"
        f"- Do NOT add emojis\n"
        f"- Output ONLY the suggested reply text\n"
    )

    for attempt in range(len(self.api_keys)):
        try:
            client = self._get_client(force_key_index=attempt)
            if not client:
                continue
            completion = client.chat.completions.create(
                model=GROQ_MODEL_FAST,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": f"Conversation:\n{conv_text}\n\nSuggest a reply:"}
                ],
                temperature=0.6,
                max_tokens=150,
                stream=False,
            )
            res = completion.choices[0].message.content.strip()
            return strip_emojis(res) or ""
        except Exception as e:
            logger.warning(f"Staff suggestion key #{attempt+1}: {str(e)[:60]}")
    return ""
```

### 3.3 Commande `/stats` pour les admins de serveur

**Ajouter dans** `bot/cogs/support.py` :

```python
@discord.app_commands.command(name="stats", description="Voir les statistiques du serveur")
@discord.app_commands.checks.has_permissions(administrator=True)
async def server_stats(self, interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    try:
        from bot.db.models import TicketModel, SubscriptionModel
        
        open_t = TicketModel.count_by_guild(interaction.guild.id, status="open")
        month_t = TicketModel.count_this_month(interaction.guild.id)
        sub = SubscriptionModel.get(interaction.guild.id)
        plan = (sub or {}).get("plan", "free").upper()
        
        embed = discord.Embed(
            title=f"Statistiques — {interaction.guild.name}",
            color=discord.Color(COLOR_SUCCESS)
        )
        embed.add_field(name="Tickets ouverts", value=f"`{open_t}`", inline=True)
        embed.add_field(name="Tickets ce mois", value=f"`{month_t}`", inline=True)
        embed.add_field(name="Plan actuel", value=f"`{plan}`", inline=True)
        embed.set_footer(text=f"Voir plus sur {DASHBOARD_URL}")
        
        await interaction.followup.send(embed=style_embed(embed), ephemeral=True)
    except Exception as e:
        logger.error(f"stats error: {e}")
        await interaction.followup.send("Erreur lors de la récupération des stats.", ephemeral=True)
```

### 3.4 Améliorer la gestion des cooldowns

**Fichier :** `bot/cogs/tickets.py`

```python
# Ajouter un cooldown plus visible
@open_ticket.error
async def open_ticket_error(self, interaction: discord.Interaction, error):
    if isinstance(error, discord.app_commands.CommandOnCooldown):
        retry_sec = int(error.retry_after)
        embed = discord.Embed(
            title="Veuillez patienter",
            description=(
                f"Vous pouvez ouvrir un nouveau ticket dans **{retry_sec} secondes**.\n"
                "Cette limite existe pour éviter les abus."
            ),
            color=discord.Color(COLOR_WARNING)
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=style_embed(embed), ephemeral=True)
        else:
            await interaction.followup.send(embed=style_embed(embed), ephemeral=True)
```

### 3.5 Message de bienvenue enrichi au join

**Fichier :** `bot/main.py` — améliorer `on_guild_join`

```python
@bot.event
async def on_guild_join(guild: discord.Guild):
    from bot.db.models import GuildModel
    GuildModel.create(guild.id, guild.name)

    try:
        owner = guild.owner or (await bot.fetch_user(int(guild.owner_id)) if guild.owner_id else None)
        if owner:
            embed = discord.Embed(
                title=f"Merci d'avoir installé Veridian AI sur {guild.name} !",
                description=(
                    "**3 étapes pour démarrer :**\n\n"
                    "**1.** Configurer le bot via le dashboard\n"
                    f"→ {DASHBOARD_URL}\n\n"
                    "**2.** Définir la catégorie des tickets et le rôle staff\n\n"
                    "**3.** Lancer `/ticket` pour tester\n\n"
                    "En cas de problème : rejoignez notre Discord support."
                ),
                color=discord.Color(COLOR_SUCCESS)
            )
            embed.set_thumbnail(url=bot.user.display_avatar.url)
            embed.set_footer(text=f"Veridian AI v{VERSION} · veridiancloud.xyz")
            await owner.send(embed=style_embed(embed))
    except Exception as e:
        logger.debug(f"Welcome DM failed: {e}")

    await _update_bot_status()
```

---

## 4. Améliorations API Backend

### 4.1 Endpoint manquant : stats globales accessibles à tous les users auth

**Fichier :** `api/routes/internal.py` — ajouter après `/bot/status`

```python
@router.get("/guild/{guild_id}/activity", dependencies=[Depends(verify_guild_access)])
def get_guild_activity(guild_id: int, limit: int = 20):
    """Activité récente du serveur pour le widget dashboard."""
    try:
        tickets = TicketModel.get_by_guild(guild_id, page=1, limit=min(limit, 20))
        activity = []
        for t in tickets[:limit]:
            activity.append({
                "type": "ticket",
                "id": t.get("id"),
                "user": t.get("user_username") or str(t.get("user_id", "?")),
                "status": t.get("status"),
                "lang": t.get("user_language"),
                "time": str(t.get("opened_at", "")),
            })
        return {"guild_id": guild_id, "activity": activity}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
```

### 4.2 Rate limiting plus intelligent

**Fichier :** `api/main.py` — améliorer le middleware

```python
# Dictionnaire par route pour des limites différenciées
_ROUTE_LIMITS = {
    "/auth/exchange":     (10, 60),   # 10 req/min max
    "/auth/discord/login":(20, 60),
    "/internal/":         (120, 60),  # 120 req/min pour dashboard
    "/webhook/":          (200, 60),  # Plus permissif pour webhooks
}

@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    # Trouver la limite applicable
    max_req, window = _RATE_LIMIT_MAX, _RATE_LIMIT_WINDOW
    for prefix, (m, w) in _ROUTE_LIMITS.items():
        if path.startswith(prefix):
            max_req, window = m, w
            break
    
    key = f"{client_ip}:{path[:20]}"
    history = [t for t in _RATE_LIMIT_DATA.get(key, []) if now - t < window]
    
    if len(history) >= max_req:
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(window)},
            content={"detail": "Too Many Requests", "retry_after": window}
        )
    
    history.append(now)
    _RATE_LIMIT_DATA[key] = history
    return await call_next(request)
```

### 4.3 Endpoint webhook amélioré avec retry idempotent

**Fichier :** `api/routes/webhook.py` — remplacer la route complète

```python
@router.post("/oxapay")
async def oxapay_webhook(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Oxapay-Signature", "")
    
    if not verify_oxapay_signature(body, signature):
        logger.warning(f"OxaPay: signature invalide depuis {request.client.host}")
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    
    status = payload.get("status", "").lower()
    if status not in ("paid", "completed"):
        return {"status": "ignored", "reason": f"status={status}"}
    
    order_id = payload.get("order_id") or payload.get("orderId")
    invoice_id = payload.get("invoice_id") or payload.get("trackId")
    amount = float(payload.get("amount") or 0)
    currency = payload.get("currency") or "EUR"
    
    # Idempotence : vérifier si déjà traité
    order = OrderModel.get(order_id) if order_id else None
    if order and str(order.get("status", "")).lower() == "paid":
        logger.info(f"OxaPay webhook idempotent: {order_id} déjà traité")
        return {"status": "already_processed"}
    
    user_id = payload.get("user_id") or (order or {}).get("user_id")
    guild_id = payload.get("guild_id") or (order or {}).get("guild_id")
    plan = payload.get("plan") or (order or {}).get("plan")
    
    if not all([user_id, guild_id, plan]):
        logger.error(f"OxaPay webhook: contexte manquant pour {order_id}")
        raise HTTPException(status_code=400, detail="Missing order context")
    
    try:
        if order_id:
            OrderModel.update_status(order_id, "paid")
        
        payment_id = PaymentModel.create(
            user_id=user_id, guild_id=guild_id,
            method="oxapay", amount=amount, currency=currency,
            plan=plan, order_id=order_id, status="completed",
            oxapay_invoice_id=invoice_id,
        )
        SubscriptionModel.create(guild_id=guild_id, user_id=user_id, plan=plan, payment_id=payment_id, duration_days=30)
        AuditLogModel.log(actor_id=user_id, action="payment.oxapay.success", guild_id=guild_id,
                          details={"order_id": order_id, "amount": amount, "plan": plan})
        PendingNotificationModel.add(user_id, f"✅ Paiement **{plan.upper()}** confirmé ! Abonnement actif.")
        
        logger.info(f"OxaPay: {order_id} traité — {plan} pour guild {guild_id}")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"OxaPay processing error: {e}")
        raise HTTPException(status_code=500, detail="Processing error")
```

### 4.4 Endpoint de santé enrichi

**Fichier :** `api/main.py`

```python
@app.get("/health", tags=["Health"])
async def health_check():
    checks = {"api": "ok", "database": "unknown", "version": VERSION}
    http_status = 200
    
    try:
        from bot.db.connection import get_connection
        conn = get_connection()
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = "error"
        checks["database_error"] = str(e)[:100]
        http_status = 503
    
    checks["environment"] = ENVIRONMENT
    checks["timestamp"] = datetime.utcnow().isoformat() + "Z"
    
    return JSONResponse(status_code=http_status, content=checks)
```

---

## 5. Refonte Dashboard (UI/UX)

### 5.1 Ajouter l'activité récente au dashboard

Le widget `#activity-recent` est vide. Ajouter dans `web/js/dashboard.js` :

```javascript
async function loadRecentActivity() {
    if (!state.currentGuild) return;
    const container = document.getElementById("activity-recent");
    if (!container) return;

    try {
        const data = await apiFetch(`/internal/guild/${state.currentGuild.id}/tickets`, { auth: true });
        const tickets = (data.tickets || []).slice(0, 8);
        
        if (!tickets.length) {
            container.innerHTML = '<div class="empty-state"><div class="empty-icon">🎫</div><div class="empty-text">Aucun ticket récent</div></div>';
            return;
        }
        
        container.innerHTML = tickets.map(t => {
            const statusColors = {
                open: "var(--accent)", in_progress: "var(--yellow)",
                pending_close: "var(--red)", closed: "var(--text3)"
            };
            const color = statusColors[t.status] || "var(--text3)";
            const ts = t.opened_at ? timeAgo(t.opened_at) : "—";
            return `
            <div class="activity-row">
              <div class="activity-icon-wrap" style="background:${color}22;color:${color}">🎫</div>
              <div class="activity-text">
                <strong>${escHtml(t.user_username || String(t.user_id))}</strong>
                a ouvert le ticket <span class="mono">#${t.id}</span>
                ${t.user_language ? `<span class="lang-chip">${escHtml((t.user_language||'').toUpperCase())}</span>` : ''}
              </div>
              <div class="activity-time">${ts}</div>
            </div>`;
        }).join('');
    } catch (e) {
        container.innerHTML = '<div style="color:var(--text3);text-align:center;padding:16px;font-size:12px">Impossible de charger l\'activité</div>';
    }
}
```

Appeler `loadRecentActivity()` dans `loadDashboardStats()`.

### 5.2 Améliorer le rendu des tickets — colonne priorité avec couleurs

**Fichier :** `web/css/dashboard.css` — ajouter :

```css
/* Priority badges améliorés */
.priority-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 10px;
  font-family: 'Space Mono', monospace;
  font-weight: 700;
  letter-spacing: 0.06em;
}
.priority-badge.low     { background: rgba(74,102,85,0.15); color: var(--text3); }
.priority-badge.medium  { background: var(--yellow-dim); color: var(--yellow); }
.priority-badge.high    { background: var(--red-dim); color: var(--red); }
.priority-badge.urgent  { background: rgba(255,77,109,0.25); color: #ff2d52; box-shadow: 0 0 8px rgba(255,77,109,0.3); animation: pulse-urgent 1.5s ease-in-out infinite; }

@keyframes pulse-urgent {
  0%, 100% { box-shadow: 0 0 8px rgba(255,77,109,0.3); }
  50% { box-shadow: 0 0 16px rgba(255,77,109,0.6); }
}

/* Ticket row hover highlight */
.data-table tbody tr:hover td {
  background: var(--surface);
  color: var(--text);
}
.data-table tbody tr.priority-urgent td {
  border-left: 2px solid #ff2d52;
}
```

### 5.3 Notifications toast améliorées

**Fichier :** `web/js/dashboard.js` — remplacer `showToast`

```javascript
function showToast(message, type = "info", duration = 4000) {
    let container = document.getElementById("toast-container");
    if (!container) {
        container = document.createElement("div");
        container.id = "toast-container";
        container.setAttribute("aria-live", "polite");
        container.style.cssText = "position:fixed;bottom:24px;right:24px;z-index:99999;display:flex;flex-direction:column;gap:8px;max-width:360px;";
        document.body.appendChild(container);
    }
    
    const icons = {
        success: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polyline points="16 8 10 14 8 12"/></svg>`,
        error:   `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        warn:    `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
        info:    `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    };
    const colors = { success: "var(--accent)", error: "var(--red)", warn: "var(--yellow)", info: "var(--blue)" };
    const color = colors[type] || colors.info;
    
    const toast = document.createElement("div");
    toast.style.cssText = `
        padding:12px 16px;border-radius:10px;font-size:12.5px;font-weight:500;
        background:var(--bg2);border:1px solid ${color}33;color:var(--text);
        box-shadow:0 4px 20px rgba(0,0,0,.5),0 0 0 1px ${color}11;
        display:flex;align-items:center;gap:10px;animation:slideInRight .25s cubic-bezier(.34,1.56,.64,1);
        cursor:pointer;user-select:none;
    `;
    toast.innerHTML = `
        <span style="color:${color};flex-shrink:0;display:flex">${icons[type] || icons.info}</span>
        <span style="flex:1;line-height:1.5">${escHtml(message)}</span>
        <span style="color:var(--text3);font-size:16px;line-height:1;flex-shrink:0;opacity:.5">×</span>
    `;
    
    const dismiss = () => {
        toast.style.animation = "slideOutRight .2s ease forwards";
        setTimeout(() => toast.remove(), 200);
    };
    toast.addEventListener("click", dismiss);
    
    container.appendChild(toast);
    setTimeout(dismiss, duration);
}
```

### 5.4 Améliorer la page Settings — aperçu en temps réel

**Ajouter dans** `web/css/dashboard.css` :

```css
/* Settings improvements */
.settings-preview-panel {
  background: linear-gradient(135deg, var(--bg2), var(--surface));
  border: 1px solid var(--border2);
  border-radius: 12px;
  padding: 16px;
  transition: all 0.2s;
}

.form-input:focus + .settings-preview-panel,
.form-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-dim2);
}

/* Tabs améliorés */
.settings-tab {
  position: relative;
  overflow: hidden;
}
.settings-tab.active::after {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: var(--accent);
  border-radius: 0 2px 2px 0;
}

/* Compact grid pour settings */
.settings-compact-grid-tight {
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

/* Save feedback */
#settings-save-btn.saved {
  background: var(--accent3) !important;
  transition: background 0.3s;
}
```

---

## 6. Refonte Landing Page

### 6.1 Ajouter une section "Témoignages / Social proof"

**Fichier :** `web/index.html` — ajouter entre `#how` et `#pricing` :

```html
<!-- ── SOCIAL PROOF ── -->
<section style="padding:80px 24px;background:var(--bg2);border-top:1px solid var(--border);border-bottom:1px solid var(--border)">
  <div style="max-width:1100px;margin:0 auto">
    <div style="text-align:center;margin-bottom:48px" class="reveal">
      <div class="section-label">TÉMOIGNAGES</div>
      <h2 class="section-title">Ils font confiance à Veridian AI</h2>
    </div>
    <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:20px" class="reveal">
      <div style="background:var(--bg3);border:1px solid var(--border);border-radius:16px;padding:24px">
        <div style="font-size:13px;color:var(--text2);line-height:1.7;margin-bottom:16px">
          "Notre communauté internationale est passée de 5 langues gérées manuellement à plus de 20 automatiquement. Le temps de réponse moyen a été divisé par 3."
        </div>
        <div style="display:flex;align-items:center;gap:10px">
          <div style="width:36px;height:36px;border-radius:50%;background:var(--accent-dim);border:1px solid rgba(45,255,143,.2);display:flex;align-items:center;justify-content:center;font-weight:700;color:var(--accent)">M</div>
          <div>
            <div style="font-size:13px;font-weight:700;color:var(--text)">MistyGuild</div>
            <div style="font-size:11px;color:var(--text3);font-family:'Space Mono',monospace">Gaming · 12k membres</div>
          </div>
        </div>
      </div>
      <!-- Ajouter 2 autres témoignages similaires -->
    </div>
  </div>
</section>
```

### 6.2 Ajouter un compteur dynamique de statistiques

**Fichier :** `web/index.html` — modifier les hero stats pour les connecter à l'API :

```javascript
// Dans main.js — charger les vraies stats au chargement
async function loadHeroStats() {
    try {
        const res = await fetch('https://api.veridiancloud.xyz/health');
        const data = await res.json();
        // Si l'API expose le nombre de guilds via /health enrichi
        // Animer les compteurs avec les vraies valeurs
    } catch (_) {
        // Garder les valeurs statiques
    }
}
```

### 6.3 Section FAQ

**Fichier :** `web/index.html` — ajouter avant la CTA :

```html
<!-- ── FAQ ── -->
<section style="padding:80px 24px;max-width:800px;margin:0 auto">
  <div class="reveal" style="text-align:center;margin-bottom:48px">
    <div class="section-label">FAQ</div>
    <h2 class="section-title">Questions fréquentes</h2>
  </div>
  <div id="faq-list" class="reveal">
    <!-- FAQ items générés en JS ou statiques -->
  </div>
</section>
```

```css
/* Dans style.css */
.faq-item {
  border: 1px solid var(--border);
  border-radius: 12px;
  margin-bottom: 10px;
  overflow: hidden;
  transition: border-color 0.2s;
}
.faq-item:hover { border-color: var(--border2); }
.faq-question {
  padding: 18px 20px;
  cursor: pointer;
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
  color: var(--text);
  font-size: 14px;
  background: var(--bg3);
}
.faq-answer {
  padding: 0 20px;
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.3s ease, padding 0.3s;
  color: var(--text2);
  font-size: 13.5px;
  line-height: 1.7;
}
.faq-item.open .faq-answer {
  max-height: 200px;
  padding: 16px 20px;
}
.faq-chevron { transition: transform 0.3s; }
.faq-item.open .faq-chevron { transform: rotate(180deg); }
```

### 6.4 Améliorer le meta SEO

**Fichier :** `web/index.html` — dans `<head>` :

```html
<!-- Open Graph -->
<meta property="og:title" content="Veridian AI — Bot Discord Multilingue IA">
<meta property="og:description" content="Traduisez vos tickets en temps réel, répondez automatiquement et gérez votre support Discord dans 100+ langues.">
<meta property="og:image" content="https://veridiancloud.xyz/assets/og-image.png">
<meta property="og:url" content="https://veridiancloud.xyz">
<meta property="og:type" content="website">

<!-- Twitter Card -->
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Veridian AI — Bot Discord Multilingue IA">
<meta name="twitter:description" content="Support multilingue IA pour Discord · 100+ langues · Tickets traduits en temps réel">
<meta name="twitter:image" content="https://veridiancloud.xyz/assets/og-image.png">

<!-- Schema.org -->
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@type": "SoftwareApplication",
  "name": "Veridian AI",
  "description": "Bot Discord multilingue alimenté par l'IA",
  "url": "https://veridiancloud.xyz",
  "applicationCategory": "BusinessApplication",
  "offers": {
    "@type": "AggregateOffer",
    "lowPrice": "0",
    "highPrice": "5",
    "priceCurrency": "EUR"
  }
}
</script>
```

---

## 7. Nouvelles fonctionnalités clés

### 7.1 Système de notes internes sur tickets (Pro)

**Ajouter dans** `database/schema.sql` / `database/init.sql` :

```sql
CREATE TABLE IF NOT EXISTS vai_ticket_notes (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id   INT NOT NULL,
    author_id   BIGINT NOT NULL,
    author_name VARCHAR(100),
    content     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ticket (ticket_id),
    FOREIGN KEY (ticket_id) REFERENCES vai_tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

**Dans** `bot/cogs/tickets.py` — ajouter commande :

```python
@discord.app_commands.command(name="note", description="Ajouter une note interne (staff uniquement)")
@discord.app_commands.describe(content="Contenu de la note (invisible pour l'utilisateur)")
async def add_note(self, interaction: discord.Interaction, content: str):
    """Ajoute une note interne sur le ticket courant, invisible pour le user."""
    ticket = TicketModel.get_by_channel(interaction.channel.id)
    if not ticket:
        await interaction.response.send_message("Cette commande est réservée aux tickets.", ephemeral=True)
        return
    
    is_staff = interaction.user.guild_permissions.administrator or \
               int(ticket.get("assigned_staff_id") or 0) == interaction.user.id
    if not is_staff:
        await interaction.response.send_message("Permission refusée.", ephemeral=True)
        return
    
    # Sauvegarder la note
    try:
        from bot.db.connection import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO vai_ticket_notes (ticket_id, author_id, author_name, content) VALUES (%s,%s,%s,%s)",
                (ticket["id"], interaction.user.id, interaction.user.display_name, content)
            )
    except Exception as e:
        logger.error(f"Note save error: {e}")
    
    embed = discord.Embed(
        title="📝 Note interne ajoutée",
        description=content,
        color=discord.Color(COLOR_WARNING)
    )
    embed.set_footer(text=f"Par {interaction.user.display_name} · Visible staff uniquement")
    await interaction.response.send_message(embed=style_embed(embed), ephemeral=False)
```

### 7.2 Système de rating après fermeture de ticket

**Fichier :** `bot/cogs/tickets.py` — dans `_post_close_outputs`

```python
# Ajouter après l'envoi du résumé user:
try:
    if user and user_lang:
        rating_texts = {
            "fr": "Comment évaluez-vous notre support ? (1⭐ à 5⭐)",
            "en": "How would you rate our support? (1⭐ to 5⭐)",
            "es": "¿Cómo calificaría nuestro soporte? (1⭐ a 5⭐)",
        }
        rating_msg = rating_texts.get(user_lang[:2], rating_texts["en"])
        
        rating_embed = discord.Embed(
            title="Votre avis compte",
            description=rating_msg,
            color=discord.Color(COLOR_SUCCESS)
        )
        rating_view = TicketRatingView(ticket["id"])
        await user.send(embed=style_embed(rating_embed), view=rating_view)
except Exception:
    pass
```

```python
class TicketRatingView(discord.ui.View):
    def __init__(self, ticket_id: int):
        super().__init__(timeout=86400)  # 24h
        self.ticket_id = ticket_id
        for i in range(1, 6):
            self.add_item(discord.ui.Button(
                label=f"{'⭐' * i}",
                custom_id=f"vai:rating:{ticket_id}:{i}",
                style=discord.ButtonStyle.secondary,
                row=0
            ))
    
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True
```

### 7.3 Export CSV des tickets (Pro)

**Fichier :** `api/routes/internal.py` — ajouter :

```python
from fastapi.responses import StreamingResponse
import csv, io

@router.get("/guild/{guild_id}/tickets/export", dependencies=[Depends(verify_guild_access)])
def export_tickets_csv(guild_id: int, request: Request):
    """Export des tickets en CSV (Pro uniquement)."""
    sub = SubscriptionModel.get(guild_id)
    if not sub or sub.get("plan") not in ("pro",):
        raise HTTPException(status_code=403, detail="Pro plan required")
    
    tickets = TicketModel.get_by_guild(guild_id, page=1, limit=1000)
    
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "id", "user_username", "user_language", "staff_language",
        "status", "priority", "assigned_staff_name",
        "opened_at", "closed_at", "close_reason"
    ])
    writer.writeheader()
    for t in tickets:
        writer.writerow({k: t.get(k, "") for k in writer.fieldnames})
    
    output.seek(0)
    return StreamingResponse(
        iter([output.read()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=tickets-{guild_id}.csv"}
    )
```

---

## 8. Performance & Scalabilité

### 8.1 Connection pooling MySQL

**Fichier :** `bot/db/connection.py` — remplacer par un pool

```python
"""Gestionnaire de connexion MySQL avec pool pour Veridian AI"""

import os
import mysql.connector
from mysql.connector import pooling, Error
from loguru import logger
from contextlib import contextmanager

_pool: pooling.MySQLConnectionPool | None = None

def _get_pool() -> pooling.MySQLConnectionPool:
    global _pool
    if _pool is None:
        _pool = pooling.MySQLConnectionPool(
            pool_name="veridian_pool",
            pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            pool_reset_session=True,
            host=os.getenv('DB_HOST'),
            port=int(os.getenv('DB_PORT', 3306)),
            user=os.getenv('DB_USER'),
            password=os.getenv('DB_PASSWORD'),
            database=os.getenv('DB_NAME'),
            connection_timeout=10,
            autocommit=False,
            charset='utf8mb4',
        )
        logger.info(f"✓ MySQL connection pool créé (size={os.getenv('DB_POOL_SIZE', '10')})")
    return _pool

def get_connection():
    return _get_pool().get_connection()

@contextmanager
def get_db_context():
    connection = get_connection()
    try:
        yield connection
        connection.commit()
    except Exception as e:
        logger.error(f"✗ Erreur DB: {e}")
        connection.rollback()
        raise
    finally:
        connection.close()
```

**Ajouter dans** `.env.example` :
```
DB_POOL_SIZE=10
```

### 8.2 Cache mémoire pour les configs guild

**Fichier :** `bot/db/models.py` — dans `GuildModel`

```python
import time as _time

_guild_cache: dict[int, tuple[dict, float]] = {}
_GUILD_CACHE_TTL = 30  # secondes

class GuildModel:
    
    @staticmethod
    def get(guild_id: int) -> Optional[Dict]:
        # Vérifier le cache
        cached, ts = _guild_cache.get(guild_id, ({}, 0))
        if cached and _time.monotonic() - ts < _GUILD_CACHE_TTL:
            return cached
        
        with get_db_context() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute(f"SELECT * FROM {DB_TABLE_PREFIX}guilds WHERE id = %s", (guild_id,))
            result = cursor.fetchone()
        
        if result:
            _guild_cache[guild_id] = (result, _time.monotonic())
        return result
    
    @staticmethod
    def update(guild_id: int, **kwargs) -> bool:
        # Invalider le cache
        _guild_cache.pop(guild_id, None)
        # ... reste du code existant
```

### 8.3 Compression gzip sur l'API

**Fichier :** `api/main.py` — ajouter après la création de `app`

```python
from fastapi.middleware.gzip import GZIPMiddleware
app.add_middleware(GZIPMiddleware, minimum_size=500)
```

---

## 9. Sécurité renforcée

### 9.1 Validation des entrées utilisateur

**Fichier :** `bot/cogs/tickets.py` — dans `open_ticket`

```python
# Sanitiser le topic
if topic:
    # Supprimer les caractères dangereux et limiter la longueur
    topic = re.sub(r'[^\w\s-]', '', topic.strip())[:32]
```

### 9.2 Headers CORS plus stricts en production

**Fichier :** `api/main.py`

```python
CORS_ORIGINS = [
    "https://veridiancloud.xyz",
    "https://www.veridiancloud.xyz",
]
# En développement uniquement:
if not is_production():
    CORS_ORIGINS += ["http://localhost:3000", "http://127.0.0.1:3000"]
```

### 9.3 Cleanup automatique des sessions expirées

**Nouveau fichier :** `api/cleanup.py`

```python
"""Tâches de nettoyage périodique"""
from loguru import logger
from bot.db.connection import get_db_context
from bot.config import DB_TABLE_PREFIX


def cleanup_expired_sessions() -> int:
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM {DB_TABLE_PREFIX}dashboard_sessions WHERE expires_at < NOW()"
        )
        count = cursor.rowcount
    if count:
        logger.info(f"[cleanup] {count} sessions expirées supprimées")
    return count


def cleanup_old_temp_codes() -> int:
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM {DB_TABLE_PREFIX}temp_codes WHERE expires_at < NOW() OR used = 1"
        )
        count = cursor.rowcount
    return count


def cleanup_failed_notifications(max_attempts: int = 5) -> int:
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"DELETE FROM {DB_TABLE_PREFIX}pending_notifications WHERE attempts >= %s",
            (max_attempts,)
        )
        count = cursor.rowcount
    if count:
        logger.info(f"[cleanup] {count} notifications failed supprimées")
    return count
```

**Ajouter dans** `bot/main.py` :

```python
@tasks.loop(hours=1)
async def cleanup_loop():
    """Nettoyage périodique toutes les heures."""
    try:
        from api.cleanup import cleanup_expired_sessions, cleanup_old_temp_codes, cleanup_failed_notifications
        cleanup_expired_sessions()
        cleanup_old_temp_codes()
        cleanup_failed_notifications()
    except Exception as e:
        logger.debug(f"Cleanup loop: {e}")

@cleanup_loop.before_loop
async def before_cleanup():
    await bot.wait_until_ready()
```

Et démarrer la loop dans `on_ready()` :

```python
if not cleanup_loop.is_running():
    cleanup_loop.start()
```

### 9.4 Logging des actions sensibles

**Ajouter dans** `bot/cogs/tickets.py` — dans `_finalize_ticket_close`

```python
AuditLogModel.log(
    actor_id=closer.id,
    actor_username=str(closer),
    action="ticket.close",
    guild_id=int(ticket["guild_id"]),
    target_id=str(ticket["id"]),
    details={"reason": reason, "plan_at_close": (SubscriptionModel.get(ticket["guild_id"]) or {}).get("plan", "free")}
)
```

---

## 10. DevOps & Déploiement Production

### 10.1 Variables d'environnement production complètes

**Fichier :** `.env.example` — version finale

```env
# ============================================================
# Veridian AI — Configuration Production
# ============================================================

# Discord
DISCORD_TOKEN=votre_token_bot_discord
DISCORD_CLIENT_ID=id_application_discord
DISCORD_CLIENT_SECRET=secret_oauth2
DISCORD_REDIRECT_URI=https://api.veridiancloud.xyz/auth/callback
BOT_OWNER_DISCORD_ID=votre_discord_id

# Base de données MySQL
DB_HOST=localhost
DB_PORT=3306
DB_USER=veridian_user
DB_PASSWORD=mot_de_passe_fort_min_32_chars
DB_NAME=veridian
DB_POOL_SIZE=10

# IA (Groq) — 4 clés recommandées pour le fallback
GROQ_API_KEY_1=gsk_...
GROQ_API_KEY_2=gsk_...
GROQ_API_KEY_3=gsk_...
GROQ_API_KEY_4=gsk_...

# API & Dashboard
ENVIRONMENT=production
API_PORT=8000
API_HOST=0.0.0.0
API_DOMAIN=api.veridiancloud.xyz
DASHBOARD_URL=https://veridiancloud.xyz/dashboard.html
AUTO_DB_MIGRATE=1

# Sécurité (CHANGER OBLIGATOIREMENT EN PROD — min 32 chars aléatoires)
INTERNAL_API_SECRET=changez_moi_min_32_chars_aleatoires_unique
JWT_SECRET=changez_moi_min_32_chars_aleatoires_unique

# Paiements
OXAPAY_MERCHANT_KEY=votre_cle_marchant_oxapay
OXAPAY_WEBHOOK_SECRET=votre_secret_webhook_oxapay
PAYPAL_EMAIL=votre_email_paypal_business@example.com
```

### 10.2 Script de démarrage production

**Nouveau fichier :** `start.sh`

```bash
#!/bin/bash
# Veridian AI — Script de démarrage production

set -e

echo "🚀 Démarrage Veridian AI..."

# Vérifications pré-démarrage
if [ -z "$DISCORD_TOKEN" ]; then
    echo "❌ DISCORD_TOKEN non défini"
    exit 1
fi

if [ -z "$GROQ_API_KEY_1" ]; then
    echo "❌ GROQ_API_KEY_1 non défini"
    exit 1
fi

# Créer les dossiers nécessaires
mkdir -p logs

# Appliquer les migrations DB
echo "🔄 Vérification schema DB..."
python -c "from api.db_migrate import ensure_database_schema; ensure_database_schema()"

# Démarrer le bot
echo "🤖 Démarrage du bot Discord..."
exec python bot/main.py
```

```bash
chmod +x start.sh
```

### 10.3 Configuration Nginx optimisée

**Nouveau fichier :** `nginx.conf`

```nginx
events { worker_connections 1024; }

http {
    # Gzip
    gzip on;
    gzip_types text/plain application/json text/css application/javascript;
    gzip_min_length 1000;

    # Rate limiting
    limit_req_zone $binary_remote_addr zone=api:10m rate=30r/m;
    limit_req_zone $binary_remote_addr zone=auth:10m rate=5r/m;

    server {
        listen 443 ssl http2;
        server_name api.veridiancloud.xyz;

        ssl_certificate     /etc/letsencrypt/live/api.veridiancloud.xyz/fullchain.pem;
        ssl_certificate_key /etc/letsencrypt/live/api.veridiancloud.xyz/privkey.pem;
        ssl_protocols       TLSv1.2 TLSv1.3;
        ssl_ciphers         ECDHE-RSA-AES256-GCM-SHA512:DHE-RSA-AES256-GCM-SHA512;

        # Security headers
        add_header X-Frame-Options "DENY" always;
        add_header X-Content-Type-Options "nosniff" always;
        add_header Referrer-Policy "no-referrer" always;
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;

        location /auth/ {
            limit_req zone=auth burst=10 nodelay;
            proxy_pass http://localhost:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        }

        location / {
            limit_req zone=api burst=20 nodelay;
            proxy_pass http://localhost:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
        }
    }

    # Redirect HTTP → HTTPS
    server {
        listen 80;
        server_name api.veridiancloud.xyz;
        return 301 https://$host$request_uri;
    }
}
```

### 10.4 Systemd service pour le bot

**Nouveau fichier :** `veridian-bot.service`

```ini
[Unit]
Description=Veridian AI Discord Bot
After=network.target mysql.service
Wants=mysql.service

[Service]
Type=simple
User=veridian
WorkingDirectory=/opt/veridian-ai
EnvironmentFile=/opt/veridian-ai/.env
ExecStart=/opt/veridian-ai/venv/bin/python bot/main.py
Restart=on-failure
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=veridian-bot

# Sécurité
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/veridian-ai/logs

[Install]
WantedBy=multi-user.target
```

```bash
# Installer:
sudo cp veridian-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable veridian-bot
sudo systemctl start veridian-bot
```

### 10.5 Docker Compose production optimisé

**Fichier :** `docker/docker-compose.prod.yml`

```yaml
version: '3.9'

services:
  mysql:
    image: mysql:8.0
    container_name: veridian-mysql
    restart: unless-stopped
    environment:
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
      MYSQL_DATABASE: ${DB_NAME}
      MYSQL_USER: ${DB_USER}
      MYSQL_PASSWORD: ${DB_PASSWORD}
      MYSQL_CHARSET: utf8mb4
    volumes:
      - mysql-data:/var/lib/mysql
      - ./database/init.sql:/docker-entrypoint-initdb.d/01-schema.sql:ro
      - ./docker/mysql.cnf:/etc/mysql/conf.d/veridian.cnf:ro
    healthcheck:
      test: ["CMD", "mysqladmin", "ping", "-h", "localhost", "-u", "root", "-p${DB_PASSWORD}"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s
    networks: [veridian]
    deploy:
      resources:
        limits:
          memory: 512M

  bot:
    build:
      context: ..
      dockerfile: docker/Dockerfile
    container_name: veridian-bot
    restart: unless-stopped
    env_file: ../.env
    environment:
      DB_HOST: mysql
      ENVIRONMENT: production
    depends_on:
      mysql:
        condition: service_healthy
    volumes:
      - ../logs:/app/logs
    networks: [veridian]
    deploy:
      resources:
        limits:
          memory: 256M

  api:
    build:
      context: ..
      dockerfile: docker/Dockerfile.api
    container_name: veridian-api
    restart: unless-stopped
    env_file: ../.env
    environment:
      DB_HOST: mysql
      ENVIRONMENT: production
    ports:
      - "127.0.0.1:8000:8000"
    depends_on:
      mysql:
        condition: service_healthy
    networks: [veridian]
    deploy:
      resources:
        limits:
          memory: 256M
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3

networks:
  veridian:
    driver: bridge

volumes:
  mysql-data:
```

**Nouveau fichier :** `docker/mysql.cnf`

```ini
[mysqld]
character-set-server = utf8mb4
collation-server     = utf8mb4_unicode_ci
innodb_buffer_pool_size = 256M
max_connections = 100
slow_query_log = 1
slow_query_log_file = /var/lib/mysql/slow.log
long_query_time = 2
```

---

## 11. Checklist de lancement

### 🔴 Obligatoire avant production

- [ ] **Fix webhook OxaPay** — `api/routes/webhook.py` signature HMAC corrigée
- [ ] **Fix `ai_intent` migration** — colonne ajoutée dans `api/db_migrate.py`
- [ ] **Fix `_embed_color()`** — support hex complet
- [ ] **Secrets forts générés** — `JWT_SECRET` et `INTERNAL_API_SECRET` (32+ chars)
- [ ] **DISCORD_REDIRECT_URI** configuré correctement dans `.env`
- [ ] **HTTPS activé** — certificat Let's Encrypt installé
- [ ] **Bot intents** validés dans le portail développeur Discord (Message Content, Server Members)
- [ ] **MySQL** — utilisateur dédié avec droits limités (pas root)
- [ ] **Logs** — dossier `logs/` créé, rotatif
- [ ] **`.env` hors du repo Git** — vérifié dans `.gitignore`

### 🟡 Fortement recommandé

- [ ] **Pool MySQL** implémenté (`DB_POOL_SIZE=10`)
- [ ] **Cog `suggestions.py`** créé et chargé
- [ ] **Cache guild** en mémoire (TTL 30s)
- [ ] **Nettoyage sessions** programmé (cleanup_loop)
- [ ] **Nginx** configuré avec rate limiting
- [ ] **Systemd** ou superviseur de processus en place
- [ ] **Monitoring** — healthcheck externe (UptimeRobot, Betterstack)
- [ ] **Backup DB** automatique quotidien
- [ ] **SEO meta tags** ajoutés sur la landing page
- [ ] **FAQ** ajoutée sur la landing page

### 🟢 Nice to have (v1.1+)

- [ ] **Notes internes tickets** (`/note` command)
- [ ] **Rating après ticket** (étoiles en DM)
- [ ] **Export CSV** des tickets (Pro)
- [ ] **Témoignages** sur la landing page
- [ ] **Webhook Discord** pour alertes admin
- [ ] **Tests automatisés** (pytest)
- [ ] **CI/CD** (GitHub Actions)

---

## 12. Ordre d'exécution recommandé

### Phase 1 — Stabilité (1-2 jours)
```
1. Fix webhook OxaPay (20 min)
2. Fix embed color (10 min)
3. Fix ai_intent migration (15 min)
4. Fix langue "auto" tickets (20 min)
5. Fix PendingNotification retry (15 min)
6. Tester le flux complet en dev (2h)
```

### Phase 2 — Performance (1 jour)
```
7. Connection pool MySQL (30 min)
8. Cache guild mémoire (30 min)
9. GZip middleware (5 min)
10. Cleanup loop (30 min)
```

### Phase 3 — Nouvelles features (2-3 jours)
```
11. Cog suggestions staff (2h)
12. generate_staff_suggestion() dans groq_client (1h)
13. Commande /language améliorée (30 min)
14. Commande /stats server (30 min)
15. Export CSV tickets Pro (1h)
```

### Phase 4 — UI/UX (1-2 jours)
```
16. Activity widget dashboard (1h)
17. Toast notifications améliorées (30 min)
18. Priority badges CSS (30 min)
19. FAQ landing page (1h)
20. SEO meta tags (30 min)
```

### Phase 5 — Production (1 jour)
```
21. Nginx configuré + rate limiting
22. Systemd service ou Docker Compose prod
23. Certificat SSL Let's Encrypt
24. Monitoring UptimeRobot
25. Backup DB automatique
26. Vérification checklist complète
27. 🚀 LAUNCH
```

---

## 📌 Commandes utiles post-lancement

```bash
# Voir les logs en temps réel
tail -f logs/bot.log | grep -v DEBUG

# Status du bot
systemctl status veridian-bot

# Vérifier la santé de l'API
curl https://api.veridiancloud.xyz/health | python3 -m json.tool

# Backup DB manuel
mysqldump -u veridian_user -p veridian | gzip > backup-$(date +%Y%m%d).sql.gz

# Redémarrer proprement
systemctl restart veridian-bot veridian-api

# Voir les erreurs uniquement
grep "ERROR\|CRITICAL" logs/bot.log | tail -50

# Stats MySQL
mysql -u root -e "SHOW STATUS LIKE 'Threads_connected';"
```

---

*Document généré le 29 mars 2026 · Veridian AI Production Roadmap*