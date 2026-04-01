"""
Cog: Support Public IA - Repond automatiquement dans les channels designes.
Les commandes de configuration sont gerees via le dashboard.
"""

import discord
from discord.ext import commands
from loguru import logger
from bot.db.models import GuildModel, SubscriptionModel, TicketModel, UserModel
from bot.services.groq_client import GroqClient
from bot.services.translator import TranslatorService
from bot.config import MIN_MESSAGE_LENGTH, PLAN_LIMITS, DASHBOARD_URL
from bot.billing import normalize_plan, get_plan_label
from bot.config import COLOR_SUCCESS, COLOR_NOTICE, COLOR_WARNING, COLOR_CRITICAL
from bot.utils.embed_style import style_embed, send_localized_embed, strip_emojis, _normalize_lang
from bot.utils.i18n import i18n

# LANGUAGE_NAMES removed - using i18n or dynamic names


class SupportCog(commands.Cog):
    """Support public IA dans les channels designes."""

    def __init__(self, bot):
        self.bot         = bot
        self.groq_client = GroqClient()
        self.translator  = TranslatorService()
        # Rate limit: 1 reponse IA toutes les 30s par salon (pour eviter le spam API)
        self._cd = commands.CooldownMapping.from_cooldown(1, 30.0, commands.BucketType.channel)
        logger.info("Cog Support Public charge")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        guild_config = GuildModel.get(message.guild.id)
        if not guild_config:
            return

        # Normaliser les types venant de la DB (souvent int, parfois str selon driver/migrations)
        try:
            support_channel_id = int(guild_config.get("support_channel_id") or 0)
        except Exception:
            support_channel_id = 0

        try:
            public_support_enabled = int(guild_config.get("public_support", 1) or 0) == 1
        except Exception:
            public_support_enabled = bool(guild_config.get("public_support", 1))

        if not support_channel_id or not public_support_enabled:
            return

        if message.channel.id != support_channel_id:
            return

        if len(message.content.split()) < MIN_MESSAGE_LENGTH:
            return

        # Check rate limit
        retry_after = self._cd.update_rate_limit(message)
        if retry_after:
            return

        async with message.channel.typing():
            try:
                language = self.translator.detect_language(message.content) or "en"
                # Utiliser le prompt personnalise si active
                custom_prompt = None
                if guild_config.get("ai_prompt_enabled") and guild_config.get("ai_custom_prompt"):
                    custom_prompt = guild_config["ai_custom_prompt"]
                
                response = self.groq_client.generate_support_response(
                    message.content,
                    guild_name=message.guild.name,
                    guild_id=message.guild.id,
                    language=language,
                    custom_prompt=custom_prompt
                )
                
                # Strict emoji stripping for the AI response
                clean_response = strip_emojis(response) or i18n.get("common.error", language)
                
                # Deliver as an Embed Only
                embed = discord.Embed(
                    title=i18n.get("support.title", language),
                    description=clean_response
                )
                style_embed(embed)
                # Set footer to indicate AI generation
                embed.set_footer(text=i18n.get("support.ai_reply_footer", language))
                
                await message.reply(embed=embed, mention_author=False)
                logger.info(f"Reponse support (Embed) envoyee sur {message.guild.id}")

                # AI Moderation: Alert staff if malicious content detected
                try:
                    security_status = self.groq_client.detect_malicious_content(message.content)
                    if security_status in ["malicious", "suspicious"]:
                        log_channel_id = guild_config.get("log_channel_id")
                        if log_channel_id:
                            log_channel = message.guild.get_channel(int(log_channel_id))
                            if log_channel:
                                locale = _normalize_lang(guild_config.get("default_language"), "fr")
                                alert_embed = discord.Embed(
                                    title=i18n.get("support.security_alert_title", locale),
                                    description=i18n.get(
                                        "support.security_alert_desc", 
                                        locale, 
                                        status=security_status, 
                                        user=message.author.mention, 
                                        channel=message.channel.mention, 
                                        content=message.content[:500]
                                    ),
                                    color=discord.Color(COLOR_CRITICAL if security_status == "malicious" else COLOR_WARNING)
                                )
                                await log_channel.send(embed=style_embed(alert_embed))
                                logger.warning(f"Alerte secu IA ({security_status}) pour {message.author.id}")
                except Exception as e:
                    logger.debug(f"AI Moderation check failed: {e}")

            except Exception as e:
                logger.error(f"Erreur support IA: {e}")
                try:
                    await send_localized_embed(message.channel, "support.error_generic", ephemeral=False)
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # /premium
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="premium", description="Voir les plans disponibles")
    async def premium_info(self, interaction: discord.Interaction):
        await send_localized_embed(
            interaction,
            "payments.suggestion",
            ephemeral=True
        )

    # ------------------------------------------------------------------
    # /status
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="status", description="Voir l'abonnement du serveur")
    async def subscription_status(self, interaction: discord.Interaction):
        locale = str(interaction.locale)
        try:
            sub = SubscriptionModel.get(interaction.guild.id)
            record = sub or SubscriptionModel.get_record(interaction.guild.id)

            if not record:
                await send_localized_embed(interaction, "support.status_title", "support.plan_free", color=discord.Color(COLOR_NOTICE), ephemeral=True)
            else:
                plan = get_plan_label(normalize_plan(record.get("plan"), default="free")).upper()
                expires = record.get("expires_at") or "Indefini"
                is_active = bool(sub) and int(record.get("is_active", 0) or 0) == 1

                if is_active:
                    embed = discord.Embed(
                        title=i18n.get("support.status_title", locale),
                        description=i18n.get("support.plan_active", locale, plan=plan),
                        color=discord.Color(COLOR_SUCCESS)
                    )
                    embed.add_field(name="Statut", value=i18n.get("support.status_active", locale), inline=True)
                    embed.add_field(name=i18n.get("support.expires_at", locale), value=str(expires), inline=True)
                    embed.add_field(name="Info", value=i18n.get("support.renewal_info", locale), inline=False)
                else:
                    embed = discord.Embed(
                        title=i18n.get("support.status_title", locale),
                        description=i18n.get("support.plan_expired", locale, plan=plan),
                        color=discord.Color(COLOR_WARNING)
                    )
                    embed.add_field(name="Statut", value=i18n.get("support.status_expired", locale), inline=True)
                    embed.add_field(name=i18n.get("support.expires_at", locale), value=str(expires), inline=True)
                    embed.add_field(name="Info", value=i18n.get("support.expired_info", locale), inline=False)
                
                embed.set_footer(text=f"{DASHBOARD_URL}")
                style_embed(embed)
                await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur subscription_status: {e}")
            await send_localized_embed(interaction, "common.error", "support.error_generic", ephemeral=True)

    @discord.app_commands.command(name="language", description="Définir votre langue préférée")
    @discord.app_commands.describe(code="Code langue : fr, en, es, de, it, pt, ru, ja, zh, ar…")
    async def set_language(self, interaction: discord.Interaction, code: str):
        locale = str(interaction.locale)
        code = (code or "").strip().lower()[:2]
        if len(code) != 2 or not code.isalpha():
            await send_localized_embed(interaction, "common.error", "support.lang_invalid", ephemeral=True)
            return

        UserModel.upsert(interaction.user.id, interaction.user.name, code)
        lang_name = code.upper() # Will be improved if we had a full list
        
        await send_localized_embed(
            interaction,
            "support.lang_updated",
            locale=locale,
            lang_name=lang_name,
            code=code,
            ephemeral=True
        )

    @discord.app_commands.command(name="stats", description="Voir les statistiques du serveur")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def server_stats(self, interaction: discord.Interaction):
        locale = str(interaction.locale)
        try:
            open_t = TicketModel.count_by_guild(interaction.guild.id, status="open")
            month_t = TicketModel.count_this_month(interaction.guild.id)
            sub = SubscriptionModel.get(interaction.guild.id)
            plan = get_plan_label(normalize_plan((sub or {}).get("plan", "free"), default="free")).upper()

            embed = discord.Embed(
                title=i18n.get("support.stats_title", locale, guild_name=interaction.guild.name),
                color=discord.Color(COLOR_SUCCESS)
            )
            embed.add_field(name=i18n.get("support.stats_open", locale), value=f"`{open_t}`", inline=True)
            embed.add_field(name=i18n.get("support.stats_monthly", locale), value=f"`{month_t}`", inline=True)
            embed.add_field(name=i18n.get("support.stats_plan", locale), value=f"`{plan}`", inline=True)
            style_embed(embed)
            await interaction.response.send_message(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"stats error: {e}")
            await send_localized_embed(interaction, "common.error", "support.error_generic", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SupportCog(bot))
