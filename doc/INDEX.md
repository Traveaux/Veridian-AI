# 📑 Veridian AI - Complete Project Index

**Project Status:** ✅ Complete & Production Ready  
**Version:** 2.0.0  
**Total Files:** 38  
**Project Size:** 7.0 MB  
**Last Updated:** February 2025

---

## 📖 Start Here

### First Time? Read These (In Order)
1. **[README.md](README.md)** - Overview, installation, features (7.7 KB)
2. **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** - Commands, endpoints, quick start (8.5 KB)
3. **[DEPLOYMENT.md](DEPLOYMENT.md)** - How to deploy locally, Docker, VPS, AWS (8.9 KB)

### Deep Dive
4. **[STRUCTURE.md](STRUCTURE.md)** - Complete architecture breakdown (17 KB)
5. **[PROJECT_SUMMARY.txt](PROJECT_SUMMARY.txt)** - Full project status report (14 KB)
6. **[REVAMP_EXECUTION_PLAN_2026-03-31.md](REVAMP_EXECUTION_PLAN_2026-03-31.md)** - Pricing revamp, Stripe priority, DB expansion, 6-sprint plan
7. **[INDEX.md](INDEX.md)** - This file!

---

## 🤖 Bot Core Files

### Main Entry Point
- **[bot/main.py](bot/main.py)** - Bot initialization, cog loading, Discord event handlers
  - Loads all cogs from `bot/cogs/`
  - Syncs slash commands
  - Handles Discord lifecycle events

### Configuration
- **[bot/config.py](bot/config.py)** - Global constants (2400+ lines)
  - Pricing tiers and plan limits (Free, Premium, Pro)
  - Language codes and limits per plan
  - Groq model definitions and system prompts
  - Plan feature matrix

### Database Layer
- **[bot/db/connection.py](bot/db/connection.py)** - MySQL connection manager
  - Context manager pattern for safe connections
  - Automatic resource cleanup
  - Connection pooling ready

- **[bot/db/models.py](bot/db/models.py)** - CRUD operations (400+ lines)
  - `GuildModel` - Server configuration
  - `UserModel` - User preferences
  - `TicketModel` - Support tickets
  - `OrderModel` - Payment orders (VAI-YYYYMM-XXXX format)
  - `SubscriptionModel` - Active subscriptions
  - `TranslationCacheModel` - SHA256 cached translations
  - `DashboardSessionModel` - OAuth2 sessions
  - + 3 more models for payments, knowledge base, messages

### Discord Commands (Cogs)
- **[bot/cogs/tickets.py](bot/cogs/tickets.py)** - Support ticket system
  - `/ticket` - Create ticket with auto-translate
  - `/close` - Close ticket with AI summary
  - Real-time message translation
  - Channel auto-creation: `ticket-{username}-{id}`
  - Ephemeral translation notifications

- **[bot/cogs/support.py](bot/cogs/support.py)** - Public AI support
  - Auto-respond in designated channels
  - `/language` - Set preferred language
  - `/premium` - Show plan information
  - `/status` - Check subscription
  - Language-aware responses

- **[bot/cogs/payments.py](bot/cogs/payments.py)** - Payment processing
  - `/pay paypal [plan]` - PayPal method (semi-manual)
  - `/pay crypto [plan]` - OxaPay crypto (automatic)
  - `/pay giftcard [plan]` - Gift card method (semi-manual)
  - Order ID generation and validation

- **[bot/cogs/admin.py](bot/cogs/admin.py)** - Admin commands
  - `/validate [order_id] [plan]` - Approve order
  - `/revoke @user` - Revoke subscription
  - `/orders pending` - List pending orders
  - `/setup` - Configure bot channels/roles

### Services (Business Logic)
- **[bot/services/groq_client.py](bot/services/groq_client.py)** - Groq LLM integration
  - `get_support_response()` - Answer questions (Llama 3.1 8B)
  - `translate_text()` - Real-time translation
  - `generate_ticket_summary()` - AI transcripts (Llama 3.1 70B)
  - `is_question()` - Detect if message needs response

- **[bot/services/translator.py](bot/services/translator.py)** - Language processing
  - `detect_language()` - Auto-detect using langdetect
  - `generate_content_hash()` - SHA256 hash of (text + lang1 + lang2)
  - `translate()` - Translate with cache lookup
  - Hit count tracking for cache optimization

- **[bot/services/oxapay.py](bot/services/oxapay.py)** - Crypto payments
  - `create_invoice()` - Generate payment link (BTC, ETH, USDT)
  - `verify_webhook()` - HMAC-SHA256 signature verification
  - Automatic subscription activation on payment

