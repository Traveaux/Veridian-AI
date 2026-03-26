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

from bot.db.models import TicketModel, GuildModel, UserModel, TicketMessageModel
from bot.db.connection import get_db_context
from bot.config import DB_TABLE_PREFIX
from bot.services.translator import TranslatorService
from bot.services.groq_client import GroqClient
from bot.config import TICKET_CHANNEL_PREFIX, BOT_OWNER_DISCORD_ID
from bot.config import COLOR_SUCCESS, COLOR_NOTICE, COLOR_WARNING, COLOR_CRITICAL
from bot.config import EMOJI_AI_API, EMOJI_AI_CACHE, EMOJI_URL_TICKET

LANGUAGE_NAMES = {
    "fr": "Français", "en": "Anglais", "es": "Espagnol", 
    "de": "Allemand", "it": "Italien", "pt": "Portugais", 
    "nl": "Néerlandais", "ru": "Russe", "zh": "Chinois", 
    "ja": "Japonais", "ar": "Arabe", "auto": "Auto"
}

def get_lang_name(code: str | None) -> str:
    if not code or code.lower() == "auto":
        return code if code else "auto"
    return LANGUAGE_NAMES.get(code.lower(), code.upper())


def _safe_int(v):
    try:
        if v is None:
            return None
        return int(str(v).replace("#", "").replace("@", "").strip())
    except Exception:
        return None


def _parse_json(raw, default):
    try:
        if raw is None:
            return default
        if isinstance(raw, (dict, list)):
            return raw
        s = str(raw).strip()
        if not s:
            return default
        return json.loads(s)
    except Exception:
        return default


def _embed_color(raw: str | None) -> discord.Color:
    n = (raw or "").strip().lower()
    if not n:
        return discord.Color(COLOR_SUCCESS)

    # Accept hex colors from dashboard (e.g. #4da6ff)
    if n.startswith("#") and len(n) in (4, 7):
        try:
            if len(n) == 4:
                n = "#" + "".join([c * 2 for c in n[1:]])
            return discord.Color(int(n[1:], 16))
        except Exception:
            return discord.Color(COLOR_SUCCESS)

    # Nuanced Veridian colors
    return {
        "blue": discord.Color(COLOR_SUCCESS),   # Now green for theme consistency
        "green": discord.Color(COLOR_SUCCESS),
        "red": discord.Color(COLOR_CRITICAL),
        "yellow": discord.Color(COLOR_WARNING),
        "purple": discord.Color(COLOR_NOTICE),
        "success": discord.Color(COLOR_SUCCESS),
        "notice": discord.Color(COLOR_NOTICE),
        "warning": discord.Color(COLOR_WARNING),
        "critical": discord.Color(COLOR_CRITICAL),
    }.get(n, discord.Color(COLOR_SUCCESS))


WELCOME_TEXTS = {
    "en": {
        "user": "Hello {user_mention}, describe your issue below. We will translate the conversation and get back to you shortly.",
        "staff": "Staff note: reply in {staff_language}. Current owner: {assigned_staff}.",
    },
    "fr": {
        "user": "Bonjour {user_mention}, décrivez votre problème ci-dessous. Nous traduirons l'échange et le staff reviendra vers vous rapidement.",
        "staff": "Note staff : répondez en {staff_language}. Ticket actuellement pris par : {assigned_staff}.",
    },
    "es": {
        "user": "Hola {user_mention}, describe tu problema abajo. Traduciremos la conversación y el staff responderá pronto.",
        "staff": "Nota para el staff: responded en {staff_language}. Ticket asignado a: {assigned_staff}.",
    },
    "de": {
        "user": "Hallo {user_mention}, beschreibe dein Problem unten. Wir übersetzen den Verlauf und das Team antwortet dir bald.",
        "staff": "Hinweis fürs Team: Antwortet auf {staff_language}. Aktuell zugewiesen an: {assigned_staff}.",
    },
    "it": {
        "user": "Ciao {user_mention}, descrivi il tuo problema qui sotto. Tradurremo la conversazione e lo staff ti risponderà presto.",
        "staff": "Nota staff: rispondere in {staff_language}. Ticket assegnato a: {assigned_staff}.",
    },
    "pt": {
        "user": "Olá {user_mention}, descreva o seu problema abaixo. Vamos traduzir a conversa e a equipa responderá em breve.",
        "staff": "Nota da equipa: responder em {staff_language}. Ticket atribuído a: {assigned_staff}.",
    },
}

