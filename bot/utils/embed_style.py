"""Embed styling helpers: remove emojis and apply a visible frame."""

from __future__ import annotations

import re
import discord

_CUSTOM_EMOJI_RE = re.compile(r"<a?:[A-Za-z0-9_]+:\d+>")
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


def strip_emojis(text: str | None) -> str | None:
    if text is None:
        return None

    cleaned = _CUSTOM_EMOJI_RE.sub("", text)
    cleaned = _EMOJI_RE.sub("", cleaned)
    cleaned = _VARIATION_RE.sub("", cleaned)
    cleaned = cleaned.replace("\r\n", "\n").replace("\r", "\n")
    cleaned = _WHITESPACE_RE.sub(" ", cleaned)
    cleaned = _MULTILINE_RE.sub("\n\n", cleaned)
    cleaned = cleaned.strip()
    return cleaned or None


def _wrap_with_border(text: str | None) -> str:
    if not text:
        return "_____"
    if text.startswith("_____\n") and text.endswith("\n_____"):
        return text
    return f"_____\n\n{text}\n\n_____"


def style_embed(embed: discord.Embed) -> discord.Embed:
    """Remove emojis from an embed and add a consistent text border."""
    if embed.title:
        embed.title = strip_emojis(embed.title) or None

    if embed.description:
        embed.description = _wrap_with_border(strip_emojis(embed.description))
    else:
        embed.description = "_____"

    if embed.author.name:
        name = strip_emojis(embed.author.name)
        if name:
            embed.set_author(name=name, icon_url=embed.author.icon_url)

    for index, field in enumerate(list(embed.fields)):
        name = strip_emojis(field.name) or "\u200b"
        value = strip_emojis(field.value) or "-"
        embed.set_field_at(index, name=name, value=value, inline=field.inline)

    if embed.fields:
        first = embed.fields[0]
        if not (first.name == "\u200b" and first.value == "_____"):
            embed.insert_field_at(0, name="\u200b", value="_____", inline=False)

        last = embed.fields[-1]
        if not (last.name == "\u200b" and last.value == "_____"):
            embed.add_field(name="\u200b", value="_____", inline=False)

    if embed.footer.text:
        footer_text = strip_emojis(embed.footer.text)
        if footer_text:
            embed.set_footer(text=footer_text, icon_url=embed.footer.icon_url)
        else:
            embed.set_footer(text="", icon_url=embed.footer.icon_url)

    return embed

