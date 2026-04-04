from __future__ import annotations

import os
from pathlib import Path

from loguru import logger

from bot.config import DB_TABLE_PREFIX
from bot.db.connection import get_db_context


def _is_truthy(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _split_sql_statements(sql: str) -> list[str]:
    statements: list[str] = []
    buf: list[str] = []

    in_single = False
    in_double = False
    in_backtick = False
    in_line_comment = False
    in_block_comment = False

    def is_escaped(pos: int) -> bool:
        # Count backslashes just before this position
        bs = 0
        j = pos - 1
        while j >= 0 and sql[j] == "\\":
            bs += 1
            j -= 1
        return (bs % 2) == 1

    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        nxt = sql[i + 1] if i + 1 < n else ""

        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            i += 1
            continue

        if in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        if not (in_single or in_double or in_backtick):
            if ch == "-" and nxt == "-":
                in_line_comment = True
                i += 2
                continue
            if ch == "#":
                in_line_comment = True
                i += 1
                continue
            if ch == "/" and nxt == "*":
                in_block_comment = True
                i += 2
                continue

        if ch == "'" and not (in_double or in_backtick) and not is_escaped(i):
            in_single = not in_single
        elif ch == '"' and not (in_single or in_backtick) and not is_escaped(i):
            in_double = not in_double
        elif ch == "`" and not (in_single or in_double):
            in_backtick = not in_backtick

        if ch == ";" and not (in_single or in_double or in_backtick):
            stmt = "".join(buf).strip()
            if stmt:
                statements.append(stmt)
            buf = []
            i += 1
            continue

        buf.append(ch)
        i += 1

    tail = "".join(buf).strip()
    if tail:
        statements.append(tail)

    return statements


def _apply_schema_file(sql_path: Path, *, only_views: bool = False, skip_views: bool = False) -> None:
    sql_text = sql_path.read_text(encoding="utf-8", errors="replace")
    statements = _split_sql_statements(sql_text)

    to_run: list[str] = []

    for stmt in statements:
        head = stmt.lstrip().split(None, 4)[:4]
        head_str = " ".join(head).lower()
        if head_str.startswith("create database") or head_str.startswith("use "):
            continue
        
        is_view = head_str.startswith("create or replace view") or head_str.startswith("create view")
        
        if only_views and not is_view:
            continue
        if skip_views and is_view:
            continue
        
        to_run.append(stmt)

    with get_db_context() as conn:
        cursor = conn.cursor()

        for stmt in to_run:
            try:
                cursor.execute(stmt)
            except Exception as e:
                msg = str(e).lower()
                # Common ignorable errors during idempotent migration
                ignorable = (
                    "duplicate key name" in msg
                    or "duplicate column name" in msg
                    or "already exists" in msg
                    or ("unknown column" in msg and only_views)
                    or ("doesn't exist" in msg and only_views)
                )
                if ignorable:
                    continue
                
                # For non-views, we might want to log but continue if it's potentially non-critical
                # but for now we follow the existing behavior of raising unless ignorable.
                raise


def _column_info(table_name: str, column_name: str) -> dict | None:
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            """
            SELECT column_name, data_type, column_type, column_default, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = DATABASE()
              AND table_name = %s
              AND column_name = %s
            """,
            (table_name, column_name),
        )
        return cursor.fetchone()


