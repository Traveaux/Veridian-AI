"""Embed styling helpers: remove emojis and apply a visible frame."""

from __future__ import annotations

import re
import discord

_CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_~]+:\d+>")
_EMOJI_RE = re.compile(
    "["
    "\U0001F1E0-\U0001F1FF"
    "\U0001F300-\U0001F5FF"
    "\U0001F600-\U0001F64F"
    "\U0001F680-\U0001F6FF"
    "\U0001F700-\U0001F77F"
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\u2600-\u26FF"
    "\u2700-\u27BF"
    "]+",
    flags=re.UNICODE,
)
_VARIATION_RE = re.compile(r"[\uFE0E\uFE0F\u200D]")
_WHITESPACE_RE = re.compile(r"[ \t]{2,}")
_MULTILINE_RE = re.compile(r"\n{3,}")

# _TRANSLATION_TITLES removed - using i18n system


def strip_emojis(text: str | None) -> str | None:
    """Remove standard Unicode emojis but preserve Discord custom emojis (<:name:id> and <a:name:id>)."""
    if text is None:
        return None

    # First, temporarily protect Discord custom emojis by replacing them with placeholders
    custom_emojis = []
    def save_custom_emoji(match):
        custom_emojis.append(match.group(0))
        return f"\x00EMOJI_{len(custom_emojis)-1}\x00"
    
    protected_text = _CUSTOM_EMOJI_RE.sub(save_custom_emoji, text)
    
    # Remove standard Unicode emojis
    cleaned = _EMOJI_RE.sub("", protected_text)
    # Remove variation selectors
    cleaned = _VARIATION_RE.sub("", cleaned)
    
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    cleaned = _MULTILINE_RE.sub("\n\n", cleaned)
    cleaned = cleaned.strip()
    
    # Restore custom emojis
    for i, emoji in enumerate(custom_emojis):
        cleaned = cleaned.replace(f"\x00EMOJI_{i}\x00", emoji)
    
    # Final check: if the text was only emojis, it might be empty now.
    return cleaned or None


def _preserve_emojis_during_styling(text: str | None) -> str | None:
    """Extract emojis, apply styling to text only, then reinsert emojis."""
    if text is None:
        return None
    
    # Extract emojis with their positions
    emojis = []
    def extract_emoji(match):
        emojis.append((match.start(), match.end(), match.group(0)))
        return "\x00EMOJI\x00"
    
    # Replace emojis with placeholder
    text_with_placeholders = _CUSTOM_EMOJI_RE.sub(extract_emoji, text)
    
    # Remove standard Unicode emojis (protected emojis are now placeholders)
    text_with_placeholders = _EMOJI_RE.sub("", text_with_placeholders)
    # Remove variation selectors
    text_with_placeholders = _VARIATION_RE.sub("", text_with_placeholders)
    
    # Apply styling cleanup (sans toucher les emojis car ils sont en placeholder)
    text_with_placeholders = text_with_placeholders.replace("\r\n", "\n").replace("\r", "\n")
    text_with_placeholders = _WHITESPACE_RE.sub(" ", text_with_placeholders)
    text_with_placeholders = _MULTILINE_RE.sub("\n\n", text_with_placeholders)
    text_with_placeholders = text_with_placeholders.strip()
    
    # Reinsert emojis at their original positions
    result = text_with_placeholders
    for _, _, emoji in reversed(emojis):  # reversed to not mess up positions
        result = result.replace("\x00EMOJI\x00", emoji, 1)
    
    return result or None


def _wrap_with_border(text: str | None) -> str:
    if not text:
        return ""
    return text


def translation_embed_title(language_code: str | None) -> str:
    from bot.utils.i18n import i18n
    return i18n.get("common.translation_title", language_code)


def style_embed(embed: discord.Embed) -> discord.Embed:
    """Clean embed text while preserving Discord custom emojis from styling issues."""
    from bot.config import COLOR_SUCCESS  # Use default color if not set

    if embed.title:
        embed.title = _preserve_emojis_during_styling(embed.title) or embed.title

    if embed.description:
        embed.description = _preserve_emojis_during_styling(embed.description) or embed.description

    if embed.author.name:
        name = _preserve_emojis_during_styling(embed.author.name)
        if name:
            embed.set_author(name=name, icon_url=embed.author.icon_url)

    for index, field in enumerate(list(embed.fields)):
        name = _preserve_emojis_during_styling(field.name) or "\u200b"
        value = _preserve_emojis_during_styling(field.value) or "-"
        embed.set_field_at(index, name=name, value=value, inline=field.inline)

    if not embed.color:
        embed.color = discord.Color(COLOR_SUCCESS)

    if embed.footer.text:
        footer_text = _preserve_emojis_during_styling(embed.footer.text)
        if footer_text:
            embed.set_footer(text=footer_text, icon_url=embed.footer.icon_url)
        else:
            embed.set_footer(text=None, icon_url=embed.footer.icon_url)

    return embed


async def send_localized_embed(
    ctx_or_interaction: discord.Interaction | commands.Context,
    key: str,
    locale: str = None,
    color: discord.Color = None,
    ephemeral: bool = False,
    view: discord.ui.View = None,
    **kwargs
) -> discord.Message | None:
    """
    Sends a styled, localized embed to a channel or interaction.
    Automatically handles locale detection from the interaction or provided locale.
    """
    from bot.utils.i18n import i18n
    
    # Detect locale
    if not locale:
        if isinstance(ctx_or_interaction, discord.Interaction):
            locale = str(ctx_or_interaction.locale)
        elif hasattr(ctx_or_interaction, "interaction") and ctx_or_interaction.interaction:
             locale = str(ctx_or_interaction.interaction.locale)
        else:
            # Fallback to DB or default
            locale = "fr"

    title = i18n.get(f"{key}.title", locale, **kwargs)
    desc = i18n.get(f"{key}.description", locale, **kwargs)
    
    # If the key itself is returned, it means title/desc don't exist under that key
    # In that case, we might just use the key as a direct string key
    if title == f"{key}.title":
        title = None
        desc = i18n.get(key, locale, **kwargs)

    embed = discord.Embed(title=title, description=desc)
    if color:
        embed.color = color
    
    style_embed(embed)

    send_kwargs: dict = {"embed": embed}
    if view is not None:
        send_kwargs["view"] = view

    if isinstance(ctx_or_interaction, discord.Interaction):
        send_kwargs["ephemeral"] = ephemeral
        if ctx_or_interaction.response.is_done():
            return await ctx_or_interaction.followup.send(**send_kwargs)
        return await ctx_or_interaction.response.send_message(**send_kwargs)

    return await ctx_or_interaction.send(**send_kwargs)


def _normalize_lang(code: str | None, fallback: str = "en") -> str:
    if not code:
        return fallback
    code = code.lower().replace("_", "-")
    if "-" in code:
        code = code.split("-")[0]
    return code
