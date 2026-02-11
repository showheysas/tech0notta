"""
メタデータ抽出サービス - 議事録からメタデータを自動抽出

Azure OpenAIを使用して議事録テキストから会議メタデータを抽出します。
"""
from typing import Optional, List
from datetime import date
from app.services.azure_openai import get_azure_openai_service
from fastapi import HTTPException
import logging
import json

logger = logging.getLogger(__name__)


class MeetingMetadata:
    """会議メタデータ"""
    def __init__(
        self,
        mtg_name: Optional[str] = None,
        participants: Optional[List[str]] = None,
        company_name: Optional[str] = None,
        meeting_date: Optional[str] = None,
        meeting_type: Optional[str] = None,
        project: Optional[str] = None,
        key_stakeholders: Optional[List[str]] = None,
        key_team: Optional[str] = None,
        search_keywords: Optional[str] = None,
        is_knowledge: bool = False,
        materials_url: Optional[str] = None,
        notes: Optional[str] = None,
        related_meetings: Optional[List[str]] = None
    ):
        self.mtg_name = mtg_name
        self.participants = participants or []
        self.company_name = company_name
        self.meeting_date = meeting_date
        self.meeting_type = meeting_type
        self.project = project
        self.key_stakeholders = key_stakeholders or []
        self.key_team = key_team
        self.search_keywords = search_keywords
        self.is_knowledge = is_knowledge
        self.materials_url = materials_url
        self.notes = notes
        self.related_meetings = related_meetings or []
    
    def to_dict(self) -> dict:
        return {
            "mtg_name": self.mtg_name,
            "participants": self.participants,
            "company_name": self.company_name,
            "meeting_date": self.meeting_date,
            "meeting_type": self.meeting_type,
            "project": self.project,
            "key_stakeholders": self.key_stakeholders,
            "key_team": self.key_team,
            "search_keywords": self.search_keywords,
            "is_knowledge": self.is_knowledge,
            "materials_url": self.materials_url,
            "notes": self.notes,
            "related_meetings": self.related_meetings
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MeetingMetadata":
        return cls(
            mtg_name=data.get("mtg_name"),
            participants=data.get("participants", []),
            company_name=data.get("company_name"),
            meeting_date=data.get("meeting_date"),
            meeting_type=data.get("meeting_type"),
            project=data.get("project"),
            key_stakeholders=data.get("key_stakeholders", []),
            key_team=data.get("key_team"),
            search_keywords=data.get("search_keywords"),
            is_knowledge=data.get("is_knowledge", False),
            materials_url=data.get("materials_url"),
            notes=data.get("notes"),
            related_meetings=data.get("related_meetings", [])
        )


class MetadataService:
    """メタデータ抽出サービス"""
    
    async def extract_metadata(
        self, 
        summary: str, 
        transcription: Optional[str] = None,
        default_date: Optional[date] = None
    ) -> MeetingMetadata:
        """
        議事録からメタデータを自動抽出する
        
        Args:
            summary: 議事録の要約テキスト
            transcription: 文字起こしテキスト（オプション）
            default_date: デフォルトの会議日（抽出できない場合に使用）
        
        Returns:
            抽出されたメタデータ
        
        Raises:
            HTTPException: AI処理エラー
        """
        try:
            logger.info("Extracting metadata from meeting summary")
            
            openai_service = get_azure_openai_service()
            
            # メタデータ抽出用プロンプト
            system_prompt = """あなたは議事録分析の専門家です。
以下の議事録から、会議のメタデータを抽出してください。

以下のJSON形式で出力してください:
{
  "mtg_name": "会議の名称（例：「QTnet案件 定例会議」）",
  "participants": ["参加者1", "参加者2"],
  "company_name": "関連する企業名（顧客企業など）",
  "meeting_date": "会議の開催日（YYYY-MM-DD形式）",
  "meeting_type": "会議の種別（定例/商談/社内/キックオフ/レビュー/その他）",
  "project": "関連する案件・プロジェクト名",
  "key_stakeholders": ["重要な共有先となる人物"],
  "key_team": "重要な共有先となるチーム（営業/開発/企画/経営/その他）",
  "search_keywords": "検索用キーワード（カンマ区切り）"
}

ルール:
1. 明示されていない項目はnullを設定してください
2. 参加者名は敬称を除いて抽出してください（「田中さん」→「田中」）
3. 日付が明示されていない場合はnullを設定してください
4. 会議の種別は内容から推定してください
5. 検索キーワードは会議の主要トピックから3-5個抽出してください
6. 必ずJSON形式で出力してください
7. **mtg_nameは必ず設定してください。会議の内容から適切な名称を生成してください（例：「札幌ビルアプリ開発 進捗確認会議」）**
8. **company_nameは顧客企業や関連企業名を抽出してください**
9. **key_stakeholdersは会議で言及された重要人物を抽出してください**"""

            # 文字起こしテキストがある場合は追加
            transcription_text = ""
            if transcription:
                # 長すぎる場合は先頭部分のみ使用
                max_length = 3000
                if len(transcription) > max_length:
                    transcription_text = f"\n\n【文字起こしテキスト（抜粋）】\n{transcription[:max_length]}..."
                else:
                    transcription_text = f"\n\n【文字起こしテキスト】\n{transcription}"
            
            user_prompt = f"""【議事録要約】
{summary}{transcription_text}

上記の議事録からメタデータを抽出してください。"""

            # Azure OpenAI APIを呼び出し
            response = openai_service.client.chat.completions.create(
                model=openai_service.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content
            logger.info(f"Metadata extraction response: {content}")
            
            result = json.loads(content)
            
            # デフォルト日付の適用
            if not result.get("meeting_date") and default_date:
                result["meeting_date"] = default_date.isoformat()
            
            # 会議名がnullの場合、プロジェクト名から生成
            if not result.get("mtg_name"):
                if result.get("project"):
                    result["mtg_name"] = f"{result['project']} 会議"
                else:
                    result["mtg_name"] = "社内会議"
            
            metadata = MeetingMetadata.from_dict(result)
            
            logger.info(f"Extracted metadata: mtg_name={metadata.mtg_name}, participants={len(metadata.participants)}")
            
            return metadata
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse metadata response as JSON: {e}")
            raise HTTPException(
                status_code=500,
                detail="メタデータ抽出に失敗しました。AI応答の形式が不正です。"
            )
        except Exception as e:
            logger.error(f"Error extracting metadata: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"メタデータ抽出に失敗しました: {str(e)}"
            )


# シングルトンインスタンス
_metadata_service: Optional[MetadataService] = None


def get_metadata_service() -> MetadataService:
    """MetadataServiceのシングルトンインスタンスを取得"""
    global _metadata_service
    if _metadata_service is None:
        _metadata_service = MetadataService()
    return _metadata_service
