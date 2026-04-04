"""
Cog: Tickets - Gestion des tickets de support avec traduction en temps reel.
La configuration du systeme (category, staff role, etc.) se fait via le dashboard.
"""

import asyncio
import discord
from discord.ext import commands, tasks
from loguru import logger
import io
import json
from datetime import datetime

from bot.db.models import TicketModel, GuildModel, UserModel, TicketMessageModel, PendingActionModel, TicketSatisfactionModel
from bot.db.connection import get_db_context
from bot.config import DB_TABLE_PREFIX, COLOR_SUCCESS, COLOR_NOTICE, COLOR_WARNING, COLOR_CRITICAL, BOT_OWNER_DISCORD_ID, TICKET_CHANNEL_PREFIX
from bot.services.translator import TranslatorService
from bot.services.groq_client import GroqClient
from bot.utils.embed_style import style_embed, translation_embed_title, send_localized_embed, strip_emojis, _normalize_lang
from bot.utils.i18n import i18n

# LEGACY DICTS REMOVED - using i18n system instead

# TICKET_BUTTON_TEXTS removed - using i18n system instead


def _status_label(status: str | None, locale: str = "fr") -> str:
    key = f"tickets.status_{status or 'open'}"
    return i18n.get(key, locale)


def _render_template(template: str, variables: dict[str, str]) -> str:
    out = str(template or "")
    for key, value in variables.items():
        out = out.replace(f"{{{key}}}", str(value))
    return out


def _truncate_block(text: str, limit: int = 1024) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text or "—"
    return text[: limit - 1].rstrip() + "…"


def _format_duration_short(total_seconds: float | int | None) -> str:
    secs = max(0, int(total_seconds or 0))
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)
    parts = []
    if days:
        parts.append(f"{days}j")
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if not parts:
        parts.append(f"{seconds}s")
    return " ".join(parts[:3])


def _compute_ticket_metrics(ticket: dict, messages: list[dict]) -> dict[str, str | None]:
    user_id = int(ticket.get("user_id") or 0)
    pending_user_at: datetime | None = None
    response_deltas: list[float] = []

    for msg in messages or []:
        sent_at = msg.get("sent_at")
        if not isinstance(sent_at, datetime):
            continue
        author_id = int(msg.get("author_id") or 0)
        if author_id == user_id:
            if pending_user_at is None:
                pending_user_at = sent_at
            continue
        if pending_user_at is not None:
            delta = (sent_at - pending_user_at).total_seconds()
            if delta >= 0:
                response_deltas.append(delta)
            pending_user_at = None

    opened_at = ticket.get("opened_at")
    closed_at = ticket.get("closed_at") or datetime.utcnow()
    open_duration = None
    if isinstance(opened_at, datetime) and isinstance(closed_at, datetime):
        open_duration = max(0, (closed_at - opened_at).total_seconds())

    avg_response = None
    if response_deltas:
        avg_response = sum(response_deltas) / len(response_deltas)

    return {
        "avg_response": _format_duration_short(avg_response) if avg_response is not None else None,
        "open_duration": _format_duration_short(open_duration) if open_duration is not None else None,
    }


def _safe_int(val) -> int | None:
    """Safely convert a value to int, returning None on failure."""
    if val is None:
        return None
    try:
        return int(val)
    except (ValueError, TypeError):
        return None


_LANG_NAMES = {
    "fr": "French", "en": "English", "es": "Spanish", "de": "German",
    "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "ru": "Russian",
    "ja": "Japanese", "ko": "Korean", "zh": "Chinese", "ar": "Arabic",
    "hi": "Hindi", "tr": "Turkish", "pl": "Polish", "sv": "Swedish",
    "da": "Danish", "no": "Norwegian", "fi": "Finnish", "cs": "Czech",
    "ro": "Romanian", "hu": "Hungarian", "uk": "Ukrainian", "el": "Greek",
    "th": "Thai", "vi": "Vietnamese", "id": "Indonesian", "ms": "Malay",
}


def get_lang_name(code: str | None) -> str:
    """Return the English name for a language code, or the code itself."""
    if not code:
        return "Unknown"
    normalized = _normalize_lang(code, "en")
    return _LANG_NAMES.get(normalized, normalized.upper())


def _safe_filename_part(value: str | None, fallback: str) -> str:
    raw = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "-" for ch in str(value or fallback).strip().lower())
    clean = raw.strip("-_")
    return clean or fallback


def _build_transcript_filename(ticket_id: int, audience: str, language_code: str | None) -> str:
    code = _normalize_lang(language_code, "en")
    language_name = _safe_filename_part(get_lang_name(code), code)
    audience_name = _safe_filename_part(audience, "audience")
    return f"ticket-{ticket_id}-{audience_name}-{language_name}-{code}.txt"


