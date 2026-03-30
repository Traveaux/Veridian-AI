# 💳 Veridian AI — Système de Paiements v2.0
> Mis à jour : Mars 2026 · Sans Stripe · 3 méthodes uniquement

---

## Méthodes acceptées

| Méthode | Traitement | Activation |
|---------|-----------|-----------|
| **OxaPay (Crypto)** | Automatique via webhook | Instantanée |
| **PayPal** | Manuel — vérifié par toi | Sous 24h |
| **Carte Cadeau** | Manuel — vérifié par toi | Sous 24h |

---

## 1. OxaPay — Crypto (Automatique)

Aucun changement. BTC, ETH, USDT, LTC via OxaPay.
Webhook HMAC → activation instantanée de l'abonnement.

---

## 2. PayPal — Validation manuelle

### Flux utilisateur

```
1. L'utilisateur lance /pay paypal pro (ou via le dashboard)
2. Le bot génère un Order ID unique : VAI-202504-4823
3. Le bot envoie un message éphémère avec les instructions :
   ┌─────────────────────────────────────────────────────┐
   │  💳 Paiement PayPal                                 │
   │                                                      │
   │  Montant : 12.00 EUR                                 │
   │  Destinataire : [ton email PayPal]                   │
   │                                                      │
   │  ⚠️ IMPORTANT : lors de l'envoi, ajoutez             │
   │  votre référence de commande dans le champ           │
   │  "Note / Message pour le vendeur" :                  │
   │                                                      │
   │  ➡️  VAI-202504-4823                                 │
   │                                                      │
   │  Sans cette référence, votre paiement ne pourra      │
   │  pas être identifié et l'activation sera retardée.   │
   │                                                      │
   │  ✅ Activation sous 24h après réception.             │
   └─────────────────────────────────────────────────────┘
4. Tu reçois le paiement PayPal avec la note "VAI-202504-4823"
5. Tu valides dans le dashboard → bot active l'abonnement + DM à l'user
```

### Instructions précises dans le bot

Le message doit expliquer **exactement** où mettre la référence selon l'interface PayPal :

```python
# bot/cogs/payments.py — _handle_paypal()

PAYPAL_INSTRUCTIONS = """
**Étapes pour payer via PayPal :**

1. Allez sur **paypal.com** → Envoyer de l'argent
2. Entrez l'adresse : `{paypal_email}`
3. Montant : **{amount:.2f} EUR**
4. **Sur mobile** : appuyez sur *"Ajouter une note"*
   **Sur ordinateur** : cliquez sur *"Ajouter un message"*
5. Dans ce champ, écrivez **exactement** :
   ```
   {order_id}
   ```
6. Envoyez le paiement

⚠️ **Sans cette référence dans le message PayPal, nous ne pourrons 
pas associer votre paiement à votre commande.**

Activation sous 24h après réception et vérification.
"""
```

### Comment trouver le champ "message" dans PayPal

À inclure dans le message éphémère (texte court, pas embed) :

```
📱 Mobile PayPal : 
   Envoyer → [montant] → Sélectionner contact → 
   « Ajouter une note » (sous le montant)

💻 Web PayPal :
   Envoyer de l'argent → Payer pour des biens/services → 
   « Ajouter un message au vendeur »
```

---

## 3. Carte Cadeau — Validation manuelle

Aucun changement de fonctionnement. L'utilisateur envoie :
- Le code en message privé au bot
- Une image de la carte en pièce jointe

---

## 4. Ce qu'il NE faut PAS ajouter

- ❌ Stripe (pas nécessaire pour le modèle actuel)
- ❌ Stripe webhooks
- ❌ Portail client Stripe
- ❌ Usage-based billing Stripe

Retirer toutes les références Stripe de :
- `requirements.txt`
- `.env.example`
- `api/routes/` (pas de stripe_webhook.py)
- `VERIDIAN_AI_V2_ROADMAP.md` → sections 2.4 et 2.3 à supprimer

---

## 5. Modèle économique sans Stripe — Fonctionnement

```
Abonnements gérés manuellement en DB :
- Tu valides → SubscriptionModel.create() via dashboard
- Expiration 30 jours → cron/heartbeat vérifie et notifie
- Renouvellement : l'user refait une commande

Avantage : 0% de frais de plateforme (OxaPay ~1%, PayPal ~3.4%)
Inconvénient : pas de renouvellement automatique pour PayPal/GC
→ Solution : rappel automatique 5 jours avant expiration via DM bot
```

### Rappel automatique d'expiration

```python
# À ajouter dans bot/main.py — task quotidienne

@tasks.loop(hours=24)
async def expiry_reminder_loop():
    """Rappelle aux abonnés dont l'abonnement expire dans 5 jours."""
    with get_db_context() as conn:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT s.*, g.name as guild_name
            FROM vai_subscriptions s
            JOIN vai_guilds g ON s.guild_id = g.id
            WHERE s.is_active = 1
              AND s.expires_at BETWEEN NOW() AND DATE_ADD(NOW(), INTERVAL 5 DAY)
              AND s.reminder_sent = 0
        """)
        expiring = cursor.fetchall()
    
    for sub in expiring:
        msg = (
            f"⏰ Votre abonnement **{sub['plan'].upper()}** sur **{sub['guild_name']}** "
            f"expire dans 5 jours.\n\n"
            f"Pour renouveler, utilisez `/pay` dans votre serveur ou visitez "
            f"https://veridiancloud.xyz/dashboard"
        )
        PendingNotificationModel.add(sub['user_id'], msg)
        # Marquer comme notifié
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE vai_subscriptions SET reminder_sent = 1 WHERE id = %s",
                (sub['id'],)
            )
```

Ajouter `reminder_sent TINYINT(1) DEFAULT 0` dans `vai_subscriptions`.

---

## Résumé des changements dans le code

### Fichiers à modifier

| Fichier | Modification |
|---------|-------------|
| `bot/cogs/payments.py` | Améliorer le message PayPal avec instructions complètes |
| `bot/main.py` | Ajouter `expiry_reminder_loop` |
| `database/schema.sql` | Ajouter `reminder_sent` dans `vai_subscriptions` |
| `api/db_migrate.py` | Ajouter la colonne `reminder_sent` |
| `web/locales/*.json` | Mettre à jour les textes PayPal (toutes les langues) |

### Aucun nouveau fichier nécessaire

Le système de paiement actuel est suffisant.
L'effort doit aller vers les **features** et l'**ergonomie dashboard**.