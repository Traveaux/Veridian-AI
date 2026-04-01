# Veridian AI - Plan d'execution revamp

Date: 31 mars 2026
Horizon: 6 sprints de 2 semaines
Objectif: passer d'un MVP "bot + paiements semi-manuels" a un SaaS support Discord orienté MRR avec billing self-serve et operations tickets avancées.

## 1. Nouveau modele economique

Nouvelle grille:

| Plan | Mensuel | Annuel (-25%) | Positionnement |
|---|---:|---:|---|
| Free | 0 EUR | - | Decouverte / petit serveur |
| Starter | 4 EUR | 36 EUR | Premier vrai plan payant |
| Pro | 12 EUR | 108 EUR | Equipes support actives |
| Business | 29 EUR | 261 EUR | Besoins SLA / automation / multi-agents |

Add-ons:

| Add-on | Logique |
|---|---|
| Serveur extra | Facturation par serveur additionnel rattache au workspace/client |
| White-label | Add-on premium, marge forte, reserve Business |
| Tokens IA | Pack variable / surconsommation controllée |

Impact attendu:
- `ARPA` beaucoup plus haut que le modele `2 EUR / 5 EUR`.
- `MRR` cible x3-x4 sans multiplier le volume client.
- Billing recurrent et self-serve indispensables: Stripe devient priorite absolue.
- Seuil de rentabilite a `~200 EUR MRR`, atteignable si le tunnel d'achat et le churn sont traites avant le backlog UX.

## 2. Lecture du code actuel

Constat actuel:
- Le code est encore structure autour de `free / premium / pro`.
- Le schema SQL bloque le nouveau pricing via plusieurs `ENUM('free','premium','pro')`.
- Le tunnel d'achat est pense pour `OxaPay + PayPal + giftcard`, avec validation manuelle encore centrale.
- Le site marketing et le dashboard affichent encore `Premium 2 EUR` et `Pro 5 EUR`.

Zones impactees immediatement:
- `bot/config.py`
- `database/schema.sql`
- `bot/cogs/payments.py`
- `api/routes/internal.py`
- `api/routes/dashboard.py`
- `api/routes/webhook.py`
- `web/index.html`
- `web/dashboard.html`
- `web/locales/*.json`

## 3. 8 corrections critiques a appliquer immediatement

Ces corrections sont a traiter avant d'ouvrir les gros chantiers fonctionnels.

1. Centraliser la definition des plans.
   Aujourd'hui, les plans sont dupliques entre config, API, SQL, landing page et dashboard. Tant que `premium/pro` restent hardcodes, toute migration vers `starter/pro/business` cassera les flux de paiement et d'affichage.

2. Supprimer la dependance business aux `ENUM` SQL actuels.
   Les colonnes `vai_guilds.tier`, `vai_orders.plan`, `vai_payments.plan` et `vai_subscriptions.plan` doivent migrer vers des `VARCHAR` ou vers des references catalogue. Sinon `Business` et les add-ons ne peuvent pas entrer en base.

3. Introduire une couche billing unique cote serveur.
   Il faut un service unique pour calculer prix, remises annuelles, add-ons, et disponibilites par plan. Aujourd'hui, le prix est lu directement depuis `PRICING`, ce qui n'est pas compatible avec Stripe, annuels, add-ons et futurs A/B tests.

4. Prioriser Stripe avant toute feature visible.
   Sans checkout recurrent + portail client + webhooks idempotents, le nouveau modele economique n'est pas operable, meme si le dashboard est plus beau.

5. Corriger le module de paiement bot.
   Le fichier `bot/cogs/payments.py` avait perdu des imports critiques pendant les changements locaux. J'ai corrige les imports manquants et rendu le callback OxaPay configurable par domaine.

6. Assainir le wording produit partout.
   Les labels `Premium`, `Pro`, `2 EUR`, `5 EUR`, "manuel" et les promesses actuelles sont presentes sur le site et le dashboard. Si le pricing change sans nettoyage complet, le produit devient incoherent pour les clients et le support.

7. Separer "subscription state" et "feature entitlements".
   Le code actuel deduit beaucoup de choses directement depuis `plan`. Avec les add-ons, il faut resoudre des droits effectifs: `base plan + add-ons + overrides + quotas`.

8. Geler les docs "MVP complete / production ready".
   La doc actuelle survend l'etat du produit par rapport au nouveau scope. Il faut requalifier le statut en "MVP en transition vers vNext" pour eviter des ecarts entre documentation, vente et capacite reelle.

## 4. Proposition de 12 nouvelles tables DB

Principe: rester a 12 tables maximum sur cette phase en normalisant seulement ce qui debloque revenu, fiabilite et operations. Les workflows secondaires peuvent rester en JSON au debut.

### Billing

1. `vai_billing_products`
   Catalogue logique: `starter`, `pro`, `business`, `server_extra`, `white_label`, `ai_tokens`.

2. `vai_billing_prices`
   Prix versionnes par produit, devise, intervalle (`month`, `year`) et provider (`stripe`, `manual`).

3. `vai_billing_customers`
   Mapping entre compte/guild et `stripe_customer_id`.

4. `vai_billing_subscriptions`
   Etat canonique de l'abonnement cote produit, independant du provider.

5. `vai_billing_subscription_items`
   Ligne par item actif: plan de base, serveur extra, white-label, tokens pack.

6. `vai_billing_invoices`
   Snapshot facture / montant / taxe / statut / lien de paiement / periode.

7. `vai_billing_webhook_events`
   Idempotence et relecture des webhooks Stripe.

### Ticket operations

8. `vai_ticket_tags`
   Definitions des tags par guild: label, couleur, ordre, archivage.

