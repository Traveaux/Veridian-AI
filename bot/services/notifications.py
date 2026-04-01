"""
Service de notifications : envoi de DM au Bot Owner pour les commandes PayPal/Giftcard.
La validation se fait via le dashboard. Les boutons DM restent comme raccourci rapide.
"""

import discord
from loguru import logger
from typing import Optional
from datetime import datetime
from bot.config import BOT_OWNER_DISCORD_ID, DASHBOARD_URL
from bot.config import COLOR_SUCCESS, COLOR_NOTICE, COLOR_WARNING, COLOR_CRITICAL
from bot.billing import normalize_interval, normalize_plan
from bot.db.models import OrderModel, SubscriptionModel, PaymentModel, AuditLogModel, PendingNotificationModel
from bot.utils.embed_style import style_embed, _normalize_lang
from bot.utils.i18n import i18n


def _format_expiry(expires_at, locale="fr") -> str:
    if not expires_at:
        return i18n.get("common.no_date", locale)
    if isinstance(expires_at, datetime):
        return expires_at.strftime("%d/%m/%Y")
    return str(expires_at)


class NotificationService:
    def __init__(self, bot):
        self.bot = bot
        logger.info("Service Notifications initialise")

    async def _get_owner(self) -> Optional[discord.User]:
        try:
            return await self.bot.fetch_user(BOT_OWNER_DISCORD_ID)
        except Exception as e:
            logger.error(f"Bot Owner introuvable: {e}")
            return None

    async def send_paypal_order_notification(
        self, user_id: int, order_id: str, plan: str,
        amount: float, guild_id: int
    ):
        owner = await self._get_owner()
        if not owner:
            return

        try:
            guild    = self.bot.get_guild(guild_id)
            user     = await self.bot.fetch_user(user_id)
            username = user.name if user else f"User {user_id}"
            locale   = _normalize_lang(guild.preferred_locale if guild else "fr", "fr")

            embed = discord.Embed(
                title=i18n.get("notifications.paypal_title", locale),
                color=discord.Color(COLOR_WARNING)
            )
            embed.add_field(name=i18n.get("notifications.order_id", locale), value=f"`{order_id}`", inline=False)
            embed.add_field(name=i18n.get("notifications.user", locale), value=f"{username} ({user_id})", inline=True)
            embed.add_field(name=i18n.get("notifications.guild", locale), value=guild.name if guild else str(guild_id), inline=True)
            embed.add_field(name=i18n.get("notifications.plan", locale), value=plan.upper(), inline=True)
            embed.add_field(name=i18n.get("notifications.amount", locale), value=f"{amount:.2f} EUR", inline=True)
            embed.add_field(
                name=i18n.get("notifications.validate", locale),
                value=i18n.get("notifications.panel_link", locale, url=DASHBOARD_URL),
                inline=False
            )
            embed.timestamp = discord.utils.utcnow()

            view = PaymentButtonView(order_id, self.bot, locale)
            await owner.send(embed=style_embed(embed), view=view)
            logger.info(f"Notification PayPal envoyee pour {order_id}")

        except Exception as e:
            logger.error(f"Erreur notification PayPal: {e}")

    async def send_giftcard_order_notification(
        self, user_id: int, order_id: str, plan: str,
        amount: float, guild_id: int,
        giftcard_code: str, image_url: Optional[str] = None
    ):
        owner = await self._get_owner()
        if not owner:
            return

        try:
            guild    = self.bot.get_guild(guild_id)
            user     = await self.bot.fetch_user(user_id)
            username = user.name if user else f"User {user_id}"
            locale   = _normalize_lang(guild.preferred_locale if guild else "fr", "fr")

            embed = discord.Embed(
                title=i18n.get("notifications.giftcard_title", locale),
                color=discord.Color(COLOR_WARNING)
            )
            embed.add_field(name=i18n.get("notifications.order_id", locale), value=f"`{order_id}`", inline=False)
            embed.add_field(name=i18n.get("notifications.user", locale), value=f"{username} ({user_id})", inline=True)
            embed.add_field(name=i18n.get("notifications.guild", locale), value=guild.name if guild else str(guild_id), inline=True)
            embed.add_field(name=i18n.get("notifications.plan", locale), value=plan.upper(), inline=True)
            embed.add_field(name=i18n.get("notifications.amount", locale), value=f"{amount:.2f} EUR", inline=True)
            embed.add_field(name=i18n.get("notifications.giftcard_code", locale), value=f"`{giftcard_code}`", inline=False)
            embed.add_field(
                name=i18n.get("notifications.validate", locale),
                value=i18n.get("notifications.panel_link", locale, url=DASHBOARD_URL),
                inline=False
            )
            if image_url:
                embed.set_image(url=image_url)
            embed.timestamp = discord.utils.utcnow()

            view = PaymentButtonView(order_id, self.bot, locale)
            await owner.send(embed=style_embed(embed), view=view)
            logger.info(f"Notification carte cadeau envoyee pour {order_id}")

        except Exception as e:
            logger.error(f"Erreur notification carte cadeau: {e}")

    async def notify_user_payment_confirmed(self, user_id: int, plan: str, guild_id: int, expires_at=None):
        try:
            user   = await self.bot.fetch_user(user_id)
            guild  = self.bot.get_guild(guild_id)
            # Detect user preferred locale if available
            user_db = None # UserModel.get(user_id) - assumed available
            locale  = _normalize_lang(getattr(user, "locale", "fr"), "fr")
            
            expiry_label = _format_expiry(expires_at, locale)
            embed = discord.Embed(
                title=i18n.get("notifications.payment_confirmed_title", locale),
                color=discord.Color(COLOR_SUCCESS),
                description=i18n.get(
                    "notifications.payment_confirmed_desc", 
                    locale, 
                    plan=plan.upper(), 
                    guild_name=guild.name if guild else str(guild_id),
                    expiry=expiry_label
                )
            )
            await user.send(embed=style_embed(embed))
            logger.info(f"Confirmation paiement envoyee a {user_id}")
        except Exception as e:
            logger.error(f"Erreur notification confirmation: {e}")

    async def notify_user_payment_rejected(self, user_id: int, order_id: str,
                                           reason: str = None):
        try:
            user   = await self.bot.fetch_user(user_id)
            locale = _normalize_lang(getattr(user, "locale", "fr"), "fr")
            embed = discord.Embed(
                title=i18n.get("notifications.payment_rejected_title", locale),
                color=discord.Color(COLOR_CRITICAL),
                description=i18n.get(
                    "notifications.payment_rejected_desc",
                    locale,
                    order_id=order_id,
                    reason=f"\nReason: {reason}" if reason else "",
                    url=DASHBOARD_URL
                )
            )
            await user.send(embed=style_embed(embed))
        except Exception as e:
            logger.error(f"Erreur notification rejet: {e}")

    async def notify_user_payment_partial(self, user_id: int, order_id: str):
        try:
            user   = await self.bot.fetch_user(user_id)
            locale = _normalize_lang(getattr(user, "locale", "fr"), "fr")
            embed  = discord.Embed(
                title=i18n.get("notifications.payment_partial_title", locale),
                color=discord.Color(COLOR_NOTICE),
                description=i18n.get("notifications.payment_partial_desc", locale, order_id=order_id)
            )
            await user.send(embed=style_embed(embed))
        except Exception as e:
            logger.error(f"Erreur notification paiement partiel: {e}")


