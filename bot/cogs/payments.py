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
from bot.config import API_DOMAIN, PRICING, COLOR_WARNING
from bot.utils.embed_style import style_embed, send_localized_embed, strip_emojis, _normalize_lang
from bot.utils.i18n import i18n


# PAYPAL_INSTRUCTIONS_TEMPLATE removed - using i18n system


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
            discord.app_commands.Choice(name="Starter (4 EUR/mois)",  value="starter"),
            discord.app_commands.Choice(name="Pro (12 EUR/mois)",     value="pro"),
            discord.app_commands.Choice(name="Business (29 EUR/mois)", value="business"),
        ]
    )
    async def pay(self, interaction: discord.Interaction, method: str, plan: str):
        if not interaction.user.guild_permissions.administrator:
            await send_localized_embed(
                interaction,
                "common.error",
                "payments.admin_required",
                ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True)

        amount = PRICING.get(plan, 0)
        if not amount:
            await send_localized_embed(
                interaction,
                "common.error",
                "payments.invalid_plan",
                ephemeral=True
            )
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

    # PayPal
    # ------------------------------------------------------------------

    async def _handle_paypal(self, interaction: discord.Interaction,
                              order_id: str, plan: str, amount: float):
        paypal_email = os.getenv("PAYPAL_EMAIL", "billing@veridiancloud.xyz")
        await send_localized_embed(
            interaction,
            "payments.paypal_title",
            "payments.paypal_instructions",
            paypal_email=paypal_email,
            amount=amount,
            order_id=order_id,
            ephemeral=True
        )

        await self.notifications.send_paypal_order_notification(
            interaction.user.id, order_id, plan, amount, interaction.guild.id
        )

    # ------------------------------------------------------------------
    # Carte Cadeau
    # ------------------------------------------------------------------

    async def _handle_giftcard(self, interaction: discord.Interaction,
                                order_id: str, plan: str, amount: float):
        locale = _normalize_lang(interaction.user.locale or interaction.guild.preferred_locale, "fr")
        await send_localized_embed(
            interaction,
            "payments.giftcard_title",
            "payments.giftcard_desc",
            plan=plan.upper(),
            amount=amount,
            ephemeral=True
        )

        def check(msg: discord.Message):
            return (msg.author.id == interaction.user.id
                    and isinstance(msg.channel, discord.DMChannel))
        try:
            embed = discord.Embed(
                title=i18n.get("payments.giftcard_title", locale),
                description=i18n.get("payments.giftcard_dm_code", locale, order_id=order_id)
            )
            await interaction.user.send(embed=style_embed(embed))

            code_msg = await self.bot.wait_for("message", check=check, timeout=600)
            giftcard_code = strip_emojis(code_msg.content)

            embed = discord.Embed(
                title=i18n.get("payments.giftcard_title", locale),
                description=i18n.get("payments.giftcard_dm_image", locale)
            )
            await interaction.user.send(embed=style_embed(embed))

            img_msg   = await self.bot.wait_for("message", check=check, timeout=600)
            image_url = img_msg.attachments[0].url if img_msg.attachments else None

            OrderModel.update_giftcard(order_id, giftcard_code, image_url)

            await self.notifications.send_giftcard_order_notification(
                interaction.user.id, order_id, plan, amount,
                interaction.guild.id, giftcard_code, image_url
            )
            
            embed = discord.Embed(
                title=i18n.get("common.success", locale),
                description=i18n.get("payments.giftcard_dm_success", locale)
            )
            await interaction.user.send(embed=style_embed(embed))

        except asyncio.TimeoutError:
            embed = discord.Embed(
                title=i18n.get("common.error", locale),
                description=i18n.get("payments.giftcard_dm_timeout", locale)
            )
            await interaction.user.send(embed=style_embed(embed))
        except Exception as e:
            logger.error(f"Erreur giftcard: {e}")
            embed = discord.Embed(
                title=i18n.get("common.error", locale),
                description=f"Error: {strip_emojis(str(e))}"
            )
            await interaction.user.send(embed=style_embed(embed))

    # ------------------------------------------------------------------
    # Crypto via OxaPay
    # ------------------------------------------------------------------

    async def _handle_crypto(self, interaction: discord.Interaction,
                                order_id: str, plan: str, amount: float):
        await send_localized_embed(interaction, "common.loading", "payments.crypto_loading", ephemeral=True)
        try:
            callback_url = f"https://{os.getenv('API_DOMAIN', API_DOMAIN)}/webhook/oxapay"
            invoice      = await self.oxapay.create_invoice(
                interaction.user.id, amount, order_id, callback_url
            )

            if not invoice or "payLink" not in invoice:
                await send_localized_embed(interaction, "common.error", "payments.crypto_error", ephemeral=True)
                return

            locale = _normalize_lang(interaction.user.locale or interaction.guild.preferred_locale, "fr")
            embed = discord.Embed(
                title=i18n.get("payments.crypto_title", locale),
                color=discord.Color(COLOR_WARNING),
                description=i18n.get("payments.crypto_desc", locale, plan=plan.upper(), amount=amount)
            )
            view = discord.ui.View()
            view.add_item(discord.ui.Button(label=i18n.get("payments.pay_now_button", locale), url=invoice["payLink"]))
            style_embed(embed)
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)

        except Exception as e:
            logger.error(f"Erreur crypto: {e}")
            await interaction.followup.send(f"Erreur : {e}", ephemeral=True)


async def setup(bot):
    await bot.add_cog(PaymentsCog(bot))
