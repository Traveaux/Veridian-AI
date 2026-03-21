-- ============================================================================
-- Schema MySQL complet pour Veridian AI v0.2
-- Toutes les tables sont prefixees 'vai_'
-- Mise a jour : nouvelles colonnes dashboard, KB CRUD, audit log, guild features
-- ============================================================================

-- ============================================================================
-- VAI_GUILDS - Serveurs Discord enregistres + configuration complete
-- Nouvelles colonnes : welcome_channel_id, features_json, updated_at
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_guilds (
    id                  BIGINT PRIMARY KEY          COMMENT 'Discord Guild ID',
    name                VARCHAR(100)    NOT NULL,
    tier                ENUM('free','premium','pro') DEFAULT 'free',
    support_channel_id  BIGINT                      COMMENT 'Channel support public IA',
    ticket_category_id  BIGINT                      COMMENT 'Categorie tickets',
    staff_role_id       BIGINT,
    log_channel_id      BIGINT,
    welcome_channel_id  BIGINT                      COMMENT 'Channel message bienvenue (optionnel)',
    default_language    VARCHAR(10)     DEFAULT 'en',
    auto_translate      TINYINT(1)      DEFAULT 1   COMMENT 'Traduction auto tickets',
    public_support      TINYINT(1)      DEFAULT 1   COMMENT 'IA channel support public',
    auto_transcript     TINYINT(1)      DEFAULT 1   COMMENT 'Resume IA fermeture ticket',
    ai_moderation       TINYINT(1)      DEFAULT 0   COMMENT 'Moderation IA (pro uniquement)',
    staff_suggestions        TINYINT(1)      DEFAULT 0   COMMENT 'Suggestions staff IA (pro)',
    -- Ticket system v0.4
    ticket_open_channel_id   BIGINT                      COMMENT 'Channel ou envoyer le message bouton/selecteur',
    ticket_open_message      TEXT                        COMMENT 'Message affiche avec le bouton/selecteur ouverture ticket',
    ticket_button_label      VARCHAR(100)  DEFAULT 'Ouvrir un ticket' COMMENT 'Label du bouton ouverture',
    ticket_button_style      VARCHAR(20)   DEFAULT 'primary' COMMENT 'Style bouton: primary/secondary/danger/success',
    ticket_button_emoji      VARCHAR(50)                 COMMENT 'Emoji du bouton (optionnel)',
    ticket_welcome_message   TEXT                        COMMENT 'Message de bienvenue personnalise dans le ticket',
    ticket_welcome_color     VARCHAR(10)   DEFAULT 'blue' COMMENT 'Couleur embed bienvenue: blue/green/red/yellow/purple',
    ticket_selector_enabled  TINYINT(1)    DEFAULT 0   COMMENT '1 = selecteur au lieu du bouton',
    ticket_selector_placeholder VARCHAR(200) DEFAULT 'Selectionnez le type de ticket',
    ticket_selector_options  JSON                        COMMENT 'Options selecteur [{label,value,description,emoji}]',
    ticket_mention_staff     TINYINT(1)    DEFAULT 1   COMMENT 'Mentionner le role staff a louverture',
    ticket_close_on_leave    TINYINT(1)    DEFAULT 0   COMMENT 'Fermer ticket si utilisateur quitte le serveur',
    ticket_max_open          INT           DEFAULT 1   COMMENT 'Nombre max de tickets ouverts par utilisateur',
    staff_languages_json     JSON                        COMMENT 'Langues staff [{user_id,username,language}]',
    -- AI Support custom v0.4
    ai_custom_prompt         TEXT                        COMMENT 'Prompt personnalise pour lIA de support',
    ai_prompt_enabled        TINYINT(1)    DEFAULT 0   COMMENT '1 = utiliser le prompt personnalise',
    -- Deployment persistence
    ticket_open_message_id    BIGINT                      COMMENT 'Message ID du message ouverture tickets (pour edit)',
    ticket_open_needs_deploy  TINYINT(1)    DEFAULT 0   COMMENT '1 = bot doit (re)deployer le message ouverture',
    ticket_open_last_deploy_error TEXT                   COMMENT 'Derniere erreur de deploiement (debug)',
    ticket_open_delete_requested  TINYINT(1)    DEFAULT 0 COMMENT '1 = bot doit supprimer le message ouverture',
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_tier    (tier),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_USERS - Utilisateurs Discord
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_users (
    id                  BIGINT PRIMARY KEY          COMMENT 'Discord User ID',
    username            VARCHAR(100),
    preferred_language  VARCHAR(10)     DEFAULT 'auto',
    is_bot_admin        TINYINT(1)      DEFAULT 0,
    last_seen_at        TIMESTAMP       NULL,
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    KEY idx_username (username)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_TICKETS - Tickets de support
-- Nouvelle colonne : assigned_staff_id, user_username pour affichage dashboard
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_tickets (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    guild_id            BIGINT          NOT NULL,
    user_id             BIGINT          NOT NULL,
    user_username       VARCHAR(100)                COMMENT 'Snapshot username au moment de louverture',
    channel_id          BIGINT          UNIQUE       COMMENT 'Channel Discord du ticket',
    initial_message_id  BIGINT                      COMMENT 'Message embed initial du ticket (pour mise a jour langue)',
    status              ENUM('open','in_progress','closed') DEFAULT 'open',
    user_language       VARCHAR(10),
    staff_language      VARCHAR(10)     DEFAULT 'en',
    assigned_staff_id   BIGINT,
    assigned_staff_name VARCHAR(100),
    priority            ENUM('low','medium','high') DEFAULT 'medium',
    close_reason        TEXT,
    transcript          LONGTEXT                    COMMENT 'Resume IA genere a la cloture',
    opened_at           TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    closed_at           TIMESTAMP       NULL,
    KEY idx_guild_status (guild_id, status),
    KEY idx_user        (user_id),
    KEY idx_opened      (opened_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_TICKET_MESSAGES - Messages des tickets avec traductions
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_ticket_messages (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    ticket_id           INT             NOT NULL,
    author_id           BIGINT,
    author_username     VARCHAR(100),
    discord_message_id  BIGINT                      COMMENT 'Discord Message ID',
    original_content    LONGTEXT,
    translated_content  LONGTEXT,
    original_language   VARCHAR(10),
    target_language     VARCHAR(10),
    from_cache          TINYINT(1)      DEFAULT 0,
    attachments_json    JSON                        COMMENT 'Liste d attachments (urls, filenames, etc.)',
    sent_at             TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    KEY idx_ticket  (ticket_id),
    FOREIGN KEY (ticket_id) REFERENCES vai_tickets(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_TRANSLATIONS_CACHE - Cache des traductions avec SHA256
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_translations_cache (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    content_hash        VARCHAR(64)     UNIQUE       COMMENT 'SHA256 de (text+src_lang+tgt_lang)',
    original_text       LONGTEXT,
    translated_text     LONGTEXT,
    source_language     VARCHAR(10),
    target_language     VARCHAR(10),
    hit_count           INT             DEFAULT 1,
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    KEY idx_hash      (content_hash),
    KEY idx_languages (source_language, target_language),
    KEY idx_hit_count (hit_count)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_ORDERS - Commandes en attente (PayPal & Cartes Cadeaux)
-- Nouvelle colonne : validated_by pour tracer qui a valide
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_orders (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    order_id            VARCHAR(20)     UNIQUE       COMMENT 'Ex: VAI-202502-4823',
    user_id             BIGINT          NOT NULL,
    user_username       VARCHAR(100),
    guild_id            BIGINT,
    guild_name          VARCHAR(100),
    method              ENUM('paypal','giftcard','oxapay'),
    plan                ENUM('premium','pro'),
    amount              DECIMAL(10,2),
    status              ENUM('pending','paid','partial','rejected') DEFAULT 'pending',
    paypal_email        VARCHAR(200)                COMMENT 'Email utilise pour PayPal',
    giftcard_code       TEXT                        COMMENT 'Code carte cadeau',
    giftcard_image_url  TEXT                        COMMENT 'URL image carte',
    admin_note          TEXT                        COMMENT 'Note admin lors validation',
    validated_by        BIGINT                      COMMENT 'Discord ID du super-admin ayant valide',
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    validated_at        TIMESTAMP       NULL,
    KEY idx_order_id (order_id),
    KEY idx_user     (user_id),
    KEY idx_status   (status),
    KEY idx_created  (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_PAYMENTS - Historique complet des paiements
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_payments (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    user_id             BIGINT,
    guild_id            BIGINT,
    order_id            VARCHAR(20)                 COMMENT 'Reference vai_orders si manuel',
    method              ENUM('oxapay','paypal','giftcard'),
    amount              DECIMAL(10,2),
    currency            VARCHAR(10)     DEFAULT 'EUR',
    plan                ENUM('premium','pro'),
    status              ENUM('completed','failed','refunded'),
    oxapay_invoice_id   VARCHAR(100)                COMMENT 'ID invoice OxaPay si crypto',
    paid_at             TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user   (user_id),
    KEY idx_status (status),
    KEY idx_paid   (paid_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_SUBSCRIPTIONS - Abonnements actifs par serveur
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_subscriptions (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    guild_id    BIGINT          UNIQUE,
    user_id     BIGINT                          COMMENT 'Qui a paye',
    plan        ENUM('premium','pro'),
    started_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    expires_at  TIMESTAMP       NULL            COMMENT 'NULL = pas dexpiration fixee',
    is_active   TINYINT(1)      DEFAULT 1,
    payment_id  INT                             COMMENT 'FK vers vai_payments',
    KEY idx_guild   (guild_id),
    KEY idx_active  (is_active),
    KEY idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_KNOWLEDGE_BASE - Base de connaissances par serveur (Premium/Pro)
-- Nouvelle colonne : is_active pour desactiver sans supprimer
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_knowledge_base (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    guild_id    BIGINT          NOT NULL,
    question    TEXT,
    answer      LONGTEXT,
    category    VARCHAR(100),
    priority    INT             DEFAULT 0,
    is_active   TINYINT(1)      DEFAULT 1,
    created_by  BIGINT                          COMMENT 'Discord user ID via dashboard',
    created_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_guild    (guild_id),
    KEY idx_category (category),
    KEY idx_active   (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_DASHBOARD_SESSIONS - Sessions OAuth2 Discord pour le dashboard
-- ============================================================================

-- ============================================================================
-- VAI_DASHBOARD_USERS - Comptes dashboard (OAuth Discord) + email
-- Objectif : compter les utilisateurs dashboard et preparer les upgrades.
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_dashboard_users (
    discord_user_id     BIGINT PRIMARY KEY          COMMENT 'Discord User ID',
    discord_username    VARCHAR(100),
    email               VARCHAR(255),
    email_verified      TINYINT(1)      DEFAULT 0,
    avatar_url          VARCHAR(255),
    first_login_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    last_login_at       TIMESTAMP       NULL,
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY idx_email       (email),
    KEY idx_last_login  (last_login_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS vai_dashboard_sessions (
    id                  INT AUTO_INCREMENT PRIMARY KEY,
    discord_user_id     BIGINT,
    discord_username    VARCHAR(100),
    access_token        VARCHAR(500)                COMMENT 'Token OAuth2 Discord',
    jwt_token           TEXT                        COMMENT 'JWT session dashboard',
    guild_ids_json      JSON                        COMMENT 'Liste des guild_ids autorises (owner/admin) au login',
    is_revoked          TINYINT(1)      DEFAULT 0,
    expires_at          TIMESTAMP,
    created_at          TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    KEY idx_user    (discord_user_id),
    KEY idx_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_AUDIT_LOG - Journal d'audit des actions dashboard (nouveau)
-- Trace toutes les actions admin : validation commandes, config, KB, etc.
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_audit_log (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    actor_id        BIGINT                          COMMENT 'Discord user ID de l auteur',
    actor_username  VARCHAR(100),
    guild_id        BIGINT                          COMMENT 'Serveur concerne (NULL si global)',
    action          VARCHAR(100)    NOT NULL        COMMENT 'Ex: order.validate, guild.config, kb.create',
    target_id       VARCHAR(100)                    COMMENT 'ID de l objet cible',
    details         JSON                            COMMENT 'Donnees supplementaires libres',
    ip_address      VARCHAR(45),
    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    KEY idx_actor   (actor_id),
    KEY idx_guild   (guild_id),
    KEY idx_action  (action),
    KEY idx_created (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ============================================================================
-- VAI_BOT_STATUS - Etat du bot en temps reel (nouveau)
-- Ecrit par le bot, lu par le dashboard pour l'indicateur "BOT EN LIGNE"
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_bot_status (
    id              INT AUTO_INCREMENT PRIMARY KEY,
    guild_count     INT             DEFAULT 0,
    user_count      INT             DEFAULT 0,
    channel_count   INT             DEFAULT 0       COMMENT 'Nombre total de channels accessibles',
    uptime_sec      INT             DEFAULT 0,
    latency_ms      FLOAT           DEFAULT 0       COMMENT 'Latence WebSocket Discord en ms',
    shard_count     INT             DEFAULT 1       COMMENT 'Nombre de shards actifs',
    started_at      TIMESTAMP       NULL            COMMENT 'Heure de demarrage du bot',
    version         VARCHAR(20),
    updated_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT IGNORE INTO vai_bot_status (id, guild_count, user_count, version)
VALUES (1, 0, 0, '0.2.0');

-- ============================================================================
-- Indexes supplementaires pour performance
-- ============================================================================

CREATE INDEX idx_vai_subscriptions_guild_active ON vai_subscriptions(guild_id, is_active);
CREATE INDEX idx_vai_orders_user_status         ON vai_orders(user_id, status);
CREATE INDEX idx_vai_tickets_guild_opened       ON vai_tickets(guild_id, opened_at);
CREATE INDEX idx_vai_audit_created              ON vai_audit_log(created_at);

-- ============================================================================
-- Vues utiles
-- ============================================================================

CREATE OR REPLACE VIEW vai_active_subscriptions AS
SELECT
    s.*,
    g.name  AS guild_name,
    u.username AS user_name
FROM vai_subscriptions s
LEFT JOIN vai_guilds g ON s.guild_id = g.id
LEFT JOIN vai_users  u ON s.user_id  = u.id
WHERE s.is_active = 1
  AND (s.expires_at IS NULL OR s.expires_at > NOW());

CREATE OR REPLACE VIEW vai_pending_orders_view AS
SELECT
    o.*,
    u.username AS user_name,
    g.name     AS guild_name
FROM vai_orders o
LEFT JOIN vai_users  u ON o.user_id  = u.id
LEFT JOIN vai_guilds g ON o.guild_id = g.id
WHERE o.status = 'pending'
ORDER BY o.created_at DESC;

CREATE OR REPLACE VIEW vai_dashboard_stats AS
SELECT
    (SELECT COUNT(*) FROM vai_guilds)                                              AS total_guilds,
    (SELECT COUNT(*) FROM vai_dashboard_users)                                     AS total_users,
    (SELECT COUNT(*) FROM vai_tickets WHERE DATE(opened_at) = CURDATE())           AS tickets_today,
    (SELECT COUNT(*) FROM vai_orders  WHERE status = 'pending')                    AS orders_pending,
    (SELECT COALESCE(SUM(amount),0) FROM vai_payments
      WHERE status = 'completed'
        AND YEAR(paid_at) = YEAR(CURDATE())
        AND MONTH(paid_at) = MONTH(CURDATE()))                                    AS revenue_month,
    (SELECT COUNT(*) FROM vai_subscriptions WHERE is_active = 1)                   AS active_subs,
    (SELECT guild_count FROM vai_bot_status WHERE id = 1)                          AS bot_guild_count,
    (SELECT user_count FROM vai_bot_status WHERE id = 1)                           AS bot_user_count,
    (SELECT uptime_sec FROM vai_bot_status WHERE id = 1)                           AS bot_uptime_sec,
    (SELECT latency_ms FROM vai_bot_status WHERE id = 1)                           AS bot_latency_ms,
    (SELECT version FROM vai_bot_status WHERE id = 1)                              AS bot_version,
    (SELECT TIMESTAMPDIFF(SECOND, updated_at, NOW()) < 120
       FROM vai_bot_status WHERE id = 1)                                           AS bot_is_online;

-- ============================================================================
-- Script de migration depuis v0.1 (a executer si la DB existe deja)
-- ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS auto_translate  TINYINT(1) DEFAULT 1;
-- ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS public_support  TINYINT(1) DEFAULT 1;
-- ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS auto_transcript TINYINT(1) DEFAULT 1;
-- ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS ai_moderation   TINYINT(1) DEFAULT 0;
-- ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS staff_suggestions TINYINT(1) DEFAULT 0;
-- ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS welcome_channel_id BIGINT;
-- ALTER TABLE vai_guilds ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;
-- ALTER TABLE vai_tickets ADD COLUMN IF NOT EXISTS user_username VARCHAR(100);
-- ALTER TABLE vai_tickets ADD COLUMN IF NOT EXISTS assigned_staff_name VARCHAR(100);
-- ALTER TABLE vai_tickets MODIFY COLUMN status ENUM('open','in_progress','closed') DEFAULT 'open';
-- ALTER TABLE vai_orders ADD COLUMN IF NOT EXISTS user_username VARCHAR(100);
-- ALTER TABLE vai_orders ADD COLUMN IF NOT EXISTS guild_name VARCHAR(100);
-- ALTER TABLE vai_orders ADD COLUMN IF NOT EXISTS validated_by BIGINT;
-- ALTER TABLE vai_ticket_messages ADD COLUMN IF NOT EXISTS author_username VARCHAR(100);
-- ALTER TABLE vai_knowledge_base ADD COLUMN IF NOT EXISTS is_active TINYINT(1) DEFAULT 1;
-- ALTER TABLE vai_dashboard_sessions ADD COLUMN IF NOT EXISTS is_revoked TINYINT(1) DEFAULT 0;
-- ALTER TABLE vai_dashboard_sessions MODIFY COLUMN jwt_token TEXT;
-- ALTER TABLE vai_dashboard_sessions MODIFY COLUMN access_token VARCHAR(500);
-- ============================================================================

-- ============================================================================
-- VAI_TEMP_CODES - Codes d'echange temporaires post-OAuth (v0.3)
-- Remplace le stockage en memoire (_temp_codes dict) pour supporter
-- les environnements multi-process et survivre aux redemarrages.
-- Chaque code est usage unique, expire en 60 secondes.
-- Flux : /auth/callback genere un code -> dashboard JS l'echange via POST /auth/exchange
-- Le JWT ne passe JAMAIS dans une URL.
-- ============================================================================

CREATE TABLE IF NOT EXISTS vai_temp_codes (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(64)     NOT NULL UNIQUE  COMMENT 'Token URL-safe genere par secrets.token_urlsafe(24)',
    jwt_token   TEXT            NOT NULL         COMMENT 'JWT complet a retourner apres echange',
    user_json   JSON            NOT NULL         COMMENT 'Donnees utilisateur {id, username, avatar, is_super_admin}',
    guilds_json JSON            NOT NULL         COMMENT 'Liste des guilds filtrees de l utilisateur',
    used        TINYINT(1)      DEFAULT 0        COMMENT '1 = deja consomme (usage unique)',
    expires_at  TIMESTAMP       NOT NULL         COMMENT 'Expire 60 secondes apres creation',
    created_at  TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
    KEY idx_code    (code),
    KEY idx_expires (expires_at),
    KEY idx_used    (used)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Nettoyage automatique des codes expires (evenement MySQL)
-- A activer si event_scheduler = ON dans MySQL config
-- CREATE EVENT IF NOT EXISTS vai_cleanup_temp_codes
--     ON SCHEDULE EVERY 5 MINUTE
--     DO DELETE FROM vai_temp_codes WHERE expires_at < NOW() OR used = 1;

-- ============================================================================
-- Migration depuis v0.2 (si la DB existe deja)
-- CREATE TABLE IF NOT EXISTS vai_temp_codes (...) -- voir ci-dessus
-- ============================================================================
