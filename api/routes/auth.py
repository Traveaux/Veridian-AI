"""
OAuth2 Discord Authentication — Architecture securisee v0.3
Flux :
  1. Discord -> /auth/callback?code=DISCORD_CODE
  2. API echange le code, genere JWT + temp_code (DB, 60s, usage unique)
  3. Redirect vers dashboard.html?auth=TEMP_CODE
  4. JS POST /auth/exchange {code} -> recoit {token, user, guilds}
  5. JWT stocke en localStorage uniquement — jamais dans une URL
"""

from fastapi import APIRouter, HTTPException, Query, Request, Cookie
from fastapi.responses import RedirectResponse, JSONResponse
import aiohttp
import os
import secrets
from datetime import datetime, timedelta
import jwt
from loguru import logger
from urllib.parse import urlencode

from bot.db.connection import get_db_context
from bot.db.models import DashboardSessionModel, DashboardUserModel, TempCodeModel
from bot.config import DB_TABLE_PREFIX, BOT_OWNER_DISCORD_ID

from api.security import get_jwt_secret, is_production

router = APIRouter(prefix="/auth", tags=["auth"])

DISCORD_API_BASE  = "https://discord.com/api/v10"
DISCORD_OAUTH_URL = "https://discord.com/api/v10/oauth2/authorize"

def _get_bearer_token_from_request(request: Request) -> str | None:
    """
    Extract a bearer token from either:
      - Authorization: Bearer <token>
      - X-VAI-Authorization: Bearer <token>   (fallback for proxies that strip Authorization)
      - X-VAI-Authorization: <token>
    """
    auth_header = request.headers.get("Authorization", "") or ""
    alt_header = request.headers.get("X-VAI-Authorization", "") or ""

    if auth_header.startswith("Bearer "):
        return auth_header[7:]
    if alt_header.startswith("Bearer "):
        return alt_header[7:]
    if alt_header:
        return alt_header.strip()
    return None


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _get_redirect_uri() -> str:
    explicit = os.getenv("DISCORD_REDIRECT_URI")
    if explicit:
        return explicit
    api_domain = os.getenv("API_DOMAIN", "api.veridiancloud.xyz")
    return f"https://{api_domain}/auth/callback"


def _get_dashboard_url() -> str:
    return os.getenv("DASHBOARD_URL", "https://veridiancloud.xyz/dashboard.html")


