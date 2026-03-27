"""
Constantes globales du projet Veridian AI v0.2
"""

# Version
VERSION = "1.0.0"
VERSION_EMOJI = "🤖"

# --- Visual Identity (Veridian Green) ---
# Discord Colors (int)
COLOR_SUCCESS  = 0x2DFF8F  # Low importance / Success
COLOR_NOTICE   = 0x00E676  # Medium importance / Info
COLOR_WARNING  = 0x008037  # High importance / Admin
COLOR_CRITICAL = 0x004D40  # Very high / Error / Security

# Emojis (fallback texte) + assets pour embeds
EMOJI_SUCCESS  = "✅"
EMOJI_WARNING  = "⚠️"
EMOJI_TICKET   = "🎫"
EMOJI_AI_API   = "🤖"
EMOJI_AI_CACHE = "💎"
EMOJI_LOADING  = "⌛"
EMOJI_ADMIN    = "🛡️"
EMOJI_STAFF    = "⭐"
EMOJI_AI       = EMOJI_AI_API  # Compat historique

# Syntax pour emojis animés (Remplacez l'ID par le vôtre après l'avoir récupéré via \:emoji:)
EMOJI_ANIM_TICKET = "<a:ticket:1342939103901749320>"

EMOJI_URL_WARNING  = "https://cdn3.emoji.gg/emojis/94735-warning.gif"
EMOJI_URL_TICKET   = "https://cdn3.emoji.gg/emojis/437007-ticket.gif"
EMOJI_URL_AI_API   = "https://cdn3.emoji.gg/emojis/77397-bot-mint-shiny.png"
EMOJI_URL_AI_CACHE = "https://cdn3.emoji.gg/emojis/58354-bot-blue-shiny.png"
EMOJI_URL_LOADING  = "https://cdn3.emoji.gg/emojis/2908-loading.gif"
EMOJI_URL_ADMIN    = "https://cdn3.emoji.gg/emojis/731909-staffbadgegreen.png"

# Discord Configuration
BOT_OWNER_DISCORD_ID = 1047760053509312642
ADMIN_IDS            = [1047760053509312642]

# Bot Information
BOT_NAME       = "Veridian AI"
DOMAIN         = "veridiancloud.xyz"
API_DOMAIN     = "api.veridiancloud.xyz"
DASHBOARD_URL  = "https://veridiancloud.xyz/dashboard"

# Database Prefix
DB_TABLE_PREFIX = "vai_"

# Pricing (en EUR)
PRICING = {
    "premium": 2.00,
    "pro":     5.00
}

# Plan Tiers
PLAN_TIERS = ["free", "premium", "pro"]

# Limites par plan
PLAN_LIMITS = {
    "free": {
        "tickets_per_month": 50,
        "languages":         5,
        "kb_entries":        10,
        "features":          ["tickets", "public_support", "knowledge_base"]
    },
    "premium": {
        "tickets_per_month": 500,
        "languages":         20,
        "kb_entries":        50,
        "features":          ["tickets", "public_support", "translations", "transcriptions"]
    },
    "pro": {
        "tickets_per_month": None,   # Illimite
        "languages":         None,   # Toutes
        "kb_entries":        None,   # Illimite
        "features":          [
            "tickets", "public_support", "translations",
            "transcriptions", "suggestions", "advanced_stats"
        ]
    }
}

# Groq Models
GROQ_MODEL_FAST    = "llama-3.1-8b-instant"
GROQ_MODEL_QUALITY = "llama-3.3-70b-versatile"
GROQ_DEFAULT_MODEL = GROQ_MODEL_FAST

# System Prompts
SYSTEM_PROMPT_SUPPORT = (
    "Tu es Veridian AI, l'assistant IA du serveur Discord '{guild_name}'.\n"
    "Tu reponds uniquement aux questions liees au serveur.\n"
    "Reponds toujours dans la meme langue que l'utilisateur.\n"
    "Sois concis, professionnel et bienveillant.\n"
    "Si tu ne sais pas, dis-le et suggere d'ouvrir un ticket."
)

SYSTEM_PROMPT_TICKET_SUMMARY = (
    "Tu es un assistant de support. Voici la conversation d'un ticket de support Discord.\n"
    "Genere un resume structure :\n"
    "1. PROBLEME : Ce que l'utilisateur demandait (1-2 phrases)\n"
    "2. RESOLUTION : Comment le probleme a ete resolu (1-2 phrases)\n"
    "3. STATUT : Resolu / Non resolu / Partiel\n"
    "Reponds dans la langue : {ticket_language}"
)

# OxaPay
OXAPAY_BASE_URL                      = "https://api.oxapay.com"
OXAPAY_MERCHANTS_REQUEST_ENDPOINT    = "/merchants/request"

# Tickets
TICKET_ARCHIVE_DELAY_HOURS = 24
TICKET_CHANNEL_PREFIX      = "ticket"
MIN_MESSAGE_LENGTH         = 3

# Cache traductions
TRANSLATION_CACHE_HIT_THRESHOLD = 10

# Logging
LOG_LEVEL = "INFO"
