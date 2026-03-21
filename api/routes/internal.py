"""
API Interne - Routes dashboard <-> bot
Toute la configuration passe par ici, plus de commandes bot admin.
"""

from fastapi import APIRouter, Depends, HTTPException, Header, Request
from pydantic import BaseModel
from typing import Optional, List
from bot.db.connection import get_db_context
from bot.db.models import (
    GuildModel, TicketModel, UserModel, SubscriptionModel,
    OrderModel, PaymentModel, KnowledgeBaseModel, AuditLogModel,
    BotStatusModel, TicketMessageModel
)
from bot.config import PLAN_LIMITS, DB_TABLE_PREFIX
from loguru import logger
import os
import jwt as pyjwt

router = APIRouter(prefix="/internal", tags=["internal"])

from api.security import get_jwt_secret
from api.security import is_production

SNOWFLAKE_FIELDS = {
    "id",
    "support_channel_id",
    "ticket_category_id",
    "staff_role_id",
    "log_channel_id",
    "welcome_channel_id",
    "ticket_open_channel_id",
    "ticket_open_message_id",
}


def _snowflake_to_str(v):
    if v in (None, ""):
        return None
    try:
        return str(int(v))
    except Exception:
        return None


def _serialize_guild_config_for_dashboard(guild: dict) -> dict:
    out = dict(guild or {})
    for key in SNOWFLAKE_FIELDS:
        if key in out:
            out[key] = _snowflake_to_str(out.get(key))
    return out


# ============================================================================
# Auth middleware
# ============================================================================

def _decode_jwt(token: str) -> dict:
    """Decode and validate a JWT token. Returns payload or raises HTTPException."""
    try:
        secret = get_jwt_secret()
        return pyjwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="veridian-dashboard",
            issuer="veridian-api",
        )
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expire")
    except pyjwt.InvalidTokenError as e:
        # Log debug info server-side (do NOT log the token itself).
        try:
            parts = token.split(".")
            logger.warning(
                f"JWT invalide: {type(e).__name__}: {str(e)[:120]} "
                f"(len={len(token)}, parts={len(parts)})"
            )
        except Exception:
            pass
        raise HTTPException(status_code=401, detail="Token invalide")


def verify_internal_auth(request: Request, x_api_secret: str = Header(None)) -> dict:
    """
    Authentification double pour les routes internes :
      - X-API-SECRET : communication bot → API (secret serveur)
      - Authorization: Bearer JWT : communication dashboard → API
    Retourne un dict avec is_super_admin et user_id.
    """
    # 1. Secret interne (bot ou service serveur)
    expected = os.getenv("INTERNAL_API_SECRET")
    if x_api_secret and expected and x_api_secret == expected:
        request.state.user_id = 0
        request.state.is_super_admin = True
        request.state.guild_ids = None
        return {"is_bot": True, "is_super_admin": True, "user_id": 0}

    # 2. JWT Bearer (dashboard utilisateur)
    # Some reverse proxies / CDNs may strip the standard Authorization header.
    # The dashboard also sends `X-VAI-Authorization` as a fallback.
    auth_header = request.headers.get("Authorization", "") or ""
    alt_header = request.headers.get("X-VAI-Authorization", "") or ""

    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    elif alt_header.startswith("Bearer "):
        token = alt_header[7:]
    elif alt_header:
        # Allow raw token value in the fallback header.
        token = alt_header.strip()

    if token:

        # Enforce server-side revocation/expiry via DB.
        try:
            from bot.db.models import DashboardSessionModel
            try:
                status = DashboardSessionModel.token_status(token)
            except Exception as e:
                logger.warning(f"Session status check error: {e}")
                status = "missing"

            if status in {"revoked", "expired"}:
                raise HTTPException(status_code=401, detail="Session invalide ou revoquee")

            # If the session row is missing, we still allow a valid JWT (stateless mode).
            # Revocation will only work when the DB session row exists and is marked revoked.
            if status == "missing" and is_production():
                logger.warning("Session manquante en DB pour un JWT valide (stateless fallback).")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Session check error: {e}")
            # Keep JWT auth working even if the session table/schema is drifting.
            # Revocation won't be enforced in that case.

        payload = _decode_jwt(token)
        try:
            user_id = int(payload.get("sub", 0) or 0)
        except Exception:
            user_id = 0

        # Prefer server-side guild allowlist stored in the dashboard session row.
        guild_ids = None
        try:
            from bot.db.models import DashboardSessionModel
            guild_ids = DashboardSessionModel.allowed_guild_ids(token)
        except Exception:
            guild_ids = None

        if guild_ids is None:
            guild_ids = payload.get("guild_ids", [])

        request.state.user_id = user_id
        request.state.is_super_admin = bool(payload.get("is_super_admin", False))
        request.state.guild_ids = guild_ids
        return {
            "is_bot": False,
            "is_super_admin": request.state.is_super_admin,
            "user_id": user_id,
            "guild_ids": guild_ids,
        }

    raise HTTPException(status_code=401, detail="Unauthorized")


