"""
Constantes globales du projet Veridian AI v0.2
"""

from bot.billing import PLAN_LIMITS, PLAN_TIERS, PRICING

# Version
VERSION = "1.0.0"

# --- Visual Identity (Veridian Green) ---
# Discord Colors (int)
COLOR_SUCCESS  = 0x2DFF8F  # Low importance / Success
COLOR_NOTICE   = 0x00E676  # Medium importance / Info
COLOR_WARNING  = 0x008037  # High importance / Admin
COLOR_CRITICAL = 0x004D40  # Very high / Error / Security

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

# Pricing / plan limits centralises dans `bot.billing`.

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
    "N'utilise pas d'emojis.\n"
    "Si tu ne sais pas, dis-le et suggere d'ouvrir un ticket."
)

SYSTEM_PROMPT_TICKET_SUMMARY = (
    "Tu es un assistant de support. Voici la conversation d'un ticket de support Discord.\n"
    "Genere un resume structure :\n"
    "1. PROBLEME : Ce que l'utilisateur demandait (1-2 phrases)\n"
    "2. RESOLUTION : Comment le probleme a ete resolu (1-2 phrases)\n"
    "3. STATUT : Resolu / Non resolu / Partiel\n"
    "N'utilise pas d'emojis.\n"
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