- **[bot/services/notifications.py](bot/services/notifications.py)** - Discord notifications
  - `send_dm_embed()` - Format and send private messages
  - `notify_bot_owner()` - Alert admin with action buttons
  - `create_payment_embed()` - Format payment info
  - Interactive buttons for order validation

---

## 🔌 API Backend Files

### Main API Application
- **[api/main.py](api/main.py)** - FastAPI app configuration
  - CORS middleware setup
  - Security headers
  - Request logging
  - Route mounting
  - Health check endpoints

### API Route Modules

#### Webhooks
- **[api/routes/webhook.py](api/routes/webhook.py)** - OxaPay payment callbacks
  - `POST /webhook/oxapay` - Receive crypto payments
  - HMAC-SHA256 signature verification
  - Auto-create subscription on payment
  - Notify Bot Owner of activation

#### Internal APIs
- **[api/routes/internal.py](api/routes/internal.py)** - Bot ↔ Dashboard communication
  - `GET/PUT /internal/guild/{id}/config` - Server config
  - `GET /internal/guild/{id}/tickets` - List tickets with pagination
  - `GET /internal/guild/{id}/stats` - Dashboard stats
  - `GET/PUT /internal/user/{id}/*` - User management
  - `GET /internal/health` - Health check
  - All require `X-API-Secret` header

#### Authentication
- **[api/routes/auth.py](api/routes/auth.py)** - OAuth2 Discord
  - `GET /auth/discord/login` - Redirect to Discord
  - `GET /auth/discord/callback` - Handle OAuth callback
  - `POST /auth/logout` - Invalidate session
  - `GET /auth/user/me` - Get current user
  - JWT token generation (7-day expiry)

---

## 🌐 Web Dashboard Files

### HTML Templates
- **[web/templates/base.html](web/templates/base.html)** - Base layout
  - Navigation bar with logout
  - Content block for page-specific content
  - Consistent styling wrapper

- **[web/templates/dashboard.html](web/templates/dashboard.html)** - Main dashboard
  - Stats cards (servers, subscriptions, tickets, orders)
  - Server list view
  - Pending orders table
  - Real-time data loading

- **[web/templates/settings.html](web/templates/settings.html)** - Server settings
  - Server selector dropdown
  - Config form (support channel, staff role, etc.)
  - Language preference selector
  - Save/cancel actions

### Static Assets
- **[web/static/css/style.css](web/static/css/style.css)** - Styling (4.7 KB)
  - Dark theme with Tailwind CSS
  - Button styles, cards, forms
  - Badges, alerts, responsive design
  - Animations and transitions

- **[web/static/js/main.js](web/static/js/main.js)** - JavaScript utilities (4.2 KB)
  - Auth token validation
  - API helper functions
  - Toast notifications
  - Date/currency formatting
  - Theme toggle (light/dark)
  - Debounce helpers

---

## 📊 Database Files

- **[database/schema.sql](database/schema.sql)** - Complete MySQL schema (9.8 KB)
  - `vai_guilds` - Server configuration
  - `vai_users` - User preferences
  - `vai_tickets` - Support tickets
  - `vai_ticket_messages` - Message translation pairs
  - `vai_translations_cache` - Translation cache (SHA256 keys)
  - `vai_orders` - Payment orders
  - `vai_payments` - Payment history
  - `vai_subscriptions` - Active subscriptions
  - `vai_knowledge_base` - Premium FAQ
  - `vai_dashboard_sessions` - OAuth2 sessions
  - Indexes on frequently queried columns
  - 2 views for optimized queries

---

## 🐳 Containerization Files

- **[docker-compose.yml](docker-compose.yml)** - Multi-container orchestration
  - MySQL service (port 3306)
  - Bot service (no external port)
  - API service (port 8000)
  - Nginx reverse proxy (ports 80/443) [optional]
  - Health checks & auto-restart
  - Volume persistence for MySQL data

- **[Dockerfile](Dockerfile)** - Bot container image
  - Python 3.11-slim base
  - Install system dependencies
  - Copy and install Python packages
  - Create logs directory
  - Run `python bot/main.py`

- **[Dockerfile.api](Dockerfile.api)** - API container image
  - Python 3.11-slim base
  - Install dependencies
  - Copy API code
  - Expose port 8000
  - Run FastAPI with uvicorn

---

## ⚙️ Configuration Files

- **[requirements.txt](requirements.txt)** - Python dependencies (207 bytes)
  - `discord.py==2.4.0` - Discord bot framework
  - `mysql-connector-python==8.2.0` - MySQL driver
  - `groq==0.7.0` - Groq API client
  - `fastapi==0.110.0` - Web framework
  - `uvicorn==0.27.0` - ASGI server
  - + 5 more essential packages