def verify_super_admin(request: Request, x_api_secret: str = Header(None)) -> dict:
    """
    Restreint l'accès aux routes Super Admin uniquement.
    Accepte le secret bot OU un JWT avec is_super_admin=True.
    """
    auth = verify_internal_auth(request, x_api_secret)
    if not auth.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="Acces reserve au Super Admin")
    return auth


def verify_guild_access(
    guild_id: int,
    request: Request,
    x_api_secret: str = Header(None),
) -> dict:
    """
    Ensures the authenticated dashboard user is allowed to access `guild_id`.
    Bot/internal secret bypasses this check.
    """
    auth = verify_internal_auth(request, x_api_secret)
    if auth.get("is_bot") or auth.get("is_super_admin"):
        return auth

    allowed = auth.get("guild_ids") or []
    try:
        gid = int(guild_id)
    except Exception:
        raise HTTPException(status_code=400, detail="guild_id invalide")

    # Normalize allowed guild ids to ints.
    norm_allowed = set()
    for x in allowed:
        try:
            norm_allowed.add(int(x))
        except Exception:
            pass

    if gid not in norm_allowed:
        raise HTTPException(status_code=403, detail="Acces refuse a ce serveur")

    return auth


# ============================================================================
# Pydantic models
# ============================================================================

class GuildConfigBody(BaseModel):
    name:                        Optional[str]  = None
    support_channel_id:          Optional[int]  = None
    ticket_category_id:          Optional[int]  = None
    staff_role_id:               Optional[int]  = None
    log_channel_id:              Optional[int]  = None
    welcome_channel_id:          Optional[int]  = None
    default_language:            Optional[str]  = None
    auto_translate:              Optional[bool] = None
    public_support:              Optional[bool] = None
    auto_transcript:             Optional[bool] = None
    ai_moderation:               Optional[bool] = None
    staff_suggestions:           Optional[bool] = None
    # Ticket system v0.4
    ticket_open_channel_id:      Optional[int]  = None
    ticket_open_message:         Optional[str]  = None
    ticket_button_label:         Optional[str]  = None
    ticket_button_style:         Optional[str]  = None
    ticket_button_emoji:         Optional[str]  = None
    ticket_welcome_message:      Optional[str]  = None
    ticket_welcome_color:        Optional[str]  = None
    ticket_selector_enabled:     Optional[bool] = None
    ticket_selector_placeholder: Optional[str]  = None
    ticket_selector_options:     Optional[str]  = None  # JSON string
    ticket_mention_staff:        Optional[bool] = None
    ticket_close_on_leave:       Optional[bool] = None
    ticket_max_open:             Optional[int]  = None
    staff_languages_json:        Optional[str]  = None  # JSON string
    # AI Support custom v0.4
    ai_custom_prompt:            Optional[str]  = None
    ai_prompt_enabled:           Optional[bool] = None


class OrderStatusBody(BaseModel):
    status:        str
    admin_note:    Optional[str] = None
    validated_by:  Optional[int] = None
    plan:          Optional[str] = None


class ActivateSubBody(BaseModel):
    guild_id:      int
    plan:          str
    duration_days: int = 30


