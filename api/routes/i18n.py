"""
API i18n - Routes pour traductions dynamiques via Grok
Stockage MySQL des traductions
"""

from fastapi import APIRouter, HTTPException, Request, Body, Query
from typing import List, Optional
from pydantic import BaseModel
from loguru import logger
import httpx
import hashlib
import json

from bot.db.connection import get_db_context
from bot.config import DB_TABLE_PREFIX

router = APIRouter(prefix="/i18n", tags=["i18n"])

# ============================================================================
# Configuration Grok API - Double clé pour rotation/fallback
# ============================================================================

import os

# Charger les clés depuis l'environnement
GROK_API_KEY_1 = os.getenv("GROK_API_KEY_1", "")
GROK_API_KEY_2 = os.getenv("GROK_API_KEY_2", "")
GROK_API_URL = "https://api.x.ai/v1/chat/completions"

# État pour rotation round-robin
_current_key_index = 0

def get_next_grok_key():
    """Retourne la prochaine clé disponible (rotation round-robin)."""
    global _current_key_index
    
    keys = [k for k in [GROK_API_KEY_1, GROK_API_KEY_2] if k and k.startswith("xai-")]
    
    if not keys:
        logger.error("Aucune clé Grok API configurée")
        return None
    
    # Rotation round-robin
    key = keys[_current_key_index % len(keys)]
    _current_key_index = (_current_key_index + 1) % len(keys)
    
    logger.debug(f"[i18n] Utilisation clé #{(_current_key_index % len(keys)) + 1}/{len(keys)}")
    return key

# ============================================================================
# Modèles
# ============================================================================

class TranslateRequest(BaseModel):
    texts: List[str]
    sourceLang: str = "en"
    targetLang: str

class TranslateResponse(BaseModel):
    translations: List[str]
    cached: bool = False

class TranslationsQuery(BaseModel):
    lang: str
    keys: str  # comma-separated

# ============================================================================
# Database Functions
# ============================================================================

def get_translation_from_db(lang: str, key_hash: str):
    """Récupère une traduction depuis la DB."""
    with get_db_context() as cursor:
        cursor.execute(
            f"SELECT translated_text, source_text FROM {DB_TABLE_PREFIX}i18n_translations "
            "WHERE lang = %s AND key_hash = %s",
            (lang, key_hash)
        )
        return cursor.fetchone()

def save_translation_to_db(lang: str, key: str, source_text: str, translated_text: str):
    """Sauvegarde une traduction en DB."""
    key_hash = hashlib.md5(key.encode()).hexdigest()
    
    with get_db_context() as cursor:
        cursor.execute(
            f"INSERT INTO {DB_TABLE_PREFIX}i18n_translations "
            "(lang, key_hash, translation_key, source_text, translated_text, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, NOW()) "
            "ON DUPLICATE KEY UPDATE "
            "translated_text = VALUES(translated_text), updated_at = NOW()",
            (lang, key_hash, key, source_text, translated_text)
        )

def clear_translations_for_lang(lang: str):
    """Efface toutes les traductions d'une langue."""
    with get_db_context() as cursor:
        cursor.execute(
            f"DELETE FROM {DB_TABLE_PREFIX}i18n_translations WHERE lang = %s",
            (lang,)
        )
        return cursor.rowcount

def get_all_translations_for_lang(lang: str, keys: List[str]):
    """Récupère toutes les traductions pour une langue et des clés."""
    if not keys:
        return {}
    
    key_hashes = [hashlib.md5(k.encode()).hexdigest() for k in keys]
    
    with get_db_context() as cursor:
        format_strings = ','.join(['%s'] * len(key_hashes))
        cursor.execute(
            f"SELECT translation_key, translated_text FROM {DB_TABLE_PREFIX}i18n_translations "
            f"WHERE lang = %s AND key_hash IN ({format_strings})",
            (lang, *key_hashes)
        )
        rows = cursor.fetchall()
        return {row['translation_key']: row['translated_text'] for row in rows}

# ============================================================================
# Grok Translation
# ============================================================================

