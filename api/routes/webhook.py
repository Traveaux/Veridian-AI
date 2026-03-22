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
from datetime import datetime
from bot.db.connection import get_db_context
from bot.db.models import SubscriptionModel, PaymentModel, OrderModel, PendingNotificationModel
from bot.services.notifications import notify_bot_owner_payment

router = APIRouter(prefix="/webhook", tags=["webhook"])


def verify_oxapay_signature(payload: bytes, signature: str) -> bool:
    """Vérifier la signature HMAC-SHA256 d'OxaPay"""
    secret = os.getenv("OXAPAY_WEBHOOK_SECRET", "")
    if not secret or not signature:
        return False
    expected_signature = hmac.new(
        secret.encode(), 
        payload, 
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected_signature, signature)


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
        signature = request.headers.get("X-Oxapay-Signature")
        
        if not signature or not verify_oxapay_signature(body, signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        payload = json.loads(body)
        
        # Vérifier le statut du paiement
        if payload.get("status") != "completed":
            return JSONResponse(
                status_code=200,
                content={"status": "ignored", "reason": "payment not completed"}
            )
        
        user_id = payload.get("user_id")
        guild_id = payload.get("guild_id")
        plan = payload.get("plan")
        order_id = payload.get("order_id")
        invoice_id = payload.get("invoice_id")
        amount = payload.get("amount")
        
        # Enregistrer le paiement
        with get_db_context() as db:
            # 1. Créer entrée paiement
            PaymentModel.create(
                user_id=user_id,
                guild_id=guild_id,
                order_id=order_id,
                method="oxapay",
                amount=amount,
                currency="USD",
                plan=plan,
                status="completed",
                oxapay_invoice_id=invoice_id
            )
            
            # 2. Marquer la commande comme payée si elle existe
            if order_id:
                OrderModel.update_status(order_id, "paid", "OxaPay webhook")
            
            # 3. Créer/activer abonnement (30 jours par défaut)
            SubscriptionModel.create(
                guild_id=guild_id,
                user_id=user_id,
                plan=plan,
                payment_id=payment_id,
                duration_days=30
            )

            # 4. Ajouter une notification DM pour l'utilisateur
            PendingNotificationModel.add(
                user_id=user_id,
                content=f"🚀 Votre abonnement **{plan.upper()}** a été activé avec succès sur votre serveur !\nMerci pour votre confiance. Vous pouvez maintenant profiter de toutes les fonctionnalités avancées.",
                category="payment_success"
            )
        
        # 4. Notifier le Bot Owner
        await notify_bot_owner_payment(
            user_id=user_id,
            guild_id=guild_id,
            plan=plan,
            method="oxapay",
            amount=amount,
            order_id=order_id
        )
        
        return JSONResponse(
            status_code=200,
            content={"status": "success", "message": "Subscription activated"}
        )
    
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
