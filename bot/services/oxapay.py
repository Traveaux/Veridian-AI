"""
Client OxaPay pour les paiements crypto
Crée les invoices et gère les webhooks
"""

import os
import aiohttp
from loguru import logger
from bot.config import OXAPAY_BASE_URL, OXAPAY_MERCHANTS_REQUEST_ENDPOINT


class OxaPayClient:
    def __init__(self):
        """Initialise le client OxaPay."""
        self.merchant_key = os.getenv('OXAPAY_MERCHANT_KEY')
        self.webhook_secret = os.getenv('OXAPAY_WEBHOOK_SECRET')
        self.base_url = OXAPAY_BASE_URL
        logger.info("✓ Client OxaPay initialisé")

    async def create_invoice(self, user_id: int, amount: float, order_id: str, 
                            callback_url: str) -> dict:
        """
        Crée une invoice OxaPay pour un paiement crypto.
        
        Args:
            user_id: ID Discord de l'utilisateur
            amount: Montant en EUR
            order_id: Numéro de commande unique
            callback_url: URL du webhook pour recevoir les notifications
            
        Returns:
            Dict contenant la réponse OxaPay (avec payLink)
        """
        payload = {
            "merchant": self.merchant_key,
            "amount": amount,
            "currency": "EUR",
            "orderId": order_id,
            "callbackUrl": callback_url,
            "description": f"Veridian AI - Commande {order_id}"
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}{OXAPAY_MERCHANTS_REQUEST_ENDPOINT}",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.info(f"✓ Invoice OxaPay créée: {order_id}")
                        return result
                    else:
                        logger.error(f"✗ Erreur OxaPay: {response.status}")
                        return {}
                        
        except Exception as e:
            logger.error(f"✗ Erreur lors de la création d'invoice OxaPay: {e}")
            return {}

    def verify_webhook_signature(self, payload: bytes | dict, signature: str) -> bool:
        """
        Vérifie la signature HMAC d'un webhook OxaPay.
        
        Args:
            payload: Données du webhook
            signature: Signature HMAC fournie
            
        Returns:
            True si la signature est valide, False sinon
        """
        import hmac
        import hashlib
        import json

        try:
            if not self.webhook_secret:
                logger.error("✗ OXAPAY_WEBHOOK_SECRET manquant: verification signature impossible")
                return False
            if not signature:
                return False

            if isinstance(payload, bytes):
                payload_bytes = payload
            else:
                payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
                payload_bytes = payload_json.encode()
            
            # Calculer le HMAC-SHA256
            expected_signature = hmac.new(
                self.webhook_secret.encode(),
                payload_bytes,
                hashlib.sha256
            ).hexdigest()
            
            # Comparaison sécurisée
            if hmac.compare_digest(expected_signature, signature.lower()):
                logger.info("✓ Signature webhook OxaPay valide")
                return True
            else:
                logger.warning("✗ Signature webhook OxaPay invalide")
                return False
                
        except Exception as e:
            logger.error(f"✗ Erreur vérification signature OxaPay: {e}")
            return False

    async def get_exchange_rates(self) -> dict:
        """
        Récupère les taux de change actuels.
        Utile pour afficher les montants en crypto.
        
        Returns:
            Dict avec les taux de change EUR vers crypto
        """
        try:
            async with aiohttp.ClientSession() as session:
                # OxaPay expose les taux via une endpoint publique
                async with session.get(
                    "https://api.oxapay.com/merchants/rates",
                    params={"from": "EUR", "to": "BTC,ETH,USDT"},
                    timeout=aiohttp.ClientTimeout(total=5)
                ) as response:
                    if response.status == 200:
                        result = await response.json()
                        logger.debug("✓ Taux de change récupérés")
                        return result
                    return {}
        except Exception as e:
            logger.debug(f"Impossible de récupérer les taux OxaPay: {e}")
            return {}
