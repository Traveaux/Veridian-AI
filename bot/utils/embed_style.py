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

_TRANSLATION_TITLES = {
    "fr": "Traduction automatique dans la langue de l'utilisateur",
    "en": "Automatic translation in the user's language",
    "es": "Traducción automática al idioma del usuario",
    "de": "Automatische Übersetzung in die Sprache des Nutzers",
    "it": "Traduzione automatica nella lingua dell'utente",
    "pt": "Tradução automática na língua do utilizador",
    "nl": "Automatische vertaling in de taal van de gebruiker",
    "ru": "Автоматический перевод на язык пользователя",
    "zh": "自动翻译为用户语言",
    "ja": "ユーザーの言語への自動翻訳",
    "ar": "الترجمة التلقائية إلى لغة المستخدم",
    "pl": "Automatyczne tłumaczenie na język użytkownika",
    "th": "แปลอัตโนมัติเป็นภาษาของผู้ใช้",
    "bn": "ব্যবহারকারীর ভাষায় স্বয়ংক্রিয় অনুবাদ",
    "ko": "사용자 언어로의 자동 번역",
    "hi": "उपयोगकर्ता की भाषा में स्वचालित अनुवाद",
}


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
    return f"_____\n{text}"


def translation_embed_title(language_code: str | None) -> str:
    code = (language_code or "").strip().lower()
    if not code:
        return _TRANSLATION_TITLES["fr"]
    base = code.split("-")[0]
    return _TRANSLATION_TITLES.get(base, _TRANSLATION_TITLES["en"])


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

    if embed.footer.text:
        footer_text = strip_emojis(embed.footer.text)
        if footer_text:
            if footer_text.endswith("_____"):
                footer_value = footer_text
            else:
                footer_value = f"{footer_text}\n_____"
            embed.set_footer(text=footer_value, icon_url=embed.footer.icon_url)
        else:
            embed.set_footer(text="_____", icon_url=embed.footer.icon_url)
    else:
        embed.set_footer(text="_____")

    return embed
