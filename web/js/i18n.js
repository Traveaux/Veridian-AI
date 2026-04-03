/**
 * Système i18n dynamique avec traductions via API Grok
 * Stockage en base de données (MySQL) via API backend
 * Langue source: Anglais (tous les textes HTML doivent être en anglais)
 * Support de toutes les langues ISO 639-1
 */

// Toutes les langues ISO 639-1 supportées
const SUPPORTED_LANGS = [
  'af', 'sq', 'am', 'ar', 'hy', 'az', 'eu', 'be', 'bn', 'bs', 'bg', 'ca', 'ceb', 'ny', 
  'zh', 'zh-CN', 'zh-TW', 'co', 'hr', 'cs', 'da', 'nl', 'en', 'eo', 'et', 'tl', 'fi', 
  'fr', 'fy', 'gl', 'ka', 'de', 'el', 'gu', 'ht', 'ha', 'haw', 'he', 'hi', 'hmn', 'hu', 
  'is', 'ig', 'id', 'ga', 'it', 'ja', 'jw', 'kn', 'kk', 'km', 'rw', 'ko', 'ku', 'ky', 
  'lo', 'la', 'lv', 'lt', 'lb', 'mk', 'mg', 'ms', 'ml', 'mt', 'mi', 'mr', 'mn', 'my', 
  'ne', 'no', 'or', 'ps', 'fa', 'pl', 'pt', 'pa', 'ro', 'ru', 'sm', 'gd', 'sr', 'st', 
  'sn', 'sd', 'si', 'sk', 'sl', 'so', 'es', 'su', 'sw', 'sv', 'tg', 'ta', 'tt', 'te', 
  'th', 'tr', 'tk', 'uk', 'ur', 'ug', 'uz', 'vi', 'cy', 'xh', 'yi', 'yo', 'zu'
];

const DEFAULT_LANG = 'en';
let currentTranslations = {};

// API endpoints
const API_BASE = '/api/i18n';
const API_TRANSLATE = `${API_BASE}/translate`;
const API_GET_TRANSLATIONS = `${API_BASE}/translations`;

/**
 * Extrait les textes source (anglais) depuis le HTML
 */
function extractSourceTexts() {
  const sourceTexts = {};
  
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    if (!sourceTexts[key]) {
      sourceTexts[key] = el.textContent.trim();
    }
  });
  
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    if (!sourceTexts[key] && el.placeholder) {
      sourceTexts[key] = el.placeholder.trim();
    }
  });
  
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.dataset.i18nTitle;
    if (!sourceTexts[key] && el.title) {
      sourceTexts[key] = el.title.trim();
    }
  });
  
  document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
    const key = el.dataset.i18nAriaLabel;
    if (!sourceTexts[key] && el.getAttribute('aria-label')) {
      sourceTexts[key] = el.getAttribute('aria-label').trim();
    }
  });
  
  return sourceTexts;
}

/**
 * Récupère les traductions depuis le backend (DB MySQL)
 */