TICKET_BUTTON_TEXTS = {
    "take": {
        "en": "Take ticket",
        "fr": "Prendre le ticket",
        "es": "Tomar el ticket",
        "de": "Ticket ubernehmen",
        "it": "Prendi il ticket",
        "pt": "Assumir ticket",
    },
    "taken_by": {
        "en": "Taken by {name}",
        "fr": "Pris par {name}",
        "es": "Tomado por {name}",
        "de": "Ubernommen von {name}",
        "it": "Preso da {name}",
        "pt": "Assumido por {name}",
    },
    "close": {
        "en": "Close ticket",
        "fr": "Fermer le ticket",
        "es": "Cerrar ticket",
        "de": "Ticket schliessen",
        "it": "Chiudi ticket",
        "pt": "Fechar ticket",
    },
    "confirm_close": {
        "en": "Confirm close",
        "fr": "Confirmer la fermeture",
        "es": "Confirmar cierre",
        "de": "Schliessung bestatigen",
        "it": "Conferma chiusura",
        "pt": "Confirmar fecho",
    },
    "reopen": {
        "en": "Reopen",
        "fr": "Reouvrir",
        "es": "Reabrir",
        "de": "Wieder offnen",
        "it": "Riapri",
        "pt": "Reabrir",
    },
    "transcript": {
        "en": "Transcript",
        "fr": "Transcript",
        "es": "Transcripcion",
        "de": "Transkript",
        "it": "Trascrizione",
        "pt": "Transcricao",
    },
}


def _normalize_lang(code: str | None, fallback: str = "en") -> str:
    raw = (code or "").strip().lower()
    if not raw or raw == "auto":
        return fallback
    return raw[:2]


