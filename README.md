# 🤖 Veridian AI - Bot Discord Multi-fonction avec IA

**Version:** 2.0 | **Status:** Phase 1 (MVP Bot)

Bot Discord polyvalent basé sur l'intelligence artificielle. Support multilingue intelligent, système de tickets avancé avec traduction en temps réel, et dashboard web d'administration.

**Site:** https://veridiancloud.xyz

---

## 📋 Table des Matières

1. [Installation](#installation)
2. [Configuration](#configuration)
3. [Architecture](#architecture)
4. [Fonctionnalités](#fonctionnalités)
5. [Commandes](#commandes)
6. [Structure du Projet](#structure-du-projet)
7. [Développement](#développement)

---

## 🚀 Installation

### Prérequis
- Python 3.11+
- MySQL 8.0+
- Discord Bot Token
- Clés API (Groq, OxaPay)

### Étapes

1. **Cloner le projet**
   ```bash
   git clone https://github.com/Traveaux/Veridian-AI.git
   cd Veridian-AI
   ```

2. **Créer l'environnement virtuel**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # Linux/Mac
   # ou
   venv\Scripts\activate  # Windows
   ```

3. **Installer les dépendances**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurer la base de données**
   ```bash
   mysql -u root -p < database/schema.sql
   ```

5. **Configurer les variables d'environnement**
   ```bash
   cp .env.example .env
   # Éditer .env avec vos clés API et config BD
   ```

6. **Lancer le bot**
   ```bash
   python bot/main.py
   ```

---

## ⚙️ Configuration

### Variables d'Environnement (.env)

```env
# Discord
DISCORD_TOKEN=your_bot_token
DISCORD_CLIENT_ID=your_client_id
DISCORD_CLIENT_SECRET=your_client_secret

# APIs
GROQ_API_KEY=your_groq_key
OXAPAY_MERCHANT_KEY=your_merchant_key
OXAPAY_WEBHOOK_SECRET=your_webhook_secret

# Database
DB_HOST=your_db_host
DB_PORT=3306
DB_USER=your_db_user
DB_PASSWORD=your_db_password
DB_NAME=veridianai

# Dashboard
JWT_SECRET=your_jwt_secret
INTERNAL_API_SECRET=your_api_secret
DASHBOARD_URL=https://veridiancloud.xyz/dashboard

# Payment
PAYPAL_EMAIL=your_paypal@email.com
BOT_OWNER_DISCORD_ID=1047760053509312642
```

---

## 🏗️ Architecture

### Stack Technique

| Composant | Technologie | Version |
|-----------|-------------|---------|
| **Bot Discord** | discord.py | 2.4.0 |
| **IA/LLM** | Groq API | Llama 3.1 |
| **Base de données** | MySQL | 8.0+ |
| **Dashboard** | FastAPI + Jinja2 | 0.110 |
| **Détection langue** | langdetect | 1.0.9 |
| **Logs** | loguru | 0.7.2 |

### Flux d'Architecture

```
User (Discord)
    ↓
Bot Cogs (Tickets, Support, Payments, Admin)
    ↓
Services (Groq, Translator, OxaPay, Notifications)
    ↓
Database (MySQL)
    ↓
Dashboard (FastAPI)
    ↓
Admin (web.veridiancloud.xyz)
```

---

## 🎯 Fonctionnalités

### ✅ Phase 1 (MVP) - EN COURS

#### 1. **Support Public IA**
- Écoute les questions dans les channels désignés
- Répond automatiquement via Groq (Llama 3.1)
- Détection automatique de la langue
- Limite par plan (Free: 5 langues, Premium: 20, Pro: toutes)

#### 2. **Système de Tickets avec Traduction**
- Création automatique de channels privés (`ticket-{username}-{id}`)
- Traduction bidirectionnelle en temps réel
- Cache des traductions (SHA256)
- Résumé IA automatique à la clôture
- Archivage après 24h

#### 3. **Paiements (3 méthodes)**

**OxaPay (Crypto - 100% automatique)**
- Paiement BTC, ETH, USDT
- Webhook d'activation instantanée
- Link de paiement généré

**PayPal (Semi-manuel)**
- Numéro de commande unique (VAI-YYYYMM-XXXX)
- DM au Bot Owner avec infos
- 4 boutons: Payé / Non payé / Incomplet / Détails

**Carte Cadeau (Semi-manuel)**
- Demande du code + image
- Stockage sécurisé en DM admin
- Validation manuelle

#### 4. **Commandes Slash**

**Utilisateurs**
- `/ticket` - Ouvrir un ticket
- `/close [raison]` - Fermer le ticket
- `/language [code]` - Définir langue préférée
- `/pay [méthode] [plan]` - Payer
- `/premium` - Voir les plans
- `/status` - Voir abonnement

**Staff**
- `/assign @user` - Assigner un ticket
- `/priority [low|medium|high]` - Changer priorité
- `/translate [langue]` - Forcer langue

**Admin (Bot Owner)**
- `/validate [order_id] [plan]` - Valider une commande
- `/revoke @user` - Révoquer abonnement
- `/orders pending` - Voir commandes en attente
- `/setup` - Configurer le bot

---

## 📊 Plans & Tarification

| Fonctionnalité | Free | Premium (2€) | Pro (5€) |
|---|---|---|---|
| Tickets/mois | 50 | 500 | ∞ |
| Langues | 5 | 20 | ∞ |
| Base connaissance | ✗ | 50 entrées | ∞ |
| Transcriptions | ✗ | ✓ Complète | ✓ + Export |
| Support public IA | ✓ Limité | ✓ | ✓ Étendu |
| Suggestions staff | ✗ | ✗ | ✓ |

---

## 📁 Structure du Projet

```
Veridian-AI/
├── bot/
│   ├── main.py                 # Point d'entrée bot
│   ├── config.py               # Constantes globales
│   ├── db/
│   │   ├── connection.py        # Pattern connexion MySQL
│   │   └── models.py            # CRUD pour toutes tables
│   ├── cogs/
│   │   ├── tickets.py           # Système tickets + traduction
│   │   ├── support.py           # Support public IA
│   │   ├── payments.py          # Paiements (tous types)
│   │   └── admin.py             # Commandes admin
│   └── services/
│       ├── groq_client.py       # Client IA (Groq)
│       ├── translator.py        # Traduction + cache
│       ├── oxapay.py            # Client crypto
│       └── notifications.py     # DM admin + embeds
│
├── api/
│   ├── main.py                 # FastAPI interne
│   └── routes/
│       ├── webhook.py           # Webhook OxaPay
│       ├── internal.py          # API bot ↔ dashboard
│       └── auth.py              # OAuth2 Discord
│
├── web/
│   ├── index.html              # Landing page
│   ├── dashboard.html          # Dashboard d'administration
│   ├── css/                    # Styles CSS
│   ├── js/                     # Scripts JS + i18n
│   ├── locales/                # Traductions frontend
│   └── assets/                 # Logos et ressources statiques
│
├── database/
│   └── schema.sql              # Schéma MySQL complet
│
├── .env                        # Variables d'environnement
├── requirements.txt            # Dépendances Python
└── README.md                   # Ce fichier
```

---

## 🔧 Développement

### Lancer le bot en local

```bash
# Avec rechargement automatique (debug)
python bot/main.py

# Logs structurés dans logs/bot.log
tail -f logs/bot.log
```

### Lancer l'API interne

```bash
cd api
uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

### Vérifications rapides

```bash
python -m compileall bot api
```

### Syntaxe de Commit

```bash
git commit -m "feat: ajouter support crypto OxaPay"
# ou
git commit -m "fix: corriger cache traductions"
git commit -m "docs: mettre à jour README"
```

---

## 📝 Notes Importantes

### Sécurité
- **Jamais** commiter le `.env` en Git
- Les codes de carte cadeau sont envoyés **UNIQUEMENT en DM privé**
- Signature HMAC vérifie tous les webhooks OxaPay
- JWT tokens sont httpOnly et sécurisés

### Performance
- Cache des traductions avec SHA256
- Indexes MySQL sur colonnes fréquemment requêtées
- Connection pooling pour DB
- Vues MySQL pour requêtes complexes

### Scalabilité
- Cogs Discord pour modularité
- Services découplés (Groq, OxaPay, etc.)
- API interne REST pour communication bot ↔ dashboard
- Tables préfixées `vai_` pour éviter conflits

---

## 🚦 Roadmap

- **Phase 1** (MVP Bot) ✅ EN COURS
- **Phase 2** (Paiements complets) - Prochaine
- **Phase 3** (Dashboard OAuth2) - Après
- **Phase 4** (Qualité & Scale) - Optionnel

---

## 📞 Support

- **Discord:** [Veridian AI Server](https://discord.gg/veridian)
- **Email:** support@veridiancloud.xyz
- **Docs:** https://docs.veridiancloud.xyz

---

## 📜 Licence

MIT - 2025 Veridian AI

---

**Dernière mise à jour:** 21 mars 2026