class RevokeSubBody(BaseModel):
    guild_id: int


class KBEntryBody(BaseModel):
    question:   str
    answer:     str
    category:   Optional[str] = None
    created_by: Optional[int] = None


class TicketPriorityBody(BaseModel):
    priority: str


# ============================================================================
# Health
# ============================================================================

@router.get("/health", dependencies=[Depends(verify_internal_auth)])
def health_check():
    try:
        with get_db_context():
            return {"status": "ok", "service": "internal-api"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Database error: {str(e)}")


# ============================================================================
# Guild config - lu et ecrit exclusivement par le dashboard
# ============================================================================

@router.get("/guild/{guild_id}/config", dependencies=[Depends(verify_guild_access)])
def get_guild_config(guild_id: int):
    guild = GuildModel.get(guild_id)
    if not guild:
        # Return a sane default config so the dashboard can still render.
        return _serialize_guild_config_for_dashboard({
            "id": guild_id,
            "name": None,
            "tier": "free",
            "support_channel_id": None,
            "ticket_category_id": None,
            "staff_role_id": None,
            "log_channel_id": None,
            "welcome_channel_id": None,
            "default_language": "en",
            "auto_translate": 1,
            "public_support": 1,
            "auto_transcript": 1,
            "ai_moderation": 0,
            "staff_suggestions": 0,
            # Ticket v0.4 defaults
            "ticket_open_channel_id": None,
            "ticket_open_message": "",
            "ticket_button_label": "Ouvrir un ticket",
            "ticket_button_style": "primary",
            "ticket_button_emoji": "",
            "ticket_welcome_message": "",
            "ticket_welcome_color": "blue",
            "ticket_selector_enabled": 0,
            "ticket_selector_placeholder": "Selectionnez le type de ticket",
            "ticket_selector_options": "[]",
            "ticket_mention_staff": 1,
            "ticket_close_on_leave": 0,
            "ticket_max_open": 1,
            "staff_languages_json": "[]",
            # AI v0.4 defaults
            "ai_custom_prompt": "",
            "ai_prompt_enabled": 0,
        })
    return _serialize_guild_config_for_dashboard(guild)


@router.put("/guild/{guild_id}/config", dependencies=[Depends(verify_guild_access)])
def update_guild_config(guild_id: int, body: GuildConfigBody, request: Request):
    guild = GuildModel.get(guild_id)
    if not guild:
        # Create the row if it doesn't exist yet (ex: bot not added yet or DB cleared).
        GuildModel.create(guild_id, body.name or f"Guild {guild_id}")

    # Keep explicit nulls to allow clearing fields from the dashboard UI.
    updates = dict(body.dict(exclude_unset=True).items())
    # Convertir bool -> int pour MySQL
    for k, v in updates.items():
        if isinstance(v, bool):
            updates[k] = int(v)

    if not updates:
        return {"status": "no_changes"}

    GuildModel.update(guild_id, **updates)

    # Audit log
    actor_id = getattr(request.state, "user_id", None)
    AuditLogModel.log(
        actor_id=actor_id or 0,
        action="guild.config",
        guild_id=guild_id,
        details=updates,
        ip_address=request.client.host if request.client else None
    )

    return {"status": "success", "guild_id": guild_id, "updated": list(updates.keys())}


# ============================================================================
# Tickets
# ============================================================================

@router.post("/guild/{guild_id}/tickets/open-message/deploy", dependencies=[Depends(verify_guild_access)])
def deploy_ticket_open_message(guild_id: int, body: GuildConfigBody, request: Request):
    """Déploie le message d'ouverture de tickets dans un channel.

    Le dashboard envoie les champs ticket_open_* (message/bouton/sélecteur).
    Le bot consommera cet endpoint via un internal route (bot-side) ou l'API
    enverra un ordre au bot (selon votre infra). Ici on persiste d'abord en DB
    puis on émet un événement best-effort via une table/queue si dispo.

    NOTE: pour l'instant, on persiste seulement. Le bot peut avoir un /sync
    ou un poll, ou vous pouvez implémenter un webhook/WS plus tard.
    """
    # Persist config first
    updates = dict(body.dict(exclude_unset=True).items())
    for k, v in updates.items():
        if isinstance(v, bool):
            updates[k] = int(v)

    if updates:
        # Mark for bot deployment (poller)
        updates["ticket_open_needs_deploy"] = 1
        GuildModel.update(guild_id, **updates)

    # Audit log
    actor_id = getattr(request.state, "user_id", None)
    AuditLogModel.log(
        actor_id=actor_id or 0,
        action="tickets.open_message.deploy",
        guild_id=guild_id,
        details=updates,
        ip_address=request.client.host if request.client else None
    )

    # Best-effort: mark a 'needs_deploy' flag in DB if you later add it.
    return {"status": "queued", "guild_id": guild_id}


@router.post("/guild/{guild_id}/tickets/open-message/delete", dependencies=[Depends(verify_guild_access)])
def request_delete_ticket_open_message(guild_id: int, request: Request):
    # Mark delete requested; bot will delete and clear message_id.
    updates = {"ticket_open_delete_requested": 1}
    GuildModel.update(guild_id, **updates)

    actor_id = getattr(request.state, "user_id", None)
    AuditLogModel.log(
        actor_id=actor_id or 0,
        action="tickets.open_message.delete",
        guild_id=guild_id,
        details=updates,
        ip_address=request.client.host if request.client else None
    )

    return {"status": "queued", "guild_id": guild_id}


@router.get("/guild/{guild_id}/tickets", dependencies=[Depends(verify_guild_access)])
def get_guild_tickets(guild_id: int, status: Optional[str] = None,
                      page: int = 1, limit: int = 50):
    tickets = TicketModel.get_by_guild(guild_id, status=status, page=page, limit=limit)
    total   = TicketModel.count_by_guild(guild_id, status=status)
    return {
        "guild_id": guild_id,
        "total":    total,
        "page":     page,
        "limit":    limit,
        "tickets":  tickets
    }


@router.get("/ticket/{ticket_id}", dependencies=[Depends(verify_internal_auth)])
def get_ticket(ticket_id: int, request: Request):
    ticket = TicketModel.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    # Enforce ticket guild access for non-super-admin users.
    if not getattr(request.state, "is_super_admin", False):
        allowed = getattr(request.state, "guild_ids", None)
        if allowed is not None:
            norm_allowed = set()
            for x in (allowed or []):
                try:
                    norm_allowed.add(int(x))
                except Exception:
                    pass
            if int(ticket.get("guild_id", 0)) not in norm_allowed:
                raise HTTPException(status_code=403, detail="Acces refuse a ce ticket")
    return ticket


@router.get("/ticket/{ticket_id}/transcript", dependencies=[Depends(verify_internal_auth)])
def get_ticket_transcript(ticket_id: int, request: Request):
    ticket = TicketModel.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not getattr(request.state, "is_super_admin", False):
        allowed = getattr(request.state, "guild_ids", None)
        if allowed is not None:
            norm_allowed = set()
            for x in (allowed or []):
                try:
                    norm_allowed.add(int(x))
                except Exception:
                    pass
            if int(ticket.get("guild_id", 0)) not in norm_allowed:
                raise HTTPException(status_code=403, detail="Acces refuse a ce ticket")
    messages = TicketMessageModel.get_by_ticket(ticket_id)
    return {
        "ticket_id":  ticket_id,
        "guild_id":   ticket.get("guild_id"),
        "user_id":    ticket.get("user_id"),
        "status":     ticket.get("status"),
        "transcript": ticket.get("transcript"),
        "messages":   messages,
        "opened_at":  str(ticket.get("opened_at")) if ticket.get("opened_at") else None,
        "closed_at":  str(ticket.get("closed_at")) if ticket.get("closed_at") else None
    }


@router.post("/ticket/{ticket_id}/close", dependencies=[Depends(verify_internal_auth)])
def close_ticket_dashboard(ticket_id: int, request: Request):
    ticket = TicketModel.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not getattr(request.state, "is_super_admin", False):
        allowed = getattr(request.state, "guild_ids", None)
        if allowed is not None:
            norm_allowed = set()
            for x in (allowed or []):
                try:
                    norm_allowed.add(int(x))
                except Exception:
                    pass
            if int(ticket.get("guild_id", 0)) not in norm_allowed:
                raise HTTPException(status_code=403, detail="Acces refuse a ce ticket")
    TicketModel.close(ticket_id, close_reason="Ferme depuis le dashboard")
    actor_id = getattr(request.state, "user_id", None)
    AuditLogModel.log(actor_id=actor_id or 0, action="ticket.close",
                      guild_id=ticket["guild_id"], target_id=str(ticket_id))
    return {"status": "success", "ticket_id": ticket_id}


@router.put("/ticket/{ticket_id}/priority", dependencies=[Depends(verify_internal_auth)])
def update_ticket_priority(ticket_id: int, body: TicketPriorityBody, request: Request):
    """
    Met à jour la priorité d'un ticket (bas, moyen, haut, prioritaire)
    depuis le dashboard ou un outil interne.
    """
    ticket = TicketModel.get(ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    # Vérifier l'accès à la guild du ticket pour les utilisateurs non super-admin.
    if not getattr(request.state, "is_super_admin", False):
        allowed = getattr(request.state, "guild_ids", None)
        if allowed is not None:
            norm_allowed = set()
            for x in (allowed or []):
                try:
                    norm_allowed.add(int(x))
                except Exception:
                    pass
            if int(ticket.get("guild_id", 0)) not in norm_allowed:
                raise HTTPException(status_code=403, detail="Acces refuse a ce ticket")

    raw = (body.priority or "").strip().lower()
    # Normalisation vers les 4 valeurs internes supportées.
    mapping = {
        "bas": "low",
        "low": "low",
        "basse": "low",
        "moyen": "medium",
        "moyenne": "medium",
        "medium": "medium",
        "haut": "high",
        "haute": "high",
        "eleve": "high",
        "élevé": "high",
        "prioritaire": "urgent",
        "urgent": "urgent",
    }
    norm = mapping.get(raw, raw)
    if norm not in {"low", "medium", "high", "urgent"}:
        raise HTTPException(status_code=400, detail="Priorite invalide")

    TicketModel.update(ticket_id, priority=norm)

    actor_id = getattr(request.state, "user_id", None)
    AuditLogModel.log(
        actor_id=actor_id or 0,
        action="ticket.priority",
        guild_id=ticket.get("guild_id"),
        target_id=str(ticket_id),
        details={"priority": norm},
        ip_address=request.client.host if request.client else None,
    )

    return {"status": "success", "ticket_id": ticket_id, "priority": norm}


# ============================================================================
# Stats guild
# ============================================================================

@router.get("/guild/{guild_id}/stats", dependencies=[Depends(verify_guild_access)])
def get_guild_stats(guild_id: int):
    # Best-effort stats: avoid returning 500 on schema drift.
    try:
        open_tickets = TicketModel.count_by_guild(guild_id, status="open")
    except Exception:
        open_tickets = 0
    try:
        inprog_tickets = TicketModel.count_by_guild(guild_id, status="in_progress")
    except Exception:
        inprog_tickets = 0
    try:
        total_tickets = TicketModel.count_by_guild(guild_id)
    except Exception:
        total_tickets = 0
    try:
        tickets_month = TicketModel.count_this_month(guild_id)
    except Exception:
        tickets_month = 0
    try:
        languages = TicketModel.get_language_stats(guild_id)
    except Exception:
        languages = []
    try:
        daily_counts = TicketModel.get_daily_counts(guild_id, days=7)
    except Exception:
        daily_counts = []
    try:
        subscription = SubscriptionModel.get(guild_id)
    except Exception:
        subscription = None
    try:
        kb_count = KnowledgeBaseModel.count(guild_id)
    except Exception:
        kb_count = 0

    return {
        "guild_id":           guild_id,
        "open_tickets":       open_tickets,
        "in_progress_tickets": inprog_tickets,
        "total_tickets":      total_tickets,
        "tickets_month":      tickets_month,
        "languages":          languages,
        "daily_counts":       daily_counts,
        "current_plan":       subscription["plan"] if subscription else "free",
        "is_subscribed":      bool(subscription),
        "kb_entries":         kb_count
    }


# ============================================================================
# Orders
# ============================================================================

@router.get("/orders/pending", dependencies=[Depends(verify_super_admin)])
def get_pending_orders():
    orders = OrderModel.list_pending()
    return {"total": len(orders), "orders": orders}


@router.get("/orders", dependencies=[Depends(verify_super_admin)])
def get_orders(page: int = 1, limit: int = 50, status: Optional[str] = None):
    orders = OrderModel.list_all(page=page, limit=limit, status=status)
    return {"orders": orders, "page": page, "limit": limit}


@router.put("/orders/{order_id}/status", dependencies=[Depends(verify_super_admin)])
def update_order_status(order_id: str, body: OrderStatusBody, request: Request):
    order = OrderModel.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    actor_id = getattr(request.state, "user_id", None)

    OrderModel.update_status(
        order_id,
        status=body.status,
        admin_note=body.admin_note,
        validated_by=actor_id or body.validated_by
    )

    if body.status == "paid":
        plan = body.plan or order.get("plan", "premium")
        payment_id = PaymentModel.create(
            user_id=order["user_id"],
            guild_id=order["guild_id"],
            method=order["method"],
            amount=float(order["amount"] or 0),
            plan=plan,
            order_id=order_id,
            status="completed"
        )
        SubscriptionModel.create(
            guild_id=order["guild_id"],
            user_id=order["user_id"],
            plan=plan,
            payment_id=payment_id,
            duration_days=30
        )
        logger.info(f"Abonnement {plan} active pour guild {order['guild_id']}")

    AuditLogModel.log(
        actor_id=actor_id or 0,
        action=f"order.{body.status}",
        target_id=order_id,
        details={"plan": body.plan, "note": body.admin_note}
    )

    return {"status": "success", "order_id": order_id, "new_status": body.status}


# ============================================================================
# Subscriptions admin
# ============================================================================

@router.post("/admin/activate-sub", dependencies=[Depends(verify_super_admin)])
def activate_subscription(body: ActivateSubBody, request: Request):
    actor_id = getattr(request.state, "user_id", None)
    SubscriptionModel.create(
        guild_id=body.guild_id,
        user_id=0,
        plan=body.plan,
        duration_days=body.duration_days
    )
    AuditLogModel.log(
        actor_id=actor_id or 0,
        action="subscription.activate",
        guild_id=body.guild_id,
        details={"plan": body.plan, "duration_days": body.duration_days}
    )
    return {"status": "success", "guild_id": body.guild_id, "plan": body.plan}


@router.post("/revoke-sub", dependencies=[Depends(verify_super_admin)])
def revoke_subscription(body: RevokeSubBody, request: Request):
    actor_id = getattr(request.state, "user_id", None)
    SubscriptionModel.deactivate(body.guild_id)
    AuditLogModel.log(
        actor_id=actor_id or 0,
        action="subscription.revoke",
        guild_id=body.guild_id
    )
    return {"status": "success", "guild_id": body.guild_id}


# ============================================================================
# Knowledge Base
# ============================================================================

@router.get("/guild/{guild_id}/kb", dependencies=[Depends(verify_guild_access)])
def get_kb(guild_id: int):
    entries = KnowledgeBaseModel.get_by_guild(guild_id)
    limit   = PLAN_LIMITS.get(
        (SubscriptionModel.get(guild_id) or {}).get("plan", "free"), {}
    ).get("kb_entries", 0)
    return {
        "guild_id": guild_id,
        "total":    len(entries),
        "limit":    limit,
        "entries":  entries
    }


@router.post("/guild/{guild_id}/kb", dependencies=[Depends(verify_guild_access)])
def create_kb_entry(guild_id: int, body: KBEntryBody, request: Request):
    # Verifier la limite du plan
    sub   = SubscriptionModel.get(guild_id)
    plan  = (sub or {}).get("plan", "free")
    limit = PLAN_LIMITS.get(plan, {}).get("kb_entries", 0)
    current_count = KnowledgeBaseModel.count(guild_id)

    if limit is not None and current_count >= limit:
        raise HTTPException(
            status_code=403,
            detail=f"Limite KB atteinte ({current_count}/{limit}) pour le plan {plan}"
        )

    actor_id = getattr(request.state, "user_id", None)
    kb_id = KnowledgeBaseModel.create(
        guild_id=guild_id,
        question=body.question,
        answer=body.answer,
        category=body.category,
        created_by=actor_id or body.created_by
    )
    if not kb_id:
        raise HTTPException(status_code=500, detail="Erreur creation entree KB")

    AuditLogModel.log(
        actor_id=actor_id or 0,
        action="kb.create",
        guild_id=guild_id,
        target_id=str(kb_id),
        details={"question": body.question[:80]}
    )
    return {"status": "success", "id": kb_id}


@router.put("/guild/{guild_id}/kb/{kb_id}", dependencies=[Depends(verify_guild_access)])
def update_kb_entry(guild_id: int, kb_id: int, body: KBEntryBody, request: Request):
    entry = KnowledgeBaseModel.get(kb_id)
    if not entry or entry["guild_id"] != guild_id:
        raise HTTPException(status_code=404, detail="Entree KB non trouvee")

    KnowledgeBaseModel.update(kb_id, question=body.question, answer=body.answer,
                              category=body.category)
    actor_id = getattr(request.state, "user_id", None)
    AuditLogModel.log(actor_id=actor_id or 0, action="kb.update",
                      guild_id=guild_id, target_id=str(kb_id))
    return {"status": "success", "id": kb_id}


@router.delete("/guild/{guild_id}/kb/{kb_id}", dependencies=[Depends(verify_guild_access)])
def delete_kb_entry(guild_id: int, kb_id: int, request: Request):
    entry = KnowledgeBaseModel.get(kb_id)
    if not entry or entry["guild_id"] != guild_id:
        raise HTTPException(status_code=404, detail="Entree KB non trouvee")

    KnowledgeBaseModel.hard_delete(kb_id)
    actor_id = getattr(request.state, "user_id", None)
    AuditLogModel.log(actor_id=actor_id or 0, action="kb.delete",
                      guild_id=guild_id, target_id=str(kb_id))
    return {"status": "success"}


# ============================================================================
# Super Admin - statistiques globales
# ============================================================================

@router.get("/admin/stats", dependencies=[Depends(verify_super_admin)])
def get_global_stats():
    try:
        from bot.db.connection import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()

            def scalar(query: str, params: tuple = ()) -> float | int:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return 0 if not row else row[0]

            total_guilds = int(scalar(f"SELECT COUNT(*) FROM {DB_TABLE_PREFIX}guilds"))

            # "Utilisateurs" = comptes dashboard (OAuth) — fallback sur sessions/anciens schemas.
            dashboard_users_count = None
            session_users_count = None
            try:
                dashboard_users_count = int(scalar(f"SELECT COUNT(*) FROM {DB_TABLE_PREFIX}dashboard_users"))
            except Exception:
                pass

            try:
                session_users_count = int(scalar(
                    f"SELECT COUNT(DISTINCT discord_user_id) FROM {DB_TABLE_PREFIX}dashboard_sessions"
                ))
            except Exception:
                pass

            if dashboard_users_count is not None:
                total_users = max(dashboard_users_count, session_users_count or 0)
            elif session_users_count is not None:
                total_users = session_users_count
            else:
                total_users = int(scalar(f"SELECT COUNT(*) FROM {DB_TABLE_PREFIX}users"))

            tickets_today = int(scalar(
                f"SELECT COUNT(*) FROM {DB_TABLE_PREFIX}tickets WHERE DATE(opened_at) = CURDATE()"
            ))
            orders_pending = int(scalar(
                f"SELECT COUNT(*) FROM {DB_TABLE_PREFIX}orders WHERE status = 'pending'"
            ))
            revenue_month = float(scalar(
                f"SELECT COALESCE(SUM(amount), 0) FROM {DB_TABLE_PREFIX}payments "
                f"WHERE status = 'completed' "
                f"AND YEAR(paid_at) = YEAR(CURDATE()) "
                f"AND MONTH(paid_at) = MONTH(CURDATE())"
            ))
            active_subs = int(scalar(
                f"SELECT COUNT(*) FROM {DB_TABLE_PREFIX}subscriptions WHERE is_active = 1"
            ))

        bot_st = BotStatusModel.get() or {}

        return {
            "total_guilds":     total_guilds,
            "total_users":      total_users,
            "tickets_today":    tickets_today,
            "orders_pending":   orders_pending,
            "revenue_month":    revenue_month,
            "active_subs":      active_subs,
            "bot_is_online":    bot_st.get("is_online", False),
            "bot_guild_count":  bot_st.get("guild_count", 0),
            "bot_user_count":   bot_st.get("user_count", 0),
            "bot_channel_count": bot_st.get("channel_count", 0),
            "bot_uptime_sec":   bot_st.get("uptime_sec", 0),
            "bot_latency_ms":   round(float(bot_st.get("latency_ms", 0) or 0), 1),
            "bot_shard_count":  bot_st.get("shard_count", 1),
            "bot_version":      bot_st.get("version", "?"),
            "bot_started_at":   str(bot_st["started_at"]) if bot_st.get("started_at") else None,
        }
    except Exception as e:
        logger.error(f"Erreur admin stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/guilds", dependencies=[Depends(verify_super_admin)])
def get_all_guilds():
    guilds = GuildModel.get_all()
    return {"total": len(guilds), "guilds": guilds}


@router.get("/admin/audit", dependencies=[Depends(verify_super_admin)])
def get_audit_log(guild_id: Optional[int] = None, limit: int = 100):
    logs = AuditLogModel.get_recent(guild_id=guild_id, limit=limit)
    return {"logs": logs}


# ============================================================================
# Bot status (ecrit par le bot, lu par le dashboard)
# ============================================================================

@router.post("/bot/heartbeat", dependencies=[Depends(verify_internal_auth)])
def bot_heartbeat(guild_count: int = 0, user_count: int = 0,
                  uptime_sec: int = 0, version: str = "",
                  latency_ms: float = 0, shard_count: int = 1,
                  channel_count: int = 0):
    BotStatusModel.update(
        guild_count=guild_count,
        user_count=user_count,
        uptime_sec=uptime_sec,
        version=version,
        latency_ms=latency_ms,
        shard_count=shard_count,
        channel_count=channel_count,
    )
    return {"status": "ok"}


@router.get("/bot/status", dependencies=[Depends(verify_internal_auth)])
def bot_status():
    """Retourne le statut complet du bot.
    Accessible a tous les utilisateurs authentifies (dashboard).
    Les donnees sensibles (tokens, secrets) ne sont jamais exposees.
    """
    raw = BotStatusModel.get()
    if not raw:
        return {"status": "unknown", "is_online": False}

    # Formater l'uptime en texte lisible
    uptime_sec = raw.get("uptime_sec", 0) or 0
    days = uptime_sec // 86400
    hours = (uptime_sec % 86400) // 3600
    minutes = (uptime_sec % 3600) // 60
    uptime_text = ""
    if days > 0:
        uptime_text += f"{days}j "
    uptime_text += f"{hours}h {minutes}m"

    return {
        "is_online":     raw.get("is_online", False),
        "guild_count":   raw.get("guild_count", 0),
        "user_count":    raw.get("user_count", 0),
        "channel_count": raw.get("channel_count", 0),
        "uptime_sec":    uptime_sec,
        "uptime_text":   uptime_text.strip(),
        "latency_ms":    round(float(raw.get("latency_ms", 0) or 0), 1),
        "shard_count":   raw.get("shard_count", 1),
        "version":       raw.get("version", "?"),
        "started_at":    str(raw["started_at"]) if raw.get("started_at") else None,
        "updated_at":    str(raw["updated_at"]) if raw.get("updated_at") else None,
    }