def get_active_guild_ids() -> list:
    try:
        with get_db_context() as conn:
            cursor = conn.cursor()
            cursor.execute(f"SELECT id FROM {DB_TABLE_PREFIX}guilds")
            return [int(row[0]) for row in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Erreur recuperation guilds: {e}")
        return []


async def _exchange_code_and_fetch_user(code: str, redirect_uri: str) -> dict:
    client_id     = os.getenv("DISCORD_CLIENT_ID")
    client_secret = os.getenv("DISCORD_CLIENT_SECRET")
    async with aiohttp.ClientSession() as session:
        token_resp = await session.post(
            f"{DISCORD_API_BASE}/oauth2/token",
            data={
                "client_id":     client_id,
                "client_secret": client_secret,
                "grant_type":    "authorization_code",
                "code":          code,
                "redirect_uri":  redirect_uri,
            },
        )
        if token_resp.status != 200:
            err = await token_resp.text()
            logger.error(f"Token exchange failed ({token_resp.status}): {err}")
            raise HTTPException(status_code=400, detail=f"Token exchange failed: {err}")
        token_data   = await token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise HTTPException(status_code=400, detail="Pas d'access_token Discord")
        headers     = {"Authorization": f"Bearer {access_token}"}
        user_resp   = await session.get(f"{DISCORD_API_BASE}/users/@me", headers=headers)
        if user_resp.status != 200:
            raise HTTPException(status_code=400, detail="Impossible de recuperer le profil")
        user        = await user_resp.json()
        guilds_resp = await session.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
        guilds      = await guilds_resp.json() if guilds_resp.status == 200 else []
    return {"access_token": access_token, "user": user, "guilds": guilds}


def _build_filtered_guilds(all_guilds: list) -> list:
    ADMIN_PERM    = 0x8
    bot_guild_ids = set(get_active_guild_ids())
    result = []
    for g in all_guilds:
        try:
            perms    = int(g.get("permissions", 0))
            guild_id = int(g.get("id", 0))
            is_owner = bool(g.get("owner", False))
            is_admin = bool(perms & ADMIN_PERM)
            if is_owner or is_admin:
                result.append({
                    "id":   str(guild_id),
                    "name": g.get("name", "Unknown"),
                    "icon": (
                        f"https://cdn.discordapp.com/icons/{guild_id}/{g['icon']}.png"
                        if g.get("icon") else None
                    ),
                    "bot_present": guild_id in bot_guild_ids,
                    "is_owner": is_owner,
                    "is_admin": is_admin,
                })
        except Exception:
            pass
    return result


def _build_avatar_url(user: dict, user_id: int) -> str:
    if user.get("avatar"):
        return f"https://cdn.discordapp.com/avatars/{user_id}/{user['avatar']}.png?size=128"
    return f"https://cdn.discordapp.com/embed/avatars/{user_id % 5}.png"


def _create_jwt(user_id: int, username: str, is_super_admin: bool, guild_ids: list[int]) -> str:
    secret = get_jwt_secret()
    return jwt.encode(
        {
            # RFC 7519: "sub" should be a string.
            "sub":            str(user_id),
            "username":       username,
            "is_super_admin": is_super_admin,
            # IMPORTANT: do NOT embed large guild lists into the JWT.
            # Some infrastructures (proxies/CDNs) may truncate large Authorization headers,
            # making the token impossible to verify ("Token invalide").
            # Access control is enforced server-side via DB session (guild_ids_json).
            "iss":            "veridian-api",
            "aud":            "veridian-dashboard",
            "iat":            datetime.utcnow(),
            "exp":            datetime.utcnow() + timedelta(days=7),
        },
        secret,
        algorithm="HS256",
    )


def _save_session(discord_user_id: int, discord_username: str,
                  access_token: str, jwt_token: str, guild_ids: list[int]):
    try:
        import json
        DashboardSessionModel.create(
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            access_token=access_token,
            jwt_token=jwt_token,
            guild_ids_json=json.dumps(guild_ids),
            expires_at=datetime.utcnow() + timedelta(days=7),
        )
    except Exception as e:
        logger.warning(f"Session non sauvegardee en DB: {e}")


# ─────────────────────────────────────────────────────────────
# Routes
# ─────────────────────────────────────────────────────────────

@router.get("/discord/login")
def discord_login():
    client_id    = os.getenv("DISCORD_CLIENT_ID")
    redirect_uri = _get_redirect_uri()
    if not client_id:
        raise HTTPException(status_code=500, detail="DISCORD_CLIENT_ID manquant")

    # OAuth CSRF protection: state stored server-side in a cookie
    state = secrets.token_urlsafe(24)
    query_params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "identify email guilds",
        "state": state,
    }
    auth_url = f"{DISCORD_OAUTH_URL}?{urlencode(query_params)}"
    logger.info(f"Login Discord -> {redirect_uri}")
    resp = RedirectResponse(url=auth_url)
    # SameSite=Lax: sent on top-level GET callback; HttpOnly prevents JS read.
    resp.set_cookie(
        "vai_oauth_state",
        state,
        max_age=600,
        httponly=True,
        secure=is_production(),
        samesite="lax",
        path="/auth",
    )
    return resp