class TicketsCog(commands.Cog):
    """Tickets de support avec traduction en temps reel."""

    @staticmethod
    def _dominant_language_from_history(ticket_id: int, author_id: int | None = None) -> str | None:
        """
        Essaie de déduire une langue stable à partir de l'historique
        des messages du ticket pour limiter les faux positifs de détection.
        """
        try:
            msgs = TicketMessageModel.get_by_ticket(ticket_id)
        except Exception:
            return None

        counts: dict[str, int] = {}
        for m in msgs or []:
            if author_id is not None:
                try:
                    if int(m.get("author_id") or 0) != int(author_id):
                        continue
                except Exception:
                    continue
            lang = (m.get("original_language") or "").strip().lower()
            if not lang or lang in {"auto", "und"}:
                continue
            counts[lang] = counts.get(lang, 0) + 1

        if not counts:
            return None

        # Retourne la langue la plus fréquente.
        return max(counts.items(), key=lambda kv: kv[1])[0]

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        try:
            data = getattr(interaction, "data", None) or {}
            custom_id = data.get("custom_id")
            if not custom_id or not isinstance(custom_id, str):
                return

            if custom_id.startswith("vai:ticket_open:"):
                bucket = self.open_ticket.get_cooldown_retry_after(interaction)
                if bucket:
                    # To be localized later
                    return await interaction.response.send_message(
                        f"Wait {int(bucket)}s...",
                        ephemeral=True
                    )
                return await self.open_ticket(interaction, topic="")
        except Exception as e:
            logger.debug(f"on_interaction ticket_open ignored: {e}")
            return

    def __init__(self, bot):
        self.bot         = bot
        self.translator  = TranslatorService()
        self.groq_client = GroqClient()
        self._label_translation_cache: dict[tuple[str, str, str], str] = {}
        self.auto_close_task.start()
        self.sla_check_task.start()  # Task 5.6: SLA breach checker
        logger.info("Cog Tickets charge")

    def cog_unload(self):
        self.auto_close_task.cancel()
        self.sla_check_task.cancel()

    # ── Task 5.5: Round-robin auto-assignment ──
    def _get_round_robin_staff(self, guild: discord.Guild, staff_role_id: int | None) -> discord.Member | None:
        """Get next available staff member using round-robin based on current ticket load."""
        if not staff_role_id:
            return None
        
        staff_role = guild.get_role(int(staff_role_id))
        if not staff_role:
            return None
        
        # Get all staff members with the role
        staff_members = [m for m in staff_role.members if not m.bot]
        if not staff_members:
            return None
        
        # Get current ticket counts per staff
        try:
            with get_db_context() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    f"""
                    SELECT assigned_staff_id, COUNT(*) as count
                    FROM {DB_TABLE_PREFIX}tickets
                    WHERE guild_id = %s AND status IN ('open', 'in_progress')
                    AND assigned_staff_id IS NOT NULL
                    GROUP BY assigned_staff_id
                    """,
                    (guild.id,)
                )
                ticket_counts = {row["assigned_staff_id"]: row["count"] for row in cursor.fetchall()}
        except Exception:
            ticket_counts = {}
        
        # Find staff with minimum tickets (round-robin logic)
        min_count = min((ticket_counts.get(m.id, 0) for m in staff_members), default=0)
        candidates = [m for m in staff_members if ticket_counts.get(m.id, 0) == min_count]
        
        if not candidates:
            return None
        
        # Pick the one who was assigned least recently (simple round-robin)
        import random
        return random.choice(candidates)

    # ── Task 5.6: SLA Methods ──
    @tasks.loop(minutes=5)
    async def sla_check_task(self):
        """Check for SLA breaches every 5 minutes."""
        try:
            with get_db_context() as conn:
                cursor = conn.cursor(dictionary=True)
                # Tickets in progress without first response within SLA (default 2 hours for Pro)
                cursor.execute(
                    f"""
                    SELECT t.*, TIMESTAMPDIFF(MINUTE, t.opened_at, NOW()) as minutes_open
                    FROM {DB_TABLE_PREFIX}tickets t
                    JOIN {DB_TABLE_PREFIX}guilds g ON t.guild_id = g.id
                    WHERE t.status IN ('open', 'in_progress')
                    AND t.assigned_staff_id IS NOT NULL
                    AND g.tier IN ('pro', 'business')
                    AND TIMESTAMPDIFF(MINUTE, t.opened_at, NOW()) > 120
                    AND (t.sla_breach_alert_sent IS NULL OR t.sla_breach_alert_sent = 0)
                    """
                )
                breach_tickets = cursor.fetchall()
                
                for ticket in breach_tickets:
                    await self._send_sla_breach_alert(ticket)
                    
        except Exception as e:
            logger.debug(f"SLA check task error: {e}")

    @sla_check_task.before_loop
    async def before_sla_check(self):
        await self.bot.wait_until_ready()

    async def _send_sla_breach_alert(self, ticket: dict):
        """Send SLA breach alert to log channel and assigned staff."""
        try:
            guild = self.bot.get_guild(int(ticket["guild_id"]))
            if not guild:
                return
            
            guild_config = GuildModel.get(guild.id) or {}
            log_channel_id = _safe_int(guild_config.get("log_channel_id"))
            
            staff_member = guild.get_member(int(ticket["assigned_staff_id"]))
            minutes_open = ticket.get("minutes_open", 0)
            
            # Mark as alerted
            TicketModel.update(ticket["id"], sla_breach_alert_sent=1)
            
            # Send to log channel
            if log_channel_id:
                log_chan = self.bot.get_channel(log_channel_id)
                if log_chan:
                    embed = discord.Embed(
                        title="⚠️ SLA Breach Alert",
                        description=f"Ticket #{ticket['id']} hasn't received a response in {minutes_open} minutes",
                        color=discord.Color(COLOR_WARNING)
                    )
                    embed.add_field(name="Assigned to", value=staff_member.mention if staff_member else "Unknown")
                    embed.add_field(name="User", value=f"<@{ticket['user_id']}>")
                    embed.add_field(name="Channel", value=f"<#{ticket['channel_id']}>")
                    await log_chan.send(embed=style_embed(embed))
            
            # DM the assigned staff
            if staff_member:
                dm_embed = discord.Embed(
                    title="⏰ SLA Alert - Response Required",
                    description=f"Ticket #{ticket['id']} is approaching SLA breach ({minutes_open} minutes open). Please respond ASAP!",
                    color=discord.Color(COLOR_WARNING)
                )
                try:
                    await staff_member.send(embed=style_embed(dm_embed))
                except Exception:
                    pass  # DMs disabled
                    
            logger.info(f"SLA breach alert sent for ticket {ticket['id']}")
        except Exception as e:
            logger.debug(f"Failed to send SLA alert: {e}")

    async def _run_with_typing(self, channel: discord.abc.Messageable, func, *args):
        async with channel.typing():
            return await asyncio.to_thread(func, *args)

    def _default_button_text(self, key: str, language: str, **variables) -> str:
        return i18n.get(f"tickets.button_{key}", language, **variables)

    def _translate_button_text(self, text: str, target_language: str, fallback_language: str) -> str:
        raw = (text or "").strip()
        if not raw:
            return raw

        target = _normalize_lang(target_language, "en")
        source = self.translator.detect_language(raw) or _normalize_lang(fallback_language, "en")
        if source == target:
            return raw

        cache_key = (raw, source, target)
        cached = self._label_translation_cache.get(cache_key)
        if cached:
            return cached

        try:
            translated, _ = self.translator.translate(raw, source, target)
        except Exception:
            translated = raw
        translated = (translated or raw).strip() or raw
        self._label_translation_cache[cache_key] = translated
        return translated

    def _resolve_ticket_button_label(
        self,
        *,
        key: str,
        guild_config: dict | None,
        target_language: str,
        fallback_language: str,
        assigned_name: str | None = None,
        status: str | None = None,
    ) -> str:
        cfg = guild_config or {}
        current_status = (status or "open").strip().lower()

        if key == "take" and assigned_name:
            return self._default_button_text("taken_by", target_language, name=assigned_name[:20])
        if key == "close" and current_status == "pending_close":
            return self._default_button_text("confirm_close", target_language)

        custom_map = {
            "take": (cfg.get("ticket_take_label") or "").strip(),
            "close": (cfg.get("ticket_close_label") or "").strip(),
            "reopen": (cfg.get("ticket_reopen_label") or "").strip(),
            "transcript": (cfg.get("ticket_transcript_label") or "").strip(),
        }
        custom_value = custom_map.get(key) or ""
        if custom_value:
            return self._translate_button_text(custom_value, target_language, fallback_language)

        return self._default_button_text(key, target_language)

    def _combine_shared_button_label(self, primary: str, secondary: str) -> str:
        a = (primary or "").strip()
        b = (secondary or "").strip()
        if not a:
            return b[:80]
        if not b or a.casefold() == b.casefold():
            return a[:80]
        combined = f"{a} / {b}"
        if len(combined) <= 80:
            return combined
        return f"{a[:38].rstrip()} / {b[:38].rstrip()}"[:80]

    def _ticket_control_labels(
        self,
        guild_config: dict | None,
        assigned_name: str | None = None,
        status: str | None = None,
        user_language: str | None = None,
        staff_language: str | None = None,
    ) -> dict[str, str]:
        cfg = guild_config or {}
        staff_lang = _normalize_lang(staff_language or cfg.get("default_language"), "en")
        user_lang = _normalize_lang(user_language, staff_lang)
        current_status = (status or "open").strip().lower()

        take_label = self._resolve_ticket_button_label(
            key="take",
            guild_config=cfg,
            target_language=staff_lang,
            fallback_language=staff_lang,
            assigned_name=assigned_name,
            status=current_status,
        )
        close_user = self._resolve_ticket_button_label(
            key="close",
            guild_config=cfg,
            target_language=user_lang,
            fallback_language=staff_lang,
            status=current_status,
        )
        close_staff = self._resolve_ticket_button_label(
            key="close",
            guild_config=cfg,
            target_language=staff_lang,
            fallback_language=staff_lang,
            status=current_status,
        )
        reopen_label = self._resolve_ticket_button_label(
            key="reopen",
            guild_config=cfg,
            target_language=staff_lang,
            fallback_language=staff_lang,
            status=current_status,
        )
        transcript_user = self._resolve_ticket_button_label(
            key="transcript",
            guild_config=cfg,
            target_language=user_lang,
            fallback_language=staff_lang,
            status=current_status,
        )
        transcript_staff = self._resolve_ticket_button_label(
            key="transcript",
            guild_config=cfg,
            target_language=staff_lang,
            fallback_language=staff_lang,
            status=current_status,
        )

        return {
            "take": take_label[:80],
            "close": self._combine_shared_button_label(close_user, close_staff),
            "reopen": reopen_label[:80],
            "transcript": self._combine_shared_button_label(transcript_user, transcript_staff),
        }

    def _message_render_for_language(self, msg: dict, target_lang: str | None) -> str:
        wanted = _normalize_lang(target_lang, "en") if target_lang else None
        original = (msg.get("original_content") or "").strip()
        translated = (msg.get("translated_content") or "").strip()
        original_lang = _normalize_lang(msg.get("original_language"), "") if msg.get("original_language") else None
        translated_lang = _normalize_lang(msg.get("target_language"), "") if msg.get("target_language") else None

        if wanted and translated and translated_lang == wanted:
            return translated
        if wanted and original and original_lang == wanted:
            return original
        if original:
            return original
        if translated:
            return translated
        return "[Attachment only]"

    def _build_transcript_text(self, *, ticket: dict, messages: list[dict], display_language: str | None, audience: str) -> str:
        header = [
            f"Ticket #{ticket.get('id')}",
            f"Audience: {audience}",
            f"Displayed language: {get_lang_name(display_language or 'en')}",
            f"User: {ticket.get('user_username') or ticket.get('user_id')}",
            f"Assigned staff: {ticket.get('assigned_staff_name') or 'Non assigne'}",
            f"Status: {_status_label(ticket.get('status'))}",
            "",
            "=" * 56,
            "",
        ]
        lines = header
        for msg in messages or []:
            sent_at = msg.get("sent_at")
            if isinstance(sent_at, datetime):
                ts = sent_at.strftime("%Y-%m-%d %H:%M:%S")
            else:
                ts = str(sent_at or "?")
            author = msg.get("author_username") or str(msg.get("author_id") or "?")
            content = self._message_render_for_language(msg, display_language)
            lines.append(f"[{ts}] {author}")
            lines.append(content or "—")
            try:
                attachments = json.loads(msg.get("attachments_json") or "null") if msg.get("attachments_json") else []
            except Exception:
                attachments = []
            if isinstance(attachments, list) and attachments:
                for att in attachments:
                    url = (att or {}).get("url")
                    filename = (att or {}).get("filename") or "file"
                    if url:
                        lines.append(f"Attachment: {filename} -> {url}")
            lines.append("")
        return "\n".join(lines).strip()

    def _build_transcript_file(self, *, ticket: dict, messages: list[dict], display_language: str | None, audience: str) -> discord.File:
        content = self._build_transcript_text(
            ticket=ticket,
            messages=messages,
            display_language=display_language,
            audience=audience,
        )
        filename = _build_transcript_filename(int(ticket.get("id") or 0), audience, display_language)
        return discord.File(io.BytesIO(content.encode("utf-8")), filename=filename)

    @tasks.loop(hours=24)
    async def auto_close_task(self):
        """Ferme les tickets inactifs depuis plus de 3 jours."""
        try:
            inactive = TicketModel.get_inactive_open_tickets(days=3)
            for t in inactive:
                channel = self.bot.get_channel(int(t["channel_id"]))
                if channel:
                    try:
                        # Using i18n for auto-close
                        embed = discord.Embed(
                            title=i18n.get("tickets.auto_close_title", "fr"),
                            description=i18n.get("tickets.auto_close_desc", "fr"),
                            color=discord.Color(COLOR_NOTICE)
                        )
                        await channel.send(embed=style_embed(embed))
                        # We trigger the close logic (summary, etc.)
                        # Since we don't have an interaction, we call a helper or the model directly.
                        # For simplicity, we just close it in DB and log it.
                        TicketModel.close(t["id"], transcript="Fermeture automatique (inactivité)", close_reason="Inactivité > 3 jours")
                        logger.info(f"Ticket {t['id']} fermé automatiquement (inactivité)")
                    except Exception as e:
                        logger.warning(f"Failed to auto-close channel for ticket {t['id']}: {e}")
                else:
                    # Channel already deleted? Just close in DB
                    TicketModel.close(t["id"], transcript="Fermeture automatique (canal introuvable)", close_reason="Canal introuvable")
        except Exception as e:
            logger.error(f"Erreur auto_close_task: {e}")

    @auto_close_task.before_loop
    async def before_auto_close(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        """Ferme le ticket en DB si le channel est supprimé manuellement."""
        ticket = TicketModel.get_by_channel(channel.id)
        if ticket and ticket["status"] != "closed":
            TicketModel.close(ticket["id"], transcript="Canal supprimé manuellement", close_reason="Channel supprimé")
            logger.info(f"Ticket {ticket['id']} fermé suite à suppression du canal")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Ferme les tickets ouverts si l'utilisateur quitte le serveur."""
        # Note: Optimization could be done by adding a get_open_by_user method.
        # But this is okay for now.
        try:
            # We don't have a direct model method for this, so we'll just check all open tickets for this guild
            with get_db_context() as conn:
                cursor = conn.cursor(dictionary=True)
                cursor.execute(
                    f"SELECT id, channel_id FROM {DB_TABLE_PREFIX}tickets "
                    f"WHERE guild_id = %s AND user_id = %s AND status != 'closed'",
                    (member.guild.id, member.id)
                )
                tickets = cursor.fetchall()
                for t in tickets:
                    TicketModel.close(t["id"], transcript="Utilisateur a quitté le serveur", close_reason="L'utilisateur a quitté")
                    logger.info(f"Ticket {t['id']} fermé (utilisateur {member.id} a quitté)")
                    # Optionnel: supprimer le channel si configuré? Habituellement oui.
                    chan = member.guild.get_channel(int(t["channel_id"]))
                    if chan:
                        try:
                            await chan.delete(reason="L'utilisateur a quitté le serveur")
                        except Exception:
                            pass
        except Exception as e:
            logger.error(f"Erreur on_member_remove ticket cleanup: {e}")

    def _build_ticket_welcome_embed(self, *, ticket_id: int,
                                   user_id: int | None,
                                   user_language: str | None,
                                   staff_language: str | None,
                                   guild_config: dict | None = None,
                                   priority: str | None = None,
                                   status: str | None = None,
                                   assigned_staff_name: str | None = None) -> discord.Embed:
        def fmt_lang(code: str | None, locale: str) -> str:
            if not code or code == "auto":
                return i18n.get("support.lang_auto", locale)
            # Use i18n for language names if we have them, or fallback to code
            return code.upper()

        locale = _normalize_lang(user_language or staff_language, "fr")
        ul = fmt_lang(user_language, locale)
        sl = fmt_lang(staff_language, locale)
        assigned_label = assigned_staff_name or i18n.get("tickets.not_assigned", locale)
        status_text = _status_label(status, locale)

        cfg = guild_config or {}
        variables = {
            "ticket_id": f"#{ticket_id}",
            "user_mention": f"<@{user_id}>" if user_id else "l'utilisateur",
            "user_language": ul,
            "staff_language": sl,
            "assigned_staff": assigned_label,
            "status": status_text,
        }

        legacy_template = (cfg.get("ticket_welcome_message") or "").strip()
        user_template = (
            (cfg.get("ticket_welcome_message_user") or "").strip()
            or legacy_template
            or i18n.get("tickets.default_welcome_user", locale)
        )
        staff_template = (
            (cfg.get("ticket_welcome_message_staff") or "").strip()
            or legacy_template
            or i18n.get("tickets.default_welcome_staff", locale)
        )

        embed = discord.Embed(
            title=i18n.get("tickets.welcome_title", locale),
            color=COLOR_SUCCESS,
            description=i18n.get("tickets.welcome_desc", locale),
        )
        embed.add_field(name=i18n.get("tickets.user_msg_field", locale), value=_truncate_block(_render_template(user_template, variables)), inline=False)
        embed.add_field(name=i18n.get("tickets.staff_note_field", locale), value=_truncate_block(_render_template(staff_template, variables)), inline=False)
        embed.add_field(name=i18n.get("tickets.ticket_id", locale), value=f"`{ticket_id}`", inline=True)
        embed.add_field(name=i18n.get("tickets.user_lang", locale), value=f"`{ul}`", inline=True)
        embed.add_field(name=i18n.get("tickets.staff_lang", locale), value=f"`{sl}`", inline=True)
        embed.add_field(name=i18n.get("tickets.status", locale), value=f"`{status_text}`", inline=True)
        embed.add_field(name=i18n.get("tickets.assigned_to", locale), value=f"`{assigned_label}`", inline=True)
        
        pr_raw = (priority or "medium").strip().lower()
        pr_label = i18n.get(f"tickets.priority_{pr_raw}", locale)
        embed.add_field(name=i18n.get("tickets.priority", locale), value=f"`{pr_label}`", inline=True)

        intent = (cfg.get("last_analysis") or "").strip()
        if intent:
            embed.add_field(name=i18n.get("tickets.ai_analysis", locale), value=f"*{intent}*", inline=False)

        return embed

    async def _try_update_welcome_embed(self, channel: discord.TextChannel, ticket_id: int):
        try:
            ticket = TicketModel.get(ticket_id)
            if not ticket:
                return
            msg_id = ticket.get("initial_message_id")
            if not msg_id:
                return
            try:
                welcome_msg = await channel.fetch_message(int(msg_id))
            except Exception:
                return

            guild_config = GuildModel.get(int(ticket.get("guild_id") or 0)) or {}
            embed = self._build_ticket_welcome_embed(
                ticket_id=ticket_id,
                user_id=ticket.get("user_id"),
                user_language=ticket.get("user_language"),
                staff_language=ticket.get("staff_language"),
                guild_config={**guild_config, "last_analysis": ticket.get("ai_intent")},
                priority=ticket.get("priority"),
                status=ticket.get("status"),
                assigned_staff_name=ticket.get("assigned_staff_name"),
            )
            await welcome_msg.edit(embed=style_embed(embed), view=TicketControlView(ticket_id, self.bot))
        except Exception as e:
            logger.debug(f"Update welcome embed failed for ticket {ticket_id}: {e}")

    async def _generate_ticket_summaries(self, channel: discord.TextChannel, ticket: dict, reason: str) -> tuple[str, str | None, str | None, str | None, list[dict]]:
        transcript_staff = f"Ticket fermé. Raison : {reason}"
        transcript_user = None
        user_lang = None
        staff_lang = None
        msgs = TicketMessageModel.get_by_ticket(ticket["id"])

        try:
            guild_config = GuildModel.get(int(ticket.get("guild_id") or 0)) or {}
            auto_translate = bool(guild_config.get("auto_translate", 1))

            user_lang = ticket.get("user_language") if ticket.get("user_language") not in (None, "", "auto") else None
            if not user_lang:
                user_db = UserModel.get(ticket["user_id"])
                if user_db and user_db.get("preferred_language") not in (None, "", "auto"):
                    user_lang = user_db.get("preferred_language")

            staff_lang = ticket.get("staff_language") or guild_config.get("default_language") or "en"
            if staff_lang == "auto":
                staff_lang = guild_config.get("default_language") or "en"

            last = msgs[-60:] if msgs else []
            conversation = [
                {"author": m.get("author_username") or str(m.get("author_id")), "content": m.get("original_content") or ""}
                for m in last
                if (m.get("original_content") or "").strip()
            ]
            lang_for_summary = staff_lang or user_lang or "en"
            transcript_staff = await self._run_with_typing(channel, self.groq_client.generate_ticket_summary, conversation, lang_for_summary)

            if auto_translate and user_lang and lang_for_summary and user_lang != lang_for_summary:
                transcript_user, _ = await self._run_with_typing(
                    channel, self.translator.translate_response_for_user, transcript_staff, lang_for_summary, user_lang
                )
        except Exception as e:
            logger.warning(f"Resume IA non genere: {e}")

        return transcript_staff, transcript_user, user_lang, staff_lang, msgs

    async def _post_close_outputs(
        self,
        *,
        channel: discord.TextChannel,
        ticket: dict,
        closer: discord.abc.User,
        reason: str,
        transcript_staff: str,
        transcript_user: str | None,
        user_lang: str | None,
        staff_lang: str | None,
        messages: list[dict],
    ) -> None:
        locale = _normalize_lang(staff_lang, "fr")
        pr_raw = (ticket.get("priority") or "medium").strip().lower()
        pr_label = i18n.get(f"tickets.priority_{pr_raw}", locale)
        metrics = _compute_ticket_metrics(ticket, messages)
        assigned_label = ticket.get("assigned_staff_name") or i18n.get("tickets.not_assigned", locale)

        try:
            base_embed = discord.Embed(
                title=i18n.get("tickets.summary_staff_title", locale),
                description=transcript_staff or i18n.get("tickets.summary_none", locale),
                color=discord.Color(COLOR_NOTICE),
            )
            base_embed.add_field(name=i18n.get("tickets.priority", locale), value=f"`{pr_label}`", inline=True)
            base_embed.add_field(
                name="Langues",
                value=f"User: `{user_lang or 'auto'}` · Staff: `{staff_lang or 'auto'}`",
                inline=True,
            )
            base_embed.add_field(name=i18n.get("tickets.assigned_to", locale), value=f"`{assigned_label}`", inline=True)
            await channel.send(embed=style_embed(base_embed))

            if transcript_user and user_lang and user_lang != staff_lang:
                u_locale = _normalize_lang(user_lang, locale)
                user_embed = discord.Embed(
                    title=i18n.get("tickets.summary_user_title", u_locale),
                    description=transcript_user,
                    color=discord.Color(COLOR_SUCCESS),
                )
                await channel.send(embed=style_embed(user_embed))
        except Exception as e:
            logger.debug(f"Envoi resume fermeture ignore: {e}")

        try:
            guild = self.bot.get_guild(int(ticket["guild_id"]))
            guild_config = GuildModel.get(int(ticket["guild_id"])) or {}

            try:
                user = self.bot.get_user(ticket["user_id"]) or await self.bot.fetch_user(ticket["user_id"])
                if user:
                    user_file = self._build_transcript_file(
                        ticket=ticket,
                        messages=messages,
                        display_language=user_lang or "en",
                        audience="user",
                    )
                    user_embed = discord.Embed(
                        title="Résumé de votre ticket",
                        description=transcript_user or transcript_staff or "Aucun résumé disponible.",
                        color=discord.Color(COLOR_SUCCESS),
                    )
                    user_embed.add_field(name="Assigné à", value=f"`{assigned_label}`", inline=True)
                    user_embed.add_field(
                        name="Fichier téléchargeable",
                        value=f"`{user_file.filename}`",
                        inline=False,
                    )
                    if metrics.get("avg_response"):
                        user_embed.add_field(name="Temps de réponse moyen", value=f"`{metrics['avg_response']}`", inline=True)
                    if metrics.get("open_duration"):
                        user_embed.add_field(name="Durée totale", value=f"`{metrics['open_duration']}`", inline=True)
                    user_embed.set_footer(text=f"Ticket #{ticket['id']} · {guild.name if guild else ''}")
                    await user.send(embed=style_embed(user_embed), file=user_file)
            except Exception:
                pass

            log_channel_id = _safe_int(guild_config.get("log_channel_id"))
            if log_channel_id:
                log_chan = self.bot.get_channel(log_channel_id) or await self.bot.fetch_channel(log_channel_id)
                if log_chan:
                    meta = discord.Embed(
                        title=f"Ticket Clôturé · #{ticket['id']}",
                        description=(
                            f"**Utilisateur:** <@{ticket['user_id']}> ({ticket['user_username']})\n"
                            f"**Clôturé par:** {closer.mention}\n"
                            f"**Assigné à:** {assigned_label}\n"
                            f"**Raison:** {reason}"
                        ),
                        color=discord.Color(COLOR_NOTICE),
                    )
                    meta.add_field(name="Priorité", value=f"`{pr_label}`", inline=True)
                    meta.add_field(name="Temps de réponse moyen", value=f"`{metrics.get('avg_response') or 'N/A'}`", inline=True)
                    meta.add_field(name="Durée totale", value=f"`{metrics.get('open_duration') or 'N/A'}`", inline=True)
                    if ticket.get("opened_at"):
                        meta.add_field(name="Ouvert le", value=f"<t:{int(ticket['opened_at'].timestamp())}:f>", inline=True)
                    staff_file = self._build_transcript_file(
                        ticket=ticket,
                        messages=messages,
                        display_language=staff_lang or "en",
                        audience="staff",
                    )
                    files = [staff_file]
                    file_labels = [f"`{staff_file.filename}`"]
                    summary_bits = [f"Staff ({get_lang_name(staff_lang or 'en')}): {(transcript_staff or 'Non généré').strip()}"]
                    if user_lang and user_lang != staff_lang:
                        user_file = self._build_transcript_file(
                            ticket=ticket,
                            messages=messages,
                            display_language=user_lang,
                            audience="user",
                        )
                        files.append(user_file)
                        file_labels.append(f"`{user_file.filename}`")
                        summary_bits.append(
                            f"Utilisateur ({get_lang_name(user_lang)}): {((transcript_user or transcript_staff) or 'Non généré').strip()}"
                        )

                    meta.add_field(
                        name="Fichiers téléchargeables",
                        value="\n".join(file_labels),
                        inline=False,
                    )
                    meta.add_field(
                        name="Résumés",
                        value=_truncate_block("\n\n".join(summary_bits), 1024),
                        inline=False,
                    )
                    await log_chan.send(embed=style_embed(meta), files=files)
        except Exception as e:
            logger.debug(f"Erreur logs/DMs fermeture: {e}")

    async def _finalize_ticket_close(self, *, channel: discord.TextChannel, ticket: dict, closer: discord.abc.User, reason: str) -> None:
        transcript_staff, transcript_user, user_lang, staff_lang, messages = await self._generate_ticket_summaries(channel, ticket, reason)
        TicketModel.close(ticket["id"], transcript=transcript_staff, close_reason=reason)
        ticket = TicketModel.get(ticket["id"]) or ticket
        await self._post_close_outputs(
            channel=channel,
            ticket=ticket,
            closer=closer,
            reason=reason,
            transcript_staff=transcript_staff,
            transcript_user=transcript_user,
            user_lang=user_lang,
            staff_lang=staff_lang,
            messages=messages,
        )
        await self._try_update_welcome_embed(channel, ticket["id"])

        # ── Task 2.3: Send satisfaction rating DM ──
        try:
            user = self.bot.get_user(int(ticket["user_id"])) or await self.bot.fetch_user(int(ticket["user_id"]))
            if user:
                locale = _normalize_lang(ticket.get("user_language"), "en")
                rating_embed = discord.Embed(
                    title=i18n.get("tickets.rating_title", locale),
                    description=i18n.get("tickets.rating_desc", locale),
                    color=discord.Color(COLOR_SUCCESS),
                )
                rating_embed.set_footer(text=f"Ticket #{ticket['id']}")
                view = SatisfactionView(ticket["id"], int(ticket["user_id"]), int(ticket.get("guild_id") or 0))
                await user.send(embed=style_embed(rating_embed), view=view)
        except Exception as e:
            logger.debug(f"Satisfaction DM failed for ticket {ticket['id']}: {e}")

        # ── Task 2.5: Schedule channel deletion ──
        try:
            closing_embed = discord.Embed(
                title=i18n.get("tickets.channel_closing", _normalize_lang(ticket.get("staff_language"), "en")),
                color=discord.Color(COLOR_NOTICE),
            )
            await channel.send(embed=style_embed(closing_embed))
            await asyncio.sleep(10)
            await channel.delete(reason=f"Ticket #{ticket['id']} closed")
        except Exception as e:
            logger.debug(f"Channel deletion failed for ticket {ticket['id']}: {e}")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        ticket = TicketModel.get_by_channel(message.channel.id)
        if not ticket or ticket["status"] == "closed":
            return
        text = (message.content or "").strip()
        if not text and not message.attachments:
            return

        if ticket.get("status") == "pending_close":
            restored_status = "in_progress" if ticket.get("assigned_staff_id") else "open"
            TicketModel.update(ticket["id"], status=restored_status, close_reason=None)
            ticket["status"] = restored_status
            await self._try_update_welcome_embed(message.channel, ticket["id"])

        guild_config = GuildModel.get(message.guild.id) or {}
        auto_translate = bool(guild_config.get("auto_translate", 1))

        is_ticket_user = message.author.id == ticket["user_id"]
        detected_lang = await asyncio.to_thread(self.translator.detect_language, text) if text else None

        translated_text = None
        from_cache = False
        target_language = None

        # ── User message: detect user language on first real message ───────────
        if is_ticket_user:
            ticket_user_lang = ticket.get("user_language")
            if not ticket_user_lang or ticket_user_lang == "auto":
                # Si la détection échoue, on tente de se baser sur l'historique du ticket.
                if not detected_lang:
                    detected_lang = self._dominant_language_from_history(ticket["id"], message.author.id)

                if detected_lang:
                    TicketModel.update(ticket["id"], user_language=detected_lang)
                    ticket["user_language"] = detected_lang

                    # Upsert user: keep 'auto' if explicitly set otherwise store detected.
                    user_db = UserModel.get(message.author.id)
                    if not user_db or (user_db.get("preferred_language") in (None, "", "auto")):
                        UserModel.upsert(message.author.id, message.author.name, detected_lang)
                    else:
                        UserModel.upsert(message.author.id, message.author.name, user_db.get("preferred_language"))

                    # Smart Welcome: Analyze first message intent
                    intent = self.groq_client.analyze_first_message(text, detected_lang or "fr")
                    if intent:
                        TicketModel.update(ticket["id"], ai_intent=intent)
                        ticket["ai_intent"] = intent

                    await self._try_update_welcome_embed(message.channel, ticket["id"])

            staff_lang = ticket.get("staff_language") or guild_config.get("default_language") or "en"
            if staff_lang == "auto":
                staff_lang = guild_config.get("default_language") or "en"

            # Prefer per-message detection for translation source; fall back to stored ticket language.
            user_lang = detected_lang or (ticket.get("user_language") if ticket.get("user_language") not in (None, "", "auto") else None)

            if auto_translate and user_lang and staff_lang and user_lang != staff_lang:
                try:
                    translated_text, from_cache = await self._run_with_typing(
                        message.channel, self.translator.translate_message_for_staff, message.content, user_lang, staff_lang
                    )
                    locale = _normalize_lang(staff_lang, "fr")
                    
                    embed = discord.Embed(
                        title=i18n.get("tickets.translation_title", locale, lang=user_lang),
                        description=translated_text[:3900],
                        color=discord.Color(COLOR_NOTICE if from_cache else COLOR_SUCCESS),
                        timestamp=message.created_at
                    )
                    embed.set_footer(text=strip_emojis(message.author.display_name), icon_url=message.author.display_avatar.url)
                    style_embed(embed)
                    await message.channel.send(embed=embed, reference=message, mention_author=False)
                    logger.debug(f"Traduction user->staff envoyee pour ticket {ticket['id']}")
                except Exception as e:
                    logger.error(f"Erreur traduction ticket {ticket['id']}: {e}")

            # Ticket-to-Payment: Suggest payment if intent detected
            try:
                if self.groq_client.detect_payment_intent(text):
                    locale = _normalize_lang(user_lang, "fr")
                    embed = discord.Embed(
                        title=i18n.get("payments.suggestion_title", locale),
                        description=i18n.get("payments.suggestion_desc", locale),
                        color=discord.Color(COLOR_WARNING)
                    )
                    embed.set_footer(text=i18n.get("payments.suggestion_footer", locale))
                    style_embed(embed)
                    await message.channel.send(embed=embed)
                    logger.info(f"Suggestion paiement envoyée pour ticket {ticket['id']}")
            except Exception as e:
                logger.debug(f"Payment suggestion failed for ticket {ticket['id']}: {e}")

            # AI Moderation: Alert staff if malicious content detected
            try:
                security_status = self.groq_client.detect_malicious_content(message.content)
                if security_status in ["malicious", "suspicious"]:
                    log_channel_id = guild_config.get("log_channel_id")
                    if log_channel_id:
                        log_channel = message.guild.get_channel(int(log_channel_id))
                        if log_channel:
                            color = discord.Color(COLOR_CRITICAL) if security_status == "malicious" else discord.Color(COLOR_WARNING)
                            embed = discord.Embed(
                                title=i18n.get("common.security_alert_title", "fr"),
                                description=i18n.get("common.security_alert_desc", "fr", 
                                    status=security_status,
                                    user=message.author.mention,
                                    channel=message.channel.mention,
                                    content=strip_emojis(message.content[:300])
                                ),
                                color=color
                            )
                            style_embed(embed)
                            await log_channel.send(embed=embed)
                            logger.warning(f"Alerte secu ticket ({security_status}) pour {message.author.id}")
            except Exception as e:
                logger.debug(f"AI Moderation check failed for ticket: {e}")

            # Stocker le message (et la traduction si presente)
            try:
                attachments = []
                for a in (message.attachments or []):
                    attachments.append({
                        "url": a.url,
                        "filename": a.filename,
                        "size": a.size,
                        "content_type": a.content_type,
                    })
                TicketMessageModel.create(
                    ticket_id=ticket["id"],
                    author_id=message.author.id,
                    author_username=message.author.name,
                    discord_message_id=message.id,
                    original_content=message.content,
                    translated_content=translated_text,
                    original_language=user_lang,
                    target_language=target_language,
                    from_cache=from_cache,
                    attachments_json=json.dumps(attachments, ensure_ascii=False) if attachments else None,
                )
            except Exception as e:
                logger.warning(f"DB store ticket message failed (ticket {ticket['id']}): {e}")

            # Priorisation automatique du ticket en fonction de la gravité (côté IA).
            try:
                msgs = TicketMessageModel.get_by_ticket(ticket["id"])
                last = msgs[-40:] if msgs else []
                conversation = [
                    {
                        "author": m.get("author_username") or str(m.get("author_id")),
                        "content": m.get("original_content") or "",
                    }
                    for m in last
                    if (m.get("original_content") or "").strip()
                ]
                if conversation:
                    lang_for_priority = (
                        ticket.get("user_language")
                        or detected_lang
                        or guild_config.get("default_language")
                        or "en"
                    )
                    new_priority = self.groq_client.classify_ticket_priority(conversation, lang_for_priority)
                    if new_priority and new_priority != ticket.get("priority"):
                        TicketModel.update(ticket["id"], priority=new_priority)
                        ticket["priority"] = new_priority
            except Exception as e:
                logger.debug(f"Auto-priorite ticket {ticket['id']} ignoree: {e}")

            return

        # ── Staff (or other participant) message: detect staff language if needed ──
        staff_lang = ticket.get("staff_language")
        if not staff_lang or staff_lang == "auto":
            if detected_lang:
                staff_lang = detected_lang
                TicketModel.update(ticket["id"], staff_language=staff_lang)
                ticket["staff_language"] = staff_lang
                await self._try_update_welcome_embed(message.channel, ticket["id"])
            else:
                staff_lang = guild_config.get("default_language") or "en"

        # User language might still be pending if the user hasn't typed yet.
        user_lang = ticket.get("user_language") if ticket.get("user_language") not in (None, "", "auto") else None
        if not user_lang:
            user_lang = self._dominant_language_from_history(ticket["id"], ticket.get("user_id"))
            if user_lang:
                TicketModel.update(ticket["id"], user_language=user_lang)
                ticket["user_language"] = user_lang
        if not user_lang:
            user_db = UserModel.get(ticket["user_id"])
            if user_db and user_db.get("preferred_language") not in (None, "", "auto"):
                user_lang = user_db.get("preferred_language")

        # Prefer per-message detection for translation source.
        staff_src_lang = detected_lang or staff_lang

        if auto_translate and staff_src_lang and user_lang and staff_src_lang != user_lang:
            try:
                translated_text, from_cache = await self._run_with_typing(
                    message.channel, self.translator.translate_response_for_user, message.content, staff_src_lang, user_lang
                )
                target_language = user_lang

                locale = _normalize_lang(user_lang, "fr")
                embed = discord.Embed(
                    title=i18n.get("tickets.translation_title", locale, lang=staff_src_lang),
                    description=translated_text[:3900],
                    color=discord.Color(COLOR_NOTICE if from_cache else COLOR_SUCCESS),
                )
                style_embed(embed)
                await message.channel.send(embed=embed, reference=message, mention_author=False)
                logger.debug(f"Traduction staff->user envoyee pour ticket {ticket['id']}")
            except Exception as e:
                logger.error(f"Erreur traduction ticket {ticket['id']}: {e}")

        # Stocker le message (et la traduction si presente)
        try:
            attachments = []
            for a in (message.attachments or []):
                attachments.append({
                    "url": a.url,
                    "filename": a.filename,
                    "size": a.size,
                    "content_type": a.content_type,
                })
            TicketMessageModel.create(
                ticket_id=ticket["id"],
                author_id=message.author.id,
                author_username=message.author.name,
                discord_message_id=message.id,
                original_content=message.content,
                translated_content=translated_text,
                original_language=staff_src_lang,
                target_language=target_language,
                from_cache=from_cache,
                attachments_json=json.dumps(attachments, ensure_ascii=False) if attachments else None,
            )
        except Exception as e:
            logger.warning(f"DB store ticket message failed (ticket {ticket['id']}): {e}")

    # ------------------------------------------------------------------
    # /ticket - ouvrir un ticket
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="ticket", description="Ouvrir un ticket de support")
    @discord.app_commands.describe(topic="(Optionnel) Type / sujet du ticket")
    @discord.app_commands.checks.cooldown(1, 60.0, key=lambda i: i.user.id)
    async def open_ticket(self, interaction: discord.Interaction, topic: str = ""):
        try:
            if not interaction.response.is_done():
                await interaction.response.defer(ephemeral=True)
        except Exception:
            pass

        guild_config = GuildModel.get(interaction.guild.id)
        if not guild_config:
            await send_localized_embed(
                interaction,
                "tickets.config_missing_title",
                "tickets.config_missing_desc",
                ephemeral=True
            )
            return

        # Limite tickets ouverts par utilisateur
        max_open = guild_config.get("ticket_max_open")
        try:
            max_open = int(max_open) if max_open is not None else 1
        except Exception:
            max_open = 1
        if max_open and max_open > 0:
            try:
                open_count = TicketModel.count_open_by_user(interaction.guild.id, interaction.user.id)
            except Exception:
                open_count = 0
            if open_count >= max_open:
                await send_localized_embed(
                    interaction,
                    "tickets.limit_reached_title",
                    "tickets.limit_reached_desc",
                    open_count=open_count,
                    max_open=max_open,
                    ephemeral=True
                )
                return

        category_id = _safe_int(guild_config.get("ticket_category_id"))
        if not category_id:
            await send_localized_embed(
                interaction,
                "tickets.no_category_title",
                "tickets.no_category_desc",
                ephemeral=True
            )
            return

        # The category may be missing from cache right after startup.
        category = interaction.guild.get_channel(category_id)
        if category is None:
            try:
                category = await interaction.guild.fetch_channel(category_id)
            except Exception:
                category = None
        if category is None:
            try:
                category = await self.bot.fetch_channel(category_id)
            except Exception:
                category = None

        if (
            not category
            or not isinstance(category, discord.CategoryChannel)
            or int(getattr(category.guild, "id", 0) or 0) != int(interaction.guild.id)
        ):
            await send_localized_embed(
                interaction,
                "tickets.invalid_category_title",
                "tickets.invalid_category_desc",
                ephemeral=True
            )
            return

        # Creer le channel
        topic_slug = ""
        if topic and topic.strip():
            # Keep Discord channel name safe
            topic_slug = "-" + "".join(ch for ch in topic.lower()[:12] if ch.isalnum() or ch in {"-", "_"}).strip("-")
        channel_name  = f"{TICKET_CHANNEL_PREFIX}{topic_slug}-{interaction.user.name[:16]}-{interaction.user.id}"
        ticket_channel = await interaction.guild.create_text_channel(
            channel_name,
            category=category,
            overwrites={
                interaction.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                interaction.user:               discord.PermissionOverwrite(read_messages=True),
                interaction.guild.me:           discord.PermissionOverwrite(read_messages=True),
            }
        )

        # Permissions du role staff
        staff_role_id = guild_config.get("staff_role_id")
        if staff_role_id:
            staff_role = interaction.guild.get_role(int(staff_role_id))
            if staff_role:
                await ticket_channel.set_permissions(staff_role, read_messages=True)

        # Langue: on attend le premier message de l'utilisateur pour detecter.
        # (Ne pas detecter depuis le pseudo: trop peu fiable)
        user_db = UserModel.get(interaction.user.id)
        if user_db and user_db.get("preferred_language") not in (None, "", "auto"):
            user_language = user_db.get("preferred_language")
        else:
            # Hint depuis la locale Discord (slash command), ex: fr, en-US…
            locale = getattr(interaction.user, "locale", None) or getattr(interaction.guild, "preferred_locale", None)
            code = None
            if locale:
                try:
                    code = str(locale).split("-")[0].lower()
                except Exception:
                    code = None
            user_language = code if code and len(code) == 2 else "auto"
        staff_language = guild_config.get("default_language") or "en"

        # Creer en DB avec username
        ticket_id = TicketModel.create(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            user_username=interaction.user.name,
            channel_id=ticket_channel.id,
            user_language=user_language,
            staff_language=staff_language
        )
        if not ticket_id:
            try:
                await ticket_channel.delete(reason="DB ticket create failed")
            except Exception:
                pass
            locale = _normalize_lang(str(interaction.locale), "fr")
            db_err_embed = discord.Embed(
                title=i18n.get("tickets.db_error_title", locale),
                description=i18n.get("tickets.db_error_desc", locale),
                color=discord.Color(COLOR_CRITICAL),
            )
            await interaction.followup.send(embed=style_embed(db_err_embed), ephemeral=True)
            return

        # Upsert utilisateur
        UserModel.upsert(interaction.user.id, interaction.user.name, user_language)

        # Message de bienvenue
        embed = self._build_ticket_welcome_embed(
            ticket_id=ticket_id,
            user_id=interaction.user.id,
            user_language=user_language,
            staff_language=staff_language,
            guild_config=guild_config,
            priority="medium",
            status="open",
            assigned_staff_name=None,
        )
        view = TicketControlView(ticket_id, self.bot)
        welcome_msg = await ticket_channel.send(embed=style_embed(embed), view=view)

        # Mention staff role if enabled
        try:
            if int(guild_config.get("ticket_mention_staff", 1) or 0) == 1 and staff_role_id:
                staff_role = interaction.guild.get_role(int(staff_role_id))
                if staff_role:
                    await ticket_channel.send(staff_role.mention, allowed_mentions=discord.AllowedMentions(roles=True))
        except Exception:
            pass
        try:
            TicketModel.update(ticket_id, initial_message_id=welcome_msg.id)
        except Exception:
            pass

        await send_localized_embed(
            interaction,
            "tickets.created_title",
            "tickets.created_desc",
            channel=ticket_channel.mention,
            ephemeral=True
        )
        logger.info(f"Ticket {ticket_id} cree pour {interaction.user.id} sur {interaction.guild.id}")

        # ── Task 5.5: Round-robin auto-assignment ──
        try:
            guild_plan = guild_config.get("tier", "free")
            round_robin_enabled = guild_plan in ("pro", "business") and guild_config.get("round_robin_enabled", 0) == 1
            if round_robin_enabled and staff_role_id:
                assigned_staff = self._get_round_robin_staff(interaction.guild, int(staff_role_id))
                if assigned_staff:
                    TicketModel.update(
                        ticket_id,
                        assigned_staff_id=assigned_staff.id,
                        assigned_staff_name=assigned_staff.display_name,
                        status="in_progress"
                    )
                    # Update welcome embed with assignment
                    await self._try_update_welcome_embed(ticket_channel, ticket_id)
                    # Notify in channel
                    locale = _normalize_lang(staff_language, "en")
                    assign_embed = discord.Embed(
                        title=i18n.get("tickets.auto_assigned_title", locale),
                        description=i18n.get("tickets.auto_assigned_desc", locale, name=assigned_staff.display_name),
                        color=discord.Color(COLOR_NOTICE)
                    )
                    await ticket_channel.send(embed=style_embed(assign_embed))
                    logger.info(f"Ticket {ticket_id} auto-assigned to {assigned_staff.id}")
        except Exception as e:
            logger.debug(f"Round-robin auto-assignment failed: {e}")

        # ── Task 2.2: Log channel notification on ticket open ──
        try:
            log_channel_id = _safe_int(guild_config.get("log_channel_id"))
            if log_channel_id:
                log_chan = self.bot.get_channel(log_channel_id) or await self.bot.fetch_channel(log_channel_id)
                if log_chan:
                    locale_staff = _normalize_lang(staff_language, "en")
                    log_embed = discord.Embed(
                        title=i18n.get("tickets.log_opened_title", locale_staff),
                        color=discord.Color(COLOR_SUCCESS),
                    )
                    log_embed.add_field(name=i18n.get("tickets.log_user", locale_staff), value=f"<@{interaction.user.id}> ({interaction.user.name})", inline=True)
                    log_embed.add_field(name=i18n.get("tickets.log_channel", locale_staff), value=ticket_channel.mention, inline=True)
                    log_embed.add_field(name=i18n.get("tickets.log_language", locale_staff), value=f"`{user_language or 'auto'}`", inline=True)
                    log_embed.add_field(name=i18n.get("tickets.ticket_id", locale_staff), value=f"`{ticket_id}`", inline=True)
                    await log_chan.send(embed=style_embed(log_embed))
        except Exception as e:
            logger.debug(f"Log notification on ticket open failed: {e}")

    # ------------------------------------------------------------------
    # /close - fermer le ticket courant
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="close", description="Fermer ce ticket")
    @discord.app_commands.describe(reason="Raison de la cloture (optionnel)")
    async def close_ticket(self, interaction: discord.Interaction, reason: str = "Non specifiee"):
        await interaction.response.defer(ephemeral=True)

        ticket = TicketModel.get_by_channel(interaction.channel.id)
        if not ticket:
            await send_localized_embed(interaction, "tickets.not_in_ticket", ephemeral=True)
            return

        is_user  = interaction.user.id == ticket["user_id"]
        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
        )

        if ticket["status"] == "closed":
            await send_localized_embed(interaction, "tickets.already_closed", ephemeral=True)
            return

        if not (is_user or is_staff):
            await send_localized_embed(interaction, "tickets.permission_denied", ephemeral=True)
            return
        if is_staff:
            await self._finalize_ticket_close(
                channel=interaction.channel,
                ticket=ticket,
                closer=interaction.user,
                reason=reason,
            )
            await send_localized_embed(interaction, "common.success", "tickets.close_success_desc", ephemeral=True)
            logger.info(f"Ticket {ticket['id']} fermé par {interaction.user.id}")
            return

        TicketModel.update(ticket["id"], status="pending_close", close_reason=reason)
        await self._try_update_welcome_embed(interaction.channel, ticket["id"])
        await send_localized_embed(interaction, "common.success", "tickets.close_confirm_desc", ephemeral=True)

    async def cog_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            await send_localized_embed(
                interaction, 
                "common.cooldown_title", 
                "common.cooldown_desc", 
                seconds=int(error.retry_after),
                ephemeral=True
            )
        else:
            logger.error(f"Erreur TicketCog command: {error}")


