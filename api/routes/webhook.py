"""
OxaPay Webhook Handler
Reçoit les confirmations de paiement crypto et active les abonnements
"""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
import hmac
import hashlib
import os
import json
from loguru import logger
from bot.db.models import (
    SubscriptionModel, PaymentModel, OrderModel, PendingNotificationModel, AuditLogModel
)
from bot.billing import normalize_interval, normalize_plan
from bot.services.notifications import notify_bot_owner_payment

router = APIRouter(prefix="/webhook", tags=["webhook"])


def verify_oxapay_signature(payload: bytes, signature: str) -> bool:
    """Vérifier la signature HMAC-SHA256 d'OxaPay"""
    secret = os.getenv("OXAPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload, 
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature.lower())


@router.post("/oxapay")
async def oxapay_webhook(request: Request):
    """
    Webhook OxaPay pour confirmations de paiement crypto
    
    Payload attendu:
    {
        "status": "completed",
        "invoice_id": "INV-123456",
        "order_id": "VAI-202501-4823",
        "amount": 2.00,
        "currency": "USD",
        "user_id": 123456789,
        "guild_id": 987654321,
        "plan": "premium"
    }
    """
    
    try:
        # Récupérer et vérifier la signature
        body = await request.body()
        signature = request.headers.get("X-Oxapay-Signature", "")
        
        if not signature or not verify_oxapay_signature(body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON")
        
        # Vérifier le statut du paiement
        status = str(payload.get("status") or "").lower()
        if status not in ("paid", "completed"):
            return JSONResponse(
                status_code=200,
                content={"status": "ignored", "reason": f"status={status}"}
            )
        
        order_id = payload.get("order_id")
        invoice_id = payload.get("invoice_id")
        amount = payload.get("amount")
        currency = payload.get("currency") or "EUR"
        
        order = OrderModel.get(order_id) if order_id else None
        if order and str(order.get("status") or "").lower() == "paid":
            return JSONResponse(
                status_code=200,
                content={"status": "already_processed"}
            )

        user_id = payload.get("user_id") or (order or {}).get("user_id")
        guild_id = payload.get("guild_id") or (order or {}).get("guild_id")
        plan = normalize_plan(payload.get("plan") or (order or {}).get("plan"), default="starter")
        billing_interval = normalize_interval((order or {}).get("billing_interval"), default="month")

        if not all([user_id, guild_id, plan]):
            raise HTTPException(status_code=400, detail="Missing order context")
        
        # Enregistrer le paiement dans la base de données
        try:
            # 1. Marquer la commande comme payée si elle existe
            if order_id:
                OrderModel.update_status(order_id, "paid", "OxaPay webhook")
            
            # 2. Créer l'enregistrement de paiement réel
            payment_id = PaymentModel.create(
                user_id=user_id,
                guild_id=guild_id,
                method="oxapay",
                amount=amount,
                currency=currency,
                plan=plan,
                billing_interval=billing_interval,
                order_id=order_id,
                status="completed",
                oxapay_invoice_id=invoice_id,
            )

            # 3. Activer l'abonnement (30 jours)
            SubscriptionModel.create(
                guild_id=guild_id,
                user_id=user_id,
                plan=plan,
                payment_id=payment_id,
                billing_interval=billing_interval
            )
            sub = SubscriptionModel.get(guild_id) or {}
            expiry = sub.get("expires_at")
            expiry_label = expiry.strftime("%d/%m/%Y") if hasattr(expiry, "strftime") else str(expiry or "date non disponible")

            # 4. Enregistrer l'action dans les logs d'audit
            AuditLogModel.log(
                actor_id=user_id,
                action="payment.oxapay.success",
                guild_id=guild_id,
                details={"order_id": order_id, "amount": amount, "plan": plan}
            )

            # 5. Notifier l'utilisateur via notification pendante (sera envoyée par le bot)
            msg = (
                f"✅ Votre paiement Crypto (**{plan.upper()}**) a ete valide.\n"
                f"Abonnement actif jusqu'au **{expiry_label}**.\n"
                "Repayez avant cette date pour le garder actif et pour eviter la desactivation des options du plan."
            )
            PendingNotificationModel.add(user_id, msg)
        except Exception as e:
            logger.error(f"Erreur lors du traitement du paiement OxaPay: {e}")
            raise HTTPException(status_code=500, detail="Internal processing error")
        
        # 4. Notifier le Bot Owner
        try:
            await notify_bot_owner_payment(
                user_id=user_id,
                guild_id=guild_id,
                plan=plan,
                method="oxapay",
                amount=amount,
                order_id=order_id
            )
        except Exception as notify_error:
            logger.warning(f"OxaPay owner notification failed: {notify_error}")
        
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Subscription activated"}
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