@router.get("/callback")
async def discord_callback(
    code:  str = Query(None),
    error: str = Query(None),
    state: str = Query(None),
    vai_oauth_state: str | None = Cookie(default=None),
):
    """
    Callback OAuth2 Discord.
    Genere un temp_code en DB (60s, usage unique) et redirige
    vers le dashboard avec ?auth=TEMP_CODE.
    Le JWT ne passe JAMAIS dans l'URL.
    """
    dashboard_url = _get_dashboard_url()

    # Validate OAuth 'state' to prevent login CSRF.
    if not state or not vai_oauth_state or state != vai_oauth_state:
        # Always redirect to dashboard with a generic error (avoid reflecting raw values).
        resp = RedirectResponse(url=f"{dashboard_url}?error=invalid_state", status_code=302)
        resp.delete_cookie("vai_oauth_state", path="/auth")
        return resp

    if error:
        resp = RedirectResponse(url=f"{dashboard_url}?error=oauth_error", status_code=302)
        resp.delete_cookie("vai_oauth_state", path="/auth")
        return resp
    if not code:
        raise HTTPException(status_code=400, detail="Code manquant")

    data     = await _exchange_code_and_fetch_user(code, _get_redirect_uri())
    user     = data["user"]
    user_id  = int(user.get("id", 0))
    username = user.get("username", "Unknown")
    email    = user.get("email")
    verified = bool(user.get("verified", False))

    bot_owner_id_raw = os.getenv("BOT_OWNER_DISCORD_ID")
    bot_owner_id     = int(bot_owner_id_raw) if bot_owner_id_raw else int(BOT_OWNER_DISCORD_ID or 0)
    is_super_admin  = user_id == bot_owner_id
    filtered_guilds = _build_filtered_guilds(data["guilds"])
    guild_ids       = [int(g["id"]) for g in filtered_guilds if g.get("id")]
    jwt_token       = _create_jwt(user_id, username, is_super_admin, guild_ids)

    _save_session(user_id, username, data["access_token"], jwt_token, guild_ids)

    # Stocker le compte dashboard (+ email) pour stats & upgrades futures.
    try:
        DashboardUserModel.upsert(
            discord_user_id=user_id,
            discord_username=username,
            email=email,
            email_verified=verified,
            avatar_url=_build_avatar_url(user, user_id),
        )
    except Exception as e:
        # Non-bloquant: l'auth doit continuer meme si la table n'est pas encore migree.
        logger.warning(f"DashboardUserModel.upsert a echoue (table manquante ?): {e}")

    user_data = {
        "id":             str(user_id),
        "username":       username,
        "avatar":         _build_avatar_url(user, user_id),
        "is_super_admin": is_super_admin,
    }

    # Stocker en DB — survit aux redemarrages, atomique (FOR UPDATE)
    temp_code = secrets.token_urlsafe(24)
    ok = TempCodeModel.create(temp_code, jwt_token, user_data, filtered_guilds)
    if not ok:
        # La table vai_temp_codes n'existe peut-etre pas encore
        # -> executer le schema.sql pour la creer
        logger.error("TempCodeModel.create a echoue — la table vai_temp_codes existe-t-elle ?")
        raise HTTPException(
            status_code=500,
            detail="Erreur interne: table vai_temp_codes manquante. Executez le schema.sql."
        )

    # Nettoyage opportuniste (non bloquant)
    try:
        TempCodeModel.cleanup()
    except Exception:
        pass

    logger.info(f"OAuth OK: {username} ({user_id}) super_admin={is_super_admin}")

    resp = RedirectResponse(
        url=f"{dashboard_url}?auth={temp_code}",
        status_code=302,
    )
    # Clear state cookie after successful callback.
    resp.delete_cookie("vai_oauth_state", path="/auth")
    return resp


