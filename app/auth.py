"""
Azure AD (Entra ID) JWT検証とユーザー認証・認可依存性

テストモード:
  Azure AD未設定時（AZURE_AD_TENANT_ID が未設定 or placeholder）は
  ダミーユーザーで動作する。
  - デフォルト: 管理者ユーザー（全件閲覧可）
  - ヘッダー X-Test-Email を指定すると、そのメールでNotion検索し一般ユーザーとして動作
  - ヘッダー X-Test-Role: admin を指定するとダミー管理者に切替
"""
import logging
from typing import Optional

import httpx
from cachetools import TTLCache
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.notion_user_service import get_notion_user_service

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)

_jwks_cache: TTLCache = TTLCache(maxsize=1, ttl=3600)

# --- Azure AD が有効かどうか ---
_PLACEHOLDER_VALUES = {"", "your-tenant-id-here", "your-client-id-here"}


def _is_azure_ad_configured() -> bool:
    tid = (settings.AZURE_AD_TENANT_ID or "").strip()
    cid = (settings.AZURE_AD_CLIENT_ID or "").strip()
    return tid not in _PLACEHOLDER_VALUES and cid not in _PLACEHOLDER_VALUES


# --- JWKS / JWT（本番用） ---

async def _get_jwks() -> dict:
    """Azure ADのJWKS（公開鍵セット）を取得。TTLキャッシュ付き。"""
    cached = _jwks_cache.get("jwks")
    if cached:
        return cached

    async with httpx.AsyncClient() as client:
        resp = await client.get(settings.azure_jwks_uri, timeout=10.0)
        resp.raise_for_status()
        jwks = resp.json()

    _jwks_cache["jwks"] = jwks
    return jwks


def _decode_token(token: str, jwks: dict) -> dict:
    """Azure AD JWTトークンを検証してペイロードを返す。"""
    try:
        unverified_header = jwt.get_unverified_header(token)
    except JWTError as e:
        raise JWTError(f"トークンヘッダー解析エラー: {e}")

    rsa_key = {}
    for key in jwks.get("keys", []):
        if key.get("kid") == unverified_header.get("kid"):
            rsa_key = {
                "kty": key["kty"],
                "kid": key["kid"],
                "use": key.get("use", "sig"),
                "n": key["n"],
                "e": key["e"],
            }
            break

    if not rsa_key:
        raise JWTError("一致する署名鍵が見つかりません")

    payload = jwt.decode(
        token,
        rsa_key,
        algorithms=["RS256"],
        audience=settings.AZURE_AD_CLIENT_ID,
        issuer=settings.azure_ad_issuer,
        options={"verify_exp": True},
    )
    return payload


# --- ダミーユーザー（テストモード用） ---

async def _get_test_user(
    db: Session,
    test_email: Optional[str],
    test_role: Optional[str],
) -> User:
    """
    Azure AD未設定時のダミーユーザーを返す。
    X-Test-Email でメール指定 → Notion検索して一般ユーザー扱い
    X-Test-Role: admin → 管理者
    何も指定なし → デフォルト管理者（既存動作を維持）
    """
    is_admin = True  # デフォルト: 管理者（認証なし時の既存動作を維持）
    email = test_email or "test-admin@example.com"
    azure_user_id = f"test-{email}"

    if test_email and (not test_role or test_role.lower() != "admin"):
        # メール指定 + 非admin → 一般ユーザー
        is_admin = False

    if test_role and test_role.lower() == "admin":
        is_admin = True

    # DB から既存ユーザーを検索 or 作成
    user = db.query(User).filter(User.azure_user_id == azure_user_id).first()
    if user is None:
        user = User(azure_user_id=azure_user_id, email=email, is_admin=is_admin)
        # Notion ユーザー解決
        notion_user_svc = get_notion_user_service()
        if notion_user_svc.enabled and email and email != "test-admin@example.com":
            notion_page_id = await notion_user_svc.resolve_by_email(email)
            user.notion_user_page_id = notion_page_id
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"[テストモード] ユーザー作成: {email}, admin={is_admin}, notion={user.notion_user_page_id}")
    else:
        updated = False
        if user.is_admin != is_admin:
            user.is_admin = is_admin
            updated = True
        if not user.notion_user_page_id and email and email != "test-admin@example.com":
            notion_user_svc = get_notion_user_service()
            if notion_user_svc.enabled:
                notion_page_id = await notion_user_svc.resolve_by_email(email)
                if notion_page_id:
                    user.notion_user_page_id = notion_page_id
                    updated = True
        if updated:
            db.commit()

    return user


# --- メイン依存性 ---

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
    x_test_email: Optional[str] = Header(None),
    x_test_role: Optional[str] = Header(None),
) -> User:
    """
    BearerトークンをAzure ADで検証し、Userオブジェクトを返す。
    Azure AD未設定時はテストモードでダミーユーザーを返す。
    """
    # --- テストモード ---
    if not _is_azure_ad_configured():
        return await _get_test_user(db, x_test_email, x_test_role)

    # --- 本番モード: JWT検証 ---
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="認証が必要です",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        raise credentials_exception

    try:
        jwks = await _get_jwks()
        payload = _decode_token(credentials.credentials, jwks)
    except JWTError as e:
        logger.warning(f"JWT検証失敗: {e}")
        raise credentials_exception
    except Exception as e:
        logger.error(f"JWT検証中に予期しないエラー: {e}")
        raise credentials_exception

    azure_user_id: Optional[str] = payload.get("oid")
    if not azure_user_id:
        logger.warning("JWTに 'oid' クレームが含まれていません")
        raise credentials_exception

    email: Optional[str] = payload.get("preferred_username") or payload.get("email")
    roles: list = payload.get("roles", [])
    is_admin = "Admin" in roles

    user = db.query(User).filter(User.azure_user_id == azure_user_id).first()
    if user is None:
        user = User(azure_user_id=azure_user_id, email=email, is_admin=is_admin)
        notion_user_svc = get_notion_user_service()
        if notion_user_svc.enabled and email:
            notion_page_id = await notion_user_svc.resolve_by_email(email)
            user.notion_user_page_id = notion_page_id
        db.add(user)
        db.commit()
        db.refresh(user)
        logger.info(f"新規ユーザーを登録しました: {azure_user_id}, email={email}, admin={is_admin}")
    else:
        updated = False
        if user.is_admin != is_admin:
            user.is_admin = is_admin
            updated = True
        if email and user.email != email:
            user.email = email
            updated = True
        if not user.notion_user_page_id and email:
            notion_user_svc = get_notion_user_service()
            if notion_user_svc.enabled:
                notion_page_id = await notion_user_svc.resolve_by_email(email)
                if notion_page_id:
                    user.notion_user_page_id = notion_page_id
                    updated = True
        if updated:
            db.commit()
            logger.info(f"ユーザー情報を更新: {azure_user_id}, admin={is_admin}")

    return user


async def get_authorized_project_ids(
    current_user: User = Depends(get_current_user),
) -> Optional[set[str]]:
    """
    認可済み案件IDセットを返す。
    - 管理者: None（フィルタなし = 全件閲覧）
    - 一般ユーザー: 所属案件IDのset
    - Notion未連携: 空set（何も見えない）
    """
    if current_user.is_admin:
        return None  # 全件
    if not current_user.notion_user_page_id:
        return set()  # Notion未連携 → 閲覧不可
    notion_user_svc = get_notion_user_service()
    return await notion_user_svc.get_project_ids_for_user(
        current_user.notion_user_page_id
    )


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """管理者権限が必要なエンドポイント用の依存性。"""
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="管理者権限が必要です",
        )
    return current_user