# ============================================================================
# Boutons de validation rapide (DM au Bot Owner)
# Ces boutons sont un raccourci ; la validation complete se fait sur le dashboard.
# ============================================================================

class PaymentButtonView(discord.ui.View):
    def __init__(self, order_id: str, bot, locale: str = "fr"):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.bot      = bot
        self.locale   = locale
        
        # Update button labels dynamically based on locale
        self.paid_button.label     = i18n.get("notifications.status_paid_short", locale) if i18n.get("notifications.status_paid_short", locale) != "notifications.status_paid_short" else "Paid"
        self.rejected_button.label = i18n.get("notifications.status_rejected_short", locale) if i18n.get("notifications.status_rejected_short", locale) != "notifications.status_rejected_short" else "Rejected"
        self.partial_button.label  = i18n.get("notifications.status_partial_short", locale) if i18n.get("notifications.status_partial_short", locale) != "notifications.status_partial_short" else "Partial"

    async def _validate(self, interaction: discord.Interaction, status: str):
        """Logique commune de validation."""
        await interaction.response.defer()
        order = OrderModel.get(self.order_id)
        if not order:
            await interaction.followup.send(i18n.get("notifications.error_not_found", self.locale), ephemeral=True)
            return

        if order["status"] != "pending":
            await interaction.followup.send(
                i18n.get("notifications.error_already_processed", self.locale, status=order['status']), ephemeral=True
            )
            return

        OrderModel.update_status(
            self.order_id, status=status,
            validated_by=interaction.user.id
        )
        AuditLogModel.log(
            actor_id=interaction.user.id,
            actor_username=str(interaction.user),
            action=f"order.{status}",
            target_id=self.order_id
        )

        notif = NotificationService(self.bot)

        if status == "paid":
            plan       = normalize_plan(order.get("plan"), default="starter")
            interval   = normalize_interval(order.get("billing_interval"), default="month")
            payment_id = PaymentModel.create(
                user_id=order["user_id"], guild_id=order["guild_id"],
                method=order["method"], amount=float(order["amount"] or 0),
                plan=plan, billing_interval=interval, order_id=self.order_id, status="completed"
            )
            SubscriptionModel.create(
                guild_id=order["guild_id"], user_id=order["user_id"],
                plan=plan, payment_id=payment_id, billing_interval=interval
            )
            sub = SubscriptionModel.get(order["guild_id"]) or {}
            await notif.notify_user_payment_confirmed(
                order["user_id"], plan, order["guild_id"], sub.get("expires_at")
            )
            label = i18n.get("notifications.status_paid", self.locale)

        elif status == "partial":
            await notif.notify_user_payment_partial(order["user_id"], self.order_id)
            label = i18n.get("notifications.status_partial", self.locale)

        else:  # rejected
            await notif.notify_user_payment_rejected(order["user_id"], self.order_id)
            label = i18n.get("notifications.status_rejected", self.locale)

        # Update embed to show status instead of changing to plain text
        embed = interaction.message.embeds[0]
        embed.description = f"**{label}**"
        embed.color = discord.Color(COLOR_SUCCESS if status == "paid" else (COLOR_NOTICE if status == "partial" else COLOR_CRITICAL))
        
        await interaction.message.edit(embed=style_embed(embed), view=self)
        logger.info(f"Commande {self.order_id} traitee via DM bot : {status}")

    @discord.ui.button(label="Paye", style=discord.ButtonStyle.success)
    async def paid_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._validate(interaction, "paid")

    @discord.ui.button(label="Rejete", style=discord.ButtonStyle.danger)
    async def rejected_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._validate(interaction, "rejected")

    @discord.ui.button(label="Montant incomplet", style=discord.ButtonStyle.secondary)
    async def partial_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._validate(interaction, "partial")


async def notify_bot_owner_payment(
    user_id: int,
    guild_id: int,
    plan: str,
    method: str,
    amount: float,
    order_id: str | None = None,
):
    """Ajoute une notification DM au owner via la file d'attente du bot."""
    try:
        message = (
            "Nouvelle confirmation de paiement.\n"
            f"Methode : {str(method).upper()}\n"
            f"Plan : {str(plan).upper()}\n"
            f"Montant : {float(amount or 0):.2f} EUR\n"
            f"Guild ID : {guild_id}\n"
            f"User ID : {user_id}\n"
            f"Reference : {order_id or 'n/a'}\n"
            f"Panel : {DASHBOARD_URL}"
        )
        PendingNotificationModel.add(BOT_OWNER_DISCORD_ID, message)
    except Exception as e:
        logger.warning(f"Impossible de notifier le Bot Owner pour un paiement: {e}")
