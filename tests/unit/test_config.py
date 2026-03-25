"""
app/config.py の C0/C1 カバレッジテスト

C0 (命令網羅): 6 テストケース
C1 (分岐網羅): 0 (分岐なし)
"""
import pytest


class TestSettings:
    """C0: 6件"""

    def test_defaults(self):
        """C0: デフォルト値が正しいこと"""
        from app.config import settings
        assert settings.DATABASE_URL == "sqlite:///./meeting_notes.db" or settings.DATABASE_URL.startswith("sqlite")
        assert settings.AZURE_STORAGE_CONTAINER_NAME == "audio-files"
        assert settings.AZURE_SPEECH_REGION == "japaneast"
        assert settings.AZURE_OPENAI_DEPLOYMENT_NAME == "gpt-4o"
        assert settings.MAX_FILE_SIZE_MB == 200
        assert settings.ACA_BOT_MODE == "job"

    def test_azure_jwks_uri(self, monkeypatch):
        """C0: azure_jwks_uri に tenant_id が含まれること"""
        monkeypatch.setattr("app.config.settings.AZURE_AD_TENANT_ID", "test-tenant-123")
        from app.config import settings
        uri = settings.azure_jwks_uri
        assert "test-tenant-123" in uri
        assert "discovery/v2.0/keys" in uri

    def test_azure_ad_issuer(self, monkeypatch):
        """C0: azure_ad_issuer に tenant_id が含まれること"""
        monkeypatch.setattr("app.config.settings.AZURE_AD_TENANT_ID", "test-tenant-456")
        from app.config import settings
        issuer = settings.azure_ad_issuer
        assert "test-tenant-456" in issuer
        assert "/v2.0" in issuer

    def test_cors_origins_list_multiple(self):
        """C0: カンマ区切り複数オリジン"""
        from app.config import settings
        origins = settings.cors_origins_list
        assert isinstance(origins, list)
        assert len(origins) >= 1
        # デフォルトに localhost:3000 が含まれる
        assert any("localhost:3000" in o for o in origins)

    def test_cors_origins_list_single(self, monkeypatch):
        """C0: 単一オリジン"""
        monkeypatch.setattr("app.config.settings.CORS_ORIGINS", "http://localhost:8080")
        from app.config import settings
        origins = settings.cors_origins_list
        assert origins == ["http://localhost:8080"]

    def test_max_file_size_bytes(self):
        """C0: MB→bytes 変換"""
        from app.config import settings
        assert settings.max_file_size_bytes == settings.MAX_FILE_SIZE_MB * 1024 * 1024
