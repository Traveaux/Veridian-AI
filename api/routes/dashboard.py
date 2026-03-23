"""
API Dashboard - Routes réservées au Super Admin
Validation des commandes, gestion des abonnements et stats globales.
"""

from fastapi import APIRouter, Depends, HTTPException, Request, Body
from typing import Optional, List
from pydantic import BaseModel
from loguru import logger
import json

from bot.db.models import (
    OrderModel, SubscriptionModel, PaymentModel, 
    AuditLogModel, GuildModel, TicketModel, BotStatusModel,
    PendingNotificationModel, KnowledgeBaseModel
)
from bot.db.connection import get_db_context, DB_TABLE_PREFIX
from bot.config import PLAN_LIMITS, PRICING
from api.routes.internal import verify_super_admin

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

# ============================================================================
# Modèles
# ============================================================================

class OrderActionRequest(BaseModel):
    reason: Optional[str] = None

class SubscriptionActivateRequest(BaseModel):
    guild_id: str
    plan: str
    duration_days: int = 30

class SubscriptionRevokeRequest(BaseModel):
    guild_id: str

class KBEntryCreateRequest(BaseModel):
    guild_id: str
    question: str
    answer: str
    category: Optional[str] = None

class KBEntryUpdateRequest(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    category: Optional[str] = None
    is_active: Optional[int] = None # 0 or 1

# ============================================================================
# Routes : Commandes (Orders)
# ============================================================================

@router.get("/orders/pending")
async def get_pending_orders(auth: dict = Depends(verify_super_admin)):
    """Liste toutes les commandes en attente de validation."""
    try:
        orders = OrderModel.get_pending()
        return {"total": len(orders), "orders": orders}
    except Exception as e:
        logger.error(f"Erreur get_pending_orders: {e}")
        raise HTTPException(status_code=500, detail="Erreur lors de la récupération des commandes")

@router.post("/orders/{order_id}/validate")
async def validate_order(
    order_id: str, 
    auth: dict = Depends(verify_super_admin)
):
    """Valide une commande manuellement (PayPal/Giftcard)."""
    order = OrderModel.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    
    if order["status"] != "pending":
        raise HTTPException(status_code=400, detail=f"Commande déjà traitée ({order['status']})")

    try:
        # 1. Update order status
        OrderModel.update_status(order_id, "paid", validated_by=auth["user_id"])
        
        # 2. Create Payment record
        payment_id = PaymentModel.create(
            user_id=order["user_id"],
            guild_id=order["guild_id"],
            method=order["method"],
            amount=float(order["amount"] or 0),
            plan=order["plan"],
            order_id=order_id,
            status="completed"
        )
        
        # 3. Create Subscription
        SubscriptionModel.create(
            guild_id=order["guild_id"],
            user_id=order["user_id"],
            plan=order["plan"],
            payment_id=payment_id,
            duration_days=30
        )
        
        # 4. Audit Log
        AuditLogModel.log(
            actor_id=auth["user_id"],
            actor_username=auth.get("username", "Super Admin"),
            action="order.validate",
            target_id=order_id,
            details={"order_id": order_id, "amount": order["amount"], "plan": order["plan"]}
        )
        
        # 5. Notify User via DM
        message = (
            f"✅ Votre commande **{order_id}** ({order['plan'].upper()}) a été validée !\n"
            f"Votre abonnement est maintenant actif sur le serveur."
        )
        PendingNotificationModel.add(order["user_id"], message)
        
        return {"status": "success", "message": "Commande validée et abonnement activé"}
    except Exception as e:
        logger.error(f"Erreur validate_order {order_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/orders/{order_id}/reject")
async def reject_order(
    order_id: str, 
    req: OrderActionRequest,
    auth: dict = Depends(verify_super_admin)
):
    """Rejette une commande."""
    order = OrderModel.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    
    try:
        OrderModel.update_status(order_id, "rejected", validated_by=auth["user_id"])
        
        # Audit Log
        AuditLogModel.log(
            actor_id=auth["user_id"],
            actor_username=auth.get("username", "Super Admin"),
            action="order.reject",
            target_id=order_id,
            details={"reason": req.reason}
        )
        
        # Notify User via DM
        message = (
            f"❌ Votre commande **{order_id}** a été refusée.\n"
            f"Raison : {req.reason or 'Non spécifiée'}"
        )
        PendingNotificationModel.add(order["user_id"], message)
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/orders/{order_id}/partial")
async def partial_order(
    order_id: str, 
    auth: dict = Depends(verify_super_admin)
):
    """Marque une commande comme partiellement payée."""
    order = OrderModel.get(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Commande introuvable")
    
    try:
        OrderModel.update_status(order_id, "partial", validated_by=auth["user_id"])
        
        # Audit Log
        AuditLogModel.log(
            actor_id=auth["user_id"],
            actor_username=auth.get("username", "Super Admin"),
            action="order.partial",
            target_id=order_id
        )
        
        # Notify User via DM
        message = (
            f"ℹ️ Votre commande **{order_id}** a été marquée comme partiellement payée.\n"
            f"Veuillez contacter le support pour finaliser le paiement."
        )
        PendingNotificationModel.add(order["user_id"], message)
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Routes : Abonnements (Subscriptions)
# ============================================================================

@router.get("/subscriptions")
async def get_all_subscriptions(auth: dict = Depends(verify_super_admin)):
    """Liste tous les abonnements actifs sur tous les serveurs."""
    try:
        from bot.db.connection import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor(dictionary=True)
            cursor.execute("SELECT * FROM vai_subscriptions WHERE expires_at > NOW()")
            return cursor.fetchall()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/subscriptions/activate")
async def activate_subscription(
    req: SubscriptionActivateRequest,
    auth: dict = Depends(verify_super_admin)
):
    """Force l'activation d'un abonnement pour un serveur."""
    try:
        guild_id = int(req.guild_id)
        sub_id = SubscriptionModel.create(
            guild_id=guild_id,
            user_id=auth["user_id"], # Link to the admin who activated it
            plan=req.plan,
            payment_id=None,
            duration_days=req.duration_days
        )
        AuditLogModel.log(
            actor_id=auth["user_id"],
            actor_username=auth.get("username", "Super Admin"),
            action="sub.activate",
            target_id=str(guild_id),
            details=f"Plan: {req.plan}, Duration: {req.duration_days}d"
        )
        return {"status": "success", "subscription_id": sub_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/subscriptions/revoke")
async def revoke_subscription(
    req: SubscriptionRevokeRequest,
    auth: dict = Depends(verify_super_admin)
):
    """Révoque manuellement un abonnement."""
    try:
        guild_id = int(req.guild_id)
        # We don't have a direct 'revoke' in SubscriptionModel, so we manually expire it
        from bot.db.connection import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE vai_subscriptions SET expires_at = NOW() WHERE guild_id = %s", 
                (guild_id,)
            )
        AuditLogModel.log(
            actor_id=auth["user_id"],
            actor_username=auth.get("username", "Super Admin"),
            action="sub.revoke",
            target_id=str(guild_id)
        )
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Routes : Global Stats
# ============================================================================

@router.get("/stats")
async def get_global_stats(auth: dict = Depends(verify_super_admin)):
    """Retourne les statistiques globales du bot pour le super-admin."""
    try:
        with get_db_context() as conn:
            cursor = conn.cursor()

            def scalar(query: str, params: tuple = ()) -> float | int:
                cursor.execute(query, params)
                row = cursor.fetchone()
                return 0 if not row else row[0]

            revenue_total = float(scalar(
                f"SELECT COALESCE(SUM(amount), 0) "
                f"FROM {DB_TABLE_PREFIX}payments "
                f"WHERE status = 'completed'"
            ))
            revenue_month = float(scalar(
                f"SELECT COALESCE(SUM(amount), 0) "
                f"FROM {DB_TABLE_PREFIX}payments "
                f"WHERE status = 'completed' "
                f"AND YEAR(paid_at) = YEAR(CURDATE()) "
                f"AND MONTH(paid_at) = MONTH(CURDATE())"
            ))
            tickets_month = int(scalar(
                f"SELECT COUNT(*) "
                f"FROM {DB_TABLE_PREFIX}tickets "
                f"WHERE opened_at > DATE_SUB(NOW(), INTERVAL 30 DAY)"
            ))
            tickets_today = int(scalar(
                f"SELECT COUNT(*) "
                f"FROM {DB_TABLE_PREFIX}tickets "
                f"WHERE DATE(opened_at) = CURDATE()"
            ))
            guilds_total = int(scalar(f"SELECT COUNT(*) FROM {DB_TABLE_PREFIX}guilds"))
            subs_active = int(scalar(
                f"SELECT COUNT(*) "
                f"FROM {DB_TABLE_PREFIX}subscriptions "
                f"WHERE is_active = 1"
            ))
            orders_pending = int(scalar(
                f"SELECT COUNT(*) "
                f"FROM {DB_TABLE_PREFIX}orders "
                f"WHERE status = 'pending'"
            ))

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

            bot_status = BotStatusModel.get() or {}

            return {
                "total_guilds": guilds_total,
                "total_users": total_users,
                "tickets_today": tickets_today,
                "revenue_month": revenue_month,
                "active_subs": subs_active,
                "orders_pending": orders_pending,
                "bot_version": bot_status.get("version", "Unknown"),
                # Compatibilite avec les anciennes cles potentiellement deja consommees.
                "revenue_total": revenue_total,
                "tickets_month": tickets_month,
                "guilds_total": guilds_total,
                "subscriptions_active": subs_active,
            }
    except Exception as e:
        logger.error(f"Erreur get_global_stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# Routes : Base de Connaissances (KB)
# ============================================================================

@router.get("/kb/{guild_id}")
async def get_guild_kb(guild_id: int, auth: dict = Depends(verify_super_admin)):
    """Récupère la base de connaissances d'un serveur."""
    try:
        return KnowledgeBaseModel.get_by_guild(guild_id, active_only=False)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/kb")
async def create_kb_entry(req: KBEntryCreateRequest, auth: dict = Depends(verify_super_admin)):
    """Crée une nouvelle entrée dans la KB."""
    try:
        kb_id = KnowledgeBaseModel.create(
            guild_id=int(req.guild_id),
            question=req.question,
            answer=req.answer,
            category=req.category,
            created_by=auth["user_id"]
        )
        if not kb_id:
            raise HTTPException(status_code=500, detail="Erreur lors de la création de l'entrée KB")
        return {"status": "success", "kb_id": kb_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.put("/kb/{kb_id}")
async def update_kb_entry(kb_id: int, req: KBEntryUpdateRequest, auth: dict = Depends(verify_super_admin)):
    """Met à jour une entrée KB."""
    try:
        # On utilise une requête directe pour la mise à jour (simple)
        from bot.db.connection import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()
            updates = []
            params = []
            if req.question is not None:
                updates.append("question = %s")
                params.append(req.question)
            if req.answer is not None:
                updates.append("answer = %s")
                params.append(req.answer)
            if req.category is not None:
                updates.append("category = %s")
                params.append(req.category)
            if req.is_active is not None:
                updates.append("is_active = %s")
                params.append(req.is_active)
            
            if not updates:
                return {"status": "no_change"}
            
            params.append(kb_id)
            query = f"UPDATE vai_knowledge_base SET {', '.join(updates)} WHERE id = %s"
            cursor.execute(query, tuple(params))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/kb/{kb_id}")
async def delete_kb_entry(kb_id: int, auth: dict = Depends(verify_super_admin)):
    """Supprime une entrée KB."""
    try:
        from bot.db.connection import get_db_context
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM vai_knowledge_base WHERE id = %s", (kb_id,))
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
