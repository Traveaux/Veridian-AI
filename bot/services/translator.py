"""
Service de traduction avec cache
Détecte les langues, vérifie le cache, et appelle Groq si nécessaire
"""

import hashlib
import re
from typing import Optional

from langdetect import detect_langs, LangDetectException, DetectorFactory
from loguru import logger
from bot.services.groq_client import GroqClient
from bot.db.models import TranslationCacheModel


class TranslatorService:
    def __init__(self):
        """Initialise le service de traduction."""
        # Make langdetect deterministic across runs.
        try:
            DetectorFactory.seed = 0
        except Exception:
            pass
        self.groq_client = GroqClient()
        logger.info("✓ Service Translator initialisé")

    _RE_URL = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
    _RE_MENTION = re.compile(r"<@!?(\d+)>|<@&(\d+)>|<#(\d+)>")
    _RE_CUSTOM_EMOJI = re.compile(r"<a?:\w+:(\d+)>")
    _RE_CODEBLOCK = re.compile(r"```[\s\S]*?```", re.MULTILINE)
    _RE_INLINE_CODE = re.compile(r"`[^`]{1,200}`")
    _RE_NON_LETTERS = re.compile(r"[^\w\s'-]", re.UNICODE)

    def _clean_for_detection(self, text: str) -> str:
        t = (text or "").strip()
        if not t:
            return ""
        # Remove blocks that often confuse detection.
        t = self._RE_CODEBLOCK.sub(" ", t)
        t = self._RE_INLINE_CODE.sub(" ", t)
        t = self._RE_URL.sub(" ", t)
        t = self._RE_MENTION.sub(" ", t)
        t = self._RE_CUSTOM_EMOJI.sub(" ", t)
        t = self._RE_NON_LETTERS.sub(" ", t)
        # Collapse whitespace
        t = " ".join(t.split())
        return t

    def detect_language(self, text: str) -> Optional[str]:
        """
        Détecte la langue d'un texte.

        La détection est volontairement prudente pour éviter les mauvaises
        classifications sur des messages très courts ou ambigus. On préfère
        ne rien détecter plutôt que de fixer une mauvaise langue.

        Args:
            text: Texte à analyser

        Returns:
            Code langue (ex: 'en', 'fr', 'es') ou None si le signal est trop faible.
        """
        try:
            cleaned = self._clean_for_detection(text)
            if len(cleaned) < 2:
                return None

            langs = detect_langs(cleaned)
            if not langs:
                return None

            top = langs[0]
            prob = float(getattr(top, "prob", 0.0) or 0.0)

            # Heuristique de confiance assouplie:
            # - un mot unique requiert une forte certitude
            # - phrases courtes requierent certitude moderee
            if len(cleaned.split()) < 2 and prob < 0.80:
                return None
            if len(cleaned) < 30 and prob < 0.65:
                return None
            elif prob < 0.50:
                return None

            language = getattr(top, "lang", None)
            if not language or len(language) != 2:
                return None

            logger.debug(f"✓ Langue détectée: {language} (p={prob:.2f})")
            return language
        except LangDetectException as e:
            logger.warning(f"Impossible de détecter la langue: {e}")
            return None

    def generate_content_hash(self, text: str, source_lang: str, target_lang: str) -> str:
        """
        Génère un hash SHA256 du contenu + langues.
        Utilisé pour le cache.
        
        Args:
            text: Texte à hacher
            source_lang: Langue source
            target_lang: Langue cible
            
        Returns:
            Hash SHA256 hexadécimal
        """
        content = f"{text}|{source_lang}|{target_lang}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()

    def translate(self, text: str, source_language: str, target_language: str) -> tuple[str, bool]:
        """
        Traduit un texte avec cache.
        
        Args:
            text: Texte à traduire
            source_language: Langue source
            target_language: Langue cible
            
        Returns:
            Tuple (texte traduit, from_cache: bool)
        """
        # Pas de traduction si langues identiques
        if source_language == target_language:
            return text, False

        # Générer hash et chercher en cache
        content_hash = self.generate_content_hash(text, source_language, target_language)
        cache_result = TranslationCacheModel.get(content_hash)

        if cache_result:
            logger.info(f"✓ Traduction trouvée en cache (hit #{cache_result['hit_count']})")
            return cache_result['translated_text'], True

        # Cache miss: appeler Groq
        logger.debug(f"✗ Cache miss, appel Groq pour traduction")
        translated_text = self.groq_client.translate(text, source_language, target_language)

        # Stocker en cache
        TranslationCacheModel.store(
            content_hash=content_hash,
            original_text=text,
            translated_text=translated_text,
            source_language=source_language,
            target_language=target_language
        )

        return translated_text, False

    def translate_message_for_staff(self, text: str, user_language: str, 
                                   staff_language: str = 'en') -> tuple[str, bool]:
        """
        Traduit un message utilisateur pour le staff.
        
        Args:
            text: Message de l'utilisateur
            user_language: Langue de l'utilisateur
            staff_language: Langue du staff
            
        Returns:
            Tuple (message traduit, from_cache: bool)
        """
        return self.translate(text, user_language, staff_language)

    def translate_response_for_user(self, text: str, response_language: str,
                                   user_language: str) -> tuple[str, bool]:
        """
        Traduit une réponse du staff pour l'utilisateur.
        
        Args:
            text: Réponse du staff
            response_language: Langue de la réponse (ex: 'en')
            user_language: Langue de l'utilisateur
            
        Returns:
            Tuple (réponse traduite, from_cache: bool)
        """
        return self.translate(text, response_language, user_language)
