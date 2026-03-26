"""
Cog: Paiements - Commande /pay pour initier un paiement.
La validation des commandes est geree sur le dashboard (panel super-admin).
"""

import discord
from discord.ext import commands
from loguru import logger
import random
import datetime
import asyncio
import os

from bot.db.models import OrderModel, SubscriptionModel, PaymentModel, UserModel, GuildModel
from bot.services.notifications import NotificationService
from bot.services.oxapay import OxaPayClient
from bot.config import BOT_OWNER_DISCORD_ID, PRICING, DASHBOARD_URL
from bot.config import COLOR_SUCCESS, COLOR_NOTICE, COLOR_WARNING, COLOR_CRITICAL
from bot.config import EMOJI_URL_TICKET


class PaymentsCog(commands.Cog):
    """Gere les paiements : PayPal, Carte Cadeau, Crypto."""

    def __init__(self, bot):
        self.bot          = bot
        self.notifications = NotificationService(bot)
        self.oxapay       = OxaPayClient()
        logger.info("Cog Paiements charge")

    @staticmethod
    def generate_order_id() -> str:
        now  = datetime.datetime.now()
        rand = random.randint(1000, 9999)
        return f"VAI-{now.year}{now.month:02d}-{rand}"

    # ------------------------------------------------------------------
    # /pay
    # ------------------------------------------------------------------

    @discord.app_commands.command(name="pay", description="Initier un paiement")
    @discord.app_commands.checks.cooldown(1, 30.0, key=lambda i: i.user.id)
    @discord.app_commands.describe(
        method="Methode de paiement",
        plan="Plan a souscrire"
    )
    @discord.app_commands.choices(
        method=[
            discord.app_commands.Choice(name="PayPal",                   value="paypal"),
            discord.app_commands.Choice(name="Carte Cadeau",             value="giftcard"),
            discord.app_commands.Choice(name="Crypto (BTC, ETH, USDT)", value="oxapay"),
        ],
        plan=[
            discord.app_commands.Choice(name="Premium (2 EUR/mois)", value="premium"),
            discord.app_commands.Choice(name="Pro (5 EUR/mois)",     value="pro"),
        ]
    )
    async def pay(self, interaction: discord.Interaction, method: str, plan: str):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message(
                "Vous devez etre administrateur du serveur pour effectuer un paiement.",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        amount = PRICING.get(plan, 0)
        if not amount:
            await interaction.followup.send("Plan invalide.", ephemeral=True)
            return

        # S'assurer que l'utilisateur est en DB
        UserModel.upsert(interaction.user.id, interaction.user.name)

        # Creer la commande
        order_id = self.generate_order_id()
        guild    = interaction.guild
        OrderModel.create(
            order_id=order_id,
            user_id=interaction.user.id,
            user_username=interaction.user.name,
            guild_id=guild.id,
            guild_name=guild.name,
            method=method,
            plan=plan,
            amount=amount
        )

        if method == "paypal":
            await self._handle_paypal(interaction, order_id, plan, amount)
        elif method == "giftcard":
            await self._handle_giftcard(interaction, order_id, plan, amount)
        elif method == "oxapay":
            await self._handle_crypto(interaction, order_id, plan, amount)

        logger.info(f"Paiement initialise: {order_id} ({method} / {plan})")

    # ------------------------------------------------------------------
    # PayPal
    # ------------------------------------------------------------------

    async def _handle_paypal(self, interaction: discord.Interaction,
                              order_id: str, plan: str, amount: float):
        paypal_email = os.getenv("PAYPAL_EMAIL", "[Email PayPal non configure]")

        embed = discord.Embed(
            title="Paiement PayPal",
            color=discord.Color(COLOR_NOTICE),
            description=(
                f"[ticket.gif]({EMOJI_URL_TICKET})\n\n"
                f"Plan : **{plan.upper()}** | Montant : **{amount:.2f} EUR**\n\n"
                f"Envoyez **{amount:.2f} EUR** a : `{paypal_email}`\n"
                f"Indiquez comme reference : **{order_id}**\n\n"
                "Votre commande sera validee sous 24h via le panel d'administration.\n"
                f"Suivi : {DASHBOARD_URL}"
            )
        )
        embed.set_footer(text="Sans la reference de commande, le paiement ne sera pas reconnu.")

        await interaction.followup.send(embed=embed, ephemeral=True)

        await self.notifications.send_paypal_order_notification(
            interaction.user.id, order_id, plan, amount, interaction.guild.id
        )

    # ------------------------------------------------------------------
    # Carte Cadeau
    # ------------------------------------------------------------------

    async def _handle_giftcard(self, interaction: discord.Interaction,
                                order_id: str, plan: str, amount: float):
        embed = discord.Embed(
            title="Carte Cadeau",
            color=discord.Color(COLOR_SUCCESS),
            description=(
                f"[ticket.gif]({EMOJI_URL_TICKET})\n\n"
                f"Plan : **{plan.upper()}** | Montant : **{amount:.2f} EUR**\n\n"
                "Vous allez recevoir un DM pour envoyer votre code et l'image de la carte."
            )
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

        def check(msg: discord.Message):
            return (msg.author.id == interaction.user.id
                    and isinstance(msg.channel, discord.DMChannel))

        try:
            await interaction.user.send(
                f"Envoyez le code de votre carte cadeau (commande : {order_id}) :"
            )
            code_msg = await self.bot.wait_for("message", check=check, timeout=600)
            giftcard_code = code_msg.content

            await interaction.user.send("Envoyez maintenant une image de la carte cadeau :")
            img_msg   = await self.bot.wait_for("message", check=check, timeout=600)
            image_url = img_msg.attachments[0].url if img_msg.attachments else None

            OrderModel.update_giftcard(order_id, giftcard_code, image_url)

            await self.notifications.send_giftcard_order_notification(
                interaction.user.id, order_id, plan, amount,
                interaction.guild.id, giftcard_code, image_url
            )
            await interaction.user.send(
                "Merci ! Votre commande est en attente de validation (max 24h)."
            )

        except asyncio.TimeoutError:
            await interaction.user.send("Delai depasse. Veuillez recommencer.")
        except Exception as e:
            logger.error(f"Erreur giftcard: {e}")
            await interaction.user.send(f"Erreur : {e}")

    # ------------------------------------------------------------------
    # Crypto via OxaPay
    # ------------------------------------------------------------------

    async def _handle_crypto(self, interaction: discord.Interaction,
                              order_id: str, plan: str, amount: float):
        await interaction.followup.send(
            "Generation de l'invoice en cours...", ephemeral=True
        )
        try:
            callback_url = "https://api.veridiancloud.xyz/webhook/oxapay"
            invoice      = await self.oxapay.create_invoice(
                interaction.user.id, amount, order_id, callback_url
            )

            if not invoice or "payLink" not in invoice:
                await interaction.followup.send(
                    "Erreur lors de la creation de l'invoice. Reessayez.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="Paiement Crypto",
                color=discord.Color(COLOR_WARNING),
                description=(
                    f"[ticket.gif]({EMOJI_URL_TICKET})\n\n"
                    f"Plan : **{plan.upper()}** | Montant : **{amount:.2f} EUR**\n\n"
                    "Cliquez sur le bouton ci-dessous pour effectuer votre paiement.\n"
                    "Le bot sera notifie automatiquement a la reception du paiement."
                )
            )
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label="Payer maintenant", url=invoice["payLink"]))
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Erreur crypto: {e}")
            await interaction.followup.send(f"Erreur : {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PaymentsCog(bot))
