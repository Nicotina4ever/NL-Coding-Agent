"""Small Qt-compatible UI internationalization service (Studio UX U1).

The service is intentionally local and deterministic: JSON catalogs under
nl_coding_agent/gui/locales, no network, no machine translation and no mutation of
agent/model/code/documentation language settings. UI language is a presentation
preference only.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Iterable, Mapping

from PySide6.QtCore import QObject, QTranslator, QLocale, QCoreApplication, Signal

DEFAULT_LANGUAGE = "it"
FALLBACK_LANGUAGE = "en"
SYSTEM_PREFERENCES = ("system", "auto")
_LOCALE_DIR = Path(__file__).resolve().parent / "locales"
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class CatalogError(ValueError):
    """Raised only for malformed catalog input; runtime lookups fail soft."""


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def format_message(template: str, **values) -> str:
    """Format named placeholders; unknown placeholders remain visible, never raise."""
    try:
        return str(template).format_map(_SafeDict(values))
    except Exception:
        return str(template)


class TranslationService(QObject):
    """Catalog-backed translation service with Qt retranslation hooks."""

    language_changed = Signal(str)

    def __init__(self, services=None, *, catalog_dir: str | Path | None = None,
                 system_locale: str | None = None):
        super().__init__()
        self._services = services
        self._catalog_dir = Path(catalog_dir) if catalog_dir else _LOCALE_DIR
        self._catalogs: dict[str, dict] = {}
        self._supported: dict[str, dict] = {}
        self._reverse_en: dict[str, str] = {}
        self._callbacks: list = []
        self._translator: QTranslator | None = None
        self._system_locale_override = system_locale
        self._load_catalogs()
        self._preference = self._read_preference()
        self._language = self.resolve_language(self._preference)

    # ------------------------------------------------------------- catalogs
    def _load_catalogs(self) -> None:
        if not self._catalog_dir.is_dir():
            self._catalogs = {}
            self._supported = {}
            return
        for path in sorted(self._catalog_dir.glob("*.json")):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not isinstance(raw, Mapping):
                continue
            locale = str(raw.get("locale") or path.stem).strip().lower()
            strings = raw.get("strings")
            if not locale or not isinstance(strings, Mapping):
                continue
            clean = {str(key): str(value) for key, value in strings.items()}
            if locale == FALLBACK_LANGUAGE:
                clean = {k: v for k, v in clean.items()}
            self._catalogs[locale] = clean
            self._supported[locale] = {
                "code": locale,
                "name": str(raw.get("name") or locale),
                "version": int(raw.get("version") or 1),
            }
        if FALLBACK_LANGUAGE not in self._catalogs:
            self._catalogs[FALLBACK_LANGUAGE] = {}
        self._reverse_en = {}
        for key, value in self._catalogs[FALLBACK_LANGUAGE].items():
            self._reverse_en.setdefault(str(value), str(key))
        self._supported.setdefault(FALLBACK_LANGUAGE, {
            "code": FALLBACK_LANGUAGE, "name": "English", "version": 0})

    def supported_codes(self) -> list[str]:
        codes = [code for code in (DEFAULT_LANGUAGE, FALLBACK_LANGUAGE)
                 if code in self._supported]
        codes.extend(sorted(code for code in self._supported if code not in codes))
        return codes

    def supported_languages(self) -> list[dict]:
        return [dict(self._supported[code]) for code in self.supported_codes()]

    def has_catalog(self, language: str) -> bool:
        return str(language or "").lower() in self._catalogs

    # ------------------------------------------------------------ resolution
    @staticmethod
    def language_for_locale(locale_name: str | None) -> str | None:
        name = str(locale_name or "").strip().lower().replace("-", "_")
        if not name:
            return None
        primary = name.split("_", 1)[0]
        if primary in (DEFAULT_LANGUAGE, FALLBACK_LANGUAGE):
            return primary
        return None

    def detect_system_language(self) -> str | None:
        if self._system_locale_override is not None:
            return self.language_for_locale(self._system_locale_override)
        try:
            name = QLocale.system().name()
        except Exception:
            return None
        return self.language_for_locale(name)

    def _read_preference(self) -> str:
        if self._services is not None:
            for name in ("ui_language_preference", "get_ui_language"):
                method = getattr(self._services, name, None)
                if callable(method):
                    try:
                        value = method()
                    except Exception:
                        value = None
                    if value:
                        return str(value).strip().lower()
        return DEFAULT_LANGUAGE

    def resolve_language(self, preference: str | None = None,
                         system_locale: str | None = None) -> str:
        pref = str(preference or self._preference or DEFAULT_LANGUAGE).strip().lower()
        if pref == "":
            pref = DEFAULT_LANGUAGE
        if pref in self._catalogs and pref not in SYSTEM_PREFERENCES:
            return pref
        if pref in SYSTEM_PREFERENCES:
            if system_locale is not None:
                detected = self.language_for_locale(system_locale)
            else:
                detected = self.detect_system_language()
            if detected and detected in self._catalogs:
                return detected
            return DEFAULT_LANGUAGE
        # Unknown/fresh preference: Italian installation default.
        return DEFAULT_LANGUAGE

    @property
    def preference(self) -> str:
        return self._preference

    @property
    def current_language(self) -> str:
        return self._language

    def language(self) -> str:
        return self._language

    def language_name(self, code: str | None = None) -> str:
        item = self._supported.get(str(code or self._language))
        return str(item.get("name")) if item else str(code or "")

    def system_language_name(self) -> str:
        detected = self.detect_system_language()
        return self.language_name(detected) if detected else self.language_name(
            DEFAULT_LANGUAGE)

    # ----------------------------------------------------------- translation
    def _lookup(self, language: str, key: str) -> str | None:
        catalog = self._catalogs.get(language) or {}
        value = catalog.get(str(key))
        if value is not None:
            return str(value)
        if language != FALLBACK_LANGUAGE:
            fallback = self._catalogs.get(FALLBACK_LANGUAGE) or {}
            if str(key) in fallback:
                return str(fallback[str(key)])
        return None

    def tr(self, key: str, default: str | None = None, **values) -> str:
        template = self._lookup(self._language, str(key))
        if template is None:
            template = self._lookup(FALLBACK_LANGUAGE, str(key))
        if template is None:
            template = default if default is not None else str(key)
        return format_message(template, **values)

    translate = tr

    def tr_source(self, source_text: str, default: str | None = None,
                  **values) -> str:
        """Translate an English source string via reverse catalog lookup."""
        source = str(source_text)
        key = self._reverse_en.get(source)
        if key is not None:
            translated = self._lookup(self._language, key)
            if translated is not None:
                return format_message(translated, **values)
        # Also accept a catalog key directly (defensive for Qt callers).
        direct = self._lookup(self._language, source)
        if direct is not None:
            return format_message(direct, **values)
        if default is not None:
            return format_message(default, **values)
        return source

    def retranslate(self) -> None:
        self._install_translator()
        self.language_changed.emit(self._language)
        for callback in list(self._callbacks):
            try:
                callback(self._language)
            except Exception:
                pass

    def register_retranslate(self, callback) -> None:
        if callback not in self._callbacks:
            self._callbacks.append(callback)

    def unregister_retranslate(self, callback) -> None:
        try:
            self._callbacks.remove(callback)
        except ValueError:
            pass

    # --------------------------------------------------------------- switching
    def set_language(self, preference: str, *, persist: bool = True) -> dict:
        pref = str(preference or "").strip().lower()
        if not pref:
            raise CatalogError("language preference must not be empty")
        if pref not in self._catalogs and pref not in SYSTEM_PREFERENCES:
            raise CatalogError("unsupported UI language: " + repr(preference))
        resolved = self.resolve_language(pref)
        if persist and self._services is not None:
            setter = getattr(self._services, "set_ui_language", None)
            if callable(setter):
                result = setter(pref)
                if isinstance(result, dict) and not result.get("ok", True):
                    raise CatalogError(str(result.get("error") or "cannot persist language"))
        self._preference = pref
        self._language = resolved
        self.retranslate()
        return {"ok": True, "preference": pref, "language": resolved,
                "language_name": self.language_name(resolved)}

    def _install_translator(self) -> None:
        app = QCoreApplication.instance()
        if app is None:
            return
        if self._translator is not None:
            try:
                app.removeTranslator(self._translator)
            except Exception:
                pass
            self._translator = None
        translator = _CatalogTranslator(self)
        try:
            if app.installTranslator(translator):
                self._translator = translator
        except Exception:
            self._translator = None

    def install(self, app=None) -> None:
        self._install_translator()


class _CatalogTranslator(QTranslator):
    """QTranslator adapter so Qt's own retranslate machinery sees the catalog."""

    def __init__(self, service: TranslationService):
        super().__init__()
        self._service = service

    def translate(self, context, source_text, disambiguation=None, n=-1):
        if not source_text:
            return ""
        translated = self._service.tr_source(str(source_text), None)
        # Return source text for unknown/English strings so Qt passthrough is
        # observable and never empty for a known caller string.
        return translated or str(source_text)


