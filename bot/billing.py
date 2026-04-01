"""
Catalogue billing centralise pour Veridian AI.
"""

from __future__ import annotations

from copy import deepcopy


LEGACY_PLAN_ALIASES = {
    "premium": "starter",
}

VALID_INTERVALS = {"month", "year"}


PLAN_CATALOG = {
    "free": {
        "label": "Free",
        "monthly_price": 0.0,
        "annual_price": 0.0,
        "badge": None,
        "highlighted": False,
        "limits": {
            "tickets_per_month": 50,
            "languages": 5,
            "kb_entries": 10,
            "features": ["tickets", "public_support", "knowledge_base"],
        },
    },
    "starter": {
        "label": "Starter",
        "monthly_price": 4.0,
        "annual_price": 36.0,
        "badge": None,
        "highlighted": False,
        "limits": {
            "tickets_per_month": 500,
            "languages": 20,
            "kb_entries": 50,
            "features": [
                "tickets",
                "public_support",
                "translations",
                "transcriptions",
                "dashboard",
            ],
        },
    },
    "pro": {
        "label": "Pro",
        "monthly_price": 12.0,
        "annual_price": 108.0,
        "badge": "Most Popular",
        "highlighted": True,
        "limits": {
            "tickets_per_month": None,
            "languages": None,
            "kb_entries": None,
            "features": [
                "tickets",
                "public_support",
                "translations",
                "transcriptions",
                "dashboard",
                "suggestions",
                "advanced_stats",
                "snippets",
                "round_robin",
            ],
        },
    },
    "business": {
        "label": "Business",
        "monthly_price": 29.0,
        "annual_price": 261.0,
        "badge": "Advanced Ops",
        "highlighted": False,
        "limits": {
            "tickets_per_month": None,
            "languages": None,
            "kb_entries": None,
            "features": [
                "tickets",
                "public_support",
                "translations",
                "transcriptions",
                "dashboard",
                "suggestions",
                "advanced_stats",
                "snippets",
                "round_robin",
                "sla",
                "webhooks",
                "white_label",
            ],
        },
    },
}


ADDON_CATALOG = {
    "server_extra": {
        "label": "Serveur extra",
        "monthly_price": 9.0,
        "annual_price": 81.0,
    },
    "white_label": {
        "label": "White-label",
        "monthly_price": 19.0,
        "annual_price": 171.0,
    },
    "ai_tokens": {
        "label": "Tokens IA",
        "monthly_price": 10.0,
        "annual_price": 90.0,
    },
}


PAYMENT_METHODS = {
    "oxapay": {
        "label": "Crypto (OxaPay)",
        "mode": "checkout",
        "automated": True,
        "priority": 1,
    },
    "paypal": {
        "label": "PayPal",
        "mode": "manual",
        "automated": False,
        "priority": 2,
    },
    "giftcard": {
        "label": "Carte cadeau",
        "mode": "manual",
        "automated": False,
        "priority": 3,
    },
}


PLAN_TIERS = list(PLAN_CATALOG.keys())
PLAN_LIMITS = {plan_id: deepcopy(plan["limits"]) for plan_id, plan in PLAN_CATALOG.items()}
PRICING = {plan_id: float(plan["monthly_price"]) for plan_id, plan in PLAN_CATALOG.items() if plan_id != "free"}


def normalize_plan(plan: str | None, default: str = "free") -> str:
    raw = str(plan or "").strip().lower()
    if not raw:
        return default
    raw = LEGACY_PLAN_ALIASES.get(raw, raw)
    return raw if raw in PLAN_CATALOG else default


def normalize_interval(interval: str | None, default: str = "month") -> str:
    raw = str(interval or "").strip().lower()
    if raw in {"monthly", "month"}:
        return "month"
    if raw in {"annual", "annually", "yearly", "year"}:
        return "year"
    return default


def is_paid_plan(plan: str | None) -> bool:
    return normalize_plan(plan) != "free"


def get_plan_config(plan: str | None) -> dict:
    return deepcopy(PLAN_CATALOG[normalize_plan(plan)])


def get_plan_limits(plan: str | None) -> dict:
    return deepcopy(PLAN_LIMITS[normalize_plan(plan)])


def get_plan_price(plan: str | None, interval: str = "month") -> float:
    normalized_plan = normalize_plan(plan)
    normalized_interval = normalize_interval(interval)
    if normalized_plan == "free":
        return 0.0
    key = "annual_price" if normalized_interval == "year" else "monthly_price"
    return float(PLAN_CATALOG[normalized_plan][key])


def get_plan_label(plan: str | None) -> str:
    return str(PLAN_CATALOG[normalize_plan(plan)]["label"])


def get_interval_label(interval: str | None) -> str:
    return "annual" if normalize_interval(interval) == "year" else "monthly"


def get_public_catalog() -> dict:
    plans = []
    for plan_id in ("free", "starter", "pro", "business"):
        item = deepcopy(PLAN_CATALOG[plan_id])
        item["id"] = plan_id
        item["intervals"] = {
            "month": float(item["monthly_price"]),
            "year": float(item["annual_price"]),
        }
        plans.append(item)

    methods = []
    for method_id, item in sorted(PAYMENT_METHODS.items(), key=lambda x: x[1]["priority"]):
        row = deepcopy(item)
        row["id"] = method_id
        methods.append(row)

    addons = []
    for addon_id, item in ADDON_CATALOG.items():
        row = deepcopy(item)
        row["id"] = addon_id
        row["intervals"] = {
            "month": float(item["monthly_price"]),
            "year": float(item["annual_price"]),
        }
        addons.append(row)

    return {
        "default_plan": "starter",
        "default_interval": "month",
        "default_method": "oxapay",
        "annual_discount_percent": 25,
        "plans": plans,
        "methods": methods,
        "addons": addons,
    }


def get_default_duration_days(interval: str | None) -> int:
    return 365 if normalize_interval(interval) == "year" else 30
