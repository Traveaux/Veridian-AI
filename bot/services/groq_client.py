"""
Client Groq pour les appels IA
Gère les réponses, traductions et résumés de tickets
Support de 4 clés API avec fallback automatique
"""

import os
from groq import Groq
from loguru import logger
from bot.config import GROQ_MODEL_FAST, GROQ_MODEL_QUALITY, SYSTEM_PROMPT_SUPPORT, SYSTEM_PROMPT_TICKET_SUMMARY
from bot.utils.embed_style import strip_emojis


class GroqClient:
    def __init__(self):
        """Initialise le client Groq avec 4 clés API."""
        self.api_keys = [
            os.getenv('GROQ_API_KEY_1'),
            os.getenv('GROQ_API_KEY_2'),
            os.getenv('GROQ_API_KEY_3'),
            os.getenv('GROQ_API_KEY_4')
        ]
        
        # Filtrer les clés vides
        self.api_keys = [key for key in self.api_keys if key]
        
        if not self.api_keys:
            logger.error("✗ Aucune clé Groq trouvée dans .env (GROQ_API_KEY_1-4)")
        else:
            logger.info(f"✓ Client Groq initialisé avec {len(self.api_keys)} clés API disponibles")
        
        self.current_key_index = 0
    
    def _get_client(self, force_key_index=None):
        """Retourne un client Groq avec la clé actuelle ou spécifique."""
        if force_key_index is not None:
            key_index = force_key_index
        else:
            key_index = self.current_key_index % len(self.api_keys) if self.api_keys else 0
        
        if not self.api_keys or key_index >= len(self.api_keys):
            return None
        
        return Groq(api_key=self.api_keys[key_index])

    def generate_support_response(self, message: str, guild_name: str, guild_id: int = None, 
                                   language: str = 'en', custom_prompt: str = None) -> str:
        """Génère une réponse IA avec fallback sur 4 clés et enrichissement KB."""
        if not self.api_keys:
            return "Erreur: Aucune clé Groq disponible"

        kb_context = ""
        if guild_id:
            try:
                from bot.db.models import KnowledgeBaseModel
                kb_entries = KnowledgeBaseModel.search(guild_id, message, limit=3)
                if kb_entries:
                    kb_texts = []
                    for entry in kb_entries:
                        kb_texts.append(f"Q: {entry['question']}\nA: {entry['answer']}")
                    kb_context = "\n\nConnaissances spécifiques au serveur :\n" + "\n---\n".join(kb_texts)
            except Exception as e:
                logger.debug(f"KB Search failed: {e}")

        if custom_prompt and custom_prompt.strip():
            # Le prompt personnalisé est utilisé tel quel, avec le nom du serveur injecté
            system_prompt = custom_prompt.strip()
            if "{guild_name}" in system_prompt:
                system_prompt = system_prompt.replace("{guild_name}", guild_name)
            logger.debug(f"Support IA: utilisation du prompt personnalise pour {guild_name}")
        else:
            system_prompt = SYSTEM_PROMPT_SUPPORT.format(guild_name=guild_name)
        
        # Inject KB context if found
        if kb_context:
            system_prompt += kb_context

        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue
                
                completion = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.7,
                    max_tokens=500,
                    top_p=1,
                    stream=False,
                )
                
                response = completion.choices[0].message.content
                logger.info(f"✓ Support généré (clé #{attempt + 1}, {len(response)} chars)")
                return strip_emojis(response) or ""
                
            except Exception as e:
                logger.warning(f"⚠ Clé Groq #{attempt + 1} échouée: {str(e)[:100]}")
        
        logger.error("✗ Toutes les clés Groq épuisées")
        return "Je suis désolé, je n'ai pas pu traiter votre demande. Veuillez ouvrir un ticket."

    def translate(self, text: str, source_language: str, target_language: str) -> str:
        """Traduit un texte avec fallback."""
        if not self.api_keys:
            return text
        
        system = (
            "You are a translation engine.\n"
            "Rules:\n"
            "- Translate strictly from the source language to the target language.\n"
            "- Output ONLY the translated text (no quotes, no explanations).\n"
            "- Preserve formatting, line breaks, mentions and code blocks.\n"
            "- Do not add emojis.\n"
            "- Do not add or remove information.\n"
        )
        prompt = (
            f"Source language: {source_language}\n"
            f"Target language: {target_language}\n"
            "Text:\n"
            f"{text}"
        )
        
        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue
                
                completion = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.3,
                    max_tokens=1000,
                    stream=False,
                )
                
                logger.debug(f"✓ Traduction (clé #{attempt + 1})")
                return strip_emojis(completion.choices[0].message.content.strip()) or ""
                
            except Exception as e:
                logger.warning(f"⚠ Clé Groq #{attempt + 1} traduction: {str(e)[:80]}")
        
        return text

    def generate_ticket_summary(self, messages: list, ticket_language: str) -> str:
        """Génère un résumé de ticket avec fallback."""
        if not self.api_keys:
            return "Impossible de générer le résumé"
        
        conversation = "\n".join([
            f"[{msg.get('author', 'Unknown')}]: {msg.get('content', '')}"
            for msg in messages
        ])
        
        system_prompt = SYSTEM_PROMPT_TICKET_SUMMARY.format(ticket_language=ticket_language)
        
        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue
                
                completion = client.chat.completions.create(
                    model=GROQ_MODEL_QUALITY,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Conversation:\n\n{conversation}"}
                    ],
                    temperature=0.5,
                    max_tokens=800,
                    stream=False,
                )
                
                logger.info(f"✓ Résumé (clé #{attempt + 1})")
                return strip_emojis(completion.choices[0].message.content) or ""
                
            except Exception as e:
                logger.warning(f"⚠ Clé Groq #{attempt + 1} résumé: {str(e)[:80]}")
        
        return "Impossible de generer le resume du ticket."

    def classify_ticket_priority(self, messages: list, ticket_language: str) -> str:
        """
        Classe la priorité d'un ticket : low, medium, high, urgent.

        `messages` est une liste de dicts {author, content}.
        """
        if not self.api_keys:
            return "medium"

        # On limite la taille du contexte pour rester efficace.
        chunks = []
        total_chars = 0
        for msg in messages or []:
            line = f"[{msg.get('author', 'Unknown')}]: {msg.get('content', '')}".strip()
            if not line:
                continue
            if total_chars + len(line) > 4000:
                break
            chunks.append(line)
            total_chars += len(line)

        conversation = "\n".join(chunks)

        system = (
            "You are a support triage assistant for a Discord ticket system.\n"
            "Your job is to analyse the conversation and assign a single priority "
            "label according to the severity and urgency.\n\n"
            "Available priorities:\n"
            "- low: question simple, demande d'information, pas d'urgence.\n"
            "- medium: problème à résoudre mais pas bloquant immédiatement.\n"
            "- high: service perturbé, utilisateur bloqué sur une action importante.\n"
            "- urgent: incident critique, service principal down, urgence forte.\n\n"
            "Rules:\n"
            "- Think carefully but respond with ONLY one word among: low, medium, high, urgent.\n"
            "- Do not add any explanation or extra text.\n"
        )

        user_prompt = (
            f"Ticket language (hint): {ticket_language}\n"
            f"Conversation:\n{conversation}\n\n"
            "Return the priority label now (low, medium, high or urgent)."
        )

        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue

                completion = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=4,
                    stream=False,
                )

                raw = (completion.choices[0].message.content or "").strip().lower()
                for label in ("low", "medium", "high", "urgent"):
                    if label in raw:
                        logger.info(f"✓ Priorité ticket classée '{label}' (clé #{attempt + 1})")
                        return label

            except Exception as e:
                logger.warning(f"⚠ Clé Groq #{attempt + 1} priorité: {str(e)[:80]}")

        return "medium"

    def detect_question(self, message: str) -> bool:
        """Détecte si un message est une question."""
        question_indicators = ['?', 'comment', 'pourquoi', 'quoi', 'qu\'est', 'qui', 'où', 'quand', 'quel',
                             'how', 'why', 'what', 'who', 'where', 'when', 'which']
        
        if any(ind in message.lower() for ind in question_indicators):
            return True
        
        if len(message.split()) < 3:
            return False
        
        if not self.api_keys:
            return False
        
        try:
            client = self._get_client(force_key_index=0)
            if not client:
                return False
            
            completion = client.chat.completions.create(
                model=GROQ_MODEL_FAST,
                messages=[{"role": "user", "content": f"Question ou non? Réponds: oui/non.\n{message}"}],
                temperature=0.1,
                max_tokens=10,
                stream=False,
            )
            
            response = completion.choices[0].message.content.lower()
            return 'oui' in response or 'yes' in response
            
        except Exception:
            return False

    def analyze_first_message(self, message: str, language: str = 'fr') -> str:
        """Analyse le premier message d'un ticket pour en extraire l'intention (Smart Welcome)."""
        if not self.api_keys or not message.strip():
            return ""

        system = (
            "You are a support assistant. Your task is to summarize the user's initial request in ONE short sentence.\n"
            "Rules:\n"
            "- Be extremely concise (max 15 words).\n"
            f"- Respond in the requested language: {language}.\n"
            "- Focus on the main intent (e.g., 'Problème de paiement PayPal', 'Question sur l'abonnement Premium').\n"
            "- No greeting, no punctuation at the end if possible.\n"
        )

        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue

                completion = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.3,
                    max_tokens=40,
                    stream=False,
                )
                
                res = completion.choices[0].message.content.strip()
                logger.info(f"✓ Analyse premier message générée (clé #{attempt + 1})")
                return res
            except Exception as e:
                logger.warning(f"⚠ Clé Groq #{attempt + 1} analyse: {str(e)[:80]}")

        return ""

    def generate_staff_suggestion(self, messages: list, staff_language: str) -> str:
        """Génère une suggestion courte de réponse pour le staff."""
        if not self.api_keys or not messages:
            return ""

        conv_text = "\n".join([
            f"[{m.get('author', '?')}]: {m.get('content', '')}"
            for m in messages[-10:]
            if (m.get("content") or "").strip()
        ])
        if not conv_text:
            return ""

        system = (
            "You are a customer support assistant helping a staff member.\n"
            "Based on the conversation, generate ONE concise, professional reply suggestion.\n"
            "Rules:\n"
            f"- Respond in: {staff_language}\n"
            "- Maximum 3 sentences\n"
            "- Be empathetic and solution-focused\n"
            "- Do NOT add emojis\n"
            "- Output ONLY the suggested reply text\n"
        )

        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue

                completion = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": f"Conversation:\n{conv_text}\n\nSuggest a reply:"}
                    ],
                    temperature=0.6,
                    max_tokens=150,
                    stream=False,
                )
                res = (completion.choices[0].message.content or "").strip()
                return strip_emojis(res) or ""
            except Exception as e:
                logger.warning(f"⚠ Clé Groq #{attempt + 1} suggestion staff: {str(e)[:80]}")

        return ""

    def detect_payment_intent(self, message: str) -> bool:
        """Détecte si l'utilisateur exprime une intention d'achat ou de paiement."""
        if not self.api_keys or not message.strip():
            return False

        # Quick check for keywords to avoid unnecessary API calls
        keywords = ["payer", "acheter", "prix", "abonnement", "premium", "pay", "buy", "price", "subscription", "upgrade"]
        if not any(k in message.lower() for k in keywords):
            return False

        system = (
            "You are a support classifier. Determine if the user message expresses an intent to BUY, PAY for a subscription, or ask about PRICING/PLANS.\n"
            "Respond with 'YES' if they want to pay/buy/upgrade or ask about prices, 'NO' otherwise.\n"
            "Rules: ONLY respond with YES or NO.\n"
        )

        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue

                completion = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.0,
                    max_tokens=5,
                    stream=False,
                )
                
                res = completion.choices[0].message.content.strip().upper()
                if "YES" in res:
                    logger.info(f"✓ Intention de paiement détectée (clé #{attempt + 1})")
                    return True
                return False
            except Exception:
                continue

        return False

    def detect_malicious_content(self, message: str) -> str:
        """
        Détecte si le contenu est malveillant (scam, phishing, insultes graves).
        Retourne : 'safe', 'suspicious' ou 'malicious'
        """
        if not self.api_keys or not message.strip():
            return "safe"

        # Keywords for quick check
        keywords = ["scam", "hack", "token", "password", "nitro", "free", "gift", "link code", "auth"]
        # On ne bloque pas direct, on utilise Groq pour juger le contexte
        
        system = (
            "You are a security moderator for a Discord bot. Analyze the user message for SCAMS, PHISHING, or MALICIOUS INTENT.\n"
            "Categories:\n"
            "- 'malicious': obvious scam, phishing link, token grabbing attempt.\n"
            "- 'suspicious': weird request, asking for sensitive info, potential soft scam.\n"
            "- 'safe': normal user message.\n"
            "Rules: ONLY respond with 'safe', 'suspicious', or 'malicious'.\n"
        )

        for attempt in range(len(self.api_keys)):
            try:
                client = self._get_client(force_key_index=attempt)
                if not client:
                    continue

                completion = client.chat.completions.create(
                    model=GROQ_MODEL_FAST,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": message}
                    ],
                    temperature=0.0,
                    max_tokens=10,
                    stream=False,
                )
                
                res = completion.choices[0].message.content.strip().lower()
                if "malicious" in res:
                    return "malicious"
                if "suspicious" in res:
                    return "suspicious"
                return "safe"
            except Exception:
                continue

        return "safe"