- **[.env.example](.env.example)** - Environment variables template
  - Discord credentials (token, client ID, secret)
  - Groq API key
  - MySQL connection details
  - OxaPay merchant credentials
  - JWT & API secrets
  - PayPal email, Bot owner ID

- **[.gitignore](.gitignore)** - Git ignore patterns
  - `.env` files (secrets)
  - `__pycache__/` directories
  - Virtual environments
  - IDE files (.vscode, .idea)
  - Logs and database dumps
  - Node modules and build artifacts

---

## 📚 Documentation Files

### Quick Starts
- **[README.md](README.md)** (7.7 KB)
  - Installation steps
  - Configuration guide
  - Architecture overview
  - Feature list
  - Command reference
  - Plans & pricing
  - Project structure diagram
  - Roadmap

- **[QUICK_REFERENCE.md](QUICK_REFERENCE.md)** (8.5 KB)
  - 30-second start guides
  - File map for navigation
  - Discord commands list
  - API endpoints reference
  - Database table schema
  - Environment variables
  - Key functions with code examples
  - Troubleshooting section
  - Monitoring commands
  - Deployment checklist

### Detailed Guides
- **[STRUCTURE.md](STRUCTURE.md)** (17 KB)
  - Complete directory tree with annotations
  - Database layer detailed breakdown
  - Services layer architecture
  - Discord commands implementation details
  - API backend documentation
  - Web dashboard structure
  - Configuration file explanations
  - Core components details
  - Security architecture
  - Scalability features
  - Data flow diagrams
  - Current implementation status
  - Future enhancements

- **[DEPLOYMENT.md](DEPLOYMENT.md)** (8.9 KB)
  - Local development setup
  - Docker deployment guide
  - VPS deployment (Ubuntu 22.04)
  - AWS deployment (ECS + RDS)
  - Database backup/restore procedures
  - Monitoring setup (CloudWatch, Datadog)
  - Performance optimization tips
  - Troubleshooting guide
  - Maintenance checklist
  - Update procedures
  - Rolling deployment strategy

### Project Status
- **[PROJECT_SUMMARY.txt](PROJECT_SUMMARY.txt)** (14 KB)
  - Project completion status
  - Deliverables summary
  - File breakdown by component
  - Core features implemented
  - Dependencies list
  - Security features checklist
  - Scalability architecture details
  - Deployment options overview
  - Architectural decisions explained
  - Next steps/future enhancements
  - Quick start commands
  - Verification checklist

---

## 🎯 File Usage by Role

### 👨‍💻 Developer
Start with:
1. `README.md` - Understand the project
2. `bot/config.py` - See all constants
3. `bot/cogs/*.py` - Implement features
4. `bot/db/models.py` - Query database
5. `STRUCTURE.md` - Understand architecture

### 🚀 DevOps/Deployment
Start with:
1. `DEPLOYMENT.md` - Choose deployment method
2. `docker-compose.yml` - Understand containerization
3. `.env.example` - Configure environment
4. `database/schema.sql` - Set up database
5. `QUICK_REFERENCE.md` - Monitor and troubleshoot

### 📊 Product Manager
Start with:
1. `README.md` - Feature overview
2. `QUICK_REFERENCE.md` - Command reference
3. `bot/config.py` - Plan limits and pricing
4. `PROJECT_SUMMARY.txt` - Project status
5. `STRUCTURE.md` - Architecture deep dive

### 🔍 Code Reviewer
Start with:
1. `STRUCTURE.md` - Architecture decisions
2. `bot/db/models.py` - Database patterns
3. `bot/services/*.py` - Reusable logic
4. `api/routes/*.py` - API design
5. `bot/cogs/*.py` - Command implementation

---

## 🔄 File Dependencies

```
bot/main.py
  ├── bot/cogs/* (all cogs auto-loaded)
  ├── bot/config.py (constants)
  ├── bot/db/models.py (database)
  └── bot/services/* (business logic)

api/main.py
  ├── api/routes/webhook.py
  ├── api/routes/internal.py
  ├── api/routes/auth.py
  └── bot/db/models.py (shared database)

bot/cogs/payments.py
  ├── bot/services/oxapay.py
  ├── bot/services/notifications.py
  └── bot/db/models.py

bot/cogs/tickets.py
  ├── bot/services/translator.py
  ├── bot/services/groq_client.py
  ├── bot/services/notifications.py
  └── bot/db/models.py

api/routes/webhook.py
  ├── bot/db/models.py
  └── bot/services/notifications.py

docker-compose.yml
  ├── Dockerfile (builds bot)
  ├── Dockerfile.api (builds api)
  └── database/schema.sql (initializes db)
```

---

## 📋 Feature Checklist

