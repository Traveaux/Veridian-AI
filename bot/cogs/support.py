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
from bot.config import COLOR_SUCCESS, COLOR_NOTICE, COLOR_WARNING, COLOR_CRITICAL
from bot.utils.embed_style import style_embed

LANGUAGE_NAMES = {
    "fr": "Français",
    "en": "Anglais",
    "es": "Espagnol",
    "de": "Allemand",
    "it": "Italien",
    "pt": "Portugais",
    "ru": "Russe",
    "ja": "Japonais",
    "zh": "Chinois",
    "ar": "Arabe",
}


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
                await message.reply(response[:2000], mention_author=False,
                                    suppress_embeds=True)
                logger.info(f"Reponse support envoyee sur {message.guild.id}")

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
                                    title="Alerte Sécurité IA",
                                    description=(
                                        f"Un message potentiellement **{security_status}** a été détecté.\n\n"
                                        f"**Utilisateur:** {message.author.mention} (`{message.author.id}`)\n"
                                        f"**Salon:** {message.channel.mention}\n"
                                        f"**Contenu:** {message.content[:500]}..."
                                    ),
                                    color=color
                                )
                                await log_channel.send(embed=style_embed(alert_embed))
                                logger.warning(f"Alerte secu IA ({security_status}) pour {message.author.id}")
                except Exception as e:
                    logger.debug(f"AI Moderation check failed: {e}")

            except Exception as e:
                logger.error(f"Erreur support IA: {e}")
                try:
                    await message.reply(
                        "Une erreur s'est produite. Veuillez ouvrir un ticket.",
                        mention_author=False
                    )
                except Exception:
                    pass

    # ------------------------------------------------------------------
    # /premium
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="premium", description="Voir les plans disponibles")
    async def premium_info(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        embed = discord.Embed(
            title="Plans Veridian AI",
            color=discord.Color(COLOR_WARNING),
            description=(
                "Upgrade via le panel ou avec la commande `/pay`.\n"
                f"{DASHBOARD_URL}"
            )
        )
        embed.add_field(
            name="Free",
            value="50 tickets/mois | 5 langues | Support public limite",
            inline=False
        )
        embed.add_field(
            name="Premium (2 EUR/mois)",
            value="500 tickets/mois | 20 langues | KB 50 entrees | Transcriptions",
            inline=False
        )
        embed.add_field(
            name="Pro (5 EUR/mois)",
            value="Illimite | Toutes langues | KB illimitee | Suggestions staff | Stats avancees",
            inline=False
        )
        await interaction.followup.send(embed=style_embed(embed), ephemeral=True)

    # ------------------------------------------------------------------
    # /status
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="status", description="Voir l'abonnement du serveur")
    async def subscription_status(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            sub = SubscriptionModel.get(interaction.guild.id)
            if not sub:
                embed = discord.Embed(
                    title="Abonnement",
                    description="Ce serveur est en plan **Free**.",
                    color=discord.Color(COLOR_NOTICE)
                )
            else:
                plan    = sub["plan"].upper()
                expires = sub.get("expires_at", "Indefini")
                embed   = discord.Embed(
                    title="Abonnement",
                    description=f"Ce serveur est en plan **{plan}**.",
                    color=discord.Color(COLOR_SUCCESS)
                )
                embed.add_field(name="Expire le", value=str(expires))
            embed.set_footer(text=f"Utilisez /pay ou visitez {DASHBOARD_URL}")
            await interaction.followup.send(embed=style_embed(embed), ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur subscription_status: {e}")
            await interaction.followup.send(f"Erreur : {e}", ephemeral=True)

    @discord.app_commands.command(name="language", description="Définir votre langue préférée")
    @discord.app_commands.describe(code="Code langue : fr, en, es, de, it, pt, ru, ja, zh, ar…")
    async def set_language(self, interaction: discord.Interaction, code: str):
        await interaction.response.defer(ephemeral=True)
        code = (code or "").strip().lower()[:2]
        if len(code) != 2 or not code.isalpha():
            await interaction.followup.send("Code langue invalide. Exemple: `fr`, `en`, `es`.", ephemeral=True)
            return

        UserModel.upsert(interaction.user.id, interaction.user.name, code)

        try:
            ticket = TicketModel.get_active_by_user(interaction.guild.id, interaction.user.id)
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

    @discord.app_commands.command(name="stats", description="Voir les statistiques du serveur")
    @discord.app_commands.checks.has_permissions(administrator=True)
    async def server_stats(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
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


async def setup(bot):
    await bot.add_cog(SupportCog(bot))
