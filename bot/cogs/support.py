"""
Cog: Support Public IA - Repond automatiquement dans les channels designes.
Les commandes de configuration sont gerees via le dashboard.
"""

import discord
from discord.ext import commands
from loguru import logger
from bot.db.models import GuildModel, SubscriptionModel
from bot.services.groq_client import GroqClient
from bot.services.translator import TranslatorService
from bot.config import MIN_MESSAGE_LENGTH, PLAN_LIMITS, DASHBOARD_URL


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
                                color = discord.Color.red() if security_status == "malicious" else discord.Color.orange()
                                alert_embed = discord.Embed(
                                    title="🛡️ Alerte Sécurité IA",
                                    description=(
                                        f"Un message potentiellement **{security_status}** a été détecté.\n\n"
                                        f"**Utilisateur:** {message.author.mention} (`{message.author.id}`)\n"
                                        f"**Salon:** {message.channel.mention}\n"
                                        f"**Contenu:** {message.content[:500]}..."
                                    ),
                                    color=color
                                )
                                await log_channel.send(embed=alert_embed)
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
            color=discord.Color.gold(),
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
        await interaction.followup.send(embed=embed, ephemeral=True)

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
                    color=discord.Color.greyple()
                )
            else:
                plan    = sub["plan"].upper()
                expires = sub.get("expires_at", "Indefini")
                embed   = discord.Embed(
                    title="Abonnement",
                    description=f"Ce serveur est en plan **{plan}**.",
                    color=discord.Color.green()
                )
                embed.add_field(name="Expire le", value=str(expires))
            embed.set_footer(text=f"Utilisez /pay ou visitez {DASHBOARD_URL}")
            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            logger.error(f"Erreur subscription_status: {e}")
            await interaction.followup.send(f"Erreur : {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(SupportCog(bot))