async def translate_with_grok(texts: List[str], source_lang: str, target_lang: str) -> List[str]:
    """Traduit un batch de textes via l'API Grok avec rotation de clés."""
    
    # Récupérer la clé avec rotation
    api_key = get_next_grok_key()
    if not api_key:
        raise HTTPException(status_code=500, detail="Translation service not configured")
    
    # Construire le prompt pour traduction
    texts_json = json.dumps(texts, ensure_ascii=False)
    
    prompt = f"""Translate the following texts from {source_lang} to {target_lang}.
Return ONLY a JSON array with the translations in the same order.
Do not add any other text or explanation.

Texts to translate:
{texts_json}

Response format: ["translation1", "translation2", ...]"""

    # Essayer avec chaque clé en cas d'échec
    keys_to_try = [k for k in [GROK_API_KEY_1, GROK_API_KEY_2] if k and k.startswith("xai-")]
    last_error = None
    
    for attempt, key in enumerate(keys_to_try):
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    GROK_API_URL,
                    headers={
                        "Authorization": f"Bearer {key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": "grok-2-latest",
                        "messages": [
                            {"role": "system", "content": "You are a professional translator. Return only valid JSON arrays."},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.1
                    },
                    timeout=30.0
                )
                
                response.raise_for_status()
                data = response.json()
                
                # Extraire la réponse
                content = data['choices'][0]['message']['content']
                
                # Parser le JSON
                try:
                    translations = json.loads(content)
                    if not isinstance(translations, list):
                        raise ValueError("Response is not a list")
                    if len(translations) != len(texts):
                        raise ValueError(f"Expected {len(texts)} translations, got {len(translations)}")
                    
                    logger.info(f"[i18n] Traduction réussie avec clé #{attempt + 1}")
                    return translations
                    
                except json.JSONDecodeError:
                    # Essayer d'extraire le JSON du texte
                    import re
                    json_match = re.search(r'\[[\s\S]*\]', content)
                    if json_match:
                        translations = json.loads(json_match.group())
                        return translations
                    raise
                    
        except httpx.TimeoutException:
            last_error = "Timeout"
            logger.warning(f"[i18n] Timeout avec clé #{attempt + 1}, essai suivant...")
            continue
        except httpx.HTTPStatusError as e:
            last_error = f"HTTP {e.response.status_code}"
            logger.warning(f"[i18n] Erreur HTTP {e.response.status_code} avec clé #{attempt + 1}, essai suivant...")
            continue
        except Exception as e:
            last_error = str(e)
            logger.warning(f"[i18n] Erreur avec clé #{attempt + 1}: {e}, essai suivant...")
            continue
    
    # Toutes les clés ont échoué
    logger.error(f"[i18n] Toutes les clés Grok ont échoué. Dernière erreur: {last_error}")
    raise HTTPException(status_code=503, detail=f"Translation service unavailable: {last_error}")

# ============================================================================
# Routes
# ============================================================================

@router.post("/translate")
async def translate_endpoint(request: TranslateRequest):
    """
    Traduit une liste de textes via Grok et sauvegarde en DB.
    """
    if not request.texts:
        return {"translations": []}
    
    if len(request.texts) > 100:
        raise HTTPException(status_code=400, detail="Maximum 100 texts per request")
    
    try:
        # Traduire via Grok
        translations = await translate_with_grok(
            request.texts, 
            request.sourceLang, 
            request.targetLang
        )
        
        # Sauvegarder en DB (avec clés générées à partir du hash du texte source)
        for i, (source, translated) in enumerate(zip(request.texts, translations)):
            key = f"auto_{hashlib.md5(source.encode()).hexdigest()[:16]}"
            save_translation_to_db(request.targetLang, key, source, translated)
        
        return {
            "translations": translations,
            "cached": False,
            "count": len(translations)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erreur endpoint translate: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/translations")
async def get_translations(
    lang: str = Query(..., description="Langue cible"),
    keys: str = Query(..., description="Clés de traduction séparées par des virgules")
):
    """
    Récupère les traductions depuis la DB.
    """
    if not keys:
        return {"translations": {}}
    
    key_list = [k.strip() for k in keys.split(',') if k.strip()]
    
    try:
        translations = get_all_translations_for_lang(lang, key_list)
        return {
            "translations": translations,
            "found": len(translations),
            "requested": len(key_list)
        }
    except Exception as e:
        logger.error(f"Erreur récupération traductions: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/clear")
async def clear_cache(lang: str = Query(..., description="Langue à effacer")):
    """
    Efface le cache des traductions pour une langue.
    """
    try:
        deleted = clear_translations_for_lang(lang)
        return {
            "status": "success",
            "lang": lang,
            "deleted_count": deleted
        }
    except Exception as e:
        logger.error(f"Erreur clear cache: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/stats")
async def get_stats():
    """
    Statistiques des traductions stockées.
    """
    try:
        with get_db_context() as cursor:
            cursor.execute(
                f"SELECT lang, COUNT(*) as count FROM {DB_TABLE_PREFIX}i18n_translations GROUP BY lang"
            )
            stats = cursor.fetchall()
            
            cursor.execute(
                f"SELECT COUNT(DISTINCT lang) as total_langs FROM {DB_TABLE_PREFIX}i18n_translations"
            )
            total_langs = cursor.fetchone()['total_langs']
            
            cursor.execute(
                f"SELECT COUNT(*) as total_entries FROM {DB_TABLE_PREFIX}i18n_translations"
            )
            total_entries = cursor.fetchone()['total_entries']
        
        return {
            "by_language": {row['lang']: row['count'] for row in stats},
            "total_languages": total_langs,
            "total_entries": total_entries
        }
    except Exception as e:
        logger.error(f"Erreur stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