# ============================================================================
# Vue ouverture ticket (bouton / select)
# ============================================================================

class TicketOpenButtonView(discord.ui.View):
    def __init__(self, bot, *, guild_id: int, label: str, style: str, emoji: str | None = None):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = int(guild_id)

        # Map style string -> discord.ButtonStyle
        style_map = {
            "primary": discord.ButtonStyle.primary,
            "secondary": discord.ButtonStyle.secondary,
            "success": discord.ButtonStyle.success,
            "danger": discord.ButtonStyle.danger,
        }
        btn_style = style_map.get((style or "primary").lower(), discord.ButtonStyle.primary)

        self.add_item(
            discord.ui.Button(
                custom_id=f"vai:ticket_open:{self.guild_id}",
                label=strip_emojis(label or "Ouvrir un ticket")[:80],
                style=btn_style,
                emoji=None,
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Ensure the interaction is in the right guild
        return interaction.guild is not None and int(interaction.guild.id) == self.guild_id


    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        logger.warning(f"TicketOpenButtonView error: {error}")
        try:
            await send_localized_embed(interaction, "common.error", "tickets.error_open", ephemeral=True)
        except Exception:
            pass


class TicketOpenSelect(discord.ui.Select):
    def __init__(self, bot, *, guild_id: int, placeholder: str, options: list[dict]):
        self.bot = bot
        self.guild_id = int(guild_id)

        select_opts: list[discord.SelectOption] = []
        for o in (options or [])[:25]:
            try:
                select_opts.append(
                    discord.SelectOption(
                        label=strip_emojis(str(o.get("label") or "Option"))[:100],
                        value=str(o.get("value") or str(o.get("label") or "option"))[:100],
                        description=strip_emojis(str(o.get("description") or ""))[:100] or None,
                        emoji=None,
                    )
                )
            except Exception:
                continue

        super().__init__(
            custom_id=f"vai:ticket_open_select:{self.guild_id}",
            placeholder=strip_emojis(placeholder or "Sélectionnez le type de ticket")[:150],
            min_values=1,
            max_values=1,
            options=select_opts or [discord.SelectOption(label="Support", value="support")],
        )

    async def callback(self, interaction: discord.Interaction):
        topic = (self.values[0] if self.values else "")
        cog = self.bot.get_cog("TicketsCog")
        if not cog:
            return await send_localized_embed(interaction, "common.error", "tickets.cog_not_found", ephemeral=True)
        return await cog.open_ticket(interaction, topic=topic)


class TicketOpenSelectView(discord.ui.View):
    def __init__(self, bot, *, guild_id: int, placeholder: str, options: list[dict]):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild_id = int(guild_id)
        self.add_item(TicketOpenSelect(bot, guild_id=guild_id, placeholder=placeholder, options=options))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.guild is not None and int(interaction.guild.id) == self.guild_id


# ============================================================================
# Vue avec controles ticket
# ============================================================================

class TicketControlView(discord.ui.View):
    def __init__(self, ticket_id: int, bot):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.bot = bot
        self._refresh_buttons()

    def _refresh_buttons(self):
        ticket = TicketModel.get(self.ticket_id) or {}
        status = (ticket.get("status") or "open").strip().lower()
        assigned_name = (ticket.get("assigned_staff_name") or "").strip()
        guild_config = GuildModel.get(int(ticket.get("guild_id") or 0)) or {}
        cog = self.bot.get_cog("TicketsCog")
        labels = cog._ticket_control_labels(
            guild_config,
            assigned_name,
            status,
            ticket.get("user_language"),
            ticket.get("staff_language"),
        ) if cog else {
            "take": "Prendre le ticket",
            "close": "Fermer le ticket",
            "reopen": "Reouvrir",
            "transcript": "Transcript",
        }

        self.take_button.label = labels["take"]
        self.take_button.style = discord.ButtonStyle.secondary
        self.take_button.disabled = status == "closed"

        self.close_button.label = labels["close"]
        self.close_button.style = discord.ButtonStyle.danger if status == "pending_close" else discord.ButtonStyle.secondary
        self.close_button.disabled = status == "closed"

        self.reopen_button.label = labels["reopen"]
        self.reopen_button.disabled = status not in {"pending_close", "closed"}
        self.transcript_button.label = labels["transcript"]
        self.transcript_button.disabled = not bool((ticket.get("transcript") or "").strip())

    @discord.ui.button(label="S'approprier le ticket", style=discord.ButtonStyle.secondary, row=0, custom_id="vai:ticket_take")
    async def take_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket:
            await send_localized_embed(interaction, "common.error", "tickets.ticket_not_found", ephemeral=True)
            return

        if ticket.get("status") == "closed":
            await send_localized_embed(interaction, "common.error", "tickets.already_closed", ephemeral=True)
            return

        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
            or any(role.permissions.manage_channels for role in interaction.user.roles)
        )
        if not is_staff:
            await send_localized_embed(interaction, "common.error", "tickets.permission_denied", ephemeral=True)
            return

        current_owner_id = int(ticket.get("assigned_staff_id") or 0)
        if current_owner_id and current_owner_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await send_localized_embed(interaction, "common.error", "tickets.ticket_already_taken", ephemeral=True)
            return

        new_status = "in_progress"
        TicketModel.update(
            self.ticket_id,
            assigned_staff_id=interaction.user.id,
            assigned_staff_name=interaction.user.display_name,
            status=new_status,
        )
        self._refresh_buttons()
        if isinstance(interaction.channel, discord.TextChannel):
            cog = self.bot.get_cog("TicketsCog")
            if cog:
                await cog._try_update_welcome_embed(interaction.channel, self.ticket_id)
            await send_localized_embed(interaction, "common.success", "tickets.ticket_taken_success", ephemeral=True)
        else:
            await send_localized_embed(interaction, "common.success", "tickets.ticket_updated", ephemeral=True)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.secondary, row=0, custom_id="vai:ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket:
            await send_localized_embed(interaction, "common.error", "tickets.ticket_not_found", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await send_localized_embed(interaction, "common.error", "tickets.invalid_channel", ephemeral=True)
            return

        is_user = interaction.user.id == ticket["user_id"]
        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
            or int(ticket.get("assigned_staff_id") or 0) == interaction.user.id
        )
        if not (is_user or is_staff):
            await send_localized_embed(interaction, "common.error", "tickets.permission_denied", ephemeral=True)
            return

        current_status = (ticket.get("status") or "open").strip().lower()
        cog = self.bot.get_cog("TicketsCog")
        if not cog:
            await send_localized_embed(interaction, "common.error", "tickets.cog_not_found", ephemeral=True)
            return

        if current_status != "pending_close":
            TicketModel.update(self.ticket_id, status="pending_close", close_reason="Demande de fermeture via bouton")
            self._refresh_buttons()
            await cog._try_update_welcome_embed(interaction.channel, self.ticket_id)
            await send_localized_embed(interaction, "common.success", "tickets.close_confirm_desc", ephemeral=True)
            return

        if not is_staff:
            await send_localized_embed(interaction, "common.error", "tickets.only_staff_confirm", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await cog._finalize_ticket_close(
            channel=interaction.channel,
            ticket=ticket,
            closer=interaction.user,
            reason="Fermeture confirmée via bouton",
        )
        self._refresh_buttons()
        await send_localized_embed(interaction, "common.success", "tickets.close_success_desc", ephemeral=True)
        logger.info(f"Ticket {self.ticket_id} ferme via bouton par {interaction.user.id}")

    @discord.ui.button(label="Réouvrir", style=discord.ButtonStyle.success, row=1, custom_id="vai:ticket_reopen")
    async def reopen_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket:
            await send_localized_embed(interaction, "common.error", "tickets.ticket_not_found", ephemeral=True)
            return

        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
            or int(ticket.get("assigned_staff_id") or 0) == interaction.user.id
        )
        if not is_staff:
            await send_localized_embed(interaction, "common.error", "tickets.only_staff_confirm", ephemeral=True)
            return

        restored_status = "in_progress" if ticket.get("assigned_staff_id") else "open"
        TicketModel.update(
            self.ticket_id,
            status=restored_status,
            closed_at=None,
            close_reason=None,
            transcript="",
        )
        self._refresh_buttons()
        if isinstance(interaction.channel, discord.TextChannel):
            cog = self.bot.get_cog("TicketsCog")
            if cog:
                await cog._try_update_welcome_embed(interaction.channel, self.ticket_id)
        await send_localized_embed(interaction, "common.success", "tickets.reopen_success", ephemeral=True)

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.primary, row=1, custom_id="vai:ticket_transcript")
    async def transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket or not (ticket.get("transcript") or "").strip():
            await send_localized_embed(interaction, "common.error", "tickets.no_transcript", ephemeral=True)
            return

        cog = self.bot.get_cog("TicketsCog")
        messages = TicketMessageModel.get_by_ticket(self.ticket_id)
        file = None
        if cog:
            display_lang = ticket.get("staff_language") or "en"
            if interaction.user.id == int(ticket.get("user_id") or 0) and ticket.get("user_language") not in (None, "", "auto"):
                display_lang = ticket.get("user_language")
            file = cog._build_transcript_file(
                ticket=ticket,
                messages=messages,
                display_language=display_lang,
                audience="user" if interaction.user.id == int(ticket.get("user_id") or 0) else "staff",
            )
        locale = _normalize_lang(ticket.get("staff_language"), "fr")
        embed = discord.Embed(
            title=i18n.get("tickets.transcript_title", locale, id=self.ticket_id),
            description=(ticket.get("transcript") or "")[:4000],
            color=discord.Color(COLOR_NOTICE),
        )
        if not interaction.response.is_done():
            await interaction.response.send_message(embed=style_embed(embed), ephemeral=True, file=file)
        else:
            await interaction.followup.send(embed=style_embed(embed), ephemeral=True, file=file)


