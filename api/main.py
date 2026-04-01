"""
API FastAPI interne - Communication entre le bot et le dashboard
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Header, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from loguru import logger
import os
import time
from datetime import datetime
from pathlib import Path

# Security helpers (no hardcoded production secrets)
from api.security import get_internal_api_secret, get_jwt_secret, security_headers, is_production

# ── Charger .env AVANT tout le reste ────────────────────────────────────────
try:
    from dotenv import load_dotenv
    for _p in [Path(".env"), Path(__file__).parent.parent / ".env", Path(__file__).parent / ".env"]:
        if _p.exists():
            load_dotenv(dotenv_path=_p, override=True)
            logger.debug(f"[dotenv] Charge depuis {_p.resolve()}")
            break
    else:
        logger.debug("[dotenv] Aucun .env trouve — variables lues depuis le systeme")
except ImportError:
    logger.warning("[dotenv] Installe python-dotenv : pip install python-dotenv")

# Créer dossier logs s'il n'existe pas
Path('logs').mkdir(exist_ok=True)

# Configuration
API_DOMAIN = os.getenv('API_DOMAIN', 'api.veridiancloud.xyz')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')

# Import version
from bot.config import VERSION

# Import routers
from api.routes.auth import router as auth_router
from api.routes.internal import router as internal_router   # ← FIX: manquait dans l'original
from api.routes.webhook import router as webhook_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    if is_production():
        missing = []
        for var in ("DISCORD_CLIENT_ID", "DISCORD_CLIENT_SECRET", "DASHBOARD_URL"):
            if not os.getenv(var):
                missing.append(var)
        if missing:
            # Fail-fast: OAuth login would be broken and security posture unclear.
            raise RuntimeError(f"Variables d'environnement manquantes en production: {', '.join(missing)}")

    # Auto DB migrations (tables/views/patches) from `database/`.
    try:
        from api.db_migrate import ensure_database_schema
        ensure_database_schema()
    except Exception as e:
        logger.error(f"[db] Migration a echoue: {e}")
        # In production, schema drift breaks auth/session checks -> fail fast.
        if is_production():
            raise

    yield

app = FastAPI(
    title=f"Veridian AI {VERSION} - API Interne",
    description="API pour la communication bot ↔ dashboard",
    version=VERSION,
    lifespan=lifespan,
)

# ============================================================================
# Security (headers + required secrets in prod)
# ============================================================================

# Ensure secrets are never "known defaults" in production.
# In dev, these may be generated ephemerally (see api/security.py).
INTERNAL_API_SECRET = get_internal_api_secret()
_JWT_SECRET = get_jwt_secret()


# ============================================================================
# Rate Limiting (Simple In-Memory)
# ============================================================================
# Dict for storing ip -> [timestamps]
_RATE_LIMIT_DATA: dict[str, list[float]] = {}
_RATE_LIMIT_MAX = 60
_RATE_LIMIT_WINDOW = 60
_ROUTE_LIMITS = {
    "/auth/exchange": (10, 60),
    "/auth/discord/login": (20, 60),
    "/internal/": (120, 60),
    "/webhook/": (200, 60),
}


@app.middleware("http")
async def _rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if not (path.startswith("/auth/") or path.startswith("/internal/") or path.startswith("/webhook/")):
        return await call_next(request)

    client_ip = request.client.host if request.client else "unknown"
    now = time.time()

    max_req, window = _RATE_LIMIT_MAX, _RATE_LIMIT_WINDOW
    for prefix, config in _ROUTE_LIMITS.items():
        if path.startswith(prefix):
            max_req, window = config
            break

    key = f"{client_ip}:{path[:20]}"
    history = [t for t in _RATE_LIMIT_DATA.get(key, []) if now - t < window]

    if len(history) >= max_req:
        logger.warning(f"Rate limit exceeded for {client_ip} on {path}")
        return JSONResponse(
            status_code=429,
            headers={"Retry-After": str(window)},
            content={"detail": "Too Many Requests", "retry_after": window}
        )

    history.append(now)
    _RATE_LIMIT_DATA[key] = history
    return await call_next(request)


@app.middleware("http")
async def _security_headers_middleware(request: Request, call_next):
    try:
        resp = await call_next(request)
    except HTTPException as e:
        # Standard HTTP exceptions (401, 403, 404, etc.)
        return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
    except Exception as e:
        # Avoid exceptions bubbling outside of CORS middleware (would drop ACAO headers).
        logger.exception(f"Unhandled exception: {e}")
        # Sanitize error in production
        detail = "Internal Server Error"
        if not is_production():
            detail = f"Debug: {str(e)}"
        return JSONResponse(status_code=500, content={"detail": detail})

    headers = security_headers()
    for k, v in headers.items():
        # Don't override explicit headers set by routes.
        resp.headers.setdefault(k, v)
    return resp


# ============================================================================
# CORS Configuration
# ============================================================================
CORS_ORIGINS = [
    "https://veridiancloud.xyz",
    "https://www.veridiancloud.xyz",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    # Keep this explicit: avoids accidentally allowing exotic headers cross-site.
    allow_headers=[
        "Authorization",
        "Content-Type",
        "X-API-SECRET",
        "X-VAI-Authorization",
        "X-WEBHOOK-SIGNATURE",
        "X-Oxapay-Signature",
    ],
)

# Include Routers
app.include_router(auth_router)
app.include_router(internal_router)
app.include_router(webhook_router)
from api.routes.dashboard import router as dashboard_router
app.include_router(dashboard_router)

# ============================================================================
# Logging
# ============================================================================
logger.remove()
logger.add(
    "logs/api.log",
    rotation="500 MB",
    retention="10 days",
    level="INFO",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
)
logger.add(
    "logs/errors.log",
    rotation="500 MB",
    retention="30 days",
    level="ERROR",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}"
)

# ============================================================================
# Middleware: Vérification du secret API interne
# ============================================================================
def verify_api_secret(x_api_key: str = Header(...)):
    """Vérifie la clé API interne."""
    if x_api_key != INTERNAL_API_SECRET:
        raise HTTPException(status_code=403, detail="Clé API invalide")
    return x_api_key


# ============================================================================
# Modèles Pydantic
# ============================================================================
class GuildConfigRequest(BaseModel):
    support_channel_id: int = None
    ticket_category_id: int = None
    staff_role_id: int = None
    log_channel_id: int = None
    default_language: str = 'en'


class ValidateOrderRequest(BaseModel):
    order_id: str
    plan: str


class RevokeSubscriptionRequest(BaseModel):
    guild_id: int


class SendDMRequest(BaseModel):
    user_id: int
    message: str


# ============================================================================
# Routes globales (non-prefixées par /internal/)
# ============================================================================

@app.get("/health", tags=["Health"])
async def health_check():
    """Vérifie la santé de l'API et de la base."""
    checks = {
        "api": "ok",
        "database": "unknown",
        "version": VERSION,
        "environment": ENVIRONMENT,
        "api_domain": API_DOMAIN,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    http_status = 200

    try:
        from bot.db.connection import get_connection
        conn = get_connection()
        conn.close()
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = "error"
        checks["database_error"] = str(e)[:100]
        http_status = 503

    return JSONResponse(status_code=http_status, content=checks)


@app.post("/webhook/oxapay", tags=["Webhooks"])
async def oxapay_webhook(request: Request):
    """Reçoit les webhooks OxaPay et traite les paiements de façon idempotente."""
    try:
        import hashlib
        import hmac
        import json

        from bot.db.models import (
            AuditLogModel,
            OrderModel,
            PaymentModel,
            PendingNotificationModel,
            SubscriptionModel,
        )
        from bot.services.notifications import notify_bot_owner_payment

        body = await request.body()
        signature = request.headers.get("X-Oxapay-Signature", "") or request.headers.get("X-WEBHOOK-SIGNATURE", "")
        secret = os.getenv("OXAPAY_WEBHOOK_SECRET", "")

        if not secret or not signature:
            raise HTTPException(status_code=401, detail="Missing signature")

        expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature.lower()):
            logger.warning(f"OxaPay: signature invalide depuis {request.client.host if request.client else 'unknown'}")
            raise HTTPException(status_code=401, detail="Invalid signature")

        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")

        status = str(payload.get("status", "")).strip().lower()
        if status not in {"paid", "completed"}:
            return {"status": "ignored", "reason": f"status={status}"}

        order_id = payload.get("order_id") or payload.get("orderId")
        invoice_id = payload.get("invoice_id") or payload.get("trackId")
        amount = float(payload.get("amount") or 0)
        currency = payload.get("currency") or "EUR"

        order = OrderModel.get(order_id) if order_id else None
        if order and str(order.get("status", "")).lower() == "paid":
            logger.info(f"OxaPay webhook idempotent: {order_id} deja traite")
            return {"status": "already_processed"}

        user_id = payload.get("user_id") or (order or {}).get("user_id")
        guild_id = payload.get("guild_id") or (order or {}).get("guild_id")
        plan = payload.get("plan") or (order or {}).get("plan")

        if not all([user_id, guild_id, plan]):
            logger.error(f"OxaPay webhook: contexte manquant pour {order_id}")
            raise HTTPException(status_code=400, detail="Missing order context")

        if order_id:
            OrderModel.update_status(order_id, "paid", "OxaPay webhook")

        payment_id = PaymentModel.create(
            user_id=user_id,
            guild_id=guild_id,
            method="oxapay",
            amount=amount,
            currency=currency,
            plan=plan,
            order_id=order_id,
            status="completed",
            oxapay_invoice_id=invoice_id,
        )
        SubscriptionModel.create(
            guild_id=guild_id,
            user_id=user_id,
            plan=plan,
            payment_id=payment_id,
            duration_days=30,
        )
        sub = SubscriptionModel.get(guild_id) or {}
        expiry = sub.get("expires_at")
        expiry_label = expiry.strftime("%d/%m/%Y") if hasattr(expiry, "strftime") else str(expiry or "date non disponible")
        AuditLogModel.log(
            actor_id=user_id,
            action="payment.oxapay.success",
            guild_id=guild_id,
            details={"order_id": order_id, "amount": amount, "plan": plan},
        )
        PendingNotificationModel.add(
            user_id,
            (
                f"✅ Paiement **{str(plan).upper()}** confirme. "
                f"Abonnement actif jusqu'au **{expiry_label}**.\n"
                "Repayez avant cette date pour le garder actif et pour eviter la desactivation des options du plan."
            ),
        )

        try:
            await notify_bot_owner_payment(
                user_id=user_id,
                guild_id=guild_id,
                plan=plan,
                method="oxapay",
                amount=amount,
                order_id=order_id,
            )
        except Exception as notify_error:
            logger.warning(f"OxaPay owner notification failed: {notify_error}")

        logger.info(f"OxaPay: {order_id} traite pour guild {guild_id}")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"✗ Erreur webhook OxaPay: {e}")
        detail = "Processing error" if is_production() else str(e)
        raise HTTPException(status_code=500, detail=detail)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Gestionnaire personnalisé pour les exceptions HTTP."""
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail}
    )


# ============================================================================
# Démarrage
# ============================================================================
if __name__ == '__main__':
    import uvicorn

    host = os.getenv('API_HOST', '0.0.0.0')
    port = int(os.getenv('API_PORT', 201))

    ssl_certfile = "/etc/letsencrypt/live/api.veridiancloud.xyz/fullchain.pem"
    ssl_keyfile = "/etc/letsencrypt/live/api.veridiancloud.xyz/privkey.pem"

    ssl_config = {}
    if os.path.exists(ssl_certfile) and os.path.exists(ssl_keyfile):
        ssl_config = {"ssl_certfile": ssl_certfile, "ssl_keyfile": ssl_keyfile}
        logger.info("🔒 SSL/TLS configuré")
    else:
        logger.warning("⚠️ Certificats SSL non trouvés — démarrage sans SSL")

    logger.info(f"🚀 API Veridian {VERSION} démarrage sur {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level='info', **ssl_config)
