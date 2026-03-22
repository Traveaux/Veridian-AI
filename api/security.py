"""
Security helpers shared across the API.

Goals:
- Avoid hardcoded / weak default secrets in production.
- Provide safe(ish) development fallbacks without leaking secrets.
"""

from __future__ import annotations

import os
import secrets
from pathlib import Path
from loguru import logger


def is_production() -> bool:
    env = (os.getenv("ENVIRONMENT") or "development").strip().lower()
    return env in {"prod", "production"}


def _is_weak_secret(value: str | None, *, min_len: int = 32) -> bool:
    if not value:
        return True
    v = value.strip()
    if len(v) < min_len:
        return True
    if v.lower() in {"change_me_in_production", "changeme", "default", "secret"}:
        return True
    return False


def _project_root() -> Path:
    # api/security.py -> api/ -> project root
    return Path(__file__).resolve().parents[1]


def _load_or_create_persistent_secret(env_key: str, filename: str) -> str | None:
    """
    Dev-only helper: persist a generated secret to disk so multiple workers/processes
    share the same secret (avoids random 401 when JWT is signed in worker A and verified in worker B).
    """
    try:
        secret = os.getenv(env_key)
        if secret and not _is_weak_secret(secret):
            return secret

        secret_file = _project_root() / "logs" / filename
        secret_file.parent.mkdir(parents=True, exist_ok=True)

        if secret_file.exists():
            val = secret_file.read_text(encoding="utf-8", errors="replace").strip()
            if not _is_weak_secret(val):
                os.environ[env_key] = val
                return val

        generated = secrets.token_urlsafe(48)
        secret_file.write_text(generated, encoding="utf-8")
        try:
            secret_file.chmod(0o600)
        except Exception:
            pass
        os.environ[env_key] = generated
        return generated
    except Exception as e:
        logger.warning(f"{env_key} persistent secret fallback failed: {e}")
        return None


def get_jwt_secret() -> str:
    """
    Returns a JWT secret.

    - Production: must be set and strong, otherwise raise.
    - Development: if missing/weak, generate an ephemeral secret for this process.
    """
    secret = os.getenv("JWT_SECRET")
    if not _is_weak_secret(secret):
        return secret  # type: ignore[return-value]

    if is_production():
        raise RuntimeError("JWT_SECRET manquant ou trop faible (production).")

    # Dev fallback: persist the secret to disk so it is stable across workers.
    persisted = _load_or_create_persistent_secret("JWT_SECRET", ".jwt_secret")
    if persisted:
        logger.warning("JWT_SECRET manquant/faible: secret persistant genere/charge (mode developpement).")
        return persisted

    # Last resort: ephemeral, per-process.
    generated = secrets.token_urlsafe(48)
    os.environ["JWT_SECRET"] = generated
    logger.warning("JWT_SECRET manquant/faible: secret ephemere genere (mode developpement).")
    return generated


def get_internal_api_secret() -> str:
    """
    Secret used for bot/service-to-API calls (X-API-SECRET).

    - Production: must be set and strong, otherwise raise.
    - Development: if missing/weak, generate an ephemeral secret for this process.
    """
    secret = os.getenv("INTERNAL_API_SECRET")
    if not _is_weak_secret(secret):
        return secret  # type: ignore[return-value]

    if is_production():
        raise RuntimeError("INTERNAL_API_SECRET manquant ou trop faible (production).")

    persisted = _load_or_create_persistent_secret("INTERNAL_API_SECRET", ".internal_api_secret")
    if persisted:
        logger.warning("INTERNAL_API_SECRET manquant/faible: secret persistant genere/charge (mode developpement).")
        return persisted

    generated = secrets.token_urlsafe(48)
    os.environ["INTERNAL_API_SECRET"] = generated
    logger.warning("INTERNAL_API_SECRET manquant/faible: secret ephemere genere (mode developpement).")
    return generated


def security_headers() -> dict[str, str]:
    """
    Security headers for API JSON responses.
    Note: frontend HTML is served separately (web/), so CSP for the dashboard
    is handled in HTML meta or the web server config.
    """
    return {
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self';",
        # API responses should not be cached (tokens, configs, PII).
        "Cache-Control": "no-store",
        "Pragma": "no-cache",
    }
