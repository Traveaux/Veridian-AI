"""
Emoji replacement utilities for Veridian AI
Replaces standard emojis with custom server emojis in embeds and messages.
"""

from __future__ import annotations

from bot.config_emojis import CUSTOM_EMOJIS, get_emoji
import discord

# Emoji mapping for automatic replacement
# Format: (standard_emoji, custom_key)
_EMOJI_REPLACEMENTS = [
    # Success/Check marks
    ("✅", "star_green"),
    ("✓", "star_green"),
    ("☑️", "star_green"),
    
    # Errors/X marks  
    ("❌", "arrow_red"),
    ("✗", "arrow_red"),
    ("❎", "arrow_red"),
    
    # Warnings
    ("⚠️", "arrow_red"),
    ("⚠", "arrow_red"),
    
    # Info
    ("ℹ️", "ai"),
    ("ℹ", "ai"),
    ("📋", "ai"),
    
    # Tickets
    ("🎫", "ticket"),
    ("📩", "ticket"),
    ("📨", "ticket"),
    
    # Bot/AI
    ("🤖", "bot_blue"),
    ("👾", "bot_blue"),
    ("💻", "bot_blue"),
    
    # Loading
    ("⏳", "loading"),
    ("🔄", "loading"),
    ("⏱️", "loading"),
    
    # Crown/VIP
    ("👑", "crown_green"),
    ("🏆", "crown_green"),
    ("🥇", "crown_green"),
    
    # Heart
    ("❤️", "heart_green"),
    ("💚", "heart_green"),
    ("💖", "heart_green"),
    
    # Arrows
    ("➡️", "arrow_green"),
    ("→", "arrow_green"),
    ("▶️", "arrow_green"),
    ("⬅️", "arrow_blue"),
    ("←", "arrow_blue"),
    ("◀️", "arrow_blue"),
]


def replace_emojis(text: str | None) -> str | None:
    """
    Replace standard emojis with custom server emojis in text.
    Returns None if input is None.
    """
    if text is None:
        return None
    
    for standard, custom_key in _EMOJI_REPLACEMENTS:
        custom = get_emoji(custom_key)
        if custom:  # Only replace if we have the custom emoji
            text = text.replace(standard, custom)
    
    return text


def apply_custom_emojis_to_embed(embed: discord.Embed) -> discord.Embed:
    """
    Apply custom emojis to all text fields in an embed.
    Modifies the embed in place and returns it.
    """
    # Title
    if embed.title:
        embed.title = replace_emojis(embed.title) or embed.title
    
    # Description
    if embed.description:
        embed.description = replace_emojis(embed.description) or embed.description
    
    # Author
    if embed.author.name:
        new_name = replace_emojis(embed.author.name)
        if new_name:
            embed.set_author(name=new_name, icon_url=embed.author.icon_url)
    
    # Footer
    if embed.footer.text:
        new_footer = replace_emojis(embed.footer.text)
        if new_footer:
            embed.set_footer(text=new_footer, icon_url=embed.footer.icon_url)
    
    # Fields
    for i, field in enumerate(list(embed.fields)):
        new_name = replace_emojis(field.name) or field.name
        new_value = replace_emojis(field.value) or field.value
        embed.set_field_at(i, name=new_name, value=new_value, inline=field.inline)
    
    return embed


# Short aliases for convenience
get = get_emoji
replace = replace_emojis
apply_to_embed = apply_custom_emojis_to_embed
