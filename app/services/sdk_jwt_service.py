"""
SDK JWT生成サービス
Zoom Meeting SDK用のJWTトークンを生成する
"""
import time
import logging
from typing import Optional

import jwt

from app.zoom_config import zoom_config

logger = logging.getLogger(__name__)


class SDKJwtService:
    """Zoom Meeting SDK用JWT生成サービス"""
    
    def generate_jwt(
        self,
        meeting_number: str,
        role: int = 0,
        expiration_seconds: int = 7200
    ) -> Optional[str]:
        """
        Meeting SDK用のJWTを生成
        
        Args:
            meeting_number: 会議番号（数字のみ）
            role: 参加者ロール（0=参加者, 1=ホスト）
            expiration_seconds: トークン有効期限（デフォルト2時間）
        
        Returns:
            JWTトークン、または生成失敗時はNone
        """
        if not zoom_config.sdk_key or not zoom_config.sdk_secret:
            logger.error(
                "SDK設定が不完全です。"
                "ZOOM_SDK_KEY, ZOOM_SDK_SECRET を設定してください。"
            )
            return None
        
        # 会議番号から非数字を除去
        clean_meeting_number = ''.join(filter(str.isdigit, meeting_number))
        
        iat = int(time.time())
        exp = iat + expiration_seconds
        
        payload = {
            "appKey": zoom_config.sdk_key,  # Documentation requires appKey (Client ID)
            "mn": clean_meeting_number,
            "role": role,
            "iat": iat,
            "exp": exp,
            "tokenExp": exp
        }
        
        try:
            token = jwt.encode(
                payload,
                zoom_config.sdk_secret,
                algorithm="HS256"
            )
            logger.info(
                f"SDK JWT生成完了: meeting={clean_meeting_number}, "
                f"role={role}, exp={exp}"
            )
            return token
        except Exception as e:
            logger.error(f"SDK JWT生成中にエラーが発生: {e}")
            return None
    
    def is_configured(self) -> bool:
        """SDK設定が完了しているかチェック"""
        return bool(zoom_config.sdk_key and zoom_config.sdk_secret)


# シングルトンインスタンス
sdk_jwt_service = SDKJwtService()