### ✅ Implemented
- [x] Discord bot with slash commands
- [x] Real-time message translation (SHA256 cache)
- [x] Ticket system with auto-channel creation
- [x] AI-powered responses (Groq Llama 3.1)
- [x] Three payment methods (PayPal, crypto, gift cards)
- [x] Order tracking (VAI-YYYYMM-XXXX format)
- [x] Subscription management
- [x] Web dashboard with OAuth2
- [x] FastAPI backend
- [x] MySQL database with 10 tables
- [x] Docker containerization
- [x] Admin commands
- [x] Multi-language support
- [x] Webhook HMAC verification
- [x] JWT session management

### 🚀 Ready for Next Phase
- [ ] Testing suite (pytest)
- [ ] Additional payment providers (Stripe)
- [ ] Advanced analytics
- [ ] Kubernetes deployment
- [ ] Message queue integration
- [ ] Advanced caching (Redis)

---

## 💡 Key Concepts

### Database Design
- **Prefixed tables:** All tables start with `vai_` to avoid conflicts
- **SHA256 caching:** Translation cache keyed by hash of (text + src_lang + tgt_lang)
- **Hit counting:** Tracks cache effectiveness for future optimization
- **Indexes:** Strategic indexes on guild_id, user_id, created_at for performance
- **Views:** Pre-computed views for complex queries (active subscriptions, pending orders)

### API Security
- **HMAC-SHA256:** Webhook payload verification
- **JWT:** Session tokens (7-day expiry)
- **Parameterized queries:** SQL injection prevention
- **Environment variables:** No hardcoded secrets
- **CORS:** Cross-origin request control

### Scalability Patterns
- **Connection pooling:** MySQL context managers for efficiency
- **Modular design:** Cogs, services, routes are independent
- **Stateless API:** FastAPI suitable for horizontal scaling
- **Async/await:** Non-blocking database operations
- **Caching:** SHA256 translation cache reduces API calls

---

## 🎓 Learning Path

1. **Understand the Project** (30 min)
   - Read `README.md`
   - Scan `QUICK_REFERENCE.md`

2. **Explore the Code** (1 hour)
   - Open `bot/main.py`
   - Read one cog (e.g., `bot/cogs/tickets.py`)
   - Check `bot/db/models.py` for database usage

3. **Understand the Flow** (1 hour)
   - Read `STRUCTURE.md` - architecture section
   - Follow data flow: Command → Cog → Service → Database

4. **Setup & Deploy** (1 hour)
   - Follow `DEPLOYMENT.md` for local setup
   - Run `python bot/main.py`
   - Test with `/ticket` command

5. **Deep Dive** (as needed)
   - Study specific service (`groq_client.py`, `translator.py`)
   - Review API routes (`api/routes/*.py`)
   - Check database schema (`database/schema.sql`)

---

## 🔗 Quick Links by Task

| Task | Files |
|------|-------|
| Add new command | `bot/cogs/`, `bot/main.py` |
| Add API endpoint | `api/routes/*.py`, `api/main.py` |
| Query database | `bot/db/models.py` |
| Change constants | `bot/config.py` |
| Deploy locally | `DEPLOYMENT.md` |
| Deploy to Docker | `docker-compose.yml`, `.env.example` |
| Understand architecture | `STRUCTURE.md` |
| Fix issues | `QUICK_REFERENCE.md` troubleshooting section |
| Check status | `PROJECT_SUMMARY.txt` |
| Configure environment | `.env.example` |

---

## 📞 File-Specific Documentation

Each major Python file includes:
- Module docstring explaining purpose
- Function/class docstrings with parameters
- Error handling with logging
- SQL queries with comments
- Configuration constants referenced

Find specific info:
- **Pricing/limits:** `bot/config.py` lines 19-36
- **Groq prompts:** `bot/config.py` lines 48-60
- **Database schema:** `database/schema.sql`
- **API endpoints:** `api/routes/*.py`
- **Commands:** `bot/cogs/*.py`

---

## ✅ Verification Checklist

Before using the project:
- [ ] All 38 files present in directories
- [ ] `.env` configured (copy from `.env.example`)
- [ ] Database schema imported (`schema.sql`)
- [ ] Dependencies installed (`requirements.txt`)
- [ ] Discord token valid
- [ ] Groq API key valid
- [ ] MySQL running and accessible
- [ ] Documentation files readable

---

**Navigation Tips:**
- Use Ctrl+F to search for terms
- File sizes listed in documentation sections
- Search for function names with `grep`
- Follow dependency tree above for imports

---

**Version:** 2.0.0  
**Last Updated:** February 2025  
**Status:** ✅ Production Ready

For more details, see individual documentation files.