def _status_label(status: str | None) -> str:
    return {
        "open": "Ouvert",
        "in_progress": "En cours",
        "pending_close": "En attente de clôture",
        "closed": "Fermé",
    }.get((status or "open").strip().lower(), status or "Ouvert")


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
                # Cooldown check for button interactions (manual)
                # 1 ticket every 60s per user
                bucket = self.open_ticket.get_cooldown_retry_after(interaction)
                if bucket:
                    return await interaction.response.send_message(
                        f"Veuillez patienter {int(bucket)}s avant d'ouvrir un autre ticket.",
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
        logger.info("Cog Tickets charge")

    def cog_unload(self):
        self.auto_close_task.cancel()

    async def _run_with_typing(self, channel: discord.abc.Messageable, func, *args):
        async with channel.typing():
            return await asyncio.to_thread(func, *args)

    def _default_button_text(self, key: str, language: str, **variables) -> str:
        lang = _normalize_lang(language, "en")
        template = TICKET_BUTTON_TEXTS.get(key, {}).get(lang) or TICKET_BUTTON_TEXTS.get(key, {}).get("en") or key
        return _render_template(template, variables)

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
                        embed = discord.Embed(
                            title="Ticket fermé automatiquement",
                            description="Ce ticket a été fermé car il était inactif depuis plus de 3 jours.",
                            color=discord.Color(COLOR_NOTICE)
                        )
                        await channel.send(embed=embed)
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
        def fmt_lang(code: str | None, pending_label: str) -> str:
            if not code or code == "auto":
                return pending_label
            return get_lang_name(code)

        ul = fmt_lang(user_language, "English")
        sl = fmt_lang(staff_language, "English")
        assigned_label = assigned_staff_name or "Non assigné"
        status_text = _status_label(status)

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
            or WELCOME_TEXTS.get(_normalize_lang(user_language), WELCOME_TEXTS["en"])["user"]
        )
        staff_template = (
            (cfg.get("ticket_welcome_message_staff") or "").strip()
            or legacy_template
            or WELCOME_TEXTS.get(_normalize_lang(staff_language), WELCOME_TEXTS["en"])["staff"]
        )

        embed = discord.Embed(
            title="Ticket de Support",
            color=_embed_color(cfg.get("ticket_welcome_color")),
            description=(
                f"[ticket.gif]({EMOJI_URL_TICKET})\n\n"
                "Le ticket est prêt. Utilisez les boutons ci-dessous pour l’assignation, la transcription et la clôture."
            ),
        )
        embed.add_field(name="Message utilisateur", value=_truncate_block(_render_template(user_template, variables)), inline=False)
        embed.add_field(name="Note staff", value=_truncate_block(_render_template(staff_template, variables)), inline=False)
        embed.add_field(name="Ticket ID", value=f"`{ticket_id}`", inline=True)
        embed.add_field(name="Langue utilisateur", value=f"`{ul}`", inline=True)
        embed.add_field(name="Langue staff", value=f"`{sl}`", inline=True)
        embed.add_field(name="Statut", value=f"`{status_text}`", inline=True)
        embed.add_field(name="Assigné à", value=f"`{assigned_label}`", inline=True)
        # Priorité du ticket (bas / moyen / haut / prioritaire)
        pr_raw = (priority or "medium").strip().lower()
        pr_label = {
            "low": "Bas",
            "medium": "Moyen",
            "high": "Haut",
            "urgent": "Prioritaire",
        }.get(pr_raw, pr_raw or "Moyen")
        embed.add_field(name="Priorité", value=f"`{pr_label}`", inline=True)

        # Smart Analysis (Intent)
        intent = (cfg.get("last_analysis") or "").strip()
        if intent:
            embed.add_field(name="Analyse IA", value=f"*{intent}*", inline=False)

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
            await welcome_msg.edit(embed=embed, view=TicketControlView(ticket_id, self.bot))
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
        pr_raw = (ticket.get("priority") or "medium").strip().lower()
        pr_label = {
            "low": "Bas",
            "medium": "Moyen",
            "high": "Haut",
            "urgent": "Prioritaire",
        }.get(pr_raw, pr_raw or "Moyen")
        metrics = _compute_ticket_metrics(ticket, messages)
        assigned_label = ticket.get("assigned_staff_name") or "Non assigné"

        try:
            base_embed = discord.Embed(
                title="Résumé du ticket (staff)",
                description=transcript_staff or "Aucun résumé généré.",
                color=discord.Color(COLOR_NOTICE),
            )
            base_embed.add_field(name="Priorité", value=f"`{pr_label}`", inline=True)
            base_embed.add_field(
                name="Langues",
                value=f"User: `{get_lang_name(user_lang or 'en')}` · Staff: `{get_lang_name(staff_lang or 'en')}`",
                inline=True,
            )
            base_embed.add_field(name="Assigné à", value=f"`{assigned_label}`", inline=True)
            await channel.send(embed=base_embed)

            if transcript_user and user_lang and user_lang != staff_lang:
                user_embed = discord.Embed(
                    title="Résumé du ticket (client)",
                    description=transcript_user,
                    color=discord.Color(COLOR_SUCCESS),
                )
                await channel.send(embed=user_embed)
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
                    await user.send(embed=user_embed, file=user_file)
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
                    await log_chan.send(embed=meta, files=files)
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
        detected_lang = self.translator.detect_language(text) if text else None

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
                    target_language = staff_lang

                    embed = discord.Embed(
                        title="Traduction automatique dans la langue de l'utilisateur",
                        description=(
                            f"staff : {EMOJI_AI_CACHE if from_cache else EMOJI_AI_API} Traduction · "
                            f"{get_lang_name(user_lang)} → {get_lang_name(staff_lang)} · "
                            f"{'backend (cache)' if from_cache else 'api'}\n\n"
                            f"{translated_text[:3900]}"
                        ),
                        color=discord.Color(COLOR_NOTICE if from_cache else COLOR_SUCCESS),
                    )
                    await message.channel.send(embed=embed, reference=message, mention_author=False)
                    logger.debug(f"Traduction user->staff envoyee pour ticket {ticket['id']}")
                except Exception as e:
                    logger.error(f"Erreur traduction ticket {ticket['id']}: {e}")

            # Ticket-to-Payment: Suggest payment if intent detected
            try:
                if self.groq_client.detect_payment_intent(text):
                    payment_embed = discord.Embed(
                        title="Veridian AI - Plans & Tarifs",
                        description=(
                            f"[ticket.gif]({EMOJI_URL_TICKET})\n\n"
                            "Il semble que vous soyez intéressé par nos offres !\n\n"
                            "**Plan Premium (5€/mois)**\n"
                            "- Support IA illimité\n"
                            "- Traduction automatique des tickets\n"
                            "- Résumés de tickets à la clôture\n\n"
                            "**Plan Pro (15€/mois)**\n"
                            "- Tout le Premium +\n"
                            "- Modération IA avancée\n"
                            "- Suggestions de réponses pour le staff\n\n"
                            "[Consulter les offres et s'abonner](https://veridiancloud.xyz/dashboard/billing)"
                        ),
                        color=discord.Color(COLOR_WARNING)
                    )
                    payment_embed.set_footer(text="Paiement sécurisé via Carte ou Crypto (OxaPay)")
                    await message.channel.send(embed=payment_embed)
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
                            alert_embed = discord.Embed(
                                title="Sécurité IA - Ticket",
                                description=(
                                    f"Détection **{security_status}** dans un ticket.\n\n"
                                    f"**Utilisateur:** {message.author.mention} (`{message.author.id}`)\n"
                                    f"**Ticket:** {message.channel.mention}\n"
                                    f"**Contenu:** {message.content[:300]}..."
                                ),
                                color=color
                            )
                            await log_channel.send(embed=alert_embed)
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

                embed = discord.Embed(
                    title="Traduction automatique dans la langue de l'utilisateur",
                    description=(
                        f"utilisateur : {EMOJI_AI_CACHE if from_cache else EMOJI_AI_API} Traduction · "
                        f"{get_lang_name(staff_src_lang)} → {get_lang_name(user_lang)} · "
                        f"{'backend (cache)' if from_cache else 'api'}\n\n"
                        f"{translated_text[:3900]}"
                    ),
                    color=discord.Color(COLOR_NOTICE if from_cache else COLOR_SUCCESS),
                )
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
            await interaction.followup.send(
                "Le bot n'est pas encore configure sur ce serveur. "
                "Demandez a un administrateur de le configurer via le panel : "
                "https://veridiancloud.xyz/dashboard",
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
                await interaction.followup.send(
                    f"Vous avez déjà {open_count} ticket(s) ouvert(s). Limite: {max_open}.",
                    ephemeral=True,
                )
                return

        category_id = _safe_int(guild_config.get("ticket_category_id"))
        if not category_id:
            await interaction.followup.send(
                "La categorie des tickets n'est pas configuree. "
                "Configurez-la sur https://veridiancloud.xyz/dashboard",
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
            await interaction.followup.send(
                "Categorie des tickets introuvable (ID invalide ou pas une categorie). "
                "Verifiez la configuration sur le panel.",
                ephemeral=True,
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
            await interaction.followup.send(
                "Erreur: impossible de créer le ticket en base de données. Réessayez plus tard.",
                ephemeral=True,
            )
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
        welcome_msg = await ticket_channel.send(embed=embed, view=view)

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

        await interaction.followup.send(
            f"Ticket cree : {ticket_channel.mention}", ephemeral=True
        )
        logger.info(f"Ticket {ticket_id} cree pour {interaction.user.id} sur {interaction.guild.id}")

    # ------------------------------------------------------------------
    # /close - fermer le ticket courant
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="close", description="Fermer ce ticket")
    @discord.app_commands.describe(reason="Raison de la cloture (optionnel)")
    async def close_ticket(self, interaction: discord.Interaction, reason: str = "Non specifiee"):
        await interaction.response.defer(ephemeral=True)

        ticket = TicketModel.get_by_channel(interaction.channel.id)
        if not ticket:
            await interaction.followup.send(
                "Cette commande est reservee aux channels de tickets.", ephemeral=True
            )
            return

        is_user  = interaction.user.id == ticket["user_id"]
        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
        )

        if ticket["status"] == "closed":
            await interaction.followup.send("Ce ticket est déjà fermé.", ephemeral=True)
            return

        if not (is_user or is_staff):
            await interaction.followup.send("Permission refusee.", ephemeral=True)
            return
        if is_staff:
            await self._finalize_ticket_close(
                channel=interaction.channel,
                ticket=ticket,
                closer=interaction.user,
                reason=reason,
            )
            await interaction.followup.send("Ticket fermé. Résumé et transcription envoyés.", ephemeral=True)
            logger.info(f"Ticket {ticket['id']} fermé par {interaction.user.id}")
            return

        TicketModel.update(ticket["id"], status="pending_close", close_reason=reason)
        await self._try_update_welcome_embed(interaction.channel, ticket["id"])
        await interaction.followup.send(
            "Demande de fermeture enregistrée. Un staff/admin doit confirmer.", ephemeral=True
        )

    async def cog_app_command_error(self, interaction: discord.Interaction, error: discord.app_commands.AppCommandError):
        if isinstance(error, discord.app_commands.CommandOnCooldown):
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    f"Veuillez patienter {int(error.retry_after)}s avant de réutiliser cette commande.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Veuillez patienter {int(error.retry_after)}s avant de réutiliser cette commande.",
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
                label=(label or "Ouvrir un ticket")[:80],
                style=btn_style,
                emoji=(emoji or None),
            )
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        # Ensure the interaction is in the right guild
        return interaction.guild is not None and int(interaction.guild.id) == self.guild_id


    async def on_error(self, interaction: discord.Interaction, error: Exception, item):
        logger.warning(f"TicketOpenButtonView error: {error}")
        try:
            if interaction.response.is_done():
                await interaction.followup.send("Erreur ouverture ticket.", ephemeral=True)
            else:
                await interaction.response.send_message("Erreur ouverture ticket.", ephemeral=True)
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
                        label=str(o.get("label") or "Option")[:100],
                        value=str(o.get("value") or str(o.get("label") or "option"))[:100],
                        description=(str(o.get("description") or "")[:100] or None),
                        emoji=(o.get("emoji") or None),
                    )
                )
            except Exception:
                continue

        super().__init__(
            custom_id=f"vai:ticket_open_select:{self.guild_id}",
            placeholder=(placeholder or "Sélectionnez le type de ticket")[:150],
            min_values=1,
            max_values=1,
            options=select_opts or [discord.SelectOption(label="Support", value="support")],
        )

    async def callback(self, interaction: discord.Interaction):
        topic = (self.values[0] if self.values else "")
        cog = self.bot.get_cog("TicketsCog")
        if not cog:
            return await interaction.response.send_message("Tickets: cog introuvable.", ephemeral=True)
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
            await interaction.response.send_message("Ticket introuvable.", ephemeral=True)
            return

        if ticket.get("status") == "closed":
            await interaction.response.send_message("Le ticket est déjà fermé.", ephemeral=True)
            return

        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
            or any(role.permissions.manage_channels for role in interaction.user.roles)
        )
        if not is_staff:
            await interaction.response.send_message("Permission refusee.", ephemeral=True)
            return

        current_owner_id = int(ticket.get("assigned_staff_id") or 0)
        if current_owner_id and current_owner_id != interaction.user.id and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("Ce ticket est déjà pris en charge par un autre membre du staff.", ephemeral=True)
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
            await interaction.response.send_message("Ticket pris en charge.", ephemeral=True)
        else:
            await interaction.response.send_message("Ticket mis à jour.", ephemeral=True)

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.secondary, row=0, custom_id="vai:ticket_close")
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("Ticket introuvable.", ephemeral=True)
            return

        if not isinstance(interaction.channel, discord.TextChannel):
            await interaction.response.send_message("Canal de ticket invalide.", ephemeral=True)
            return

        is_user = interaction.user.id == ticket["user_id"]
        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
            or int(ticket.get("assigned_staff_id") or 0) == interaction.user.id
        )
        if not (is_user or is_staff):
            await interaction.response.send_message("Permission refusee.", ephemeral=True)
            return

        current_status = (ticket.get("status") or "open").strip().lower()
        cog = self.bot.get_cog("TicketsCog")
        if not cog:
            await interaction.response.send_message("Cog tickets introuvable.", ephemeral=True)
            return

        if current_status != "pending_close":
            TicketModel.update(self.ticket_id, status="pending_close", close_reason="Demande de fermeture via bouton")
            self._refresh_buttons()
            await cog._try_update_welcome_embed(interaction.channel, self.ticket_id)
            await interaction.response.send_message(
                "Demande de fermeture enregistrée. Un staff/admin doit confirmer.", ephemeral=True
            )
            return

        if not is_staff:
            await interaction.response.send_message("Seul le staff/admin peut confirmer la fermeture.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        await cog._finalize_ticket_close(
            channel=interaction.channel,
            ticket=ticket,
            closer=interaction.user,
            reason="Fermeture confirmée via bouton",
        )
        self._refresh_buttons()
        await interaction.followup.send("Ticket fermé. Transcription envoyée.", ephemeral=True)
        logger.info(f"Ticket {self.ticket_id} ferme via bouton par {interaction.user.id}")

    @discord.ui.button(label="Réouvrir", style=discord.ButtonStyle.success, row=1, custom_id="vai:ticket_reopen")
    async def reopen_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("Ticket introuvable.", ephemeral=True)
            return

        is_staff = (
            interaction.user.guild_permissions.administrator
            or interaction.user.id == BOT_OWNER_DISCORD_ID
            or int(ticket.get("assigned_staff_id") or 0) == interaction.user.id
        )
        if not is_staff:
            await interaction.response.send_message("Seul le staff/admin peut réouvrir le ticket.", ephemeral=True)
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
        await interaction.response.send_message("Ticket réouvert.", ephemeral=True)

    @discord.ui.button(label="Transcript", style=discord.ButtonStyle.primary, row=1, custom_id="vai:ticket_transcript")
    async def transcript_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket or not (ticket.get("transcript") or "").strip():
            await interaction.response.send_message("Aucune transcription disponible pour le moment.", ephemeral=True)
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
        embed = discord.Embed(
            title=f"Transcript · Ticket #{self.ticket_id}",
            description=(ticket.get("transcript") or "")[:4000],
            color=discord.Color(COLOR_NOTICE),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True, file=file)


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
