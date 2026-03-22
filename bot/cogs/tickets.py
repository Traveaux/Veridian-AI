"""
Cog: Tickets - Gestion des tickets de support avec traduction en temps reel.
La configuration du systeme (category, staff role, etc.) se fait via le dashboard.
"""

import discord
from discord.ext import commands, tasks
from loguru import logger
import json

from bot.db.models import TicketModel, GuildModel, UserModel, TicketMessageModel
from bot.services.translator import TranslatorService
from bot.services.groq_client import GroqClient
from bot.config import TICKET_CHANNEL_PREFIX, BOT_OWNER_DISCORD_ID

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
        return discord.Color.blue()

    # Accept hex colors from dashboard (e.g. #4da6ff)
    if n.startswith("#") and len(n) in (4, 7):
        try:
            if len(n) == 4:
                n = "#" + "".join([c * 2 for c in n[1:]])
            return discord.Color(int(n[1:], 16))
        except Exception:
            return discord.Color.blue()

    # Backward compatible named colors
    return {
        "blue": discord.Color.blue(),
        "green": discord.Color.green(),
        "red": discord.Color.red(),
        "yellow": discord.Color.gold(),
        "purple": discord.Color.purple(),
    }.get(n, discord.Color.blue())


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
        self.auto_close_task.start()
        logger.info("Cog Tickets charge")

    def cog_unload(self):
        self.auto_close_task.cancel()

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
                            color=discord.Color.orange()
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
                                   user_language: str | None,
                                   staff_language: str | None,
                                   guild_config: dict | None = None,
                                   priority: str | None = None) -> discord.Embed:
        def fmt_lang(code: str | None, pending_label: str) -> str:
            if not code or code == "auto":
                return pending_label
            return get_lang_name(code)

        ul = fmt_lang(user_language, "Détection en cours…")
        sl = fmt_lang(staff_language, "AUTO")

        cfg = guild_config or {}
        custom_desc = (cfg.get("ticket_welcome_message") or "").strip()
        if not custom_desc:
            custom_desc = (
                "Bienvenue ! Décrivez votre problème ci-dessous.\n"
                "Le bot détectera votre langue à partir de votre premier message.\n"
                "Un membre du staff vous répondra bientôt."
            )

        embed = discord.Embed(
            title="Ticket de Support",
            color=_embed_color(cfg.get("ticket_welcome_color")),
            description=custom_desc,
        )
        embed.add_field(name="Ticket ID", value=f"`{ticket_id}`", inline=True)
        embed.add_field(name="Langue utilisateur", value=f"`{ul}`", inline=True)
        embed.add_field(name="Langue staff", value=f"`{sl}`", inline=True)
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
                user_language=ticket.get("user_language"),
                staff_language=ticket.get("staff_language"),
                guild_config={**guild_config, "last_analysis": ticket.get("ai_intent")},
                priority=ticket.get("priority"),
            )
            await welcome_msg.edit(embed=embed, view=TicketCloseView(ticket_id, self.bot))
        except Exception as e:
            logger.debug(f"Update welcome embed failed for ticket {ticket_id}: {e}")

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
                    translated_text, from_cache = self.translator.translate_message_for_staff(
                        message.content, user_lang, staff_lang
                    )
                    target_language = staff_lang

                    embed = discord.Embed(
                        description=translated_text[:4000],
                        color=discord.Color.blurple(),
                    )
                    embed.set_author(
                        name=f"Traduction · {get_lang_name(user_lang)} → {get_lang_name(staff_lang)} ({'cache' if from_cache else 'api'})"
                    )
                    await message.channel.send(embed=embed, reference=message, mention_author=False)
                    logger.debug(f"Traduction user->staff envoyee pour ticket {ticket['id']}")
                except Exception as e:
                    logger.error(f"Erreur traduction ticket {ticket['id']}: {e}")

            # Ticket-to-Payment: Suggest payment if intent detected
            try:
                if self.groq_client.detect_payment_intent(text):
                    payment_embed = discord.Embed(
                        title="💎 Veridian AI - Plans & Tarifs",
                        description=(
                            "Il semble que vous soyez intéressé par nos offres !\n\n"
                            "**✨ Plan Premium (5€/mois)**\n"
                            "- Support IA illimité\n"
                            "- Traduction automatique des tickets\n"
                            "- Résumés de tickets à la clôture\n\n"
                            "**🚀 Plan Pro (15€/mois)**\n"
                            "- Tout le Premium +\n"
                            "- Modération IA avancée\n"
                            "- Suggestions de réponses pour le staff\n\n"
                            "👉 [Consulter les offres et s'abonner](https://veridiancloud.xyz/dashboard/billing)"
                        ),
                        color=discord.Color.gold()
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
                            color = discord.Color.red() if security_status == "malicious" else discord.Color.orange()
                            alert_embed = discord.Embed(
                                title="🛡️ Sécurité IA - Ticket",
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
                translated_text, from_cache = self.translator.translate_response_for_user(
                    message.content, staff_src_lang, user_lang
                )
                target_language = user_lang

                embed = discord.Embed(
                    description=translated_text[:4000],
                    color=discord.Color.green(),
                )
                embed.set_author(
                    name=f"Traduction · {get_lang_name(staff_src_lang)} → {get_lang_name(user_lang)} ({'cache' if from_cache else 'api'})"
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
            user_language=user_language,
            staff_language=staff_language,
            guild_config=guild_config,
            priority="medium",
        )
        view = TicketCloseView(ticket_id, self.bot)
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

        # Generer le resume IA si disponible + double embed (staff + client)
        transcript_staff = f"Ticket ferme. Raison : {reason}"
        transcript_user = None
        user_lang = None
        staff_lang = None
        try:
            guild_config = GuildModel.get(int(ticket.get("guild_id") or 0)) or {}
            auto_translate = bool(guild_config.get("auto_translate", 1))

            # Langues
            user_lang = ticket.get("user_language") if ticket.get("user_language") not in (None, "", "auto") else None
            if not user_lang:
                user_db = UserModel.get(ticket["user_id"])
                if user_db and user_db.get("preferred_language") not in (None, "", "auto"):
                    user_lang = user_db.get("preferred_language")

            staff_lang = ticket.get("staff_language") or guild_config.get("default_language") or "en"
            if staff_lang == "auto":
                staff_lang = guild_config.get("default_language") or "en"

            msgs = TicketMessageModel.get_by_ticket(ticket["id"])
            # Limiter pour eviter un prompt trop long.
            last = msgs[-60:] if msgs else []
            conversation = [
                {"author": m.get("author_username") or str(m.get("author_id")), "content": m.get("original_content") or ""}
                for m in last
            ]
            lang_for_summary = staff_lang or user_lang or "en"
            transcript_staff = self.groq_client.generate_ticket_summary(conversation, lang_for_summary)

            if auto_translate and user_lang and lang_for_summary and user_lang != lang_for_summary:
                try:
                    transcript_user, _ = self.translator.translate_response_for_user(
                        transcript_staff, lang_for_summary, user_lang
                    )
                except Exception:
                    transcript_user = None
        except Exception as e:
            logger.warning(f"Resume IA non genere: {e}")

        TicketModel.close(ticket["id"], transcript=transcript_staff, close_reason=reason)

        # Envoyer un resume dans le channel (staff + éventuellement client)
        try:
            pr_raw = (ticket.get("priority") or "medium").strip().lower()
            pr_label = {
                "low": "Bas",
                "medium": "Moyen",
                "high": "Haut",
                "urgent": "Prioritaire",
            }.get(pr_raw, pr_raw or "Moyen")

            base_embed = discord.Embed(
                title="Résumé du ticket (staff)",
                description=transcript_staff or "Aucun résumé généré.",
                color=discord.Color.greyple(),
            )
            base_embed.add_field(name="Priorité", value=f"`{pr_label}`", inline=True)
            base_embed.add_field(
                name="Langues",
                value=f"User: `{get_lang_name(user_lang or 'auto')}` · Staff: `{get_lang_name(staff_lang or 'en')}`",
                inline=True,
            )
            await interaction.channel.send(embed=base_embed)

            if transcript_user and user_lang and user_lang != staff_lang:
                user_embed = discord.Embed(
                    title="Résumé du ticket (client)",
                    description=transcript_user,
                    color=discord.Color.blurple(),
                )
                await interaction.channel.send(embed=user_embed)
        except Exception as e:
            logger.debug(f"Envoi resume fermeture commande ignore: {e}")

        # Envoyer la transcription en DM / Salon de logs
        try:
            guild = self.bot.get_guild(int(ticket["guild_id"]))
            guild_config = GuildModel.get(int(ticket["guild_id"])) or {}
            
            # 1. DM au client
            try:
                user = self.bot.get_user(ticket["user_id"]) or await self.bot.fetch_user(ticket["user_id"])
                if user:
                    user_embed = discord.Embed(
                        title="Résumé de votre ticket",
                        description=transcript_user or transcript_staff or "Aucun résumé disponible.",
                        color=discord.Color.blue()
                    )
                    user_embed.set_footer(text=f"Ticket #{ticket['id']} · {guild.name if guild else ''}")
                    await user.send(embed=user_embed)
            except Exception:
                pass

            # 2. Log Channel (Staff)
            log_channel_id = _safe_int(guild_config.get("log_channel_id"))
            if log_channel_id:
                log_chan = self.bot.get_channel(log_channel_id) or await self.bot.fetch_channel(log_channel_id)
                if log_chan:
                    log_embed = discord.Embed(
                        title=f"Ticket Clôturé · #{ticket['id']}",
                        description=f"**Utilisateur:** <@{ticket['user_id']}> ({ticket['user_username']})\n**Raison:** {reason}\n\n**Résumé IA:**\n{transcript_staff or 'Non généré'}",
                        color=discord.Color.dark_grey()
                    )
                    log_embed.add_field(name="Priorité", value=f"`{pr_label}`", inline=True)
                    log_embed.add_field(name="Ouvert le", value=f"<t:{int(ticket['opened_at'].timestamp())}:f>", inline=True)
                    await log_chan.send(embed=log_embed)

        except Exception as e:
            logger.debug(f"Erreur logs/DMs fermeture: {e}")

        await interaction.followup.send(
            "Ticket fermé. Résumé envoyé.", ephemeral=True
        )
        logger.info(f"Ticket {ticket['id']} fermé par {interaction.user.id}")

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
# Vue avec bouton Fermer
# ============================================================================

class TicketCloseView(discord.ui.View):
    def __init__(self, ticket_id: int, bot):
        super().__init__(timeout=None)
        self.ticket_id = ticket_id
        self.bot       = bot
        self.translator = TranslatorService()
        self.groq_client = GroqClient()

    @discord.ui.button(label="Fermer le ticket", style=discord.ButtonStyle.danger)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        ticket = TicketModel.get(self.ticket_id)
        if not ticket:
            await interaction.response.send_message("Ticket introuvable.", ephemeral=True)
            return

        if ticket["status"] == "closed":
            await interaction.response.send_message("Ce ticket est déjà fermé.", ephemeral=True)
            return

        is_user  = interaction.user.id == ticket["user_id"]
        is_staff = interaction.user.guild_permissions.administrator
        if not (is_user or is_staff):
            await interaction.response.send_message("Permission refusee.", ephemeral=True)
            return

        # Résumé IA + priorite + double embed (staff + client) best-effort
        summary_staff = ""
        summary_user = None
        user_lang = None
        staff_lang = None
        try:
            guild_config = GuildModel.get(int(ticket.get("guild_id") or 0)) or {}
            auto_translate = bool(guild_config.get("auto_translate", 1))

            # Langues
            user_lang = ticket.get("user_language") if ticket.get("user_language") not in (None, "", "auto") else None
            if not user_lang:
                user_db = UserModel.get(ticket.get("user_id"))
                if user_db and user_db.get("preferred_language") not in (None, "", "auto"):
                    user_lang = user_db.get("preferred_language")

            staff_lang = ticket.get("staff_language") or guild_config.get("default_language") or "en"
            if staff_lang == "auto":
                staff_lang = guild_config.get("default_language") or "en"

            msgs = TicketMessageModel.get_by_ticket(self.ticket_id)
            last = msgs[-60:] if msgs else []
            conversation = [
                {"author": m.get("author_username") or str(m.get("author_id")), "content": m.get("original_content") or ""}
                for m in last
                if (m.get("original_content") or "").strip()
            ]
            lang_for_summary = staff_lang or user_lang or "en"
            summary_staff = self.groq_client.generate_ticket_summary(conversation, lang_for_summary)

            if auto_translate and user_lang and lang_for_summary and user_lang != lang_for_summary:
                try:
                    summary_user, _ = self.translator.translate_response_for_user(
                        summary_staff, lang_for_summary, user_lang
                    )
                except Exception:
                    summary_user = None
        except Exception as e:
            logger.warning(f"Resume IA bouton non genere: {e}")
            summary_staff = ""
            summary_user = None

        TicketModel.close(self.ticket_id, transcript=summary_staff, close_reason="Ferme via bouton")

        # Envoyer les embeds de resume dans le channel
        try:
            pr_raw = (ticket.get("priority") or "medium").strip().lower()
            pr_label = {
                "low": "Bas",
                "medium": "Moyen",
                "high": "Haut",
                "urgent": "Prioritaire",
            }.get(pr_raw, pr_raw or "Moyen")

            base_embed = discord.Embed(
                title="Résumé du ticket (staff)",
                description=summary_staff or "Aucun résumé généré.",
                color=discord.Color.greyple(),
            )
            base_embed.add_field(name="Priorité", value=f"`{pr_label}`", inline=True)
            base_embed.add_field(
                name="Langues",
                value=f"User: `{get_lang_name(user_lang or 'auto')}` · Staff: `{get_lang_name(staff_lang or 'en')}`",
                inline=True,
            )
            channel = interaction.channel
            if isinstance(channel, discord.TextChannel):
                await channel.send(embed=base_embed)

                if summary_user and user_lang and user_lang != staff_lang:
                    user_embed = discord.Embed(
                        title="Résumé du ticket (client)",
                        description=summary_user,
                        color=discord.Color.blurple(),
                    )
                    await channel.send(embed=user_embed)
        except Exception as e:
            logger.debug(f"Envoi resume fermeture bouton ignore: {e}")
        button.disabled = True
        await interaction.response.edit_message(
            content="Ticket ferme.", view=self
        )
        logger.info(f"Ticket {self.ticket_id} ferme via bouton par {interaction.user.id}")


async def setup(bot):
    await bot.add_cog(TicketsCog(bot))
