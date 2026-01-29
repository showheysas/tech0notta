from openai import AzureOpenAI
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class AzureOpenAIService:
    def __init__(self):
        self.client = AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
        self.deployment_name = settings.AZURE_OPENAI_DEPLOYMENT_NAME

    def generate_summary(self, transcription: str) -> str:
        try:
            system_prompt = """あなたは議事録を要約する専門家です。
以下の議事録を、次の形式で要約してください:

## 概要
会議の全体的な目的と主なトピックを簡潔にまとめてください。

## 主な議題
- 議論された主要なトピックをリスト形式で記載
- それぞれのポイントについて簡潔に説明

## 決定事項
- 会議で決まった事項をリスト形式で記載
- 具体的な決定内容を明確に

## アクションアイテム
- 誰が何をいつまでにするかを明記
- フォローアップが必要な項目

## 次回の議題
- 次回の会議で取り上げるべき項目があれば記載

簡潔で分かりやすい日本語でまとめてください。"""

            response = self.client.chat.completions.create(
                model=self.deployment_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"以下の議事録を要約してください:\n\n{transcription}"}
                ],
                temperature=0.3,
                max_tokens=2000
            )

            summary = response.choices[0].message.content
            logger.info(f"Summary generated: {len(summary)} characters")
            return summary

        except Exception as e:
            logger.error(f"Error generating summary: {e}")
            raise


_azure_openai_service = None


def get_azure_openai_service() -> AzureOpenAIService:
    global _azure_openai_service
    if _azure_openai_service is None:
        _azure_openai_service = AzureOpenAIService()
    return _azure_openai_service
