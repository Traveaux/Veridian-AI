"""
Cog: Suggestions staff IA pour les tickets Pro.
"""

import discord
from discord.ext import commands
from loguru import logger

from bot.config import COLOR_NOTICE
from bot.db.models import GuildModel, SubscriptionModel, TicketMessageModel, TicketModel
from bot.services.groq_client import GroqClient
from bot.utils.embed_style import style_embed


class SuggestionsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.groq = GroqClient()

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        ticket = TicketModel.get_by_channel(message.channel.id)
        if not ticket or ticket.get("status") == "closed":
            return

        guild_config = GuildModel.get(message.guild.id) or {}
        if not int(guild_config.get("staff_suggestions", 0) or 0):
            return

        sub = SubscriptionModel.get(message.guild.id)
        if not sub or str(sub.get("plan") or "").lower() != "pro":
            return

        if message.author.id != ticket.get("user_id"):
            return

        text = (message.content or "").strip()
        if not text or len(text.split()) < 3:
            return

        try:
            msgs = TicketMessageModel.get_by_ticket(ticket["id"])
            conversation = [
                {"author": m.get("author_username", "?"), "content": m.get("original_content", "")}
                for m in (msgs or [])[-20:]
                if (m.get("original_content") or "").strip()
            ]
            if not conversation:
                return

            staff_lang = ticket.get("staff_language") or guild_config.get("default_language") or "en"
            suggestion = self.groq.generate_staff_suggestion(conversation, staff_lang)
            if not suggestion:
                return

            embed = discord.Embed(
                title="Suggestion de réponse",
                description=suggestion[:1500],
                color=discord.Color(COLOR_NOTICE),
            )
            embed.set_footer(text="IA · Suggestion uniquement")
            await message.channel.send(embed=style_embed(embed))
        except Exception as e:
            logger.debug(f"Staff suggestion failed: {e}")


async def setup(bot):
    await bot.add_cog(SuggestionsCog(bot))