@router.post("/exchange")
async def exchange_temp_code(request: Request):
    """
    Echange un temp_code contre {token, user, guilds}.
    Usage unique, expire en 60 secondes, atomique en DB (FOR UPDATE).
    Body JSON: { "code": "..." }
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Body JSON invalide")

    temp_code = body.get("code")
    if not temp_code:
        raise HTTPException(status_code=400, detail="Champ 'code' manquant")

    data = TempCodeModel.consume(temp_code)
    if not data:
        raise HTTPException(status_code=400, detail="Code invalide, expire ou deja utilise")

    logger.info(f"Temp code echange: {data['user'].get('username')}")

    # Ensure a DB session row exists for this JWT (some older DB schemas or strict SQL modes
    # could cause the callback insert to fail, which would then make /internal/* return 401).
    try:
        try:
            status = DashboardSessionModel.token_status(data["jwt"])
        except Exception:
            status = "missing"

        if status == "missing":
            u = data.get("user") or {}
            guild_ids = [int(g.get("id")) for g in (data.get("guilds") or []) if g.get("id")]
            import json
            DashboardSessionModel.create(
                discord_user_id=int(u.get("id") or 0),
                discord_username=str(u.get("username") or "Unknown"),
                access_token="",
                jwt_token=data["jwt"],
                guild_ids_json=json.dumps(guild_ids),
                expires_at=datetime.utcnow() + timedelta(days=7),
            )
    except Exception as e:
        logger.warning(f"Dashboard session ensure failed: {e}")

    return JSONResponse(
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        content={
        "token":  data["jwt"],
        "user":   data["user"],
        "guilds": data["guilds"],
    })


@router.get("/user/me")
async def get_current_user(request: Request):
    """Valide le JWT Bearer et retourne les infos utilisateur."""
    token = _get_bearer_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Header Authorization manquant")
    try:
        # Enforce server-side revocation/expiry via DB session.
        try:
            try:
                status = DashboardSessionModel.token_status(token)
            except Exception as e:
                logger.warning(f"Session status check error: {e}")
                status = "missing"

            if status in {"revoked", "expired"}:
                raise HTTPException(status_code=401, detail="Session invalide ou revoquee")
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Session check error: {e}")
            # Stateless fallback: accept valid JWT even if DB session is missing/broken.

        secret  = get_jwt_secret()
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            audience="veridian-dashboard",
            issuer="veridian-api",
        )
        # Guild allowlist is stored server-side in DB (dashboard session).
        guild_ids = payload.get("guild_ids", [])
        try:
            allowed = DashboardSessionModel.allowed_guild_ids(token)
            if allowed is not None:
                guild_ids = allowed
        except Exception:
            pass
        return {
            "user_id":        payload.get("sub"),
            "username":       payload.get("username"),
            "is_super_admin": payload.get("is_super_admin", False),
            "guild_ids":      guild_ids,
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expire")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token invalide")


@router.get("/user/guilds")
async def get_current_user_guilds(request: Request):
    """
    Returns the filtered guild list for the current user (from Discord),
    using the access_token stored in the dashboard session DB row.
    """
    token = _get_bearer_token_from_request(request)
    if not token:
        raise HTTPException(status_code=401, detail="Header Authorization manquant")

    try:
        status = DashboardSessionModel.token_status(token)
    except Exception as e:
        logger.warning(f"Session status check error: {e}")
        status = "missing"

    if status in {"revoked", "expired"}:
        raise HTTPException(status_code=401, detail="Session invalide ou revoquee")

    session_row = None
    try:
        session_row = DashboardSessionModel.get_by_token(token)
    except Exception as e:
        logger.warning(f"Session fetch error: {e}")

    # Without a stored access_token we can't call Discord; return empty list (non-bloquant).
    if not session_row:
        return JSONResponse(
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            content={"guilds": []},
        )

    access_token = session_row.get("access_token")
    if not access_token:
        return JSONResponse(
            headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            content={"guilds": []},
        )

    headers = {"Authorization": f"Bearer {access_token}"}
    async with aiohttp.ClientSession() as session:
        guilds_resp = await session.get(f"{DISCORD_API_BASE}/users/@me/guilds", headers=headers)
        guilds = await guilds_resp.json() if guilds_resp.status == 200 else []

    filtered = _build_filtered_guilds(guilds)
    return JSONResponse(
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
        content={"guilds": filtered},
    )


@router.post("/logout")
async def logout(request: Request):
    """Invalide la session en DB."""
    token = _get_bearer_token_from_request(request)
    if not token:
        try:
            body = await request.json()
            token = body.get("token")
        except Exception:
            pass
    if token:
        try:
            DashboardSessionModel.revoke_token(token)
        except Exception as e:
            logger.warning(f"Logout DB error: {e}")
    return JSONResponse(content={"status": "success"})
