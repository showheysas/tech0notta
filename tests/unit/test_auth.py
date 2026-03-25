"""
app/auth.py の C0/C1 カバレッジテスト

C0 (命令網羅): 25 テストケース
C1 (分岐網羅): 12 追加テストケース
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from jose import JWTError
from fastapi import HTTPException

from app.models.user import User


# ============================================================
# _is_azure_ad_configured テスト
# ============================================================

class TestIsAzureAdConfigured:
    """C0: 4件, C1: 1件"""

    def test_both_set(self, monkeypatch):
        """C0: tenant_id, client_id 両方設定済み → True"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tenant-id")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-client-id")
        from app.auth import _is_azure_ad_configured
        assert _is_azure_ad_configured() is True

    def test_tenant_missing(self, monkeypatch):
        """C0: tenant_id 未設定 → False"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-client-id")
        from app.auth import _is_azure_ad_configured
        assert _is_azure_ad_configured() is False

    def test_client_missing(self, monkeypatch):
        """C0: client_id 未設定 → False"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tenant-id")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "")
        from app.auth import _is_azure_ad_configured
        assert _is_azure_ad_configured() is False

    def test_placeholder_values(self, monkeypatch):
        """C0: プレースホルダー値 → False"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "your-tenant-id-here")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "your-client-id-here")
        from app.auth import _is_azure_ad_configured
        assert _is_azure_ad_configured() is False

    def test_client_placeholder_only(self, monkeypatch):
        """C1: tid有効 + cid=placeholder → False"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tenant-id")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "your-client-id-here")
        from app.auth import _is_azure_ad_configured
        assert _is_azure_ad_configured() is False

    def test_none_values(self, monkeypatch):
        """C1: None値 → False"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", None)
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", None)
        from app.auth import _is_azure_ad_configured
        assert _is_azure_ad_configured() is False


# ============================================================
# _get_jwks テスト
# ============================================================

class TestGetJwks:
    """C0: 2件"""

    @pytest.mark.asyncio
    async def test_cache_miss(self, monkeypatch):
        """C0: キャッシュなし → HTTP取得 → キャッシュ保存"""
        from app.auth import _get_jwks, _jwks_cache
        _jwks_cache.clear()

        mock_jwks = {"keys": [{"kid": "test-kid", "kty": "RSA", "n": "abc", "e": "AQAB"}]}
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        monkeypatch.setattr("app.auth.httpx.AsyncClient", lambda: mock_client)

        result = await _get_jwks()
        assert result == mock_jwks
        assert _jwks_cache.get("jwks") == mock_jwks

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """C0: キャッシュあり → HTTP不要"""
        from app.auth import _get_jwks, _jwks_cache
        cached_jwks = {"keys": [{"kid": "cached-kid"}]}
        _jwks_cache["jwks"] = cached_jwks

        result = await _get_jwks()
        assert result == cached_jwks

        # cleanup
        _jwks_cache.clear()


# ============================================================
# _decode_token テスト
# ============================================================

class TestDecodeToken:
    """C0: 3件"""

    def test_success(self, mocker):
        """C0: 正常JWT → ペイロード返却"""
        from app.auth import _decode_token
        mocker.patch("app.auth.jwt.get_unverified_header", return_value={"kid": "key1"})
        mocker.patch("app.auth.jwt.decode", return_value={"oid": "user-123", "email": "a@b.com"})

        jwks = {"keys": [{"kid": "key1", "kty": "RSA", "n": "abc", "e": "AQAB"}]}
        result = _decode_token("fake-token", jwks)
        assert result["oid"] == "user-123"

    def test_invalid_header(self, mocker):
        """C0: 不正ヘッダー → JWTError"""
        from app.auth import _decode_token
        mocker.patch("app.auth.jwt.get_unverified_header", side_effect=JWTError("bad header"))

        with pytest.raises(JWTError, match="トークンヘッダー解析エラー"):
            _decode_token("bad-token", {"keys": []})

    def test_no_matching_key(self, mocker):
        """C0: kid不一致 → JWTError"""
        from app.auth import _decode_token
        mocker.patch("app.auth.jwt.get_unverified_header", return_value={"kid": "unknown-kid"})

        jwks = {"keys": [{"kid": "different-kid", "kty": "RSA", "n": "abc", "e": "AQAB"}]}
        with pytest.raises(JWTError, match="一致する署名鍵が見つかりません"):
            _decode_token("fake-token", jwks)

    def test_key_with_use_field(self, mocker):
        """C1: use フィールドあり → 正しく取得"""
        from app.auth import _decode_token
        mocker.patch("app.auth.jwt.get_unverified_header", return_value={"kid": "key1"})
        mocker.patch("app.auth.jwt.decode", return_value={"oid": "user-1"})

        jwks = {"keys": [{"kid": "key1", "kty": "RSA", "use": "sig", "n": "abc", "e": "AQAB"}]}
        result = _decode_token("token", jwks)
        assert result["oid"] == "user-1"

    def test_empty_keys_list(self, mocker):
        """C1: keys空リスト → forループ未実行 → JWTError"""
        from app.auth import _decode_token
        mocker.patch("app.auth.jwt.get_unverified_header", return_value={"kid": "key1"})

        with pytest.raises(JWTError, match="一致する署名鍵が見つかりません"):
            _decode_token("token", {"keys": []})


# ============================================================
# _get_test_user テスト
# ============================================================

class TestGetTestUser:
    """C0: 6件, C1: 5件"""

    @pytest.mark.asyncio
    async def test_default_admin(self, db_session, mock_notion_user_service):
        """C0: ヘッダーなし → admin=True, email=test-admin@example.com"""
        from app.auth import _get_test_user
        user = await _get_test_user(db_session, None, None)
        assert user.is_admin is True
        assert user.email == "test-admin@example.com"
        assert user.azure_user_id == "test-test-admin@example.com"

    @pytest.mark.asyncio
    async def test_email_specified_regular(self, db_session, mock_notion_user_service):
        """C0: email指定、role未指定 → admin=False"""
        from app.auth import _get_test_user
        user = await _get_test_user(db_session, "user@example.com", None)
        assert user.is_admin is False
        assert user.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_email_with_admin_role(self, db_session, mock_notion_user_service):
        """C0: email指定+role=admin → admin=True"""
        from app.auth import _get_test_user
        user = await _get_test_user(db_session, "user@example.com", "admin")
        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_new_user_with_notion_resolve(self, db_session, mock_notion_user_service):
        """C0: 新規ユーザー + Notion解決成功"""
        mock_notion_user_service.resolve_by_email.return_value = "notion-page-abc"
        from app.auth import _get_test_user
        user = await _get_test_user(db_session, "user@example.com", None)
        assert user.notion_user_page_id == "notion-page-abc"

    @pytest.mark.asyncio
    async def test_existing_user_update_admin(self, db_session, mock_notion_user_service):
        """C0: 既存ユーザー admin フラグ変更"""
        from app.auth import _get_test_user
        # まず admin=True で作成
        user1 = await _get_test_user(db_session, "change@example.com", "admin")
        assert user1.is_admin is True
        # admin=False に変更
        user2 = await _get_test_user(db_session, "change@example.com", None)
        assert user2.is_admin is False
        assert user1.azure_user_id == user2.azure_user_id

    @pytest.mark.asyncio
    async def test_existing_user_notion_resolve(self, db_session, mock_notion_user_service):
        """C0: 既存ユーザー Notion解決（notion_user_page_id が未設定の場合）"""
        from app.auth import _get_test_user
        # まず Notion 無しで作成
        mock_notion_user_service.resolve_by_email.return_value = None
        user1 = await _get_test_user(db_session, "resolve@example.com", None)
        assert user1.notion_user_page_id is None
        # 2回目で Notion 解決
        mock_notion_user_service.resolve_by_email.return_value = "notion-page-xyz"
        user2 = await _get_test_user(db_session, "resolve@example.com", None)
        assert user2.notion_user_page_id == "notion-page-xyz"

    # --- C1 追加 ---

    @pytest.mark.asyncio
    async def test_email_with_non_admin_role(self, db_session, mock_notion_user_service):
        """C1: email有り, role="user" → admin=False"""
        from app.auth import _get_test_user
        user = await _get_test_user(db_session, "user@example.com", "user")
        assert user.is_admin is False

    @pytest.mark.asyncio
    async def test_no_email_no_role(self, db_session, mock_notion_user_service):
        """C1: email=None, role=None → デフォルト admin=True"""
        from app.auth import _get_test_user
        user = await _get_test_user(db_session, None, None)
        assert user.is_admin is True
        assert user.email == "test-admin@example.com"

    @pytest.mark.asyncio
    async def test_existing_no_changes(self, db_session, mock_notion_user_service):
        """C1: 既存ユーザー変更なし → commit不要"""
        from app.auth import _get_test_user
        user1 = await _get_test_user(db_session, None, None)
        # 同じ条件で再度呼び出し → 変更なし
        user2 = await _get_test_user(db_session, None, None)
        assert user1.azure_user_id == user2.azure_user_id

    @pytest.mark.asyncio
    async def test_notion_disabled(self, db_session, mock_notion_user_service):
        """C1: notion_svc.enabled=False → Notion解決スキップ"""
        mock_notion_user_service.enabled = False
        from app.auth import _get_test_user
        user = await _get_test_user(db_session, "user@example.com", None)
        assert user.notion_user_page_id is None
        mock_notion_user_service.resolve_by_email.assert_not_called()

    @pytest.mark.asyncio
    async def test_existing_notion_resolve_returns_none(self, db_session, mock_notion_user_service):
        """C1: 既存ユーザー resolve_by_email→None → 更新なし"""
        from app.auth import _get_test_user
        # 1回目: Notion 解決失敗で作成
        mock_notion_user_service.resolve_by_email.return_value = None
        user1 = await _get_test_user(db_session, "nonotion@example.com", None)
        assert user1.notion_user_page_id is None
        # 2回目: まだ None → 更新なし
        mock_notion_user_service.resolve_by_email.return_value = None
        user2 = await _get_test_user(db_session, "nonotion@example.com", None)
        assert user2.notion_user_page_id is None


# ============================================================
# get_current_user テスト
# ============================================================

class TestGetCurrentUser:
    """C0: 7件, C1: 4件"""

    @pytest.mark.asyncio
    async def test_test_mode(self, db_session, monkeypatch, mock_notion_user_service):
        """C0: Azure AD未設定 → テストモード"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "")
        from app.auth import get_current_user
        user = await get_current_user(
            credentials=None, db=db_session, x_test_email=None, x_test_role=None
        )
        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_no_credentials(self, db_session, monkeypatch):
        """C0: credentials=None → 401"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        from app.auth import get_current_user
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                credentials=None, db=db_session, x_test_email=None, x_test_role=None
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_jwt_success_new_user(self, db_session, monkeypatch, mocker, mock_notion_user_service):
        """C0: JWT成功 + 新規ユーザー作成"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, return_value={"keys": []})
        mocker.patch("app.auth._decode_token", return_value={
            "oid": "new-user-oid",
            "preferred_username": "new@example.com",
            "roles": [],
        })
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "fake-jwt-token"
        user = await get_current_user(
            credentials=creds, db=db_session, x_test_email=None, x_test_role=None
        )
        assert user.azure_user_id == "new-user-oid"
        assert user.email == "new@example.com"
        assert user.is_admin is False

    @pytest.mark.asyncio
    async def test_jwt_success_existing_user(self, db_session, monkeypatch, mocker, mock_notion_user_service):
        """C0: JWT成功 + 既存ユーザー更新"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        # 既存ユーザーを事前作成
        existing = User(azure_user_id="existing-oid", email="old@example.com", is_admin=False)
        db_session.add(existing)
        db_session.commit()

        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, return_value={"keys": []})
        mocker.patch("app.auth._decode_token", return_value={
            "oid": "existing-oid",
            "preferred_username": "old@example.com",
            "roles": ["Admin"],
        })
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "fake-jwt"
        user = await get_current_user(
            credentials=creds, db=db_session, x_test_email=None, x_test_role=None
        )
        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_jwt_error(self, db_session, monkeypatch, mocker):
        """C0: JWTError → 401"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, side_effect=JWTError("bad"))
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "bad-jwt"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                credentials=creds, db=db_session, x_test_email=None, x_test_role=None
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_unexpected_error(self, db_session, monkeypatch, mocker):
        """C0: Exception → 401"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, side_effect=RuntimeError("unexpected"))
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "bad-jwt"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                credentials=creds, db=db_session, x_test_email=None, x_test_role=None
            )
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_no_oid_in_payload(self, db_session, monkeypatch, mocker):
        """C0: oidクレーム欠落 → 401"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, return_value={"keys": []})
        mocker.patch("app.auth._decode_token", return_value={"email": "no-oid@example.com"})
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "jwt-no-oid"
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(
                credentials=creds, db=db_session, x_test_email=None, x_test_role=None
            )
        assert exc_info.value.status_code == 401

    # --- C1 追加 ---

    @pytest.mark.asyncio
    async def test_preferred_username_fallback(self, db_session, monkeypatch, mocker, mock_notion_user_service):
        """C1: preferred_username=None → emailフォールバック"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, return_value={"keys": []})
        mocker.patch("app.auth._decode_token", return_value={
            "oid": "fallback-oid",
            "email": "fallback@example.com",
            "roles": [],
        })
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "jwt"
        user = await get_current_user(
            credentials=creds, db=db_session, x_test_email=None, x_test_role=None
        )
        assert user.email == "fallback@example.com"

    @pytest.mark.asyncio
    async def test_admin_role_in_jwt(self, db_session, monkeypatch, mocker, mock_notion_user_service):
        """C1: roles=["Admin"] → is_admin=True"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, return_value={"keys": []})
        mocker.patch("app.auth._decode_token", return_value={
            "oid": "admin-oid",
            "preferred_username": "admin@example.com",
            "roles": ["Admin"],
        })
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "jwt"
        user = await get_current_user(
            credentials=creds, db=db_session, x_test_email=None, x_test_role=None
        )
        assert user.is_admin is True

    @pytest.mark.asyncio
    async def test_existing_email_changed(self, db_session, monkeypatch, mocker, mock_notion_user_service):
        """C1: 既存ユーザーの email 変更検出"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        # 既存ユーザー
        existing = User(azure_user_id="email-change-oid", email="old@example.com", is_admin=False)
        db_session.add(existing)
        db_session.commit()

        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, return_value={"keys": []})
        mocker.patch("app.auth._decode_token", return_value={
            "oid": "email-change-oid",
            "preferred_username": "new@example.com",
            "roles": [],
        })
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "jwt"
        user = await get_current_user(
            credentials=creds, db=db_session, x_test_email=None, x_test_role=None
        )
        assert user.email == "new@example.com"

    @pytest.mark.asyncio
    async def test_existing_notion_resolve_success(self, db_session, monkeypatch, mocker, mock_notion_user_service):
        """C1: 既存ユーザー Notion解決成功 → page_id設定"""
        monkeypatch.setattr("app.auth.settings.AZURE_AD_TENANT_ID", "real-tid")
        monkeypatch.setattr("app.auth.settings.AZURE_AD_CLIENT_ID", "real-cid")
        # notion_user_page_id 未設定の既存ユーザー
        existing = User(azure_user_id="notion-oid", email="notion@example.com", is_admin=False)
        db_session.add(existing)
        db_session.commit()

        mock_notion_user_service.resolve_by_email.return_value = "notion-page-new"
        mocker.patch("app.auth._get_jwks", new_callable=AsyncMock, return_value={"keys": []})
        mocker.patch("app.auth._decode_token", return_value={
            "oid": "notion-oid",
            "preferred_username": "notion@example.com",
            "roles": [],
        })
        from app.auth import get_current_user
        creds = MagicMock()
        creds.credentials = "jwt"
        user = await get_current_user(
            credentials=creds, db=db_session, x_test_email=None, x_test_role=None
        )
        assert user.notion_user_page_id == "notion-page-new"


# ============================================================
# get_authorized_project_ids テスト
# ============================================================

class TestGetAuthorizedProjectIds:
    """C0: 3件"""

    @pytest.mark.asyncio
    async def test_admin_returns_none(self, test_user, mock_notion_user_service):
        """C0: admin → None（全件閲覧）"""
        from app.auth import get_authorized_project_ids
        result = await get_authorized_project_ids(current_user=test_user)
        assert result is None

    @pytest.mark.asyncio
    async def test_no_notion_returns_empty_set(self, db_session, mock_notion_user_service):
        """C0: notion未連携 → 空set"""
        user = User(azure_user_id="no-notion", email="x@x.com", is_admin=False)
        db_session.add(user)
        db_session.commit()
        from app.auth import get_authorized_project_ids
        result = await get_authorized_project_ids(current_user=user)
        assert result == set()

    @pytest.mark.asyncio
    async def test_regular_user_returns_project_set(self, test_regular_user, mock_notion_user_service):
        """C0: 一般ユーザー → プロジェクトset"""
        mock_notion_user_service.get_project_ids_for_user.return_value = {"proj-1", "proj-2"}
        from app.auth import get_authorized_project_ids
        result = await get_authorized_project_ids(current_user=test_regular_user)
        assert result == {"proj-1", "proj-2"}


# ============================================================
# require_admin テスト
# ============================================================

class TestRequireAdmin:
    """C0: 2件"""

    def test_is_admin(self, test_user):
        """C0: admin=True → ユーザー返却"""
        from app.auth import require_admin
        result = require_admin(current_user=test_user)
        assert result.is_admin is True

    def test_not_admin(self, test_regular_user):
        """C0: admin=False → 403"""
        from app.auth import require_admin
        with pytest.raises(HTTPException) as exc_info:
            require_admin(current_user=test_regular_user)
        assert exc_info.value.status_code == 403
