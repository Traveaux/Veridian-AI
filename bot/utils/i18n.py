import os
import json
from loguru import logger

class I18n:
    _instance = None
    _locales = {}
    DEFAULT_LOCALE = "fr"  # User seems to prefer French, but we'll fallback to EN if needed

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(I18n, cls).__new__(cls)
            cls._instance._load_locales()
        return cls._instance

    def _load_locales(self):
        locales_path = os.path.join(os.path.dirname(__file__), "..", "locales")
        for filename in os.listdir(locales_path):
            if filename.endswith(".json"):
                lang_code = filename.replace(".json", "")
                try:
                    with open(os.path.join(locales_path, filename), "r", encoding="utf-8") as f:
                        self._locales[lang_code] = json.load(f)
                    logger.info(f"✓ Loaded locale: {lang_code}")
                except Exception as e:
                    logger.error(f"✗ Failed to load locale {lang_code}: {e}")

    def get(self, key: str, locale: str = None, **kwargs) -> str:
        """
        Retrieves a translated string.
        Supports nested keys like 'common.error'.
        """
        if not locale:
            locale = self.DEFAULT_LOCALE
        
        # Normalize Discord locales (e.g., en-US -> en)
        lang = locale.lower().split("-")[0]
        
        if lang not in self._locales:
            lang = self.DEFAULT_LOCALE
        
        if lang not in self._locales:
            # Last fallback
            lang = "en" if "en" in self._locales else list(self._locales.keys())[0]

        data = self._locales.get(lang, {})
        parts = key.split(".")
        
        for part in parts:
            if isinstance(data, dict):
                data = data.get(part, key)
            else:
                data = key
                break
        
        if data == key and lang != "en":
            # Fallback to English if key not found in current locale
            data = self.get(key, "en", **kwargs) if lang != "en" else key

        if isinstance(data, str) and kwargs:
            try:
                return data.format(**kwargs)
            except Exception:
                return data
        
        return str(data)

i18n = I18n()