# ============================================================================
# Satisfaction Rating View (Task 2.3)
# ============================================================================

class SatisfactionButton(discord.ui.Button):
    def __init__(self, rating: int, ticket_id: int, user_id: int, guild_id: int):
        stars = "⭐" * rating
        super().__init__(label=stars, style=discord.ButtonStyle.secondary, custom_id=f"sat:{ticket_id}:{rating}")
        self.rating = rating
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.guild_id = guild_id

    async def callback(self, interaction: discord.Interaction):
        # Verify the user
        if interaction.user.id != self.user_id:
            locale = _normalize_lang(str(interaction.locale), "fr")
            embed = discord.Embed(
                title=i18n.get("common.error", locale),
                description=i18n.get("tickets.not_your_ticket", locale),
                color=discord.Color(COLOR_WARNING)
            )
            style_embed(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        # Save rating to DB
        from bot.db.models import TicketSatisfactionModel
        TicketSatisfactionModel.upsert(
            ticket_id=self.ticket_id,
            user_id=self.user_id,
            guild_id=self.guild_id,
            rating=self.rating
        )

        locale = _normalize_lang(str(interaction.locale), "en")
        embed = discord.Embed(
            title=i18n.get("tickets.rating_thanks", locale),
            description=i18n.get("tickets.rating_saved", locale),
            color=discord.Color(COLOR_SUCCESS)
        )
        style_embed(embed)
        # Créer une vue vide pour remplacer les boutons
        empty_view = discord.ui.View(timeout=None)
        await interaction.response.edit_message(embed=embed, view=empty_view)


class SatisfactionView(discord.ui.View):
    def __init__(self, ticket_id: int, user_id: int, guild_id: int):
        super().__init__(timeout=86400)  # 24h timeout
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.guild_id = guild_id

        # Add buttons for ratings 1-5
        for i in range(1, 6):
            self.add_item(SatisfactionButton(i, ticket_id, user_id, guild_id))


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
