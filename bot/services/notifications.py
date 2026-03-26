"""
Service de notifications : envoi de DM au Bot Owner pour les commandes PayPal/Giftcard.
La validation se fait via le dashboard. Les boutons DM restent comme raccourci rapide.
"""

import discord
from loguru import logger
from typing import Optional
from bot.config import BOT_OWNER_DISCORD_ID, DASHBOARD_URL
from bot.config import COLOR_SUCCESS, COLOR_NOTICE, COLOR_WARNING, COLOR_CRITICAL
from bot.config import EMOJI_URL_TICKET
from bot.db.models import OrderModel, SubscriptionModel, PaymentModel, AuditLogModel


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

            embed = discord.Embed(
                title="Nouvelle commande PayPal",
                color=discord.Color(COLOR_WARNING)
            )
            embed.description = f"[ticket.gif]({EMOJI_URL_TICKET})"
            embed.add_field(name="Order ID",    value=f"`{order_id}`",           inline=False)
            embed.add_field(name="Utilisateur", value=f"{username} ({user_id})", inline=True)
            embed.add_field(name="Serveur",     value=guild.name if guild else str(guild_id), inline=True)
            embed.add_field(name="Plan",        value=plan.upper(),              inline=True)
            embed.add_field(name="Montant",     value=f"{amount:.2f} EUR",       inline=True)
            embed.add_field(
                name="Valider",
                value=f"Panel : {DASHBOARD_URL}",
                inline=False
            )
            embed.timestamp = discord.utils.utcnow()

            view = PaymentButtonView(order_id, self.bot)
            await owner.send(embed=embed, view=view)
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

            embed = discord.Embed(
                title="Nouvelle commande Carte Cadeau",
                color=discord.Color(COLOR_WARNING)
            )
            embed.description = f"[ticket.gif]({EMOJI_URL_TICKET})"
            embed.add_field(name="Order ID",    value=f"`{order_id}`",           inline=False)
            embed.add_field(name="Utilisateur", value=f"{username} ({user_id})", inline=True)
            embed.add_field(name="Serveur",     value=guild.name if guild else str(guild_id), inline=True)
            embed.add_field(name="Plan",        value=plan.upper(),              inline=True)
            embed.add_field(name="Montant",     value=f"{amount:.2f} EUR",       inline=True)
            embed.add_field(name="Code carte",  value=f"`{giftcard_code}`",      inline=False)
            embed.add_field(
                name="Valider",
                value=f"Panel : {DASHBOARD_URL}",
                inline=False
            )
            if image_url:
                embed.set_image(url=image_url)
            embed.timestamp = discord.utils.utcnow()

            view = PaymentButtonView(order_id, self.bot)
            await owner.send(embed=embed, view=view)
            logger.info(f"Notification carte cadeau envoyee pour {order_id}")

        except Exception as e:
            logger.error(f"Erreur notification carte cadeau: {e}")

    async def notify_user_payment_confirmed(self, user_id: int, plan: str, guild_id: int):
        try:
            user  = await self.bot.fetch_user(user_id)
            guild = self.bot.get_guild(guild_id)
            embed = discord.Embed(
                title="Paiement confirme",
                color=discord.Color(COLOR_SUCCESS),
                description=(
                    f"Votre abonnement **{plan.upper()}** est actif"
                    f" sur **{guild.name if guild else guild_id}**. Merci !"
                )
            )
            await user.send(embed=embed)
            logger.info(f"Confirmation paiement envoyee a {user_id}")
        except Exception as e:
            logger.error(f"Erreur notification confirmation: {e}")

    async def notify_user_payment_rejected(self, user_id: int, order_id: str,
                                           reason: str = None):
        try:
            user  = await self.bot.fetch_user(user_id)
            embed = discord.Embed(
                title="Commande rejetee",
                color=discord.Color(COLOR_CRITICAL),
                description=(
                    f"Votre commande `{order_id}` a ete rejetee."
                    + (f"\nRaison : {reason}" if reason else "")
                    + f"\nContactez le support : {DASHBOARD_URL}"
                )
            )
            await user.send(embed=embed)
        except Exception as e:
            logger.error(f"Erreur notification rejet: {e}")

    async def notify_user_payment_partial(self, user_id: int, order_id: str):
        try:
            user  = await self.bot.fetch_user(user_id)
            embed = discord.Embed(
                title="Montant incomplet",
                color=discord.Color(COLOR_NOTICE),
                description=(
                    f"Le montant recu pour la commande `{order_id}` est insuffisant.\n"
                    "Veuillez envoyer le solde manquant avec la meme reference."
                )
            )
            await user.send(embed=embed)
        except Exception as e:
            logger.error(f"Erreur notification paiement partiel: {e}")


# ============================================================================
# Boutons de validation rapide (DM au Bot Owner)
# Ces boutons sont un raccourci ; la validation complete se fait sur le dashboard.
# ============================================================================

class PaymentButtonView(discord.ui.View):
    def __init__(self, order_id: str, bot):
        super().__init__(timeout=None)
        self.order_id = order_id
        self.bot      = bot

    async def _validate(self, interaction: discord.Interaction, status: str):
        """Logique commune de validation."""
        await interaction.response.defer()
        order = OrderModel.get(self.order_id)
        if not order:
            await interaction.followup.send("Commande introuvable.", ephemeral=True)
            return

        if order["status"] != "pending":
            await interaction.followup.send(
                f"Commande deja traitee (statut : {order['status']}).", ephemeral=True
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
            plan       = order.get("plan", "premium")
            payment_id = PaymentModel.create(
                user_id=order["user_id"], guild_id=order["guild_id"],
                method=order["method"], amount=float(order["amount"] or 0),
                plan=plan, order_id=self.order_id, status="completed"
            )
            SubscriptionModel.create(
                guild_id=order["guild_id"], user_id=order["user_id"],
                plan=plan, payment_id=payment_id, duration_days=30
            )
            await notif.notify_user_payment_confirmed(
                order["user_id"], plan, order["guild_id"]
            )
            label = "Valide et abonnement active"

        elif status == "partial":
            await notif.notify_user_payment_partial(order["user_id"], self.order_id)
            label = "Marque comme montant incomplet"

        else:  # rejected
            await notif.notify_user_payment_rejected(order["user_id"], self.order_id)
            label = "Commande rejetee"

        # Desactiver tous les boutons
        for item in self.children:
            item.disabled = True
        await interaction.message.edit(content=f"[{label}]", view=self)
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