def _table_exists(table_name: str) -> bool:
    with get_db_context() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = DATABASE()
              AND table_name = %s
            LIMIT 1
            """,
            (table_name,),
        )
        return cursor.fetchone() is not None


def _ensure_dashboard_sessions_migrations() -> None:
    table = f"{DB_TABLE_PREFIX}dashboard_sessions"
    if not _table_exists(table):
        return

    # Add is_revoked if missing.
    if _column_info(table, "is_revoked") is None:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"ALTER TABLE {table} ADD COLUMN is_revoked TINYINT(1) DEFAULT 0"
            )

    # Add guild_ids_json if missing.
    if _column_info(table, "guild_ids_json") is None:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                f"ALTER TABLE {table} "
                f"ADD COLUMN guild_ids_json JSON NULL "
                f"COMMENT 'Liste des guild_ids autorises (owner/admin) au login'"
            )

    # Ensure jwt_token is TEXT (older init.sql used VARCHAR(500)).
    info = _column_info(table, "jwt_token")
    if info and (info.get("data_type") or "").lower() in {"varchar", "char"}:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN jwt_token TEXT")

    # Ensure access_token can hold Discord access tokens comfortably.
    info = _column_info(table, "access_token")
    max_len = info.get("character_maximum_length") if info else None
    if info and (info.get("data_type") or "").lower() in {"varchar", "char"} and (max_len or 0) < 500:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN access_token VARCHAR(500)")


def _ensure_bot_status_migrations() -> None:
    """Ajoute les nouvelles colonnes a vai_bot_status si elles manquent."""
    table = f"{DB_TABLE_PREFIX}bot_status"
    if not _table_exists(table):
        return

    new_columns = {
        "channel_count": "INT DEFAULT 0 COMMENT 'Nombre total de channels accessibles'",
        "latency_ms":    "FLOAT DEFAULT 0 COMMENT 'Latence WebSocket Discord en ms'",
        "shard_count":   "INT DEFAULT 1 COMMENT 'Nombre de shards actifs'",
        "started_at":    "TIMESTAMP NULL COMMENT 'Heure de demarrage du bot'",
    }

    for col_name, col_def in new_columns.items():
        if _column_info(table, col_name) is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    logger.info(f"[db] Colonne {col_name} ajoutee a {table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {table}.{col_name}: {e}")


def _ensure_ticket_migrations() -> None:
    """Ajoute les colonnes necessaires pour update embed + stockage complet messages."""
    tickets_table = f"{DB_TABLE_PREFIX}tickets"
    if _table_exists(tickets_table):
        # Snapshot username at ticket creation (used by dashboard and bot).
        if _column_info(tickets_table, "user_username") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"ADD COLUMN user_username VARCHAR(100) NULL "
                        f"COMMENT 'Snapshot username au moment de louverture'"
                    )
                    logger.info(f"[db] Colonne user_username ajoutee a {tickets_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {tickets_table}.user_username: {e}")

        # Assigned staff name (dashboard display)
        if _column_info(tickets_table, "assigned_staff_name") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"ADD COLUMN assigned_staff_name VARCHAR(100) NULL"
                    )
                    logger.info(f"[db] Colonne assigned_staff_name ajoutee a {tickets_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {tickets_table}.assigned_staff_name: {e}")

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

        if _column_info(tickets_table, "assigned_staff_id") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"ADD COLUMN assigned_staff_id BIGINT NULL"
                    )
                    logger.info(f"[db] Colonne assigned_staff_id ajoutee a {tickets_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {tickets_table}.assigned_staff_id: {e}")

        if _column_info(tickets_table, "initial_message_id") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"ADD COLUMN initial_message_id BIGINT NULL "
                        f"COMMENT 'Message embed initial du ticket (pour mise a jour langue)'"
                    )
                    logger.info(f"[db] Colonne initial_message_id ajoutee a {tickets_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {tickets_table}.initial_message_id: {e}")

        # Priorité du ticket (bas / moyen / haut / urgent) pour triage.
        if _column_info(tickets_table, "priority") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"ADD COLUMN priority VARCHAR(20) DEFAULT 'medium' "
                        f"COMMENT 'Priorite du ticket: low|medium|high|urgent'"
                    )
                    logger.info(f"[db] Colonne priority ajoutee a {tickets_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {tickets_table}.priority: {e}")

        # Harmonise status pour supporter pending_close sur les bases existantes.
        status_info = _column_info(tickets_table, "status")
        status_type = ((status_info or {}).get("column_type") or "").lower()
        if status_info and ("enum(" not in status_type or "pending_close" not in status_type):
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"UPDATE {tickets_table} "
                        f"SET status = 'open' "
                        f"WHERE status IS NULL OR status NOT IN ('open','in_progress','pending_close','closed')"
                    )
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"MODIFY COLUMN status ENUM('open','in_progress','pending_close','closed') DEFAULT 'open'"
                    )
                    logger.info(f"[db] Colonne status harmonisee sur {tickets_table}")
                except Exception as e:
                    logger.warning(f"[db] ALTER {tickets_table}.status enum: {e}")

        # Harmonise priority pour supporter urgent et normaliser les anciennes valeurs.
        priority_info = _column_info(tickets_table, "priority")
        priority_type = ((priority_info or {}).get("column_type") or "").lower()
        if priority_info and ("enum(" not in priority_type or "urgent" not in priority_type):
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"""
                        UPDATE {tickets_table}
                        SET priority = CASE
                            WHEN priority IS NULL OR TRIM(priority) = '' THEN 'medium'
                            WHEN LOWER(priority) IN ('low', 'bas', 'basse') THEN 'low'
                            WHEN LOWER(priority) IN ('medium', 'moyen', 'moyenne') THEN 'medium'
                            WHEN LOWER(priority) IN ('high', 'haut', 'haute', 'eleve') THEN 'high'
                            WHEN LOWER(priority) IN ('urgent', 'prioritaire') THEN 'urgent'
                            ELSE 'medium'
                        END
                        """
                    )
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"MODIFY COLUMN priority ENUM('low','medium','high','urgent') DEFAULT 'medium'"
                    )
                    logger.info(f"[db] Colonne priority harmonisee sur {tickets_table}")
                except Exception as e:
                    logger.warning(f"[db] ALTER {tickets_table}.priority enum: {e}")

        # SLA breach alert tracking
        if _column_info(tickets_table, "sla_breach_alert_sent") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {tickets_table} "
                        f"ADD COLUMN sla_breach_alert_sent TINYINT(1) DEFAULT 0 "
                        f"COMMENT 'Alerte SLA envoyee (1=oui)'"
                    )
                    logger.info(f"[db] Colonne sla_breach_alert_sent ajoutee a {tickets_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {tickets_table}.sla_breach_alert_sent: {e}")

    msgs_table = f"{DB_TABLE_PREFIX}ticket_messages"
    if _table_exists(msgs_table):
        if _column_info(msgs_table, "author_username") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {msgs_table} "
                        f"ADD COLUMN author_username VARCHAR(100) NULL"
                    )
                    logger.info(f"[db] Colonne author_username ajoutee a {msgs_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {msgs_table}.author_username: {e}")

        if _column_info(msgs_table, "discord_message_id") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {msgs_table} "
                        f"ADD COLUMN discord_message_id BIGINT NULL "
                        f"COMMENT 'Discord Message ID'"
                    )
                    logger.info(f"[db] Colonne discord_message_id ajoutee a {msgs_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {msgs_table}.discord_message_id: {e}")

        if _column_info(msgs_table, "attachments_json") is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(
                        f"ALTER TABLE {msgs_table} "
                        f"ADD COLUMN attachments_json JSON NULL "
                        f"COMMENT 'Liste d attachments (urls, filenames, etc.)'"
                    )
                    logger.info(f"[db] Colonne attachments_json ajoutee a {msgs_table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {msgs_table}.attachments_json: {e}")


def _ensure_guild_v04_migrations() -> None:
    """Ajoute les colonnes v0.4 a vai_guilds (ticket custom + AI prompt)."""
    table = f"{DB_TABLE_PREFIX}guilds"
    if not _table_exists(table):
        return

    new_columns = {
        # Core feature toggles (for schema drift safety)
        "auto_translate":             "TINYINT(1) DEFAULT 1 COMMENT 'Traduction auto tickets'",
        "public_support":             "TINYINT(1) DEFAULT 1 COMMENT 'IA channel support public'",
        "auto_transcript":            "TINYINT(1) DEFAULT 1 COMMENT 'Resume IA fermeture ticket'",
        "ai_moderation":              "TINYINT(1) DEFAULT 0 COMMENT 'Moderation IA'",
        "staff_suggestions":          "TINYINT(1) DEFAULT 0 COMMENT 'Suggestions staff IA'",

        "ticket_open_channel_id":     "BIGINT NULL COMMENT 'Channel bouton/selecteur ouverture ticket'",
        "ticket_open_message":        "TEXT NULL COMMENT 'Message avec bouton/selecteur'",
        "ticket_button_label":        "VARCHAR(100) DEFAULT 'Ouvrir un ticket'",
        "ticket_button_style":        "VARCHAR(20) DEFAULT 'primary'",
        "ticket_button_emoji":        "VARCHAR(50) NULL",
        "ticket_welcome_message":     "TEXT NULL COMMENT 'Message bienvenue personnalise'",
        "ticket_welcome_message_user": "TEXT NULL COMMENT 'Message bienvenue personnalise cote utilisateur'",
        "ticket_welcome_message_staff": "TEXT NULL COMMENT 'Message bienvenue personnalise cote staff'",
        "ticket_take_label":          "VARCHAR(100) DEFAULT 'S''approprier le ticket'",
        "ticket_close_label":         "VARCHAR(100) DEFAULT 'Fermer le ticket'",
        "ticket_reopen_label":        "VARCHAR(100) DEFAULT 'Réouvrir'",
        "ticket_transcript_label":    "VARCHAR(100) DEFAULT 'Transcript'",
        "ticket_welcome_color":       "VARCHAR(10) DEFAULT 'blue'",
        "ticket_selector_enabled":    "TINYINT(1) DEFAULT 0",
        "ticket_selector_placeholder": "VARCHAR(200) DEFAULT 'Selectionnez le type de ticket'",
        "ticket_selector_options":    "JSON NULL",
        "ticket_mention_staff":       "TINYINT(1) DEFAULT 1",
        "ticket_close_on_leave":      "TINYINT(1) DEFAULT 0",
        "ticket_max_open":            "INT DEFAULT 1",
        "staff_languages_json":       "JSON NULL COMMENT 'Langues staff [{user_id,username,language}]'",
        "ai_custom_prompt":           "TEXT NULL COMMENT 'Prompt IA personnalise'",
        "ai_prompt_enabled":          "TINYINT(1) DEFAULT 0",
        # Deploy queue / persistence
        "ticket_open_message_id":      "BIGINT NULL COMMENT 'Message ID du message ouverture tickets (pour edit)'",
        "ticket_open_needs_deploy":    "TINYINT(1) DEFAULT 0 COMMENT '1 = bot doit (re)deployer le message ouverture'",
        "ticket_open_last_deploy_error": "TEXT NULL COMMENT 'Derniere erreur de deploiement (debug)'",
        "ticket_open_delete_requested":  "TINYINT(1) DEFAULT 0 COMMENT '1 = bot doit supprimer le message ouverture'",
    }

    for col_name, col_def in new_columns.items():
        if _column_info(table, col_name) is None:
            with get_db_context() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    logger.info(f"[db] Colonne {col_name} ajoutee a {table}")
                except Exception as e:
                    if "duplicate column" not in str(e).lower():
                        logger.warning(f"[db] ALTER {table}.{col_name}: {e}")


def _ensure_knowledge_base_migrations() -> None:
    """Ajoute les colonnes KB manquantes (schema drift)."""
    table = f"{DB_TABLE_PREFIX}knowledge_base"
    if not _table_exists(table):
        return

    if _column_info(table, "is_active") is None:
        with get_db_context() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN is_active TINYINT(1) DEFAULT 1"
                )
                logger.info(f"[db] Colonne is_active ajoutee a {table}")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning(f"[db] ALTER {table}.is_active: {e}")


def _ensure_audit_log_and_notifications_migrations() -> None:
    """Crée les tables d'audit et de notifications si elles manquent."""
    # Audit Log
    audit_table = f"{DB_TABLE_PREFIX}audit_log"
    if not _table_exists(audit_table):
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {audit_table} (
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
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            logger.info(f"[db] Table {audit_table} creee")

    # Pending Notifications
    notif_table = f"{DB_TABLE_PREFIX}pending_notifications"
    if not _table_exists(notif_table):
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS {notif_table} (
                    id              INT AUTO_INCREMENT PRIMARY KEY,
                    user_id         BIGINT          NOT NULL        COMMENT 'ID utilisateur Discord destinataire',
                    message         TEXT            NOT NULL        COMMENT 'Contenu du message DM',
                    attempts        INT             DEFAULT 0       COMMENT 'Nombre de tentatives denvoi',
                    last_attempt    TIMESTAMP       NULL            COMMENT 'Derniere tentative',
                    created_at      TIMESTAMP       DEFAULT CURRENT_TIMESTAMP,
                    KEY idx_user    (user_id),
                    KEY idx_attempts (attempts)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """)
            logger.info(f"[db] Table {notif_table} creee")


def _ensure_subscription_migrations() -> None:
    table = f"{DB_TABLE_PREFIX}subscriptions"
    if not _table_exists(table):
        return

    if _column_info(table, "reminder_sent") is None:
        with get_db_context() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"ALTER TABLE {table} "
                    f"ADD COLUMN reminder_sent TINYINT(1) DEFAULT 0 "
                    f"COMMENT '1 = rappel de renouvellement deja envoye'"
                )
                logger.info(f"[db] Colonne reminder_sent ajoutee a {table}")
            except Exception as e:
                if "duplicate column" not in str(e).lower():
                    logger.warning(f"[db] ALTER {table}.reminder_sent: {e}")


def _ensure_billing_vnext_migrations() -> None:
    column_specs = {
        f"{DB_TABLE_PREFIX}guilds": {
            "tier": "VARCHAR(32) DEFAULT 'free'",
        },
        f"{DB_TABLE_PREFIX}orders": {
            "method": "VARCHAR(32) NULL",
            "plan": "VARCHAR(32) NULL",
            "billing_interval": "VARCHAR(16) DEFAULT 'month'",
        },
        f"{DB_TABLE_PREFIX}payments": {
            "method": "VARCHAR(32) NULL",
            "plan": "VARCHAR(32) NULL",
            "billing_interval": "VARCHAR(16) DEFAULT 'month'",
        },
        f"{DB_TABLE_PREFIX}subscriptions": {
            "plan": "VARCHAR(32) NULL",
            "billing_interval": "VARCHAR(16) DEFAULT 'month'",
        },
    }

    for table, columns in column_specs.items():
        if not _table_exists(table):
            continue
        for column_name, column_sql in columns.items():
            info = _column_info(table, column_name)
            if info is None:
                with get_db_context() as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_name} {column_sql}")
                        logger.info(f"[db] Colonne {column_name} ajoutee a {table}")
                    except Exception as e:
                        if "duplicate column" not in str(e).lower():
                            logger.warning(f"[db] ALTER {table}.{column_name}: {e}")
                continue

            data_type = str(info.get("data_type") or "").lower()
            col_type = str(info.get("column_type") or "").lower()
            needs_modify = False
            if data_type == "enum":
                needs_modify = True
            elif column_name == "billing_interval" and ("varchar" not in data_type):
                needs_modify = True
            elif column_name in {"tier", "plan", "method"} and "varchar" not in data_type:
                needs_modify = True
            elif column_name in {"tier", "plan", "method"} and data_type == "varchar":
                max_len = int(info.get("character_maximum_length") or 0)
                if max_len < 16:
                    needs_modify = True

            if needs_modify:
                with get_db_context() as conn:
                    cursor = conn.cursor()
                    try:
                        cursor.execute(f"ALTER TABLE {table} MODIFY COLUMN {column_name} {column_sql}")
                        logger.info(f"[db] Colonne {table}.{column_name} convertie en mode billing vNext")
                    except Exception as e:
                        logger.warning(f"[db] MODIFY {table}.{column_name}: {e}")

    replacements = (
        (f"{DB_TABLE_PREFIX}guilds", "tier"),
        (f"{DB_TABLE_PREFIX}orders", "plan"),
        (f"{DB_TABLE_PREFIX}payments", "plan"),
        (f"{DB_TABLE_PREFIX}subscriptions", "plan"),
    )
    for table, column_name in replacements:
        if not _table_exists(table):
            continue
        with get_db_context() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute(
                    f"UPDATE {table} SET {column_name} = 'starter' WHERE LOWER({column_name}) = 'premium'"
                )
            except Exception as e:
                logger.warning(f"[db] UPDATE legacy plan alias on {table}.{column_name}: {e}")


def ensure_database_schema() -> None:
    """
    Creates/migrates the MySQL schema at API startup using the `database/` folder.

    This is meant to fix common drift issues (ex: missing vai_dashboard_sessions.is_revoked),
    and to auto-create tables/views in fresh environments.
    """
    if not _is_truthy(os.getenv("AUTO_DB_MIGRATE"), default=True):
        logger.info("[db] AUTO_DB_MIGRATE=0 -> skip migrations")
        return

    root = Path(__file__).resolve().parents[1]
    schema_sql = root / "database" / "schema.sql"

    if not schema_sql.exists():
        logger.warning(f"[db] schema.sql introuvable: {schema_sql}")
        return

    logger.info(f"[db] Migration schema depuis {schema_sql}")
    # 1) Apply tables/indexes/inserts (skip views to avoid failures on missing columns).
    _apply_schema_file(schema_sql, skip_views=True)

    # 2) Targeted ALTERs (schema drift fixes).
    _ensure_dashboard_sessions_migrations()
    _ensure_bot_status_migrations()
    _ensure_ticket_migrations()
    _ensure_knowledge_base_migrations()
    _ensure_guild_v04_migrations()
    _ensure_audit_log_and_notifications_migrations()
    _ensure_subscription_migrations()
    _ensure_billing_vnext_migrations()

    # 3) Re-apply views (so they can reference the new columns).
    try:
        _apply_schema_file(schema_sql, only_views=True)
    except Exception as e:
        # Don't block startup only because of view creation issues in older schemas.
        logger.warning(f"[db] View creation failed (drift?): {str(e)[:180]}")

    logger.info("[db] Migration OK")