9. `vai_ticket_tag_links`
   Jointure ticket <-> tag pour filtrage et analytics.

10. `vai_ticket_notes`
   Notes internes horodatees par agent/staff.

11. `vai_ticket_satisfaction`
   Rating post-fermeture, commentaire, delai de reponse, date de reponse.

12. `vai_outbound_webhooks`
   Webhooks sortants par guild vers Zapier/Make/Notion avec secret, event types et statut.

Notes de cadrage:
- `panel builder`, `interactive forms`, `SLA`, `round-robin`, `per-category staff roles`, `blacklist` et `snippets` peuvent demarrer en colonnes JSON sur `vai_guilds` / `vai_tickets` tant que le besoin n'est pas stabilise.
- Si le volume ou la complexite augmente, ces blocs meritent ensuite leur propre normalisation.

## 5. Mapping features -> stockage initial

| Feature | Stockage recommande en phase 1 |
|---|---|
| Panel builder visuel | JSON versionne sur `vai_guilds` |
| Interactive Forms | JSON versionne sur `vai_guilds` + references ticket |
| Tags & Labels | `vai_ticket_tags` + `vai_ticket_tag_links` |
| Snippets auto-traduits | JSON sur `vai_guilds` puis table dediee si adoption forte |
| SLA + breach alerts | JSON policy sur `vai_guilds`, events calcules en applicatif |
| Round-robin | JSON routing policy sur `vai_guilds` |
| Per-category staff roles | JSON mapping category -> roles sur `vai_guilds` |
| Thread Discord support | Colonnes supplementaires sur `vai_tickets` |
| Webhooks sortants | `vai_outbound_webhooks` |
| Blacklist utilisateurs | JSON par guild au debut, table dediee si moderation lourde |
| Notes internes | `vai_ticket_notes` |
| Satisfaction rating | `vai_ticket_satisfaction` |

## 6. Plan en 6 sprints

### Sprint 1 - Billing foundation

Objectif:
- figer le nouveau catalogue produit
- sortir les `ENUM` SQL
- brancher Stripe en lecture/ecriture

Livrables:
- migration `premium/pro` -> `starter/pro/business`
- tables billing 1 a 7
- service billing central
- creation checkout Stripe abonnement mensuel / annuel
- webhook idempotent `checkout.session.completed`, `invoice.paid`, `customer.subscription.updated`, `customer.subscription.deleted`

Definition of done:
- un serveur peut souscrire un plan mensuel ou annuel sans intervention humaine

### Sprint 2 - Self-serve billing

Objectif:
- rendre l'achat et la gestion d'abonnement autonomes

Livrables:
- portail client Stripe
- upgrade / downgrade / cancel at period end
- add-ons `serveur extra`, `white-label`, `tokens IA`
- affichage du prochain renouvellement et de la MRR par serveur
- e-mails/DM de confirmation et d'echeance

Definition of done:
- le support n'intervient plus pour les cas standard de billing

### Sprint 3 - Ticket ops core

Objectif:
- rattraper les features concurrentielles les plus monetisables

Livrables:
- tags & filtres
- notes internes
- blacklist utilisateurs
- per-category staff roles
- round-robin auto-assignment
- thread Discord support

Definition of done:
- un staff peut router, annoter et prioriser sans bricolage manuel

### Sprint 4 - SLA et knowledge acceleration

Objectif:
- augmenter la valeur percue cote staff

Livrables:
- SLA policies + breach alerts
- snippets / quick replies auto-traduits
- satisfaction rating post-fermeture
- premieres analytics de performance staff

Definition of done:
- le produit commence a justifier `Pro` et `Business`

### Sprint 5 - Builder UX

Objectif:
- rendre la configuration differenciante et demo-friendly

Livrables:
- panel builder visuel avec preview live Discord
- interactive forms avec modal Discord
- onboarding wizard 4 etapes
- detail drawer ticket sans navigation

Definition of done:
- un admin configure un setup complet sans document externe

### Sprint 6 - Dashboard vNext et polish

Objectif:
- finir le packaging produit et la lisibilite business

Livrables:
- nouvelle sidebar en 3 zones
- `Ctrl+K` command palette
- analytics complets + leaderboard agents
- mobile responsive avec bottom bar + gestes clefs
- outbound webhooks
- hardening, monitoring, QA de regression

Definition of done:
- le dashboard devient vendable, mesurable et mobile-friendly

## 7. Ordre de priorite reel

Si la bande passante est limitee, l'ordre doit etre:

1. Stripe + migrations plans
2. Billing self-serve + add-ons
3. Ticket ops core
4. SLA + snippets + rating
5. Builder UX
6. Polish dashboard

Raison:
- le pricing revu n'a aucun effet sans facturation recurrente reelle
- les features concurrentielles n'ont de valeur economique que si l'upgrade est frictionless
- l'UX seule n'augmente pas le MRR si les droits, quotas et paiements restent fragiles

## 8. KPI de pilotage

KPI a suivre des le Sprint 1:
- `MRR`
- `ARPA`
- `conversion Free -> payant`
- `part annuel`
- `churn logo` et `churn revenu`
- `take rate` des add-ons
- `tickets staff / agent / jour`
- `median first response time`
- `SLA breach rate`
- `CSAT post-fermeture`

## 9. Decision produit recommande

Decision conseillee:
- ne pas implementer toutes les features concurrentielles avant Stripe
- livrer d'abord la machine a encaisser, puis les operations tickets qui soutiennent `Pro` et `Business`
- reserver les features "wow" de builder visuel au moment ou le billing et les entitlements sont stables

En pratique:
- le prochain lot de dev devrait etre "Billing vNext" et non "UI vNext".
