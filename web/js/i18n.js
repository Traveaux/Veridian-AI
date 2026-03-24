// Supported languages (15 major languages)
const SUPPORTED_LANGS = ['fr', 'en', 'es', 'de', 'ru', 'pt', 'it', 'ja', 'zh', 'ko', 'ar', 'pl', 'th', 'bn', 'hi'];
const DEFAULT_LANG = 'en';
let currentTranslations = {};

// Load translations from JSON files
async function loadTranslations(lang) {
  try {
    const res = await fetch(`/locales/${lang}.json`);
    if (!res.ok) throw new Error(`Failed to load ${lang}`);
    return await res.json();
  } catch (error) {
    console.warn(`Failed to load ${lang}, falling back to ${DEFAULT_LANG}`);
    try {
      const res = await fetch(`/locales/${DEFAULT_LANG}.json`);
      return await res.json();
    } catch (err) {
      console.error('Failed to load default language', err);
      return {};
    }
  }
}

// Detect user language preference
function detectLanguage() {
  // 1. Check if user already chose a language (localStorage)
  const saved = localStorage.getItem('vai_lang');
  if (saved && SUPPORTED_LANGS.includes(saved)) return saved;

  // 2. Detect browser language
  const browserLang = navigator.language?.slice(0, 2).toLowerCase();
  if (SUPPORTED_LANGS.includes(browserLang)) return browserLang;

  // 3. Fallback to English
  return DEFAULT_LANG;
}

// Apply translations to HTML elements
function applyTranslations(translations) {
  // Replace text content for [data-i18n="key"]
  document.querySelectorAll('[data-i18n]').forEach(el => {
    const key = el.dataset.i18n;
    if (translations[key]) {
      el.textContent = translations[key];
    }
  });

  // Replace attributes for [data-i18n-placeholder], [data-i18n-title], etc.
  document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
    const key = el.dataset.i18nPlaceholder;
    if (translations[key]) el.placeholder = translations[key];
  });

  document.querySelectorAll('[data-i18n-title]').forEach(el => {
    const key = el.dataset.i18nTitle;
    if (translations[key]) el.title = translations[key];
  });

  document.querySelectorAll('[data-i18n-aria-label]').forEach(el => {
    const key = el.dataset.i18nAriaLabel;
    if (translations[key]) el.setAttribute('aria-label', translations[key]);
  });

  document.querySelectorAll('[data-i18n-value]').forEach(el => {
    const key = el.dataset.i18nValue;
    if (translations[key]) el.value = translations[key];
  });

  // HTML content (careful with XSS - only use for trusted content)
  document.querySelectorAll('[data-i18n-html]').forEach(el => {
    const key = el.dataset.i18nHtml;
    // Security: treat as text, not raw HTML, to prevent XSS via translation files.
    if (translations[key]) el.textContent = translations[key];
  });
}

// Update language switcher visual state
function updateLanguageSwitcher(lang) {
  document.querySelectorAll('[data-lang-btn]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.langBtn === lang);
  });
}

// Initialize i18n on page load
async function initI18n() {
  const lang = detectLanguage();
  currentTranslations = await loadTranslations(lang);
  applyTranslations(currentTranslations);

  // Update HTML lang attribute for accessibility
  document.documentElement.lang = lang;

  // Save language preference
  localStorage.setItem('vai_lang', lang);

  // Update language switcher if present
  updateLanguageSwitcher(lang);

  console.log(`Loaded language: ${lang}`);
  return { lang, translations: currentTranslations };
}

// Switch language manually (from language selector)
async function switchLanguage(lang) {
  if (!SUPPORTED_LANGS.includes(lang)) {
    console.warn(`Language ${lang} not supported`);
    return;
  }

  localStorage.setItem('vai_lang', lang);
  currentTranslations = await loadTranslations(lang);
  applyTranslations(currentTranslations);
  document.documentElement.lang = lang;
  updateLanguageSwitcher(lang);

  console.log(`Switched to language: ${lang}`);
  return currentTranslations;
}

// Get current translation key (useful for dynamic content)
function t(key) {
  return currentTranslations[key] || key;
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initI18n);
} else {
  initI18n();
}