_INSTANCE: TranslationService | None = None



def tr_for(translator, key: str, default: str | None = None, **values) -> str:
    """Translate when a translator is injected; otherwise return English source.

    Direct widget construction (tests/tools) stays language-neutral unless the
    application explicitly supplies a TranslationService.
    """
    if translator is not None:
        try:
            return translator.tr(key, default, **values)
        except Exception:
            pass
    template = default if default is not None else str(key)
    return format_message(template, **values)


def create_i18n(services=None, **kwargs) -> TranslationService:
    return TranslationService(services, **kwargs)


def get_i18n(services=None) -> TranslationService:
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = TranslationService(services)
    elif services is not None and getattr(_INSTANCE, "_services", None) is not services:
        _INSTANCE = TranslationService(services)
    return _INSTANCE


def reset_i18n() -> None:
    global _INSTANCE
    _INSTANCE = None


def tr(key: str, default: str | None = None, **values) -> str:
    return get_i18n().tr(key, default, **values)


def translate(key: str, default: str | None = None, **values) -> str:
    return tr(key, default, **values)


def ui_text(source: str) -> str:
    """Translate legacy presentation literals using the existing source catalog."""
    if _INSTANCE is None or _INSTANCE._services is None:
        return source
    return _INSTANCE.tr_source(source)

# Public aliases for consumers that prefer a shorter name.
I18n = TranslationService


def set_language(preference: str, *, persist: bool = True) -> dict:
    return get_i18n().set_language(preference, persist=persist)


def current_language() -> str:
    return get_i18n().current_language


def supported_languages() -> list[dict]:
    return get_i18n().supported_languages()


def resolve_language(preference: str | None = None,
                     system_locale: str | None = None) -> str:
    return get_i18n().resolve_language(preference, system_locale)