async function fetchTranslationsFromDB(targetLang, keys) {
  try {
    const response = await fetch(`${API_GET_TRANSLATIONS}?lang=${targetLang}&keys=${keys.join(',')}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data.translations || {};
  } catch (error) {
    console.error('[i18n] Erreur récupération DB:', error);
    return null;
  }
}

/**
 * Traduit via l'API Grok et sauvegarde en DB
 */
async function translateAndSave(texts, targetLang) {
  try {
    const response = await fetch(API_TRANSLATE, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        texts: texts,
        sourceLang: 'en',
        targetLang: targetLang
      })
    });
    
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    
    const data = await response.json();
    return data.translations || null;
    
  } catch (error) {
    console.error('[i18n] Erreur traduction API:', error);
    return null;
  }
}

/**
 * Charge les traductions (DB -> API Grok si manquant)
 */
async function loadTranslations(targetLang) {
  // Si langue source (anglais), utiliser le texte HTML directement
  if (targetLang === 'en') {
    return extractSourceTexts();
  }
  
  const sourceTexts = extractSourceTexts();
  const keys = Object.keys(sourceTexts);
  
  if (keys.length === 0) return {};
  
  // 1. Essayer de récupérer depuis la DB
  let translations = await fetchTranslationsFromDB(targetLang, keys);
  
  if (translations && Object.keys(translations).length === keys.length) {
    console.log(`[i18n] Traductions chargées depuis DB pour ${targetLang}`);
    return translations;
  }
  
  // 2. Si incomplet, traduire via Grok API
  showLoadingIndicator();
  console.log(`[i18n] Traduction via Grok API pour ${targetLang}...`);
  
  const textsArray = keys.map(k => sourceTexts[k]);
  const translatedTexts = await translateAndSave(textsArray, targetLang);
  
  hideLoadingIndicator();
  
  if (translatedTexts && translatedTexts.length === textsArray.length) {
    // Construire l'objet traductions
    translations = {};
    keys.forEach((key, index) => {
      translations[key] = translatedTexts[index];
    });
    
    console.log(`[i18n] Traductions Grok sauvegardées en DB pour ${targetLang}`);
    return translations;
  }
  
  // 3. Fallback: texte anglais
  console.warn(`[i18n] Fallback vers anglais pour ${targetLang}`);
  return sourceTexts;
}

/**
 * Détecte la langue préférée
 */
function detectLanguage() {
  // 1. localStorage
  const saved = localStorage.getItem('vai_lang');
  if (saved && SUPPORTED_LANGS.includes(saved)) return saved;
  
  // 2. Navigateur
  const browserLang = navigator.language?.toLowerCase();
  if (browserLang) {
    if (SUPPORTED_LANGS.includes(browserLang)) return browserLang;
    const baseLang = browserLang.split('-')[0];
    if (SUPPORTED_LANGS.includes(baseLang)) return baseLang;
  }
  
  // 3. Fallback anglais
  return DEFAULT_LANG;
}

/**
 * Applique les traductions au DOM
 */
function applyTranslations(translations) {
  // Texte content
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    if (translations[key]) {
      el.textContent = translations[key];
    }
  });
  
  // Placeholder
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    if (translations[key]) {
      el.placeholder = translations[key];
    }
  });
  
  // Title
  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.dataset.i18nTitle;
    if (translations[key]) {
      el.title = translations[key];
    }
  });
  
  // Aria-label
  document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
    const key = el.dataset.i18nAriaLabel;
    if (translations[key]) {
      el.setAttribute('aria-label', translations[key]);
    }
  });
  
  // Value
  document.querySelectorAll('[data-i18n-value]').forEach(el => {
    const key = el.dataset.i18nValue;
    if (translations[key]) {
      el.value = translations[key];
    }
  });
}

/**
 * Met à jour le sélecteur de langue
 */
function updateLanguageSwitcher(lang) {
  document.querySelectorAll('[data-lang-btn]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.langBtn === lang);
  });
}

/**
 * Indicateur de chargement
 */
function showLoadingIndicator() {
  let indicator = document.getElementById('i18n-loading');
  if (!indicator) {
    indicator = document.createElement('div');
    indicator.id = 'i18n-loading';
    indicator.style.cssText = `
      position: fixed;
      top: 10px;
      right: 10px;
      background: var(--accent, #22c55e);
      color: white;
      padding: 8px 16px;
      border-radius: 6px;
      font-size: 13px;
      z-index: 9999;
      font-family: system-ui, sans-serif;
      box-shadow: 0 2px 8px rgba(0,0,0,0.3);
    `;
    document.body.appendChild(indicator);
  }
  indicator.textContent = '🌐 Translating...';
  indicator.style.display = 'block';
}

function hideLoadingIndicator() {
  const indicator = document.getElementById('i18n-loading');
  if (indicator) {
    indicator.style.display = 'none';
  }
}

/**
 * Initialise i18n
 */
async function initI18n() {
  const lang = detectLanguage();
  
  currentTranslations = await loadTranslations(lang);
  applyTranslations(currentTranslations);
  
  document.documentElement.lang = lang;
  localStorage.setItem('vai_lang', lang);
  updateLanguageSwitcher(lang);
  
  console.log(`[i18n] Langue: ${lang}`);
  return { lang, translations: currentTranslations };
}

/**
 * Change de langue
 */
async function switchLanguage(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) {
    console.warn(`[i18n] Langue non supportée: ${lang}`);
    return;
  }
  
  if (lang !== 'en') {
    showLoadingIndicator();
  }
  
  localStorage.setItem('vai_lang', lang);
  currentTranslations = await loadTranslations(lang);
  applyTranslations(currentTranslations);
  
  hideLoadingIndicator();
  
  document.documentElement.lang = lang;
  updateLanguageSwitcher(lang);
  
  window.dispatchEvent(new CustomEvent('languageChanged', { detail: { lang } }));
  
  console.log(`[i18n] Changé vers: ${lang}`);
  return currentTranslations;
}

/**
 * Fonction de traduction rapide
 */
function t(key) {
  return currentTranslations[key] || key;
}

/**
 * Force la régénération des traductions (supprime et recrée)
 */
async function refreshTranslations(lang) {
  try {
    await fetch(`${API_BASE}/clear?lang=${lang}`, { method: 'POST' });
    console.log(`[i18n] Cache DB effacé pour ${lang}`);
    
    if (localStorage.getItem('vai_lang') === lang) {
      await switchLanguage(lang);
    }
  } catch (error) {
    console.error('[i18n] Erreur refresh:', error);
  }
}

// API globale
window.i18n = {
  t,
  switchLanguage,
  detectLanguage,
  refreshTranslations,
  supportedLangs: SUPPORTED_LANGS,
  getCurrentLang: () => localStorage.getItem('vai_lang') || DEFAULT_LANG,
  init: initI18n
};

// Auto-init
document.addEventListener('DOMContentLoaded', initI18n);
