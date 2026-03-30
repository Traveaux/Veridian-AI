# 🚀 Veridian AI — Roadmap v2.0 Production-Ready & Rentable
> **Cible :** 1.0-stable rentable · Rédigé : Mars 2026 · Mise à jour complète

---

## 📋 Table des matières

1. [Analyse concurrentielle & Positionnement](#1-analyse-concurrentielle--positionnement)
2. [Nouveau modèle économique](#2-nouveau-modèle-économique)
3. [Fonctionnalités manquantes vs concurrents](#3-fonctionnalités-manquantes-vs-concurrents)
4. [Refonte Dashboard — Architecture & UX](#4-refonte-dashboard--architecture--ux)
5. [Nouvelles fonctionnalités bot Discord](#5-nouvelles-fonctionnalités-bot-discord)
6. [Implémentation base de données — Nouvelles tables](#6-implémentation-base-de-données--nouvelles-tables)
7. [Plan d'implémentation par sprints](#7-plan-dimplémentation-par-sprints)
8. [Corrections critiques à appliquer maintenant](#8-corrections-critiques-à-appliquer-maintenant)

---

## 1. Analyse concurrentielle & Positionnement

### Concurrents directs

| Bot | Prix | Points forts | Faiblesse |
|-----|------|-------------|-----------|
| **Ticket Tool** | 5–15$/m | Forms, panels, multi-catégories | Pas de traduction, dashboard complexe |
| **ModMail** | Gratuit/5$ | Simple, DM-based, tagging | Mono-langue, pas d'IA |
| **Helper.gg** | 10–30$/m | SLA, équipes, stats avancées | Cher, interface lourde |
| **Saikou** | 3–10$/m | Polls, automod, multi-features | Pas spécialisé tickets |
| **Pylon** | 8–25$/m | Scripting avancé, workflows | Technique, courbe d'apprentissage |

### Avantage différenciateur Veridian AI

> **Seul bot avec traduction bidirectionnelle IA + dashboard self-serve complet**

Veridian AI doit gagner sur :
- **Multilingue natif** (aucun concurrent ne fait ça sérieusement)
- **Self-serve total** — un admin non-technique configure tout en 5 min
- **Dashboard ergonomique** — aussi simple que Notion, aussi puissant que Ticket Tool
- **Prix juste** — meilleur rapport fonctionnalités/prix du marché

---

## 2. Nouveau modèle économique

### 2.1 Grille tarifaire révisée

#### Principes directeurs
- Free suffisamment généreux pour acquérir des utilisateurs
- Starter remplace Premium pour un prix d'entrée plus accessible
- Pro et Business capturent la valeur réelle
- Add-ons pour monétiser sans gating les features core

```
┌─────────────────────────────────────────────────────────────────────┐
│                    GRILLE TARIFAIRE v2.0                            │
├──────────┬──────────┬──────────┬──────────┬────────────────────────┤
│  FREE    │ STARTER  │   PRO    │ BUSINESS │ ADD-ONS                │
│  0€/m    │  4€/m    │  12€/m   │  29€/m   │                        │
│          │ (3€/m·an)│ (9€/m·an)│(22€/m·an)│                        │
├──────────┼──────────┼──────────┼──────────┼────────────────────────┤
│ 1 serveur│ 1 serveur│ 3 serveurs│Illimité  │ +Serveur extra: 5€/m  │
│ 50 tkt/m │ 300 tkt/m│ Illimité │ Illimité │ +AI Tokens pack: 5€   │
│ 3 langues│ 15 langues│ 100+lang│ 100+lang │ +White-label: 15€/m   │
│ 1 panel  │ 3 panels │ Illimité │ Illimité │ +Priority support: 10€│
│ -        │ Forms    │ Forms    │ Forms+API│ +Custom domain: 8€/m  │
│ -        │ -        │ SLA      │ SLA+alerte│                       │
│ -        │ -        │ Exports  │ Exports  │                        │
│ -        │ -        │ API REST │ API REST │                        │
│ -        │ -        │ -        │ Webhooks │                        │
│ -        │ -        │ -        │ SSO/SAML │                        │
└──────────┴──────────┴──────────┴──────────┴────────────────────────┘
```

#### Comparaison avec le modèle actuel

| Actuel | Nouveau | Impact |
|--------|---------|--------|
| Free/Premium(2€)/Pro(5€) | Free/Starter(4€)/Pro(12€)/Business(29€) | MRR x3-4 |
| Pas d'annuel | -25% annuel | Réduit churn, cash-flow |
| Pas d'add-ons | 5 add-ons | Upsell naturel |
| 1 tier mid | 2 tiers mid | Meilleure conversion |

### 2.2 Métriques cibles année 1

```
Objectif 12 mois :
- 500 serveurs Free → 80 conversions Starter (16%) = 320€ MRR
- 80 Starter → 25 upgrades Pro (31%) = 300€ MRR
- 25 Pro → 8 Business (32%) = 232€ MRR
- Add-ons ~15% du MRR = ~128€ MRR

Total objectif : ~980€ MRR (~11 760€ ARR)

Seuil de rentabilité estimé : 400€ MRR (hosting + API costs)
```

### 2.3 Usage-based AI tokens (optionnel Pro/Business)

```
Modèle : chaque plan inclut un quota mensuel de tokens IA.
Dépassement : 0.002€ / 1K tokens (largement supérieur au coût Groq)

Inclus par plan :
- Free    : 50K tokens/mois
- Starter : 300K tokens/mois
- Pro     : 2M tokens/mois
- Business: 10M tokens/mois

Dépassement auto-facturé si carte enregistrée (Stripe).
```

### 2.4 Intégration Stripe (priorité haute)

Remplacer/compléter OxaPay/PayPal par Stripe pour :
- Abonnements récurrents automatiques (webhooks fiables)
- Facturation annuelle avec discount
- Usage-based billing pour tokens
- Portail client self-serve (annuler, changer de plan)
- Stripe Tax pour conformité EU

**Fichier :** `bot/services/stripe_client.py` (nouveau)
**Fichier :** `api/routes/stripe_webhook.py` (nouveau)

---

## 3. Fonctionnalités manquantes vs concurrents

### 3.1 Ticket Tool killer features à implémenter

#### A. Interactive Ticket Forms (drag-and-drop)

```
Ce que Ticket Tool propose : formulaires avec champs custom.
Ce que Veridian doit avoir : pareil + traduit automatiquement.

Fonctionnement :
1. Admin crée un formulaire via le dashboard (drag-and-drop)
2. Champs : texte court, texte long, sélection, note/priorité
3. À l'ouverture du ticket, l'utilisateur remplit le formulaire
4. Les réponses sont intégrées dans le premier message du ticket
5. BONUS Veridian : tout traduit pour le staff automatiquement

DB : vai_ticket_forms, vai_form_fields, vai_form_responses
```

#### B. Multi-button Ticket Panels avec embed preview

```
Ce que Ticket Tool propose : panels avec jusqu'à 5 boutons, couleurs, emojis
Ce que Veridian doit avoir : pareil + preview Discord live dans le dashboard

Interface dashboard :
- Canvas drag-and-drop de l'embed Discord
- Preview temps réel (styled comme un vrai embed Discord)
- Boutons par catégorie avec label/couleur/emoji configurable
- Sélecteur de type (boutons rangée unique ou dropdown select menu)
```

#### C. Tags / Labels système

```
Tags assignables par le staff sur les tickets.
Exemples : "bug", "facturation", "urgent", "en attente client"

Fonctionnalités :
- Création libre de tags (couleur personnalisée)
- Filtrage par tags dans le dashboard
- Tags auto-suggérés par l'IA selon le contenu
- Stats par tag (les plus fréquents, temps de résolution)
```

#### D. Snippet / Réponses rapides (canned responses)

```
Le staff tape /snippet "remboursement" → réponse préformatée collée.
Traduite automatiquement dans la langue de l'utilisateur.

Dashboard : éditeur de snippets avec variables :
{user_name}, {ticket_id}, {guild_name}, {date}
```

#### E. Per-category staff roles

```
Catégorie "Facturation" → role @Billing
Catégorie "Support technique" → role @Tech-Support
Catégorie "Bugs" → role @Devs

Config dans le dashboard, pas de commande bot nécessaire.
```

#### F. Round-robin auto-assignment

```
Distribue les nouveaux tickets automatiquement entre les membres du staff.
Algorithme : least recently assigned (équitable).
Dashboard : activer/désactiver par catégorie, exclure certains membres.
```

### 3.2 Helper.gg killer features

#### G. SLA (Service Level Agreement) avec breach alerts

```
Configurez un délai de réponse max (ex: 2h pour Pro, 30min pour urgent)
Si un ticket dépasse le SLA sans réponse staff → alert automatique.

Dashboard :
- Définir SLA par catégorie et priorité
- Indicateur visuel sur les tickets (vert/orange/rouge)
- Alerte Discord dans le channel de logs quand SLA breach
- Stats SLA dans les analytics (% respecting SLA)
```

#### H. Thread support (Discord Threads)

```
Optionnel : créer des threads Discord au lieu de channels.
Avantages : moins de clutter, privé, auto-archive.
Config : "Channel mode" ou "Thread mode" dans le dashboard.
```

#### I. Outbound webhooks configurables

```
Chaque événement (ticket ouvert, fermé, tag ajouté, etc.)
peut déclencher un webhook vers n'importe quelle URL externe.
→ Integration Zapier, Make, n8n, Notion, Jira, etc.

Dashboard :
- Ajouter/tester des webhooks
- Sélectionner les événements à transmettre
- Voir l'historique des envois
```

### 3.3 ModMail killer features

#### J. User blacklist

```
Interdire à un utilisateur d'ouvrir des tickets.
Raison stockée, visible par le staff.
Durée : permanente ou temporaire.
Command : /blacklist @user [raison] [durée]
Dashboard : liste, recherche, suppression.
```

#### K. Post-close satisfaction surveys

```
After ticket close, DM to user with 5-star rating.
Staff voit les notes dans le dashboard.
Moyenne par agent, par catégorie, par semaine.
```

### 3.4 Fonctionnalités Veridian-only (différenciateurs)

#### L. AI Smart Routing

```
Analyse le premier message → suggère la catégorie correcte.
Si tickets mal catégorisés → suggestion de réassignation.
```

#### M. Multilingual Knowledge Base avec auto-traduction

```
Ajoutez une FAQ en anglais → disponible en 100 langues.
L'IA traduit à la volée selon la langue de l'utilisateur.
```

#### N. AI Ticket Summary pour le staff (internal notes)

```
Résumé IA automatique en cours de ticket (pas seulement à la fermeture).
Accessible via bouton "Résumé IA" dans le panel de contrôle.
```

---

## 4. Refonte Dashboard — Architecture & UX

### 4.1 Problèmes UX actuels identifiés

```
❌ Navigation confuse (ordres ≠ abonnement dans le même menu)
❌ Pas de onboarding pour les nouveaux serveurs
❌ Settings en onglets, informations trop denses
❌ Pas de feedback visuel sur les actions
❌ Boutons de deploy/déploiement peu accessibles
❌ Pas de recherche globale
❌ Pas d'historique d'activité
❌ Mobile inutilisable
❌ Preview Discord non représentatif
```

### 4.2 Nouvelle architecture de navigation

```
SIDEBAR REDESIGN :
────────────────────
  🏠 Vue d'ensemble
  ─────────────────
  📋 Tickets
      ├── En cours
      ├── En attente
      └── Fermés
  📌 Panels & Forms
      ├── Mes panels
      └── Formulaires
  📚 Knowledge Base
  👥 Staff & Équipes
  ─────────────────
  ⚙️  Configuration
      ├── Général
      ├── Catégories
      ├── Notifications
      └── Intégrations
  💳 Abonnement
  ─────────────────
  📊 Analytics (Pro+)
  🔔 Alertes SLA (Pro+)
  🌐 Webhooks (Business)
  ─────────────────
  ★  Admin Global    (super-admin only)
```

### 4.3 Ctrl+K Command Palette

```javascript
// Raccourci Ctrl+K → ouvre une palette de commandes
// Fonctionnalités :
// - Recherche dans les tickets (#1234, @username, "problème paiement")
// - Navigation rapide (aller à Configuration, Analytics...)
// - Actions rapides (Créer panel, Ajouter snippet, Blacklister user...)
// - Recherche KB

// Implementation : web/js/command-palette.js (nouveau fichier)
// Styles : web/css/command-palette.css (nouveau fichier)
```

### 4.4 Panel Builder — Visual Discord Preview

```
FONCTIONNEMENT :
1. Admin clique "Nouveau Panel"
2. Interface split en deux :
   - Gauche : éditeur (titre, description, boutons, couleur embed)
   - Droite : preview Discord live (pixel-perfect)
3. Drag-and-drop des boutons (réordonner)
4. Clic "Déployer" → bot poste dans le channel sélectionné

PREVIEW DISCORD :
- Avatar du bot en haut à gauche
- Embed avec bordure colorée (couleur configurable)
- Titre, description, footer
- Boutons Discord (primary/secondary/success/danger)
- Emojis custom supportés (via :emoji_name: format)
```

### 4.5 Refonte de la page Tickets

```
FILTRES :
- Barre de recherche principale (ID, username, contenu, tag)
- Filtres rapides par statut (chips cliquables)
- Filtre par catégorie, langue, assigné, priorité
- Tri : date, priorité, SLA breach, langue

TABLE ENRICHIE :
- Colonne "SLA" avec indicateur coloré (vert/orange/rouge)
- Colonne "Tags" (badges colorés)
- Colonne "Assigné" (avatar + nom)
- Action rapide : assigner, fermer, tagger directement

DETAIL DRAWER :
- Clic sur un ticket → panel latéral (pas de navigation)
- Voir l'historique complet des messages
- Ajouter une note interne
- Assigner, changer priorité, tagger
- Bouton "Transcript" → télécharge PDF
```

### 4.6 Analytics Dashboard (Pro+)

```
KPI CARDS :
- Tickets ouverts aujourd'hui vs hier (delta %)
- Temps de résolution moyen
- Score de satisfaction (notes post-fermeture)
- % SLA respecté

GRAPHIQUES :
- Volume de tickets par jour/semaine/mois (line chart)
- Distribution par catégorie (donut chart)
- Langues détectées ce mois (bar chart)
- Heures de pointe (heatmap)

AGENT LEADERBOARD (gamification) :
- Classement du staff par tickets résolus
- Temps de réponse moyen par agent
- Score de satisfaction par agent
```

### 4.7 Onboarding Wizard

```
Lors du premier accès dashboard pour un nouveau serveur :

ÉTAPE 1/4 : "Choisissez votre langue par défaut"
ÉTAPE 2/4 : "Configurez votre catégorie de tickets"
           (input ID ou sélecteur depuis dropdown des canaux)
ÉTAPE 3/4 : "Créez votre premier panel de tickets"
           (template prêt à l'emploi ou personnalisé)
ÉTAPE 4/4 : "Invitez votre équipe"
           (lien d'invitation admin)

→ Barre de progression visible
→ Chaque étape peut être sautée
→ Badge "Onboarding complété" dans le dashboard
```

### 4.8 Mobile Dashboard

```
BREAKPOINTS :
- ≥1200px : layout 3 colonnes (sidebar + main + detail)
- 768-1199px : sidebar repliable, main full-width
- <768px : navigation bottom bar, sidebar en drawer

COMPOSANTS MOBILES :
- Cartes tickets swipables (swipe gauche = fermer, droite = assigner)
- Fab button (+) pour actions rapides
- Notifications push browser (si permission)
```

---

## 5. Nouvelles fonctionnalités bot Discord

### 5.1 Architecture des nouvelles commandes

```
NOUVELLES COMMANDES :

/panel create                    → créer un panel (via dashboard recommandé)
/panel edit <panel_id>           → modifier
/panel deploy <channel>          → déployer dans un channel

/form create                     → créer un formulaire (via dashboard)
/form preview <form_id>          → aperçu d'un formulaire

/snippet add <nom> <contenu>     → ajouter une réponse rapide
/snippet list                    → lister les snippets
/snippet use <nom>               → coller un snippet dans le ticket actif

/tag add <nom> <couleur>         → créer un tag
/tag set <ticket_id> <nom>       → taguer un ticket
/tag remove <ticket_id> <nom>    → retirer un tag

/assign @membre                  → assigner manuellement
/assign auto                     → activer round-robin

/blacklist add @user [raison]    → blacklister
/blacklist remove @user          → retirer de la blacklist
/blacklist list                  → afficher la liste

/sla set <catégorie> <heures>    → configurer SLA
/sla status                      → statut SLA du ticket actif

/summary                         → résumé IA du ticket en cours

COMMANDES CONTEXTUELLES (clic droit sur message) :
- "Ajouter comme snippet"
- "Marquer comme résolu"
- "Escalader"
```

### 5.2 Modal Forms lors de l'ouverture d'un ticket

```python
# Quand un utilisateur ouvre un ticket avec un formulaire configuré :
# → Discord ouvre une modal (popup) avec les champs du formulaire
# → L'utilisateur remplit et soumet
# → Les réponses constituent le premier message du ticket
# → Tout est traduit automatiquement pour le staff

class TicketModal(discord.ui.Modal):
    def __init__(self, form_fields: list, guild_config: dict):
        super().__init__(title="Ouvrez votre ticket")
        for field in form_fields[:5]:  # Discord max 5 components par modal
            component = discord.ui.TextInput(
                label=field["label"][:45],
                placeholder=field.get("placeholder", ""),
                style=discord.TextStyle.paragraph if field["type"] == "long" 
                      else discord.TextStyle.short,
                required=field.get("required", True),
                max_length=field.get("max_length", 1024),
            )
            self.add_item(component)
```

### 5.3 Thread Support

```python
# Configuration dans dashboard : "Mode d'ouverture : Channel ou Thread"
# En mode Thread :

async def _create_ticket_thread(
    self, 
    interaction: discord.Interaction,
    parent_channel: discord.TextChannel,
    topic: str = ""
) -> discord.Thread:
    thread_name = f"ticket-{interaction.user.name[:20]}"
    thread = await parent_channel.create_thread(
        name=thread_name,
        auto_archive_duration=10080,  # 7 jours
        type=discord.ChannelType.private_thread,
        reason="Ticket support Veridian AI"
    )
    # Ajouter les participants
    await thread.add_user(interaction.user)
    return thread
```

### 5.4 SLA System

```python
# Dans bot/services/sla_monitor.py (nouveau fichier)
# Task qui tourne toutes les 5 minutes

@tasks.loop(minutes=5)
async def sla_monitor_loop(self):
    """Vérifie les tickets en dépassement de SLA."""
    try:
        breaches = await self._get_sla_breaches()
        for ticket in breaches:
            await self._send_sla_alert(ticket)
    except Exception as e:
        logger.error(f"SLA monitor error: {e}")

async def _get_sla_breaches(self) -> list[dict]:
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT t.*, g.default_sla_hours, g.log_channel_id,
                   ts.sla_hours as category_sla
            FROM vai_tickets t
            JOIN vai_guilds g ON t.guild_id = g.id
            LEFT JOIN vai_ticket_sla ts ON t.category_id = ts.category_id
            WHERE t.status IN ('open','in_progress')
              AND t.sla_alerted = 0
              AND TIMESTAMPDIFF(HOUR, t.opened_at, NOW()) >= 
                  COALESCE(ts.sla_hours, g.default_sla_hours, 24)
        """)
        return cursor.fetchall()
```

### 5.5 Round-robin auto-assignment

```python
# Dans bot/services/assignment.py (nouveau fichier)

class RoundRobinAssigner:
    def __init__(self, guild_id: int):
        self.guild_id = guild_id
    
    def get_next_assignee(self, category_id: int = None) -> dict | None:
        """Retourne le membre du staff le moins récemment assigné."""
        with get_db_context() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT sa.user_id, sa.username, 
                       COUNT(t.id) as open_tickets,
                       MAX(t.opened_at) as last_assigned
                FROM vai_staff_agents sa
                LEFT JOIN vai_tickets t ON t.assigned_staff_id = sa.user_id
                    AND t.status NOT IN ('closed')
                WHERE sa.guild_id = %s 
                  AND sa.is_active = 1
                  AND (%s IS NULL OR sa.category_id = %s OR sa.category_id IS NULL)
                GROUP BY sa.user_id, sa.username
                ORDER BY open_tickets ASC, last_assigned ASC
                LIMIT 1
            """, (self.guild_id, category_id, category_id))
            return cursor.fetchone()
```

---

## 6. Implémentation base de données — Nouvelles tables

### 6.1 Tables à créer

```sql
-- ============================================
-- PANELS & FORMS
-- ============================================

CREATE TABLE IF NOT EXISTS vai_panels (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    name            VARCHAR(100),
    embed_title     VARCHAR(256),
    embed_desc      TEXT,
    embed_color     VARCHAR(10) DEFAULT '#2DFF8F',
    embed_footer    VARCHAR(256),
    embed_image_url VARCHAR(500),
    channel_id      BIGINT COMMENT 'Channel où le panel est posté',
    message_id      BIGINT COMMENT 'ID du message panel posté',
    is_active       TINYINT(1) DEFAULT 1,
    created_by      BIGINT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id)
);

CREATE TABLE IF NOT EXISTS vai_panel_buttons (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    panel_id        INT NOT NULL,
    label           VARCHAR(80),
    emoji           VARCHAR(50),
    style           ENUM('primary','secondary','success','danger') DEFAULT 'primary',
    category_id     INT,
    form_id         INT,
    sort_order      INT DEFAULT 0,
    FOREIGN KEY (panel_id) REFERENCES vai_panels(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vai_ticket_forms (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    name            VARCHAR(100),
    is_active       TINYINT(1) DEFAULT 1,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id)
);

CREATE TABLE IF NOT EXISTS vai_form_fields (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    form_id         INT NOT NULL,
    label           VARCHAR(45),
    placeholder     VARCHAR(100),
    type            ENUM('short','long','select') DEFAULT 'short',
    required        TINYINT(1) DEFAULT 1,
    max_length      INT DEFAULT 1024,
    options_json    JSON COMMENT 'Pour le type select',
    sort_order      INT DEFAULT 0,
    FOREIGN KEY (form_id) REFERENCES vai_ticket_forms(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS vai_form_responses (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id       INT NOT NULL,
    form_id         INT NOT NULL,
    responses_json  JSON,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES vai_tickets(id) ON DELETE CASCADE
);

-- ============================================
-- TAGS
-- ============================================

CREATE TABLE IF NOT EXISTS vai_tags (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    name            VARCHAR(50),
    color           VARCHAR(10) DEFAULT '#2DFF8F',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id),
    UNIQUE KEY uk_guild_name (guild_id, name)
);

CREATE TABLE IF NOT EXISTS vai_ticket_tags (
    ticket_id       INT NOT NULL,
    tag_id          INT NOT NULL,
    added_by        BIGINT,
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (ticket_id, tag_id),
    FOREIGN KEY (ticket_id) REFERENCES vai_tickets(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES vai_tags(id) ON DELETE CASCADE
);

-- ============================================
-- SNIPPETS (Canned Responses)
-- ============================================

CREATE TABLE IF NOT EXISTS vai_snippets (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    name            VARCHAR(50),
    content         TEXT,
    auto_translate  TINYINT(1) DEFAULT 1,
    usage_count     INT DEFAULT 0,
    created_by      BIGINT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id),
    UNIQUE KEY uk_guild_name (guild_id, name)
);

-- ============================================
-- STAFF & TEAMS
-- ============================================

CREATE TABLE IF NOT EXISTS vai_staff_agents (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    username        VARCHAR(100),
    language        VARCHAR(10) DEFAULT 'en',
    category_id     INT COMMENT 'NULL = tous les types',
    is_active       TINYINT(1) DEFAULT 1,
    max_tickets     INT DEFAULT 0 COMMENT '0 = illimité',
    joined_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_guild_user (guild_id, user_id),
    KEY idx_guild (guild_id)
);

CREATE TABLE IF NOT EXISTS vai_ticket_categories (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    name            VARCHAR(100),
    description     VARCHAR(200),
    discord_category_id BIGINT,
    staff_role_id   BIGINT,
    form_id         INT,
    default_priority ENUM('low','medium','high','urgent') DEFAULT 'medium',
    sla_hours       INT DEFAULT 24,
    auto_assign     TINYINT(1) DEFAULT 0,
    sort_order      INT DEFAULT 0,
    KEY idx_guild (guild_id)
);

-- ============================================
-- SLA
-- ============================================

CREATE TABLE IF NOT EXISTS vai_sla_rules (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    category_id     INT,
    priority        ENUM('low','medium','high','urgent'),
    response_hours  INT DEFAULT 24 COMMENT 'Délai de première réponse',
    resolution_hours INT DEFAULT 72 COMMENT 'Délai de résolution',
    alert_channel_id BIGINT,
    KEY idx_guild (guild_id)
);

ALTER TABLE vai_tickets ADD COLUMN IF NOT EXISTS category_id INT NULL;
ALTER TABLE vai_tickets ADD COLUMN IF NOT EXISTS sla_breach_at TIMESTAMP NULL;
ALTER TABLE vai_tickets ADD COLUMN IF NOT EXISTS sla_alerted TINYINT(1) DEFAULT 0;
ALTER TABLE vai_tickets ADD COLUMN IF NOT EXISTS satisfaction_score TINYINT NULL COMMENT '1-5';
ALTER TABLE vai_tickets ADD COLUMN IF NOT EXISTS thread_id BIGINT NULL;

-- ============================================
-- BLACKLIST
-- ============================================

CREATE TABLE IF NOT EXISTS vai_user_blacklist (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    username        VARCHAR(100),
    reason          TEXT,
    banned_by       BIGINT,
    expires_at      TIMESTAMP NULL COMMENT 'NULL = permanent',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_guild_user (guild_id, user_id),
    KEY idx_guild (guild_id)
);

-- ============================================
-- NOTES INTERNES
-- ============================================

CREATE TABLE IF NOT EXISTS vai_ticket_notes (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id       INT NOT NULL,
    author_id       BIGINT NOT NULL,
    author_username VARCHAR(100),
    content         TEXT NOT NULL,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (ticket_id) REFERENCES vai_tickets(id) ON DELETE CASCADE,
    KEY idx_ticket (ticket_id)
);

-- ============================================
-- WEBHOOKS SORTANTS
-- ============================================

CREATE TABLE IF NOT EXISTS vai_outbound_webhooks (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    name            VARCHAR(100),
    url             VARCHAR(500),
    secret          VARCHAR(200) COMMENT 'Pour signature HMAC optionnelle',
    events_json     JSON COMMENT '["ticket.created","ticket.closed",...]',
    is_active       TINYINT(1) DEFAULT 1,
    last_triggered  TIMESTAMP NULL,
    failure_count   INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_guild (guild_id)
);

CREATE TABLE IF NOT EXISTS vai_webhook_logs (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    webhook_id      INT NOT NULL,
    event           VARCHAR(50),
    payload_json    JSON,
    response_code   INT,
    response_body   TEXT,
    triggered_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    KEY idx_webhook (webhook_id)
);

-- ============================================
-- STRIPE SUBSCRIPTIONS
-- ============================================

CREATE TABLE IF NOT EXISTS vai_stripe_customers (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_id        BIGINT NOT NULL,
    user_id         BIGINT NOT NULL,
    stripe_customer_id VARCHAR(100) UNIQUE,
    stripe_sub_id   VARCHAR(100),
    stripe_price_id VARCHAR(100),
    current_period_end TIMESTAMP NULL,
    status          VARCHAR(50) DEFAULT 'inactive',
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_guild (guild_id),
    KEY idx_stripe_customer (stripe_customer_id)
);
```

### 6.2 Migrations dans `api/db_migrate.py`

Ajouter `_ensure_v2_features()` qui crée toutes les tables ci-dessus de façon idempotente.

---

## 7. Plan d'implémentation par sprints

### Sprint 1 — Fondations (Semaine 1-2)

**Objectif : base solide, zero bugs, Stripe fonctionnel**

```
BACKEND :
□ Fix webhook OxaPay (hmac.new signature)
□ Fix embed color support hex
□ Fix langue "auto" traduction staff→user
□ Intégration Stripe : stripe_client.py + webhook handler
□ Migration DB v2 : toutes les nouvelles tables
□ Endpoint /guild/{id}/categories (CRUD)
□ Endpoint /guild/{id}/tags (CRUD)
□ Connection pool MySQL (DB_POOL_SIZE)

BOT :
□ Commande /blacklist (add/remove/list)
□ Commande /tag (add/set/remove/list)
□ Commande /note (note interne)
□ Fix PendingNotification backoff exponentiel

DASHBOARD :
□ Refonte sidebar (nouvelle navigation)
□ Page "Abonnement" reliée à Stripe checkout
□ Portail Stripe customer (gérer/annuler)
□ Onboarding wizard 4 étapes
```

### Sprint 2 — Panels & Forms (Semaine 3-4)

**Objectif : le panel builder doit être aussi bon que Ticket Tool**

```
DASHBOARD :
□ Page "Panels" — liste des panels
□ Panel Builder UI (éditeur + preview Discord live)
□ Form Builder UI (drag-and-drop des champs)
□ Deploy panel vers un channel Discord

BOT :
□ TicketOpenButtonView multi-boutons (jusqu'à 5)
□ Modal Forms lors de l'ouverture d'un ticket
□ Stockage des réponses de formulaire (vai_form_responses)
□ Affichage des réponses formatées dans le ticket + traduction

API :
□ CRUD /guild/{id}/panels
□ CRUD /guild/{id}/forms
□ POST /guild/{id}/panels/{id}/deploy
```

### Sprint 3 — Staff Features (Semaine 5-6)

**Objectif : rendre le staff 2x plus efficace**

```
BOT :
□ Commande /snippet (add/list/use)
□ Snippets auto-traduits dans la langue utilisateur
□ Round-robin auto-assignment (RoundRobinAssigner)
□ Per-category staff roles (vai_ticket_categories)
□ Thread support (option dans la config)

DASHBOARD :
□ Page "Staff & Équipes" (gérer agents, catégories, langues)
□ Page "Snippets" (éditeur avec variables {user_name} etc.)
□ Table tickets enrichie (SLA indicator, tags, assigné)
□ Ticket Detail Drawer (panel latéral sans navigation)

API :
□ CRUD /guild/{id}/staff
□ CRUD /guild/{id}/snippets
□ CRUD /guild/{id}/categories
□ POST /ticket/{id}/assign
□ POST /ticket/{id}/tags
```

### Sprint 4 — SLA & Analytics (Semaine 7-8)

**Objectif : fonctionnalités Pro qui justifient 12€/mois**

```
BOT :
□ SLA monitor background task (toutes les 5 min)
□ SLA breach alerts dans log channel
□ SLA indicator dans l'embed de bienvenue du ticket
□ Post-close satisfaction rating DM (1-5 étoiles)

DASHBOARD :
□ Page "Analytics" (Pro+)
   - KPI cards avec delta
   - Volume de tickets (chart)
   - Distribution par catégorie (donut)
   - Heatmap heures de pointe
   - Agent leaderboard
□ Page "Alertes SLA" (Pro+)
□ Configuration SLA dans "Catégories"

API :
□ GET /guild/{id}/analytics?period=30d
□ GET /guild/{id}/analytics/agents
□ GET /guild/{id}/sla/breaches
```

### Sprint 5 — Webhooks & Intégrations (Semaine 9-10)

**Objectif : fonctionnalités Business et écosystème**

```
BOT :
□ Outbound webhooks (déclencher sur événements tickets)
□ Commande /summary (résumé IA en cours de ticket)

DASHBOARD :
□ Page "Intégrations" (webhooks sortants)
   - Ajouter/tester/supprimer des webhooks
   - Historique des envois (vai_webhook_logs)
   - Événements sélectionnables
□ Ctrl+K Command Palette
□ Mobile responsive (bottom nav, drawer)

API :
□ CRUD /guild/{id}/webhooks
□ GET /guild/{id}/webhooks/{id}/logs
□ Stripe usage-based billing (AI token tracking)
```

### Sprint 6 — Polish & Lancement (Semaine 11-12)

**Objectif : tout est poli, zero friction pour les nouveaux utilisateurs**

```
DASHBOARD :
□ Dark/Light mode toggle
□ Animations de transition pages
□ Toasts améliorés (avec actions, stack)
□ Skeletons de chargement
□ Empty states dessinés (pas juste du texte)

LANDING PAGE :
□ Section témoignages
□ Comparaison avec concurrents (tableau)
□ FAQ interactive
□ Pricing page dédiée avec feature comparison
□ SEO meta tags complets

MARKETING :
□ Changelog public (roadmap.veridiancloud.xyz)
□ Discord server avec rôles (free/starter/pro/business)
□ Bot de demo public accessible sans install
```

---

## 8. Corrections critiques à appliquer maintenant

### 8.1 Fix webhook OxaPay (BLOQUANT)

**Fichier :** `api/routes/webhook.py` et `api/main.py`

```python
# Le bug : dans api/main.py ligne ~193
# hmac.new() avec bytes fonctionne, mais le secret doit être bytes
expected = hmac.new(secret.encode('utf-8'), body, hashlib.sha256).hexdigest()
# S'assurer que body est bien bytes bruts (pas re-sérialisé)
```

### 8.2 Fix embed color (#4DA6FF hex non géré)

**Fichier :** `bot/cogs/tickets.py` — `_embed_color()`

```python
def _embed_color(raw: str | None) -> discord.Color:
    n = (raw or "").strip().lower()
    if not n:
        return discord.Color(COLOR_SUCCESS)
    
    # Support hex direct (depuis le colorpicker dashboard)
    hex_raw = n.lstrip('#')
    if len(hex_raw) in (3, 6) and all(c in '0123456789abcdef' for c in hex_raw):
        if len(hex_raw) == 3:
            hex_raw = ''.join(c*2 for c in hex_raw)
        return discord.Color(int(hex_raw, 16))
    
    # Noms de couleur
    return {
        "blue":    discord.Color(0x4DA6FF),
        "green":   discord.Color(COLOR_SUCCESS),
        "red":     discord.Color(COLOR_CRITICAL),
        "yellow":  discord.Color(COLOR_WARNING),
        "purple":  discord.Color(COLOR_NOTICE),
    }.get(n, discord.Color(COLOR_SUCCESS))
```

### 8.3 Fix langue "auto" dans traduction staff→user

**Fichier :** `bot/cogs/tickets.py` — `on_message()` côté staff

```python
# AVANT
user_lang = ticket.get("user_language") if ticket.get("user_language") not in (None, "", "auto") else None

# APRÈS — avec fallback sur l'historique
if not user_lang or user_lang == "auto":
    user_lang = self._dominant_language_from_history(ticket["id"], ticket.get("user_id"))
    if user_lang and user_lang != "auto":
        TicketModel.update(ticket["id"], user_language=user_lang)
        ticket["user_language"] = user_lang
```

### 8.4 Migration DB manquante — colonne `ai_intent`

**Fichier :** `api/db_migrate.py` — dans `_ensure_ticket_migrations()`

```python
# Déjà présente dans le fichier, vérifier qu'elle est bien exécutée
if _column_info(tickets_table, "ai_intent") is None:
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"ALTER TABLE {tickets_table} "
            f"ADD COLUMN ai_intent TEXT NULL "
            f"COMMENT 'Analyse IA du premier message'"
        )
```

### 8.5 Ajouter Stripe dans requirements.txt

```
stripe>=7.0.0
```

### 8.6 Variables .env à ajouter

```env
# Stripe
STRIPE_SECRET_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_STARTER_MONTHLY=price_...
STRIPE_PRICE_STARTER_YEARLY=price_...
STRIPE_PRICE_PRO_MONTHLY=price_...
STRIPE_PRICE_PRO_YEARLY=price_...
STRIPE_PRICE_BUSINESS_MONTHLY=price_...
STRIPE_PRICE_BUSINESS_YEARLY=price_...

# Feature flags
ENABLE_STRIPE=true
ENABLE_THREADS=false
ENABLE_SLA=true
ENABLE_FORMS=true
```

---

## Annexe — Estimation de revenus projetés

```
SCÉNARIO CONSERVATEUR (12 mois) :
  Mois 3  : 50 Free, 8 Starter, 2 Pro         = 56€ MRR
  Mois 6  : 200 Free, 30 Starter, 8 Pro, 1 Biz = 241€ MRR
  Mois 12 : 500 Free, 80 Starter, 25 Pro, 8 Biz = 980€ MRR
             + add-ons ~150€ MRR
  Total mois 12 : ~1 130€ MRR

SCÉNARIO OPTIMISTE (si viralité discord.py community) :
  Mois 12 : 2 000 Free, 300 Starter, 80 Pro, 25 Biz = 3 500€ MRR

COÛTS ESTIMÉS :
  Hosting VPS (2 cores, 4GB) : 20€/m
  MySQL managed : 15€/m
  Groq API (free tier large)  : ~10-50€/m selon usage
  Stripe fees (~2.9%)         : ~30€/m à 1 000€ MRR
  Total opex : ~75-115€/m

Seuil de rentabilité : ~200€ MRR (atteint mois 8 scénario conservateur)
```

---

*Document généré le 30 mars 2026 · Veridian AI v2.0 Roadmap*
*Priorité : Sprint 1 immédiatement → lancement public Sprint 6*