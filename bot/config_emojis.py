"""
Custom Emoji Configuration for Veridian AI
These emojis are uploaded on the main server and can be used across all servers
where the bot is present via the emoji ID system.
"""

# Main server emoji IDs (can be used globally)
CUSTOM_EMOJIS = {
    "ai": "<:ai:1490059429331337419>",
    "arrow_green": "<:arrowgreen:1490059431885406290>",
    "arrow_blue": "<:bluearrow:1490059434804777135>",
    "bot_blue": "<:botblue:1490059436692213871>",
    "crown_green": "<:greencrown:1490059438604681368>",
    "heart_green": "<:greenheart:1490059441322721390>",
    "loading": "<:Loading:1490059443646500884>",
    "star_green": "<:stargreen:1490059445240074420>",
    "ticket": "<:ticket~1:1490059461388406834>",
    "arrow_red": "<:arrowred:1490070068631961861>",
}

# Helper function to get emoji
def get_emoji(key: str) -> str:
    """Get a custom emoji by key, returns empty string if not found."""
    return CUSTOM_EMOJIS.get(key, "")

# Standard replacements for common icons
EMOJI_SUCCESS = CUSTOM_EMOJIS.get("star_green", "✅")
EMOJI_ERROR = CUSTOM_EMOJIS.get("arrow_red", "❌")
EMOJI_WARNING = CUSTOM_EMOJIS.get("arrow_red", "⚠️")
EMOJI_INFO = CUSTOM_EMOJIS.get("ai", "ℹ️")
EMOJI_TICKET = CUSTOM_EMOJIS.get("ticket", "🎫")
EMOJI_BOT = CUSTOM_EMOJIS.get("bot_blue", "🤖")
EMOJI_LOADING = CUSTOM_EMOJIS.get("loading", "⏳")
EMOJI_CROWN = CUSTOM_EMOJIS.get("crown_green", "👑")
EMOJI_HEART = CUSTOM_EMOJIS.get("heart_green", "💚")
